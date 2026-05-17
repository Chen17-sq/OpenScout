"""Deep-dive: on-demand intensive enrichment for a single researcher.

Per user (Chinese VC): the daily cron only does shallow signals at scale —
sparse pages for auto-discovered first-authors hurt trust ("我点进去发现它
其实没啥信息"). Deep-dive is the manual override: 5 sources hit in one call,
results persisted forever, re-run only refreshes sources older than 30 days
so we don't burn API quota.

Sources (in priority order — early exits if researcher has no relevant id):

  1. arxiv_author          search arxiv by name, pull full work list
  2. openalex_full         pull all works (remove the 80 cap from anchor backfill)
  3. github_profile        if github_handle → /users/{h} bio/org/loc + top repos
  4. huggingface_profile   if has HF model signals → user page + model downloads
  5. homepage_llm          if homepage_url → fetch HTML, DeepSeek extracts
                           bio / advisor / interests / graduation year

Each source returns a dict {ok: bool, fields_set: int, note: str}. The
orchestrator merges + writes provenance to `deep_dive_sources_used` JSON.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher, Signal
from . import llm

STALE_AFTER_DAYS = 30
HEADERS = {"User-Agent": "OpenScout/1.6 (+https://github.com/Chen17-sq/OpenScout)"}


# ── source 1: arxiv author search ──────────────────────────────────────────


def _arxiv_author(db, r: Researcher, http: httpx.Client) -> dict:
    """Search arXiv by author name, INGEST any papers we don't yet have.

    The previous version only noted IDs found; that's useless data. Now we
    actually fetch the paper metadata + insert into our DB so the next
    page render shows them. Links the researcher to each new paper at
    their byline position.

    Disambiguation: we don't try hard on common names — we trust that the
    name + first/last 2 keyword overlap with the existing DB is enough for
    auto-discovered researchers. False-positive papers can be cleaned later.
    """
    if not r.name_en:
        return {"ok": False, "fields_set": 0, "note": "no name"}

    import arxiv  # heavy import, only when needed

    try:
        search = arxiv.Search(
            query=f'au:"{r.name_en}"',
            max_results=30,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        client = arxiv.Client(page_size=30, delay_seconds=3.0, num_retries=2)
        results = list(client.results(search))
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    if not results:
        return {"ok": True, "fields_set": 0, "note": "no arxiv hits"}

    from .arxiv import _normalize_arxiv_id, _upsert_researcher_by_name

    added = 0
    linked_to_us = 0
    for res in results:
        arxiv_id = _normalize_arxiv_id(res.entry_id)
        paper = db.execute(select(Paper).where(Paper.arxiv_id == arxiv_id)).scalar_one_or_none()
        is_new = paper is None
        if is_new:
            paper = Paper(
                arxiv_id=arxiv_id,
                title=res.title.strip(),
                abstract=res.summary.strip(),
                published_at=res.published.date() if res.published else None,
                pdf_url=res.pdf_url,
                venue="arXiv",
            )
            db.add(paper)
            db.flush()
            added += 1

        # Check if THIS researcher is on the byline; if so, link
        our_position = None
        for pos, author in enumerate(res.authors, start=1):
            if author.name.strip().lower() == r.name_en.strip().lower():
                our_position = pos
                break

        if our_position is not None:
            # Avoid duplicate PaperAuthor row
            existing_link = db.execute(
                select(PaperAuthor).where(
                    PaperAuthor.paper_id == paper.id,
                    PaperAuthor.researcher_id == r.id,
                )
            ).scalar_one_or_none()
            if not existing_link:
                db.add(PaperAuthor(paper_id=paper.id, researcher_id=r.id, position=our_position))
                linked_to_us += 1

        # For new papers, also ensure the other authors get researcher rows.
        # We only do this for NEW papers (existing papers already have their
        # author links from the original ingest).
        # Dedupe guard: different name spellings of the same person (e.g.
        # "X. Wang" + "Xinyi Wang") collapse to the same Researcher row, which
        # would violate the PaperAuthor (paper_id, researcher_id) UNIQUE
        # constraint. Track who we've already linked for THIS paper.
        if is_new:
            seen_rids: set[int] = {int(r.id)} if our_position is not None else set()
            for pos, author in enumerate(res.authors, start=1):
                if our_position is not None and pos == our_position:
                    continue
                co = _upsert_researcher_by_name(db, author.name)
                if co.id in seen_rids:
                    continue
                seen_rids.add(int(co.id))
                db.add(PaperAuthor(paper_id=paper.id, researcher_id=co.id, position=pos))

    return {
        "ok": True,
        "fields_set": added + linked_to_us,
        "note": f"+{added} new papers · +{linked_to_us} byline links",
    }


# ── source 1.5: OpenAlex author auto-match ─────────────────────────────────


def _openalex_match(db, r: Researcher, http: httpx.Client) -> dict:
    """For researchers WITHOUT an openalex_id, try to find one.

    Strategy: search OpenAlex authors by name, then disambiguate by checking
    whether any of the returned candidates' top works overlap with the
    researcher's known paper DOIs in our DB. The first candidate with
    overlap wins.

    Without this, every auto-discovered researcher (the 1,200+ we surfaced
    via surname inference) hits a wall on the 3 OpenAlex-dependent sources.
    """
    if r.openalex_id:
        return {"ok": True, "fields_set": 0, "note": "already matched"}
    if not r.name_en:
        return {"ok": False, "fields_set": 0, "note": "no name"}

    # Get our known DOIs for this researcher — used to disambiguate candidates
    our_dois = {
        doi.lower()
        for (doi,) in db.execute(
            select(Paper.doi)
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(PaperAuthor.researcher_id == r.id, Paper.doi.is_not(None))
        ).all()
    }
    our_arxiv_ids = {
        aid
        for (aid,) in db.execute(
            select(Paper.arxiv_id)
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(
                PaperAuthor.researcher_id == r.id,
                Paper.arxiv_id.is_not(None),
                Paper.arxiv_id.notlike("or-%"),
            )
        ).all()
    }

    name_q = httpx.QueryParams({"search": r.name_en, "per-page": "10"})
    try:
        rr = http.get(f"https://api.openalex.org/authors?{name_q}", timeout=15.0)
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        candidates = rr.json().get("results") or []
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    if not candidates:
        return {"ok": True, "fields_set": 0, "note": "no OpenAlex hits for name"}

    # Strict mode: require DOI / arxiv overlap to claim a match. Without overlap
    # signal, fall back to top-candidate ONLY if the researcher has just one
    # OpenAlex hit (i.e. unambiguous name).
    for cand in candidates[:5]:
        cand_id = (cand.get("id") or "").rsplit("/", 1)[-1]
        if not cand_id:
            continue
        try:
            wr = http.get(
                f"https://api.openalex.org/works?filter=author.id:{cand_id}&per-page=25"
                "&select=doi,ids,title",
                timeout=15.0,
            )
            if wr.status_code != 200:
                continue
            works = wr.json().get("results") or []
        except Exception:
            continue

        overlap = False
        for w in works:
            wdoi = (w.get("doi") or "").lower().replace("https://doi.org/", "")
            if wdoi and wdoi in our_dois:
                overlap = True
                break
            ids = w.get("ids") or {}
            mag = (ids.get("mag") or "").lower()
            if mag and any(aid in mag for aid in our_arxiv_ids):
                overlap = True
                break

        if overlap:
            r.openalex_id = cand.get("id")
            if not r.h_index and cand.get("summary_stats"):
                r.h_index = cand["summary_stats"].get("h_index")
            return {
                "ok": True,
                "fields_set": 1,
                "note": f"matched {cand_id} via DOI/arxiv overlap",
            }

    # Single-hit fallback: rare name, only 1 candidate, no overlap available
    if len(candidates) == 1 and (our_dois or our_arxiv_ids):
        cand = candidates[0]
        r.openalex_id = cand.get("id")
        return {
            "ok": True,
            "fields_set": 1,
            "note": f"matched {cand.get('id', '').rsplit('/', 1)[-1]} (unambiguous name)",
        }

    return {"ok": True, "fields_set": 0, "note": f"{len(candidates)} candidates, no overlap"}


# ── source 1.6: Semantic Scholar author discovery ──────────────────────────


def _semantic_scholar_discover(db, r: Researcher, http: httpx.Client) -> dict:
    """Search S2 by name → set semantic_scholar_id + homepage_url + h_index + cites.

    This is the BIG unlock: most researchers have an S2 profile with a
    `homepage` field that we'd otherwise never know. With homepage populated,
    `homepage_llm` below can finally run.

    Disambiguation: if we have S2 paper IDs for this researcher (from the
    existing semanticscholar enrichment), pick the author whose top papers
    overlap. Otherwise prefer the first candidate whose `paperCount` is
    plausible (3-500 range).
    """
    if r.semantic_scholar_id and r.h_index is not None:
        return {"ok": True, "fields_set": 0, "note": "already matched"}
    if not r.name_en:
        return {"ok": False, "fields_set": 0, "note": "no name"}

    from ..config import settings

    s2_headers = {}
    if settings.semantic_scholar_api_key:
        s2_headers["x-api-key"] = settings.semantic_scholar_api_key

    try:
        rr = http.get(
            "https://api.semanticscholar.org/graph/v1/author/search",
            params={
                "query": r.name_en,
                "limit": 10,
                "fields": "name,affiliations,homepage,paperCount,citationCount,hIndex,papers.title",
            },
            headers=s2_headers,
            timeout=15.0,
        )
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        data = rr.json().get("data") or []
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    if not data:
        return {"ok": True, "fields_set": 0, "note": "no S2 hits"}

    # Get our paper titles for fuzzy overlap matching
    our_titles = {
        (t or "").lower().strip()
        for (t,) in db.execute(
            select(Paper.title)
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(PaperAuthor.researcher_id == r.id)
        ).all()
    }

    # Score by title overlap ONLY — plausibility-band is too weak, multiple
    # "Wang Jing"s pass it. With title overlap we know it's the same person.
    best = None
    best_overlap = 0
    for cand in data[:8]:
        cand_titles = {(p.get("title") or "").lower().strip() for p in (cand.get("papers") or [])}
        overlap = len(cand_titles & our_titles)
        if overlap > best_overlap:
            best_overlap = overlap
            best = cand

    if not best or best_overlap == 0:
        # No overlap = ambiguous; only safe to accept single-candidate
        # AND only if that candidate has a plausible paper count for our researcher
        if len(data) == 1 and our_titles:
            single = data[0]
            pc = single.get("paperCount") or 0
            if 3 <= pc <= 500:
                best = single
            else:
                return {
                    "ok": True,
                    "fields_set": 0,
                    "note": f"1 candidate but implausible (pc={pc})",
                }
        else:
            return {
                "ok": True,
                "fields_set": 0,
                "note": f"{len(data)} candidates, no title overlap (ambiguous)",
            }

    updated = 0
    if not r.semantic_scholar_id and best.get("authorId"):
        r.semantic_scholar_id = best["authorId"]
        updated += 1
    if not r.homepage_url and best.get("homepage"):
        r.homepage_url = best["homepage"]
        updated += 1
    if not r.h_index and best.get("hIndex") is not None:
        r.h_index = int(best["hIndex"])
        updated += 1
    if (not r.citation_count or r.citation_count < (best.get("citationCount") or 0)) and best.get(
        "citationCount"
    ):
        r.citation_count = int(best["citationCount"])
        updated += 1
    affs = best.get("affiliations") or []
    if affs and not r.bio:
        # Provisional bio if homepage_llm hasn't fired yet; will be overwritten
        # by the LLM-synthesized one later in the pipeline.
        r.bio = f"{affs[0]} · (per Semantic Scholar)"
        updated += 1

    return {
        "ok": True,
        "fields_set": updated,
        "note": (
            f"S2 {best.get('authorId')} · h={best.get('hIndex')} · {best.get('paperCount')} papers"
            + (" · homepage ✓" if best.get("homepage") else "")
        ),
    }


# ── source 1.7: GitHub user discovery ──────────────────────────────────────


def _github_discover(db, r: Researcher, http: httpx.Client) -> dict:
    """Search GitHub users by name + heuristic-pick a research-y account.

    Without this, github_profile below only fires for the ~50 researchers
    we manually entered github_handle for. With this, any researcher gets
    a GitHub auto-discovery attempt.

    Heuristic: prefer accounts where bio mentions PhD/research/CS/AI, or
    company is a known academic affiliation. Skip handles that look like
    bots / companies (uppercase, > 14 chars, etc.).
    """
    if r.github_handle:
        return {"ok": True, "fields_set": 0, "note": "already has handle"}
    if not r.name_en:
        return {"ok": False, "fields_set": 0, "note": "no name"}

    gh_headers = HEADERS.copy()
    gh_token = os.environ.get("GITHUB_TOKEN")
    if gh_token:
        gh_headers["Authorization"] = f"Bearer {gh_token}"

    try:
        rr = http.get(
            "https://api.github.com/search/users",
            params={"q": f'"{r.name_en}" in:name type:user', "per_page": 10},
            headers=gh_headers,
            timeout=12.0,
        )
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        items = rr.json().get("items") or []
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    if not items:
        return {"ok": True, "fields_set": 0, "note": "no GitHub hits"}

    # Score each candidate by research signals. Need to fetch each profile
    # for bio/company (expensive — cap at top 5 candidates).
    research_kw = re.compile(
        r"\b(ph\.?d|research|cs|computer science|ai|ml|machine learning|nlp|cv|vision|robotics|hci|ai4science|university|mit|stanford|berkeley|cmu|tsinghua|deepmind|google|microsoft|nvidia|meta|anthropic)\b",
        re.IGNORECASE,
    )
    best = None
    best_score = -1
    for item in items[:5]:
        login = item.get("login")
        if not login:
            continue
        # Skip obvious org accounts
        if item.get("type") != "User":
            continue
        try:
            pr = http.get(f"https://api.github.com/users/{login}", headers=gh_headers, timeout=8.0)
            if pr.status_code != 200:
                continue
            profile = pr.json()
        except Exception:
            continue

        score = 0
        bio = profile.get("bio") or ""
        company = profile.get("company") or ""
        if research_kw.search(bio):
            score += 50
        if research_kw.search(company):
            score += 30
        if (profile.get("public_repos") or 0) >= 5:
            score += 10
        if (profile.get("followers") or 0) >= 20:
            score += 5
        # Name match boost — bio or `name` field contains our exact name
        if r.name_en.lower() in (profile.get("name") or "").lower():
            score += 20
        if score > best_score:
            best_score = score
            best = (login, profile)

    if not best or best_score < 30:
        # Not confident enough — better to skip than guess wrong
        return {
            "ok": True,
            "fields_set": 0,
            "note": f"{len(items)} hits, best score {best_score} (need ≥30)",
        }

    login, profile = best
    r.github_handle = login
    updated = 1
    if profile.get("bio") and not r.bio:
        r.bio = profile["bio"]
        updated += 1
    if profile.get("blog") and not r.homepage_url:
        blog = profile["blog"]
        if not blog.startswith(("http://", "https://")):
            blog = "https://" + blog
        r.homepage_url = blog
        updated += 1
    return {
        "ok": True,
        "fields_set": updated,
        "note": f"@{login} · score {best_score} · bio:{bool(profile.get('bio'))}",
    }


# ── source 1.8: DBLP author discovery ──────────────────────────────────────


def _dblp_discover(db, r: Researcher, http: httpx.Client) -> dict:
    """DBLP author search → store PID, infer affiliation from `notes`.

    DBLP profile pages are well-maintained for academic CS researchers and
    often include institution affiliations in the notes field that we don't
    get elsewhere.
    """
    if not r.name_en:
        return {"ok": False, "fields_set": 0, "note": "no name"}

    try:
        rr = http.get(
            "https://dblp.org/search/author/api",
            params={"q": r.name_en, "format": "json", "h": 5},
            timeout=10.0,
        )
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        hits = rr.json().get("result", {}).get("hits", {}).get("hit") or []
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    if not hits:
        return {"ok": True, "fields_set": 0, "note": "no DBLP hits"}

    # Prefer the first hit (DBLP sorts by relevance); record as a Signal
    info = hits[0].get("info", {})
    pid_url = info.get("url", "")
    affiliations = []
    notes = info.get("notes")
    if isinstance(notes, dict):
        note_items = (
            notes.get("note") if isinstance(notes.get("note"), list) else [notes.get("note")]
        )
        for n in note_items or []:
            if isinstance(n, dict) and n.get("@type") == "affiliation" and n.get("text"):
                affiliations.append(n["text"])

    db.add(
        Signal(
            researcher_id=r.id,
            type="dblp_profile",
            payload={
                "pid_url": pid_url,
                "name": info.get("author"),
                "affiliations": affiliations,
                "n_hits": len(hits),
            },
            occurred_at=datetime.now(UTC),
        )
    )

    return {
        "ok": True,
        "fields_set": 0,
        "note": f"DBLP {pid_url.rsplit('/', 1)[-1] if pid_url else '?'}"
        + (f" · {len(affiliations)} aff" if affiliations else ""),
    }


# ── source 1.9: institution discover (DISCOVERY phase) ─────────────────────


# Loose heuristic: name contains any of these → company; else university/lab.
# Used only when we CREATE a new Institution from a name string and have no
# OpenAlex country/type metadata to lean on.
_COMPANY_HINTS = re.compile(
    r"\b(google|deepmind|microsoft|nvidia|meta|facebook|apple|amazon|openai|"
    r"anthropic|huawei|baidu|tencent|alibaba|bytedance|tiktok|ibm|adobe|"
    r"intel|qualcomm|snap|snapchat|tesla|spacex|stripe|salesforce|"
    r"research\b|labs?\b|inc\.?|corp\.?|ltd\.?|gmbh|technologies|technology)\b",
    re.IGNORECASE,
)


def _guess_institution_type(name: str) -> str:
    """Coarse heuristic: 'company' if name hits a known industry token, else
    'university'. Lab-style names (e.g. 'X-Lab', 'Foo Research') also map to
    'company'. Falls back to 'university' which is the safe default for
    academic profiles surfaced by S2 / OpenAlex.
    """
    if _COMPANY_HINTS.search(name or ""):
        return "company"
    return "university"


def _institution_discover(db, r: Researcher, http: httpx.Client) -> dict:
    """Fill `current_affiliation_id` from S2 / OpenAlex BEFORE consumption.

    Why early: `_institution_tag` (later in the pipeline) needs an
    affiliation to emit its tag chip; researchers like Shuangrui Ding land
    here with semantic_scholar_id + openalex_id set but no
    current_affiliation_id, so the tag step no-ops. Running this in the
    DISCOVERY phase means the rest of the pipeline can use the fresh
    affiliation immediately.

    Strategy — stop at first hit:
      A. Semantic Scholar  affiliations[0] from author/{id}?fields=affiliations
                          (same shape that `_semantic_scholar_discover` already
                          pulled, just re-queried via the existing helper so
                          we don't have to mutate that function's contract)
      B. OpenAlex          authors/{id}.last_known_institution{,s}

    If the institution name has no matching row, CREATE one with a
    type-heuristic (company vs university). Country is filled only when
    OpenAlex gives us `country_code`.

    This co-exists with `_affiliation_discover_wrapper` (later) on purpose —
    that one runs once consumption has populated more bio context, and is
    the safer fallback. Per project memory: "preserve alternatives on major
    changes".
    """
    if r.current_affiliation_id:
        return {"ok": True, "fields_set": 0, "note": "already set"}
    if not (r.semantic_scholar_id or r.openalex_id):
        return {"ok": True, "fields_set": 0, "note": "no S2/OpenAlex id"}

    from .affiliation_discovery import (
        _get_or_create,
        _openalex_lookup,
        _semantic_scholar_lookup,
    )

    inst_name: str | None = None
    inst_oa_id: str | None = None
    inst_country: str | None = None
    source: str | None = None

    # Source A — Semantic Scholar
    if r.semantic_scholar_id:
        try:
            n = _semantic_scholar_lookup(http, r.semantic_scholar_id)
        except Exception:
            n = None
        if n:
            inst_name = n
            source = "s2_affiliations"

    # Source B — OpenAlex
    if not inst_name and r.openalex_id:
        try:
            n, oa_id, cc = _openalex_lookup(http, r.openalex_id)
        except Exception:
            n, oa_id, cc = None, None, None
        if n:
            inst_name, inst_oa_id, inst_country = n, oa_id, cc
            source = "openalex_last_known"

    if not inst_name:
        return {"ok": True, "fields_set": 0, "note": "no aff in S2/OpenAlex"}

    try:
        inst, created = _get_or_create(
            db,
            inst_name,
            openalex_id=inst_oa_id,
            country=inst_country,
        )
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"create err: {type(e).__name__}"}

    if not inst:
        return {"ok": True, "fields_set": 0, "note": "could not match/create"}

    # New row: stamp the heuristic type (the bulk discover_affiliations path
    # leaves type=NULL — this is a small improvement we can afford here).
    if created and not inst.type:
        inst.type = _guess_institution_type(inst.name or "")

    r.current_affiliation_id = inst.id
    r.affiliation_source = "deep_dive_discover"
    suffix = " (new)" if created else ""
    return {
        "ok": True,
        "fields_set": 1,
        "note": f"{source} → {inst.name}{suffix}",
    }


# ── source 2: OpenAlex full works ──────────────────────────────────────────


def _openalex_full(db, r: Researcher, http: httpx.Client) -> dict:
    """For researchers with an openalex_id, pull their FULL works list AND
    their author profile (for x_concepts → research-direction tags + h-index).

    Anchor backfill caps at 80 works per anchor; we want everything for
    deep-dive. Plus the author profile has `x_concepts` (topic distribution)
    which we use to populate `tags` — the "Research Directions" section of
    the UI that was previously empty for everyone.
    """
    if not r.openalex_id:
        return {"ok": False, "fields_set": 0, "note": "no openalex_id"}
    aid = r.openalex_id.rsplit("/", 1)[-1]

    # Author profile — for tags + summary_stats (h-index, mean citedness)
    try:
        ar = http.get(f"https://api.openalex.org/authors/{aid}", timeout=15.0)
        author = ar.json() if ar.status_code == 200 else {}
    except Exception:
        author = {}

    # Works list — for cumulative counts + recency
    works_url = (
        f"https://api.openalex.org/works?filter=author.id:{aid}&per-page=200"
        "&select=id,title,publication_year,cited_by_count,doi"
    )
    try:
        rr = http.get(works_url, timeout=20.0)
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        data = rr.json()
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    results = data.get("results") or []
    total = len(results)
    total_cited = sum(int(w.get("cited_by_count") or 0) for w in results)
    most_recent_year = max((int(w.get("publication_year") or 0) for w in results), default=0)

    updated = 0
    if total and (r.works_count or 0) < total:
        r.works_count = total
        updated += 1
    if total_cited and (r.citation_count or 0) < total_cited:
        r.citation_count = total_cited
        updated += 1
    # very crude: if PhD's most recent paper is current year-ish, they're
    # probably still active (Y3+); if 2022-, probably graduated.
    if (
        most_recent_year
        and r.career_stage_year is None
        and r.current_role == "phd"
        and most_recent_year >= datetime.now(UTC).year - 1
    ):
        r.career_stage_year = 4
        updated += 1

    # ── Research-direction tags from x_concepts (the big new field!) ──
    # Reuse the existing OpenAlex enrichment's extraction so the format
    # matches what the UI already renders.
    from .openalex import _extract_tags

    new_tags = _extract_tags(author) if author else []
    if new_tags and not r.tags:
        r.tags = new_tags
        updated += 1
    elif new_tags and len(new_tags) > len(r.tags or []):
        # Existing tags are weaker (e.g. from homepage_llm with 3 interests);
        # OpenAlex has more — merge by label, keep the higher score.
        merged_by_label: dict[str, dict] = {t.get("label", ""): t for t in (r.tags or [])}
        for nt in new_tags:
            label = nt.get("label", "")
            if not label:
                continue
            existing = merged_by_label.get(label)
            if not existing or (nt.get("score", 0) > existing.get("score", 0)):
                merged_by_label[label] = nt
        r.tags = list(merged_by_label.values())
        updated += 1

    # h-index from summary_stats (S2 may have it too; whichever is higher wins)
    if author.get("summary_stats"):
        oa_h = author["summary_stats"].get("h_index")
        if oa_h and (not r.h_index or r.h_index < oa_h):
            r.h_index = int(oa_h)
            updated += 1

    n_tags = len(r.tags or [])
    return {
        "ok": True,
        "fields_set": updated,
        "note": f"{total} works · {total_cited:,} cites · {n_tags} tags",
    }


# ── source 3: GitHub profile ───────────────────────────────────────────────


def _github_profile(db, r: Researcher, http: httpx.Client) -> dict:
    if not r.github_handle:
        return {"ok": False, "fields_set": 0, "note": "no github_handle"}
    handle = r.github_handle.lstrip("@/")
    url = f"https://api.github.com/users/{handle}"
    try:
        gh_headers = HEADERS.copy()
        gh_token = os.environ.get("GITHUB_TOKEN")
        if gh_token:
            gh_headers["Authorization"] = f"Bearer {gh_token}"
        rr = http.get(url, headers=gh_headers, timeout=10.0)
        if rr.status_code == 404:
            return {"ok": True, "fields_set": 0, "note": "user not found"}
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        data = rr.json()
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    updated = 0
    if data.get("bio") and not r.bio:
        r.bio = data["bio"]
        updated += 1
    if data.get("blog") and not r.homepage_url:
        blog = data["blog"]
        if not blog.startswith(("http://", "https://")):
            blog = "https://" + blog
        r.homepage_url = blog
        updated += 1
    if data.get("twitter_username") and not r.twitter_handle:
        r.twitter_handle = data["twitter_username"]
        updated += 1

    note = f"public_repos={data.get('public_repos', 0)} · followers={data.get('followers', 0)}"
    # Persist as a Signal row so we can show in UI
    db.add(
        Signal(
            researcher_id=r.id,
            type="github_profile",
            payload={
                "bio": data.get("bio"),
                "company": data.get("company"),
                "location": data.get("location"),
                "public_repos": data.get("public_repos"),
                "followers": data.get("followers"),
                "blog": data.get("blog"),
            },
            occurred_at=datetime.now(UTC),
        )
    )
    return {"ok": True, "fields_set": updated, "note": note}


# ── source 4: HuggingFace profile ──────────────────────────────────────────


def _huggingface_profile(db, r: Researcher, http: httpx.Client) -> dict:
    """Look up an HF user matching the researcher's name. If found, fetch
    their model list and their org. Best for industry researchers / model
    releasers — strong commercial signal.
    """
    # Strategy: try the most likely HF user-id forms first
    name = (r.name_en or "").strip()
    if not name:
        return {"ok": False, "fields_set": 0, "note": "no name"}
    handles = []
    parts = name.lower().split()
    if len(parts) >= 2:
        handles.append("".join(parts))  # firstlast
        handles.append("-".join(parts))  # first-last
        handles.append(parts[-1])  # lastname only
    if r.github_handle:
        handles.append(r.github_handle.lower())

    # Try each candidate handle; for each that exists, fetch their models.
    # Only consider it a real match if model_count >= 1 — generic handles like
    # "ding" or "wang" exist but with no models, so they're false positives.
    found_user = None
    models: list[dict] = []
    for h in handles[:4]:
        try:
            rr = http.get(f"https://huggingface.co/api/users/{h}/overview", timeout=8.0)
            if rr.status_code != 200:
                continue
            ms = http.get(
                f"https://huggingface.co/api/models?author={h}&limit=20", timeout=10.0
            ).json()
            if not isinstance(ms, list) or len(ms) == 0:
                continue
            found_user = h
            models = ms
            break
        except Exception:
            continue

    if not found_user:
        return {"ok": True, "fields_set": 0, "note": "no HF user with models matched"}

    total_downloads = sum(int(m.get("downloads", 0) or 0) for m in models)
    db.add(
        Signal(
            researcher_id=r.id,
            type="huggingface_profile",
            payload={
                "user": found_user,
                "model_count": len(models),
                "total_downloads": total_downloads,
                "top_models": [
                    {"id": m.get("id"), "downloads": m.get("downloads", 0)}
                    for m in sorted(models, key=lambda m: m.get("downloads", 0) or 0, reverse=True)[
                        :5
                    ]
                ],
            },
            occurred_at=datetime.now(UTC),
        )
    )
    return {
        "ok": True,
        "fields_set": 0,
        "note": f"HF @{found_user} · {len(models)} models · {total_downloads:,} dl",
    }


# ── source 5: homepage scrape + LLM extraction ─────────────────────────────


HOMEPAGE_PROMPT = """You are reading a researcher's personal academic homepage.
Extract the following as a JSON object. Use null when not stated. Be terse.

