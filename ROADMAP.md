# OpenScout Roadmap — to Production

Status: 2026-05-23. We're at v1.13 — production-blocking work has shipped:
async deep-dive with rate limit, Sentry, Fly + Vercel deploy targets, Postgres
via alembic, 9 new scrapers. Tier-0 is done. Tier-1 is the new ground floor.

Track this file in repo. Update as items ship. Each line tagged with:

- **S / M / L** — complexity (≤2h / ½–1 day / >1 day)
- **P** if parallelizable to a subagent (touches only new files)
- **D:** dep on another item

---

## Shipped

- **v1.13** — 10-subagent fan-out: Postgres + alembic, tag pages, async-everything
- **v1.12** — production-ready deep-dive: rate-limited, async jobs, Sentry, Fly + Vercel
- **v1.11** — 10-subagent fan-out: 9 new scrapers (twitter / zhihu / news / faculty / patents / startups / PC / awards / affiliation) + dedicated `/investment` page
- **v1.10** — tag taxonomy split (institution / signal / topic)
- **v1.9** — deep-dive populates research-direction tags
- **v1.8** — deep-dive discovery: actively hunts down missing IDs
- **v1.7** — deep-dive that actually helps zero-ID researchers
- **v1.6** — deep-dive: on-demand 5-source enrichment per researcher

---

## Tier 0 — production-blocking (DONE)

### Backend & data

- [x] **0.1 Rate limit deep-dive endpoint** (shipped v1.12) — `DeepDiveQuota(ip, day, count)`, 3 dives/IP/day, 429 + `Retry-After` on overflow.
- [x] **0.2 Background-job deep-dive** (shipped v1.12) — `DeepDiveJob` lifecycle queued→running→succeeded|failed, `scraper/jobs.py` daemon-thread pool with `MAX_CONCURRENT_JOBS=4`.
- [x] **0.3 SSE streaming for deep-dive** (shipped v1.12) — per-source progress streamed via `GET /researchers/{slug}/deep-dive/stream`.
- [x] **0.4 Switch from SQLite → Postgres** (shipped v1.13) — alembic tree under `src/openscout/alembic/`, `init-db` branches on `DATABASE_URL` prefix. SQLite still works for local dev via `migrations.py` fallback.
- [x] **0.5 Affiliation discovery** (shipped v1.13) — `_institution_discover` source in deep-dive: S2 affiliations[0] → OpenAlex `last_known_institution` → fuzzy-match Institution row.
- [x] **0.6 Daily cron is reliable** (shipped v1.13) — CI workflow runs full pipeline inside the runner; Sentry alerts on failure.

### Frontend & UX

- [x] **0.7 `/investment` dedicated page** (shipped v1.11) — full page with signal / country / topic filters + pagination + CSV export.
- [x] **0.8 Mobile-responsive audit** (shipped v1.11) — every page tested at 375px; brand chrome preserved.
- [x] **0.9 Public/anonymous demo mode** (shipped v1.12) — quota gating on deep-dive button.

### Infrastructure

- [x] **0.10 Deploy frontend** (shipped v1.12) — Vercel target; `VITE_API_BASE` wired to deployed API.
- [x] **0.11 Deploy backend** (shipped v1.12) — `fly.toml` checked in, release_command runs `init-db`.
- [ ] **0.12 Domain + HTTPS** (S, D:0.10,0.11) — register `openscout.io` (or similar) and point DNS. *Only Tier-0 item still open.*
- [x] **0.13 Error tracking** (shipped v1.12) — Sentry SDK on both frontend + backend (`api/sentry_init.py`). `SENTRY_DSN` env var, `SENTRY_ENV` for environment label.

### Quality

- [ ] **0.14 Cleanup duplicate researchers** (M) — slid into Tier 1 as 1.17 disambiguation. Same root cause.
- [x] **0.15 Handle `or-xxx` papers** (shipped v1.11) — OpenReview API pull for synthetic IDs.

---

## Tier 1 — high-value features (the new ground floor)

### Personalization & auth (foundational — unlocks billing + cloud-state)

- [ ] **1.1 Auth: who is this user?** (M) — magic-link login via Resend. Email-only sign in, store user → email mapping. Replaces IP-based deep-dive quota with per-user. Foundation for Stripe + watchlist 2.0 + investor notes. New: `src/openscout/api/auth.py` + `users` table (alembic migration).
- [ ] **1.2 Stripe billing — tiered access** (M, D:1.1) — free tier 3 dives/day (current default); pro tier unlimited + private notes + watchlist sync. Webhook handler updates `users.tier`. Quota check reads `users.tier` before counting against IP bucket. New: `src/openscout/api/billing.py`.
- [ ] **1.3 Watchlist 2.0: cloud-synced star list** (M, D:1.1) — replaces localStorage watchlist. New `user_watchlist(user_id, researcher_id, starred_at)` table; verify-then-merge migration nudges localStorage entries into the DB on first login. Email digest of watchlist activity (new papers / signal changes) becomes a thing.
- [ ] **1.4 Notion-style researcher notes** (M, D:1.1) — investor's private annotation per researcher. Markdown body, last-edited-at, scoped to user. Renders inline on the researcher detail page, never leaks across users. New table `researcher_notes(user_id, researcher_id, body, updated_at)`.

