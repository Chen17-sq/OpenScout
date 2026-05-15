"""Admin endpoints — protected by `X-Ingest-Secret` header.

`POST /admin/ingest` is the GitHub Actions cron target: it pulls today's papers
for all topics and regenerates the daily brief.
"""

from fastapi import APIRouter, Header, HTTPException

from ...brief.generate import generate_brief
from ...config import settings
from ...scraper.arxiv import ingest_topic

router = APIRouter()


def _check_secret(provided: str | None) -> None:
    if not settings.ingest_secret or settings.ingest_secret == "change-me":
        raise HTTPException(500, detail="server ingest_secret not configured")
    if provided != settings.ingest_secret:
        raise HTTPException(401, detail="invalid ingest secret")


@router.post("/ingest")
def trigger_ingest(
    x_ingest_secret: str | None = Header(default=None, alias="X-Ingest-Secret"),
) -> dict:
    """Full daily run: ingest all topics, regenerate the brief."""
    _check_secret(x_ingest_secret)
    results = {}
    for topic in ("embodied", "world_models", "ai4sci"):
        try:
            results[topic] = ingest_topic(topic, limit=50)
        except Exception as exc:  # noqa: BLE001 — surface but don't halt other topics
            results[topic] = f"error: {exc}"

    brief_path = generate_brief()
    return {"ingested": results, "brief_path": str(brief_path)}


@router.post("/brief")
def trigger_brief_only(
    x_ingest_secret: str | None = Header(default=None, alias="X-Ingest-Secret"),
) -> dict:
    """Regenerate today's brief without re-ingesting."""
    _check_secret(x_ingest_secret)
    path = generate_brief()
    return {"brief_path": str(path)}
