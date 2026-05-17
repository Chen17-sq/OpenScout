"""Tests for src/openscout/scraper/jobs.py — async deep-dive runner."""

from __future__ import annotations

import time

import pytest

from openscout.db import session_scope
from openscout.models import DeepDiveJob, Researcher
from openscout.scraper import deep_dive as deep_dive_mod
from openscout.scraper import jobs


@pytest.fixture(autouse=True)
def _clean_job_tables():
    """Wipe the job + researcher tables before each test — session-scoped
    schema fixture leaks rows otherwise."""
    with session_scope() as db:
        db.query(DeepDiveJob).delete()
        db.query(Researcher).delete()
    yield


def _make_researcher(slug: str, name: str = "Test Person") -> int:
    with session_scope() as db:
        r = Researcher(slug=slug, name_en=name)
        db.add(r)
        db.flush()
        return int(r.id)


def _wait_for_terminal(job_id: int, timeout_s: float = 3.0) -> dict:
    """Poll the job row until state is no longer queued/running, or timeout."""
    end = time.time() + timeout_s
    last: dict | None = None
    while time.time() < end:
        last = jobs.get(job_id)
        if last and last["state"] not in ("queued", "running"):
            return last
        time.sleep(0.02)
    return last or {}


def test_enqueue_inserts_queued_row(monkeypatch):
    """enqueue() returns a dict with state in {queued, running, succeeded}
    and the row exists in the DB."""
    # Mock the dive so the worker thread finishes near-instantly with a
    # known result — no real network.
    monkeypatch.setattr(
        deep_dive_mod,
        "deep_dive_one",
        lambda slug, force=False: {"slug": slug, "sources": {}, "fields_total": 0},
    )
    _make_researcher("alice")
    out = jobs.enqueue("alice", ip_address="1.2.3.4", force=False)
    assert "id" in out
    assert out["slug"] == "alice"
    assert out["state"] in ("queued", "running", "succeeded")


def test_enqueue_unknown_slug_returns_error():
    out = jobs.enqueue("does-not-exist")
    assert "error" in out
    assert "not found" in out["error"]


def test_enqueue_dedupes_running_job(monkeypatch):
    """If a job for the slug is already queued/running, enqueue returns the SAME row."""
    # Make the dive block long enough for the second enqueue to see "running".
    started = []

    def slow_dive(slug, force=False):
        started.append(slug)
        time.sleep(0.5)
        return {"slug": slug, "sources": {}}

    monkeypatch.setattr(deep_dive_mod, "deep_dive_one", slow_dive)
    _make_researcher("bob")
    out1 = jobs.enqueue("bob")
    out2 = jobs.enqueue("bob")
    assert out1["id"] == out2["id"]
    # Wait so the slow dive doesn't bleed past the test's fixture teardown.
    _wait_for_terminal(int(out1["id"]), timeout_s=3.0)


def test_get_returns_none_for_missing():
    assert jobs.get(999_999) is None


def test_get_returns_dict_for_existing(monkeypatch):
    monkeypatch.setattr(
        deep_dive_mod,
        "deep_dive_one",
        lambda slug, force=False: {"slug": slug, "sources": {}},
    )
    _make_researcher("carol")
    out = jobs.enqueue("carol")
    fetched = jobs.get(int(out["id"]))
    assert fetched is not None
    assert fetched["slug"] == "carol"


def test_succeeded_state_after_dive(monkeypatch):
    """End-to-end: worker thread runs the (mocked) dive, transitions to succeeded,
    persists progress + result."""
    monkeypatch.setattr(
        deep_dive_mod,
        "deep_dive_one",
        lambda slug, force=False: {
            "slug": slug,
            "sources": {
                "arxiv_author": {"ok": True, "fields_set": 1, "note": "+1 paper", "ran": True},
                "openalex_full": {"ok": True, "fields_set": 0, "note": "no id", "ran": True},
            },
            "fields_total": 1,
        },
    )
    _make_researcher("dave")
    out = jobs.enqueue("dave")
    final = _wait_for_terminal(int(out["id"]))
    assert final["state"] == "succeeded"
    assert final["error"] is None
    assert final["result"]["slug"] == "dave"
    # progress is flattened: list of dicts with `source` key from the result.sources map
    assert isinstance(final["progress"], list)
    assert len(final["progress"]) == 2
    source_names = {p["source"] for p in final["progress"]}
    assert source_names == {"arxiv_author", "openalex_full"}


def test_failed_state_when_dive_raises(monkeypatch):
    def boom(slug, force=False):
        raise RuntimeError("dive blew up")

    monkeypatch.setattr(deep_dive_mod, "deep_dive_one", boom)
    _make_researcher("eve")
    out = jobs.enqueue("eve")
    final = _wait_for_terminal(int(out["id"]))
    assert final["state"] == "failed"
    assert "RuntimeError" in (final["error"] or "")
    assert "dive blew up" in (final["error"] or "")
