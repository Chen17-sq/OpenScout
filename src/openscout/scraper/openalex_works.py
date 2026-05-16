"""Backfill each anchor's publication history from OpenAlex.

Why: our arXiv ingest only has the last N days of papers — anchors have years
of work. By pulling their OpenAlex `works` list, we discover papers we don't
have yet (some on arXiv, some only in journals), which dramatically improves
the lineage inference (anchors + their students share papers).

For each anchor with `openalex_id`:
  1. Fetch their last 80 works from OpenAlex
  2. For each work, upsert a Paper record
  3. Link PaperAuthor for the anchor (position from OpenAlex authorship list)
  4. Link any other co-authors who already exist in our DB (so lineage can fire)

Polite-pool email is set in scraper/openalex.py.
"""

import re
import time

import pyalex
from pyalex import Works
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher

pyalex.config.email = "openscout-public@github.com"


def _normalize_name(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _extract_arxiv_id(work: dict) -> str | None:
    """OpenAlex work → arxiv id when available."""
    # Try external IDs
    ids = work.get("ids", {})
    arxiv = ids.get("arxiv") or ""
    if arxiv:
        m = re.search(r"(\d{4}\.\d{4,5})", arxiv)
        if m:
            return m.group(1)
    # Fallback: scan landing page URL
    url = work.get("primary_location", {}).get("landing_page_url") or ""
    m = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", url)
    return m.group(1) if m else None


def _extract_pdf_url(work: dict) -> str | None:
    return (work.get("primary_location") or {}).get("pdf_url") or work.get("open_access", {}).get(
        "oa_url"
    )


def _upsert_paper(db: Session, work: dict) -> Paper | None:
    openalex_id = work.get("id")
    if not openalex_id:
        return None

    # Already have it via openalex_id?
    existing = db.execute(
        select(Paper).where(Paper.openalex_id == openalex_id)
    ).scalar_one_or_none()
    if existing:
        # Refresh citation count opportunistically
        cb = int(work.get("cited_by_count") or 0)
        if cb and cb != (existing.citation_count or 0):
            existing.citation_count = cb
        return existing

    arxiv_id = _extract_arxiv_id(work)
    # Maybe we already have it by arxiv_id (from earlier ingest)
    if arxiv_id:
        existing_arxiv = db.execute(
            select(Paper).where(Paper.arxiv_id == arxiv_id)
        ).scalar_one_or_none()
        if existing_arxiv:
            existing_arxiv.openalex_id = openalex_id
            existing_arxiv.citation_count = int(work.get("cited_by_count") or 0)
            return existing_arxiv

    title = work.get("title") or "[untitled]"
    abstract_idx = work.get("abstract_inverted_index")
    abstract = _abstract_from_inverted_index(abstract_idx) if abstract_idx else None

    published_at = None
    if work.get("publication_date"):
        try:
            from datetime import date as Date

            published_at = Date.fromisoformat(work["publication_date"])
        except Exception:
            pass

    src = (work.get("primary_location") or {}).get("source") or {}
    paper = Paper(
        openalex_id=openalex_id,
        arxiv_id=arxiv_id,
        title=title[:1000],
        abstract=abstract,
        published_at=published_at,
        venue=src.get("display_name") if isinstance(src, dict) else None,
        pdf_url=_extract_pdf_url(work),
        citation_count=int(work.get("cited_by_count") or 0),
        doi=work.get("doi"),
    )
    db.add(paper)
    db.flush()
    return paper


def _abstract_from_inverted_index(idx: dict) -> str | None:
    """OpenAlex stores abstracts as inverted indexes (word → positions). Reconstruct."""
    if not idx:
        return None
    try:
        positions: list[tuple[int, str]] = []
        for word, pos_list in idx.items():
            for pos in pos_list:
                positions.append((pos, word))
        positions.sort()
        return " ".join(w for _, w in positions)[:4000]
    except Exception:
        return None


def _link_anchor_authorship(db: Session, paper: Paper, anchor: Researcher, work: dict) -> None:
    """Attach anchor + any other already-known co-authors to the paper."""
    authorships = work.get("authorships") or []
    anchor_name = _normalize_name(anchor.name_en)

    # Position the anchor
    anchor_position: int | None = None
    for idx, a in enumerate(authorships, start=1):
        name = _normalize_name((a.get("author") or {}).get("display_name") or "")
        if name == anchor_name:
            anchor_position = idx
            break

    if anchor_position:
        existing = db.execute(
            select(PaperAuthor).where(
                PaperAuthor.paper_id == paper.id, PaperAuthor.researcher_id == anchor.id
            )
        ).scalar_one_or_none()
        if not existing:
            db.add(
                PaperAuthor(
                    paper_id=paper.id,
                    researcher_id=anchor.id,
                    position=anchor_position,
                )
            )

    # For each other co-author, try to find an existing Researcher by name
    for idx, a in enumerate(authorships, start=1):
        if idx == anchor_position:
            continue
        author = a.get("author") or {}
        name = (author.get("display_name") or "").strip()
        if not name:
            continue
        existing_r = db.execute(
            select(Researcher).where(Researcher.name_en == name)
        ).scalar_one_or_none()
        if not existing_r:
            continue
        existing_pa = db.execute(
            select(PaperAuthor).where(
                PaperAuthor.paper_id == paper.id, PaperAuthor.researcher_id == existing_r.id
            )
        ).scalar_one_or_none()
        if not existing_pa:
            db.add(
                PaperAuthor(
                    paper_id=paper.id,
                    researcher_id=existing_r.id,
                    position=idx,
                )
            )


def backfill_anchor_works(per_anchor_limit: int = 80, sleep_between: float = 0.2) -> dict[str, int]:
    """Walk every anchor (high/medium confidence with openalex_id), fetch their
    last N works, and upsert Papers + PaperAuthor links.

    Returns counts: {anchors_processed, papers_added, links_added}
    """
    counts = {
        "anchors_processed": 0,
        "papers_added": 0,
        "papers_updated": 0,
        "links_added": 0,
        "errors": 0,
    }
    with session_scope() as db:
        anchors = list(
            db.execute(
                select(Researcher)
                .where(
                    Researcher.openalex_id.is_not(None),
                    Researcher.confidence_level.in_(["high", "medium"]),
                )
                .order_by(desc(Researcher.citation_count))
            )
            .scalars()
            .all()
        )

    for anchor_id in [r.id for r in anchors]:
        # Re-fetch anchor in fresh session (so we don't keep huge txn open)
        with session_scope() as db:
            anchor = db.execute(
                select(Researcher).where(Researcher.id == anchor_id)
            ).scalar_one_or_none()
            if not anchor or not anchor.openalex_id:
                continue
            counts["anchors_processed"] += 1

            try:
                works_query = Works().filter(authorships={"author": {"id": anchor.openalex_id}})
                works = works_query.get(per_page=min(per_anchor_limit, 100))
            except Exception:
                counts["errors"] += 1
                time.sleep(sleep_between)
                continue

            for work in (works or [])[:per_anchor_limit]:
                paper = _upsert_paper(db, work)
                if not paper:
                    continue
                # Track whether this was new
                if paper.openalex_id and paper.openalex_id != work.get("id"):
                    pass  # shouldn't happen
                before_links_count = (
                    db.execute(select(PaperAuthor).where(PaperAuthor.paper_id == paper.id))
                    .scalars()
                    .all()
                )
                before_n = len(list(before_links_count))
                _link_anchor_authorship(db, paper, anchor, work)
                db.flush()
                after_links_count = (
                    db.execute(select(PaperAuthor).where(PaperAuthor.paper_id == paper.id))
                    .scalars()
                    .all()
                )
                after_n = len(list(after_links_count))
                counts["links_added"] += max(0, after_n - before_n)
                if not before_n:
                    counts["papers_added"] += 1
                else:
                    counts["papers_updated"] += 1
            time.sleep(sleep_between)

    return counts
