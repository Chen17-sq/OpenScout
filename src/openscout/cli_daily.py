"""Single-command daily pipeline orchestrator.

`openscout daily` runs the full ingest → enrich → render flow. Each step is
isolated: a failure in one step doesn't stop the rest. The CLI prints a colored
summary at the end showing what succeeded / failed.

This is what GitHub Actions cron should call once a day.

Phase ordering (load-bearing — don't shuffle without thinking):
  1. Ingest — pull fresh content/people: arxiv, HF papers, awards rosters,
     news mentions, conference PC rolls, faculty hire pages. These create
     papers/signals/researcher rows that downstream phases enrich.
  2. Enrich researchers — OpenAlex institutions+anchors, then affiliation
     discovery to fill `current_affiliation_id` for any new researcher.
  3. Enrich papers — arxiv HTML (emails+code), code-URL regex, GitHub stars,
     citation refresh. Builds the signal feed work_score consumes.
  4. Researcher-level signals — twitter/zhihu profile scrape, Google Patents
     for industry-email researchers. Runs after enrich so handles/emails
     populated by enrich are available; runs before scoring so signals land.
  5. Derived — lineage, surname→country, peer inheritance, role inference,
     then scoring (work_score → investability_v2). MUST be last in the
     ingest-side so it scores fresh signals from phases 1–4.
  6. Deep-dive — top-N investability researchers get the 5-source pull.
     MUST be after scoring (it reads the rollup).
  7. LLM enrichment + render — translate, classify, brief, cards, banner,
     email digest.
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

    # ── Phase 1: ingest new content + people-source scrapers ──────────────
    # arxiv + HF feed papers; v1.11 awards/news/PC/faculty feed researchers
    # and signals. All run early so downstream enrich/score sees fresh rows.
    from .scraper.arxiv import ingest_topic

    for topic in ("embodied", "world_models", "ai4sci"):
        steps.append(_step(f"arxiv ingest [{topic}]", ingest_topic, topic_slug=topic, limit=50))

    from .scraper.huggingface import fetch_hf_daily

    steps.append(_step("hf daily papers", fetch_hf_daily, limit=30))

    # v1.11 ingest-class scrapers — each isolated via _step, so a broken
    # upstream feed never kills the rest. The three fixed-source scrapers
    # (awards / PC / faculty) take no `limit`; news caps via days+limit_papers.
    from .scraper.awards import scrape_awards
    from .scraper.conference_committees import scrape_conference_committees
    from .scraper.faculty_announcements import scrape_faculty_pages
    from .scraper.news_mentions import scan_news_mentions

    steps.append(_step("awards roster", scrape_awards))
    steps.append(_step("news mentions (RSS scan)", scan_news_mentions, days=7))
    steps.append(_step("conference PC/AC", scrape_conference_committees))
    steps.append(_step("faculty page diff", scrape_faculty_pages))

    # ── Phase 2: enrich researchers ────────────────────────────────────────
    from .scraper.openalex import enrich_all, resolve_institutions

    steps.append(_step("resolve institutions (new only)", resolve_institutions))
    steps.append(
        _step("enrich openalex (anchors)", enrich_all, limit=60, only_confidence=["high", "medium"])
    )

    from .scraper.openalex_works import backfill_anchor_works

    steps.append(_step("backfill anchor works", backfill_anchor_works, per_anchor_limit=20))

    # v1.11: affiliation discovery — fills current_affiliation_id for
    # researchers with openalex_id / s2_id but no resolved institution.
    # Runs right after OpenAlex enrich so it picks up freshly-set ids.
    from .scraper.affiliation_discovery import discover_affiliations

    steps.append(_step("affiliation discovery", discover_affiliations, limit=30))

    # ── Phase 3: enrich papers ─────────────────────────────────────────────
    from .scraper.arxiv_html import scrape_papers as arxiv_html_scrape

    steps.append(_step("arxiv HTML scrape (emails+code)", arxiv_html_scrape, limit=20))

    from .scraper.code_urls import backfill_code_urls

    steps.append(_step("code URL regex", backfill_code_urls, limit=300))

    from .scraper.github_stars import fetch_stars

    steps.append(_step("github stars", fetch_stars, limit=30))

    from .scraper.citation_refresh import refresh_citation_counts

    steps.append(_step("citation refresh", refresh_citation_counts, limit=60))

    # ── Phase 4: researcher-level signals ──────────────────────────────────
    # Run AFTER enrich (twitter handles + industry emails come from enrich)
    # and BEFORE scoring (signals must land before work_score reads them).
    from .scraper.patents import scrape_patents
    from .scraper.twitter import scrape_twitter
    from .scraper.zhihu import scrape_zhihu

    steps.append(_step("twitter / nitter scrape", scrape_twitter, limit=20))
    steps.append(_step("zhihu profile scrape", scrape_zhihu, limit=20))
    steps.append(_step("google patents", scrape_patents, limit=20))

    # ── Phase 5: compute derived data + scoring ────────────────────────────
    from .scraper.lineage import infer_lineage
    from .scraper.name_inference import infer_country_from_names
    from .scraper.openalex import assign_signature_papers
    from .scraper.peer_inference import infer_from_peers
    from .scraper.role_inference import infer_roles
    from .scraper.scoring import compute_scores
    from .scraper.work_scoring import compute_investability_v2, score_all_papers

    steps.append(_step("signature papers", assign_signature_papers))
    steps.append(_step("lineage inference", infer_lineage))
    # Cheap heuristic enrichment for the auto-discovered tail (v1.2 + v1.5)
    steps.append(_step("surname → country", infer_country_from_names))
    steps.append(_step("peer inheritance", infer_from_peers))
    steps.append(_step("publication-pattern → phd", infer_roles))
    steps.append(_step("compute scores (v1 legacy)", compute_scores))
    # v1.4 three-pillar Investment Lens — must run AFTER all paper signals are
    # in (citations, github stars, buzz, emails, twitter/zhihu/patents) so
    # work_score uses fresh data.
    steps.append(_step("work_score (3-pillar)", score_all_papers))
    steps.append(_step("investability_v2 rollup", compute_investability_v2))

    # ── Phase 6: deep-dive top investability researchers ───────────────────
    # MUST be after investability_v2 — it queues based on the rollup.
    from .scraper.deep_dive import auto_queue

    steps.append(_step("deep-dive queue (top 10)", auto_queue, limit=10))

    # ── Phase 7: optional LLM enrichment ───────────────────────────────────
    from .scraper.classify import filter_topic_papers
    from .scraper.translator import translate_papers

    steps.append(_step("translate (Claude)", translate_papers, limit=20))
    steps.append(
        _step(
            "topic classifier ai4sci (Claude)", filter_topic_papers, topic_slug="ai4sci", limit=20
        )
    )

    # ── Phase 8: render outputs ────────────────────────────────────────────
    from .brief.generate import generate_brief
    from .scraper.banner import write_banners
    from .scraper.social_cards import write_daily_cards

    steps.append(_step("daily brief markdown", generate_brief))
    steps.append(_step("9 social SVG cards", write_daily_cards))
    steps.append(_step("banner + og-card SVGs", write_banners))

    # ── Phase 9: optional email digest ─────────────────────────────────────
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
