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

Per-step freshness gate (v1.13):
  Each `_step()` call accepts `min_hours=N`. If the step's last successful
  run is within `min_hours`, it's skipped and reported as "skipped (fresh)".
  See `scraper/step_log.py`. Use `--force` to override; `--only` / `--skip`
  to filter steps by substring match against the label.
"""

import contextlib
import time
from collections.abc import Callable

from rich.console import Console

from .scraper import step_log

console = Console()


# ── module-level filter state ──────────────────────────────────────────────
# Filled by `run_daily(only=..., skip=..., force=...)` before iteration. The
# `_step()` wrapper reads these to decide whether to actually call the fn.
# Kept module-level (not a class) to avoid threading state through every
# import line below.
_only_terms: list[str] = []
_skip_terms: list[str] = []
_force: bool = False


# Each step: (label, callable, kwargs). The callable is the imported function;
# kwargs are passed through. Wrapping keeps imports lazy so a broken module
# doesn't kill the whole pipeline at import time.
def _step(
    label: str,
    fn: Callable,
    /,
    *,
    min_hours: float = 0.0,
    **kwargs,
) -> dict[str, object]:
    """Wrap a single pipeline step.

    Skip logic, in order:
      1. `--only` was given AND label doesn't match any term → skipped (not selected)
      2. `--skip` was given AND label matches a term → skipped (excluded)
      3. `min_hours > 0` AND last OK run within window AND not --force → skipped (fresh)

    Otherwise: run the fn, record the result to `step_log`, return the row.
    """
    # 1. --only filter
    if _only_terms and not _match_any(label, _only_terms):
        print(f"⊘ {label} (not in --only)", flush=True)
        return {
            "label": label,
            "ok": True,
            "skipped": True,
            "skip_reason": "not in --only",
            "elapsed_s": 0.0,
        }

    # 2. --skip filter
    if _skip_terms and _match_any(label, _skip_terms):
        print(f"⊘ {label} (in --skip)", flush=True)
        return {
            "label": label,
            "ok": True,
            "skipped": True,
            "skip_reason": "in --skip",
            "elapsed_s": 0.0,
        }

    # 3. freshness gate
    if not _force and min_hours > 0 and step_log.should_skip(label, min_hours):
        last = step_log.last_run(label)
        last_str = last.isoformat(timespec="minutes") if last else "?"
        msg = f"fresh (last ok {last_str}, gate={min_hours:.0f}h)"
        print(f"⊘ {label} ({msg})", flush=True)
        # Record as 'skipped' so the dashboard can show why; doesn't reset
        # last_status='ok' so future runs still see freshness.
        return {
            "label": label,
            "ok": True,
            "skipped": True,
            "skip_reason": msg,
            "elapsed_s": 0.0,
        }

    # Live progress line — important when daily is piped (rich buffers
    # console.print() until process exit if stdout isn't a TTY).
    print(f"→ {label} ...", flush=True)
    start = time.monotonic()
    try:
        result = fn(**kwargs)
        elapsed = time.monotonic() - start
        print(f"  ✓ {label} ({elapsed:.1f}s)", flush=True)
        # Record success — gates future freshness skips. Wrap in try because
        # a logging failure must NEVER take down the pipeline.
        try:
            step_log.record(label, "ok", result)
        except Exception as log_exc:  # noqa: BLE001
            print(f"  ⚠ step_log record failed: {log_exc}", flush=True)
        return {"label": label, "ok": True, "result": result, "elapsed_s": round(elapsed, 1)}
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"  ✗ {label} ({elapsed:.1f}s) — {type(exc).__name__}: {exc}", flush=True)
        with contextlib.suppress(Exception):
            step_log.record(label, "failed", {"error": f"{type(exc).__name__}: {exc}"})
        return {
            "label": label,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(elapsed, 1),
        }


def _match_any(label: str, terms: list[str]) -> bool:
    """Case-insensitive substring match — `terms` is a list of CLI tokens."""
    low = label.lower()
    return any(t and t.lower() in low for t in terms)


def run_daily(
    only: list[str] | None = None,
    skip: list[str] | None = None,
    force: bool = False,
) -> list[dict]:
    """Run the full daily pipeline in order. Returns a summary per step.

    Args:
        only: if non-empty, ONLY run steps whose label matches any of these
              (case-insensitive substring). Overrides freshness gates by
              implication — you asked for these, you get them.
        skip: skip steps whose label matches any of these.
        force: ignore the per-step freshness gate (`min_hours`).
    """
    global _only_terms, _skip_terms, _force
    _only_terms = [t for t in (only or []) if t]
    _skip_terms = [t for t in (skip or []) if t]
    _force = force

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
    # Freshness gates applied: faculty page diffs change ~weekly, conference
    # PC rolls update monthly, award rosters mostly post-conference.
    from .scraper.awards import scrape_awards
    from .scraper.conference_committees import scrape_conference_committees
    from .scraper.faculty_announcements import scrape_faculty_pages
    from .scraper.news_mentions import scan_news_mentions

    steps.append(_step("awards roster", scrape_awards, min_hours=168))
    steps.append(_step("news mentions (RSS scan)", scan_news_mentions, days=7))
    steps.append(_step("conference PC/AC", scrape_conference_committees, min_hours=720))
    steps.append(_step("faculty page diff", scrape_faculty_pages, min_hours=168))

    # ── Phase 2: enrich researchers ────────────────────────────────────────
    from .scraper.openalex import enrich_all, resolve_institutions

    # Institution resolution is mostly a one-off — only re-run weekly to pick
    # up new seed rows (institutions.yaml).
    steps.append(_step("resolve institutions (new only)", resolve_institutions, min_hours=168))
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
    # Lineage is idempotent and slow; only really shifts when >50 new
    # anchor-coauthor edges land, which empirically takes ~2 days.
    steps.append(_step("lineage inference", infer_lineage, min_hours=48))
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
    # Banner re-render is daily by default, but cheap to skip if nothing
    # changed in last 24h. The 24h gate matches the cron cadence.
    steps.append(_step("banner + og-card SVGs", write_banners, min_hours=24))

    # ── Phase 9: optional email digest ─────────────────────────────────────
    from .scraper.email_digest import send_latest_digest

    steps.append(_step("email digest (Resend)", send_latest_digest))

    return steps


def print_summary(steps: list[dict]) -> int:
    """Print a colored summary. Returns the count of failed steps.

    Skipped steps appear separately at the top so they don't get lost in the
    main list — useful when you ran with --only / --skip and want to confirm
    the filter did what you expected.
    """
    skipped = [s for s in steps if s.get("skipped")]
    ran = [s for s in steps if not s.get("skipped")]
    n_ok = sum(1 for s in ran if s["ok"])
    n_fail = sum(1 for s in ran if not s["ok"])
    n_skip = len(skipped)
    total_s = sum(s["elapsed_s"] for s in steps)

    console.print()
    console.print("[bold]Daily pipeline summary[/bold]")
    console.print("─" * 60)

    if skipped:
        console.print(f"[yellow]Skipped ({n_skip}):[/yellow]")
        for s in skipped:
            console.print(
                f"  [yellow]⊘[/yellow] {s['label']:<42} [dim]{s.get('skip_reason', '')}[/dim]"
            )
        console.print("─" * 60)

    for s in ran:
        mark = "[green]✓[/green]" if s["ok"] else "[red]✗[/red]"
        console.print(f"{mark} {s['label']:<42} [cyan]{s['elapsed_s']:>5.1f}s[/cyan]")
        if not s["ok"]:
            console.print(f"     [red]{s['error']}[/red]")
    console.print("─" * 60)
    console.print(
        f"[bold]{n_ok}[/bold] succeeded · "
        f"{'[red]' if n_fail else ''}{n_fail} failed{'[/red]' if n_fail else ''} · "
        f"[yellow]{n_skip}[/yellow] skipped · "
        f"[cyan]{total_s:.1f}s total[/cyan]"
    )
    return n_fail
