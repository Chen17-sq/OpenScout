"""alphaXiv buzz scraper.

alphaXiv (https://alphaxiv.org) is Reddit-for-arxiv: a forum where researchers
post comments and upvotes on arxiv papers. They mirror arxiv ids and expose a
simple JSON view.

Lower-tech approach: their paper page HTML has the comment count visible in
JSON-LD or in the React-rendered DOM. We hit `alphaxiv.org/abs/<id>` and look
for embedded JSON.

If alphaXiv changes its frontend or rate-limits, this returns gracefully empty.
The signal is optional — it just bumps buzz_score for papers people are
actively discussing.
"""

import json
import re
import time

import httpx
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper

HEADERS = {
    "User-Agent": "OpenScout/0.7 (+https://github.com/Chen17-sq/OpenScout)",
    "Accept": "text/html,application/json",
}


def _comments_for(client: httpx.Client, arxiv_id: str) -> int | None:
    """Best-effort: fetch alphaXiv page, regex for comment count from page state."""
    try:
        r = client.get(
            f"https://alphaxiv.org/abs/{arxiv_id}",
            timeout=12.0,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return None
        text = r.text
        # Look for inline JSON like "commentCount":N or "numComments":N
        m = re.search(r'"commentCount"\s*:\s*(\d+)', text)
        if m:
            return int(m.group(1))
        m = re.search(r'"numComments"\s*:\s*(\d+)', text)
        if m:
            return int(m.group(1))
        # Try JSON-LD script tags
        for script_match in re.finditer(
            r'<script type="application/ld\+json">(.*?)</script>', text, re.DOTALL
        ):
            try:
                data = json.loads(script_match.group(1))
                if isinstance(data, dict) and "commentCount" in data:
                    return int(data["commentCount"])
            except Exception:
                continue
        return None
    except Exception:
        return None


def boost_from_alphaxiv(limit: int = 30, sleep_between: float = 1.5) -> dict[str, int]:
    """Scan recent papers; if alphaXiv shows discussion, bump buzz_score."""
    counts = {"attempted": 0, "with_comments": 0, "boosted": 0, "errors": 0}

    client = httpx.Client(headers=HEADERS, follow_redirects=True)
    try:
        with session_scope() as db:
            papers = list(
                db.execute(
                    select(Paper)
                    .where(
                        Paper.arxiv_id.is_not(None),
                        Paper.arxiv_id.notlike("or-%"),
                    )
                    .order_by(desc(Paper.first_seen_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            for paper in papers:
                counts["attempted"] += 1
                n = _comments_for(client, paper.arxiv_id)
                time.sleep(sleep_between)
                if n is None:
                    continue
                if n > 0:
                    counts["with_comments"] += 1
                    # Each comment adds 0.05 to buzz_score, cap at +1.0
                    boost = min(1.0, n * 0.05)
                    if (paper.buzz_score or 0) < boost + (paper.buzz_score or 0):
                        paper.buzz_score = (paper.buzz_score or 0) + boost
                        counts["boosted"] += 1
    finally:
        client.close()
    return counts
