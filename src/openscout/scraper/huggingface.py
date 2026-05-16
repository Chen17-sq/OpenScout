"""HuggingFace Daily Papers ingestion.

HF maintains a curated daily list at https://huggingface.co/papers — papers
that the community/upload-bot flagged as trending. They expose a JSON-ish API.

We use it as a high-signal source: papers featured here are more likely to be
"hot" than a random arXiv paper. The buzz_score gets a bump.

Public, no auth needed. Polite: one request per minute is plenty.
"""

import re
import time
from datetime import date as Date
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher

HF_API = "https://huggingface.co/api/daily_papers"


def _slug_from_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


def _ensure_researcher(db, name: str) -> Researcher:
    """Find or create a Researcher row by exact name match."""
    name = (name or "").strip()
    if not name:
        name = "Unknown"
    existing = db.execute(
        select(Researcher).where(Researcher.name_en == name)
    ).scalar_one_or_none()
    if existing:
        return existing

    base = _slug_from_name(name)
    candidate = base
    n = 1
    while db.execute(select(Researcher).where(Researcher.slug == candidate)).first():
        n += 1
        candidate = f"{base}-{n}"
    r = Researcher(slug=candidate, name_en=name, confidence_level="low")
    db.add(r)
    db.flush()
    return r


def fetch_hf_daily(limit: int = 30) -> dict[str, int]:
    """Pull today's HF Daily Papers and ensure they exist in our DB.

    For papers with an arxiv_id we already have, bump their buzz_score.
    For new papers, insert + link authors + tag as 'hf_featured'.
    """
    counts = {"fetched": 0, "added": 0, "updated": 0, "errors": 0}

    client = httpx.Client(
        headers={"User-Agent": "OpenScout/0.5 (+https://github.com/Chen17-sq/OpenScout)"},
        timeout=20.0,
    )
    try:
        r = client.get(HF_API)
        if r.status_code != 200:
            counts["errors"] = 1
            return counts
        data = r.json() or []
    except Exception:
        counts["errors"] = 1
        return counts
    finally:
        client.close()

    if not isinstance(data, list):
        return counts

    with session_scope() as db:
        for entry in data[:limit]:
            counts["fetched"] += 1
            paper_meta = entry.get("paper") or entry
            arxiv_id = paper_meta.get("id") or paper_meta.get("arxivId")
            if not arxiv_id:
                continue
            arxiv_id = re.sub(r"v\d+$", "", str(arxiv_id))

            existing = db.execute(
                select(Paper).where(Paper.arxiv_id == arxiv_id)
            ).scalar_one_or_none()

            title = paper_meta.get("title", "[untitled]").strip()
            abstract = (paper_meta.get("summary") or paper_meta.get("abstract") or "").strip()
            upvotes = int(paper_meta.get("upvotes") or 0)

            if existing:
                # Boost buzz_score; HF-featured = a strong relevance signal
                existing.buzz_score = max(existing.buzz_score or 0.0, 1.0 + (upvotes / 50.0))
                counts["updated"] += 1
                continue

            paper = Paper(
                arxiv_id=arxiv_id,
                title=title[:1000],
                abstract=abstract or None,
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                venue="arXiv (HF featured)",
                buzz_score=1.0 + (upvotes / 50.0),
                first_seen_at=datetime.now(timezone.utc),
            )
            db.add(paper)
            db.flush()

            # Authors — HF uses {name, hidden, ...}
            authors = paper_meta.get("authors") or []
            for pos, a in enumerate(authors[:30], start=1):
                aname = a.get("name") if isinstance(a, dict) else str(a)
                if not aname:
                    continue
                r_obj = _ensure_researcher(db, aname)
                db.add(PaperAuthor(paper_id=paper.id, researcher_id=r_obj.id, position=pos))

            counts["added"] += 1

        time.sleep(0.5)

    return counts
