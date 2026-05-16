"""LLM Chinese one-liner translator — Anthropic Claude or DeepSeek.

Generates a ≤ 25-character Chinese sentence summarizing each paper's core
contribution. Stored on `paper.one_liner_zh`.

Provider picked from `settings.llm_provider` (auto if blank: prefer deepseek
if its key is set, else anthropic). Graceful skip when no provider configured.

API errors → leave `one_liner_zh` null (never write garbage).
"""

import time

from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper
from . import llm

PROMPT = """请用一句中文（不超过 25 字）概括下面这篇论文的核心创新点。
要求：
1. 直接说创新点，不要加 "本文" "我们" 等前缀
2. 包含关键技术词（如：扩散模型 / 强化学习 / 蛋白质结构预测）
3. 如果摘要是英文，直接翻译核心句即可，专有名词保留英文

论文标题：{title}

摘要：
{abstract}

输出（仅一句中文，最多 25 字）："""


def translate_papers(limit: int = 30, sleep_between: float = 0.3) -> dict[str, int]:
    counts = {
        "attempted": 0,
        "translated": 0,
        "skipped_no_provider": 0,
        "skipped_api_error": 0,
        "errors": 0,
    }

    if not llm.is_available():
        counts["skipped_no_provider"] = limit
        return counts

    consecutive_errors = 0

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
            prompt = PROMPT.format(
                title=paper.title.strip(),
                abstract=(paper.abstract or "").strip()[:2000],
            )
            text, err = llm.complete(prompt, max_tokens=80)
            if text is None:
                counts["skipped_api_error"] += 1
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    counts["errors"] = limit - counts["attempted"]
                    break
                time.sleep(1.0)
                continue
            consecutive_errors = 0

            for ch in "\"'「」":
                text = text.strip(ch)
            if len(text) > 40:
                text = text[:40].rstrip() + "…"
            if text:
                paper.one_liner_zh = text
                counts["translated"] += 1
            time.sleep(sleep_between)

    return counts
