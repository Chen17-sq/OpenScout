"""Advisor / student inference — heuristic, statistical.

v2 algorithm: for each researcher with ≤ 5 papers, look at co-authors.
For each co-author who appears on ≥ 2 of their papers:
  base_score = co_author_count / total_papers
  + 0.3 if same country (institutional proxy)
  + 0.2 if anchor (high/medium confidence)
  + 0.2 if co-author has h-index >= 10 (seniority)
Pick top-scoring co-author. If score >= 0.5, infer advisor edge.

Each edge gets `evidence` text describing the signals used.
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import PaperAuthor, Relationship, Researcher

MIN_COAUTHOR_PAPERS = 2
MAX_JUNIOR_PAPERS = 5
MIN_INFERENCE_SCORE = 0.5


def _coauthors_of(db: Session, researcher_id: int) -> list[tuple[int, int]]:
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


def _score_edge(
    coauthor_count: int,
    total_papers: int,
    same_country: bool,
    is_anchor: bool,
    advisor_h: int | None,
) -> tuple[float, list[str]]:
    """Composite score in [0, ~1.5] and a list of evidence strings."""
    base = coauthor_count / max(1, total_papers)
    score = base
    evidence = [f"{coauthor_count}/{total_papers} papers co-authored"]
    if same_country:
        score += 0.30
        evidence.append("same country")
    if is_anchor:
        score += 0.20
        evidence.append("anchor")
    if advisor_h and advisor_h >= 10:
        score += 0.20
        evidence.append(f"h-index ≥ 10 ({advisor_h})")
    return score, evidence


def infer_lineage() -> dict[str, int]:
    """Infer advisor → student edges. Returns counts."""
    added = 0
    juniors = 0
    matched_anchors = 0

    with session_scope() as db:
        # Candidates: low-confidence researchers with ≤ MAX_JUNIOR_PAPERS papers
        candidates_stmt = select(Researcher).where(Researcher.confidence_level == "low")
        candidates = list(db.execute(candidates_stmt).scalars().all())

        for junior in candidates:
            n_papers_rows = db.execute(
                select(PaperAuthor).where(PaperAuthor.researcher_id == junior.id)
            ).all()
            n_papers = len(n_papers_rows)
            if n_papers == 0 or n_papers > MAX_JUNIOR_PAPERS:
                continue
            juniors += 1

            coauthors = _coauthors_of(db, junior.id)
            if not coauthors:
                continue

            best_score = 0.0
            best_anchor: Researcher | None = None
            best_evidence: list[str] = []
            best_count = 0

            for c_id, c_count in coauthors[:5]:
                if c_count < MIN_COAUTHOR_PAPERS:
                    continue
                candidate_anchor = db.execute(
                    select(Researcher).where(Researcher.id == c_id)
                ).scalar_one_or_none()
                if not candidate_anchor:
                    continue
                is_anchor = candidate_anchor.confidence_level != "low"
                same_country = bool(
                    junior.country
                    and candidate_anchor.country
                    and junior.country == candidate_anchor.country
                )
                score, evidence = _score_edge(
                    c_count,
                    n_papers,
                    same_country,
                    is_anchor,
                    candidate_anchor.h_index,
                )
                if score > best_score:
                    best_score = score
                    best_anchor = candidate_anchor
                    best_evidence = evidence
                    best_count = c_count

            if best_anchor and best_score >= MIN_INFERENCE_SCORE:
                matched_anchors += 1
                existing = db.execute(
                    select(Relationship).where(
                        Relationship.from_researcher_id == best_anchor.id,
                        Relationship.to_researcher_id == junior.id,
                        Relationship.type == "advisor",
                    )
                ).scalar_one_or_none()
                if existing:
                    # Update evidence if score is higher
                    if best_count > 0:
                        existing.evidence = "; ".join(best_evidence)
                    continue

                db.add(
                    Relationship(
                        from_researcher_id=best_anchor.id,
                        to_researcher_id=junior.id,
                        type="advisor",
                        confidence="low" if best_score < 0.8 else "medium",
                        evidence="; ".join(best_evidence),
                    )
                )
                if not junior.advisor_id:
                    junior.advisor_id = best_anchor.id
                added += 1

    return {
        "edges_added": added,
        "juniors_scanned": juniors,
        "anchors_matched": matched_anchors,
    }
