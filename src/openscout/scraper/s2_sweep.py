"""Standalone Semantic Scholar author-ID sweep.

Only a few dozen of our ~12k researchers carry a `semantic_scholar_id`, yet S2
author profiles expose homepage / hIndex / citationCount / affiliations —
high-value fields we otherwise never see. This sweep walks researchers without
an S2 id (highest `investability_score_v2` first), performs ONE author-search
request each, and accepts a candidate only on paper-title overlap with the
papers we already attribute to that researcher.

Run it standalone:

    .venv/bin/python -c "from openscout.scraper.s2_sweep import sweep_s2; print(sweep_s2(limit=300))"

Rate limit: our S2 API key allows 1 request/second *cumulative*, so we sleep
1.05s before every request and back off 10s (+ one retry) on HTTP 429.

DB writes are committed in batches of 25 (one `session_scope` per batch) so a
mid-run crash loses at most the current batch.
"""

from __future__ import annotations

import time

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher

S2_AUTHOR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/author/search"
S2_FIELDS = "name,affiliations,homepage,paperCount,citationCount,hIndex,papers.title"
S2_SEARCH_LIMIT = 5

SLEEP_BETWEEN_REQUESTS = 1.05  # strict 1 req/s cumulative limit, with margin
SLEEP_ON_429 = 10.0
BATCH_SIZE = 25  # researchers per session_scope commit


def _search_author(http: httpx.Client, name: str) -> httpx.Response:
    """One S2 author-search request. On HTTP 429: sleep 10s, retry once."""
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    params = {"query": name, "limit": S2_SEARCH_LIMIT, "fields": S2_FIELDS}
    resp = http.get(S2_AUTHOR_SEARCH_URL, params=params, headers=headers, timeout=20.0)
    if resp.status_code == 429:
        time.sleep(SLEEP_ON_429)
        resp = http.get(S2_AUTHOR_SEARCH_URL, params=params, headers=headers, timeout=20.0)
    return resp


def _known_titles(db: Session, researcher_id: int) -> set[str]:
    """Lower-cased titles of the papers we already link to this researcher."""
    titles = {
        (t or "").lower().strip()
        for (t,) in db.execute(
            select(Paper.title)
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(PaperAuthor.researcher_id == researcher_id)
        ).all()
    }
    titles.discard("")
    return titles


def _pick_by_title_overlap(candidates: list[dict], our_titles: set[str]) -> dict | None:
    """Pick the S2 candidate whose papers overlap our known titles.

    Disambiguation pattern copied from `_semantic_scholar_discover` in
    scraper/deep_dive.py (the proven approach): score by title overlap ONLY —
    a paper-count plausibility band alone is too weak, multiple "Wang Jing"s
    pass it. The single-candidate fallback (rare name, exactly one hit, with a
    plausible paper count) is carried over too.
    """
    best: dict | None = None
    best_overlap = 0
    for cand in candidates:
        cand_titles = {(p.get("title") or "").lower().strip() for p in (cand.get("papers") or [])}
        cand_titles.discard("")
        overlap = len(cand_titles & our_titles)
        if overlap > best_overlap:
            best_overlap = overlap
            best = cand

    if best is not None:
        return best

    # Single-hit fallback: rare name, only one candidate, no overlap available —
    # accept only when we *do* know titles (so absence of overlap is meaningful)
    # and the candidate's paper count is plausible for an early-stage researcher.
    if len(candidates) == 1 and our_titles:
        single = candidates[0]
        pc = single.get("paperCount") or 0
        if 3 <= pc <= 500:
            return single
    return None


def _fill_profile_fields(r: Researcher, cand: dict) -> int:
    """Fill h_index / citation_count / homepage_url — only where null or lower."""
    updated = 0
    h_index = cand.get("hIndex")
    if h_index is not None and (r.h_index is None or r.h_index < int(h_index)):
        r.h_index = int(h_index)
        updated += 1
    cites = cand.get("citationCount")
    if cites is not None and (r.citation_count is None or r.citation_count < int(cites)):
        r.citation_count = int(cites)
        updated += 1
    if not r.homepage_url and cand.get("homepage"):
        r.homepage_url = str(cand["homepage"]).strip()
        updated += 1
    return updated


def _s2_id_taken(db: Session, s2_id: str) -> bool:
    """True if another researcher row already owns this S2 id (UNIQUE column)."""
    row = db.execute(
        select(Researcher.id).where(Researcher.semantic_scholar_id == s2_id).limit(1)
    ).first()
    return row is not None


def sweep_s2(limit: int = 300) -> dict[str, int]:
    """Match up to `limit` researchers to Semantic Scholar author profiles.

    Selection: `semantic_scholar_id IS NULL` and `name_en` set, ordered by
    `investability_score_v2 DESC NULLS LAST` so the highest-value researchers
    get matched first.
    """
    counts = {
        "attempted": 0,
        "matched": 0,
        "ambiguous_skipped": 0,
        "no_hits": 0,
        "fields_updated": 0,
        "errors": 0,
    }

    with session_scope() as db:
        ids = [
            rid
            for (rid,) in db.execute(
                select(Researcher.id)
                .where(
                    Researcher.semantic_scholar_id.is_(None),
                    Researcher.name_en.is_not(None),
                    Researcher.name_en != "",
                )
                .order_by(desc(Researcher.investability_score_v2).nulls_last(), Researcher.id)
                .limit(limit)
            ).all()
        ]

    # S2 ids assigned during this run. The column is UNIQUE — without this,
    # two duplicate researcher rows matching the same S2 author would blow up
    # an entire 25-row batch commit with an IntegrityError.
    claimed: set[str] = set()

    with httpx.Client(follow_redirects=True) as http:
        for batch_start in range(0, len(ids), BATCH_SIZE):
            batch_ids = ids[batch_start : batch_start + BATCH_SIZE]
            with session_scope() as db:
                for rid in batch_ids:
                    r = db.get(Researcher, rid)
                    if r is None or r.semantic_scholar_id or not r.name_en:
                        continue

                    counts["attempted"] += 1
                    time.sleep(SLEEP_BETWEEN_REQUESTS)
                    try:
                        resp = _search_author(http, r.name_en)
                        if resp.status_code != 200:
                            counts["errors"] += 1
                            continue
                        data = resp.json().get("data") or []
                    except Exception:
                        counts["errors"] += 1
                        continue

                    if not data:
                        counts["no_hits"] += 1
                        continue

                    best = _pick_by_title_overlap(data, _known_titles(db, r.id))
                    s2_id = str(best.get("authorId") or "") if best else ""
                    if not s2_id or s2_id in claimed or _s2_id_taken(db, s2_id):
                        counts["ambiguous_skipped"] += 1
                        continue

                    claimed.add(s2_id)
                    r.semantic_scholar_id = s2_id
                    counts["matched"] += 1
                    counts["fields_updated"] += _fill_profile_fields(r, best)

            done = min(batch_start + BATCH_SIZE, len(ids))
            print(
                f"[s2_sweep] committed {done}/{len(ids)} · "
                f"matched={counts['matched']} ambiguous={counts['ambiguous_skipped']} "
                f"no_hits={counts['no_hits']} errors={counts['errors']}",
                flush=True,
            )

    return counts
