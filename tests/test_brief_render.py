"""Tests for src/openscout/brief/generate.py."""

from openscout.brief.generate import _arxiv_url, _blurb


def test_blurb_short():
    assert _blurb("hello world") == "hello world"


def test_blurb_truncates():
    long = "x" * 1000
    out = _blurb(long)
    assert len(out) <= 220
    assert out.endswith("…")


def test_blurb_none():
    assert _blurb(None) == ""


def test_blurb_normalizes_whitespace():
    assert _blurb("a  \n  b") == "a b"


def test_arxiv_url_with_id():
    assert _arxiv_url("2401.12345") == "https://arxiv.org/abs/2401.12345"


def test_arxiv_url_without_id():
    assert _arxiv_url(None) == "#"
