# Contributing to OpenScout

Thanks for your interest. OpenScout is a personal-scale tracker, but the
design intentionally accepts community contributions — especially for the
seed data (anchor researchers, institutions, flagship projects).

## Quick-start dev loop

```bash
git clone https://github.com/Chen17-sq/OpenScout.git
cd OpenScout
make install        # uv sync + npm install (web)
make init           # create tables + run migrations
make seed           # load seeds/*.yaml
make ingest         # pull recent arXiv (TOPIC=embodied LIMIT=50)
make brief          # generate today's daily brief markdown
make dev            # FastAPI :8000 + SvelteKit :5174
```

## Adding a new anchor researcher

Anchors are senior figures used as roots for lineage and as priors for topic
classification. Add them to `seeds/researchers.yaml`:

```yaml
- slug: jiajun-wu                       # kebab-case, stable, unique
  name_en: Jiajun Wu
  name_zh: 吴佳俊                       # OPTIONAL — only if you can verify it
  current_affiliation: Stanford University    # must match an entry in institutions.yaml
  current_role: ap                      # phd / postdoc / incoming_ap / ap / associate / full / industry
  bio: "3D vision, intuitive physics, embodied AI."
  confidence_level: high                # high / medium / low
  projects:                             # OPTIONAL — flagship companies/labs/projects
    - {name: "Stanford SAIL", role: "PI", category: "lab"}
```

### Rules
- **`name_zh` is conservative** — never guess. If you don't have a verified
  source for the Chinese name (their own homepage, 知乎 column, paper byline),
  leave it null. The OpenAlex enricher will fill it in when it can.
- Use `confidence_level: high` only for figures you're confident are who you
  think they are. The enricher will not overwrite high-confidence rows.
- `current_role` `incoming_ap` is what populates Section D of the daily brief.

### After adding seeds

```bash
make seed                              # load new rows
uv run openscout resolve-institutions  # if you added an institution
uv run openscout enrich-openalex --only-anchors --limit 5  # pull OpenAlex stats
uv run openscout backfill-works --per-anchor 60   # pull their papers
uv run openscout score                 # recompute person_score
```

## Adding a topic

Edit `seeds/topics.yaml` and add a key to `TOPIC_QUERIES` in
`src/openscout/scraper/arxiv.py`. Each query is an arXiv API search string.
Use parentheses; combine cat: + abs: filters.

## Code style

- Python: `ruff format` + `ruff check --fix` (enforced by pre-commit)
- Svelte: `prettier --plugin=prettier-plugin-svelte` (enforced by pre-commit)
- Commit messages: NO `Co-Authored-By:` trailer for AI assistants.

## Pre-commit

```bash
uv tool install pre-commit
pre-commit install
```

After this, formatting + lint runs automatically on every commit.

## Roadmap-ish

The repository is intentionally feature-spiky. If you want to add a major
feature, open an issue first so we can align on data model + naming. Areas
that need work:

- Real lineage inference (currently anchor-coauthor heuristic; needs more
  data flowing through the pipeline)
- LLM topic classifier (stub at `src/openscout/scraper/classify.py`)
- Conference oral/spotlight scraping (NeurIPS / ICML / ICLR)
- HuggingFace model-release tracking
- Email digest via Resend (config exists in `.env.example`)
