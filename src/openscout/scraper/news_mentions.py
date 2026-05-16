"""News-mention scraper.

For each paper in our DB with an arxiv_id, and each high-confidence anchor
researcher, scan recent AI/tech news for mentions. A hit means the work has
crossed into public attention — that's a strong buzz signal for ranking.

Sources:
  - 36kr AI HTML feed         (https://36kr.com/information/AI)
  - The Decoder RSS           (https://the-decoder.com/feed/)
  - VentureBeat AI RSS        (https://venturebeat.com/category/ai/feed/)
  - TechCrunch AI RSS         (https://techcrunch.com/category/artificial-intelligence/feed/)

For each article we pull {title, url, summary, published} and scan the
concatenated text for:

  1. Any arxiv_id we have in the DB (matches `\\d{4}\\.\\d{4,5}`) — strongest
     signal; bumps `paper.buzz_score` by +0.5 (capped at 5.0).
  2. Any high/medium-confidence anchor researcher's full English name —
     weaker signal but still worth a Signal row.

Hits are stored as `Signal` rows with `type="news_mention"`. Dedup is keyed on
a hash of the article URL stored in `Signal.source` (per researcher_id) so a
re-run of the same day's feed won't double-write.

This is polite: 1s sleep between feed requests, a real User-Agent header, and
all failures degrade gracefully (a 404 / parse error on one source returns
zero hits for that source rather than killing the whole scan).
"""

import hashlib
import re
import time
from datetime import UTC, datetime, timedelta

import feedparser
import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher, Signal

USER_AGENT = "OpenScout/0.7 (+https://github.com/Chen17-sq/OpenScout)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Order matters only for logs / "first hit wins" — all are scanned.
RSS_FEEDS: list[tuple[str, str]] = [
    ("the_decoder", "https://the-decoder.com/feed/"),
    ("venturebeat_ai", "https://venturebeat.com/category/ai/feed/"),
    ("techcrunch_ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
]

# 36kr is HTML, not RSS — scraped separately.
KR36_URL = "https://36kr.com/information/AI"

# Matches `2401.12345` or `2401.1234` — the standard arXiv id post-2007.
ARXIV_ID_RE = re.compile(r"\b(\d{4}\.\d{4,5})\b")

# Cap on per-paper buzz bump so a few news hits don't blow past the score range.
BUZZ_CAP = 5.0
BUZZ_BUMP = 0.5


def _url_hash(url: str) -> str:
    """Short stable hash for URL dedup — fits in Signal.source (varchar 64)."""
    return hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:32]


def _strip_html(text: str | None) -> str:
    """RSS summaries often carry HTML; flatten to plain text for matching."""
    if not text:
        return ""
    try:
        return HTMLParser(text).text(separator=" ").strip()
    except Exception:
        # Belt-and-suspenders: regex out tags if selectolax chokes
        return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_rss(client: httpx.Client, source: str, url: str, since: datetime) -> list[dict]:
    """Fetch an RSS feed and return a list of {title, url, summary, published}.

    Articles older than `since` are dropped. On any HTTP / parse error, returns
    an empty list — caller treats this as "source had nothing today."
    """
    try:
        r = client.get(url, timeout=15.0)
        if r.status_code != 200:
            return []
        parsed = feedparser.parse(r.content)
    except Exception:
        return []

    out: list[dict] = []
    for entry in parsed.entries or []:
        link = entry.get("link") or ""
        title = (entry.get("title") or "").strip()
        if not link or not title:
            continue

        summary = entry.get("summary") or entry.get("description") or ""
        summary = _strip_html(summary)

        # Time parsing — feedparser puts a struct_time in `*_parsed`; not all
        # entries have it (e.g. broken feeds), so fall back to "now" and let
        # the caller decide whether to keep undated entries.
        published_dt: datetime | None = None
        for key in ("published_parsed", "updated_parsed"):
            tt = entry.get(key)
            if tt:
                try:
                    published_dt = datetime(*tt[:6], tzinfo=UTC)
                    break
                except Exception:
                    continue
        if published_dt and published_dt < since:
            continue

        out.append(
            {
                "source": source,
                "url": link,
                "title": title,
                "summary": summary,
                "published": published_dt.isoformat() if published_dt else None,
            }
        )
    return out


