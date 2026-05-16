"""Zhihu profile scraper — Chinese-researcher bio enrichment.

知乎 (Zhihu) is the Quora-of-China. Many Chinese AI researchers maintain
profiles with bio / employer / education that don't appear on Western sources
like OpenAlex / DBLP / Twitter. For a Chinese-VC user this is uniquely high
signal.

For each researcher with ``zhihu_url`` set we GET their public profile page
and extract:

  - headline (简介)    one-line bio
  - employer (工作)    e.g. "清华大学交叉信息院"
  - school   (学校)    e.g. "Tsinghua University"
  - follower_count     followers (社交证据)
  - answer_count       回答数 — proxy for recent activity

Field availability varies — Zhihu sometimes renders content client-side. We
pull what's in the server-rendered HTML and skip the rest gracefully.

Extraction strategy (resilient → fragile):
  1. ``<script id="js-initialData">``  embedded JSON  (most reliable)
  2. ``<meta name="description">`` / ``<meta property="og:*">``  (fallback)
  3. ``<h1 class="ProfileHeader-name">`` and visible labels  (last resort)

Rate-limit posture:
  Zhihu rate-limits aggressively. We sleep 1-2s between requests and treat
  ``403`` / ``429`` as "back off, count it, move on".
"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import UTC, datetime, timedelta

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select

from ..db import session_scope
from ..models import Researcher, Signal

# Real-browser UA — Zhihu's edge serves a degraded page to non-browser UAs.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

# Don't re-scrape a profile we hit in the last 30 days.
RESCRAPE_WINDOW = timedelta(days=30)


def _handle_from_url(url: str) -> str | None:
    """Extract the bare handle from a Zhihu profile URL.

    Accepts:
      https://www.zhihu.com/people/<handle>
      https://www.zhihu.com/people/<handle>/answers
      zhihu.com/people/<handle>?...
    """
    if not url:
        return None
    m = re.search(r"zhihu\.com/people/([^/?#\s]+)", url)
    return m.group(1) if m else None


def _from_initial_data(html: str) -> dict | None:
    """Pull the user record out of the embedded ``js-initialData`` script.

    Zhihu inlines its Redux store as JSON in a ``<script id="js-initialData">``
    tag. Schema (lightly abridged):

      {"initialState": {"entities": {"users": {"<handle>": {...}}}}}
    """
    tree = HTMLParser(html)
    node = tree.css_first("script#js-initialData")
    if node is None or not node.text():
        return None
    try:
        data = json.loads(node.text())
    except (ValueError, json.JSONDecodeError):
        return None
    users = ((data.get("initialState") or {}).get("entities") or {}).get("users") or {}
    if not isinstance(users, dict) or not users:
        return None
    # There may be multiple users (followees, etc.) — pick the one whose
    # url-token / id matches the page. If unsure, take the entry with the
    # most populated fields.
    best: dict | None = None
    best_score = -1
    for u in users.values():
        if not isinstance(u, dict):
            continue
        # Look for the "current" user (has headline + employments populated
        # more than a follower-list snippet).
        score = sum(
            1
            for k in (
                "headline",
                "employments",
                "educations",
                "followerCount",
                "answerCount",
            )
            if u.get(k) not in (None, "", [], {})
        )
        if score > best_score:
            best = u
            best_score = score
    return best


def _from_meta_tags(html: str) -> dict:
    """Fallback extraction from ``<meta>`` and visible header text.

    Zhihu's ``<meta name="description">`` is typically:
      "<name>，<headline>。<bio>"
    """
    tree = HTMLParser(html)
    out: dict = {}

    desc_node = tree.css_first('meta[name="description"]')
    if desc_node is not None:
        out["description"] = desc_node.attributes.get("content") or None

    name_node = tree.css_first("h1.ProfileHeader-name") or tree.css_first("h1")
    if name_node is not None:
        out["name"] = (name_node.text() or "").strip() or None

    # Headline lives in a sibling span; Zhihu has churned class names over
    # the years, so try a few variants.
    for sel in (
        "div.ProfileHeader-headline",
        "span.RichText.ztext.ProfileHeader-headline",
        "div.Profile-headline",
    ):
        node = tree.css_first(sel)
        if node is not None:
            text = (node.text() or "").strip()
            if text:
                out["headline"] = text
                break

    return out


def _employer_from_record(user: dict) -> str | None:
    """Read employments list — schema is:
    ``[{"job": {"name": "..."}, "company": {"name": "..."}}, ...]``
    """
    emps = user.get("employments") or []
    if not isinstance(emps, list) or not emps:
        return None
    e = emps[0]
    if not isinstance(e, dict):
        return None
    company = ((e.get("company") or {}).get("name") or "").strip()
    job = ((e.get("job") or {}).get("name") or "").strip()
    if company and job:
        return f"{company} · {job}"
    return company or job or None


def _school_from_record(user: dict) -> str | None:
    """Read educations list — schema is:
    ``[{"school": {"name": "..."}, "major": {"name": "..."}}, ...]``
    """
    edus = user.get("educations") or []
    if not isinstance(edus, list) or not edus:
        return None
    e = edus[0]
    if not isinstance(e, dict):
        return None
    school = ((e.get("school") or {}).get("name") or "").strip()
    major = ((e.get("major") or {}).get("name") or "").strip()
    if school and major:
        return f"{school} · {major}"
    return school or major or None


def _extract_profile(html: str) -> dict:
    """Top-level extractor — try initialData first, then meta fallback."""
    out: dict = {
        "name": None,
        "headline": None,
        "employer": None,
        "school": None,
        "follower_count": None,
        "answer_count": None,
    }

    user = _from_initial_data(html)
    if user:
        out["name"] = user.get("name") or None
        out["headline"] = (user.get("headline") or "").strip() or None
        out["employer"] = _employer_from_record(user)
        out["school"] = _school_from_record(user)
        fc = user.get("followerCount")
        if isinstance(fc, int):
            out["follower_count"] = fc
        ac = user.get("answerCount")
        if isinstance(ac, int):
            out["answer_count"] = ac

    # Fill any gaps from meta/visible markup.
    meta = _from_meta_tags(html)
    if not out["name"]:
        out["name"] = meta.get("name")
    if not out["headline"]:
        out["headline"] = meta.get("headline")

    return out


def _recent_zhihu_signal_ids(db, cutoff: datetime) -> set[int]:
    """Researcher ids that already have a recent zhihu_profile Signal."""
    rows = db.execute(
        select(Signal.researcher_id)
        .where(Signal.type == "zhihu_profile", Signal.detected_at >= cutoff)
        .distinct()
    ).all()
    return {row[0] for row in rows}


def scrape_zhihu(limit: int = 20) -> dict[str, int]:
    """Scrape Zhihu profiles for researchers with ``zhihu_url`` set.

    For each researcher we hit in this run:
      - parse handle, fetch page, extract profile dict
      - write a ``zhihu_profile`` Signal (always — even if mostly empty)
      - if ``r.bio`` is null and we got a headline, set it

    Skips researchers that already have a Signal of this type within
    ``RESCRAPE_WINDOW`` (default 30 days).
    """
    counts = {
        "attempted": 0,
        "got_profile": 0,
        "got_bio": 0,
        "errors": 0,
        "rate_limited": 0,
    }

    cutoff = datetime.now(UTC) - RESCRAPE_WINDOW

    client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20.0)
    try:
        with session_scope() as db:
            skip_ids = _recent_zhihu_signal_ids(db, cutoff)

            stmt = (
                select(Researcher).where(Researcher.zhihu_url.is_not(None)).order_by(Researcher.id)
            )
            if skip_ids:
                stmt = stmt.where(Researcher.id.notin_(skip_ids))
            stmt = stmt.limit(limit)

            researchers = list(db.execute(stmt).scalars().all())

            for r in researchers:
                counts["attempted"] += 1
                handle = _handle_from_url(r.zhihu_url or "")
                if not handle:
                    counts["errors"] += 1
                    continue

                url = f"https://www.zhihu.com/people/{handle}"
                try:
                    resp = client.get(url)
                except Exception:
                    counts["errors"] += 1
                    # Polite pause even on error so we don't hammer.
                    time.sleep(random.uniform(1.0, 2.0))
                    continue

                if resp.status_code in (403, 429):
                    counts["rate_limited"] += 1
                    # Back off a bit harder when throttled.
                    time.sleep(random.uniform(2.0, 3.5))
                    continue

                if resp.status_code != 200:
                    counts["errors"] += 1
                    time.sleep(random.uniform(1.0, 2.0))
                    continue

                try:
                    profile = _extract_profile(resp.text)
                except Exception:
                    counts["errors"] += 1
                    time.sleep(random.uniform(1.0, 2.0))
                    continue

                # "Got profile" = at least one non-None field beyond name.
                informative = any(
                    profile.get(k)
                    for k in ("headline", "employer", "school", "follower_count", "answer_count")
                )
                if informative:
                    counts["got_profile"] += 1

                db.add(
                    Signal(
                        researcher_id=r.id,
                        type="zhihu_profile",
                        payload={
                            "handle": handle,
                            "headline": profile.get("headline"),
                            "employer": profile.get("employer"),
                            "school": profile.get("school"),
                            "follower_count": profile.get("follower_count"),
                            "answer_count": profile.get("answer_count"),
                        },
                        occurred_at=datetime.now(UTC),
                        source=f"zhihu:{handle}",
                    )
                )

                # Only backfill bio when we have something meaningful and
                # the field is currently empty — never overwrite manual notes.
                if (not r.bio) and profile.get("headline"):
                    r.bio = profile["headline"]
                    counts["got_bio"] += 1

                time.sleep(random.uniform(1.0, 2.0))
    finally:
        client.close()
    return counts
