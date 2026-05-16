"""Health check — `openscout doctor`.

Reports on:
  - DB state (table counts)
  - API keys present / missing in env
  - External-service reachability
  - Disk usage
  - Most recent brief date
"""

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
    t = Table(title="API keys", title_style="bold", show_header=False)
    t.add_column("var")
    t.add_column("status")
    keys = [
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key, "translator + topic classifier"),
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
    console.print(_check_services())
    console.print()
    console.print(_check_disk())
    console.print()
    return 0