{
  "bio": "two-sentence summary of who they are and what they work on",
  "advisor": "PhD advisor name, if mentioned (just the name)",
  "interests": ["list", "of", "research", "topics"],
  "current_role": "phd | postdoc | incoming_ap | ap | associate | full | industry | null",
  "graduation_year": "year as integer if stated, else null",
  "affiliation": "current institution name if explicitly stated, else null"
}

Reply with ONLY the JSON object, no markdown, no commentary."""


def _fetch_homepage(http: httpx.Client, url: str) -> tuple[str | None, str | None, str | None]:
    """Fetch researcher homepage HTML once and cache on the http client.

    Returns (raw_html, visible_text, error_note). `error_note` is None on
    success. The cache key is the URL itself — sources later in the pipeline
    that need the same page (homepage_llm + twitter_discover) get a single
    network round-trip per deep-dive run.
    """
    cache: dict[str, tuple[str | None, str | None, str | None]] = (
        getattr(http, "_openscout_homepage_cache", None) or {}
    )
    if url in cache:
        return cache[url]
    try:
        rr = http.get(url, timeout=15.0, follow_redirects=True)
        if rr.status_code != 200:
            result = (None, None, f"http {rr.status_code}")
        else:
            tree = HTMLParser(rr.text)
            body = tree.body
            text = body.text(separator=" ", strip=True) if body else ""
            text = re.sub(r"\s+", " ", text)[:8000]
            result = (rr.text, text, None)
    except Exception as e:
        result = (None, None, f"fetch err: {type(e).__name__}")
    cache[url] = result
    # First-time attach — httpx.Client allows attribute assignment.
    if not hasattr(http, "_openscout_homepage_cache"):
        http._openscout_homepage_cache = cache  # type: ignore[attr-defined]
    return result


def _homepage_llm(db, r: Researcher, http: httpx.Client) -> dict:
    if not r.homepage_url:
        return {"ok": False, "fields_set": 0, "note": "no homepage_url"}
    _, text, err = _fetch_homepage(http, r.homepage_url)
    if err:
        return {"ok": False, "fields_set": 0, "note": err}
    if not text or len(text) < 200:
        return {"ok": True, "fields_set": 0, "note": "homepage too sparse"}

    if not llm.is_available():
        return {"ok": False, "fields_set": 0, "note": "no LLM provider configured"}

    prompt = f"{HOMEPAGE_PROMPT}\n\n--- HOMEPAGE TEXT ---\n{text}"
    raw, err = llm.complete(prompt, max_tokens=400)
    if raw is None:
        return {"ok": False, "fields_set": 0, "note": f"llm err: {err}"}
    # Strip markdown fences if present, find first {...} block
    raw_stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.M)
    match = re.search(r"\{.*\}", raw_stripped, re.DOTALL)
    if not match:
        return {"ok": False, "fields_set": 0, "note": "llm: no JSON in response"}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        return {"ok": False, "fields_set": 0, "note": f"llm: bad JSON ({e})"}

    updated = 0
    if data.get("bio") and not r.bio:
        r.bio = data["bio"][:600]
        updated += 1
    if data.get("interests") and not r.tags:
        r.tags = [
            {
                "label": t,
                "score": 0.5,
                "level": 1,
                "type": "topic",
                "source": "homepage_llm",
            }
            for t in data["interests"][:8]
        ]
        updated += 1
    if data.get("current_role") and not r.current_role:
        cr = data["current_role"]
        if cr in {"phd", "postdoc", "incoming_ap", "ap", "associate", "full", "industry"}:
            r.current_role = cr
            r.role_source = "homepage_llm"
            updated += 1
    if data.get("graduation_year") and not r.graduation_year_estimate:
        try:
            r.graduation_year_estimate = int(data["graduation_year"])
            updated += 1
        except (ValueError, TypeError):
            pass

    return {
        "ok": True,
        "fields_set": updated,
        "note": f"bio:{bool(data.get('bio'))} adv:{bool(data.get('advisor'))} role:{data.get('current_role')}",
    }


# ── source 5.5: twitter handle discovery from homepage ─────────────────────


# `username` per Twitter rules: alphanumeric + underscore, 1-15 chars.
# Match twitter.com/<u> or x.com/<u>; allow optional `www.`/`mobile.` subdomains.
# Reject /intent/, /share, /home, /search, /i/, etc.
_TWITTER_HANDLE_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/"
    r"(?!intent/|share|home|search|i/|hashtag/|explore|notifications|messages)"
    r"([A-Za-z0-9_]{1,15})(?:[/?#]|$)",
    re.IGNORECASE,
)


def _twitter_discover(db, r: Researcher, http: httpx.Client) -> dict:
    """Scan homepage HTML for twitter.com / x.com links → set twitter_handle.

    Many researcher homepages link their Twitter from a "contact" / "social"
    icon strip that the LLM-extraction prompt doesn't capture (it's after
    page chrome stripping). Cheap regex over the raw HTML is more reliable
    here than another LLM call.

    Shares the homepage fetch with `_homepage_llm` via the per-run
    `_fetch_homepage` cache, so a deep dive on a researcher with a homepage
    incurs ONE HTTP round-trip for both sources combined.
    """
    if r.twitter_handle:
        return {"ok": True, "fields_set": 0, "note": "already has handle"}
    if not r.homepage_url:
        return {"ok": False, "fields_set": 0, "note": "no homepage_url"}

    html, _, err = _fetch_homepage(http, r.homepage_url)
    if err:
        return {"ok": False, "fields_set": 0, "note": err}
    if not html:
        return {"ok": True, "fields_set": 0, "note": "empty homepage"}

    # Tally each candidate handle; pick the most frequently linked one. This
    # filters incidental "share this paper on X" footer icons that link to
    # /intent/ (already rejected) or to neutral handles.
    counts: dict[str, int] = {}
    for m in _TWITTER_HANDLE_RE.finditer(html):
        handle = m.group(1)
        # Skip obvious non-personal accounts (case-insensitive)
        if handle.lower() in {"twitter", "x", "verified", "support", "help"}:
            continue
        counts[handle] = counts.get(handle, 0) + 1

    if not counts:
        return {"ok": True, "fields_set": 0, "note": "no twitter links found"}

    # Highest-count handle wins; tie → first-seen alphabetical for determinism
    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    r.twitter_handle = best
    return {
        "ok": True,
        "fields_set": 1,
        "note": f"@{best} ({counts[best]}x)"
        + (f" · {len(counts)} candidates" if len(counts) > 1 else ""),
    }


# ── source 6: bio synthesis from paper history ─────────────────────────────


BIO_SYNTH_PROMPT = """You are summarizing a researcher's work for an investor.
You will be given a list of their paper titles + abstract snippets. Reply
with a JSON object — NO markdown, NO commentary — matching this schema:

