"""Daily brief generator — renders Markdown in the KS Newsprint style and persists it.

Section layout:
  A · 头版概览          KPI table
  B · 🆕 今日新冒头      first-time authors first-authoring a paper today
  B · 🔄 动态更新        anchor researchers (or prior-discovered) who shipped today
  C · 🎓 即将毕业        coming soon — needs career_stage_year inference
  D · 🚀 即将入职 AP      coming soon — needs faculty-announcement scraper
  E · 🔥 热门工作        today's papers ranked (v1: author-count proxy)
  F · 🌙 Sleeper Picks   coming soon — algorithm column
"""

from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import DailyBrief, Paper, PaperAuthor, Researcher

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"

# Volume 1 starts on this date.
VOLUME_1_START = Date(2026, 5, 15)

# Max characters of abstract to show as the inline blurb.
BLURB_MAX_CHARS = 220


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
        md = _render(db, brief_date, issue_no)

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


# ─── Queries ────────────────────────────────────────────────────────────────


def _kpi_counts(db: Session, brief_date: Date) -> dict[str, int]:
    tracked = db.execute(select(func.count(Researcher.id))).scalar() or 0
    today_papers = (
        db.execute(
            select(func.count(Paper.id)).where(
                func.date(Paper.first_seen_at) == brief_date
            )
        ).scalar()
        or 0
    )
    today_emergences = (
        db.execute(
            select(func.count(Researcher.id)).where(
                func.date(Researcher.first_seen_at) == brief_date,
                Researcher.confidence_level == "low",
            )
        ).scalar()
        or 0
    )
    return {
        "tracked": tracked,
        "today_papers": today_papers,
        "today_emergences": today_emergences,
    }