### Search & ranking

- [ ] **1.5 Search v2: pgvector semantic search** (L, D:0.4 ✓) — embed researcher bios + paper abstracts with a free model (bge-small / nomic-embed); store in pgvector column; `/search?q=diffusion+for+robotics` returns top-K by cosine. Needs Postgres (done) + embedding cron. New: `src/openscout/scraper/embeddings.py` + alembic migration adding `vector(384)` columns.

### New data sources (each = new scraper file, parallel-safe)

- [x] **1.6 Twitter/X bio scraper** (shipped v1.11) — `scraper/twitter.py`.
- [x] **1.7 知乎 profile scraper** (shipped v1.11) — `scraper/zhihu.py`.
- [x] **1.8 News mentions scraper** (shipped v1.11) — `scraper/news_mentions.py`.
- [x] **1.9 University faculty hire pages** (shipped v1.11) — `scraper/faculty_announcements.py`.
- [x] **1.10 Google Patents API** (shipped v1.11) — `scraper/patents.py`.
- [x] **1.11 Crunchbase / startup funding** (shipped v1.11) — `scraper/startups.py` (open-data first pass).
- [x] **1.12 Conference PC / area-chair** (shipped v1.11) — `scraper/conference_committees.py`.
- [x] **1.13 Academic awards** (shipped v1.11) — `scraper/awards.py`.

### Frontend

- [ ] **1.14 Researcher comparison page** (M, P) — `/compare?a=slug1&b=slug2` exists; add the v1.4 pillar scores side-by-side.
- [x] **1.15 Tag pages** (shipped v1.13) — `/tags/<label>` with signal-tag filtering.
- [ ] **1.16 Institution detail polish** (M, P) — `/institutions/<id>` exists; surface v1.10 signal tags + topic breakdown.
- [ ] **1.17 PDF / print edition** (M, P) — `/print/<date>` for daily brief; verify A4 + "save as PDF" output.
- [ ] **1.18 Onboarding tour** (S, P) — first-visit popover explaining the Investment Lens pillars.

### Quality

- [ ] **1.19 Better disambiguation for common names** (L) — "Yi Wang" maps to one Researcher row; in reality 10+ people share that name. Use OpenAlex ID + email domain as primary unique key when present.
- [ ] **1.20 Photo discovery** (M, P) — Wikidata P18 covered; pull from GitHub avatar + S2 author photo as fallback.

---

## Tier 2 — nice-to-haves (post-launch backlog)

- [ ] **2.1 RSS / Atom feeds** — exist; verify content quality.
- [ ] **2.2 OG / social cards** — verified; add Investment Lens score to card.
- [ ] **2.3 OpenAPI docs** — FastAPI auto-generates; expose at `/docs` + link from README.
- [ ] **2.4 Plausible / PostHog analytics** — track which researchers get clicks → feed into ranking.
- [ ] **2.5 i18n: full Traditional Chinese (`zh-TW`)** — currently zh = Simplified.
- [ ] **2.6 HK / TW / SG expansion** — corporate-email domains + institution seeds.
- [ ] **2.7 Slack / WeChat bot** — push daily Investment Lens picks to channels.
- [ ] **2.8 Multi-investor mode (Pro)** — shared watchlists + shared annotations (extends 1.3 + 1.4).
- [ ] **2.9 Researcher → startup match** — alert when a researcher leaves academia and starts a company.
- [ ] **2.10 Citation-velocity tracker** — paper-level "10 → 200 cites in 3 months" alerts.
- [ ] **2.11 arXiv withdrawal / retraction tracker** — negative signal.

---

## "Specific person" deep-mode (parked)

Beyond the 11-source deep-dive, a **per-person deep-mode** would let the
investor burn API quota on one researcher:

1. Read every paper they've first-authored (full PDF text via arxiv HTML).
2. LLM extracts: thesis topic, advisor name, method novelty per paper, TRL.
3. Network graph: co-author + advisor + student edges, 2-hop visualized.
4. News / blog mention search by name across past 12 months.
5. GitHub repo deep-read for popular repos: README, contributors, star history.
6. Email outreach draft (with disclaimer + signature line).

Reasonable next big feature after 1.1 (auth) lands — gated to pro tier.

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
- Most signal tags currently have null `label_en` / `slug` per `openscout
  doctor` Tag coverage section — investigate the scraper that's writing them
  and backfill labels.

---

Last updated: 2026-05-23 by the v1.13 ship + doctor enhancements.
