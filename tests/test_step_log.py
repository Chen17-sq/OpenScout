"""Tests for src/openscout/scraper/step_log.py — per-step freshness gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from openscout.db import session_scope
from openscout.models import StepLog
from openscout.scraper import step_log


@pytest.fixture(autouse=True)
def _clean_step_log():
    """Wipe step_log between tests — session-scoped DB fixture leaks rows."""
    with session_scope() as db:
        db.query(StepLog).delete()
    yield


def test_record_creates_row():
    step_log.record("arxiv ingest [embodied]", "ok", {"fetched": 3, "added": 1})
    with session_scope() as db:
        row = db.query(StepLog).filter_by(step_name="arxiv ingest [embodied]").one()
    assert row.last_status == "ok"
    assert row.last_result_json == {"fetched": 3, "added": 1}


def test_record_upserts_same_step():
    step_log.record("twitter scrape", "ok", {"updated": 2})
    step_log.record("twitter scrape", "failed", {"error": "rate limit"})
    with session_scope() as db:
        rows = db.query(StepLog).filter_by(step_name="twitter scrape").all()
    assert len(rows) == 1
    assert rows[0].last_status == "failed"
    assert rows[0].last_result_json == {"error": "rate limit"}


def test_should_skip_fresh_ok():
    step_log.record("awards roster", "ok", {"added": 0})
    # Just recorded — within ANY non-zero window.
    assert step_log.should_skip("awards roster", min_hours=168) is True


def test_should_skip_zero_hours_disabled():
    """min_hours=0 means freshness gate disabled — never skip."""
    step_log.record("awards roster", "ok", {"added": 0})
    assert step_log.should_skip("awards roster", min_hours=0) is False


def test_should_skip_after_failed_run():
    """A failed last_run should NOT block a retry."""
    step_log.record("conference PC/AC", "failed", {"error": "boom"})
    assert step_log.should_skip("conference PC/AC", min_hours=720) is False


def test_should_skip_after_window_elapsed():
    """Manually backdate the row to outside the window."""
    step_log.record("lineage inference", "ok", {"edges_added": 0})
    with session_scope() as db:
        row = db.query(StepLog).filter_by(step_name="lineage inference").one()
        # Backdate to 49 hours ago (outside the 48h gate).
        row.last_run_at = datetime.now(UTC) - timedelta(hours=49)
    assert step_log.should_skip("lineage inference", min_hours=48) is False


def test_should_skip_missing_step_returns_false():
    """Never-run step is never skipped — always wants a first run."""
    assert step_log.should_skip("brand new step", min_hours=24) is False


def test_last_run_returns_timestamp():
    step_log.record("step A", "ok", None)
    ts = step_log.last_run("step A")
    assert ts is not None
    # Should be within a few seconds of now.
    delta = datetime.now(UTC) - ts
    assert delta.total_seconds() < 10


def test_last_run_missing_returns_none():
    assert step_log.last_run("never") is None


def test_record_coerces_weird_results():
    """Steps return ints/None/Path/whatever — payload must serialise."""
    step_log.record("step int", "ok", 42)
    step_log.record("step none", "ok", None)
    step_log.record("step path", "ok", "/tmp/x.svg")
    with session_scope() as db:
        rows = {r.step_name: r.last_result_json for r in db.query(StepLog).all()}
    assert rows["step int"] == {"value": 42}
    assert rows["step none"] is None
    assert rows["step path"] == {"value": "/tmp/x.svg"}


def test_step_wrapper_skips_when_fresh(monkeypatch):
    """Integration: `_step()` must short-circuit on freshness."""
    from openscout import cli_daily

    # Reset module-level filter state so other tests don't leak.
    cli_daily._only_terms = []
    cli_daily._skip_terms = []
    cli_daily._force = False

    calls = {"n": 0}

    def fake_fn():
        calls["n"] += 1
        return {"x": 1}

    # First call — runs, records ok.
    r1 = cli_daily._step("fresh-test", fake_fn, min_hours=24)
    assert r1["ok"] is True and not r1.get("skipped")
    assert calls["n"] == 1

    # Second call — should be skipped (fresh).
    r2 = cli_daily._step("fresh-test", fake_fn, min_hours=24)
    assert r2.get("skipped") is True
    assert "fresh" in r2["skip_reason"]
    assert calls["n"] == 1  # NOT incremented

    # --force should bypass.
    cli_daily._force = True
    r3 = cli_daily._step("fresh-test", fake_fn, min_hours=24)
    assert not r3.get("skipped")
    assert calls["n"] == 2

    cli_daily._force = False


def test_step_wrapper_only_filter():
    from openscout import cli_daily

    cli_daily._only_terms = ["arxiv"]
    cli_daily._skip_terms = []
    cli_daily._force = False

    calls = {"n": 0}

    def fake():
        calls["n"] += 1

    r1 = cli_daily._step("arxiv ingest [foo]", fake)
    r2 = cli_daily._step("twitter scrape", fake)

    assert not r1.get("skipped")
    assert r2.get("skipped")
    assert "--only" in r2["skip_reason"]
    assert calls["n"] == 1

    cli_daily._only_terms = []


def test_step_wrapper_skip_filter():
    from openscout import cli_daily

    cli_daily._only_terms = []
    cli_daily._skip_terms = ["twitter"]
    cli_daily._force = False

    calls = {"n": 0}

    def fake():
        calls["n"] += 1

    r1 = cli_daily._step("arxiv ingest", fake)
    r2 = cli_daily._step("twitter / nitter scrape", fake)

    assert not r1.get("skipped")
    assert r2.get("skipped")
    assert "--skip" in r2["skip_reason"]
    assert calls["n"] == 1

    cli_daily._skip_terms = []
