"""Tests for src/openscout/api/quota.py — per-IP daily quota."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from openscout.api import quota as quota_mod
from openscout.db import session_scope
from openscout.models import DeepDiveQuota


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    """Minimal stand-in for fastapi.Request — only what `_ip_for_request` reads."""

    def __init__(
        self,
        ip: str = "1.2.3.4",
        xff: str | None = None,
        ingest_secret: str | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        if xff is not None:
            self.headers["x-forwarded-for"] = xff
        if ingest_secret is not None:
            self.headers["x-ingest-secret"] = ingest_secret
        self.client = _FakeClient(ip)


@pytest.fixture(autouse=True)
def _clean_quota_rows():
    """Wipe the deep_dive_quota table before each test — the conftest schema
    is session-scoped so rows otherwise leak between tests."""
    with session_scope() as db:
        db.query(DeepDiveQuota).delete()
    yield


def test_first_call_returns_count_one():
    req = _FakeRequest(ip="10.0.0.1")
    out = quota_mod.check_and_increment(req, daily_limit=3)
    assert out["count"] == 1
    assert out["remaining"] == 2
    assert out["limit"] == 3
    assert out["ip"] == "10.0.0.1"


def test_second_call_increments():
    req = _FakeRequest(ip="10.0.0.2")
    quota_mod.check_and_increment(req, daily_limit=3)
    out = quota_mod.check_and_increment(req, daily_limit=3)
    assert out["count"] == 2
    assert out["remaining"] == 1


def test_call_beyond_limit_raises_429():
    req = _FakeRequest(ip="10.0.0.3")
    quota_mod.check_and_increment(req, daily_limit=2)
    quota_mod.check_and_increment(req, daily_limit=2)
    with pytest.raises(HTTPException) as exc_info:
        quota_mod.check_and_increment(req, daily_limit=2)
    assert exc_info.value.status_code == 429
    # The 429 response should not silently mutate the counter
    with session_scope() as db:
        row = db.query(DeepDiveQuota).filter_by(ip_address="10.0.0.3").one()
        assert row.count == 2


def test_different_ips_are_isolated():
    req_a = _FakeRequest(ip="10.0.0.4")
    req_b = _FakeRequest(ip="10.0.0.5")
    quota_mod.check_and_increment(req_a, daily_limit=3)
    quota_mod.check_and_increment(req_a, daily_limit=3)
    out_b = quota_mod.check_and_increment(req_b, daily_limit=3)
    # B should still see count=1 — completely independent
    assert out_b["count"] == 1
    assert out_b["remaining"] == 2


def test_different_days_are_isolated(monkeypatch):
    """Simulating UTC midnight rollover — Day-N counter resets on Day-N+1."""
    req = _FakeRequest(ip="10.0.0.6")
    monkeypatch.setattr(quota_mod, "_today", lambda: "2026-05-17")
    quota_mod.check_and_increment(req, daily_limit=2)
    quota_mod.check_and_increment(req, daily_limit=2)
    # Day rolls over
    monkeypatch.setattr(quota_mod, "_today", lambda: "2026-05-18")
    out = quota_mod.check_and_increment(req, daily_limit=2)
    assert out["count"] == 1
    assert out["remaining"] == 1


def test_status_no_prior_use():
    req = _FakeRequest(ip="10.0.0.7")
    out = quota_mod.status(req, daily_limit=3)
    assert out["used"] == 0
    assert out["remaining"] == 3
    assert out["limit"] == 3


def test_status_after_increment_does_not_increment():
    req = _FakeRequest(ip="10.0.0.8")
    quota_mod.check_and_increment(req, daily_limit=3)
    out1 = quota_mod.status(req, daily_limit=3)
    out2 = quota_mod.status(req, daily_limit=3)
    assert out1["used"] == 1
    assert out2["used"] == 1  # status is read-only
    assert out1["remaining"] == 2


def test_xff_header_picks_originating_ip():
    """X-Forwarded-For takes precedence over socket client when set."""
    req = _FakeRequest(ip="10.0.0.99", xff="203.0.113.7, 10.0.0.99")
    out = quota_mod.check_and_increment(req, daily_limit=3)
    assert out["ip"] == "203.0.113.7"


def test_endpoint_label_in_429_detail():
    req = _FakeRequest(ip="10.0.0.10")
    quota_mod.check_and_increment(req, daily_limit=1, endpoint="custom_endpoint")
    with pytest.raises(HTTPException) as exc_info:
        quota_mod.check_and_increment(req, daily_limit=1, endpoint="custom_endpoint")
    assert "custom_endpoint" in exc_info.value.detail


def test_admin_secret_bypasses_429(monkeypatch):
    """A request carrying the matching X-Ingest-Secret header skips the
    quota even when an anonymous IP has been exhausted.

    Scenario: IP 10.0.0.11 exhausts the limit (cap=2). A third call with
    no secret would 429. A fourth call with the admin secret on the same
    IP succeeds anyway — and crucially must not bump the counter (it's an
    operator override, not a normal dive).
    """
    monkeypatch.setattr(quota_mod.settings, "ingest_secret", "real-secret")

    # Exhaust the IP's daily quota
    req_anon = _FakeRequest(ip="10.0.0.11")
    quota_mod.check_and_increment(req_anon, daily_limit=2)
    quota_mod.check_and_increment(req_anon, daily_limit=2)
    with pytest.raises(HTTPException) as exc_info:
        quota_mod.check_and_increment(req_anon, daily_limit=2)
    assert exc_info.value.status_code == 429

    # Same IP, but now with the admin header — must succeed
    req_admin = _FakeRequest(ip="10.0.0.11", ingest_secret="real-secret")
    out = quota_mod.check_and_increment(req_admin, daily_limit=2)
    assert out.get("admin_bypass") is True
    assert out["remaining"] == 2  # not decremented

    # The DB row for this IP must remain at the exhausted count
    with session_scope() as db:
        row = db.query(DeepDiveQuota).filter_by(ip_address="10.0.0.11").one()
        assert row.count == 2

    # Sanity: wrong secret falls through to the real quota path → still 429
    req_wrong = _FakeRequest(ip="10.0.0.11", ingest_secret="not-the-secret")
    with pytest.raises(HTTPException) as exc_info:
        quota_mod.check_and_increment(req_wrong, daily_limit=2)
    assert exc_info.value.status_code == 429

    # Sanity: even a correct-looking secret is refused when the server is
    # still on the default "change-me" — closes the prod-misconfig hole
    monkeypatch.setattr(quota_mod.settings, "ingest_secret", "change-me")
    req_default = _FakeRequest(ip="10.0.0.11", ingest_secret="change-me")
    with pytest.raises(HTTPException) as exc_info:
        quota_mod.check_and_increment(req_default, daily_limit=2)
    assert exc_info.value.status_code == 429
