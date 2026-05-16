"""Tests for OpenAlex enricher helpers."""

from openscout.scraper.openalex import _has_cjk, _normalize_name, _pick_chinese_name


def test_has_cjk_pure_english():
    assert _has_cjk("Jun Zhu") is False


def test_has_cjk_chinese():
    assert _has_cjk("朱军") is True


def test_has_cjk_mixed():
    assert _has_cjk("Jun Zhu 朱军") is True


def test_has_cjk_empty():
    assert _has_cjk("") is False
    assert _has_cjk(None) is False


def test_normalize_name_lowercase():
    assert _normalize_name("Jun Zhu") == "jun zhu"


def test_normalize_name_whitespace():
    assert _normalize_name("  Jun   Zhu  ") == "jun zhu"


def test_pick_chinese_name_picks_cjk():
    alts = ["J. Zhu", "Jun Zhu", "朱军", "Zhu Jun"]
    assert _pick_chinese_name(alts) == "朱军"


def test_pick_chinese_name_no_cjk():
    alts = ["J. Zhu", "Jun Zhu", "Zhu Jun"]
    assert _pick_chinese_name(alts) is None


def test_pick_chinese_name_empty():
    assert _pick_chinese_name([]) is None
    assert _pick_chinese_name(None) is None
