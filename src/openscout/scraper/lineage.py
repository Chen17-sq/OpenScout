"""Advisor / student inference — heuristic, statistical.

We don't have explicit "advised-by" data from arXiv. Two signals we DO have:
  1. Co-authorship: junior author + senior anchor on the same papers
  2. Affiliation: both at the same institution

v0 algorithm: for each low-confidence researcher R, count how many of R's papers
have an anchor researcher A as co-author. If A appears on ≥ N of R's papers AND
A's count is the highest among co-authors AND R has ≤ 3 papers total (i.e. R is
junior), infer A → R is a likely advisor edge.

We tag the inferred edge with `confidence: 'low'` and `evidence: 'co-author
frequency: X/Y papers'`. The frontend can then visually distinguish inferred
from manually-asserted lineage.
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import PaperAuthor, Relationship, Researcher

# Min co-authored papers required before we'll propose a lineage edge.
MIN_COAUTHOR_PAPERS = 2
# Max papers a junior researcher can have for us to consider them "junior."
MAX_JUNIOR_PAPERS = 5


def _coauthors_of(db: Session, researcher_id: int) -> list[tuple[int, int]]:
    """Return list of (coauthor_id, count) for one researcher's papers."""
    paper_ids = [
        pid
        for (pid,) in db.execute(
            select(PaperAuthor.paper_id).where(PaperAuthor.researcher_id == researcher_id)
        ).all()
    ]
    if not paper_ids:
        return []

    coauthor_rows = db.execute(
        select(PaperAuthor.researcher_id).where(
            PaperAuthor.paper_id.in_(paper_ids),
            PaperAuthor.researcher_id != researcher_id,
        )
    ).all()
    counter: Counter[int] = Counter()
    for (rid,) in coauthor_rows:
        counter[rid] += 1
    return counter.most_common()


def infer_lineage() -> dict[str, int]:
    """Insert `Relationship` rows for inferred advisor → student edges.

    Returns counts: {edges_added, juniors_scanned, anchors_matched}
    """
    added = 0
    juniors = 0
    matched_anchors = 0

    with session_scope() as db:
        # Identify candidates: researchers with <= MAX_JUNIOR_PAPERS papers
        # and currently low confidence (= auto-discovered from paper bylines)
        rows = db.execute(
            select(Researcher, PaperAuthor.researcher_id)
            .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
            .where(Researcher.confidence_level == "low")
            .group_by(Researcher.id)
        ).all()
        candidates = {r.id: r for r, _ in rows}

        for r_id, junior in candidates.items():
            n_papers = db.execute(
                select(PaperAuthor).where(PaperAuthor.researcher_id == r_id)
            ).all()
            n_papers = len(n_papers)
            if n_papers == 0 or n_papers > MAX_JUNIOR_PAPERS:
                continue
            juniors += 1

            coauthors = _coauthors_of(db, r_id)
            if not coauthors:
                continue

            # Top co-author by count
            top_id, top_n = coauthors[0]
            if top_n < MIN_COAUTHOR_PAPERS:
                continue

            # Is the top co-author an anchor (medium/high confidence)?
            anchor = db.execute(
                select(Researcher).where(Researcher.id == top_id)
            ).scalar_one_or_none()
            if not anchor or anchor.confidence_level == "low":
                continue
            matched_anchors += 1

            # Don't re-add if already exists
            existing = db.execute(
                select(Relationship).where(
                    Relationship.from_researcher_id == anchor.id,
                    Relationship.to_researcher_id == r_id,
                    Relationship.type == "advisor",
                )
            ).scalar_one_or_none()
            if existing:
                continue

            db.add(
                Relationship(
                    from_researcher_id=anchor.id,
                    to_researcher_id=r_id,
                    type="advisor",
                    confidence="low",
                    evidence=f"co-author frequency: {top_n}/{n_papers} papers",
                )
            )
            # Also set the convenience advisor_id on the junior
            if not junior.advisor_id:
                junior.advisor_id = anchor.id
            added += 1

    return {
        "edges_added": added,
        "juniors_scanned": juniors,
        "anchors_matched": matched_anchors,
    }