def _parse_36kr(client: httpx.Client, since: datetime) -> list[dict]:
    """Scrape 36kr's AI listing page for article cards.

    36kr is a JS-heavy site; the listing page does ship server-rendered
    article links inside <a> tags, which is enough to capture {title, url}.
    Summaries are typically empty (the cards' description text is short),
    but we extract the visible blurb when present.
    """
    try:
        r = client.get(KR36_URL, timeout=20.0)
        if r.status_code != 200:
            return []
        tree = HTMLParser(r.text)
    except Exception:
        return []

    # Article hrefs on 36kr look like /p/<numeric_id>. The page renders each
    # card with MULTIPLE anchors to the same /p/ URL (image-link first with
    # empty text, then title-link with the headline). Walk every anchor and
    # keep the longest text seen per URL.
    titles_by_url: dict[str, str] = {}
    for a in tree.css("a"):
        href = a.attributes.get("href", "") or ""
        if not href.startswith("/p/"):
            continue
        url = "https://36kr.com" + href.split("?")[0]
        title = a.text(strip=True)
        if not title:
            continue
        if len(title) > len(titles_by_url.get(url, "")):
            titles_by_url[url] = title

    out: list[dict] = []
    for url, title in titles_by_url.items():
        if len(title) < 6:
            # Icon-only / "more" anchors — skip.
            continue
        out.append(
            {
                "source": "36kr_ai",
                "url": url,
                "title": title,
                # Summary intentionally empty: the listing page doesn't carry
                # excerpt text inside the anchor reliably. Title-only matching
                # is still useful for arxiv id (rare in title) and researcher
                # name mentions.
                "summary": "",
                # No timestamp from the listing page; let the freshness filter
                # accept these (caller will skip the since-filter for entries
                # without `published`).
                "published": None,
            }
        )
    # 36kr puts hundreds of duplicate cards across the page; cap at first 80
    # unique article URLs we see.
    return out[:80]


def _build_anchor_index() -> tuple[dict[str, int], dict[str, int]]:
    """Build two lookup dicts from the DB for fast in-memory matching.

    Returns:
      arxiv_to_paper_id: {"2401.12345": 17, ...} for every paper that has an
        arxiv_id (and isn't a synthetic 'or-…' OpenReview id).
      name_to_researcher_id: {"Yoshua Bengio": 3, ...} keyed on the lowercase
        full English name, restricted to high/medium-confidence anchors so we
        don't generate noise for the auto-discovered tail.
    """
    arxiv_to_paper_id: dict[str, int] = {}
    name_to_researcher_id: dict[str, int] = {}

    with session_scope() as db:
        papers = db.execute(
            select(Paper.id, Paper.arxiv_id).where(
                Paper.arxiv_id.is_not(None),
                Paper.arxiv_id.notlike("or-%"),
            )
        ).all()
        for pid, aid in papers:
            if aid and ARXIV_ID_RE.match(aid):
                arxiv_to_paper_id[aid] = pid

        anchors = db.execute(
            select(Researcher.id, Researcher.name_en).where(
                Researcher.confidence_level.in_(["high", "medium"]),
                Researcher.name_en.is_not(None),
            )
        ).all()
        for rid, name in anchors:
            name = (name or "").strip()
            # Skip single-token names (e.g. "Sora") and very short ones — too
            # prone to false-positive substring hits in news prose.
            if not name or len(name) < 6 or " " not in name:
                continue
            name_to_researcher_id[name.lower()] = rid

    return arxiv_to_paper_id, name_to_researcher_id


