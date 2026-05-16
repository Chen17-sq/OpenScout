"""Backfill paper.code_url from regex scan of abstract + title.

arXiv abstracts often mention "code at https://github.com/..." Many do not.
For papers without code_url, scan abstract+title for GitHub-flavored URLs.
After this, `openscout github-stars` can fetch star counts.
"""

import re

from sqlalchemy import select

from ..db import session_scope
from ..models import Paper

# Matches github.com/<owner>/<repo> in various forms (with trailing punctuation)
GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([\w.\-]{1,40})/([\w.\-]{1,40})",
    re.IGNORECASE,
)


def _clean(owner: str, repo: str) -> tuple[str, str] | None:
    repo = repo.rstrip(".,;:)").rstrip("/")
    repo = re.sub(r"\.git$", "", repo)
    if owner.lower() in {"static", "raw", "search", "trending", "topics", "marketplace"}:
        return None
    if not owner or not repo:
        return None
    if "." in owner and len(owner) < 4:  # like "v.s" — noise
        return None
    return owner, repo


def backfill_code_urls(limit: int = 500) -> dict[str, int]:
    """Scan papers without `code_url` for GitHub URLs in abstract+title."""
    counts = {"checked": 0, "matched": 0}

    with session_scope() as db:
        papers = list(
            db.execute(
                select(Paper)
                .where(Paper.code_url.is_(None))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for p in papers:
            counts["checked"] += 1
            text = " ".join(filter(None, [p.abstract or "", p.title or ""]))
            for m in GITHUB_RE.finditer(text):
                cleaned = _clean(m.group(1), m.group(2))
                if not cleaned:
                    continue
                owner, repo = cleaned
                p.code_url = f"https://github.com/{owner}/{repo}"
                counts["matched"] += 1
                break

    return counts
