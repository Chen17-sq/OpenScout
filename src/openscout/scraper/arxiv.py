"""arXiv ingest — pull recent papers, create Paper + Researcher + PaperAuthor rows."""

import re

import arxiv
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Paper, PaperAuthor, PaperTopic, Researcher, Topic

# Topic-specific arXiv query strings. Tune as you find false positives / negatives.
TOPIC_QUERIES: dict[str, str] = {
    "embodied": (
        "cat:cs.RO OR "
        "(cat:cs.AI AND (abs:robot OR abs:manipulation OR abs:locomotion OR abs:dexterous OR abs:embodied))"
    ),
    "world_models": (
        '(abs:"world model" OR abs:"video prediction" OR abs:"dynamics model" OR abs:"latent dynamics") '
        "AND (cat:cs.LG OR cat:cs.AI OR cat:cs.CV)"
    ),
    "ai4sci": (
        "cat:q-bio.BM OR cat:physics.chem-ph OR cat:cond-mat.mtrl-sci OR "
        '(cat:cs.LG AND (abs:protein OR abs:molecule OR abs:"material discovery" OR abs:crystallography))'
    ),
}

# Safety gate — fewer results suggests a scraper failure.
MIN_RESULTS_THRESHOLD = 3


def ingest_topic(topic_slug: str, limit: int = 50) -> int:
    """Pull recent arXiv papers for `topic_slug`. Returns count of newly added papers.

    Side effects (per new paper):
      - Insert into `papers`
      - Insert one `paper_topics` row tying it to the topic
      - For each author (in original byline order), upsert a `researchers` row
        and insert a `paper_authors` row with the author's `position` (1-indexed)
    """
    query = TOPIC_QUERIES.get(topic_slug)
    if not query:
        raise ValueError(f"Unknown topic: {topic_slug!r}. Known: {list(TOPIC_QUERIES)}")

    search = arxiv.Search(
        query=query,
        max_results=limit,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    client = arxiv.Client(page_size=min(limit, 100), delay_seconds=3.0, num_retries=3)

    results = list(client.results(search))
    if len(results) < MIN_RESULTS_THRESHOLD:
        raise RuntimeError(
            f"arxiv returned only {len(results)} results for {topic_slug!r}; "
            "likely a scraper failure — refusing to write."
        )

    added = 0
    with session_scope() as db:
        topic = db.execute(select(Topic).where(Topic.slug == topic_slug)).scalar_one_or_none()
        if not topic:
            raise RuntimeError(f"Topic {topic_slug!r} not in DB — run `openscout seed` first.")

        for result in results:
            arxiv_id = _normalize_arxiv_id(result.entry_id)
            existing = db.execute(
                select(Paper).where(Paper.arxiv_id == arxiv_id)
            ).scalar_one_or_none()
            if existing:
                _ensure_paper_topic(db, existing.id, topic.id)
                continue

            paper = Paper(
                arxiv_id=arxiv_id,
                title=result.title.strip(),
                abstract=result.summary.strip(),
                published_at=result.published.date() if result.published else None,
                pdf_url=result.pdf_url,
                venue="arXiv",
            )
            db.add(paper)
            db.flush()

            _ensure_paper_topic(db, paper.id, topic.id)

            # Per-paper dedupe: arXiv sometimes lists the same author twice with
            # different spellings ("X. Wang" + "Xinyi Wang") which collapse to
            # the same Researcher row via _upsert_researcher_by_name and would
            # violate PaperAuthor (paper_id, researcher_id) UNIQUE. Same fix
            # pattern as v1.1 backfill_anchor_works and v1.6 deep_dive._arxiv_author.
            seen_rids: set[int] = set()
            for position, author in enumerate(result.authors, start=1):
                researcher = _upsert_researcher_by_name(db, author.name)
                if researcher.id in seen_rids:
                    continue
                seen_rids.add(int(researcher.id))
                db.add(
                    PaperAuthor(
                        paper_id=paper.id,
                        researcher_id=researcher.id,
                        position=position,
                    )
                )

            added += 1

    return added


def _normalize_arxiv_id(entry_id: str) -> str:
    """Strip version suffix: `arxiv.org/abs/2401.12345v2` -> `2401.12345`."""
    base = entry_id.rsplit("/", 1)[-1]
    return re.sub(r"v\d+$", "", base)


def _ensure_paper_topic(db: Session, paper_id: int, topic_id: int) -> None:
    pt = db.execute(
        select(PaperTopic).where(
            PaperTopic.paper_id == paper_id,
            PaperTopic.topic_id == topic_id,
        )
    ).scalar_one_or_none()
    if not pt:
        db.add(PaperTopic(paper_id=paper_id, topic_id=topic_id))


def _upsert_researcher_by_name(db: Session, name: str) -> Researcher:
    """Find by exact name_en or create a new low-confidence row.

    This will collapse different people who share a name (e.g. multiple "Wei Wang").
    The Semantic Scholar enrichment pass refines via S2 author IDs.
    """
    name = name.strip()
    if not name:
        name = "Unknown Author"

    existing = db.execute(select(Researcher).where(Researcher.name_en == name)).scalar_one_or_none()
    if existing:
        return existing

    slug = _generate_unique_slug(db, name)
    researcher = Researcher(
        slug=slug,
        name_en=name,
        confidence_level="low",  # auto-discovered; seed anchors are medium/high
    )
    db.add(researcher)
    db.flush()
    return researcher


def _generate_unique_slug(db: Session, name: str) -> str:
    """kebab-case the name, append `-2/-3/...` on collision."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"
    candidate = base
    n = 1
    while db.execute(select(Researcher.id).where(Researcher.slug == candidate)).first():
        n += 1
        candidate = f"{base}-{n}"
    return candidate
