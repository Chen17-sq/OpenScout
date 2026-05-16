"""OpenScout CLI — `uv run openscout <command>`."""

from typing import Annotated

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
    topic: Annotated[
        str, typer.Option(help="Topic slug: embodied / world_models / ai4sci")
    ] = "embodied",
    limit: Annotated[int, typer.Option(help="Max papers to pull")] = 50,
) -> None:
    """Pull recent arXiv papers for the given topic."""
    from .scraper.arxiv import ingest_topic

    n = ingest_topic(topic, limit=limit)
    console.print(f"[green]✓[/green] ingested {n} new papers for topic={topic}")


@app.command()
def brief(
    date: Annotated[str | None, typer.Option(help="YYYY-MM-DD; defaults to today")] = None,
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
    only_anchors: Annotated[
        bool, typer.Option(help="Only anchor researchers (high/medium conf)")
    ] = False,
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


@app.command("backfill-works")
def backfill_works(
    per_anchor: Annotated[int, typer.Option(help="Max works per anchor")] = 80,
) -> None:
    """For each anchor, pull their last N works from OpenAlex and upsert Papers."""
    from .scraper.openalex_works import backfill_anchor_works

    c = backfill_anchor_works(per_anchor_limit=per_anchor)
    console.print(
        f"[green]✓[/green] backfill: anchors={c['anchors_processed']} · "
        f"+{c['papers_added']} papers · {c['papers_updated']} updated · "
        f"+{c['links_added']} co-author links · {c['errors']} errors"
    )


@app.command()
def score() -> None:
    """Compute person_score / trajectory_score / investability_score for all researchers."""
    from .scraper.scoring import compute_scores

    c = compute_scores()
    console.print(f"[green]✓[/green] scored {c['updated']} researchers")


@app.command("social-cards")
def social_cards() -> None:
    """Generate the 9 social SVG cards (today's top researchers) for sharing."""
    from .scraper.social_cards import write_daily_cards

    c = write_daily_cards()
    console.print(f"[green]✓[/green] wrote {c['cards']} cards to [cyan]{c['out_dir']}[/cyan]")


@app.command("classify-topics")
def classify_topics(
    topic: Annotated[str, typer.Option(help="topic slug to filter")] = "ai4sci",
    limit: Annotated[int, typer.Option(help="Max papers to check")] = 30,
) -> None:
    """LLM hard-filter for paper↔topic relevance (Anthropic; graceful skip)."""
    from .scraper.classify import filter_topic_papers

    c = filter_topic_papers(topic, limit=limit)
    if c.get("skipped_no_provider"):
        console.print(
            "[yellow]⚠[/yellow] no LLM provider configured — set ANTHROPIC_API_KEY "
            "or DEEPSEEK_API_KEY in .env"
        )
    else:
        console.print(
            f"[green]✓[/green] {topic}: kept {c['kept']} / removed {c['removed']} / "
            f"skipped_api_error {c.get('skipped_api_error', 0)} / checked {c['checked']}"
        )


@app.command("github-stars")
def github_stars(
    limit: Annotated[int, typer.Option(help="Max papers to scan")] = 30,
) -> None:
    """For papers with a GitHub code_url, fetch star count via GitHub API."""
    from .scraper.github_stars import fetch_stars

    c = fetch_stars(limit=limit)
    console.print(f"[green]✓[/green] github stars: {c['updated']} updated · {c['errors']} errors")


@app.command("send-digest")
def send_digest() -> None:
    """Send today's brief as HTML email via Resend (requires RESEND_API_KEY + NOTIFY_EMAIL_TO)."""
    from .scraper.email_digest import send_latest_digest

    r = send_latest_digest()
    if r.get("sent"):
        console.print(f"[green]✓[/green] sent digest for {r['brief_date']}")
    else:
        console.print(f"[yellow]⚠[/yellow] not sent: {r.get('reason')}")


@app.command("hf-papers")
def hf_papers(
    limit: Annotated[int, typer.Option(help="Max HF Daily Papers to ingest")] = 30,
) -> None:
    """Ingest HuggingFace Daily Papers (trending list). High-signal source."""
    from .scraper.huggingface import fetch_hf_daily

    c = fetch_hf_daily(limit=limit)
    console.print(
        f"[green]✓[/green] HF: fetched {c['fetched']} · added {c['added']} · "
        f"updated buzz on {c['updated']} · errors {c['errors']}"
    )


@app.command("conference-papers")
def conference_papers() -> None:
    """Ingest accepted papers from ICLR/NeurIPS/ICML via OpenReview API."""
    from .scraper.openreview_conf import fetch_all

    results = fetch_all()
    for venue, c in results.items():
        console.print(
            f"[green]✓[/green] {venue}: fetched {c['fetched']} · "
            f"+{c['added']} · {c['tiered']} oral/spotlight · errors {c['errors']}"
        )


@app.command("refresh-citations")
def refresh_citations(
    limit: Annotated[int, typer.Option(help="Top-N papers to refresh from OpenAlex")] = 100,
) -> None:
    """Refresh citation_count for top papers from OpenAlex."""
    from .scraper.citation_refresh import refresh_citation_counts

    c = refresh_citation_counts(limit=limit)
    console.print(
        f"[green]✓[/green] citations: checked {c['checked']} · "
        f"updated {c['updated']} · errors {c['errors']}"
    )


@app.command("code-urls")
def code_urls(
    limit: Annotated[int, typer.Option(help="Max papers to scan")] = 300,
) -> None:
    """Backfill paper.code_url by regex-scanning abstracts for github URLs."""
    from .scraper.code_urls import backfill_code_urls

    c = backfill_code_urls(limit=limit)
    console.print(
        f"[green]✓[/green] code_url: {c['matched']}/{c['checked']} papers got a github URL"
    )


@app.command("wikidata-photos")
def wikidata_photos(
    limit: Annotated[int, typer.Option(help="Max anchors to enrich")] = 40,
) -> None:
    """Fetch photo_url from Wikidata P18 via OpenAlex external ids."""
    from .scraper.wikidata import enrich_photos

    c = enrich_photos(limit=limit)
    console.print(
        f"[green]✓[/green] wikidata: {c['attempted']} attempted · "
        f"{c['found_wikidata']} had QIDs · +{c['found_photo']} photo_urls"
    )


@app.command("hf-models")
def hf_models(
    limit: Annotated[int, typer.Option(help="Max anchors to scan")] = 30,
) -> None:
    """Discover HuggingFace model releases by searching anchors' names."""
    from .scraper.hf_models import discover_models

    c = discover_models(limit=limit)
    console.print(
        f"[green]✓[/green] HF models: {c['hits']}/{c['attempted']} researchers had hits · "
        f"+{c['signals_added']} signals"
    )


@app.command("arxiv-html")
def arxiv_html(
    limit: Annotated[int, typer.Option(help="Max papers to scrape")] = 30,
) -> None:
    """Scrape arxiv.org/html/<id> for emails + code URLs (replaces PDF scraper)."""
    from .scraper.arxiv_html import scrape_papers

    c = scrape_papers(limit=limit)
    console.print(
        f"[green]✓[/green] arxiv HTML: {c['with_emails']} emails · "
        f"{c['with_code']} code URLs / {c['attempted']} attempted · "
        f"{c['no_html']} no html · {c['errors']} errors"
    )


@app.command("pwc")
def pwc(
    limit: Annotated[int, typer.Option(help="Max papers to enrich")] = 50,
) -> None:
    """Papers with Code lookup: code_url + github_stars from PwC's curated DB."""
    from .scraper.paperswithcode import enrich_papers

    c = enrich_papers(limit=limit)
    console.print(
        f"[green]✓[/green] PwC: {c['matched']}/{c['attempted']} matched · "
        f"+{c['got_repo']} code URLs · +{c['got_stars']} star counts"
    )


@app.command("dblp")
def dblp(
    limit: Annotated[int, typer.Option(help="Max anchors to look up")] = 30,
) -> None:
    """DBLP author lookup: store stable PIDs for cleaner cross-referencing."""
    from .scraper.dblp import enrich_anchors

    c = enrich_anchors(limit=limit)
    console.print(f"[green]✓[/green] DBLP: {c['found_pid']}/{c['attempted']} anchors got PIDs")


@app.command("alphaxiv")
def alphaxiv(
    limit: Annotated[int, typer.Option(help="Max papers to scan")] = 30,
) -> None:
    """alphaXiv comment-count buzz signal (lightweight community discussion proxy)."""
    from .scraper.alphaxiv import boost_from_alphaxiv

    c = boost_from_alphaxiv(limit=limit)
    console.print(
        f"[green]✓[/green] alphaXiv: {c['with_comments']}/{c['attempted']} papers with comments · "
        f"+{c['boosted']} boosted"
    )


@app.command()
def daily() -> None:
    """One-command full pipeline: ingest → enrich → score → brief → cards.

    Each step is isolated — one failure doesn't stop the rest. This is what
    the GitHub Actions cron should call once a day. Prints a colored summary
    of what succeeded / failed.
    """
    from .cli_daily import print_summary, run_daily

    steps = run_daily()
    n_failed = print_summary(steps)
    if n_failed:
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Health check: DB state, API keys, external service reachability, disk."""
    from .cli_doctor import run_doctor

    raise typer.Exit(run_doctor())


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
    if c.get("skipped_no_provider"):
        console.print(
            "[yellow]⚠[/yellow] no LLM provider configured — set ANTHROPIC_API_KEY "
            "or DEEPSEEK_API_KEY in .env"
        )
    else:
        console.print(
            f"[green]✓[/green] translated {c['translated']}/{c['attempted']} · "
            f"skipped_api_error {c.get('skipped_api_error', 0)} · errors {c['errors']}"
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
