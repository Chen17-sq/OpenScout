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


# ── source 2: OpenAlex full works ──────────────────────────────────────────


def _openalex_full(db, r: Researcher, http: httpx.Client) -> dict:
    """For researchers with an openalex_id, pull their FULL works list — the
    anchor backfill caps at 80 per anchor; we want everything for deep-dive.
    """
    if not r.openalex_id:
        return {"ok": False, "fields_set": 0, "note": "no openalex_id"}
    aid = r.openalex_id.rsplit("/", 1)[-1]
    works_url = f"https://api.openalex.org/works?filter=author.id:{aid}&per-page=200&select=id,title,publication_year,cited_by_count,doi"
    try:
        rr = http.get(works_url, timeout=20.0)
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        data = rr.json()
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"err: {type(e).__name__}"}

    results = data.get("results") or []
    # We only update the researcher's cumulative metrics here, not insert
    # papers (which is the full backfill_works pipeline). Cheap and useful.
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

    return {"ok": True, "fields_set": updated, "note": f"{total} works · {total_cited:,} cites"}


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


def _homepage_llm(db, r: Researcher, http: httpx.Client) -> dict:
    if not r.homepage_url:
        return {"ok": False, "fields_set": 0, "note": "no homepage_url"}
    try:
        rr = http.get(r.homepage_url, timeout=15.0, follow_redirects=True)
        if rr.status_code != 200:
            return {"ok": False, "fields_set": 0, "note": f"http {rr.status_code}"}
        # Strip HTML, take the first 8000 chars of visible text
        tree = HTMLParser(rr.text)
        body = tree.body
        text = body.text(separator=" ", strip=True) if body else ""
        text = re.sub(r"\s+", " ", text)[:8000]
        if len(text) < 200:
            return {"ok": True, "fields_set": 0, "note": "homepage too sparse"}
    except Exception as e:
        return {"ok": False, "fields_set": 0, "note": f"fetch err: {type(e).__name__}"}

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
            {"label": t, "score": 0.5, "source": "homepage_llm"} for t in data["interests"][:8]
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


# ── orchestrator ───────────────────────────────────────────────────────────

SOURCES: list[tuple[str, Callable]] = [
    ("arxiv_author", _arxiv_author),
    ("openalex_full", _openalex_full),
    ("github_profile", _github_profile),
    ("huggingface_profile", _huggingface_profile),
    ("homepage_llm", _homepage_llm),
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


def auto_queue(limit: int = 20) -> dict[str, int]:
    """Auto-pick researchers most worth deep-diving:
      - investability_score_v2 > 0.4
      - never deep-dived OR last dive > 30 days ago
    Ordered by score desc so the top picks get covered first.
    """
    from sqlalchemy import desc, or_

    cutoff = datetime.now(UTC) - timedelta(days=STALE_AFTER_DAYS)

    counts = {"attempted": 0, "succeeded": 0, "skipped_fresh": 0}
    with session_scope() as db:
        slugs = [
            slug
            for (slug,) in db.execute(
                select(Researcher.slug)
                .where(
                    Researcher.investability_score_v2.is_not(None),
                    Researcher.investability_score_v2 > 0.4,
                    or_(
                        Researcher.deep_dive_run_at.is_(None),
                        Researcher.deep_dive_run_at < cutoff,
                    ),
                )
                .order_by(desc(Researcher.investability_score_v2))
                .limit(limit)
            ).all()
        ]
    for slug in slugs:
        counts["attempted"] += 1
        result = deep_dive_one(slug)
        if any(s.get("ran") and s.get("ok") for s in result.get("sources", {}).values()):
            counts["succeeded"] += 1
    return counts
