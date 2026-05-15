"""arXiv ingest — pull recent papers for a topic and stash them."""

import arxiv
from sqlalchemy import select

from ..db import session_scope
from ..models import Paper, PaperTopic, Topic

# Topic-specific arXiv query strings. Tune these as you find false positives / negatives.
TOPIC_QUERIES: dict[str, str] = {
    "embodied": (
        "cat:cs.RO OR "
        "(cat:cs.AI AND (abs:robot OR abs:manipulation OR abs:locomotion OR abs:dexterous OR abs:embodied))"
    ),
    "world_models": (
        "(abs:\"world model\" OR abs:\"video prediction\" OR abs:\"dynamics model\" OR abs:\"latent dynamics\") "
        "AND (cat:cs.LG OR cat:cs.AI OR cat:cs.CV)"
    ),
    "ai4sci": (
        "cat:q-bio.BM OR cat:physics.chem-ph OR cat:cond-mat.mtrl-sci OR "
        "(cat:cs.LG AND (abs:protein OR abs:molecule OR abs:\"material discovery\" OR abs:crystallography))"
    ),
}

# Safety gate — if we get fewer than this many results, suspect a scraper failure
MIN_RESULTS_THRESHOLD = 3


def ingest_topic(topic_slug: str, limit: int = 50) -> int:
    """Pull recent arXiv papers for `topic_slug`. Returns count of newly added papers."""
    query = TOPIC_QUERIES.get(topic_slug)
    if not query:
        raise ValueError(
            f"Unknown topic: {topic_slug!r}. Known: {list(TOPIC_QUERIES)}"
        )

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
            f"likely a scraper failure — refusing to write."
        )

    added = 0
    with session_scope() as db:
        topic = db.execute(
            select(Topic).where(Topic.slug == topic_slug)
        ).scalar_one_or_none()
        if not topic:
            raise RuntimeError(
                f"Topic {topic_slug!r} not in DB — run `openscout seed` first."
            )

        for result in results:
            arxiv_id = result.entry_id.rsplit("/", 1)[-1].split("v")[0]
            existing = db.execute(
                select(Paper).where(Paper.arxiv_id == arxiv_id)
            ).scalar_one_or_none()
            if existing:
                # Already have this paper; ensure the topic mapping exists.
                pt = db.execute(
                    select(PaperTopic).where(
                        PaperTopic.paper_id == existing.id, PaperTopic.topic_id == topic.id
                    )
                ).scalar_one_or_none()
                if not pt:
                    db.add(PaperTopic(paper_id=existing.id, topic_id=topic.id))
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
            db.flush()  # populate paper.id
            db.add(PaperTopic(paper_id=paper.id, topic_id=topic.id))
            added += 1

    return added
