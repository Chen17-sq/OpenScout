"""Pure data layer for the daily brief.

Both the markdown renderer (`brief/generate.py`) and the structured API
endpoint (`/briefs/today`) read from these functions. Keeping queries in one
place lets us iterate on ranking/section logic without forking two callers.
"""

from dataclasses import dataclass, field
from datetime import date as Date

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from ..models import Paper, PaperAuthor, PaperTopic, Researcher, Topic

# ─── Output schemas ─────────────────────────────────────────────────────────


@dataclass
class ResearcherSummary:
    slug: str
    name_en: str
    name_zh: str | None
    current_role: str | None
    homepage_url: str | None
    confidence_level: str


@dataclass
class PaperSummary:
    arxiv_id: str | None
    title: str
    abstract: str | None
    one_liner_zh: str | None
    venue: str | None
    pdf_url: str | None
    published_at: str | None
    n_authors: int
    topics: list[str] = field(default_factory=list)


@dataclass
class StoryItem:
    """One row in any of Sections B/C/E/F — a researcher + the paper they shipped."""

    researcher: ResearcherSummary
    paper: PaperSummary
    reasoning: str | None = None  # for Sleeper Picks: why was it selected


@dataclass
class BriefData:
    brief_date: Date
    issue: int

    tracked: int
    today_papers: int
    today_emergences: int
    soon_graduating: int
    incoming_ap: int

    new_first_authors: list[StoryItem]
    anchor_activity: list[StoryItem]
    soon_graduating_picks: list[StoryItem]
    hot_papers: list[StoryItem]
    sleeper_picks: list[StoryItem]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _researcher_summary(r: Researcher) -> ResearcherSummary:
    return ResearcherSummary(
        slug=r.slug,
        name_en=r.name_en,
        name_zh=r.name_zh,
        current_role=r.current_role,
        homepage_url=r.homepage_url,
        confidence_level=r.confidence_level,
    )


def _paper_summary(p: Paper, n_authors: int = 0, topics: list[str] | None = None) -> PaperSummary:
    return PaperSummary(
        arxiv_id=p.arxiv_id,
        title=p.title,
        abstract=p.abstract,
        one_liner_zh=p.one_liner_zh,
        venue=p.venue,
        pdf_url=p.pdf_url,
        published_at=p.published_at.isoformat() if p.published_at else None,
        n_authors=n_authors,
        topics=topics or [],
    )


def _topics_for_paper(db: Session, paper_id: int) -> list[str]:
    rows = db.execute(
        select(Topic.slug)
        .join(PaperTopic, PaperTopic.topic_id == Topic.id)
        .where(PaperTopic.paper_id == paper_id)
    ).all()
    return [r[0] for r in rows]


def _author_count(db: Session, paper_id: int) -> int:
    n = db.execute(
        select(func.count(PaperAuthor.researcher_id)).where(PaperAuthor.paper_id == paper_id)
    ).scalar()
    return int(n or 0)


def _first_author(db: Session, paper_id: int) -> Researcher | None:
    return db.execute(
        select(Researcher)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .where(PaperAuthor.paper_id == paper_id, PaperAuthor.position == 1)
        .limit(1)
    ).scalar_one_or_none()


# ─── Section queries ────────────────────────────────────────────────────────


def kpi_counts(db: Session, brief_date: Date) -> dict[str, int]:
    tracked = int(db.execute(select(func.count(Researcher.id))).scalar() or 0)
    today_papers = int(
        db.execute(
            select(func.count(Paper.id)).where(func.date(Paper.first_seen_at) == brief_date)
        ).scalar()
        or 0
    )
    today_emergences = int(
        db.execute(
            select(func.count(Researcher.id)).where(
                func.date(Researcher.first_seen_at) == brief_date,
                Researcher.confidence_level == "low",
            )
        ).scalar()
        or 0
    )
    soon_graduating = int(
        db.execute(
            select(func.count(Researcher.id)).where(
                Researcher.current_role == "phd",
                Researcher.career_stage_year.is_not(None),
                Researcher.career_stage_year >= 4,
            )
        ).scalar()
        or 0
    )
    incoming_ap = int(
        db.execute(
            select(func.count(Researcher.id)).where(Researcher.current_role == "incoming_ap")
        ).scalar()
        or 0
    )
    return {
        "tracked": tracked,
        "today_papers": today_papers,
        "today_emergences": today_emergences,
        "soon_graduating": soon_graduating,
        "incoming_ap": incoming_ap,
    }