{
  "bio": "TWO sentences, ~280 chars, factual. Name the SPECIFIC techniques/
          domains. Start with their research area (e.g. 'Researcher working
          on video segmentation and long-context vision models'). Do NOT
          speculate about personality, university, or career stage. No
          first-person.",
  "tags": ["3-6 specific research-direction tags",
           "e.g. 'video object segmentation', 'long-context VLM',
           'symbolic music generation' — concrete topic names, NOT broad
           umbrellas like 'AI' or 'Computer Vision'. Lowercase, ≤4 words each."]
}"""


def _bio_synth(db, r: Researcher, http: httpx.Client) -> dict:
    """Synthesize a bio AND specific research-direction tags from papers.

    Two birds: gives the auto-discovered tail (a) a 2-sentence bio for the
    detail page and (b) concrete tags for the "Research Directions" section.
    OpenAlex x_concepts is too coarse ("Computer Science / AI / CV") — the
    LLM read of actual paper abstracts gives "video object segmentation",
    "long-context VLM", etc.
    """
    need_bio = not r.bio
    # OpenAlex tags often arrive level=0 ("Computer Science") only — treat
    # those as "still needs LLM-synth tags" too.
    has_specific_tags = any((t.get("level") or 0) >= 2 for t in (r.tags or []))
    need_tags = not r.tags or not has_specific_tags
    if not need_bio and not need_tags:
        return {"ok": True, "fields_set": 0, "note": "bio + specific tags both present"}
    if not llm.is_available():
        return {"ok": False, "fields_set": 0, "note": "no LLM provider configured"}

    rows = db.execute(
        select(Paper.title, Paper.abstract, PaperAuthor.position)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .where(PaperAuthor.researcher_id == r.id)
        .order_by(PaperAuthor.position.asc(), Paper.first_seen_at.desc())
        .limit(12)
    ).all()
    if len(rows) < 3:
        return {"ok": True, "fields_set": 0, "note": f"only {len(rows)} papers (need ≥3)"}

    # Build a compact input — titles always, abstracts only for first-authored
    # papers (we care most about what they DROVE, not co-authored).
    lines = []
    for title, abstract, position in rows:
        marker = "[FIRST AUTHOR]" if position == 1 else f"[#{position}]"
        if position == 1 and abstract:
            snippet = re.sub(r"\s+", " ", abstract)[:300]
            lines.append(f"{marker} {title}\n  {snippet}")
        else:
            lines.append(f"{marker} {title}")
    paper_block = "\n".join(lines)

    prompt = f"{BIO_SYNTH_PROMPT}\n\nResearcher: {r.name_en}\nPapers:\n{paper_block}"
    raw, err = llm.complete(prompt, max_tokens=400)
    if raw is None:
        return {"ok": False, "fields_set": 0, "note": f"llm err: {err}"}

    raw_stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.M)
    match = re.search(r"\{.*\}", raw_stripped, re.DOTALL)
    if not match:
        return {"ok": False, "fields_set": 0, "note": "llm: no JSON in response"}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        return {"ok": False, "fields_set": 0, "note": f"llm: bad JSON ({e})"}

    updated = 0
    bio_text = (data.get("bio") or "").strip().strip('"').strip()
    bio_text = re.sub(r"^(?:bio|summary)\s*[:：]\s*", "", bio_text, flags=re.IGNORECASE)
    if need_bio and len(bio_text) >= 40:
        r.bio = bio_text[:600]
        updated += 1

    new_tags_raw = data.get("tags") or []
    if need_tags and new_tags_raw:
        # Synth tags get level=2 (specific) and a high score, so they don't
        # get crowded out by OpenAlex's level=0 generic ones in UI sort.
        synth_tags = [
            {
                "label": t.strip().lower(),
                "score": 0.8,
                "level": 2,
                "type": "topic",
                "source": "bio_synth",
            }
            for t in new_tags_raw
            if isinstance(t, str) and 2 < len(t.strip()) < 50
        ][:6]
        if synth_tags:
            # Merge with existing tags (e.g. OpenAlex level-0 ones) — by label.
            merged: dict[str, dict] = {t.get("label", ""): t for t in (r.tags or [])}
            for nt in synth_tags:
                # Don't overwrite OpenAlex high-confidence tag with same label
                existing = merged.get(nt["label"])
                if not existing or nt["score"] > existing.get("score", 0):
                    merged[nt["label"]] = nt
            r.tags = list(merged.values())
            updated += 1

    if updated == 0:
        return {"ok": False, "fields_set": 0, "note": "llm output unusable"}
    return {
        "ok": True,
        "fields_set": updated,
        "note": f"bio:{need_bio and bool(bio_text)} +{len(new_tags_raw)} tags",
    }


# ── source 6.4: per-researcher affiliation discovery (v1.11) ───────────────


def _affiliation_discover_wrapper(db, r: Researcher, http: httpx.Client) -> dict:
    """Single-researcher affiliation discovery for the deep-dive pipeline.

    Mirrors the bulk `discover_affiliations` orchestrator but reuses the
    deep-dive's open session + http client (one researcher only).
    """
    if r.current_affiliation_id:
        return {"ok": True, "fields_set": 0, "note": "already set"}
    has_signal = bool(
        r.openalex_id or r.semantic_scholar_id or (r.bio and "· (per Semantic Scholar)" in r.bio)
    )
    if not has_signal:
        return {"ok": True, "fields_set": 0, "note": "no source signal"}

    from .affiliation_discovery import (
        _bio_lookup,
        _get_or_create,
        _openalex_lookup,
        _semantic_scholar_lookup,
    )

    inst_name = inst_oa_id = inst_country = source = None
    if r.openalex_id:
        n, oid, cc = _openalex_lookup(http, r.openalex_id)
        if n:
            inst_name, inst_oa_id, inst_country, source = n, oid, cc, "openalex"
    if not inst_name and r.semantic_scholar_id:
        n = _semantic_scholar_lookup(http, r.semantic_scholar_id)
        if n:
            inst_name, source = n, "semantic_scholar"
    if not inst_name:
        n = _bio_lookup(r.bio)
        if n:
            inst_name, source = n, "bio_s2_leftover"
    if not inst_name:
        return {"ok": True, "fields_set": 0, "note": "no affiliation found"}

    inst, created = _get_or_create(db, inst_name, openalex_id=inst_oa_id, country=inst_country)
    if not inst:
        return {"ok": True, "fields_set": 0, "note": "could not match/create"}

    r.current_affiliation_id = inst.id
    r.affiliation_source = source
    suffix = " (new)" if created else ""
    return {"ok": True, "fields_set": 1, "note": f"{source} → {inst.name}{suffix}"}


# ── source 6.5: institution + signal tags ──────────────────────────────────


def _merge_tags(existing: list[dict] | None, new: list[dict]) -> tuple[list[dict], int]:
    """Merge `new` tags into `existing` by (label, type). Returns (merged, n_added)."""
    by_key: dict[tuple[str, str], dict] = {
        (t.get("label", ""), t.get("type", "topic")): t for t in (existing or [])
    }
    n_added = 0
    for nt in new:
        key = (nt.get("label", ""), nt.get("type", "topic"))
        if not key[0]:
            continue
        if key not in by_key:
            n_added += 1
        existing_score = by_key.get(key, {}).get("score", 0)
        if key not in by_key or nt.get("score", 0) > existing_score:
            by_key[key] = nt
    return list(by_key.values()), n_added


def _institution_tag(db, r: Researcher, http: httpx.Client) -> dict:
    """Emit the researcher's current affiliation as an `institution`-typed tag.

    The 机构 (affiliation) cell already shows the institution name, but tagging
    it lets the user filter "show me all Tsinghua people" via the tag system
    and gives the chip a visual home in the Tags row.
    """
    if not r.current_affiliation_id:
        return {"ok": True, "fields_set": 0, "note": "no affiliation"}

    from ..models import Institution

    inst = db.execute(
        select(Institution).where(Institution.id == r.current_affiliation_id)
    ).scalar_one_or_none()
    if not inst or not inst.name:
        return {"ok": True, "fields_set": 0, "note": "affiliation not resolvable"}

    new_tag = {
        "label": inst.name,
        "label_zh": inst.name_zh,
        "score": 1.0,
        "level": 3,
        "type": "institution",
        "country": inst.country,
        "source": "current_affiliation",
    }
    merged, added = _merge_tags(r.tags, [new_tag])
    if not added:
        return {"ok": True, "fields_set": 0, "note": f"already tagged: {inst.name}"}
    r.tags = merged
    return {"ok": True, "fields_set": 1, "note": f"+ {inst.name}"}


def _signal_tag(db, r: Researcher, http: httpx.Client) -> dict:
    """Emit "high-potential" / "rising star" / status tags based on combined signals.

    These are the chips the investor scans for first — "is this person worth
    a closer look?" Computed every dive (cheap; idempotent). All tagged with
    type="signal" so the UI styles them prominently.
    """
    new_tags: list[dict] = []

    # Top investment lens — anyone v2 >= 0.5 is among the strongest investable
    v2 = r.investability_score_v2 or 0
    if v2 >= 0.5:
        new_tags.append(
            {
                "label": "🔥 high-potential",
                "label_zh": "🔥 高潜",
                "score": min(1.0, v2),
                "level": 3,
                "type": "signal",
                "source": f"investability_v2={v2:.2f}",
            }
        )

    # Senior already — flag accordingly so we don't confuse them with rising stars
    if r.current_role == "incoming_ap":
        new_tags.append(
            {
                "label": "⭐ incoming AP",
                "label_zh": "⭐ 即将入职 AP",
                "score": 1.0,
                "level": 3,
                "type": "signal",
                "source": "current_role",
            }
        )

    # Prolific junior — PhD/postdoc with high h-index relative to career stage
    if r.current_role in ("phd", "postdoc") and (r.h_index or 0) >= 10:
        new_tags.append(
            {
                "label": "🚀 prolific junior",
                "label_zh": "🚀 学界新星",
                "score": min(1.0, (r.h_index or 0) / 20.0),
                "level": 3,
                "type": "signal",
                "source": f"h_index={r.h_index}",
            }
        )

    # High-impact-per-paper — citation density > 100 means each paper landed
    if (r.h_index or 0) >= 5 and (r.citation_count or 0) >= 500:
        density = (r.citation_count or 0) / max((r.h_index or 1), 1)
        if density >= 80:
            new_tags.append(
                {
                    "label": "📈 high-impact per paper",
                    "label_zh": "📈 单篇高引",
                    "score": min(1.0, density / 200.0),
                    "level": 3,
                    "type": "signal",
                    "source": f"cites_per_h={density:.0f}",
                }
            )

    # PhD Y4+ marker — the user's investment sweet spot (graduating soon)
    if r.current_role == "phd" and (r.career_stage_year or 0) >= 4:
        new_tags.append(
            {
                "label": "🎓 graduating soon",
                "label_zh": "🎓 即将毕业",
                "score": 0.9,
                "level": 3,
                "type": "signal",
                "source": f"PhD-Y{r.career_stage_year}",
            }
        )

    # GitHub momentum — has a model release with significant downloads
    # (handled when huggingface_profile fires, but tag it here for consistency)
    # Note: signals_by_type would be cleaner if Signal had a 'has_recent' helper

    if not new_tags:
        return {"ok": True, "fields_set": 0, "note": "no signals triggered"}

    # ALWAYS remove any prior signal tags before re-adding — signals are
    # computed fresh each dive, so stale ones (e.g. "graduating soon" set
    # last year when they were Y3 PhD, now they're a postdoc) should clear.
    non_signal = [t for t in (r.tags or []) if t.get("type") != "signal"]
    merged, added = _merge_tags(non_signal, new_tags)
    r.tags = merged
    labels = ", ".join(t["label"] for t in new_tags)
    return {"ok": True, "fields_set": added, "note": labels}


# ── source 7: refresh signature paper ──────────────────────────────────────


def _signature_paper(db, r: Researcher, http: httpx.Client) -> dict:
    """Assign / refresh the researcher's signature paper.

    Pick the FIRST-AUTHORED paper with the best signal, where "best" =
    citations (when any > 0) else work_score (which folds in github stars +
    buzz + breakthrough). Falls back to any-position if no first-author papers.

    This is the difference between "代表作: WildClawBench (random arbitrary
    pick from a list of 0-cite papers)" and "代表作: SAM2Long (the one with
    real github + buzz)".
    """
    from sqlalchemy import func

    # Composite signal — citations dominate when present, else work_score
    signal = func.coalesce(Paper.citation_count, 0) * 100.0 + func.coalesce(Paper.work_score, 0.0)

    first_authored = db.execute(
        select(Paper.id, Paper.citation_count, Paper.work_score, Paper.title)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .where(PaperAuthor.researcher_id == r.id, PaperAuthor.position == 1)
        .order_by(signal.desc())
        .limit(1)
    ).first()

    pick = first_authored
    fallback = False
    if not pick:
        pick = db.execute(
            select(Paper.id, Paper.citation_count, Paper.work_score, Paper.title)
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(PaperAuthor.researcher_id == r.id)
            .order_by(signal.desc())
            .limit(1)
        ).first()
        fallback = True

    if not pick:
        return {"ok": True, "fields_set": 0, "note": "no papers"}

    pid, cites, ws, title = pick
    if r.signature_paper_id == pid:
        return {"ok": True, "fields_set": 0, "note": f"unchanged: {(title or '')[:50]}"}

    r.signature_paper_id = int(pid)
    descriptor = "first-author" if not fallback else "co-author fallback"
    return {
        "ok": True,
        "fields_set": 1,
        "note": f"→ {(title or '')[:50]} ({cites or 0} cites · work_score={ws or 0:.2f} · {descriptor})",
    }


# ── orchestrator ───────────────────────────────────────────────────────────

# Two-phase pipeline:
#   DISCOVERY  — fan out, find missing IDs (no IDs needed to run)
#   CONSUMPTION — use those IDs to pull rich data
# Order matters: discovery sources MUST run first so their writes (homepage_url,
# github_handle, openalex_id, semantic_scholar_id) are available to consumers.
#
# Discovery first:
SOURCES: list[tuple[str, Callable]] = [
    # ── DISCOVERY: find IDs ──
    ("arxiv_author", _arxiv_author),  # name → ingest missing papers
    ("openalex_match", _openalex_match),  # name → openalex_id
    ("semantic_scholar_discover", _semantic_scholar_discover),  # name → S2 id, homepage, h-index
    ("github_discover", _github_discover),  # name → github_handle (+ bio fallback)
    ("dblp_discover", _dblp_discover),  # name → DBLP PID + affiliation hint
    ("institution_discover", _institution_discover),  # S2/OpenAlex → current_affiliation_id
    # ── CONSUMPTION: use IDs to pull rich data ──
    ("openalex_full", _openalex_full),  # openalex_id → all works
    ("affiliation_discover", _affiliation_discover_wrapper),  # IDs → current_affiliation_id (v1.11)
    ("github_profile", _github_profile),  # github_handle → bio/blog/twitter
    ("huggingface_profile", _huggingface_profile),  # name guess → HF user + models
    ("homepage_llm", _homepage_llm),  # homepage_url → bio/advisor/interests
    ("twitter_discover", _twitter_discover),  # homepage HTML → twitter_handle
    # ── SYNTHESIS: fill remaining gaps from what we have ──
    ("bio_synth", _bio_synth),  # papers → 2-sentence bio + topic tags
    ("institution_tag", _institution_tag),  # affiliation → institution-typed tag chip
    ("signal_tag", _signal_tag),  # combined signals → 🔥 高潜 / 🚀 学界新星 / etc.
    ("signature_paper", _signature_paper),  # papers + work_score → featured paper
]


def _is_stale(sources_used: dict | None, source: str, now: datetime) -> bool:
    """A source is stale if not run, or run > STALE_AFTER_DAYS ago."""
    if not sources_used or source not in sources_used:
        return True
    try:
        last = datetime.fromisoformat(sources_used[source])
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return (now - last) > timedelta(days=STALE_AFTER_DAYS)
    except (ValueError, TypeError):
        return True


def deep_dive_one(slug: str, force: bool = False) -> dict:
    """Run all 5 sources for the researcher; persist results + provenance.

    Returns: {slug, sources: {name: {ran, fields_set, note}}, fields_total}
    """
    out: dict = {"slug": slug, "sources": {}, "fields_total": 0}
    now = datetime.now(UTC)

    with session_scope() as db:
        r = db.execute(select(Researcher).where(Researcher.slug == slug)).scalar_one_or_none()
        if not r:
            return {"slug": slug, "error": "not found"}

        sources_used: dict = dict(r.deep_dive_sources_used or {})

        with httpx.Client(headers=HEADERS, follow_redirects=True) as http:
            for name, fn in SOURCES:
                if not force and not _is_stale(sources_used, name, now):
                    out["sources"][name] = {"ran": False, "note": "cached (<30d)"}
                    continue
                try:
                    result = fn(db, r, http)
                except Exception as e:
                    result = {"ok": False, "fields_set": 0, "note": f"unhandled: {e}"}
                result["ran"] = True
                out["sources"][name] = result
                out["fields_total"] += int(result.get("fields_set") or 0)
                if result.get("ok"):
                    sources_used[name] = now.isoformat()

        r.deep_dive_sources_used = sources_used
        r.deep_dive_run_at = now

    return out


def _auto_queue_candidates(db, limit: int) -> list[str]:
    """Build the ordered union of researchers worth deep-diving.

    Three reasoned buckets (priority order — earlier buckets take limit
    capacity first):

      a) Never-deep-dived AND `investability_score_v2 >= 0.4`
         The cold-start backlog. Ranked by score desc.

      b) Stale-but-active: `deep_dive_run_at` older than 30 days AND has
         a paper published in the last 60 days.
         Catches researchers who were dived once, then dropped a new
         paper that changed their trajectory. Ranked by score desc.

      c) Newly-flagged 🔥 high-potential: signal_tag added (proxied by
         `updated_at`) in the last 7 days AND tags JSON includes the
         high-potential label. These are the freshest investability
         spikes. Ranked by updated_at desc.

    Union is deduped by slug — earlier-bucket assignment wins.

    Extracted to its own function so it can be tested / inspected without
    actually firing the deep-dive HTTP calls.
    """
    from sqlalchemy import desc

    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=STALE_AFTER_DAYS)
    recent_paper_cutoff = (now - timedelta(days=60)).date()
    fresh_signal_cutoff = now - timedelta(days=7)

    ordered: list[str] = []
    seen: set[str] = set()

    def _add(slug: str) -> None:
        if slug and slug not in seen and len(ordered) < limit:
            ordered.append(slug)
            seen.add(slug)

    # Bucket A — never dived, score ≥ 0.4
    rows_a = db.execute(
        select(Researcher.slug)
        .where(
            Researcher.deep_dive_run_at.is_(None),
            Researcher.investability_score_v2.is_not(None),
            Researcher.investability_score_v2 >= 0.4,
        )
        .order_by(desc(Researcher.investability_score_v2))
        .limit(limit)
    ).all()
    for (slug,) in rows_a:
        _add(slug)

    # Bucket B — stale dive + recent paper. The join filters to researchers
    # with at least one paper published in the last 60 days; DISTINCT keeps
    # one row per researcher even if they have multiple recent papers.
    if len(ordered) < limit:
        rows_b = db.execute(
            select(Researcher.slug)
            .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
            .join(Paper, Paper.id == PaperAuthor.paper_id)
            .where(
                Researcher.deep_dive_run_at.is_not(None),
                Researcher.deep_dive_run_at < stale_cutoff,
                Paper.published_at.is_not(None),
                Paper.published_at >= recent_paper_cutoff,
            )
            .order_by(desc(Researcher.investability_score_v2))
            .distinct()
            .limit(limit)
        ).all()
        for (slug,) in rows_b:
            _add(slug)

    # Bucket C — recently-updated AND tags JSON has a high-potential signal.
    # We can't index into JSON portably across SQLite/Postgres, so fetch
    # candidates by updated_at and filter in Python. Cheap because the
    # updated_at window is narrow (7 days).
    if len(ordered) < limit:
        rows_c = db.execute(
            select(Researcher.slug, Researcher.tags)
            .where(
                Researcher.updated_at >= fresh_signal_cutoff,
                Researcher.tags.is_not(None),
            )
            .order_by(desc(Researcher.updated_at))
            .limit(limit * 4)  # over-fetch; filter below
        ).all()
        for slug, tags in rows_c:
            if not isinstance(tags, list):
                continue
            for t in tags:
                if not isinstance(t, dict):
                    continue
                label = t.get("label", "")
                if t.get("type") == "signal" and "high-potential" in label:
                    _add(slug)
                    break
            if len(ordered) >= limit:
                break

    return ordered


def auto_queue(limit: int = 10) -> dict[str, int]:
    """Auto-pick researchers most worth deep-diving.

    Picks top-N from a UNION of three buckets (see `_auto_queue_candidates`):
      a) Never-dived + investability_score_v2 ≥ 0.4
      b) Stale dive (>30d) + a paper in the last 60d (active trajectory)
      c) Newly-tagged 🔥 high-potential (signal added in last 7 days)

    Capped to `limit`. Default 10 — tuned for a daily cron that doesn't
    burn API quota in one shot.
    """
    counts = {"attempted": 0, "succeeded": 0, "skipped_fresh": 0}
    with session_scope() as db:
        slugs = _auto_queue_candidates(db, limit=limit)
    for slug in slugs:
        counts["attempted"] += 1
        result = deep_dive_one(slug)
        if any(s.get("ran") and s.get("ok") for s in result.get("sources", {}).values()):
            counts["succeeded"] += 1
    return counts
