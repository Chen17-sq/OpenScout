"""Standalone batch bio synthesis for the highest-scored researchers.

The deep-dive pipeline already has a `_bio_synth` source (deep_dive.py) that
feeds paper titles + first-author abstracts to the LLM and gets back a
2-sentence bio + specific topic tags. But it only runs inside full dives, so
only ~1% of researchers have a bio. This module reuses that exact source
function standalone: walk the top of the investability_score_v2 ranking,
synthesize bios for everyone who has none (and enough papers to say
something factual), commit in batches so progress survives interruption.

Usage:
    from openscout.scraper.bio_backfill import backfill_bios
    backfill_bios(limit=400)
"""

from __future__ import annotations

import time

import httpx
from sqlalchemy import desc, func, select

from ..db import session_scope
from ..models import PaperAuthor, Researcher
from . import llm
from .deep_dive import HEADERS, _bio_synth

# Researchers per session_scope — commit every batch so progress persists
# even if the run dies mid-way.
BATCH_SIZE = 20
# Pause between LLM calls. DeepSeek is fast; this is just politeness.
SLEEP_SECONDS = 0.3
# API-outage guard (same philosophy as classify.py's short-circuit): if this
# many calls fail back-to-back, the provider is down — stop burning time.
MAX_CONSECUTIVE_LLM_ERRORS = 5

# `_bio_synth` requires ≥3 papers to synthesize; mirror that in the selection
# so we don't waste slots on researchers it would skip anyway.
MIN_PAPERS = 3


def _select_candidate_ids(db, limit: int) -> list[int]:
    """IDs of bio-less researchers with ≥3 paper links, best score first.

    NULLS LAST so unscored researchers queue behind every scored one; id
    tiebreak keeps the order deterministic.
    """
    rows = db.execute(
        select(Researcher.id)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .where(Researcher.bio.is_(None))
        .group_by(Researcher.id)
        .having(func.count(PaperAuthor.paper_id) >= MIN_PAPERS)
        .order_by(desc(Researcher.investability_score_v2).nulls_last(), Researcher.id.asc())
        .limit(limit)
    ).all()
    return [row[0] for row in rows]


def backfill_bios(limit: int = 400) -> dict[str, int]:
    """Synthesize bios + topic tags for the top `limit` bio-less researchers.

    Returns counts: {attempted, bio_set, tags_set, skipped_few_papers,
    llm_errors}. Stops early (committing progress) after
    MAX_CONSECUTIVE_LLM_ERRORS back-to-back LLM failures.
    """
    counts = {
        "attempted": 0,
        "bio_set": 0,
        "tags_set": 0,
        "skipped_few_papers": 0,
        "llm_errors": 0,
    }
    if not llm.is_available():
        return counts

    with session_scope() as db:
        ids = _select_candidate_ids(db, limit)

    consecutive_errors = 0
    # _bio_synth never touches the network itself (LLM goes through llm.py),
    # but its signature requires an httpx.Client — share one for the run.
    with httpx.Client(headers=HEADERS, follow_redirects=True) as http:
        for start in range(0, len(ids), BATCH_SIZE):
            batch = ids[start : start + BATCH_SIZE]
            with session_scope() as db:
                for rid in batch:
                    r = db.get(Researcher, rid)
                    if r is None:  # deleted between selection and processing
                        continue
                    counts["attempted"] += 1
                    bio_before = r.bio
                    tags_before = r.tags
                    result = _bio_synth(db, r, http)
                    note = str(result.get("note") or "")

                    if result.get("ok"):
                        if result.get("fields_set", 0) == 0 and "papers" in note:
                            # Race: paper links shrank below the threshold
                            # after selection. No LLM call was made — neither
                            # sleep nor touch the consecutive-error counter.
                            counts["skipped_few_papers"] += 1
                            continue
                        consecutive_errors = 0
                        if bio_before is None and r.bio:
                            counts["bio_set"] += 1
                        # _bio_synth reassigns r.tags (new list) on update.
                        if r.tags is not tags_before:
                            counts["tags_set"] += 1
                    else:
                        counts["llm_errors"] += 1
                        consecutive_errors += 1
                        if consecutive_errors >= MAX_CONSECUTIVE_LLM_ERRORS:
                            # Returning inside session_scope still commits
                            # this batch's progress on context exit.
                            return counts
                    time.sleep(SLEEP_SECONDS)
    return counts
