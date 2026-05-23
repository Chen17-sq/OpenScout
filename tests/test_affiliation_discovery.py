"""Tests for src/openscout/scraper/affiliation_discovery.py.

The orchestrator scans researchers with NULL `current_affiliation_id` and
tries OpenAlex → Semantic Scholar → bio-leftover in order. We mock the HTTP
client for the first two and inject a researcher with the bio shape for the
third.

This module does NOT call any LLM (despite the task hint) — sources are
OpenAlex/S2/bio regex only. Confirmed by reading the source.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from openscout.db import session_scope
from openscout.models import Institution, Researcher
from openscout.scraper import affiliation_discovery as ad_mod


@pytest.fixture(autouse=True)
def _clean_tables():
    """Wipe researchers + institutions between tests."""
    with session_scope() as db:
        # Detach FK first to avoid integrity errors on delete
        for r in db.query(Researcher).all():
            r.current_affiliation_id = None
        db.flush()
        db.query(Researcher).delete()
        db.query(Institution).delete()
    yield


def _make_researcher(
    slug: str,
    *,
    name_en: str = "Test Person",
    openalex_id: str | None = None,
    semantic_scholar_id: str | None = None,
    bio: str | None = None,
) -> int:
    with session_scope() as db:
        r = Researcher(
            slug=slug,
            name_en=name_en,
            openalex_id=openalex_id,
            semantic_scholar_id=semantic_scholar_id,
            bio=bio,
        )
        db.add(r)
        db.flush()
        return int(r.id)


def _make_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ── signature smoke ───────────────────────────────────────────────────────────


def test_discover_affiliations_signature():
    sig = inspect.signature(ad_mod.discover_affiliations)
    assert "limit" in sig.parameters
    assert sig.parameters["limit"].default is None
    required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert required == []


# ── empty-DB return shape ─────────────────────────────────────────────────────


def test_discover_affiliations_empty_db_returns_expected_keys():
    """No researchers needing resolution → all-zero counts, never touches the network."""
    with patch("httpx.Client.get") as mock_get:
        out = ad_mod.discover_affiliations()
        mock_get.assert_not_called()
    assert set(out.keys()) == {
        "scanned",
        "matched_openalex",
        "matched_s2",
        "matched_bio",
        "created_institution",
        "errors",
    }
    assert all(v == 0 for v in out.values())


# ── mocked-network success path: OpenAlex hit ─────────────────────────────────


_OPENALEX_AUTHOR_PAYLOAD = {
    "last_known_institution": {
        "id": "https://openalex.org/I12345",
        "display_name": "Test University",
        "country_code": "US",
    }
}


def test_discover_affiliations_openalex_hit_fills_field_and_creates_institution():
    """Alice has openalex_id but no current_affiliation_id; mock OpenAlex to
    return a known institution; verify Institution row is created and FK set."""
    _make_researcher("alice", openalex_id="A1234567")

    with (
        patch("httpx.Client.get", return_value=_make_response(200, _OPENALEX_AUTHOR_PAYLOAD)),
        patch("time.sleep"),
    ):
        out = ad_mod.discover_affiliations()

    assert out["scanned"] == 1
    assert out["matched_openalex"] == 1
    assert out["created_institution"] == 1
    with session_scope() as db:
        r = db.query(Researcher).filter_by(slug="alice").one()
        assert r.current_affiliation_id is not None
        assert r.affiliation_source == "openalex"
        inst = db.query(Institution).filter_by(id=r.current_affiliation_id).one()
        assert inst.name == "Test University"
        assert inst.country == "US"


# ── bio-leftover branch (no HTTP at all) ──────────────────────────────────────


def test_discover_affiliations_bio_leftover_branch():
    """The bio-pattern lookup runs entirely in-process; no HTTP needed."""
    _make_researcher(
        "bob",
        name_en="Bob Builder",
        bio="Acme Research Lab · (per Semantic Scholar)",
    )

    # We still mock httpx.Client to be safe — bob has no openalex/s2 IDs so
    # the scraper should never call get().
    with (
        patch("httpx.Client.get", return_value=_make_response(500)),
        patch("time.sleep"),
    ):
        out = ad_mod.discover_affiliations()

    assert out["matched_bio"] == 1
    assert out["created_institution"] == 1
    with session_scope() as db:
        r = db.query(Researcher).filter_by(slug="bob").one()
        assert r.affiliation_source == "bio_s2_leftover"
        inst = db.query(Institution).filter_by(id=r.current_affiliation_id).one()
        assert inst.name == "Acme Research Lab"


# ── idempotency ───────────────────────────────────────────────────────────────


def test_discover_affiliations_is_idempotent_after_resolution():
    """Once a researcher has a current_affiliation_id, the next run skips
    them entirely — `scanned` drops back to 0."""
    _make_researcher("alice", openalex_id="A1234567")

    with (
        patch("httpx.Client.get", return_value=_make_response(200, _OPENALEX_AUTHOR_PAYLOAD)),
        patch("time.sleep"),
    ):
        first = ad_mod.discover_affiliations()
        second = ad_mod.discover_affiliations()

    assert first["scanned"] == 1
    assert second["scanned"] == 0
    assert second["created_institution"] == 0
