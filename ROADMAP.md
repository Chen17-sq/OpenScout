# OpenScout Roadmap — to Production

Status: 2026-05-17. We're at v1.10 with a working investor-facing local app.
The gap to production is: (1) **rate-limit deep-dive** so it can't be abused,
(2) **deploy** frontend + backend somewhere with HTTPS, (3) **fill the data
coverage holes** still visible in user testing (institution, news mentions,
faculty announcements, etc.).

Track this file in repo. Update as items ship. Each line tagged with:

- **S / M / L** — complexity (≤2h / ½–1 day / >1 day)
- **P** if parallelizable to a subagent (touches only new files)
- **D:** dep on another item

---

## Tier 0 — production-blocking (must ship before launch)

### Backend & data

- [ ] **0.1 Rate limit deep-dive endpoint** (S, P) — `POST /researchers/{slug}/deep-dive` currently has no quota. Bake in: per-IP (or per-user once auth lands) **3 dives/day**, reset at midnight UTC. Use SQLite table `deep_dive_quota(ip, day, count)`. Return 429 + `Retry-After` when exceeded. New file: `src/openscout/api/quota.py`.
- [ ] **0.2 Background-job deep-dive** (M) — current dive is synchronous (~30s blocks the API). Move to a queue: enqueue → return job_id → poll `/jobs/{id}` for status. New module: `src/openscout/scraper/jobs.py` using SQLite for queue (Postgres-ready abstraction later). Frontend polls every 2s + shows per-source progress.
- [ ] **0.3 SSE streaming for deep-dive** (M, D:0.2) — once async, stream each source completion to the browser. New endpoint: `GET /researchers/{slug}/deep-dive/stream`. UI updates the per-source ✓/✗ list incrementally instead of waiting for the full result.
- [ ] **0.4 Switch from SQLite → Postgres** (L) — needed for any production traffic (SQLite locks on concurrent writes). New: `alembic` migrations replacing our hand-rolled `migrations.py`. Test that all queries work on PG. Set up local docker-compose for PG.
- [ ] **0.5 Affiliation discovery** (M, P) — most auto-discovered researchers have null `current_affiliation_id`. New source `_affiliation_discover` in `deep_dive.py`: use S2 author affiliations + OpenAlex `last_known_institution` + Institution-name fuzzy-match to existing Institution rows. Triggers the institution tag.
- [ ] **0.6 Daily cron is reliable** (S) — verify GitHub Actions cron still fires; add Sentry-ish alert if any phase fails.

### Frontend & UX

- [ ] **0.7 `/investment` dedicated page** (M, P) — currently 8 picks on homepage; want a full page with: filter by signal (🔥 / 🚀 / 🎓), filter by country, filter by topic tag, pagination, CSV export. New file: `web/src/routes/investment/+page.svelte` + `.ts`.
- [ ] **0.8 Mobile-responsive audit** (M) — test every page at 375px width; fix horizontal scroll, oversized headings, tap targets <44px. Brand chrome (Playfair / Lora / Inter) preserved.
- [ ] **0.9 Public/anonymous demo mode** (S) — visitors without auth see same data but deep-dive button → "Sign in for deep-dive (free, 3/day)". Hides nothing else.

### Infrastructure

- [ ] **0.10 Deploy frontend** (S, P) — Vercel or Cloudflare Pages. Set `VITE_API_BASE` env var to the deployed API URL. Hook GitHub auto-deploy on push to main.
- [ ] **0.11 Deploy backend** (M, D:0.4) — Fly.io or Render. Set env vars (DEEPSEEK_API_KEY, SEMANTIC_SCHOLAR_API_KEY, GITHUB_TOKEN, RESEND_API_KEY, INGEST_SECRET). PG attached. Daily cron either there or via GitHub Actions hitting the deployed `/admin/ingest`.
- [ ] **0.12 Domain + HTTPS** (S, D:0.10,0.11) — register `openscout.io` or similar; set DNS to Vercel + backend service.
- [ ] **0.13 Error tracking** (S, P) — Sentry SDK on both frontend + backend. Free tier covers low traffic.

### Quality

- [ ] **0.14 Cleanup duplicate researchers** (M) — same person with slightly different names (e.g. `xinyi-wang` and `xinyi-wang-2`). Script: find slugs with same OpenAlex ID or S2 ID, merge under one. Move all PaperAuthor links to the survivor.
- [ ] **0.15 Handle `or-xxx` papers** (S) — OpenReview synthetic IDs route to `/papers/{id}` internal page. Currently the page exists but renders little. Pull title + abstract from OpenReview API.

---

## Tier 1 — high-value features (ship within 2 weeks of launch)

### New data sources (each = new scraper file, parallel-safe)

