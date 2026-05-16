<p align="center">
  <img src="web/static/banner.svg" alt="OpenScout — All The Researchers Fit To Watch.">
</p>

<p align="center">
  <strong><em>All The Researchers Fit To Watch.</em></strong><br>
  A daily newspaper for early-stage AI researchers — embodied AI, world models, AI for Science.
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-111111?style=for-the-badge"></a>
  <a href=".github/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/Chen17-sq/OpenScout/ci.yml?branch=main&style=for-the-badge&label=CI"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.11+-3776ab?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Node" src="https://img.shields.io/badge/node-22-339933?style=for-the-badge&logo=node.js&logoColor=white">
  <a href="https://github.com/Chen17-sq/OpenScout"><img alt="Stars" src="https://img.shields.io/github/stars/Chen17-sq/OpenScout?style=for-the-badge&color=CC0000"></a>
</p>

---

## What it does

OpenScout reverse-maps from papers to authors. Every morning at 09:00 Beijing
it ingests the previous 24 hours of **arXiv**, **HuggingFace Daily Papers**,
and **OpenReview**-tracked conferences (ICLR / NeurIPS / ICML), then enriches
every researcher from **OpenAlex** (h-index, citations, topic concepts, ORCID)
and **DBLP** (stable PIDs), cross-references with **Papers with Code**, and
pulls **arxiv.org/html/{id}** for contact emails. The output:

- A newsprint-style daily brief — Sections A–F: KPIs, new emergences, anchor
  activity, graduating PhDs, incoming faculty, hot papers, algorithmic
  Sleeper Picks.
- Per-researcher profiles with research-direction tags, signature paper,
  flagship projects, inferred advisor lineage, and contact emails.
- Filterable rosters by topic, country, citation rank, h-index.
- Conference accepted-paper view, institution rosters, tag cloud,
  side-by-side compare, archive of past briefs.
- RSS feeds, 9-image social cards, dynamic OG cards per researcher,
  print-friendly view, browser-local watchlist.

The chrome is bilingual (Chinese / English toggle). Paper titles and abstracts
stay in their original language; an LLM-generated Chinese one-liner appears
next to each card.

## Why

Investors covering early-career AI researchers face one problem: by the time
a paper trends on alphaXiv or the media picks it up, the window is closed.
The delta between *"this person is going to matter"* and *"everyone knows"*
is six months to a year. OpenScout aggressively backfills advisor → student
lineage so unknown junior names surface the moment they co-author with a
researcher already tracked.

## Inside this issue

| Surface | What | URL |
| --- | --- | --- |
| Live dashboard | Today's brief + roster | `/` |
| Researcher detail | Stage · affiliation · advisor · signature paper · tags · projects · contact | `/researchers/{slug}` |
| Compare | Side-by-side two researchers | `/compare?a=...&b=...` |
| Lineage tree | Advisor + students | `/researchers/{slug}/tree` |
| Paper detail | Authors · topics · emails · GitHub stars | `/papers/{arxiv_id}` |
| Conferences | By venue · oral / spotlight tinted | `/conferences` |
| Institutions | Roster by institution | `/institutions` |
| Tags | Tag cloud (font size by count) | `/tags` |
| Watchlist | Personal star, browser-local | `/watchlist` |
| Stats | KPIs · 7-day trend bars | `/stats` |
| Print | A4 print stylesheet | `/print/{date}` |
| Markdown brief | Permanent archive in repo | `reports/{date}.md` |
| RSS | Daily briefs · recent papers | `/rss/daily` · `/rss/papers` |
| 9-image grid | Social-share SVGs | `web/static/social/{date}/` |
| OG card | Per-researcher 1200×630 | `/og/researchers/{slug}.svg` |

## Live snapshot

Output of `openscout doctor` on the dev box at v1.0:

```
Papers              714
  ├─ with emails    105     (extracted from arxiv.org/html/<id>)
  └─ with code_url   64     (regex + Papers with Code)
Researchers       2,168
  └─ anchors          67    (curated + OpenAlex-verified)
Paper-author links 2,561
Advisor edges        55    (co-author × same-country × h-index)
SQLite DB         1.9 MB
External services   all 7 ✓ HTTP 200
```

