"""Calibration tests for the percentile-based 🔥 high-potential cutoff.

The hardcoded v2 >= 0.5 broke when the pool grew 6k → 12k; the cutoff is
now the 98th percentile of nonzero investability_score_v2, clamped to
[SIGNAL_V2_FLOOR, SIGNAL_V2_CEILING] and cached in-process for 10 minutes.
"""

from openscout.db import session_scope
from openscout.models import Researcher
from openscout.scraper.deep_dive import (
    SIGNAL_V2_CEILING,
    SIGNAL_V2_FLOOR,
    _clamp_signal_cutoff,
    _v2_cutoff_cache,
    _v2_percentile_cutoff,
)
from openscout.scraper.work_scoring import percentile


def test_percentile_sane_on_synthetic_distribution():
    """Nearest-rank percentile on a clean 0.01..1.00 ramp."""
    vals = sorted(i / 100 for i in range(1, 101))
    assert percentile(vals, 0.98) == 0.98
    assert percentile(vals, 0.50) == 0.50
    assert percentile(vals, 1.0) == 1.00
    # Degenerate single-value pool: the only value IS every percentile
    assert percentile([0.42], 0.98) == 0.42


def test_cutoff_floor_and_ceiling_clamps():
    """Weak pools floor at 0.35; hot pools ceiling at 0.6; in-band passes through."""
    assert _clamp_signal_cutoff(0.262) == SIGNAL_V2_FLOOR  # today's real p98 pre-floor
    assert _clamp_signal_cutoff(0.05) == SIGNAL_V2_FLOOR
    assert _clamp_signal_cutoff(0.95) == SIGNAL_V2_CEILING
    assert _clamp_signal_cutoff(0.45) == 0.45


def test_db_cutoff_ceilings_on_hot_pool_and_caches():
    """DB-backed cutoff: a distribution of 0.9s clamps to the ceiling, and the
    10-minute cache returns the same value even after the rows are deleted."""
    _v2_cutoff_cache.clear()
    with session_scope() as db:
        for i in range(200):
            db.add(
                Researcher(
                    slug=f"calib-hot-{i}",
                    name_en=f"Calib Hot {i}",
                    investability_score_v2=0.9,
                )
            )

    with session_scope() as db:
        assert _v2_percentile_cutoff(db) == SIGNAL_V2_CEILING

    # Cache hit: deleting the rows must NOT change the answer within the TTL
    with session_scope() as db:
        for r in db.query(Researcher).filter(Researcher.slug.like("calib-hot-%")).all():
            db.delete(r)
    with session_scope() as db:
        assert _v2_percentile_cutoff(db) == SIGNAL_V2_CEILING

    _v2_cutoff_cache.clear()