def new_first_authors(db: Session, brief_date: Date, limit: int = 10) -> list[StoryItem]:
    """Section B 今日新冒头 — researchers first seen today, first-author on a paper today."""
    stmt = (
        select(Researcher, Paper)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .join(Paper, Paper.id == PaperAuthor.paper_id)
        .where(
            PaperAuthor.position == 1,
            func.date(Researcher.first_seen_at) == brief_date,
            Researcher.confidence_level == "low",
            func.date(Paper.first_seen_at) == brief_date,
        )
        .order_by(desc(Paper.first_seen_at))
        .limit(limit)
    )
    out: list[StoryItem] = []
    for r, p in db.execute(stmt).all():
        out.append(
            StoryItem(
                researcher=_researcher_summary(r),
                paper=_paper_summary(p, _author_count(db, p.id), _topics_for_paper(db, p.id)),
            )
        )
    return out


def anchor_activity(db: Session, brief_date: Date, limit: int = 10) -> list[StoryItem]:
    """Section B 动态更新 — known anchors (medium/high confidence) who shipped today."""
    stmt = (
        select(Researcher, Paper)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .join(Paper, Paper.id == PaperAuthor.paper_id)
        .where(
            Researcher.confidence_level != "low",
            func.date(Paper.first_seen_at) == brief_date,
        )
        .order_by(desc(Paper.first_seen_at))
        .limit(limit)
    )
    out: list[StoryItem] = []
    for r, p in db.execute(stmt).all():
        out.append(
            StoryItem(
                researcher=_researcher_summary(r),
                paper=_paper_summary(p, _author_count(db, p.id), _topics_for_paper(db, p.id)),
            )
        )
    return out


def soon_graduating_picks(db: Session, limit: int = 10) -> list[StoryItem]:
    """Section C 即将毕业 — explicit phd-Y4/Y5 anchors; falls back to most-productive
    low-confidence researchers if our anchor pool doesn't have stage data yet.
    """
    stmt = (
        select(Researcher)
        .where(
            Researcher.current_role == "phd",
            Researcher.career_stage_year.is_not(None),
            Researcher.career_stage_year >= 4,
        )
        .order_by(desc(Researcher.career_stage_year))
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars().all())

    if not rows:
        # Fallback: most-productive auto-discovered first-authors of the last 7 days.
        # Proxy for "active in late-stage / early-career."
        author_paper_count_sq = (
            select(
                PaperAuthor.researcher_id,
                func.count(PaperAuthor.paper_id).label("n"),
            )
            .where(PaperAuthor.position == 1)
            .group_by(PaperAuthor.researcher_id)
            .subquery()
        )
        stmt2 = (
            select(Researcher, author_paper_count_sq.c.n)
            .join(author_paper_count_sq, author_paper_count_sq.c.researcher_id == Researcher.id)
            .where(Researcher.confidence_level == "low")
            .order_by(desc(author_paper_count_sq.c.n))
            .limit(limit)
        )
        rows = [r for r, _ in db.execute(stmt2).all()]

    out: list[StoryItem] = []
    for r in rows:
        # attach their most recent first-author paper for context
        latest = db.execute(
            select(Paper)
            .join(PaperAuthor, and_(PaperAuthor.paper_id == Paper.id, PaperAuthor.position == 1))
            .where(PaperAuthor.researcher_id == r.id)
            .order_by(desc(Paper.first_seen_at))
            .limit(1)
        ).scalar_one_or_none()
        if not latest:
            continue
        out.append(
            StoryItem(
                researcher=_researcher_summary(r),
                paper=_paper_summary(latest, _author_count(db, latest.id), _topics_for_paper(db, latest.id)),
            )
        )
    return out


