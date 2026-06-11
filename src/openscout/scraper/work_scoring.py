"""Three-pillar work_score for papers — the investment-conversion view.

Per the user (Chinese VC in AI/智能硬件): "我们的核心还是要关注那些具备较大商业化
可能性和高价值量的方向" → not the highest-buzz paper, but the paper that is
breakthrough × commercial × hot all at once.

Three pillars, each in [0, 1]:

  ① breakthrough — academic-impact signal
       influential_citation_count (Semantic Scholar's high-quality cite count;
       paper has been built upon, not just cited)
       + bonus when accepted as oral/spotlight (encoded historically in
       buzz_score ≥ 1.5 by openreview_conf.py)

  ② commercial — adoption + IP signal
       github_stars (log-normalized; 2k stars ≈ 1.0)
       + has-code bonus
       + industry-author bonus (any author_email at a top AI lab)

  ③ buzz — community attention (already exists)
       buzz_score from HF likes + alphaXiv comments + spotlight

Combined: work_score = 0.35 × breakthrough + 0.35 × commercial + 0.30 × buzz

The per-pillar score is persisted (paper.breakthrough_score / .commercial_score)
plus a JSON `work_score_reasons` list of short tokens like
  ["S2 cites: 47", "github ★ 2.1k", "@meta"]
so the UI can render a transparent "why this was picked" badge — same audit
philosophy as the v1.3 country/role provenance badges.

Researcher.investability_score_v2 rolls up the top-3 recent papers' work_scores,
so a researcher whose three most recent papers are all high-investability ranks
higher than one with a single old hit.
"""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher

# Corporate email domains that indicate the author is at a major AI lab — i.e.
# the work has a shorter line to production. Curated; lowercase; matched as
# substring of the email's domain part. Extend as needed.
INDUSTRY_DOMAINS: set[str] = {
    # US frontier labs
    "openai.com",
    "anthropic.com",
    "deepmind.com",
    "google.com",
    "meta.com",
    "fb.com",
    "microsoft.com",
    "nvidia.com",
    "apple.com",
    "amazon.com",
    "amazon.de",
    "amazon.co.jp",
    "intel.com",
    "ibm.com",
    "cohere.com",
    "cohere.ai",
    "ai.cohere.com",
    "huggingface.co",
    "stability.ai",
    "midjourney.com",
    "mistral.ai",
    "x.ai",
    # CN labs / companies
    "bytedance.com",
    "alibaba-inc.com",
    "alibaba.com",
    "tencent.com",
    "baidu.com",
    "huawei.com",
    "deepseek.com",
    "moonshot.cn",
    "zhipuai.cn",
    "01.ai",
    "sensetime.com",
    "megvii.com",
    "kuaishou.com",
    "xiaomi.com",
    "pony.ai",
    "horizon.ai",
    "horizon.cc",
    # Robotics / embodied players
    "tesla.com",
    "1x.tech",
    "figure.ai",
    "agilityrobotics.com",
    "physicalintelligence.company",
    "skild.ai",
}


def _industry_match(emails: list[str] | None) -> tuple[bool, str | None]:
    """Return (matched, first-matching-domain)."""
    if not emails:
        return False, None
    for e in emails:
        if "@" not in e:
            continue
        domain = e.split("@", 1)[1].lower().strip()
        # Match exact OR subdomain (e.g. "research.google.com" should match "google.com")
        for d in INDUSTRY_DOMAINS:
            if domain == d or domain.endswith("." + d):
                return True, d
    return False, None


def _breakthrough(paper: Paper) -> tuple[float, list[str]]:
    """Pillar 1 — academic-impact signal."""
    reasons: list[str] = []
    inf = paper.influential_citation_count or 0
    score = min(1.0, math.log1p(inf) / math.log1p(50))  # 50 influential cites ≈ 1.0
    if inf >= 5:
        reasons.append(f"S2 influential cites: {inf}")

    # Spotlight / oral: openreview_conf.py historically encoded these as
    # buzz_score >= 1.5 with the venue string updated. Treat as a strong
    # breakthrough signal independently.
    if (paper.buzz_score or 0) >= 1.5 and (paper.venue or "").lower() in {
        "neurips",
        "iclr",
        "icml",
        "cvpr",
        "iccv",
        "eccv",
        "acl",
        "emnlp",
        "naacl",
    }:
        score = max(score, 0.75)
        reasons.append(f"{paper.venue} oral/spotlight")

    # Heavy overall citation count (older paper that became a classic)
    cc = paper.citation_count or 0
    if cc >= 200:
        score = max(score, min(1.0, math.log1p(cc) / math.log1p(1000)))
        reasons.append(f"{cc:,} citations")

    return score, reasons


