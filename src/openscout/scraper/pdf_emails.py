"""Extract emails from arXiv PDF first pages.

We don't try to match emails to specific authors — that requires either
position-mapping the email order to the byline (fragile) or LLM-assisted
parsing (slow). Instead we collect ALL emails on the first page and store
them on `paper.author_emails`. The frontend surfaces them as "possible
contacts" so the user can manually verify and copy to a Researcher record.

Polite to arXiv: download with a UA, 1-2s sleep between PDFs.
"""

import io
import re
import time

import httpx
from pypdf import PdfReader
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.UNICODE,
)
# Sloppy "obfuscated" email patterns commonly seen in PDFs:
#   "name [at] uni [dot] edu" or "name@uni dot edu"
OBFUSCATED_RE = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*[\[\(]?\s*(?:at|@)\s*[\]\)]?\s*([a-zA-Z0-9\-]+)"
    r"(?:\s*[\[\(]?\s*(?:dot|\.)\s*[\]\)]?\s*([a-zA-Z0-9.\-]+))+",
    re.IGNORECASE,
)


def _fetch_pdf(client: httpx.Client, url: str) -> bytes | None:
    try:
        r = client.get(url, timeout=20.0, follow_redirects=True)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"):
            return r.content
        return None
    except Exception:
        return None


def _first_page_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if not reader.pages:
            return ""
        return reader.pages[0].extract_text() or ""
    except Exception:
        return ""


def _extract_emails(text: str) -> list[str]:
    if not text:
        return []
    found = set()
    for m in EMAIL_RE.finditer(text):
        e = m.group(0).rstrip(".,;)").lower()
        # filter common noise
        if e.endswith(".png") or e.endswith(".pdf") or "..." in e:
            continue
        # drop emails that are clearly placeholder
        if e in {"example@example.com", "info@example.com"}:
            continue
        found.add(e)
    return sorted(found)


def extract_paper_emails(limit: int = 30, sleep_between: float = 1.5) -> dict[str, int]:
    """Download recent papers without `author_emails` set and extract emails from page 1."""
    counts = {"attempted": 0, "with_emails": 0, "no_pdf": 0, "errors": 0}
    client = httpx.Client(
        headers={"User-Agent": "OpenScout/0.2 (+https://github.com/Chen17-sq/OpenScout)"},
        follow_redirects=True,
    )
    with session_scope() as db:
        papers = list(
            db.execute(
                select(Paper)
                .where(Paper.author_emails.is_(None), Paper.pdf_url.is_not(None))
                .order_by(desc(Paper.first_seen_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for paper in papers:
            counts["attempted"] += 1
            pdf_bytes = _fetch_pdf(client, paper.pdf_url)
            if not pdf_bytes:
                counts["no_pdf"] += 1
                paper.author_emails = []  # mark attempted so we don't loop
                continue
            try:
                text = _first_page_text(pdf_bytes)
                emails = _extract_emails(text)
                paper.author_emails = emails
                if emails:
                    counts["with_emails"] += 1
            except Exception:
                counts["errors"] += 1
                paper.author_emails = []
            time.sleep(sleep_between)
    client.close()
    return counts
