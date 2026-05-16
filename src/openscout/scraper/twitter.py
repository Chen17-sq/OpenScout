"""Twitter/X scraper via Nitter — bio + recent research-relevant tweets.

X killed free API access in 2023. Two paths remain for unauthenticated read:

  1. Nitter — community-run web frontends that re-render twitter.com without
     login. HTML scraping, fragile, instance churn. We try a list of mirrors
     and fall over on failure.
  2. twscrape — Python lib that drives logged-in accounts. Requires you to
     supply cookies, gets you banned eventually, and feels closer to ToS
     violation. Skipped for now.

For each anchor researcher with `twitter_handle` set (and no recent twitter
Signal in the last 30 days), pull the bio + last few tweets, keep tweets that
mention research-y keywords, and write a Signal of type='twitter_recent'.

Behaviour is best-effort. When every Nitter instance returns 4xx/5xx/timeout
we increment `errors` and keep going. The function should never crash even if
the entire Nitter ecosystem is down — Chinese-VC users see "0 hits" rather
than a stack trace in the daily report.
"""

import re
import time
from datetime import UTC, datetime, timedelta

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Researcher, Signal

# Rotating list — pick whichever responds. Nitter is a moving target;
# update this from https://github.com/zedeus/nitter/wiki/Instances when
# the list rots. Order matters: try the more reliable ones first.
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.cz",
    "https://nitter.unixfox.eu",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Research-y keyword filter for tweet content. We want to surface the
# "paper drop / model release / talk" tweets and discard the personal /
# political noise. Case-insensitive substring match.
RESEARCH_KEYWORDS = (
    "research",
    "paper",
    "preprint",
    "arxiv",
    "model",
    "models",
    "train",
    "training",
    "fine-tune",
    "finetune",
    "benchmark",
    "results",
    "dataset",
    "neurips",
    "iclr",
    "icml",
    "cvpr",
    "acl",
    "emnlp",
    "robot",
    "embodied",
    "policy",
    "diffusion",
    "transformer",
    "rl ",
    "reinforcement",
    "agent",
    "agents",
    "lab",
    "code",
    "github.com",
    "huggingface.co",
    "openreview",
    "thesis",
    "phd",
    "postdoc",
    "release",
    "released",
    "open-source",
    "open source",
    "talk",
    "keynote",
    "workshop",
)


def _clean_handle(raw: str) -> str:
    """Normalize a twitter handle — strip URL, @, whitespace."""
    s = (raw or "").strip()
    s = re.sub(r"^https?://(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/", "", s, flags=re.I)
    s = s.strip("/@ ").split("?")[0].split("/")[0]
    return s


def _is_research_relevant(text: str) -> bool:
    low = (text or "").lower()
    return any(kw in low for kw in RESEARCH_KEYWORDS)


