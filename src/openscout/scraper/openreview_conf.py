"""OpenReview conference accepted-papers ingester.

OpenReview hosts ICLR / NeurIPS / ICML / CoLM / TMLR submissions and accept
decisions. Their `notes` API returns paginated submissions.

For each accepted paper:
  - Upsert Paper (use first arxiv ref if present, else OR note id)
  - Link authors (best-effort by name)
  - Set venue to e.g. "NeurIPS 2024 (oral)"
  - Boost buzz_score for oral / spotlight

Tag papers with the venue prefix so the brief can highlight them.
"""

import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher

OR_BASE = "https://api2.openreview.net"

# (venue_id, label, max_papers)
KNOWN_VENUES = [
    ("ICLR.cc/2025/Conference", "ICLR 2025", 200),
    ("NeurIPS.cc/2024/Conference", "NeurIPS 2024", 200),
    ("ICML.cc/2024/Conference", "ICML 2024", 200),
]


def _slug_from_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


def _ensure_researcher(db, name: str) -> Researcher:
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


def _is_accepted(note: dict) -> tuple[bool, str | None]:
    """Inspect the note for accept/reject status. Returns (accepted, tier_label_or_none)."""
    content = note.get("content") or {}
    venue_value = (content.get("venue") or {}).get("value") if isinstance(content.get("venue"), dict) else content.get("venue")
    if not venue_value:
        return False, None
    venue_value = str(venue_value)
    if "Reject" in venue_value or "Withdraw" in venue_value:
        return False, None
    if any(tier in venue_value for tier in ("Oral", "Spotlight", "Outstanding", "Best Paper")):
        for tier in ("Best Paper", "Outstanding", "Oral", "Spotlight"):
            if tier in venue_value:
                return True, tier.lower().replace(" ", "_")
    if any(tier in venue_value for tier in ("Poster", "Accept")):
        return True, "poster"
    return False, None


def fetch_venue(venue_id: str, label: str, max_papers: int = 200) -> dict[str, int]:
    counts = {"fetched": 0, "added": 0, "updated": 0, "errors": 0, "tiered": 0}

    client = httpx.Client(timeout=30.0)
    try:
        offset = 0
        while offset < max_papers:
            params = {
                "invitation": f"{venue_id}/-/Submission",
                "limit": min(50, max_papers - offset),
                "offset": offset,
                "details": "directReplies",
            }
            try:
                r = client.get(f"{OR_BASE}/notes", params=params)
            except Exception:
                counts["errors"] += 1
                break
            if r.status_code != 200:
                # OpenReview API may not expose accepted notes for the same invitation
                break
            data = r.json() or {}
            notes = data.get("notes") or []
            if not notes:
                break

            with session_scope() as db:
                for note in notes:
                    counts["fetched"] += 1
                    accepted, tier = _is_accepted(note)
                    if not accepted:
                        continue
                    content = note.get("content") or {}

                    # Extract paper metadata
                    def _v(key: str) -> str | None:
                        val = content.get(key)
                        if isinstance(val, dict):
                            return val.get("value")
                        return val

                    title = (_v("title") or "[untitled]").strip()
                    abstract = (_v("abstract") or "").strip() or None
                    authors_field = _v("authors") or []
                    if not isinstance(authors_field, list):
                        authors_field = []

                    # Look for an arxiv reference in title or abstract — rare but try
                    arxiv_match = re.search(r"arXiv:(\d{4}\.\d{4,5})", " ".join([title, abstract or ""]))
                    arxiv_id = arxiv_match.group(1) if arxiv_match else None

                    or_id = note.get("id")

                    # Upsert by openalex_id-style "or:NOTE_ID" (we don't have a separate column;
                    # reuse arxiv_id field with prefix to avoid collisions when arxiv_id is null)
                    existing = None
                    if arxiv_id:
                        existing = db.execute(
                            select(Paper).where(Paper.arxiv_id == arxiv_id)
                        ).scalar_one_or_none()
                    if not existing:
                        synthetic_id = f"or-{or_id[-12:]}"
                        existing = db.execute(
                            select(Paper).where(Paper.arxiv_id == synthetic_id)
                        ).scalar_one_or_none()

                    venue_label = f"{label} ({tier})" if tier else label
                    if existing:
                        existing.venue = venue_label
                        if tier in ("oral", "spotlight", "best_paper", "outstanding"):
                            existing.buzz_score = max(existing.buzz_score or 0.0, 1.5)
                            counts["tiered"] += 1
                        counts["updated"] += 1
                        continue

                    paper = Paper(
                        arxiv_id=arxiv_id or f"or-{or_id[-12:]}",
                        title=title[:1000],
                        abstract=abstract,
                        venue=venue_label,
                        buzz_score=1.5 if tier in ("oral", "spotlight", "best_paper", "outstanding") else 1.0,
                        first_seen_at=datetime.now(timezone.utc),
                    )
                    db.add(paper)
                    db.flush()

                    for pos, aname in enumerate(authors_field[:25], start=1):
                        if not aname:
                            continue
                        r_obj = _ensure_researcher(db, str(aname))
                        db.add(
                            PaperAuthor(paper_id=paper.id, researcher_id=r_obj.id, position=pos)
                        )
                    counts["added"] += 1
                    if tier in ("oral", "spotlight", "best_paper", "outstanding"):
                        counts["tiered"] += 1

            offset += len(notes)
            time.sleep(0.4)
    finally:
        client.close()
    return counts


def fetch_all() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for venue_id, label, n in KNOWN_VENUES:
        out[label] = fetch_venue(venue_id, label, max_papers=n)
        time.sleep(1.5)
    return out
