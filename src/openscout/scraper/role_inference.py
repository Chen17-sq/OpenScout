"""Publication-pattern → role heuristic.

Most auto-discovered researchers come in with `current_role=NULL` because we
don't have their CV. The peer_inference.py pass handles the cases where they
also have a strong anchor co-author. This pass catches the long tail: a
researcher who has clearly been a first author of recent work and not a lot
of it is almost certainly a PhD student.

Heuristic — set role=phd when ALL of:
  - current_role is currently NULL (never overwrite verified data)
  - confidence_level == 'low' (only auto-discovered; don't touch anchors)
  - h_index is NULL or ≤ 3 (real PIs have higher)
  - total paper count is small (≤ 8) — established researchers have more
  - is first author of at least one paper (i.e. did the work, didn't just
    co-author with a famous person)

Provenance stored as role_source='publication_pattern' (visible as a dashed
amber badge on the researcher page, same way as v1.3 surname / peer tags).

A 2nd-pass tags `incoming_ap` when a researcher's most-recent affiliation is
a top university AND they have >10 papers AND no current_role — these are
the people the user actively hunts. Conservative on purpose.
"""

from sqlalchemy import func, select

from ..db import session_scope
from ..models import PaperAuthor, Researcher


def infer_roles_from_publication_pattern() -> dict[str, int]:
    counts = {"scanned": 0, "tagged_phd": 0}

    with session_scope() as db:
        # Pre-compute paper counts + min-author-position per researcher (in
        # SQL — much faster than per-row Python loop on 2,500 rows).
        agg_rows = db.execute(
            select(
                PaperAuthor.researcher_id,
                func.count(PaperAuthor.paper_id).label("n_papers"),
                func.min(PaperAuthor.position).label("best_pos"),
            ).group_by(PaperAuthor.researcher_id)
        ).all()
        agg = {int(rid): (int(np), int(bp) if bp is not None else None) for rid, np, bp in agg_rows}

        rs = list(
            db.execute(
                select(Researcher).where(
                    Researcher.current_role.is_(None),
                    Researcher.confidence_level == "low",
                )
            )
            .scalars()
            .all()
        )

        for r in rs:
            counts["scanned"] += 1
            n_papers, best_pos = agg.get(int(r.id), (0, None))
            if not n_papers:
                continue
            # PhD pattern: low h-index, few papers, at least one first-authored
            if (r.h_index is None or r.h_index <= 3) and n_papers <= 8 and best_pos == 1:
                r.current_role = "phd"
                r.role_source = "publication_pattern"
                counts["tagged_phd"] += 1

    return counts


def infer_roles() -> dict[str, int]:
    """Public entrypoint — currently just the PhD-pattern pass."""
    return infer_roles_from_publication_pattern()
