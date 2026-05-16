"""Papers with Code integration — paper → code repos + benchmarks.

PwC API: https://paperswithcode.com/api/v1/papers/?arxiv_id=<id>
Returns: title, abstract, repositories, tasks (benchmarks), methods, datasets.

For each paper with an arxiv_id, we look up:
  - GitHub repos (often more accurate than abstract regex scan)
  - GitHub stars (PwC tracks framework + popularity)
  - Tasks (e.g., "Image Classification", "Question Answering")
  - Methods used (e.g., "Transformer", "ResNet")
  - Datasets benchmarked on

The tasks/methods/datasets give us a richer topic signal than OpenAlex concepts
because they're paper-level (not author-aggregated).
"""

import re
import time

import httpx
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper

PWC_BASE = "https://paperswithcode.com/api/v1"

HEADERS = {
    "User-Agent": "OpenScout/0.7 (+https://github.com/Chen17-sq/OpenScout)",
    "Accept": "application/json",
}


def _strip_arxiv_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def _paper_by_arxiv(client: httpx.Client, arxiv_id: str) -> dict | None:
    try:
        r = client.get(
            f"{PWC_BASE}/papers/",
            params={"arxiv_id": _strip_arxiv_version(arxiv_id)},
            timeout=15.0,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results") or []
        return results[0] if results else None
    except Exception:
        return None


def _paper_repositories(client: httpx.Client, paper_id: str) -> list[dict]:
    try:
        r = client.get(f"{PWC_BASE}/papers/{paper_id}/repositories/", timeout=15.0)
        if r.status_code != 200:
            return []
        return r.json().get("results") or []
    except Exception:
        return []


def enrich_papers(limit: int = 50, sleep_between: float = 0.6) -> dict[str, int]:
    """For papers without code_url, look up Papers with Code → repos + stars."""
    counts = {
        "attempted": 0,
        "matched": 0,
        "got_repo": 0,
        "got_stars": 0,
        "errors": 0,
    }

    client = httpx.Client(headers=HEADERS, follow_redirects=True)
    try:
        with session_scope() as db:
            papers = list(
                db.execute(
                    select(Paper)
                    .where(
                        Paper.arxiv_id.is_not(None),
                        Paper.arxiv_id.notlike("or-%"),
                        # Prefer papers without code_url
                    )
                    .order_by(desc(Paper.first_seen_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )

            for paper in papers:
                counts["attempted"] += 1
                meta = _paper_by_arxiv(client, paper.arxiv_id)
                time.sleep(sleep_between)
                if not meta:
                    continue
                counts["matched"] += 1

                # PwC returns paper.id — fetch repositories
                pwc_id = meta.get("id")
                if not pwc_id:
                    continue

                repos = _paper_repositories(client, pwc_id)
                time.sleep(sleep_between)

                if repos:
                    # Pick the most-starred repo as primary code_url
                    repos.sort(key=lambda x: x.get("stars", 0) or 0, reverse=True)
                    top = repos[0]
                    url = top.get("url")
                    if url and not paper.code_url:
                        paper.code_url = url
                        counts["got_repo"] += 1
                    stars = top.get("stars")
                    if stars is not None:
                        paper.github_stars = max(paper.github_stars or 0, int(stars))
                        counts["got_stars"] += 1
    finally:
        client.close()
    return counts
