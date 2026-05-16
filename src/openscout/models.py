"""SQLAlchemy 2.x models for OpenScout.

Core entities:
- Researcher / Institution / Topic / Paper
- PaperAuthor, PaperTopic, ResearcherTopic — many-to-many
- Relationship — advisor/student/coauthor graph
- Affiliation — researcher × institution over time
- Signal — recent activity events (paper/tweet/talk/repo/AP-announcement)
- DailyBrief — the rendered daily report
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name_zh: Mapped[str | None] = mapped_column(String(255))
    type: Mapped[str | None] = mapped_column(String(32))  # university / lab / company
    country: Mapped[str | None] = mapped_column(String(8))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    homepage_url: Mapped[str | None] = mapped_column(Text)
    prestige_score: Mapped[float | None] = mapped_column(Float)
    # OpenAlex Institution ID. Used to disambiguate same-name authors during enrichment.
    openalex_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    name_zh: Mapped[str | None] = mapped_column(String(128))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    description: Mapped[str | None] = mapped_column(Text)


class Researcher(Base):
    __tablename__ = "researchers"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    semantic_scholar_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    openalex_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    orcid: Mapped[str | None] = mapped_column(String(32), unique=True)
    arxiv_author_id: Mapped[str | None] = mapped_column(String(64))

    name_en: Mapped[str] = mapped_column(String(255), index=True)
    name_zh: Mapped[str | None] = mapped_column(String(255))
    # Provenance for the Chinese name — "manual" / "openalex_alt" / "openalex_chinese_alt" /
    # "arxiv_byline" / "homepage". Never auto-fill with a guess; leave null instead.
    name_zh_source: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    homepage_url: Mapped[str | None] = mapped_column(Text)
    twitter_handle: Mapped[str | None] = mapped_column(String(64))
    github_handle: Mapped[str | None] = mapped_column(String(64))
    zhihu_url: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)

    current_affiliation_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    current_role: Mapped[str | None] = mapped_column(String(32))
    # phd / postdoc / incoming_ap / ap / associate / full / industry_researcher / senior
    career_stage_year: Mapped[int | None] = mapped_column(Integer)
    graduation_year_estimate: Mapped[int | None] = mapped_column(Integer)
    advisor_id: Mapped[int | None] = mapped_column(ForeignKey("researchers.id"))

    bio: Mapped[str | None] = mapped_column(Text)
    bio_zh: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(8))
    # Provenance for country / current_role / current_affiliation_id. Values:
    #   "manual"           — seeds/researchers.yaml
    #   "openalex"         — from OpenAlex last_known_institution
    #   "surname_pinyin"   — Pinyin family-name heuristic (country=CN only)
    #   "peer_inheritance" — inherited from co-author anchor
    #   "arxiv_html"       — extracted from arXiv HTML author footnote
    country_source: Mapped[str | None] = mapped_column(String(32))
    role_source: Mapped[str | None] = mapped_column(String(32))
    affiliation_source: Mapped[str | None] = mapped_column(String(32))
    confidence_level: Mapped[str] = mapped_column(String(16), default="medium")
    # low / medium / high — applied to identity disambiguation + advisor inference

    # OpenAlex-derived metrics (refreshed by `openscout enrich`)
    h_index: Mapped[int | None] = mapped_column(Integer)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    works_count: Mapped[int | None] = mapped_column(Integer)
    # Research-direction tags — array of {slug, label_en, label_zh?, score}
    tags: Mapped[list | None] = mapped_column(JSON)
    # Flagship projects this researcher is publicly associated with (hand-curated).
    # Each: {name, role?, url?}. E.g. {"name":"AlphaFold","role":"lead"} for John Jumper.
    projects: Mapped[list | None] = mapped_column(JSON)
    # Signature paper — the most cited / most-collaborative paper for this researcher
    signature_paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id"))

    person_score: Mapped[float | None] = mapped_column(Float)
    trajectory_score: Mapped[float | None] = mapped_column(Float)
    # v1 (legacy): stage + tag_count + projects — kept for A/B comparison.
    investability_score: Mapped[float | None] = mapped_column(Float)
    # v2: rolls up paper.work_score from the researcher's top-3 recent papers.
    # See scraper/work_scoring.py compute_investability_v2().
    investability_score_v2: Mapped[float | None] = mapped_column(Float)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    semantic_scholar_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    openalex_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    doi: Mapped[str | None] = mapped_column(String(128))

    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    abstract_zh: Mapped[str | None] = mapped_column(Text)
    one_liner_zh: Mapped[str | None] = mapped_column(Text)  # like KS blurbs_zh

    published_at: Mapped[date | None] = mapped_column(Date, index=True)
    venue: Mapped[str | None] = mapped_column(String(128))
    pdf_url: Mapped[str | None] = mapped_column(Text)
    code_url: Mapped[str | None] = mapped_column(Text)

    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    influential_citation_count: Mapped[int | None] = mapped_column(Integer)
    github_stars: Mapped[int | None] = mapped_column(Integer)
    # Three-pillar investability score (see scraper/work_scoring.py):
    #   breakthrough_score — academic-impact signal (S2 influential cites + oral/spotlight)
    #   commercial_score   — adoption signal (github stars + code_url + industry email)
    #   buzz_score         — community attention (HF likes + alphaXiv comments)
    #   work_score         — weighted combination, used for "Investment Lens" ranking
    # work_score_reasons stores per-paper "why this scored high" tokens for the UI.
    buzz_score: Mapped[float | None] = mapped_column(Float)
    breakthrough_score: Mapped[float | None] = mapped_column(Float)
    commercial_score: Mapped[float | None] = mapped_column(Float)
    work_score: Mapped[float | None] = mapped_column(Float)
    work_score_reasons: Mapped[list | None] = mapped_column(JSON)
    # OpenAlex concept tags — array of {label, score}
    concepts: Mapped[list | None] = mapped_column(JSON)
    # Emails extracted from PDF first page — array of strings. Loose matching
    # to authors not attempted; the UI surfaces them as "possible contacts."
    author_emails: Mapped[list | None] = mapped_column(JSON)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class PaperAuthor(Base):
    __tablename__ = "paper_authors"

    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    researcher_id: Mapped[int] = mapped_column(
        ForeignKey("researchers.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer)  # 1-indexed
    is_corresponding: Mapped[bool] = mapped_column(Boolean, default=False)


class PaperTopic(Base):
    __tablename__ = "paper_topics"

    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )


class ResearcherTopic(Base):
    __tablename__ = "researcher_topics"

    researcher_id: Mapped[int] = mapped_column(
        ForeignKey("researchers.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    weight: Mapped[float | None] = mapped_column(Float)


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_researcher_id: Mapped[int] = mapped_column(ForeignKey("researchers.id"), index=True)
    to_researcher_id: Mapped[int] = mapped_column(ForeignKey("researchers.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # advisor / student / coauthor / sibling
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    evidence: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[date | None] = mapped_column(Date)
    ended_at: Mapped[date | None] = mapped_column(Date)


class Affiliation(Base):
    __tablename__ = "affiliations"

    id: Mapped[int] = mapped_column(primary_key=True)
    researcher_id: Mapped[int] = mapped_column(ForeignKey("researchers.id"), index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    role: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[date | None] = mapped_column(Date)
    ended_at: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    researcher_id: Mapped[int] = mapped_column(ForeignKey("researchers.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    # paper / tweet / talk / repo / affiliation_change / ap_announcement / preprint
    payload: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source: Mapped[str | None] = mapped_column(String(64))


class DailyBrief(Base):
    __tablename__ = "daily_briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    brief_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    volume: Mapped[int] = mapped_column(Integer, default=1)
    issue: Mapped[int] = mapped_column(Integer)
    rendered_md: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
