"""Daily brief generator — uses brief.data for queries; renders to Markdown.

For the structured JSON used by the frontend, call `data.collect()` directly.
"""

from datetime import UTC, datetime
from datetime import date as Date
from pathlib import Path

from sqlalchemy import select

from ..db import session_scope
from ..models import DailyBrief
from . import data as bd

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"

BLURB_MAX_CHARS = 220


def generate_brief(date: str | None = None) -> Path:
    """Generate the brief for `date` (defaults to today UTC).

    Side effects:
      - Writes `reports/YYYY-MM-DD.md` and `reports/latest.md`
      - Upserts a row in `daily_briefs`
    """
    brief_date = Date.fromisoformat(date) if date else datetime.now(UTC).date()

    with session_scope() as db:
        brief = bd.collect(db, brief_date)
        md = _render(brief)

        existing = db.execute(
            select(DailyBrief).where(DailyBrief.brief_date == brief_date)
        ).scalar_one_or_none()
        if existing:
            existing.rendered_md = md
        else:
            db.add(
                DailyBrief(
                    brief_date=brief_date,
                    volume=1,
                    issue=brief.issue,
                    rendered_md=md,
                )
            )

    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{brief_date.isoformat()}.md"
    path.write_text(md, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(md, encoding="utf-8")
    return path


# ─── Markdown render ────────────────────────────────────────────────────────


def _blurb(text: str | None) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= BLURB_MAX_CHARS else text[: BLURB_MAX_CHARS - 1].rstrip() + "…"


def _arxiv_url(arxiv_id: str | None) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "#"


def _render_story_card(idx: int, story: bd.StoryItem) -> str:
    r, p = story.researcher, story.paper
    parts = [
        f"### No. {idx:02d} · {p.title}\n\n",
        f"**{r.name_en}** · 一作 · {p.n_authors} 作者 · "
        f"[arXiv:{p.arxiv_id}]({_arxiv_url(p.arxiv_id)})\n\n",
    ]
    if p.one_liner_zh:
        parts.append(f"*{p.one_liner_zh}*\n\n")
    parts.append(f"_{_blurb(p.abstract)}_\n\n")
    if story.reasoning:
        parts.append(f"**▸ 选中原因：{story.reasoning}**\n\n")
    parts.append(f"→ [profile](/researchers/{r.slug})\n\n---\n")
    return "".join(parts)


def _render(brief: bd.BriefData) -> str:
    weekday = brief.brief_date.strftime("%A").upper()
    pretty_date = brief.brief_date.strftime("%B %-d, %Y").upper()
    gen_iso = datetime.now(UTC).isoformat(timespec="seconds")

    out: list[str] = []
    out.append(
        f"""```
VOL. 1 · NO. {brief.issue:03d}                              BEIJING EDITION
DAILY · 具身 / 世界模型 / AI4SCI · {weekday}, {pretty_date}
```

# OpenScout

> *All The Researchers Fit To Watch* — Vol. 1, No. {brief.issue:03d} · {brief.brief_date.isoformat()}

_Auto-generated at {gen_iso} · [完整看板](http://localhost:5174) · [API](/briefs/today)_

---

## Section A · 头版概览

| Tracked | 今日新增 paper | 新冒头 | 毕业季 PhD | 即将入职 AP |
| ---: | ---: | ---: | ---: | ---: |
| **{brief.tracked}** | {brief.today_papers} | {brief.today_emergences} | {brief.soon_graduating or "_n/a_"} | {brief.incoming_ap or "_n/a_"} |

✦ &nbsp; ✦ &nbsp; ✦
"""
    )

    # Section B 新冒头
    out.append(f"\n## Section B · 🆕 今日新冒头 · {len(brief.new_first_authors)} 人\n\n")
    if not brief.new_first_authors:
        out.append("_今日没有新冒头的一作。_\n")
    else:
        for i, s in enumerate(brief.new_first_authors, start=1):
            out.append(_render_story_card(i, s))

    # Section B 动态更新
    out.append(f"\n## Section B · 🔄 动态更新 · {len(brief.anchor_activity)} 项\n\n")
    if not brief.anchor_activity:
        out.append("_库内已知人今日无新动作。_\n")
    else:
        out.append("| 研究者 | 新工作 | 主题 | arXiv |\n| --- | --- | --- | --- |\n")
        for s in brief.anchor_activity:
            r, p = s.researcher, s.paper
            short_title = p.title if len(p.title) <= 70 else p.title[:69].rstrip() + "…"
            topics = ", ".join(p.topics) or "—"
            out.append(
                f"| [{r.name_en}](/researchers/{r.slug}) | {short_title} | {topics} | [{p.arxiv_id}]({_arxiv_url(p.arxiv_id)}) |\n"
            )

    out.append("\n✦ &nbsp; ✦ &nbsp; ✦\n")

    # Section C 即将毕业
    out.append(f"\n## Section C · 🎓 即将毕业 PhD · Top {len(brief.soon_graduating_picks)}\n\n")
    if not brief.soon_graduating_picks:
        out.append("_数据不足 — 需要 career_stage_year 推断 (TODO)._\n")
    else:
        out.append(
            "_v0 fallback: 最高产的 auto-discovered first-author（proxy for 活跃晚期）._\n\n"
        )
        for i, s in enumerate(brief.soon_graduating_picks[:10], start=1):
            out.append(_render_story_card(i, s))

    # Section D 即将 AP
    out.append("\n## Section D · 🚀 即将入职 AP · Top 10\n\n")
    out.append(
        "_coming soon — 需要 faculty announcement scraper (清华/北大/Stanford 招聘公告 + Twitter 监听)._\n"
    )

    out.append("\n✦ &nbsp; ✦ &nbsp; ✦\n")

    # Section E 热门工作
    out.append(f"\n## Section E · 🔥 热门工作 · Top {len(brief.hot_papers)}\n\n")
    if not brief.hot_papers:
        out.append("_今日无新 paper。_\n")
    else:
        for i, s in enumerate(brief.hot_papers, start=1):
            out.append(_render_story_card(i, s))

    out.append("\n✦ &nbsp; ✦ &nbsp; ✦\n")

    # Section F Sleeper Picks
    out.append(f"\n## Section F · 🌙 Sleeper Picks · {len(brief.sleeper_picks)} 个\n\n")
    if not brief.sleeper_picks:
        out.append("_今日无符合算法的 Sleeper Pick — 算法看上去保守了，或今日确实没有合规候选._\n")
    else:
        out.append("_算法挑的「非显式但值得看」，每个写明被选中的原因。_\n\n")
        for i, s in enumerate(brief.sleeper_picks, start=1):
            out.append(_render_story_card(i, s))

    out.append("\n---\n\n*All the research that's fit to watch, every morning at 09:00 Beijing.*\n")
    return "".join(out)