## Data sources

OpenScout doesn't run its own crawlers when an aggregator exists. Every source
exposes a public API or HTML view; each is hit politely (rate-limited, UA-tagged).

| Source | What we pull | Rate | Notes |
| --- | --- | --- | --- |
| arXiv API | new papers per topic | ~3 req/s soft | via the `arxiv` Python lib |
| arXiv HTML (`arxiv.org/html/<id>`) | author emails · code URLs | 1 req/s | replaces PDF parsing |
| OpenAlex | author IDs · h-index · citations · concepts | 100k req/day | polite-pool email |
| OpenReview | ICLR / NeurIPS / ICML accepted + tier | soft | `api2.openreview.net/notes` |
| HuggingFace Daily Papers | trending list + upvotes | open | `huggingface.co/api/daily_papers` |
| HuggingFace Models | per-anchor model releases | open | search by author name |
| Papers with Code | paper → code + stars | open | `paperswithcode.com/api/v1` |
| DBLP | stable author PIDs | open | `dblp.org/search/author/api` |
| Wikidata | researcher photos (P18) | open | when OpenAlex has the QID |
| GitHub | repo star counts | 60 / hr unauth | bump with `GITHUB_TOKEN` |
| DeepSeek | Chinese one-liner · topic filter | pay-go | $0.14 / $0.28 per 1M tokens |
| Anthropic Claude | same (alternate) | pay-go | switch via `LLM_PROVIDER` |
| Resend | daily digest email | 100 / day free | optional |

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | SvelteKit 2 · Svelte 5 · Tailwind 4 · `marked` |
| Backend | FastAPI · SQLAlchemy 2 · Pydantic 2 · `psycopg` / sqlite |
| DB | SQLite (local) → Postgres 16 + pgvector (prod) |
| Scrapers | `pyalex` · `httpx` · `selectolax` · `pypdf` · `arxiv` |
| LLM | DeepSeek or Anthropic Claude — unified `llm.complete()` |
| Cron | GitHub Actions → `POST /admin/ingest` |
| Tests | pytest (31 unit) · ruff format / lint · svelte-check |

## Quick start

```bash
git clone https://github.com/Chen17-sq/OpenScout.git
cd OpenScout

# Backend
uv sync --all-extras
uv run openscout init-db
uv run openscout seed

# Optional: pick an LLM provider (DeepSeek or Anthropic)
echo "DEEPSEEK_API_KEY=sk-..." >> .env
echo "LLM_PROVIDER=deepseek"   >> .env

# Full daily pipeline (ingest → enrich → score → render)
uv run openscout daily

# Frontend
cd web && npm install && npm run dev      # http://localhost:5174
```

`openscout doctor` reports DB state, key availability, external-service
reachability, and disk usage. Run it whenever something looks off.

## Pipeline

`openscout daily` runs this sequence; each step is isolated so a single
failure does not stop the rest. The exit code is the count of failed steps.

```
Phase 1 — ingest
  arxiv (embodied)   →  arxiv (world_models)  →  arxiv (ai4sci)  →  HF daily

Phase 2 — researcher enrichment
  resolve-institutions  →  enrich-openalex (anchors)  →  backfill-anchor-works

Phase 3 — paper enrichment
  arxiv-html (emails, code)  →  code_url regex  →  github-stars  →  citation refresh

Phase 4 — derived
  signature-papers  →  lineage  →  scoring

Phase 5 — LLM (auto-skip without provider key)
  translate (Chinese one-liner)  →  classify (topic relevance)

Phase 6 — render
  daily brief markdown  →  9 social SVG cards  →  banner + og-card

Phase 7 — distribute (optional)
  email digest via Resend
```

## CLI