def scan_news_mentions(days: int = 14, limit_papers: int = 500) -> dict[str, int]:
    """Scan recent AI/tech news for mentions of papers / anchor researchers.

    Args:
        days: how far back to look; entries older than this are dropped (only
            applied when the feed provides a publish date).
        limit_papers: cap on the arxiv_id index size to keep substring scans
            bounded on very large DBs. Most recent papers (by `first_seen_at`)
            are preferred.

    Returns:
        {"feeds_fetched": N, "articles": A, "paper_hits": P,
         "researcher_hits": R, "errors": E}
    """
    counts = {
        "feeds_fetched": 0,
        "articles": 0,
        "paper_hits": 0,
        "researcher_hits": 0,
        "errors": 0,
    }

    # ── 1. Build in-memory indexes (one DB session, cheap) ─────────────────
    arxiv_to_paper_id, name_to_researcher_id = _build_anchor_index()

    # Cap arxiv_id scanning to most-recent N papers to bound regex work per
    # article. Refetch ordered by recency.
    if len(arxiv_to_paper_id) > limit_papers:
        with session_scope() as db:
            recent = db.execute(
                select(Paper.id, Paper.arxiv_id)
                .where(
                    Paper.arxiv_id.is_not(None),
                    Paper.arxiv_id.notlike("or-%"),
                )
                .order_by(desc(Paper.first_seen_at))
                .limit(limit_papers)
            ).all()
        arxiv_to_paper_id = {aid: pid for pid, aid in recent if aid and ARXIV_ID_RE.match(aid)}

    if not arxiv_to_paper_id and not name_to_researcher_id:
        # Empty DB — nothing to match against. Bail before any HTTP traffic.
        return counts

    # ── 2. Fetch all feeds ─────────────────────────────────────────────────
    since = datetime.now(UTC) - timedelta(days=days)
    articles: list[dict] = []
    client = httpx.Client(headers=HEADERS, follow_redirects=True)
    try:
        # 36kr first (HTML), then the RSS feeds with a polite sleep between.
        try:
            kr_articles = _parse_36kr(client, since)
            counts["feeds_fetched"] += 1
            articles.extend(kr_articles)
        except Exception:
            counts["errors"] += 1
        time.sleep(1.0)

        for source, url in RSS_FEEDS:
            try:
                items = _parse_rss(client, source, url, since)
                counts["feeds_fetched"] += 1
                articles.extend(items)
            except Exception:
                counts["errors"] += 1
            time.sleep(1.0)
    finally:
        client.close()

    counts["articles"] = len(articles)
    if not articles:
        return counts

    # ── 3. Scan + write hits ───────────────────────────────────────────────
    with session_scope() as db:
        for art in articles:
            blob = " ".join([art["title"], art.get("summary") or ""])
            blob_lower = blob.lower()
            url_hash = _url_hash(art["url"])

            # 3a. arxiv_id hits — strongest signal; bump buzz_score on the paper.
            matched_arxiv: set[str] = set()
            for m in ARXIV_ID_RE.finditer(blob):
                aid = m.group(1)
                if aid in arxiv_to_paper_id:
                    matched_arxiv.add(aid)
            for aid in matched_arxiv:
                paper_id = arxiv_to_paper_id[aid]
                paper = db.get(Paper, paper_id)
                if not paper:
                    continue
                paper.buzz_score = min(BUZZ_CAP, (paper.buzz_score or 0.0) + BUZZ_BUMP)

                # Attribute the Signal to the paper's first author so the row
                # shows up in that researcher's activity timeline. Signal
                # rows require a non-null researcher_id (FK), so a paper with
                # no linked authors gets the buzz bump but no Signal.
                first_author_id = db.execute(
                    select(PaperAuthor.researcher_id)
                    .where(PaperAuthor.paper_id == paper_id)
                    .order_by(PaperAuthor.position)
                    .limit(1)
                ).scalar_one_or_none()
                if not first_author_id:
                    # Paper has no linked authors — record against a synthetic
                    # 0 id would violate FK. Skip the Signal but keep the buzz
                    # bump (which is the more important effect).
                    counts["paper_hits"] += 1
                    continue

                # Dedup: (researcher_id, url_hash) is unique enough.
                exists = db.execute(
                    select(Signal.id).where(
                        Signal.researcher_id == first_author_id,
                        Signal.type == "news_mention",
                        Signal.source == url_hash,
                    )
                ).scalar_one_or_none()
                if exists:
                    continue

                db.add(
                    Signal(
                        researcher_id=first_author_id,
                        type="news_mention",
                        payload={
                            "source": art["source"],
                            "url": art["url"],
                            "title": art["title"][:300],
                            "snippet": (art.get("summary") or "")[:500],
                            "matched_via": "arxiv_id",
                            "arxiv_id": aid,
                            "paper_id": paper_id,
                            "published": art.get("published"),
                        },
                        source=url_hash,
                        occurred_at=datetime.now(UTC),
                    )
                )
                counts["paper_hits"] += 1

            # 3b. Researcher-name hits — only against anchor names to keep
            # the false-positive rate low. Skip if we already matched an
            # arxiv_id from this article AND that paper has the same researcher
            # as an author (avoids double-counting the same news story).
            matched_authors_via_arxiv: set[int] = set()
            for aid in matched_arxiv:
                pid = arxiv_to_paper_id[aid]
                ar = (
                    db.execute(select(PaperAuthor.researcher_id).where(PaperAuthor.paper_id == pid))
                    .scalars()
                    .all()
                )
                matched_authors_via_arxiv.update(ar)

            for name_lower, rid in name_to_researcher_id.items():
                if rid in matched_authors_via_arxiv:
                    continue
                if name_lower not in blob_lower:
                    continue

                # Dedup: (researcher_id, url_hash) again.
                exists = db.execute(
                    select(Signal.id).where(
                        Signal.researcher_id == rid,
                        Signal.type == "news_mention",
                        Signal.source == url_hash,
                    )
                ).scalar_one_or_none()
                if exists:
                    continue

                db.add(
                    Signal(
                        researcher_id=rid,
                        type="news_mention",
                        payload={
                            "source": art["source"],
                            "url": art["url"],
                            "title": art["title"][:300],
                            "snippet": (art.get("summary") or "")[:500],
                            "matched_via": "name",
                            "published": art.get("published"),
                        },
                        source=url_hash,
                        occurred_at=datetime.now(UTC),
                    )
                )
                counts["researcher_hits"] += 1

    return counts
