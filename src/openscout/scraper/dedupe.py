"""Merge duplicate Researcher rows.

The same person often gets ingested multiple times under slightly different
names — "X. Wang" / "Xinyi Wang" / "Wang Xinyi" all become separate
Researcher rows because they come from different papers. This module finds
those duplicates by matching on strong identifiers, picks one row to keep,
and migrates all references from the losers to the winner.

Merge keys (any one is sufficient to fuse two rows):
    1. same non-null ``openalex_id``  — cleanest signal (OpenAlex assigns one author per person)
    2. same non-null ``semantic_scholar_id``
    3. same non-null ``email``
    4. same non-null ``orcid``

If two rows match on multiple keys we union them into a single merge group
(``A == B`` by openalex_id, ``B == C`` by email  ⇒  ``{A, B, C}``).

Survivor pick within a group:
    1. higher ``confidence_level``  (high > medium > low)
    2. higher ``works_count``
    3. more ``PaperAuthor`` links
    4. lowest ``id``  (earliest created — last-resort tiebreaker)

This is risky: losing a Researcher row that wasn't actually a duplicate
destroys real data. So:

    * Default is **dry-run**. The function only mutates the DB when called
      with ``dry_run=False``.
    * Each merge group is committed in its own transaction so that one
      bad row can't roll back progress on hundreds of clean merges.
    * Unique-constraint collisions on ``paper_authors`` and
      ``researcher_topics`` (where survivor already has the link) drop the
      duplicate's row rather than crashing the migration.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import (
    Affiliation,
    PaperAuthor,
    Relationship,
    Researcher,
    ResearcherTopic,
    Signal,
)

logger = logging.getLogger(__name__)

# Ranking for confidence_level — higher wins.
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}

# Identifier columns used to find duplicates, in priority order.
# Same shape as Researcher attribute names so we can ``getattr`` cleanly.
_MERGE_KEYS: tuple[str, ...] = ("openalex_id", "semantic_scholar_id", "email", "orcid")


# ---------------------------------------------------------------------------
# Union-find — collapse rows that share ANY merge key into a single group.
# ---------------------------------------------------------------------------


class _UnionFind:
    """Tiny union-find / disjoint-set over integer researcher ids."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        # Path compression.
        root = x
        while self.parent.get(root, root) != root:
            root = self.parent[root]
        while self.parent.get(x, x) != root:
            nxt = self.parent.get(x, x)
            self.parent[x] = root
            x = nxt
        self.parent.setdefault(root, root)
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Attach larger id under smaller — keeps roots low which makes
            # downstream group iteration deterministic.
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb

    def groups(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for node in list(self.parent):
            out.setdefault(self.find(node), []).append(node)
        for ids in out.values():
            ids.sort()
        return out


def _find_duplicate_groups(db: Session) -> list[list[int]]:
    """Return a list of researcher-id groups, each containing >=2 ids.

    Two researchers land in the same group if they share a non-null value
    on any one of the configured merge keys.
    """
    uf = _UnionFind()

    for key in _MERGE_KEYS:
        col = getattr(Researcher, key)
        # Find values shared by more than one row.
        dup_values = list(
            db.execute(
                select(col)
                .where(col.is_not(None))
                .group_by(col)
                .having(func.count(Researcher.id) > 1)
            )
            .scalars()
            .all()
        )
        if not dup_values:
            continue
        # Pull the actual researcher ids for those values and union them.
        rows = list(db.execute(select(Researcher.id, col).where(col.in_(dup_values))).all())
        # Group by value, union ids per value.
        by_value: dict[str, list[int]] = {}
        for rid, val in rows:
            by_value.setdefault(val, []).append(rid)
        for ids in by_value.values():
            anchor = ids[0]
            for other in ids[1:]:
                uf.union(anchor, other)

    return [ids for ids in uf.groups().values() if len(ids) >= 2]


# ---------------------------------------------------------------------------
# Survivor selection.
# ---------------------------------------------------------------------------


def _link_counts(db: Session, ids: Iterable[int]) -> dict[int, int]:
    """Return ``{researcher_id: paper_authors row count}`` for the given ids."""
    rows = list(
        db.execute(
            select(PaperAuthor.researcher_id, func.count())
            .where(PaperAuthor.researcher_id.in_(list(ids)))
            .group_by(PaperAuthor.researcher_id)
        ).all()
    )
    return dict(rows)


def _pick_survivor(researchers: list[Researcher], link_counts: dict[int, int]) -> Researcher:
    """Pick the row to keep from a duplicate group.

    Higher confidence > higher works_count > more PaperAuthor links > lowest id.
    """

    def sort_key(r: Researcher) -> tuple[int, int, int, int]:
        return (
            # Negate so higher value comes first when sorted ascending.
            -_CONFIDENCE_RANK.get((r.confidence_level or "medium").lower(), 0),
            -(r.works_count or 0),
            -link_counts.get(r.id, 0),
            r.id,
        )

    return sorted(researchers, key=sort_key)[0]


# ---------------------------------------------------------------------------
# Migrate one duplicate row's references onto the survivor.
# ---------------------------------------------------------------------------


def _migrate_paper_authors(db: Session, survivor_id: int, dup_id: int) -> int:
    """Move ``paper_authors`` rows from ``dup_id`` to ``survivor_id``.

    Watch the UNIQUE(paper_id, researcher_id) constraint: if the survivor
    already has a row for the same paper, drop the duplicate's row instead
    of moving it (would otherwise raise IntegrityError).
    """
    survivor_papers = set(
        db.execute(select(PaperAuthor.paper_id).where(PaperAuthor.researcher_id == survivor_id))
        .scalars()
        .all()
    )
    dup_links = list(
        db.execute(select(PaperAuthor).where(PaperAuthor.researcher_id == dup_id)).scalars().all()
    )

    moved = 0
    for link in dup_links:
        if link.paper_id in survivor_papers:
            # Survivor already authors this paper — just drop the dup's row.
            db.delete(link)
        else:
            db.execute(
                update(PaperAuthor)
                .where(
                    PaperAuthor.paper_id == link.paper_id,
                    PaperAuthor.researcher_id == dup_id,
                )
                .values(researcher_id=survivor_id)
            )
            survivor_papers.add(link.paper_id)
            moved += 1
    return moved


def _migrate_researcher_topics(db: Session, survivor_id: int, dup_id: int) -> int:
    """Same collision-aware migrate for the (researcher_id, topic_id) PK table."""
    survivor_topics = set(
        db.execute(
            select(ResearcherTopic.topic_id).where(ResearcherTopic.researcher_id == survivor_id)
        )
        .scalars()
        .all()
    )
    dup_rows = list(
        db.execute(select(ResearcherTopic).where(ResearcherTopic.researcher_id == dup_id))
        .scalars()
        .all()
    )
    moved = 0
    for row in dup_rows:
        if row.topic_id in survivor_topics:
            db.delete(row)
        else:
            db.execute(
                update(ResearcherTopic)
                .where(
                    ResearcherTopic.researcher_id == dup_id,
                    ResearcherTopic.topic_id == row.topic_id,
                )
                .values(researcher_id=survivor_id)
            )
            survivor_topics.add(row.topic_id)
            moved += 1
    return moved


def _migrate_relationships(db: Session, survivor_id: int, dup_id: int) -> int:
    """Remap relationships referencing the duplicate onto the survivor.

    The ``relationships`` table has no unique constraint on
    (from, to, type), so we don't need collision handling. We DO drop
    self-loops that the remap would create (advisor of myself, etc.) and
    fold exact duplicates (same from + to + type) after the remap.
    """
    moved = 0
    # from_researcher_id
    moved += (
        db.execute(
            update(Relationship)
            .where(Relationship.from_researcher_id == dup_id)
            .values(from_researcher_id=survivor_id)
        ).rowcount
        or 0
    )
    # to_researcher_id
    moved += (
        db.execute(
            update(Relationship)
            .where(Relationship.to_researcher_id == dup_id)
            .values(to_researcher_id=survivor_id)
        ).rowcount
        or 0
    )

    # Drop self-loops that may have been introduced (e.g. if dup was
    # listed as both ends of a coauthor edge with the survivor).
    db.execute(
        delete(Relationship).where(Relationship.from_researcher_id == Relationship.to_researcher_id)
    )

    # De-duplicate identical (from, to, type) triples — keep the lowest id.
    dup_groups = list(
        db.execute(
            select(
                Relationship.from_researcher_id,
                Relationship.to_researcher_id,
                Relationship.type,
                func.min(Relationship.id),
                func.count(Relationship.id),
            )
            .group_by(
                Relationship.from_researcher_id,
                Relationship.to_researcher_id,
                Relationship.type,
            )
            .having(func.count(Relationship.id) > 1)
        ).all()
    )
    for from_id, to_id, rel_type, keep_id, _ in dup_groups:
        db.execute(
            delete(Relationship).where(
                Relationship.from_researcher_id == from_id,
                Relationship.to_researcher_id == to_id,
                Relationship.type == rel_type,
                Relationship.id != keep_id,
            )
        )

    return moved


def _merge_one_group(db: Session, group: list[int]) -> tuple[Researcher, list[Researcher], int]:
    """Plan a merge: load rows, pick survivor, return (survivor, losers, link_count).

    Does NOT mutate the DB — caller is responsible for executing the
    migration if it wants to.
    """
    researchers = list(
        db.execute(select(Researcher).where(Researcher.id.in_(group))).scalars().all()
    )
    link_counts = _link_counts(db, group)
    survivor = _pick_survivor(researchers, link_counts)
    losers = [r for r in researchers if r.id != survivor.id]
    total_links = sum(link_counts.get(r.id, 0) for r in losers)
    return survivor, losers, total_links


def _execute_merge(db: Session, survivor: Researcher, losers: list[Researcher]) -> int:
    """Apply the migration. Returns the number of paper_authors links moved."""
    links_moved = 0
    for dup in losers:
        # paper_authors — collision-aware.
        links_moved += _migrate_paper_authors(db, survivor.id, dup.id)

        # researcher_topics — collision-aware.
        _migrate_researcher_topics(db, survivor.id, dup.id)

        # relationships — remap + de-dupe.
        _migrate_relationships(db, survivor.id, dup.id)

        # signals — straight remap.
        db.execute(
            update(Signal).where(Signal.researcher_id == dup.id).values(researcher_id=survivor.id)
        )

        # affiliations — straight remap (no unique constraint).
        db.execute(
            update(Affiliation)
            .where(Affiliation.researcher_id == dup.id)
            .values(researcher_id=survivor.id)
        )

        # Any other researcher whose advisor_id pointed at dup → repoint
        # at survivor.
        db.execute(
            update(Researcher).where(Researcher.advisor_id == dup.id).values(advisor_id=survivor.id)
        )

        # signature_paper_id — only adopt the dup's value if survivor lacks one.
        if dup.signature_paper_id and not survivor.signature_paper_id:
            survivor.signature_paper_id = dup.signature_paper_id

        # Clear dup.advisor_id if it points at survivor (would survive the
        # delete and tomorrow become a dangling self-loop after a future
        # remap) — defensive, mostly belt-and-suspenders.
        if dup.advisor_id == survivor.id:
            dup.advisor_id = None

        # Finally — delete the loser. Flush so dependent FK updates have
        # already hit the DB before the row goes away.
        db.flush()
        db.delete(dup)
        db.flush()

    return links_moved


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def dedupe_researchers(dry_run: bool = True) -> dict[str, int]:
    """Find and (optionally) merge duplicate Researcher rows.

    Args:
        dry_run: When True (default) only log what *would* be merged.

    Returns:
        Counts dict with keys:
            ``groups_found``  — number of dup groups (each >=2 rows)
            ``would_merge``   — number of duplicate rows that would be deleted
            ``merged``        — number of duplicate rows actually deleted
                                (== ``would_merge`` on a successful apply run)
            ``links_moved``   — number of paper_authors rows re-pointed
            ``errors``        — number of groups that failed and were skipped
    """
    counts = {
        "groups_found": 0,
        "would_merge": 0,
        "merged": 0,
        "links_moved": 0,
        "errors": 0,
    }

    # Manage the session manually instead of using ``session_scope`` so
    # we can commit per-group and isolate failures.
    db = SessionLocal()
    try:
        groups = _find_duplicate_groups(db)
        counts["groups_found"] = len(groups)
        if not groups:
            logger.info("dedupe: no duplicate groups found")
            return counts

        mode = "DRY RUN" if dry_run else "APPLY"
        logger.info("dedupe (%s): %d duplicate group(s) found", mode, len(groups))

        for group in groups:
            try:
                survivor, losers, link_total = _merge_one_group(db, group)
            except Exception:
                logger.exception("dedupe: failed to plan merge for group=%s", group)
                counts["errors"] += 1
                continue

            # Identify which merge key(s) actually matched — useful in logs.
            matched: list[str] = []
            for key in _MERGE_KEYS:
                vals = {getattr(r, key) for r in [survivor, *losers]}
                vals.discard(None)
                if len(vals) == 1 and vals:
                    matched.append(f"{key}={next(iter(vals))}")

            logger.info(
                "dedupe %s: keep id=%d slug=%s name=%r  drop=%s  links_to_move=%d  matched=%s",
                mode,
                survivor.id,
                survivor.slug,
                survivor.name_en,
                [(r.id, r.slug, r.name_en) for r in losers],
                link_total,
                ", ".join(matched) or "<none>",
            )

            counts["would_merge"] += len(losers)

            if dry_run:
                # Don't even let SQLAlchemy persist the "planning" state.
                db.expunge_all()
                continue

            try:
                links_moved = _execute_merge(db, survivor, losers)
                db.commit()
                counts["merged"] += len(losers)
                counts["links_moved"] += links_moved
            except Exception:
                logger.exception(
                    "dedupe: failed to apply merge survivor=%d losers=%s",
                    survivor.id,
                    [r.id for r in losers],
                )
                db.rollback()
                counts["errors"] += 1

        return counts
    finally:
        db.close()
