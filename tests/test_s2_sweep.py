"""Tests for src/openscout/scraper/s2_sweep.py — no network.

Isolation trick: the suite shares one in-memory DB, so instead of wiping
tables (FK headaches with leftovers from other modules) each test gives its
researcher a sky-high `investability_score_v2` and calls `sweep_s2(limit=1)`.
The ORDER BY investability DESC NULLS LAST guarantees only that researcher
is selected.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from openscout.db import session_scope
from openscout.models import Paper, PaperAuthor, Researcher
from openscout.scraper.s2_sweep import SLEEP_BETWEEN_REQUESTS, SLEEP_ON_429, sweep_s2


def _make_researcher_with_paper(slug: str, *, name_en: str, paper_title: str, score: float) -> int:
    """Researcher + one linked paper (the title S2 disambiguation matches on).

    `score` must beat every still-unmatched researcher left over from earlier
    tests in this module (e.g. the ambiguous-skip one keeps a NULL s2 id), so
    each test uses a higher score than the previous one.
    """
    with session_scope() as db:
        r = Researcher(slug=slug, name_en=name_en, investability_score_v2=score)
        db.add(r)
        db.flush()
        p = Paper(title=paper_title)
        db.add(p)
        db.flush()
        db.add(PaperAuthor(paper_id=p.id, researcher_id=r.id, position=1))
        return int(r.id)


def _make_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ── match path ────────────────────────────────────────────────────────────────


def test_sweep_matches_on_title_overlap_and_fills_fields():
    rid = _make_researcher_with_paper(
        "s2-alice",
        name_en="Alice Liu",
        paper_title="World Models for Dexterous Manipulation",
        score=90001.0,
    )

    payload = {
        "data": [
            {
                "authorId": "9111",
                "name": "Alice Liu",
                "homepage": "https://aliceliu.example.com",
                "hIndex": 7,
                "citationCount": 321,
                "paperCount": 12,
                "papers": [{"title": "World Models for Dexterous Manipulation"}],
            },
            {
                # Same-name decoy with zero overlap — must lose to the first.
                "authorId": "9999",
                "name": "Alice Liu",
                "hIndex": 40,
                "citationCount": 9000,
                "paperCount": 200,
                "papers": [{"title": "Unrelated Protein Folding Survey"}],
            },
        ]
    }

    with (
        patch("httpx.Client.get", return_value=_make_response(200, payload)) as mock_get,
        patch("time.sleep") as mock_sleep,
    ):
        out = sweep_s2(limit=1)

    assert mock_get.call_count == 1
    # Strict pacing: the 1.05s inter-request sleep fired
    assert any(c.args == (SLEEP_BETWEEN_REQUESTS,) for c in mock_sleep.call_args_list)
    assert out["attempted"] == 1
    assert out["matched"] == 1
    assert out["fields_updated"] == 3  # h_index + citation_count + homepage_url
    assert out["ambiguous_skipped"] == 0
    assert out["errors"] == 0

    with session_scope() as db:
        r = db.get(Researcher, rid)
        assert r.semantic_scholar_id == "9111"
        assert r.h_index == 7
        assert r.citation_count == 321
        assert r.homepage_url == "https://aliceliu.example.com"


# ── ambiguous-skip path ───────────────────────────────────────────────────────


def test_sweep_skips_when_multiple_candidates_and_no_title_overlap():
    rid = _make_researcher_with_paper(
        "s2-bob",
        name_en="Wang Jing",
        paper_title="Embodied Agents in Open Worlds",
        score=90002.0,
    )

    payload = {
        "data": [
            {"authorId": "8001", "paperCount": 30, "papers": [{"title": "Topic A"}]},
            {"authorId": "8002", "paperCount": 50, "papers": [{"title": "Topic B"}]},
        ]
    }

    with (
        patch("httpx.Client.get", return_value=_make_response(200, payload)),
        patch("time.sleep"),
    ):
        out = sweep_s2(limit=1)

    assert out["attempted"] == 1
    assert out["matched"] == 0
    assert out["ambiguous_skipped"] == 1
    assert out["fields_updated"] == 0

    with session_scope() as db:
        r = db.get(Researcher, rid)
        assert r.semantic_scholar_id is None
        assert r.h_index is None


# ── 429 retry path ────────────────────────────────────────────────────────────


def test_sweep_retries_once_after_429():
    rid = _make_researcher_with_paper(
        "s2-carol",
        name_en="Carol Chen",
        paper_title="Diffusion Policies for Soft Robots",
        score=90003.0,
    )

    payload = {
        "data": [
            {
                "authorId": "7333",
                "hIndex": 3,
                "citationCount": 45,
                "paperCount": 6,
                "papers": [{"title": "Diffusion Policies for Soft Robots"}],
            }
        ]
    }

    responses = [_make_response(429), _make_response(200, payload)]

    def fake_get(self, url, **kwargs):
        return responses.pop(0)

    with (
        patch("httpx.Client.get", new=fake_get),
        patch("time.sleep") as mock_sleep,
    ):
        out = sweep_s2(limit=1)

    assert responses == []  # both responses consumed → exactly one retry
    assert any(c.args == (SLEEP_ON_429,) for c in mock_sleep.call_args_list)
    assert out["attempted"] == 1
    assert out["matched"] == 1
    assert out["errors"] == 0

    with session_scope() as db:
        r = db.get(Researcher, rid)
        assert r.semantic_scholar_id == "7333"
