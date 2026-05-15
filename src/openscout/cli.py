"""OpenScout CLI — `uv run openscout <command>`."""

from typing import Annotated, Optional

import typer
from rich.console import Console

app = typer.Typer(help="OpenScout — daily tracker for early-stage AI researchers.")
console = Console()


@app.command("init-db")
def init_db() -> None:
    """Create all tables + run idempotent ALTER TABLE migrations."""
    from .db import engine
    from .migrations import upgrade_schema
    from .models import Base

    Base.metadata.create_all(engine)
    added = upgrade_schema(engine)
    console.print("[green]✓[/green] tables created")
    if added:
        for col in added:
            console.print(f"  [green]+[/green] added column [cyan]{col}[/cyan]")


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


@app.command("resolve-institutions")
def resolve_institutions_cmd() -> None:
    """Resolve seed institutions → OpenAlex Institution IDs (used to disambiguate authors)."""
    from .scraper.openalex import resolve_institutions

    c = resolve_institutions()
    console.print(
        f"[green]✓[/green] institutions: matched {c['matched']}/{c['attempted']} · "
        f"no_match {c['no_match']}"
    )


@app.command("reset-enrichment")
def reset_enrichment() -> None:
    """Clear openalex_id for researchers with affiliation (forces re-enrichment with institution filter)."""
    from .scraper.openalex import reset_low_quality_matches

    n = reset_low_quality_matches()
    console.print(f"[green]✓[/green] reset {n} researchers")


@app.command("enrich-openalex")
def enrich_openalex(
    limit: Annotated[int, typer.Option(help="Max researchers to enrich")] = 200,
    only_anchors: Annotated[bool, typer.Option(help="Only anchor researchers (high/medium conf)")] = False,
) -> None:
    """Pull Chinese names, citation counts, h-index, and topic tags from OpenAlex."""
    from .scraper.openalex import enrich_all

    only_conf = ["high", "medium"] if only_anchors else None
    counts = enrich_all(limit=limit, only_confidence=only_conf)
    console.print(
        f"[green]✓[/green] OpenAlex enrichment: "
        f"matched {counts['matched']}/{counts['attempted']} · "
        f"+{counts['with_zh_name']} Chinese names · "
        f"+{counts['with_tags']} with tags · "
        f"{counts['errors']} errors"
    )


@app.command()
def lineage() -> None:
    """Infer advisor → student edges from co-author frequency (heuristic)."""
    from .scraper.lineage import infer_lineage

    counts = infer_lineage()
    console.print(
        f"[green]✓[/green] lineage inference: "
        f"+{counts['edges_added']} edges · "
        f"{counts['juniors_scanned']} juniors scanned · "
        f"{counts['anchors_matched']} anchor-coauthor matches"
    )


@app.command("signature-papers")
def signature_papers() -> None:
    """Assign each researcher a signature paper (highest citation among their works)."""
    from .scraper.openalex import assign_signature_papers

    n = assign_signature_papers()
    console.print(f"[green]✓[/green] assigned {n} signature papers")


@app.command("extract-emails")
def extract_emails(
    limit: Annotated[int, typer.Option(help="Max recent papers to scrape")] = 20,
) -> None:
    """Download recent arXiv PDFs and extract emails from page 1."""
    from .scraper.pdf_emails import extract_paper_emails

    c = extract_paper_emails(limit=limit)
    console.print(
        f"[green]✓[/green] email scrape: {c['with_emails']} papers with emails / "
        f"{c['attempted']} attempted · {c['no_pdf']} no_pdf · {c['errors']} errors"
    )


@app.command("translate-papers")
def translate_papers_cmd(
    limit: Annotated[int, typer.Option(help="Max papers to translate")] = 20,
) -> None:
    """LLM Chinese one-liner for paper abstracts (requires ANTHROPIC_API_KEY)."""
    from .scraper.translator import translate_papers

    c = translate_papers(limit=limit)
    if c["skipped_no_key"]:
        console.print(
            f"[yellow]⚠[/yellow] ANTHROPIC_API_KEY not set — skipping translation. "
            f"Set it in .env to enable."
        )
    else:
        console.print(
            f"[green]✓[/green] translated {c['translated']}/{c['attempted']} · "
            f"{c['errors']} errors"
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