- [ ] **1.1 Twitter/X bio scraper** (M, P) — use snscrape or a free wrapper. For each researcher with a known twitter_handle, pull bio + last 5 tweets mentioning AI/research keywords. New: `src/openscout/scraper/twitter.py`.
- [ ] **1.2 知乎 profile scraper** (M, P) — for CN researchers, 知乎 has biographical info Western sources miss. Scrape if `r.zhihu_url` set. New: `src/openscout/scraper/zhihu.py`.
- [ ] **1.3 News mentions scraper** (M, P) — scan 36氪 / TechCrunch / The Information for paper IDs or researcher names. If hit, store as Signal + bump buzz_score. New: `src/openscout/scraper/news_mentions.py`.
- [ ] **1.4 University faculty hire pages** (L, P) — top schools publish incoming-AP lists each May/June. Scrape MIT, Stanford, CMU, Berkeley, Tsinghua, PKU, SJTU faculty pages, match names → set `current_role=incoming_ap` + announce date. New: `src/openscout/scraper/faculty_announcements.py`.
- [ ] **1.5 Google Patents API** (M, P) — for industry-affiliated researchers, list their patents. Strong commercial signal (the user's pillar #2). New: `src/openscout/scraper/patents.py`.
- [ ] **1.6 Crunchbase / 天眼查 funding signal** (L, P) — if researcher's name OR github-org appears as founder/CTO of a recently-funded startup, that's the holy grail. New: `src/openscout/scraper/startups.py`. Crunchbase needs paid API; start with open data (Wikipedia infoboxes, news scraping).
- [ ] **1.7 Conference PC / area-chair membership** (M, P) — being on NeurIPS / ICLR / ICML program committee is a strong status signal. Scrape OpenReview conference pages for committee lists. New: `src/openscout/scraper/conference_committees.py`.
- [ ] **1.8 Academic awards** (M, P) — ACM Doctoral Dissertation, NSF CAREER, MIT TR35, etc. Each has a webpage with recipient names. Scrape annually. New: `src/openscout/scraper/awards.py`.

### Personalization & auth

- [ ] **1.9 Magic-link auth** (M) — email-only sign in via Resend. Store user → email mapping. Replaces IP-based rate limit with per-user. New: `src/openscout/api/auth.py` + `users` table.
- [ ] **1.10 Saved searches / Watchlist v2** (M, D:1.9) — let logged-in users save filter combinations and get email digests when new researchers match.
- [ ] **1.11 Per-user investment lens settings** (S, D:1.9) — user can save preferred topics (具身/世界模型/AI4Sci weights), country filter, role filter. Investment Lens uses their weights.

### Frontend

- [ ] **1.12 Researcher comparison page** (M, P) — `/compare?a=slug1&b=slug2` already exists per file listing; verify it works and add the new pillar scores side-by-side.
- [ ] **1.13 Tag pages** (M, P) — `/tags/<label>` lists all researchers with that tag, ordered by investability_v2. Already partially exists; add signal-tag filtering.
- [ ] **1.14 Institution detail page** (M, P) — `/institutions/<id>` shows all researchers there + topic breakdown. Exists; needs the new signal tags surfaced.
- [ ] **1.15 PDF / print edition** (M, P) — `/print/<date>` for the daily brief; verify it works well at A4 and via "save as PDF".
- [ ] **1.16 Onboarding tour** (S, P) — first-visit popover: "OpenScout finds early-career AI researchers worth investing in." Three steps explaining the Investment Lens pillars.

### Quality

- [ ] **1.17 Better disambiguation for common names** (L) — currently "Yi Wang" maps to one Researcher row; in reality 10+ people share that name. Use OpenAlex ID + email domain as the primary unique key when present; treat name-only as low confidence.
- [ ] **1.18 Photo discovery** (M, P) — Wikidata P18 already covered; also pull from GitHub avatar + S2 author profile photo. New source in `deep_dive.py`.
- [ ] **1.19 Pin/star researcher UX** (S) — already have StarButton component; verify the watchlist page renders correctly and stars persist via localStorage (or per-user DB once auth lands).

---

## Tier 2 — nice-to-haves (post-launch backlog)

- [ ] **2.1 Vector search (pgvector)** — semantic search on paper abstracts. `Find researchers working on diffusion + robotics` instead of keyword grep.
- [ ] **2.2 RSS / Atom feeds** — exist already (`/rss/daily`, `/rss/papers`); verify content quality.
- [ ] **2.3 OG / social cards** — verified for each researcher (existing `og.py`); add the Investment Lens score to the card.
- [ ] **2.4 OpenAPI docs** — FastAPI auto-generates; expose at `/docs` publicly + link from README.
- [ ] **2.5 Plausible / PostHog analytics** — track which researchers get the most clicks → feed back into ranking heuristics.
- [ ] **2.6 i18n: full Traditional Chinese support** — currently zh = Simplified. Add `zh-TW` toggle.
- [ ] **2.7 Hong Kong / Taiwan / Singapore expansion** — corporate-email domains list + institution seeds need their universities.
- [ ] **2.8 Slack / WeChat bot** — push daily Investment Lens picks to a channel.
- [ ] **2.9 Multi-investor mode (Pro)** — multiple users can share a watchlist + annotate researchers.
- [ ] **2.10 Researcher → startup match** — when a researcher leaves academia and starts a company, alert.
- [ ] **2.11 Citation-velocity tracker** — paper-level "this paper went from 10 → 200 cites in 3 months" alert.
- [ ] **2.12 arXiv withdrawal / retraction tracker** — negative signal for the paper (and the researcher's other work).

---

## Parallel subagent fan-out plan

Subagents can run in parallel safely ONLY when they touch **distinct files**. The
matrix below assigns each Tier-0/1 task to a stream. Each stream is sequential
(one task at a time); streams run in parallel.

| Stream | Owns these files | First task | Then |
|---|---|---|---|
| **A — Quota & jobs** | `api/quota.py`, `scraper/jobs.py`, modify `api/routes/researchers.py` | 0.1 rate limit | 0.2 bg jobs → 0.3 SSE |
| **B — Postgres** | `alembic/`, `db.py`, `docker-compose.yml` | 0.4 PG migration | nothing else |
| **C — Deploy** | `vercel.json`, `fly.toml`, `Dockerfile`, GitHub Actions workflow | 0.10 frontend deploy | 0.11 backend → 0.12 domain |
| **D — Sources: Twitter** | `scraper/twitter.py` | 1.1 | (none) |
| **E — Sources: 知乎** | `scraper/zhihu.py` | 1.2 | (none) |
| **F — Sources: News** | `scraper/news_mentions.py` | 1.3 | (none) |
| **G — Sources: Faculty** | `scraper/faculty_announcements.py` | 1.4 | (none) |
| **H — Sources: Patents** | `scraper/patents.py` | 1.5 | (none) |
| **I — Sources: Awards** | `scraper/awards.py` | 1.8 | (none) |
| **J — Sources: PC/AC** | `scraper/conference_committees.py` | 1.7 | (none) |
| **K — Frontend: /investment** | `web/src/routes/investment/` | 0.7 | 1.13 tag pages |
| **L — Frontend: mobile audit** | only CSS / responsive media queries | 0.8 | 1.16 onboarding |
| **M — Auth & users** | `api/auth.py`, `users` table migration | 1.9 magic link | 1.10 watchlist v2 → 1.11 personal settings |
| **N — Quality: dedupe** | `scraper/dedupe.py` + CLI | 0.14 dup researchers | 1.17 disambig |
| **O — Quality: affiliation** | new source in `scraper/deep_dive.py` (additive, append-only) | 0.5 affiliation discovery | 1.18 photo discovery |
| **P — Errors/monitoring** | `api/sentry.py`, web hook | 0.13 Sentry | (none) |

**Integration step** (NOT parallelizable, the orchestrator does it at the end of each round):

- Register new scrapers in `cli.py` (each as `openscout <name>` command)
- Register new routes in `api/main.py`
- Register new sources in `deep_dive.SOURCES` registry
- Run `init-db` to apply any new migrations
- One commit per stream

**Conflict-prone files** (do NOT let two agents touch in one round):
- `src/openscout/models.py` (schema)
- `src/openscout/migrations.py` (schema)
- `src/openscout/cli.py` (Typer registry)
- `src/openscout/cli_daily.py` (daily orchestrator)
- `src/openscout/api/main.py` (FastAPI router registry)
- `src/openscout/api/routes/researchers.py` (the heavy file)
- `web/src/lib/translations.ts` (bilingual labels)
- `web/src/routes/researchers/[slug]/+page.svelte` (researcher detail)

Treatment: orchestrator opens these files itself when integrating.

---

## "Specific person" deep-mode (what the user asked for)

Beyond the 11-source deep-dive, a **per-person deep-mode** would let the
investor zero in on one researcher and burn API quota on them:

1. **Read every paper they've first-authored** (full PDF text via arxiv HTML).
2. **LLM extracts**: thesis topic, advisor name, method novelty per paper,
   commercial readiness (TRL estimate).
3. **Network graph**: co-author + advisor + student edges, 2-hop visualized.
4. **News / blog mention search** by name across the past 12 months.
5. **GitHub repo deep-read** if they have a popular repo: README, contributors,
   star history, fork tree.
6. **Email outreach draft** (with disclaimer + signature line for the investor).

This is the next big feature after Tier 0 ships. Captured here so we don't
forget.

---

## To-do (live, untracked)

Things I noticed during dev that haven't been formally ticketed:

- Some researchers have `current_affiliation_id = null` but a perfectly good
  affiliation visible in their bio (`"MIT · (per Semantic Scholar)"`). The
  bio-extracted affiliation should be resolved against `institutions` table.
- The `WildClawBench` paper has citation_count = 0 even though it's the
  signature paper for several Chinese PhDs. Refresh-citations cron should pick
  up but verify.
- Deep-dive's `huggingface_profile` source still emits a Signal row when
  model_count==0 (from before v1.7 fix); old signals should be purged.
- The `Researcher.h_index` for Shuangrui jumped 0 → 19 in one S2 dive. Ensure
  the `investability_v2` rollup picked it up — visually his card on the home
  page should now show a stronger 🔥 signal-tag.

---

Last updated: 2026-05-17 by the v1.10 ship.
