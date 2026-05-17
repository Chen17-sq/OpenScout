"""Smoke tests for src/openscout/scraper/deep_dive.py + work_scoring helpers.

These never hit the network — they just verify shapes / signatures of the
SOURCES registry plus the pure functions in work_scoring.
"""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta

from openscout.scraper.deep_dive import SOURCES, _merge_tags
from openscout.scraper.work_scoring import (
    _industry_match,
    _junior_boost,
    _position_weight,
    _recency_multiplier,
)

# ── SOURCES registry shape ───────────────────────────────────────────────────


def test_sources_registry_nonempty():
    assert len(SOURCES) > 0


def test_sources_entries_are_name_callable_pairs():
    for entry in SOURCES:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        name, fn = entry
        assert isinstance(name, str) and name
        assert callable(fn)


def test_sources_names_unique():
    names = [name for name, _ in SOURCES]
    assert len(names) == len(set(names))


def test_each_source_has_db_r_http_signature():
    """Every source function takes (db, r, http) — three positional params."""
    for name, fn in SOURCES:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        assert len(params) == 3, f"{name}: expected 3 params, got {len(params)}"
        # Names are stable across the registry
        assert [p.name for p in params] == ["db", "r", "http"], (
            f"{name}: param names should be (db, r, http), got {[p.name for p in params]}"
        )


# ── _industry_match ──────────────────────────────────────────────────────────


def test_industry_match_empty():
    assert _industry_match(None) == (False, None)
    assert _industry_match([]) == (False, None)


def test_industry_match_exact_domain():
    matched, dom = _industry_match(["foo@meta.com"])
    assert matched is True
    assert dom == "meta.com"


def test_industry_match_subdomain():
    matched, dom = _industry_match(["x@research.google.com"])
    assert matched is True
    assert dom == "google.com"


def test_industry_match_non_industry():
    assert _industry_match(["nobody@gmail.com"]) == (False, None)


def test_industry_match_handles_malformed():
    """Strings without '@' shouldn't crash."""
    assert _industry_match(["not-an-email"]) == (False, None)


# ── _position_weight ─────────────────────────────────────────────────────────


def test_position_weight_first_author():
    assert _position_weight(1, 10) == 1.0


def test_position_weight_last_author():
    assert _position_weight(10, 10) == 0.85


def test_position_weight_middle_author():
    assert _position_weight(5, 10) == 0.45


def test_position_weight_solo():
    assert _position_weight(1, 1) == 1.0


def test_position_weight_missing_inputs():
    """Defensive: None / 0 inputs should fall through to 1.0 not crash."""
    assert _position_weight(None, None) == 1.0
    assert _position_weight(0, 0) == 1.0


# ── _junior_boost ────────────────────────────────────────────────────────────


def test_junior_boost_incoming_ap():
    assert _junior_boost("incoming_ap", None) == 1.30


def test_junior_boost_late_phd():
    assert _junior_boost("phd", 4) == 1.25


def test_junior_boost_early_phd():
    """PhD without year-4 marker still gets the generic 1.20 PhD/postdoc boost."""
    assert _junior_boost("phd", 2) == 1.20


def test_junior_boost_postdoc():
    assert _junior_boost("postdoc", None) == 1.20


def test_junior_boost_ap():
    assert _junior_boost("ap", None) == 1.10


def test_junior_boost_full_penalized():
    assert _junior_boost("full", None) == 0.85


def test_junior_boost_unknown_role():
    assert _junior_boost(None, None) == 1.0
    assert _junior_boost("misc-string", None) == 1.0


# ── _recency_multiplier ──────────────────────────────────────────────────────


class _FakePaper:
    """Minimal duck-typed stand-in — _recency_multiplier only reads two attrs."""

    def __init__(self, published_at: date | None, first_seen_at: datetime | None = None) -> None:
        self.published_at = published_at
        self.first_seen_at = first_seen_at


def test_recency_multiplier_today_is_one():
    today = datetime.now(UTC).date()
    mult, reason = _recency_multiplier(_FakePaper(today))
    assert mult == 1.0
    # No reason emitted when the multiplier doesn't visibly cut the score
    assert reason is None


def test_recency_multiplier_six_months_decays():
    """Six-month-old paper: multiplier should fall to roughly exp(-0.5) ≈ 0.61."""
    six_mo = datetime.now(UTC).date() - timedelta(days=int(30.4 * 6))
    mult, reason = _recency_multiplier(_FakePaper(six_mo))
    assert 0.5 < mult < 0.7
    assert reason is not None  # decayed enough to surface a token


def test_recency_multiplier_very_old():
    three_yr = datetime.now(UTC).date() - timedelta(days=int(30.4 * 36))
    mult, _ = _recency_multiplier(_FakePaper(three_yr))
    assert mult < 0.1


def test_recency_multiplier_no_dates_returns_one():
    """When neither date is set, no decay — multiplier stays 1.0."""
    mult, reason = _recency_multiplier(_FakePaper(None, None))
    assert mult == 1.0
    assert reason is None


def test_recency_multiplier_falls_back_to_first_seen_at():
    """When published_at is missing, first_seen_at drives the decay."""
    one_yr = datetime.now(UTC) - timedelta(days=365)
    mult, _ = _recency_multiplier(_FakePaper(None, one_yr))
    # exp(-12/12) ≈ 0.37; loose range to avoid clock-flake
    assert 0.3 < mult < 0.45


# ── _merge_tags (deep_dive) ──────────────────────────────────────────────────


def test_merge_tags_into_empty():
    new = [{"label": "vlm", "score": 0.7, "type": "topic"}]
    merged, added = _merge_tags(None, new)
    assert added == 1
    assert merged == new


def test_merge_tags_keeps_higher_score_on_same_label():
    existing = [{"label": "vlm", "score": 0.4, "type": "topic"}]
    new = [{"label": "vlm", "score": 0.9, "type": "topic"}]
    merged, added = _merge_tags(existing, new)
    assert added == 0  # same key — no addition
    # The higher-scored tag wins
    assert len(merged) == 1
    assert merged[0]["score"] == 0.9


def test_merge_tags_keeps_existing_when_new_is_lower():
    existing = [{"label": "vlm", "score": 0.9, "type": "topic"}]
    new = [{"label": "vlm", "score": 0.2, "type": "topic"}]
    merged, _ = _merge_tags(existing, new)
    assert len(merged) == 1
    assert merged[0]["score"] == 0.9


def test_merge_tags_different_types_coexist():
    """Same label but different type counts as a different key."""
    existing = [{"label": "Tsinghua", "score": 1.0, "type": "topic"}]
    new = [{"label": "Tsinghua", "score": 1.0, "type": "institution"}]
    merged, added = _merge_tags(existing, new)
    assert added == 1
    assert len(merged) == 2


def test_merge_tags_skips_empty_label():
    new = [{"label": "", "score": 0.9, "type": "topic"}]
    merged, added = _merge_tags(None, new)
    assert added == 0
    assert merged == []
