# Deploy

OpenScout is two deploys: a SvelteKit frontend on Vercel and a FastAPI backend (with Postgres) on Fly.io. Both are cheap or free for the traffic OpenScout will see.

```
┌──────────────────────────┐      ┌────────────────────────────────┐
│  Vercel (frontend)       │ ───▶ │  Fly.io (api + pgvector pg)    │
│  https://openscout.app/  │      │  https://openscout.fly.dev/    │
└──────────────────────────┘      └────────────────────────────────┘
                                            │
                                            ▼
                                  ┌────────────────────────────┐
                                  │  GitHub Actions cron       │
                                  │  daily 01:00 UTC → ingest  │
                                  └────────────────────────────┘
```

---

## 1 · Backend on Fly.io

### One-time setup

```bash
# 1. CLI
brew install flyctl
flyctl auth login

# 2. App + region
cd /path/to/OpenScout
flyctl launch --no-deploy         # use existing fly.toml; say "no" to Postgres prompt

# 3. Managed Postgres (the prompt above would create a free dev one, but
#    we want pgvector — create it explicitly with the right image)
flyctl postgres create --name openscout-db --region nrt --image-ref flyio/postgres-flex:16
flyctl postgres attach openscout-db   # sets DATABASE_URL secret automatically

# 4. Enable pgvector on the attached DB
flyctl postgres connect -a openscout-db
#   then in psql:
#   \c openscout
#   CREATE EXTENSION IF NOT EXISTS vector;
#   \q

# 5. App-level secrets
flyctl secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  SEMANTIC_SCHOLAR_API_KEY=... \
  RESEND_API_KEY=... \
  INGEST_SECRET=$(openssl rand -hex 32) \
  FRONTEND_ORIGIN=https://openscout.vercel.app

# 6. First deploy
flyctl deploy
```

### Initialize the DB

```bash
flyctl ssh console -C "openscout init-db"
flyctl ssh console -C "openscout seed"
flyctl ssh console -C "openscout ingest --topic embodied --limit 50"
flyctl ssh console -C "openscout brief"
```

### Continuous deploys

Push to `main` → `.github/workflows/deploy.yml` runs `flyctl deploy --remote-only`. Requires repo secret `FLY_API_TOKEN`:

```bash
flyctl auth token             # copy the token
gh secret set FLY_API_TOKEN   # paste it
```

---

## 2 · Frontend on Vercel

### One-time setup

```bash
# Install Vercel CLI (or use the dashboard at vercel.com)
npm i -g vercel

cd web
vercel link              # connect this directory to a Vercel project
vercel env add PUBLIC_API_BASE   # set to https://openscout.fly.dev
vercel --prod            # first prod deploy
```

After the first `vercel link`, future pushes to `main` auto-deploy via Vercel's GitHub integration. No GitHub Action needed.

### Custom domain

1. In the Vercel dashboard, add `openscout.app` (or whatever domain).
2. Point an `A` record / `CNAME` to Vercel's targets.
3. Update Fly.io's `FRONTEND_ORIGIN` secret to match: `flyctl secrets set FRONTEND_ORIGIN=https://openscout.app`.

---

## 3 · Daily ingest cron

`.github/workflows/ingest.yml` already exists. It needs two settings:

```bash
# Repo variable (public)
gh variable set API_URL --body "https://openscout.fly.dev"

# Repo secret (matches the value set on Fly above)
gh secret set INGEST_SECRET --body "<the value you generated above>"
```

It will fire daily at 01:00 UTC (09:00 Beijing). Trigger manually any time:

```bash
gh workflow run ingest.yml
```

---

## 4 · Verify

```bash
# Backend
curl https://openscout.fly.dev/health
curl https://openscout.fly.dev/briefs/latest | jq .issue,.brief_date

# Frontend
open https://openscout.app
```

---

## Switching local dev to Postgres (optional)

Local SQLite is fine for v0. If you want to mirror prod locally:

```bash
brew install postgresql@16
brew services start postgresql@16
psql postgres -c "CREATE DATABASE openscout; CREATE EXTENSION vector;"

# Then in .env:
DATABASE_URL=postgresql+psycopg://chensiqi@localhost:5432/openscout
```

---

## Costs (May 2026 estimate)

| Service | Plan | Monthly |
| --- | --- | --- |
| Fly.io app (1× shared 512MB, auto-stop) | Hobby | ~$0–3 |
| Fly Postgres (1GB pgvector) | Hobby | ~$0–7 |
| Vercel (Hobby) | Hobby | $0 |
| Resend (1k emails/mo) | Free | $0 |
| Semantic Scholar API key | Free | $0 |
| Anthropic API (~10k tokens/day for topic + 中文 blurbs) | Pay-go | ~$3–10 |
| **Total** | | **~$6–20** |