def _commercial(paper: Paper) -> tuple[float, list[str]]:
    """Pillar 2 — adoption / IP signal."""
    reasons: list[str] = []
    score = 0.0

    stars = paper.github_stars or 0
    if stars > 0:
        # 2k stars ≈ 1.0; log-normalized
        score = min(1.0, math.log1p(stars) / math.log1p(2000))
        if stars >= 200:
            reasons.append(
                f"github ★ {stars:,}" if stars < 1000 else f"github ★ {stars / 1000:.1f}k"
            )

    # Bonus: has code at all (lower bar than star count)
    if paper.code_url:
        score = min(1.0, score + 0.15)
        if not stars:
            reasons.append("open-source code")

    # Industry-author bonus
    matched, domain = _industry_match(paper.author_emails)
    if matched:
        score = min(1.0, score + 0.25)
        reasons.append(f"@{domain}")

    return score, reasons


def _buzz(paper: Paper) -> tuple[float, list[str]]:
    """Pillar 3 — community attention (already populated by other scrapers)."""
    reasons: list[str] = []
    raw = paper.buzz_score or 0.0
    # buzz_score is unbounded-ish: HF can push to ~5, oral pushes to 1.5, alphaXiv
    # adds 0.05 per comment. 3.0+ is real buzz.
    score = min(1.0, raw / 3.0)
    if raw >= 1.0:
        reasons.append(f"buzz {raw:.1f}")
    return score, reasons


def _recency_multiplier(paper: Paper) -> tuple[float, str | None]:
    """Time decay for the 'invest now' view.

    An investor doesn't want LeCun's 2021 MDETR ranking above a 2026 PhD
    first-author paper. We multiply the breakthrough + commercial pillars
    by an exponential decay on age — buzz is naturally already-recent so
    we leave it alone.

      months_old   multiplier
       0 (today)   1.00
       6           0.61
       12          0.37
       24          0.14
       36          0.05

    Uses paper.published_at when present (true publication), falls back to
    first_seen_at (when we ingested). Returns the reason token only when
    the multiplier visibly cuts the score (<0.85), to avoid clutter.
    """
    ref_date = paper.published_at
    if ref_date is None and paper.first_seen_at is not None:
        ref_date = paper.first_seen_at.date()
    if ref_date is None:
        return 1.0, None

    today = datetime.now(UTC).date()
    days_old = max(0, (today - ref_date).days)
    months_old = days_old / 30.4
    mult = math.exp(-months_old / 12.0)  # 12-month half-life-ish

    reason = None
    if mult < 0.85:
        reason = f"{int(months_old / 12)}y old" if months_old >= 24 else f"{int(months_old)}mo old"
    return mult, reason


def score_one_paper(paper: Paper) -> dict:
    """Compute and persist all three pillars + the combined work_score.

    Returns the breakdown for logging / debugging.
    """
    b, b_reasons = _breakthrough(paper)
    c, c_reasons = _commercial(paper)
    z, z_reasons = _buzz(paper)
    # Recency cuts breakthrough + commercial (the long-horizon pillars).
    # Buzz is already a now-signal (HF likes spike + decay on their own).
    mult, age_reason = _recency_multiplier(paper)
    b *= mult
    c *= mult
    paper.breakthrough_score = round(b, 3)
    paper.commercial_score = round(c, 3)
    paper.work_score = round(0.35 * b + 0.35 * c + 0.30 * z, 3)
    reasons = b_reasons + c_reasons + z_reasons
    if age_reason:
        reasons.append(age_reason)
    paper.work_score_reasons = reasons
    return {
        "breakthrough": paper.breakthrough_score,
        "commercial": paper.commercial_score,
        "buzz": round(z, 3),
        "work_score": paper.work_score,
        "reasons": paper.work_score_reasons,
    }


def score_all_papers(limit: int | None = None) -> dict[str, int]:
    """Compute work_score for every paper that has any signal at all."""
    counts = {"scored": 0, "skipped_nosignal": 0}
    with session_scope() as db:
        stmt = select(Paper)
        if limit:
            stmt = stmt.limit(limit)
        for p in db.execute(stmt).scalars().all():
            # Skip pure-empty papers (no citations, no code, no buzz) — work_score=0
            # would just clutter rankings.
            if not (
                (p.influential_citation_count or 0)
                or (p.citation_count or 0)
                or (p.github_stars or 0)
                or (p.code_url)
                or (p.buzz_score or 0)
                or (p.author_emails)
            ):
                counts["skipped_nosignal"] += 1
                continue
            score_one_paper(p)
            counts["scored"] += 1
    return counts


