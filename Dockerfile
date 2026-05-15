# OpenScout backend — FastAPI + uv + Python 3.12
#
# Builds the slimmest viable image: uv-managed venv copied into a runtime layer
# that has only system Python + libpq (for psycopg with Postgres).

FROM python:3.12-slim AS builder

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Cache the dep install: copy lockfiles first.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install deps + the project itself into a venv at /app/.venv
RUN uv sync --frozen --no-dev

# ─── Runtime stage ──────────────────────────────────────────────────────────

FROM python:3.12-slim

# libpq for psycopg (Postgres in prod). Curl handy for healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app /app
COPY seeds ./seeds

# Use the venv's python and uvicorn directly — no `uv run` needed at runtime.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "openscout.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
