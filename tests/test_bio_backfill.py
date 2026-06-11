"""Tests for src/openscout/scraper/bio_backfill.py.

Never hit the network or the LLM — `_bio_synth` is mocked where needed.
Uses the shared in-memory SQLite from conftest.py; assertions filter to the
rows created here so leftovers from other test files can't interfere.
"""

from __future__ import annotations

from openscout.db import session_scope
from openscout.models import Paper, PaperAuthor, Researcher
from openscout.scraper import bio_backfill
from openscout.scraper.bio_backfill import _select_candidate_ids, backfill_bios


def _mk_researcher(db, slug: str, score: float | None, bio: str | None = None) -> Researcher:
    r = Researcher(slug=slug, name_en=slug.replace("-", " ").title(), bio=bio)
    r.investability_score_v2 = score
    db.add(r)
    db.flush()
    return r


def _link_papers(db, researcher_id: int, n: int, slug: str) -> None:
    for i in range(n):
        p = Paper(title=f"paper {slug} {i}", abstract=f"abstract {i}")
        db.add(p)
        db.flush()
        db.add(PaperAuthor(paper_id=p.id, researcher_id=researcher_id, position=1))
    db.flush()


def test_selection_orders_by_score_and_skips_ineligible():
    with session_scope() as db:
        # Eligible: bio NULL + ≥3 papers. Scores deliberately out of
        # insertion order to prove the ORDER BY.
        mid = _mk_researcher(db, "bb-mid-score", 50.0)
        top = _mk_researcher(db, "bb-top-score", 99.0)
        unscored = _mk_researcher(db, "bb-null-score", None)  # NULLS LAST
        # Ineligible: already has a bio (even with the best score)…
        has_bio = _mk_researcher(db, "bb-has-bio", 999.0, bio="Already written.")
        # …or too few paper links.
        few = _mk_researcher(db, "bb-few-papers", 98.0)

        for r in (mid, top, unscored, has_bio):
            _link_papers(db, r.id, 3, r.slug)
        _link_papers(db, few.id, 2, few.slug)

        mine = {top.id, mid.id, unscored.id, has_bio.id, few.id}
        selected = _select_candidate_ids(db, limit=10_000)

        assert has_bio.id not in selected
        assert few.id not in selected
        # Relative order among our rows: high score → low score → NULL score.
        ours_in_order = [rid for rid in selected if rid in mine]
        assert ours_in_order == [top.id, mid.id, unscored.id]


def test_consecutive_llm_errors_short_circuit(monkeypatch):
    with session_scope() as db:
        # More candidates than the error threshold — the run must stop early.
        for i in range(bio_backfill.MAX_CONSECUTIVE_LLM_ERRORS + 2):
            r = _mk_researcher(db, f"bb-err-{i}", 1000.0 - i)
            _link_papers(db, r.id, 3, r.slug)

    calls = []

    def _always_fail(db, r, http):
        calls.append(r.id)
        return {"ok": False, "fields_set": 0, "note": "llm err: simulated outage"}

    monkeypatch.setattr(bio_backfill, "_bio_synth", _always_fail)
    monkeypatch.setattr(bio_backfill.llm, "is_available", lambda: True)
    monkeypatch.setattr(bio_backfill, "SLEEP_SECONDS", 0)

    counts = backfill_bios(limit=400)

    threshold = bio_backfill.MAX_CONSECUTIVE_LLM_ERRORS
    assert len(calls) == threshold  # stopped exactly at the threshold
    assert counts["attempted"] == threshold
    assert counts["llm_errors"] == threshold
    assert counts["bio_set"] == 0
    assert counts["tags_set"] == 0
