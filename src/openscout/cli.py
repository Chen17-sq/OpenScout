"""OpenScout CLI — `uv run openscout <command>`."""

from typing import Annotated, Optional

import typer
from rich.console import Console

app = typer.Typer(help="OpenScout — daily tracker for early-stage AI researchers.")
console = Console()


@app.command("init-db")
def init_db() -> None:
    """Create all tables. DEV ONLY — use `alembic upgrade head` in production."""
    from .db import engine
    from .models import Base

    Base.metadata.create_all(engine)
    console.print("[green]✓[/green] tables created")


@app.command()
def seed() -> None:
    """Load seeds/*.yaml into the DB."""
    from .db import session_scope
    from .seeds import load_all

    with session_scope() as db:
        counts = load_all(db)
    for name, n in counts.items():
        console.print(f"[green]✓[/green] {name}: +{n}")


@app.command()
def ingest(
    topic: Annotated[str, typer.Option(help="Topic slug: embodied / world_models / ai4sci")] = "embodied",
    limit: Annotated[int, typer.Option(help="Max papers to pull")] = 50,
) -> None:
    """Pull recent arXiv papers for the given topic."""
    from .scraper.arxiv import ingest_topic

    n = ingest_topic(topic, limit=limit)
    console.print(f"[green]✓[/green] ingested {n} new papers for topic={topic}")


@app.command()
def brief(
    date: Annotated[Optional[str], typer.Option(help="YYYY-MM-DD; defaults to today")] = None,
) -> None:
    """Generate the daily brief Markdown."""
    from .brief.generate import generate_brief

    path = generate_brief(date=date)
    console.print(f"[green]✓[/green] brief written to [cyan]{path}[/cyan]")


@app.command()
def enrich(
    limit: Annotated[int, typer.Option(help="Max papers to enrich via Semantic Scholar")] = 30,
) -> None:
    """Look up recent papers on Semantic Scholar; attach S2 author IDs + citation counts."""
    from .scraper.semanticscholar import enrich_recent_papers

    papers_n, researchers_n = enrich_recent_papers(limit=limit)
    console.print(
        f"[green]✓[/green] enriched {papers_n} papers; "
        f"updated {researchers_n} researcher records with S2 IDs / affiliations / homepages"
    )


@app.command()
def banner() -> None:
    """Generate web/static/banner.svg + og-card.svg with today's stamps."""
    from sqlalchemy import func, select

    from .brief.generate import generate_brief  # noqa: F401  ensures imports resolve
    from .db import session_scope
    from .models import Paper, Researcher
    from .scraper.banner import write_banners

    with session_scope() as db:
        tracked = int(db.execute(select(func.count(Researcher.id))).scalar() or 0)
        papers = int(db.execute(select(func.count(Paper.id))).scalar() or 0)

    out = write_banners(tracked=tracked, papers=papers)
    for k, v in out.items():
        console.print(f"[green]✓[/green] {k}: [cyan]{v}[/cyan]")


if __name__ == "__main__":
    app()