def _today_new_first_authors(db: Session, brief_date: Date, limit: int = 10) -> list[tuple[Researcher, Paper]]:
    """Researchers first seen today who are first-author on a paper today."""
    stmt = (
        select(Researcher, Paper)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .join(Paper, Paper.id == PaperAuthor.paper_id)
        .where(
            PaperAuthor.position == 1,
            func.date(Researcher.first_seen_at) == brief_date,
            Researcher.confidence_level == "low",
            func.date(Paper.first_seen_at) == brief_date,
        )
        .order_by(desc(Paper.first_seen_at))
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def _today_anchor_activity(db: Session, brief_date: Date, limit: int = 10) -> list[tuple[Researcher, Paper]]:
    """Anchor / previously-known researchers who published today."""
    stmt = (
        select(Researcher, Paper)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .join(Paper, Paper.id == PaperAuthor.paper_id)
        .where(
            Researcher.confidence_level != "low",
            func.date(Paper.first_seen_at) == brief_date,
        )
        .order_by(desc(Paper.first_seen_at))
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def _today_hot_papers(db: Session, brief_date: Date, limit: int = 10) -> list[tuple[Paper, int, Researcher | None]]:
    """Today's papers ranked by author count (v1 proxy for collaboration weight)."""
    author_count_sq = (
        select(
            PaperAuthor.paper_id,
            func.count(PaperAuthor.researcher_id).label("n_authors"),
        )
        .group_by(PaperAuthor.paper_id)
        .subquery()
    )
    stmt = (
        select(Paper, func.coalesce(author_count_sq.c.n_authors, 0).label("n_authors"))
        .outerjoin(author_count_sq, author_count_sq.c.paper_id == Paper.id)
        .where(func.date(Paper.first_seen_at) == brief_date)
        .order_by(desc("n_authors"), desc(Paper.first_seen_at))
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    out: list[tuple[Paper, int, Researcher | None]] = []
    for paper, n in rows:
        first_author = db.execute(
            select(Researcher)
            .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
            .where(PaperAuthor.paper_id == paper.id, PaperAuthor.position == 1)
            .limit(1)
        ).scalar_one_or_none()
        out.append((paper, int(n), first_author))
    return out


# ─── Render helpers ─────────────────────────────────────────────────────────


def _blurb(text: str | None) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= BLURB_MAX_CHARS else text[: BLURB_MAX_CHARS - 1].rstrip() + "…"


def _arxiv_url(arxiv_id: str | None) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "#"


# ─── Main render ────────────────────────────────────────────────────────────


def _render(db: Session, brief_date: Date, issue_no: int) -> str:
    weekday = brief_date.strftime("%A").upper()
    pretty_date = brief_date.strftime("%B %-d, %Y").upper()
    gen_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    kpi = _kpi_counts(db, brief_date)
    new_authors = _today_new_first_authors(db, brief_date)
    anchor_activity = _today_anchor_activity(db, brief_date)
    hot_papers = _today_hot_papers(db, brief_date)

    out: list[str] = []
    out.append(
        f"""```
VOL. 1 · NO. {issue_no:03d}                              BEIJING EDITION
DAILY · 具身 / 世界模型 / AI4SCI · {weekday}, {pretty_date}
```

# OpenScout

> *All The Researchers Fit To Watch* — Vol. 1, No. {issue_no:03d} · {brief_date.isoformat()}

_Auto-generated at {gen_iso} · [完整看板](http://localhost:5174) · [API](/researchers)_

---

## Section A · 头版概览

| Tracked | 今日新增 paper | 新冒头 | 毕业季 PhD | 即将入职 AP |
| ---: | ---: | ---: | ---: | ---: |
| **{kpi["tracked"]}** | {kpi["today_papers"]} | {kpi["today_emergences"]} | _coming soon_ | _coming soon_ |

✦ &nbsp; ✦ &nbsp; ✦
"""
    )

    # Section B · 🆕 今日新冒头
    out.append(f"## Section B · 🆕 今日新冒头 · {len(new_authors)} 人\n")
    if not new_authors:
        out.append("_今日没有新冒头的一作。_\n")
    else:
        for i, (r, p) in enumerate(new_authors[:10], start=1):
            out.append(
                f"### No. {i:02d} · {p.title}\n\n"
                f"**{r.name_en}** · 一作 · [arXiv:{p.arxiv_id}]({_arxiv_url(p.arxiv_id)})\n\n"
                f"_{_blurb(p.abstract)}_\n\n"
                f"→ [profile](/researchers/{r.slug})\n\n"
                "---\n"
            )

    # Section B · 🔄 动态更新
    out.append(f"\n## Section B · 🔄 动态更新 · {len(anchor_activity)} 项\n")
    if not anchor_activity:
        out.append("_库内已知人今日无新动作。_\n")
    else:
        out.append("| 研究者 | 新工作 | arXiv |\n| --- | --- | --- |\n")
        for r, p in anchor_activity[:10]:
            short_title = p.title if len(p.title) <= 70 else p.title[:69].rstrip() + "…"
            out.append(
                f"| [{r.name_en}](/researchers/{r.slug}) | {short_title} | [{p.arxiv_id}]({_arxiv_url(p.arxiv_id)}) |\n"
            )

    out.append("\n✦ &nbsp; ✦ &nbsp; ✦\n")

    # Section C, D — TBD
    out.append("\n## Section C · 🎓 即将毕业 PhD · Top 10\n\n_coming soon — 需要 career_stage_year 推断._\n")
    out.append("\n## Section D · 🚀 即将入职 AP · Top 10\n\n_coming soon — 需要 faculty announcement scraper._\n")
    out.append("\n✦ &nbsp; ✦ &nbsp; ✦\n")

    # Section E · 🔥 热门工作
    out.append(f"\n## Section E · 🔥 热门工作 · Top {min(len(hot_papers), 10)}\n\n")
    if not hot_papers:
        out.append("_今日无新 paper。_\n")
    else:
        for i, (p, n_authors, first_author) in enumerate(hot_papers[:10], start=1):
            fa = (
                f"[{first_author.name_en}](/researchers/{first_author.slug})"
                if first_author
                else "_(no first author resolved)_"
            )
            out.append(
                f"### No. {i:02d} · {p.title}\n\n"
                f"{fa} · {n_authors} 作者 · [arXiv:{p.arxiv_id}]({_arxiv_url(p.arxiv_id)})\n\n"
                f"_{_blurb(p.abstract)}_\n\n"
                "---\n"
            )

    out.append("\n✦ &nbsp; ✦ &nbsp; ✦\n")

    # Section F — TBD
    out.append(
        '\n## Section F · 🌙 Sleeper Picks\n\n'
        '_coming soon — 算法挑的「非显式但值得看」，每个写明被选中的原因 '
        '(e.g.「第一篇 paper 但导师是 Shuran Song」「citation 增速异常」)._\n'
    )

    out.append("\n---\n\n*All the research that's fit to watch, every morning at 09:00 Beijing.*\n")

    return "".join(out)
