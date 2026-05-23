"""Health check — `openscout doctor`.

Reports on:
  - DB state (table counts)
  - API keys present / missing in env (+ Sentry status)
  - External-service reachability
  - Disk usage
  - Most recent brief date
  - Deep-dive activity (today + last 7d + stuck jobs)
  - Tag coverage (signal / institution / topic + top-5 signal tags)
"""

import os
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from .config import settings
from .db import session_scope

console = Console()


def _ok(b: bool) -> str:
    return "[green]✓[/green]" if b else "[red]✗[/red]"


def _check_db() -> Table:
    from .models import DailyBrief, Paper, PaperAuthor, Relationship, Researcher

    t = Table(title="Database", title_style="bold", show_header=False)
    t.add_column("metric")
    t.add_column("value", justify="right")
    with session_scope() as db:
        papers = int(db.execute(select(func.count(Paper.id))).scalar() or 0)
        researchers = int(db.execute(select(func.count(Researcher.id))).scalar() or 0)
        links = int(db.execute(select(func.count()).select_from(PaperAuthor)).scalar() or 0)
        rel = int(db.execute(select(func.count()).select_from(Relationship)).scalar() or 0)
        latest = db.execute(
            select(DailyBrief.brief_date).order_by(DailyBrief.brief_date.desc()).limit(1)
        ).scalar_one_or_none()
        anchors = int(
            db.execute(
                select(func.count(Researcher.id)).where(
                    Researcher.confidence_level.in_(["high", "medium"])
                )
            ).scalar()
            or 0
        )
        with_emails = int(
            db.execute(
                select(func.count(Paper.id)).where(Paper.author_emails.is_not(None))
            ).scalar()
            or 0
        )
        with_code = int(
            db.execute(select(func.count(Paper.id)).where(Paper.code_url.is_not(None))).scalar()
            or 0
        )

    t.add_row("Papers", f"{papers:,}")
    t.add_row("  ├─ with author_emails", f"{with_emails:,}")
    t.add_row("  └─ with code_url", f"{with_code:,}")
    t.add_row("Researchers", f"{researchers:,}")
    t.add_row("  └─ anchors (high/medium conf)", f"{anchors:,}")
    t.add_row("Paper-author links", f"{links:,}")
    t.add_row("Advisor edges", f"{rel:,}")
    t.add_row("Latest brief", str(latest) if latest else "[red]never[/red]")
    return t


def _check_env() -> Table:
    from .scraper import llm

    t = Table(title="API keys", title_style="bold", show_header=False)
    t.add_column("var")
    t.add_column("status")
    keys = [
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key, "Anthropic Claude"),
        ("DEEPSEEK_API_KEY", settings.deepseek_api_key, "DeepSeek (cheaper, OpenAI-compatible)"),
        ("LLM_PROVIDER", settings.llm_provider, f"active: {llm.provider_name()}"),
        (
            "SEMANTIC_SCHOLAR_API_KEY",
            settings.semantic_scholar_api_key,
            "higher S2 rate limit (optional)",
        ),
        ("RESEND_API_KEY", settings.resend_api_key, "email digest"),
        ("NOTIFY_EMAIL_TO", settings.notify_email_to, "email digest recipient"),
        ("INGEST_SECRET", settings.ingest_secret, "GitHub Actions cron auth"),
    ]
    for name, val, purpose in keys:
        present = bool(val and val != "change-me")
        t.add_row(name, f"{_ok(present)} [dim]{purpose}[/dim]")

    # Sentry — read directly from env (not in Settings; init_sentry() reads os.environ).
    sentry_dsn = os.environ.get("SENTRY_DSN", "")
    sentry_env = os.environ.get("SENTRY_ENV", "production")
    sentry_present = bool(sentry_dsn)
    t.add_row(
        "SENTRY_DSN",
        f"{_ok(sentry_present)} [dim]error tracking · environment: {sentry_env}[/dim]",
    )
    return t