def _position_weight(position: int | None, n_authors: int | None) -> float:
    """Credit allocation by author position.

    A 12-author paper assigns FULL credit to the first and last author (the
    student who drove it + the PI who shaped it) and discounted credit to the
    middle. Without this, a single hot paper would stack all 12 of its authors
    at identical scores in the picks list — useless for the investor.

    First author       → 1.00
    Last  author       → 0.85   (senior PI; valuable but usually already placed)
    Middle (2nd, etc.) → 0.45
    Solo               → 1.00
    """
    if not position or not n_authors or n_authors <= 1:
        return 1.0
    if position == 1:
        return 1.0
    if position == n_authors:
        return 0.85
    return 0.45


def _junior_boost(role: str | None, career_year: int | None) -> float:
    """Multiply for early-career researchers — the user's investment thesis.

    Note on role=None (deliberate): medium-confidence auto-anchors from
    anchor_expansion land without a role, so they fall through to the
    neutral 1.0 — neither boosted as juniors nor discounted as seniors.
    That's the right default: we don't know their stage yet, and a deep
    dive / classify pass will assign current_role later, at which point
    the next compute_investability_v2 run re-applies the proper boost.
    """
    if role == "incoming_ap":
        return 1.30
    if role == "phd" and (career_year or 0) >= 4:
        return 1.25  # graduating PhDs
    if role in ("phd", "postdoc"):
        return 1.20
    if role == "ap":
        return 1.10
    if role in ("full", "senior", "associate"):
        return 0.85  # established; less investable for this user's thesis
    return 1.0


def _effective_date_expr():
    """SQL: COALESCE(published_at, DATE(first_seen_at)) — the paper's
    true age for ranking, falling back to ingestion time if we never got
    a publication date. Important for v2: we want a 2026 paper we ingested
    a week ago to rank as "fresh," not because of when we crawled it.
    """
    return func.coalesce(Paper.published_at, func.date(Paper.first_seen_at))


def compute_investability_v2(window_days: int = 365) -> dict[str, int]:
    """Roll up Researcher.investability_score_v2 from their recent papers.

    Per-paper credit = paper.work_score × position_weight × junior_boost.
    Then aggregate the top-3 weighted scores as 0.7 × max + 0.3 × mean, so a
    single breakthrough paper dominates the ranking but consistent recent
    quality still helps tie-breaking.
    """
    counts = {"updated": 0, "no_recent_papers": 0}
    cutoff_date = (datetime.now(UTC) - timedelta(days=window_days)).date()
    effective_date = _effective_date_expr()
    with session_scope() as db:
        # Map paper_id → n_authors (one query, cached in memory — cheap)
        n_authors_by_paper: dict[int, int] = {
            int(pid): int(n)
            for pid, n in db.execute(
                select(PaperAuthor.paper_id, func.count(PaperAuthor.researcher_id)).group_by(
                    PaperAuthor.paper_id
                )
            ).all()
        }

        for r in db.execute(select(Researcher)).scalars().all():
            rows = db.execute(
                select(Paper.id, Paper.work_score, PaperAuthor.position)
                .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
                .where(
                    PaperAuthor.researcher_id == r.id,
                    Paper.work_score.is_not(None),
                    effective_date >= cutoff_date,
                )
                .order_by(desc(Paper.work_score))
                .limit(15)
            ).all()
            if not rows:
                r.investability_score_v2 = 0.0
                counts["no_recent_papers"] += 1
                continue

            boost = _junior_boost(r.current_role, r.career_stage_year)
            weighted = [
                float(score) * _position_weight(pos, n_authors_by_paper.get(int(pid))) * boost
                for pid, score, pos in rows
            ]
            weighted.sort(reverse=True)
            top3 = weighted[:3]
            top = top3[0]
            mean = sum(top3) / len(top3)
            r.investability_score_v2 = round(min(1.0, 0.7 * top + 0.3 * mean), 3)
            counts["updated"] += 1
    return counts


def percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile of an ASCENDING-sorted list.

    pct in (0, 1]; e.g. pct=0.98 on 100 values returns the 98th value.
    Deterministic and dependency-free (no numpy) — used both for the
    🔥 signal-tag cutoff (deep_dive) and score_distribution() below.
    Raises ValueError on an empty list: callers decide their own fallback.
    """
    if not sorted_vals:
        raise ValueError("percentile() of empty list")
    n = len(sorted_vals)
    idx = min(n - 1, max(0, math.ceil(pct * n) - 1))
    return sorted_vals[idx]


def score_distribution() -> dict[str, float | int]:
    """Snapshot of the nonzero investability_score_v2 distribution.

    For `doctor` / debugging — answers "is the score calibration sane after
    the pool grew?" without ad-hoc SQL. Returns zeros when nothing is scored.
    """
    with session_scope() as db:
        vals = sorted(
            float(v)
            for (v,) in db.execute(
                select(Researcher.investability_score_v2).where(
                    Researcher.investability_score_v2 > 0
                )
            ).all()
        )
    if not vals:
        return {
            "count_scored": 0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p98": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    return {
        "count_scored": len(vals),
        "p50": percentile(vals, 0.50),
        "p90": percentile(vals, 0.90),
        "p95": percentile(vals, 0.95),
        "p98": percentile(vals, 0.98),
        "p99": percentile(vals, 0.99),
        "max": vals[-1],
    }


def top_investment_picks(
    limit: int = 10,
    window_days: int = 30,
    max_per_paper: int = 2,
) -> list[dict]:
    """Return the top-N researchers by investability_score_v2, filtered to
    those with at least one paper in the last `window_days`.

    Diversity guard: at most `max_per_paper` picks share the same top paper
    (otherwise a single hot paper with 12 authors fills the entire board).
    We over-fetch and then sieve.

    ── Perf notes ─────────────────────────────────────────────────────────
    BEFORE (per-researcher subquery, classic N+1):
      limit=10 → 1 + up to 60 queries; ~16ms on the dev DB
        (1668 papers × 7311 researchers, ~84 with v2-scored)
    AFTER (single window-function query: row_number per researcher):
      limit=10 → 1 query → ~8-9ms (~2× speedup at current data size).
      The win scales with `limit`: each unit of `limit` previously cost up
      to 6 extra round-trips; they all collapse into the single CTE here.
    Window functions need SQLite ≥ 3.25 (we run 3.47) and are native on
    Postgres — same SQL works on both dialects via SQLAlchemy.
    ──────────────────────────────────────────────────────────────────────
    """
    cutoff_date = (datetime.now(UTC) - timedelta(days=window_days)).date()
    effective_date = _effective_date_expr()
    picks: list[dict] = []
    seen_paper_count: dict[int, int] = {}
    over_fetch = limit * 6  # sieve below

    with session_scope() as db:
        # Window function: rank each researcher's recent papers by work_score
        # so row_num=1 is "the paper that drove their score." One row per
        # researcher × paper; we'll filter to row_num=1 outside. This replaces
        # the previous per-researcher subquery — the classic N+1 — with one
        # plan the DB can execute in a single pass.
        rn = (
            func.row_number()
            .over(
                partition_by=PaperAuthor.researcher_id,
                order_by=desc(Paper.work_score),
            )
            .label("rn")
        )
        ranked = (
            select(
                PaperAuthor.researcher_id.label("rid"),
                Paper.id.label("paper_id"),
                Paper.arxiv_id,
                Paper.title,
                Paper.work_score,
                Paper.breakthrough_score,
                Paper.commercial_score,
                Paper.buzz_score,
                Paper.work_score_reasons,
                PaperAuthor.position,
                rn,
            )
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(
                effective_date >= cutoff_date,
                Paper.work_score.is_not(None),
            )
        ).subquery("ranked")

        # Join top-paper-per-researcher onto the ranked researchers. The DB
        # gives back researcher rows already sorted by score, each paired with
        # its single top paper — exactly what we used to assemble in Python.
        stmt = (
            select(
                Researcher.slug,
                Researcher.name_en,
                Researcher.name_zh,
                Researcher.country,
                Researcher.current_role,
                Researcher.investability_score_v2,
                ranked.c.paper_id,
                ranked.c.arxiv_id,
                ranked.c.title,
                ranked.c.work_score,
                ranked.c.breakthrough_score,
                ranked.c.commercial_score,
                ranked.c.buzz_score,
                ranked.c.work_score_reasons,
                ranked.c.position,
            )
            .join(ranked, ranked.c.rid == Researcher.id)
            .where(
                ranked.c.rn == 1,
                Researcher.investability_score_v2.is_not(None),
                Researcher.investability_score_v2 > 0,
            )
            .order_by(desc(Researcher.investability_score_v2))
            .limit(over_fetch)
        )

        for row in db.execute(stmt).all():
            paper_id = int(row.paper_id)
            if seen_paper_count.get(paper_id, 0) >= max_per_paper:
                continue
            seen_paper_count[paper_id] = seen_paper_count.get(paper_id, 0) + 1

            picks.append(
                {
                    "slug": row.slug,
                    "name_en": row.name_en,
                    "name_zh": row.name_zh,
                    "country": row.country,
                    "current_role": row.current_role,
                    "score": row.investability_score_v2,
                    "top_paper": {
                        "arxiv_id": row.arxiv_id,
                        "title": row.title,
                        "work_score": row.work_score,
                        "breakthrough": row.breakthrough_score,
                        "commercial": row.commercial_score,
                        "buzz": round(min(1.0, (row.buzz_score or 0) / 3.0), 3),
                        "reasons": row.work_score_reasons or [],
                        "position": int(row.position) if row.position is not None else None,
                    },
                }
            )
            if len(picks) >= limit:
                break
    return picks
