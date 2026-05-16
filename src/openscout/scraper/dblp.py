"""DBLP integration — clean author records + co-author network.

DBLP is the canonical CS bibliography. Their API returns JSON (XML available).
Two endpoints we use:

  Author search:   dblp.org/search/author/api?q=<name>&format=json
  Author publications: dblp.org/pid/<PID>.json

Why DBLP on top of OpenAlex:
  1. Author PIDs are stable + community-curated (less name collision)
  2. Returns affiliations + their date ranges (advisor cohort detection)
  3. Co-author network on the publication record itself (better lineage)

We don't replace OpenAlex — we cross-reference. For each researcher we already
have, attempt to find their DBLP PID and store it on `Researcher.arxiv_author_id`
(field is generic-named; we reuse it for DBLP since we lack a dedicated column).
"""

import re
import time

import httpx
from sqlalchemy import select

from ..db import session_scope
from ..models import Researcher

DBLP_BASE = "https://dblp.org"
HEADERS = {
    "User-Agent": "OpenScout/0.7 (+https://github.com/Chen17-sq/OpenScout)",
    "Accept": "application/json",
}


def _normalize_name(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _search_author(client: httpx.Client, name: str) -> dict | None:
    """Search DBLP for the most likely author match."""
    try:
        r = client.get(
            f"{DBLP_BASE}/search/author/api",
            params={"q": name, "format": "json", "h": "5"},
            timeout=15.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        hits = (data.get("result", {}).get("hits", {}) or {}).get("hit") or []
        if not hits:
            return None

        target = _normalize_name(name)
        # Exact name match preferred
        for h in hits:
            info = h.get("info") or {}
            if _normalize_name(info.get("author") or "") == target:
                return info
        # Otherwise top hit
        return hits[0].get("info")
    except Exception:
        return None


def _pid_from_url(url: str) -> str | None:
    # URLs look like https://dblp.org/pid/49/4604.html → PID = "49/4604"
    m = re.search(r"/pid/([\w/]+?)(?:\.html)?$", url)
    return m.group(1) if m else None


def enrich_anchors(limit: int = 30, sleep_between: float = 0.6) -> dict[str, int]:
    """Find DBLP PID for anchor researchers + cache top affiliations."""
    counts = {"attempted": 0, "found_pid": 0, "errors": 0}

    client = httpx.Client(headers=HEADERS, follow_redirects=True)
    try:
        with session_scope() as db:
            rs = list(
                db.execute(
                    select(Researcher)
                    .where(
                        Researcher.confidence_level.in_(["high", "medium"]),
                        Researcher.arxiv_author_id.is_(None),
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )

            for r in rs:
                counts["attempted"] += 1
                info = _search_author(client, r.name_en)
                time.sleep(sleep_between)
                if not info:
                    continue
                url = info.get("url") or ""
                pid = _pid_from_url(url)
                if pid:
                    # Reuse arxiv_author_id field for DBLP PID (prefix to disambiguate)
                    r.arxiv_author_id = f"dblp:{pid}"
                    counts["found_pid"] += 1
    finally:
        client.close()
    return counts
