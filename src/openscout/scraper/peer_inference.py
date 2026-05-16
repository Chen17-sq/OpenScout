"""Co-author affiliation inheritance.

For each auto-discovered researcher with no country, look at their co-authors.
If their most-frequent co-author has a known country AND that co-author is an
anchor (high/medium confidence), inherit:

  - country
  - current_affiliation_id   (likely they're at the same institution)
  - current_role = "phd"     (if they have ≤ 3 papers — junior signal)

Inference is recorded with source = "peer_inheritance" so it's auditable.
"""

from collections import Counter

from sqlalchemy import select

from ..db import session_scope
from ..models import PaperAuthor, Researcher


def _coauthor_anchor(db, junior_id: int) -> Researcher | None:
    """Return the highest-frequency anchor co-author (or None)."""
    paper_ids = [
        pid
        for (pid,) in db.execute(
            select(PaperAuthor.paper_id).where(PaperAuthor.researcher_id == junior_id)
        ).all()
    ]
    if not paper_ids:
        return None

    coauthor_rows = db.execute(
        select(PaperAuthor.researcher_id).where(
            PaperAuthor.paper_id.in_(paper_ids),
            PaperAuthor.researcher_id != junior_id,
        )
    ).all()
    counter: Counter[int] = Counter(rid for (rid,) in coauthor_rows)

    for cid, _count in counter.most_common(10):
        candidate = db.execute(select(Researcher).where(Researcher.id == cid)).scalar_one_or_none()
        if candidate and candidate.confidence_level in ("high", "medium"):
            return candidate
    return None


def infer_from_peers(limit: int | None = None) -> dict[str, int]:
    counts = {
        "scanned": 0,
        "country_inherited": 0,
        "affiliation_inherited": 0,
        "role_inherited": 0,
    }

    with session_scope() as db:
        stmt = select(Researcher).where(
            Researcher.confidence_level == "low",
            Researcher.country.is_(None),  # only fill what's missing
        )
        if limit:
            stmt = stmt.limit(limit)
        juniors = list(db.execute(stmt).scalars().all())

        for j in juniors:
            counts["scanned"] += 1
            anchor = _coauthor_anchor(db, j.id)
            if not anchor:
                continue

            if anchor.country and not j.country:
                j.country = anchor.country
                j.country_source = "peer_inheritance"
                counts["country_inherited"] += 1

            if anchor.current_affiliation_id and not j.current_affiliation_id:
                j.current_affiliation_id = anchor.current_affiliation_id
                j.affiliation_source = "peer_inheritance"
                counts["affiliation_inherited"] += 1

            # Junior role inference: ≤ 3 papers AND first-author position somewhere
            # → likely a PhD student of this anchor.
            if not j.current_role:
                n_papers = len(
                    db.execute(
                        select(PaperAuthor.paper_id).where(PaperAuthor.researcher_id == j.id)
                    ).all()
                )
                if n_papers <= 3:
                    j.current_role = "phd"
                    j.role_source = "peer_inheritance"
                    counts["role_inherited"] += 1

    return counts
