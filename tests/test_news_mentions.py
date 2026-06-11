"""Tests for src/openscout/scraper/news_mentions.py — news scanner.

The scraper builds an arxiv-id + name index from the DB, fetches a handful of
feeds, and emits Signal rows when an article mentions a paper / anchor. We
mock httpx.Client.get so no real RSS / 36kr requests happen.
"""

from __future__ import annotations

import inspect
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from openscout.db import session_scope
from openscout.models import Paper, PaperAuthor, Researcher, Signal
from openscout.scraper import news_mentions as nm_mod


@pytest.fixture(autouse=True)
def _clean_tables():
    with session_scope() as db:
        db.query(Signal).delete()
        db.query(PaperAuthor).delete()
        db.query(Paper).delete()
        db.query(Researcher).delete()
    yield


def _make_paper_with_author(arxiv_id: str, name: str) -> tuple[int, int]:
    """Insert a paper + researcher + their authorship link. Returns (paper_id, researcher_id)."""
    with session_scope() as db:
        p = Paper(arxiv_id=arxiv_id, title="Sample Paper", published_at=date.today())
        db.add(p)
        db.flush()
        r = Researcher(slug="anchor", name_en=name, confidence_level="high")
        db.add(r)
        db.flush()
        db.add(PaperAuthor(paper_id=p.id, researcher_id=r.id, position=1))
        db.flush()
        return int(p.id), int(r.id)


def _make_response(status_code: int, *, text: str = "", content: bytes | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = content if content is not None else text.encode("utf-8")
    return resp


# ── signature smoke ───────────────────────────────────────────────────────────


def test_scan_news_mentions_signature():
    sig = inspect.signature(nm_mod.scan_news_mentions)
    # Defaults declared in source
    assert sig.parameters["days"].default == 14
    assert sig.parameters["limit_papers"].default == 500
    # All parameters have defaults — call site can pass nothing
    required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert required == []


# ── empty-DB return shape ─────────────────────────────────────────────────────


def test_scan_news_mentions_empty_db_bails_early():
    """No papers + no anchor researchers → returns the zeroed counts dict and
    never even touches the network."""
    with patch("httpx.Client.get") as mock_get:
        out = nm_mod.scan_news_mentions()
        # Empty index means we short-circuit before any HTTP call
        mock_get.assert_not_called()
    assert set(out.keys()) == {
        "feeds_fetched",
        "articles",
        "paper_hits",
        "researcher_hits",
        "errors",
    }
    assert all(v == 0 for v in out.values())


# ── mocked success path: arxiv_id hit in feed ─────────────────────────────────

_RSS_WITH_ARXIV_HIT = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>The Decoder</title>
<item>
  <title>Breakthrough on 2401.12345 changes the game</title>
  <link>https://example.com/article-1</link>
  <description>Researchers announced 2401.12345 today.</description>
</item>
</channel></rss>
"""


def _fake_get_one_rss_only():
    """Return the canned RSS body for the first RSS feed call, 404 for the rest.

    Why: news_mentions scans 36kr (HTML) + 3 RSS feeds in one DB session. If
    every RSS call got the same body, three Signal writes would land in the
    SAME session before commit — historically (pre per-run guard) that wrote
    duplicate rows and tripped MultipleResultsFound on the next run. Serving
    the body only on the first `the-decoder.com` call keeps this helper a
    single-hit fixture; the all-feeds-same-body case is covered explicitly by
    test_scan_news_mentions_same_url_across_feeds_writes_one_signal.
    """

    def fake_get(self, url, **kwargs):
        # 36kr is HTML — 404 it. Only the first RSS feed gets the canned body.
        if "the-decoder.com" in url:
            return _make_response(200, text=_RSS_WITH_ARXIV_HIT)
        return _make_response(404)

    return fake_get


def test_scan_news_mentions_picks_up_arxiv_id_hit():
    """Inject a paper with arxiv_id `2401.12345`, mock one feed to return an
    article whose title contains that id, verify a paper-hit Signal lands."""
    paper_id, researcher_id = _make_paper_with_author("2401.12345", "Anchor Person")

    with patch("httpx.Client.get", new=_fake_get_one_rss_only()), patch("time.sleep"):
        out = nm_mod.scan_news_mentions()

    assert out["feeds_fetched"] >= 1
    assert out["articles"] >= 1
    assert out["paper_hits"] >= 1
    with session_scope() as db:
        rows = db.query(Signal).filter(Signal.type == "news_mention").all()
        assert len(rows) >= 1
        # The Signal should be attributed to the paper's first author
        assert any(s.researcher_id == researcher_id for s in rows)


# ── idempotency ───────────────────────────────────────────────────────────────


def test_scan_news_mentions_is_idempotent():
    """Re-running the same scan against the same feed body doesn't duplicate
    Signal rows (dedup is keyed on URL hash)."""
    _make_paper_with_author("2401.12345", "Anchor Person")

    with patch("httpx.Client.get", new=_fake_get_one_rss_only()), patch("time.sleep"):
        nm_mod.scan_news_mentions()
        with session_scope() as db:
            count_first = db.query(Signal).filter(Signal.type == "news_mention").count()

    with patch("httpx.Client.get", new=_fake_get_one_rss_only()), patch("time.sleep"):
        nm_mod.scan_news_mentions()
        with session_scope() as db:
            count_second = db.query(Signal).filter(Signal.type == "news_mention").count()

    assert count_second == count_first
    assert count_first >= 1


def _fake_get_same_rss_everywhere():
    """Serve the SAME canned RSS body for every RSS feed (404 for 36kr's HTML).

    The same article URL therefore arrives three times in a single run — the
    regression case for the per-run dedup guard: with `autoflush=False` the
    SELECT-based dedup can't see uncommitted rows from the same session, so a
    guard-less scraper writes one Signal per feed for the same (researcher,
    url_hash) and the NEXT run's scalar lookup trips MultipleResultsFound.
    """

    def fake_get(self, url, **kwargs):
        if "36kr.com" in url:
            return _make_response(404)
        return _make_response(200, text=_RSS_WITH_ARXIV_HIT)

    return fake_get


def test_scan_news_mentions_same_url_across_feeds_writes_one_signal():
    """The same article URL served by all three RSS feeds in ONE run produces
    exactly one Signal row, and the re-run neither raises nor adds rows."""
    _, researcher_id = _make_paper_with_author("2401.12345", "Anchor Person")

    with patch("httpx.Client.get", new=_fake_get_same_rss_everywhere()), patch("time.sleep"):
        nm_mod.scan_news_mentions()
    with session_scope() as db:
        rows = db.query(Signal).filter(Signal.type == "news_mention").all()
        assert len(rows) == 1
        assert rows[0].researcher_id == researcher_id

    # Re-run against the same feeds: must not raise MultipleResultsFound and
    # must not duplicate the row.
    with patch("httpx.Client.get", new=_fake_get_same_rss_everywhere()), patch("time.sleep"):
        nm_mod.scan_news_mentions()
    with session_scope() as db:
        assert db.query(Signal).filter(Signal.type == "news_mention").count() == 1
