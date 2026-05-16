"""Single-command daily pipeline orchestrator.

`openscout daily` runs the full ingest → enrich → render flow. Each step is
isolated: a failure in one step doesn't stop the rest. The CLI prints a colored
summary at the end showing what succeeded / failed.

This is what GitHub Actions cron should call once a day.
"""

import time
from collections.abc import Callable

from rich.console import Console

console = Console()


# Each step: (label, callable, kwargs). The callable is the imported function;
# kwargs are passed through. Wrapping keeps imports lazy so a broken module
# doesn't kill the whole pipeline at import time.
def _step(
    label: str,
    fn: Callable,
    /,
    **kwargs,
) -> dict[str, object]:
    # Live progress line — important when daily is piped (rich buffers
    # console.print() until process exit if stdout isn't a TTY).
    print(f"→ {label} ...", flush=True)
    start = time.monotonic()
    try:
        result = fn(**kwargs)
        elapsed = time.monotonic() - start
        print(f"  ✓ {label} ({elapsed:.1f}s)", flush=True)
        return {"label": label, "ok": True, "result": result, "elapsed_s": round(elapsed, 1)}
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"  ✗ {label} ({elapsed:.1f}s) — {type(exc).__name__}: {exc}", flush=True)
        return {
            "label": label,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(elapsed, 1),
        }


def run_daily() -> list[dict]:
    """Run the full daily pipeline in order. Returns a summary per step."""
    steps: list[dict] = []

    # ── Phase 1: ingest new content ────────────────────────────────────────
    from .scraper.arxiv import ingest_topic

    for topic in ("embodied", "world_models", "ai4sci"):
        steps.append(_step(f"arxiv ingest [{topic}]", ingest_topic, topic_slug=topic, limit=50))

    from .scraper.huggingface import fetch_hf_daily

    steps.append(_step("hf daily papers", fetch_hf_daily, limit=30))

    # ── Phase 2: enrich researchers ────────────────────────────────────────
    from .scraper.openalex import enrich_all, resolve_institutions

    steps.append(_step("resolve institutions (new only)", resolve_institutions))
    steps.append(
        _step("enrich openalex (anchors)", enrich_all, limit=60, only_confidence=["high", "medium"])
    )

    from .scraper.openalex_works import backfill_anchor_works

    steps.append(_step("backfill anchor works", backfill_anchor_works, per_anchor_limit=20))

    # ── Phase 3: enrich papers ─────────────────────────────────────────────
    from .scraper.arxiv_html import scrape_papers as arxiv_html_scrape

    steps.append(_step("arxiv HTML scrape (emails+code)", arxiv_html_scrape, limit=20))

    from .scraper.code_urls import backfill_code_urls

    steps.append(_step("code URL regex", backfill_code_urls, limit=300))

    from .scraper.github_stars import fetch_stars

    steps.append(_step("github stars", fetch_stars, limit=30))

    from .scraper.citation_refresh import refresh_citation_counts

    steps.append(_step("citation refresh", refresh_citation_counts, limit=60))

    # ── Phase 4: compute derived data ──────────────────────────────────────
    from .scraper.lineage import infer_lineage
    from .scraper.name_inference import infer_country_from_names
    from .scraper.openalex import assign_signature_papers
    from .scraper.peer_inference import infer_from_peers
    from .scraper.scoring import compute_scores
    from .scraper.work_scoring import compute_investability_v2, score_all_papers

    steps.append(_step("signature papers", assign_signature_papers))
    steps.append(_step("lineage inference", infer_lineage))
    # Cheap heuristic enrichment for the auto-discovered tail (v1.2)
    steps.append(_step("surname → country", infer_country_from_names))
    steps.append(_step("peer inheritance", infer_from_peers))
    steps.append(_step("compute scores (v1 legacy)", compute_scores))
    # v1.4 three-pillar Investment Lens — must run AFTER all paper signals are
    # in (citations, github stars, buzz, emails) so work_score uses fresh data.
    steps.append(_step("work_score (3-pillar)", score_all_papers))
    steps.append(_step("investability_v2 rollup", compute_investability_v2))

    # ── Phase 5: optional LLM enrichment ───────────────────────────────────
    from .scraper.classify import filter_topic_papers
    from .scraper.translator import translate_papers

    steps.append(_step("translate (Claude)", translate_papers, limit=20))
    steps.append(
        _step(
            "topic classifier ai4sci (Claude)", filter_topic_papers, topic_slug="ai4sci", limit=20
        )
    )

    # ── Phase 6: render outputs ────────────────────────────────────────────
    from .brief.generate import generate_brief
    from .scraper.banner import write_banners
    from .scraper.social_cards import write_daily_cards

    steps.append(_step("daily brief markdown", generate_brief))
    steps.append(_step("9 social SVG cards", write_daily_cards))
    steps.append(_step("banner + og-card SVGs", write_banners))

    # ── Phase 7: optional email digest ─────────────────────────────────────
    from .scraper.email_digest import send_latest_digest

    steps.append(_step("email digest (Resend)", send_latest_digest))

    return steps


def print_summary(steps: list[dict]) -> int:
    """Print a colored summary. Returns the count of failed steps."""
    n_ok = sum(1 for s in steps if s["ok"])
    n_fail = len(steps) - n_ok
    total_s = sum(s["elapsed_s"] for s in steps)

    console.print()
    console.print("[bold]Daily pipeline summary[/bold]")
    console.print("─" * 60)
    for s in steps:
        mark = "[green]✓[/green]" if s["ok"] else "[red]✗[/red]"
        console.print(f"{mark} {s['label']:<42} [cyan]{s['elapsed_s']:>5.1f}s[/cyan]")
        if not s["ok"]:
            console.print(f"     [red]{s['error']}[/red]")
    console.print("─" * 60)
    console.print(
        f"[bold]{n_ok}[/bold] succeeded · "
        f"{'[red]' if n_fail else ''}{n_fail} failed{'[/red]' if n_fail else ''} · "
        f"[cyan]{total_s:.1f}s total[/cyan]"
    )
    return n_fail
