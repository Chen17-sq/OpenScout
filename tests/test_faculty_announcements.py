"""Tests for src/openscout/scraper/faculty_announcements.py — faculty-page diff.

The scraper fetches per-university directory pages, diffs against a local
cache, and promotes matching PhD/postdoc researchers to `incoming_ap`. We
mock httpx.Client.get and point the cache directory at a tmp_path.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from openscout.db import session_scope
from openscout.models import Researcher, Signal
from openscout.scraper import faculty_announcements as fa_mod


@pytest.fixture(autouse=True)
def _clean_tables():
    with session_scope() as db:
        db.query(Signal).delete()
        db.query(Researcher).delete()
    yield


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Point the cache dir at a per-test tmp dir so the on-disk JSON doesn't
    leak between tests or pollute the repo's `data/faculty_cache/`."""
    monkeypatch.setattr(fa_mod, "CACHE_DIR", tmp_path / "faculty_cache")
    yield


def _make_researcher(slug: str, name_en: str, current_role: str | None = "phd") -> int:
    with session_scope() as db:
        r = Researcher(slug=slug, name_en=name_en, current_role=current_role)
        db.add(r)
        db.flush()
        return int(r.id)


def _make_response(status_code: int, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ── signature smoke ───────────────────────────────────────────────────────────


def test_scrape_faculty_pages_signature():
    sig = inspect.signature(fa_mod.scrape_faculty_pages)
    assert "universities" in sig.parameters
    assert sig.parameters["universities"].default is None
    # No required positional args — caller can pass nothing
    required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert required == []


# ── empty-DB return shape ─────────────────────────────────────────────────────


def test_scrape_faculty_pages_empty_db_returns_expected_keys():
    """Every university page mocked to 404 — counts dict still has the right keys."""
    tiny_pages = [
        {"slug": "test_u", "name": "Test University", "url": "https://x.test", "selector": "h3"}
    ]
    with (
        patch("httpx.Client.get", return_value=_make_response(404)),
        patch("time.sleep"),
    ):
        out = fa_mod.scrape_faculty_pages(universities=tiny_pages)
    assert set(out.keys()) == {
        "universities",
        "names_seen",
        "matched_researchers",
        "promoted_to_incoming_ap",
        "errors",
    }
    # 404 counts as an error and does not increment matched/promoted
    assert out["universities"] == 1
    assert out["errors"] == 1
    assert out["matched_researchers"] == 0
    assert out["promoted_to_incoming_ap"] == 0


# ── mocked-network success path ───────────────────────────────────────────────


# Padded with filler text so the body exceeds the 200-char minimum that
# `_fetch_html` enforces (it treats <200-char responses as "empty / broken page").
_FACULTY_PAGE_HTML = """
<html><head><title>Faculty Directory</title></head>
<body>
<h1>Faculty Directory</h1>
<p>Our faculty are leaders in their fields. Below is the current roster of
appointed and incoming professors, listed alphabetically.</p>
<h3>Alice Anchor</h3>
<h3>Bob Builder</h3>
<h3>Carol Coder</h3>
</body></html>
"""


def test_scrape_faculty_pages_promotes_phd_to_incoming_ap():
    """Alice is a PhD in the DB. The mocked faculty page lists her name; she
    should be promoted to incoming_ap and emit a faculty_announcement Signal."""
    _make_researcher("alice-anchor", "Alice Anchor", current_role="phd")
    tiny_pages = [
        {
            "slug": "test_u",
            "name": "Test University",
            "url": "https://x.test",
            "selector": "h3",
        }
    ]

    with (
        patch("httpx.Client.get", return_value=_make_response(200, _FACULTY_PAGE_HTML)),
        patch("time.sleep"),
    ):
        out = fa_mod.scrape_faculty_pages(universities=tiny_pages)

    assert out["names_seen"] >= 3
    assert out["matched_researchers"] >= 1
    assert out["promoted_to_incoming_ap"] >= 1
    with session_scope() as db:
        r = db.query(Researcher).filter_by(name_en="Alice Anchor").one()
        assert r.current_role == "incoming_ap"
        assert r.role_source == "faculty_page"
        sigs = db.query(Signal).filter(Signal.type == "faculty_announcement").all()
        assert len(sigs) >= 1


# ── idempotency: rerun doesn't double-promote ─────────────────────────────────


def test_scrape_faculty_pages_does_not_re_promote_already_incoming_ap():
    """Once a researcher is `incoming_ap`, a re-run keeps her there and the
    promotion counter only counts the FIRST transition.

    Note: this scraper DOES still emit a fresh faculty_announcement Signal on
    every run (by design — appearance on a new page is news). So we only
    assert no NEW promotion happened, not zero new Signal rows.
    """
    _make_researcher("alice-anchor", "Alice Anchor", current_role="phd")
    tiny_pages = [
        {
            "slug": "test_u",
            "name": "Test University",
            "url": "https://x.test",
            "selector": "h3",
        }
    ]

    with (
        patch("httpx.Client.get", return_value=_make_response(200, _FACULTY_PAGE_HTML)),
        patch("time.sleep"),
    ):
        out1 = fa_mod.scrape_faculty_pages(universities=tiny_pages)
        out2 = fa_mod.scrape_faculty_pages(universities=tiny_pages)

    assert out1["promoted_to_incoming_ap"] >= 1
    # Second run: Alice is already incoming_ap → no fresh promotion
    assert out2["promoted_to_incoming_ap"] == 0