```
make api / make web / make dev     # FastAPI :8000 · SvelteKit :5174 · both

openscout init-db                  # create tables + run idempotent migrations
openscout seed                     # load seeds/*.yaml
openscout doctor                   # health check
openscout daily                    # full pipeline

# ingest
openscout ingest --topic embodied --limit 50
openscout hf-papers --limit 30
openscout conference-papers
openscout backfill-works

# enrichment
openscout enrich-openalex --only-anchors
openscout resolve-institutions
openscout arxiv-html
openscout code-urls
openscout github-stars
openscout pwc
openscout dblp
openscout refresh-citations
openscout wikidata-photos
openscout hf-models

# compute
openscout signature-papers
openscout lineage
openscout score

# llm
openscout translate-papers
openscout classify-topics --topic ai4sci

# render / distribute
openscout brief
openscout banner
openscout social-cards
openscout send-digest              # needs RESEND_API_KEY
```

## Architecture

```
       ┌──────────────────────────────────────────────────────┐
       │  arXiv · HF · OpenReview · OpenAlex · DBLP · PwC ·   │
       │  Wikidata · GitHub · Resend                          │
       └──────────────────────┬───────────────────────────────┘
                              │
                              ▼
       ┌──────────────────────────────────────────────────────┐
       │  scraper/*  — one module per source, all idempotent  │
       └──────────────────────┬───────────────────────────────┘
                              ▼
                       ┌──────────────┐
                       │  SQLite /    │
                       │  Postgres    │
                       └──────┬───────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  ┌────────────┐       ┌─────────────┐        ┌──────────────┐
  │ brief/     │       │ api/        │        │ web/         │
  │ generate.py│       │ FastAPI     │ ◀───── │ SvelteKit    │
  │ → markdown │       │ /briefs     │        │ pages        │
  └─────┬──────┘       │ /researchers│        └──────────────┘
        │              │ /og/*.svg   │
        ▼              └─────────────┘
  reports/{date}.md
```

Core tables: `researchers · papers · institutions · topics · paper_authors ·
paper_topics · researcher_topics · relationships · affiliations · signals ·
daily_briefs`.

## Configuration

API keys and secrets are looked up in this order:

1. Shell environment variable
2. `OpenScout/.env` (gitignored)
3. macOS Keychain — `service=OpenScout`, account = key name

Layer 3 survives re-cloning the repo. On non-macOS hosts it is silently skipped.

```bash
# Persist a key in Keychain (Touch-ID protected after first unlock):
security add-generic-password -s OpenScout -a DEEPSEEK_API_KEY -w "sk-..."

# Or set it in CI:
gh secret set DEEPSEEK_API_KEY -R Chen17-sq/OpenScout
```

## Roadmap

**Shipped in v1.0**
- All ingest pipelines · LLM abstraction (DeepSeek / Anthropic interchangeable)
- 11 page routes · search · watchlist · compare · lineage tree
- Pre-commit · pytest · CI

**Next**
- Postgres + pgvector for production (current SQLite caps comfortably at ~10k researchers)
- Twitter / X paper-announcement scraper
- D3 force-directed lineage graph (current view is a text tree)
- Conference rebuttal / acceptance-probability signals

**Deliberately out of scope**
- CRM features (notes, ratings) — this is a display layer, not workflow
- Lead-gen / outreach automation — emails surface for manual research, not bulk-send

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Especially welcome:

- New anchor researchers in `seeds/researchers.yaml`
- New seed institutions or topics
- New aggregator sources

The "do not guess Chinese names" rule is firm — only add `name_zh` when
verified from a source the researcher controls (their homepage, paper byline,
or a column they author). The OpenAlex enricher fills the rest where it can.

## Acknowledgments

The newsprint visual language is borrowed from
[kickstarter-china-tracker](https://github.com/Chen17-sq/kickstarter-china-tracker),
the sister project this one was prototyped against. Heavy reliance on
[OpenAlex](https://openalex.org), [pyalex](https://github.com/J535D165/pyalex),
[DBLP](https://dblp.org), [Papers with Code](https://paperswithcode.com),
[HuggingFace](https://huggingface.co/papers), and
[OpenReview](https://openreview.net).

## License

[MIT](LICENSE)
