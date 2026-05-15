"""LLM Chinese one-liner translator — Claude Haiku.

Generates a ≤ 25-character Chinese sentence summarizing each paper's core
contribution. Stored on `paper.one_liner_zh`. Re-runs only on papers with
abstract present and one_liner_zh still null.

Graceful skip when ANTHROPIC_API_KEY is unset — the rest of the pipeline
keeps working with empty Chinese blurbs.
"""

import time

from sqlalchemy import desc, select

from ..config import settings
from ..db import session_scope
from ..models import Paper

PROMPT = """请用一句中文（不超过 25 字）概括下面这篇论文的核心创新点。
要求：
1. 直接说创新点，不要加 "本文" "我们" 等前缀
2. 包含关键技术词（如：扩散模型 / 强化学习 / 蛋白质结构预测）
3. 如果摘要是英文，直接翻译核心句即可，专有名词保留英文

论文标题：{title}

摘要：
{abstract}

输出（仅一句中文）："""


def _call_claude(client, title: str, abstract: str) -> str | None:
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=80,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT.format(title=title.strip(), abstract=abstract.strip()[:2000]),
                }
            ],
        )
        if not resp.content:
            return None
        text = resp.content[0].text.strip()
        # Strip quote chars sometimes added
        text = text.strip("\"'「」「")
        # Cap length defensively
        if len(text) > 40:
            text = text[:40].rstrip() + "…"
        return text or None
    except Exception:
        return None


def translate_papers(limit: int = 30, sleep_between: float = 0.3) -> dict[str, int]:
    """Translate up to `limit` papers' abstracts into Chinese one-liners.

    Returns {attempted, translated, skipped_no_key, errors}.
    """
    counts = {"attempted": 0, "translated": 0, "skipped_no_key": 0, "errors": 0}

    if not settings.anthropic_api_key:
        counts["skipped_no_key"] = limit
        return counts

    try:
        import anthropic
    except ImportError:
        return {**counts, "errors": limit}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    with session_scope() as db:
        papers = list(
            db.execute(
                select(Paper)
                .where(Paper.one_liner_zh.is_(None), Paper.abstract.is_not(None))
                .order_by(desc(Paper.first_seen_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for paper in papers:
            counts["attempted"] += 1
            zh = _call_claude(client, paper.title, paper.abstract or "")
            if zh:
                paper.one_liner_zh = zh
                counts["translated"] += 1
            else:
                counts["errors"] += 1
            time.sleep(sleep_between)

    return counts
