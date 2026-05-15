"""Semantic Scholar enrichment — canonical S2 author IDs, citation counts, affiliations.

The arXiv ingest creates Researchers from authors via exact-name match — which collapses
homonyms (every "Wei Wang" becomes the same row). S2 has disambiguated author IDs;
this module attaches those to our Researchers so future cross-paper joins are correct.

Rate limits without API key: ~100 requests / 5 minutes. With key: ~1000 / 5 min.
"""

import time

import httpx
from sqlalchemy import desc, select
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings
from ..db import session_scope
from ..models import Paper, Researcher

S2_BASE = "https://api.semanticscholar.org/graph/v1"
PAPER_FIELDS = (
    "paperId,title,citationCount,influentialCitationCount,"
    "authors.authorId,authors.name,authors.affiliations,authors.homepage,"
    "authors.hIndex,authors.paperCount,authors.citationCount"
)

# Sleep between requests. Without an API key, ~1.1s keeps us under the rate limit.
REQUEST_INTERVAL_SEC = 1.1


class TransientS2Error(Exception):
    """Raised on 429 / 5xx so tenacity can retry."""


def _client() -> httpx.Client:
    headers = {"User-Agent": "OpenScout/0.1 (+https://github.com/Chen17-sq/OpenScout)"}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    return httpx.Client(headers=headers, timeout=30.0)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type(TransientS2Error),
    reraise=True,
)
def _fetch_paper(client: httpx.Client, arxiv_id: str) -> dict | None:
    url = f"{S2_BASE}/paper/arXiv:{arxiv_id}"
    r = client.get(url, params={"fields": PAPER_FIELDS})
    if r.status_code == 200:
        return r.json()
    if r.status_code in (400, 404):
        return None
    if r.status_code == 429 or 500 <= r.status_code < 600:
        raise TransientS2Error(f"S2 {r.status_code} on {arxiv_id}")
    return None


def enrich_recent_papers(limit: int = 30) -> tuple[int, int]:
    """For each paper without an S2 ID, fetch S2 metadata and update authors.

    Returns: (papers_enriched, researchers_updated)
    """
    enriched = 0
    updated = 0

    with _client() as client, session_scope() as db:
        papers = (
            db.execute(
                select(Paper)
                .where(Paper.semantic_scholar_id.is_(None), Paper.arxiv_id.is_not(None))
                .order_by(desc(Paper.first_seen_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )

        for paper in papers:
            try:
                data = _fetch_paper(client, paper.arxiv_id)
            except TransientS2Error:
                continue
            time.sleep(REQUEST_INTERVAL_SEC)

            if not data:
                continue

            paper.semantic_scholar_id = data.get("paperId")
            paper.citation_count = int(data.get("citationCount") or 0)
            enriched += 1

            for ad in data.get("authors", []) or []:
                if _update_researcher(db, ad):
                    updated += 1

    return enriched, updated


def _update_researcher(db, ad: dict) -> bool:
    """Update a Researcher row with S2-provided fields. Returns True if anything changed."""
    s2_id = ad.get("authorId")
    name = ad.get("name")
    if not s2_id or not name:
        return False

    # Already mapped to this S2 ID — nothing to do.
    by_s2 = db.execute(
        select(Researcher).where(Researcher.semantic_scholar_id == s2_id)
    ).scalar_one_or_none()
    if by_s2:
        return False

    # Fall back to exact-name match. Collisions remain a known v0 limitation.
    target = db.execute(select(Researcher).where(Researcher.name_en == name)).scalar_one_or_none()
    if not target:
        return False

    changed = False
    if not target.semantic_scholar_id:
        target.semantic_scholar_id = s2_id
        changed = True

    affs = ad.get("affiliations") or []
    if affs and not target.bio:
        target.bio = f"{affs[0]} · (per Semantic Scholar)"
        changed = True

    homepage = ad.get("homepage")
    if homepage and not target.homepage_url:
        target.homepage_url = homepage
        changed = True

    # Lift confidence from "low" once we have an S2-anchored identity.
    if changed and target.confidence_level == "low":
        target.confidence_level = "medium"

    return changed