def _check_services() -> Table:
    t = Table(title="External services", title_style="bold", show_header=False)
    t.add_column("service")
    t.add_column("status")
    probes = [
        ("arXiv", "https://export.arxiv.org/api/query?search_query=cs.AI&max_results=1"),
        ("OpenAlex", "https://api.openalex.org/works?per-page=1"),
        ("HuggingFace", "https://huggingface.co/api/daily_papers"),
        ("OpenReview", "https://api2.openreview.net/notes?limit=1"),
        ("GitHub", "https://api.github.com/rate_limit"),
        ("DBLP", "https://dblp.org/search/author/api?q=test&format=json&h=1"),
        ("arxiv HTML", "https://arxiv.org/html/2401.12345"),
    ]
    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
        for name, url in probes:
            try:
                r = client.head(url)
                # Some endpoints don't HEAD; fall back to GET
                if r.status_code >= 400:
                    r = client.get(url)
                ok = r.status_code < 500
                t.add_row(name, f"{_ok(ok)} HTTP {r.status_code}")
            except Exception as e:
                t.add_row(name, f"{_ok(False)} [red]{type(e).__name__}[/red]")
    return t


def _check_deep_dive() -> Table:
    """Deep-dive job + quota activity.

    Dialect-agnostic: we slice on enqueued_at by date in Python rather than
    DATE(enqueued_at) so this works identically on SQLite and Postgres.
    """
    from .models import DeepDiveJob, DeepDiveQuota

    t = Table(title="Deep-dive activity", title_style="bold", show_header=False)
    t.add_column("metric")
    t.add_column("value", justify="right")

    today_utc = datetime.now(UTC).date()
    today_start = datetime.combine(today_utc, datetime.min.time(), tzinfo=UTC)
    week_ago_start = today_start - timedelta(days=6)  # rolling 7d incl. today
    stuck_cutoff = datetime.now(UTC) - timedelta(minutes=5)

    with session_scope() as db:
        # Today's job totals (group by state in one pass)
        rows = db.execute(
            select(DeepDiveJob.state, func.count(DeepDiveJob.id))
            .where(DeepDiveJob.enqueued_at >= today_start)
            .group_by(DeepDiveJob.state)
        ).all()
        by_state = {state: int(n) for state, n in rows}
        total_today = sum(by_state.values())
        succeeded = by_state.get("succeeded", 0)
        failed = by_state.get("failed", 0)

        # Quota used today (sum of count)
        quota_used = int(
            db.execute(
                select(func.coalesce(func.sum(DeepDiveQuota.count), 0)).where(
                    DeepDiveQuota.day == today_utc.isoformat()
                )
            ).scalar()
            or 0
        )

        # Last 7 days grouped by date (Python-side bucketing for portability)
        last7_rows = db.execute(
            select(DeepDiveJob.enqueued_at).where(DeepDiveJob.enqueued_at >= week_ago_start)
        ).all()
        per_day: Counter[date] = Counter()
        for (ts,) in last7_rows:
            if ts is not None:
                per_day[ts.date()] += 1

        # Oldest stale job (queued/running > 5min)
        stale = db.execute(
            select(DeepDiveJob.id, DeepDiveJob.slug, DeepDiveJob.state, DeepDiveJob.enqueued_at)
            .where(DeepDiveJob.state.in_(("queued", "running")))
            .where(DeepDiveJob.enqueued_at < stuck_cutoff)
            .order_by(DeepDiveJob.enqueued_at.asc())
            .limit(1)
        ).first()

    t.add_row("Jobs today (total)", f"{total_today:,}")
    t.add_row("  ├─ succeeded", f"[green]{succeeded:,}[/green]")
    fail_style = "red" if failed else "dim"
    t.add_row("  └─ failed", f"[{fail_style}]{failed:,}[/{fail_style}]")
    t.add_row("Quota used today", f"{quota_used:,}")

    if per_day:
        # Compact sparkline: oldest → newest
        days = [(week_ago_start.date() + timedelta(days=i)) for i in range(7)]
        spark = " ".join(f"{d.strftime('%m-%d')}:{per_day.get(d, 0)}" for d in days)
        t.add_row("Last 7 days", f"[dim]{spark}[/dim]")
    else:
        t.add_row("Last 7 days", "[dim]no jobs[/dim]")

    if stale:
        sid, slug, state, ts = stale
        age_min = int((datetime.now(UTC) - ts).total_seconds() / 60)
        t.add_row(
            "Oldest stale job",
            f"[red]#{sid} {slug} ({state}, {age_min}m old)[/red]",
        )
    else:
        t.add_row("Oldest stale job", "[green]none[/green]")
    return t


