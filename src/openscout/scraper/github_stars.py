"""Fetch GitHub stars for papers that have a `code_url` pointing to GitHub.

Uses unauthenticated GitHub REST API (60 req/hour per IP). Add a GITHUB_TOKEN
env var to bump to 5000/hr if you ingest a lot.

Polite no-op when no `code_url` matches GitHub.
"""

import os
import re
import time

import httpx
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper

GITHUB_URL_RE = re.compile(r"github\.com/([\w.\-]+)/([\w.\-]+)", re.IGNORECASE)


def fetch_stars(limit: int = 30, sleep_between: float = 1.0) -> dict:
    """Walk papers with a github code_url and missing github_stars. Update."""
    counts = {"attempted": 0, "updated": 0, "errors": 0}
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    client = httpx.Client(headers=headers, timeout=15.0)

    with session_scope() as db:
        papers = list(
            db.execute(
                select(Paper)
                .where(Paper.code_url.is_not(None), Paper.github_stars.is_(None))
                .order_by(desc(Paper.first_seen_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for p in papers:
            counts["attempted"] += 1
            m = GITHUB_URL_RE.search(p.code_url or "")
            if not m:
                p.github_stars = 0
                continue
            owner, repo = m.group(1), m.group(2).rstrip(".git")
            try:
                r = client.get(f"https://api.github.com/repos/{owner}/{repo}")
                if r.status_code == 200:
                    data = r.json()
                    p.github_stars = int(data.get("stargazers_count") or 0)
                    counts["updated"] += 1
                else:
                    counts["errors"] += 1
                    p.github_stars = 0
            except Exception:
                counts["errors"] += 1
                p.github_stars = 0
            time.sleep(sleep_between)
    client.close()
    return counts
