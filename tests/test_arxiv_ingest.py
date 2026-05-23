"""Tests for the arXiv topic ingestor — specifically the per-paper author
dedupe guard added after the v1.13 daily run failed on ai4sci with
UNIQUE(paper_id, researcher_id) violations.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from openscout.db import session_scope
from openscout.models import Paper, PaperAuthor, Researcher, Topic


@pytest.fixture
def topic_row():
    """Make sure an 'embodied' topic row exists."""
    with session_scope() as db:
        existing = db.execute(select(Topic).where(Topic.slug == "embodied")).scalar_one_or_none()
        if not existing:
            db.add(Topic(slug="embodied", name="Embodied AI"))
    yield
    # cleanup left to subsequent tests / DB teardown


def _fake_arxiv_result(arxiv_id: str, title: str, author_names: list[str]):
    """Build a stub that quacks like the `arxiv` library's Result object."""
    result = MagicMock()
    result.entry_id = f"http://arxiv.org/abs/{arxiv_id}v1"
    result.title = title
    result.summary = "A test abstract."
    result.published = None
    result.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    result.authors = [MagicMock(name=name) for name in author_names]
    # MagicMock auto-assigns .name; override so it actually returns the string
    for stub, n in zip(result.authors, author_names, strict=True):
        stub.name = n
    return result


def test_dedup_same_researcher_byline_twice(topic_row):
    """If arXiv lists the same person twice with different spellings (e.g.
    'X. Wang' and 'Xinyi Wang'), `_upsert_researcher_by_name` slugifies both
    to the same row, and the second PaperAuthor insert would violate the
    UNIQUE(paper_id, researcher_id) constraint without the dedupe guard.
    """
    # Two spellings that normalize to the SAME slug
    paper = _fake_arxiv_result(
        "2511.01234",
        "Test Paper With A Collision",
        ["Wei Wei", "Wei Wei", "Bob Smith"],  # exact duplicate is the simplest collision case
    )

    fake_search = MagicMock()
    fake_client = MagicMock()
    fake_client.results.return_value = [paper]

    with (
        patch("openscout.scraper.arxiv.arxiv.Search", return_value=fake_search),
        patch("openscout.scraper.arxiv.arxiv.Client", return_value=fake_client),
        patch("openscout.scraper.arxiv.MIN_RESULTS_THRESHOLD", 0),
    ):
        from openscout.scraper.arxiv import ingest_topic

        n_added = ingest_topic("embodied", limit=10)
        assert n_added == 1

    # Verify the duplicate author row was NOT inserted (i.e. the dedupe guard fired)
    with session_scope() as db:
        paper_row = db.execute(select(Paper).where(Paper.arxiv_id == "2511.01234")).scalar_one()
        author_rows = db.execute(
            select(PaperAuthor).where(PaperAuthor.paper_id == paper_row.id)
        ).all()
        # 2 distinct researchers (Wei Wei collapsed; Bob Smith separate)
        assert len(author_rows) == 2
        researcher_ids = {row.PaperAuthor.researcher_id for row in author_rows}
        assert len(researcher_ids) == 2


def test_ingest_does_not_double_link_existing_researcher(topic_row):
    """A researcher already in the DB (e.g. from a previous run) should NOT
    end up with two PaperAuthor rows pointing at the same paper.
    """
    # Pre-create the researcher
    with session_scope() as db:
        existing = Researcher(slug="grace-hopper", name_en="Grace Hopper")
        db.add(existing)
        db.flush()
        existing_id = existing.id

    paper = _fake_arxiv_result(
        "2511.05678",
        "Another Test Paper",
        ["Grace Hopper", "G. Hopper"],  # both should slugify to grace-hopper
    )

    fake_client = MagicMock()
    fake_client.results.return_value = [paper]

    with (
        patch("openscout.scraper.arxiv.arxiv.Search"),
        patch("openscout.scraper.arxiv.arxiv.Client", return_value=fake_client),
        patch("openscout.scraper.arxiv.MIN_RESULTS_THRESHOLD", 0),
    ):
        from openscout.scraper.arxiv import ingest_topic

        ingest_topic("embodied", limit=10)

    with session_scope() as db:
        paper_row = db.execute(select(Paper).where(Paper.arxiv_id == "2511.05678")).scalar_one()
        links_to_grace = db.execute(
            select(PaperAuthor).where(
                PaperAuthor.paper_id == paper_row.id,
                PaperAuthor.researcher_id == existing_id,
            )
        ).all()
        # Exactly ONE byline link for Grace despite her name appearing twice
        assert len(links_to_grace) == 1
