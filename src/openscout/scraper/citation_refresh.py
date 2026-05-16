"""Refresh paper.citation_count from OpenAlex.

We grab citation counts at first-ingest time, but they grow. This refreshes the
most-cited and most-recent papers periodically. Cheap (one /works/ID call per
paper, no rate limits in OpenAlex polite pool).
"""

import time

import pyalex
from pyalex import Works
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper

pyalex.config.email = "openscout-public@github.com"


def refresh_citation_counts(limit: int = 100, sleep_between: float = 0.15) -> dict[str, int]:
    """Refresh citation_count for top-N papers with `openalex_id`."""
    counts = {"checked": 0, "updated": 0, "errors": 0}

    with session_scope() as db:
        papers = list(
            db.execute(
                select(Paper)
                .where(Paper.openalex_id.is_not(None))
                .order_by(desc(Paper.citation_count))
                .limit(limit)
            )
            .scalars()
            .all()
        )

        for p in papers:
            counts["checked"] += 1
            try:
                work_id = p.openalex_id.rsplit("/", 1)[-1]
                w = Works()[work_id]
                new_cc = int(w.get("cited_by_count") or 0)
                if new_cc != (p.citation_count or 0):
                    p.citation_count = new_cc
                    counts["updated"] += 1
            except Exception:
                counts["errors"] += 1
            time.sleep(sleep_between)

    return counts
