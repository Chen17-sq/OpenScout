"""Daily brief generator — renders Markdown in the KS Newsprint style and persists it.

Section structure (v0 skeleton, sections populated as features land):
  A · 头版概览 (KPI table)
  B · 🆕 今日新冒头  +  🔄 动态更新
  C · 🎓 即将毕业 PhD · Top 10
  D · 🚀 即将入职 AP · Top 10
  E · 🔥 热门工作 · Top 10
  F · 🌙 Sleeper Picks
"""

from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from ..db import session_scope
from ..models import DailyBrief, Paper, Researcher

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"

# Volume 1 starts on this date.
VOLUME_1_START = Date(2026, 5, 15)


def _issue_number(brief_date: Date) -> int:
    return (brief_date - VOLUME_1_START).days + 1


def generate_brief(date: str | None = None) -> Path:
    """Generate the brief for `date` (defaults to today UTC).

    Writes:
      - `reports/YYYY-MM-DD.md`
      - `reports/latest.md`
      - row in `daily_briefs` table
    """
    brief_date = Date.fromisoformat(date) if date else datetime.now(timezone.utc).date()
    issue_no = _issue_number(brief_date)

    with session_scope() as db:
        tracked = db.execute(select(func.count(Researcher.id))).scalar() or 0
        today_papers = (
            db.execute(
                select(func.count(Paper.id)).where(
                    func.date(Paper.first_seen_at) == brief_date
                )
            ).scalar()
            or 0
        )

        md = _render(brief_date, issue_no, tracked=tracked, today_papers=today_papers)

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
                    issue=issue_no,
                    rendered_md=md,
                )
            )

    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{brief_date.isoformat()}.md"
    path.write_text(md, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(md, encoding="utf-8")
    return path


def _render(brief_date: Date, issue_no: int, *, tracked: int, today_papers: int) -> str:
    weekday = brief_date.strftime("%A").upper()
    pretty_date = brief_date.strftime("%B %-d, %Y").upper()
    gen_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return f"""```
VOL. 1 · NO. {issue_no:03d}                              BEIJING EDITION
DAILY · 具身 / 世界模型 / AI4SCI · {weekday}, {pretty_date}
```

# OpenScout

> *All The Researchers Fit To Watch* — Vol. 1, No. {issue_no:03d} · {brief_date.isoformat()}

_Auto-generated at {gen_iso} · [完整看板](https://openscout.app/) · [API](/researchers)_

---

## Section A · 头版概览

| Tracked | 今日新增 paper | 新冒头 | 毕业季 PhD | 即将入职 AP |
| ---: | ---: | ---: | ---: | ---: |
| **{tracked}** | {today_papers} | _coming soon_ | _coming soon_ | _coming soon_ |

✦ &nbsp; ✦ &nbsp; ✦

## Section B · 🆕 今日新冒头

_第一次出现的高 work_score 作者 — coming soon._

## Section B · 🔄 动态更新

_库内已知人的新动作 — coming soon._

✦ &nbsp; ✦ &nbsp; ✦

## Section C · 🎓 即将毕业 PhD · Top 10

_coming soon — PhD-4/5 卡片：照片 + 导师 + 代表作 + 联系图标._

## Section D · 🚀 即将入职 AP · Top 10

_coming soon — 公告的 incoming faculty._

## Section E · 🔥 热门工作 · Top 10

_coming soon — 今日 buzz 高的 paper → 一作详情._

## Section F · 🌙 Sleeper Picks

_coming soon — 算法挑的"非显式但值得看"，每个写明被选中的原因.
e.g.「第一篇 paper 但导师是 Shuran Song」「citation 增速异常」「在 NeurIPS oral 但没人讨论」_

✦ &nbsp; ✦ &nbsp; ✦

---

*All the research that's fit to watch, every morning at 09:00 Beijing.*
"""
