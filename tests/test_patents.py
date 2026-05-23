"""Tests for src/openscout/scraper/patents.py — Google Patents lookup."""

from __future__ import annotations

import inspect
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from openscout.db import session_scope
from openscout.models import Paper, PaperAuthor, Researcher, Signal
from openscout.scraper import patents as patents_mod


@pytest.fixture(autouse=True)
def _clean_tables():
    with session_scope() as db:
        db.query(Signal).delete()
        db.query(PaperAuthor).delete()
        db.query(Paper).delete()
        db.query(Researcher).delete()
    yield


def _make_industry_author(name: str) -> int:
    """Insert a researcher who co-authored a paper carrying an industry email
    (`openai.com`). That's the trigger for inclusion in the patent search."""
    with session_scope() as db:
        r = Researcher(slug="industry-author", name_en=name)
        db.add(r)
        db.flush()
        p = Paper(
            arxiv_id="2401.99999",
            title="Industry Paper",
            published_at=date.today(),
            author_emails=["someone@openai.com"],
        )
        db.add(p)
        db.flush()
        db.add(PaperAuthor(paper_id=p.id, researcher_id=r.id, position=1))
        db.flush()
        return int(r.id)


def _make_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ── signature smoke ───────────────────────────────────────────────────────────


def test_scrape_patents_signature():
    sig = inspect.signature(patents_mod.scrape_patents)
    assert "limit" in sig.parameters
    assert sig.parameters["limit"].default == 30
    required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert required == []


# ── empty-DB return shape ─────────────────────────────────────────────────────


def test_scrape_patents_empty_db_returns_expected_keys():
    """No industry authors in the DB → early-exit, no HTTP calls."""
    with patch("httpx.Client.get") as mock_get:
        out = patents_mod.scrape_patents(limit=5)
        mock_get.assert_not_called()
    assert set(out.keys()) == {"attempted", "with_patents", "patents_found", "errors"}
    assert all(v == 0 for v in out.values())


# ── mocked-network success path ───────────────────────────────────────────────


_GOOGLE_PATENTS_JSON = {
    "results": {
        "cluster": [
            {
                "result": [
                    {
                        "patent": {
                            "publication_number": "US20240000001A1",
                            "title": "Method for <b>doing</b> things",
                            "assignee": "OpenAI Inc.",
                            "filing_date": "2024-01-15",
                        }
                    }
                ]
            }
        ]
    }
}


def test_scrape_patents_records_signal_for_match():
    """Industry author Alice has one mocked Google Patents hit — verify the
    Signal row lands with the right keys."""
    rid = _make_industry_author("Alice Industry")

    with (
        patch("httpx.Client.get", return_value=_make_response(200, _GOOGLE_PATENTS_JSON)),
        patch("time.sleep"),
    ):
        out = patents_mod.scrape_patents(limit=5)

    assert out["attempted"] >= 1
    assert out["with_patents"] >= 1
    assert out["patents_found"] >= 1
    with session_scope() as db:
        sigs = db.query(Signal).filter(Signal.type == "patent").all()
        assert len(sigs) == 1
        assert sigs[0].researcher_id == rid
        assert sigs[0].source == "US20240000001A1"
        # The <b>…</b> highlight tags should be stripped from the title
        assert "<b>" not in (sigs[0].payload or {}).get("title", "")


# ── idempotency ───────────────────────────────────────────────────────────────


def test_scrape_patents_is_idempotent():
    """A re-run with the same mocked response doesn't double-write the patent
    Signal (dedup on publication_number). The recency guard (30-day window)
    also skips re-querying entirely on the second pass."""
    _make_industry_author("Alice Industry")

    with (
        patch("httpx.Client.get", return_value=_make_response(200, _GOOGLE_PATENTS_JSON)),
        patch("time.sleep"),
    ):
        patents_mod.scrape_patents(limit=5)
        with session_scope() as db:
            first = db.query(Signal).filter(Signal.type == "patent").count()

        patents_mod.scrape_patents(limit=5)
        with session_scope() as db:
            second = db.query(Signal).filter(Signal.type == "patent").count()

    assert second == first
    assert second >= 1
