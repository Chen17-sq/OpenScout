.PHONY: help install db-up db-down db-shell init seed ingest brief api web dev fmt lint test clean

help:
	@echo "OpenScout — make targets"
	@echo "  install    Install Python deps (uv sync) + web deps (npm install)"
	@echo "  db-up      Start Postgres (docker compose)"
	@echo "  db-down    Stop Postgres"
	@echo "  db-shell   psql into the running Postgres"
	@echo "  init       Create tables (alembic upgrade head)"
	@echo "  seed       Load seeds/*.yaml into DB"
	@echo "  ingest     Pull arXiv + enrich (TOPIC=embodied LIMIT=50)"
	@echo "  brief      Generate today's daily brief"
	@echo "  api        Run FastAPI dev server (port 8000)"
	@echo "  web        Run SvelteKit dev server (port 5173)"
	@echo "  dev        api + web in parallel"
	@echo "  fmt        ruff format + prettier"
	@echo "  lint       ruff check + svelte-check"
	@echo "  clean      Drop caches and build artifacts"

install:
	uv sync --all-extras
	cd web && npm install

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-shell:
	docker compose exec postgres psql -U openscout -d openscout

init:
	uv run alembic upgrade head

seed:
	uv run openscout seed

TOPIC ?= embodied
LIMIT ?= 50
ingest:
	uv run openscout ingest --topic $(TOPIC) --limit $(LIMIT)

brief:
	uv run openscout brief

api:
	uv run uvicorn openscout.api.main:app --reload --port 8000

web:
	cd web && npm run dev

dev:
	$(MAKE) -j2 api web

fmt:
	uv run ruff format src/
	cd web && npm run format

lint:
	uv run ruff check src/
	cd web && npm run check

test:
	uv run pytest

clean:
	rm -rf .ruff_cache .pytest_cache .mypy_cache dist build
	rm -rf web/.svelte-kit web/build
	find . -type d -name __pycache__ -exec rm -rf {} +
