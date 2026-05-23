"""Tests for src/openscout/scraper/conference_committees.py — PC/AC roll scraper."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from openscout.db import session_scope
from openscout.models import Researcher, Signal
from openscout.scraper import conference_committees as cc_mod


@pytest.fixture(autouse=True)
def _clean_tables():
    with session_scope() as db:
        db.query(Signal).delete()
        db.query(Researcher).delete()
    yield


def _make_researcher(slug: str, name_en: str) -> int:
    with session_scope() as db:
        r = Researcher(slug=slug, name_en=name_en)
        db.add(r)
        db.flush()
        return int(r.id)


def _make_response(status_code: int, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ── signature smoke ───────────────────────────────────────────────────────────


def test_scrape_conference_committees_signature():
    sig = inspect.signature(cc_mod.scrape_conference_committees)
    # Both kwargs have defaults; no required positional args
    required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert required == []
    assert sig.parameters["sleep_between"].default == 1.0
    assert sig.parameters["timeout"].default == 25.0


# ── empty-DB return shape ─────────────────────────────────────────────────────


def test_scrape_conference_committees_empty_db_returns_expected_keys():
    """With every TARGET page mocked to 404, the counts dict still has the
    right shape."""
    with (
        patch("httpx.Client.get", return_value=_make_response(404)),
        patch("time.sleep"),
    ):
        out = cc_mod.scrape_conference_committees(sleep_between=0.0)
    assert set(out.keys()) == {
        "conferences_scraped",
        "names_seen",
        "matched_researchers",
        "roles_recorded",
        "errors",
    }
    assert out["matched_researchers"] == 0
    assert out["roles_recorded"] == 0


# ── mocked-network success path ───────────────────────────────────────────────


_CC_BLOCKS_HTML = """
<html><body>
<h2>Senior Area Chair</h2>
<div class="reviewer-block">Alice Anchor<br>Bob Builder<br></div>
<h2>Area Chair</h2>
<div class="reviewer-block">Carol Coder<br></div>
</body></html>
"""


def test_scrape_conference_committees_matches_name_and_records_role():
    """Alice is in the DB; the mocked NeurIPS page lists her as a Senior Area
    Chair. Bob/Carol are not in the DB and shouldn't produce signals."""
    _make_researcher("alice-anchor", "Alice Anchor")

    def fake_get(self, url, **kwargs):
        # Return the same canned HTML for every TARGETS URL
        return _make_response(200, _CC_BLOCKS_HTML)

    with patch("httpx.Client.get", new=fake_get), patch("time.sleep"):
        out = cc_mod.scrape_conference_committees(sleep_between=0.0)

    assert out["conferences_scraped"] >= 1
    assert out["names_seen"] >= 3  # Alice + Bob + Carol
    assert out["matched_researchers"] >= 1
    assert out["roles_recorded"] >= 1
    with session_scope() as db:
        sigs = db.query(Signal).filter(Signal.type == "conference_role").all()
        assert len(sigs) >= 1
        # Alice should be the matched researcher (Bob/Carol absent from DB)
        payload = sigs[0].payload or {}
        assert payload.get("role") == "Senior Area Chair"


# ── idempotency ───────────────────────────────────────────────────────────────


def test_scrape_conference_committees_is_idempotent():
    """A second run with the same canned page must not re-insert the same
    (researcher, conf, year, role) Signal."""
    _make_researcher("alice-anchor", "Alice Anchor")

    def fake_get(self, url, **kwargs):
        return _make_response(200, _CC_BLOCKS_HTML)

    with patch("httpx.Client.get", new=fake_get), patch("time.sleep"):
        cc_mod.scrape_conference_committees(sleep_between=0.0)
        with session_scope() as db:
            first = db.query(Signal).filter(Signal.type == "conference_role").count()

        cc_mod.scrape_conference_committees(sleep_between=0.0)
        with session_scope() as db:
            second = db.query(Signal).filter(Signal.type == "conference_role").count()

    assert second == first