def _check_tags() -> Table:
    """Tag coverage across the researcher catalog.

    `tags` is a JSON array of {slug, label_en, label_zh?, score, type?}.
    The 'type' key was introduced in v1.10's tag taxonomy split
    (signal / institution / topic). We materialize the JSON in Python
    rather than SQL JSON ops to stay portable across SQLite & Postgres.
    """
    from .models import Researcher

    t = Table(title="Tag coverage", title_style="bold", show_header=False)
    t.add_column("metric")
    t.add_column("value", justify="right")

    with session_scope() as db:
        total = int(db.execute(select(func.count(Researcher.id))).scalar() or 0)
        rows = (
            db.execute(select(Researcher.tags).where(Researcher.tags.is_not(None))).scalars().all()
        )

    has_signal = 0
    has_inst = 0
    has_topic = 0
    signal_counter: Counter[str] = Counter()
    for tags in rows:
        if not tags:
            continue
        types = set()
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            ttype = tag.get("type")
            if ttype:
                types.add(ttype)
            if ttype == "signal":
                label = tag.get("label_en") or tag.get("slug") or "?"
                signal_counter[label] += 1
        if "signal" in types:
            has_signal += 1
        if "institution" in types:
            has_inst += 1
        if "topic" in types:
            has_topic += 1

    def _pct(n: int) -> str:
        if not total:
            return ""
        return f" [dim]({n / total:.0%})[/dim]"

    t.add_row("Researchers (total)", f"{total:,}")
    t.add_row("  ├─ with signal tag", f"{has_signal:,}{_pct(has_signal)}")
    t.add_row("  ├─ with institution tag", f"{has_inst:,}{_pct(has_inst)}")
    t.add_row("  └─ with topic tag", f"{has_topic:,}{_pct(has_topic)}")

    top5 = signal_counter.most_common(5)
    if top5:
        for i, (label, n) in enumerate(top5):
            prefix = "Top signal tags" if i == 0 else ""
            branch = "└─" if i == len(top5) - 1 else "├─"
            t.add_row(prefix, f"[dim]{branch}[/dim] {label} · {n:,}")
    else:
        t.add_row("Top signal tags", "[dim]none[/dim]")
    return t


def _check_disk() -> Table:
    t = Table(title="Disk usage", title_style="bold", show_header=False)
    t.add_column("path")
    t.add_column("size", justify="right")
    root = Path(__file__).resolve().parents[2]
    for label, p in [
        ("openscout.db", root / "openscout.db"),
        ("reports/", root / "reports"),
        ("web/static/social/", root / "web" / "static" / "social"),
        (".venv/", root / ".venv"),
        ("web/node_modules/", root / "web" / "node_modules"),
    ]:
        if p.exists():
            if p.is_file():
                size = p.stat().st_size
            else:
                size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            t.add_row(label, _human(size))
        else:
            t.add_row(label, "[dim]—[/dim]")
    return t


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def run_doctor() -> int:
    """Print all checks. Returns exit code (0 = healthy, nonzero = something flagged)."""
    console.print()
    console.print(_check_db())
    console.print()
    console.print(_check_env())
    console.print()
    console.print(_check_deep_dive())
    console.print()
    console.print(_check_tags())
    console.print()
    console.print(_check_services())
    console.print()
    console.print(_check_disk())
    console.print()
    return 0
