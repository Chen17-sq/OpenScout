"""Tests for src/openscout/scraper/awards.py — award-roster scraper.

`scrape_awards()` orchestrates four per-source helpers (ACM, Sloan, Packard,
TR35) and matches recipient names against the researchers table. We mock the
HTTP layer so no real Wikipedia/Packard/MIT traffic happens.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from openscout.db import session_scope
from openscout.models import Researcher, Signal
from openscout.scraper import awards as awards_mod


@pytest.fixture(autouse=True)
def _clean_tables():
    """Wipe Signal + Researcher between tests — fixture schema is session-scoped."""
    with session_scope() as db:
        db.query(Signal).delete()
        db.query(Researcher).delete()
    yield


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_researcher(slug: str, name_en: str) -> int:
    with session_scope() as db:
        r = Researcher(slug=slug, name_en=name_en)
        db.add(r)
        db.flush()
        return int(r.id)


def _make_response(status_code: int, *, text: str = "", json_data: dict | None = None):
    """Stand-in for httpx.Response — only the attrs the scraper reads."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    resp.headers = {}
    return resp


# ── signature smoke ───────────────────────────────────────────────────────────


def test_scrape_awards_signature_takes_no_args():
    sig = inspect.signature(awards_mod.scrape_awards)
    # No required parameters
    required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert required == []


# ── empty-DB return shape ─────────────────────────────────────────────────────


def test_scrape_awards_returns_expected_keys_on_empty_db():
    """With no researchers and all HTTP mocked to 404, we still get the
    documented counts dict."""
    with patch("httpx.Client.get", return_value=_make_response(404)):
        out = awards_mod.scrape_awards()
    expected_keys = {
        "sources_scraped",
        "recipients_seen",
        "matched_researchers",
        "errors",
        "signals_added",
    }
    assert set(out.keys()) == expected_keys
    assert out["matched_researchers"] == 0
    assert out["signals_added"] == 0


# ── mocked-network success path ───────────────────────────────────────────────


_ACM_WIKI_HTML = """
<html><body>
<table class="wikitable">
<tr><th>Year</th><th>Recipient</th></tr>
<tr><td>2023</td><td>Alice Researcher</td></tr>
<tr><td>2022</td><td>Bob Builder</td></tr>
</table>
</body></html>
"""


def _wiki_acm_response():
    """Canned Wikipedia action=parse JSON envelope."""
    return _make_response(
        200,
        json_data={"parse": {"text": {"*": _ACM_WIKI_HTML}}},
    )


def test_scrape_awards_matches_acm_recipient_and_emits_signal():
    """ACM Wikipedia helper finds Alice; sloan/packard/tr35 return 404."""
    _make_researcher("alice-researcher", "Alice Researcher")

    call_count = {"n": 0}

    def fake_get(self, url, **kwargs):
        # First call goes to the action=parse API for ACM page; subsequent
        # calls go to Sloan / Packard / TR35 — all 404 in this scenario.
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _wiki_acm_response()
        return _make_response(404)

    with patch("httpx.Client.get", new=fake_get):
        out = awards_mod.scrape_awards()

    # Alice should have been matched and emit a Signal
    assert out["recipients_seen"] >= 2  # both Alice + Bob harvested
    assert out["signals_added"] >= 1
    with session_scope() as db:
        rows = db.query(Signal).filter(Signal.type == "award").all()
        assert len(rows) >= 1
        names = {(r.payload or {}).get("recipient_name") for r in rows}
        assert "Alice Researcher" in names


# ── idempotency ───────────────────────────────────────────────────────────────


def test_scrape_awards_is_idempotent_on_rerun():
    """Running the same scrape twice doesn't double-write Signal rows."""
    _make_researcher("alice-researcher", "Alice Researcher")

    def fake_get(self, url, **kwargs):
        if "api.php" in url or "ACM" in url:
            return _wiki_acm_response()
        return _make_response(404)

    with patch("httpx.Client.get", new=fake_get):
        awards_mod.scrape_awards()
        with session_scope() as db:
            count_after_first = db.query(Signal).filter(Signal.type == "award").count()

        awards_mod.scrape_awards()
        with session_scope() as db:
            count_after_second = db.query(Signal).filter(Signal.type == "award").count()

    assert count_after_second == count_after_first