def hot_papers(db: Session, brief_date: Date, limit: int = 10) -> list[StoryItem]:
    """Section E 热门工作 — today's papers ranked by author-count (proxy for collaboration weight)."""
    author_count_sq = (
        select(PaperAuthor.paper_id, func.count(PaperAuthor.researcher_id).label("n"))
        .group_by(PaperAuthor.paper_id)
        .subquery()
    )
    stmt = (
        select(Paper, func.coalesce(author_count_sq.c.n, 0).label("n"))
        .outerjoin(author_count_sq, author_count_sq.c.paper_id == Paper.id)
        .where(func.date(Paper.first_seen_at) == brief_date)
        .order_by(desc("n"), desc(Paper.first_seen_at))
        .limit(limit)
    )
    out: list[StoryItem] = []
    for p, n in db.execute(stmt).all():
        fa = _first_author(db, p.id)
        if not fa:
            continue
        out.append(
            StoryItem(
                researcher=_researcher_summary(fa),
                paper=_paper_summary(p, int(n), _topics_for_paper(db, p.id)),
            )
        )
    return out


def sleeper_picks(db: Session, brief_date: Date, limit: int = 3, skip_top: int = 10) -> list[StoryItem]:
    """Section F 🌙 Sleeper Picks — algorithmic surprises.

    v0 algorithm: papers ranked 11+ in collaboration weight, whose first author is a
    fresh discovery (low confidence + first seen today). Reasoning: "first paper here,
    large collaboration" — a high-signal proxy for "junior in a big lab."
    """
    author_count_sq = (
        select(PaperAuthor.paper_id, func.count(PaperAuthor.researcher_id).label("n"))
        .group_by(PaperAuthor.paper_id)
        .subquery()
    )
    candidates_sq = (
        select(Paper.id.label("pid"), func.coalesce(author_count_sq.c.n, 0).label("n"))
        .outerjoin(author_count_sq, author_count_sq.c.paper_id == Paper.id)
        .where(func.date(Paper.first_seen_at) == brief_date)
        .order_by(desc("n"))
        .offset(skip_top)
        .limit(50)
        .subquery()
    )
    stmt = (
        select(Paper, Researcher, candidates_sq.c.n)
        .join(candidates_sq, candidates_sq.c.pid == Paper.id)
        .join(PaperAuthor, and_(PaperAuthor.paper_id == Paper.id, PaperAuthor.position == 1))
        .join(Researcher, Researcher.id == PaperAuthor.researcher_id)
        .where(
            Researcher.confidence_level == "low",
            func.date(Researcher.first_seen_at) == brief_date,
            candidates_sq.c.n >= 6,
        )
        .order_by(desc(candidates_sq.c.n))
        .limit(limit)
    )
    out: list[StoryItem] = []
    for p, r, n in db.execute(stmt).all():
        out.append(
            StoryItem(
                researcher=_researcher_summary(r),
                paper=_paper_summary(p, int(n), _topics_for_paper(db, p.id)),
                reasoning=f"首次出现，{int(n)} 作者合作（大组潜在新人）",
            )
        )
    return out


# ─── Orchestrator ───────────────────────────────────────────────────────────


VOLUME_1_START = Date(2026, 5, 15)


def _issue_number(brief_date: Date) -> int:
    return (brief_date - VOLUME_1_START).days + 1


def collect(db: Session, brief_date: Date) -> BriefData:
    """Pull everything needed for one day's brief in a single coordinated pass."""
    kpi = kpi_counts(db, brief_date)
    return BriefData(
        brief_date=brief_date,
        issue=_issue_number(brief_date),
        tracked=kpi["tracked"],
        today_papers=kpi["today_papers"],
        today_emergences=kpi["today_emergences"],
        soon_graduating=kpi["soon_graduating"],
        incoming_ap=kpi["incoming_ap"],
        new_first_authors=new_first_authors(db, brief_date),
        anchor_activity=anchor_activity(db, brief_date),
        soon_graduating_picks=soon_graduating_picks(db),
        hot_papers=hot_papers(db, brief_date),
        sleeper_picks=sleeper_picks(db, brief_date),
    )