def _fetch_profile_html(client: httpx.Client, handle: str) -> str | None:
    """Try each Nitter instance until one returns a 200."""
    for base in NITTER_INSTANCES:
        url = f"{base}/{handle}"
        try:
            r = client.get(url, timeout=15.0, follow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        ctype = r.headers.get("content-type", "")
        if "text/html" not in ctype:
            continue
        # Nitter renders an error page (HTTP 200) when the account doesn't
        # exist or the instance is rate-limited. Sniff the body.
        body = r.text
        if "User not found" in body or "Instance has been rate limited" in body:
            continue
        if "</html>" not in body.lower():
            continue
        return body
    return None


def _parse_profile(html: str) -> tuple[str | None, list[dict]]:
    """Extract (bio, tweets) from a Nitter profile page.

    Tweets is a list of dicts: {text, created_at (ISO str or None), url}.
    """
    tree = HTMLParser(html)

    bio = None
    bio_node = tree.css_first("div.profile-bio")
    if bio_node is not None:
        txt = (bio_node.text(separator=" ") or "").strip()
        bio = re.sub(r"\s+", " ", txt) or None

    tweets: list[dict] = []
    # Nitter renders each tweet as `<div class="timeline-item">`. The body
    # text lives in `.tweet-content`, the canonical link in `.tweet-link`,
    # and the timestamp in `.tweet-date a[title]` (title attr is a UTC
    # string like "Mar 5, 2026 · 4:17 PM UTC").
    for node in tree.css("div.timeline-item"):
        # Skip pinned-only / retweet-only rows? Nitter marks retweets with
        # a "retweet-header" — we still keep them; a retweet is also signal.
        content_node = node.css_first("div.tweet-content")
        if content_node is None:
            continue
        text = (content_node.text(separator=" ") or "").strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue

        link_node = node.css_first("a.tweet-link")
        url = None
        if link_node is not None:
            href = link_node.attributes.get("href") or ""
            # href like /<handle>/status/<id>#m — strip the fragment, build x.com URL
            m = re.search(r"/([^/]+)/status/(\d+)", href)
            if m:
                url = f"https://x.com/{m.group(1)}/status/{m.group(2)}"

        date_node = node.css_first("span.tweet-date a")
        created_at = None
        if date_node is not None:
            title = date_node.attributes.get("title")
            if title:
                # Try a couple of formats. Nitter has churned the format
                # over time. Fall through on any parse error.
                for fmt in (
                    "%b %d, %Y · %I:%M %p %Z",
                    "%b %d, %Y · %H:%M %Z",
                    "%d %b %Y, %H:%M:%S %Z",
                ):
                    try:
                        dt = datetime.strptime(title, fmt)
                        created_at = dt.isoformat()
                        break
                    except Exception:
                        continue

        tweets.append({"text": text, "created_at": created_at, "url": url})

    return bio, tweets


def scrape_twitter(limit: int = 30) -> dict[str, int]:
    """Pull bio + last 5 research-y tweets for each researcher with handle.

    Skips anyone with a twitter Signal already recorded in the last 30 days.
    Returns counts dict — never raises.
    """
    counts = {"attempted": 0, "got_bio": 0, "got_tweets": 0, "errors": 0}

    cutoff = datetime.now(UTC) - timedelta(days=30)

    client = httpx.Client(headers=HEADERS, timeout=15.0)
    try:
        with session_scope() as db:
            # Researchers with a twitter handle, ordered newest-first so a
            # daily run progresses through fresh anchors before old ones.
            candidates = list(
                db.execute(
                    select(Researcher)
                    .where(Researcher.twitter_handle.is_not(None))
                    .order_by(desc(Researcher.first_seen_at))
                    .limit(limit * 3)  # over-fetch; we'll skip recent ones below
                )
                .scalars()
                .all()
            )

            picked = 0
            for r in candidates:
                if picked >= limit:
                    break
                handle = _clean_handle(r.twitter_handle or "")
                if not handle:
                    continue

                # Skip if we already scraped this person recently. The
                # Signal table is our cache.
                recent = db.execute(
                    select(Signal)
                    .where(
                        Signal.researcher_id == r.id,
                        Signal.type == "twitter_recent",
                        Signal.detected_at >= cutoff,
                    )
                    .limit(1)
                ).first()
                if recent:
                    continue

                picked += 1
                counts["attempted"] += 1

                html = _fetch_profile_html(client, handle)
                if html is None:
                    counts["errors"] += 1
                    continue

                try:
                    bio, all_tweets = _parse_profile(html)
                except Exception:
                    counts["errors"] += 1
                    continue

                # Fill bio if missing (don't overwrite user-curated text)
                if bio and not r.bio:
                    r.bio = bio[:2000]
                    counts["got_bio"] += 1

                relevant = [t for t in all_tweets if _is_research_relevant(t["text"])][:5]

                if relevant:
                    counts["got_tweets"] += 1

                # Write the Signal regardless of whether we filtered any
                # tweets — recording the visit prevents re-scraping on the
                # next run, and the bio alone is useful provenance.
                db.add(
                    Signal(
                        researcher_id=r.id,
                        type="twitter_recent",
                        payload={
                            "handle": handle,
                            "bio": bio,
                            "tweets": relevant,
                        },
                        occurred_at=datetime.now(UTC),
                        source=f"nitter:{handle}",
                    )
                )

                # Be polite — Nitter mirrors are volunteer-run.
                time.sleep(1.5)
    finally:
        client.close()

    return counts
