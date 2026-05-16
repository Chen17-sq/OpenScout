"""Compute person_score / trajectory_score / investability_score from real signals.

These were null in v0. v1 formulas (deliberately simple — refine later from
real outcomes):

person_score ∈ [0, 1]
  Aggregate "is this person worth tracking" — used for default ranking.
  Inputs: h-index, citation count, recent activity, role/stage.

trajectory_score ∈ [-1, 1]
  Are they on the way up or down?
  Inputs: ratio of recent (last-year) to all-time citations, papers/year delta.

investability_score ∈ [0, 1]
  How matched to the investor's "young + high-potential" thesis?
  Inputs: stage_fit (PhD-Y4/Y5 or incoming AP boost), tag overlap with
  target topics, presence of flagship project entries.
"""

import math

from sqlalchemy import func, select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _stage_fit(role: str | None, year: int | None) -> float:
    """0..1. Peaks at "soon-to-be-AP" / "graduating PhD" — the user's sweet spot."""
    if not role:
        return 0.4
    base = {
        "phd": 0.7,
        "postdoc": 0.85,
        "incoming_ap": 1.0,
        "ap": 0.9,
        "associate": 0.6,
        "full": 0.4,
        "senior": 0.3,
        "industry": 0.55,
    }.get(role, 0.4)
    # Late-stage PhDs / first-year APs get an extra bump
    if role == "phd" and year and year >= 4:
        base = min(1.0, base + 0.15)
    return base


def _project_bonus(projects: list | None) -> float:
    """Each flagship project add a small bump (capped). Companies / open_source weigh more."""
    if not projects:
        return 0.0
    weight = 0.0
    for p in projects:
        cat = (p.get("category") or "").lower()
        weight += {"company": 0.10, "lab": 0.06, "open_source": 0.08, "research_line": 0.05}.get(
            cat, 0.04
        )
    return min(0.30, weight)


def compute_scores() -> dict[str, int]:
    """Compute and persist all three scores for every researcher with enough data."""
    counts = {"updated": 0, "skipped_no_data": 0}

    with session_scope() as db:
        rs = list(db.execute(select(Researcher)).scalars().all())

        # Max citation in the corpus, for normalization
        max_cite = db.execute(select(func.max(Researcher.citation_count))).scalar() or 1
        max_cite = max(1, max_cite)

        for r in rs:
            # Person score: log-normalized citations + h-index + stage
            cite_factor = math.log1p(r.citation_count or 0) / math.log1p(max_cite)
            h_factor = min(1.0, (r.h_index or 0) / 50.0)
            stage = _stage_fit(r.current_role, r.career_stage_year)

            person = 0.45 * cite_factor + 0.35 * h_factor + 0.20 * stage
            r.person_score = round(_clamp01(person), 3)

            # Trajectory: ratio of last-year-ish papers to all-time
            n_recent = (
                db.execute(
                    select(func.count(PaperAuthor.paper_id))
                    .join(Paper, Paper.id == PaperAuthor.paper_id)
                    .where(
                        PaperAuthor.researcher_id == r.id,
                        func.date(Paper.first_seen_at)
                        >= func.date(func.datetime("now", "-365 days")),
                    )
                ).scalar()
                or 0
            )
            n_all = r.works_count or 1
            recency = min(1.0, n_recent / max(1, n_all * 0.3))  # 30%+ of works recent → 1.0
            # Map [0, 1] → [-1, 1] for "rising" / "settled" axis
            r.trajectory_score = round((recency - 0.4) * 2, 3)

            # Investability: stage + project bonus + tag-presence bonus
            tag_factor = min(1.0, len(r.tags or []) / 5.0)
            invest = 0.55 * stage + 0.30 * tag_factor + _project_bonus(r.projects)
            r.investability_score = round(_clamp01(invest), 3)

            counts["updated"] += 1

    return counts
