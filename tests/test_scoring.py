"""Tests for src/openscout/scraper/scoring.py."""

from openscout.scraper.scoring import _clamp01, _project_bonus, _stage_fit


def test_stage_fit_no_role():
    assert _stage_fit(None, None) == 0.4


def test_stage_fit_phd_year_bump():
    """Late-stage PhDs get a +0.15 bump."""
    base = _stage_fit("phd", 2)
    late = _stage_fit("phd", 5)
    assert late > base


def test_stage_fit_incoming_ap_peak():
    """Incoming AP should be the highest of all stages."""
    incoming = _stage_fit("incoming_ap", None)
    senior = _stage_fit("senior", None)
    full = _stage_fit("full", None)
    assert incoming >= full
    assert incoming >= senior


def test_clamp01_above():
    assert _clamp01(1.5) == 1.0


def test_clamp01_below():
    assert _clamp01(-0.2) == 0.0


def test_clamp01_in_range():
    assert _clamp01(0.7) == 0.7


def test_project_bonus_empty():
    assert _project_bonus([]) == 0.0
    assert _project_bonus(None) == 0.0


def test_project_bonus_company_weighted_higher():
    company = _project_bonus([{"name": "Foo", "category": "company"}])
    open_src = _project_bonus([{"name": "Bar", "category": "open_source"}])
    assert company > open_src


def test_project_bonus_capped():
    """Should not exceed 0.30 no matter how many projects."""
    many = _project_bonus([{"name": f"P{i}", "category": "company"} for i in range(20)])
    assert many <= 0.30
