"""FastAPI app entry — `uvicorn openscout.api.main:app`."""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import settings
from .sentry_init import init_sentry

# Sentry must be initialized BEFORE the FastAPI app is created so it wraps
# the middleware stack. No-ops cleanly when SENTRY_DSN is unset.
init_sentry()
from .routes import (  # noqa: E402 — must follow init_sentry()
    admin,
    briefs,
    conferences,
    institutions,
    investment,
    jobs,
    og,
    papers,
    researchers,
    rss,
    search,
    stats,
    tags,
    topics,
)

app = FastAPI(
    title="OpenScout API",
    version=__version__,
    description="All The Researchers Fit To Watch.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(researchers.router, prefix="/researchers", tags=["researchers"])
app.include_router(papers.router, prefix="/papers", tags=["papers"])
app.include_router(briefs.router, prefix="/briefs", tags=["briefs"])
app.include_router(topics.router, prefix="/topics", tags=["topics"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(tags.router, prefix="/tags", tags=["tags"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(rss.router, prefix="/rss", tags=["rss"])
app.include_router(og.router, prefix="/og", tags=["og"])
app.include_router(institutions.router, prefix="/institutions", tags=["institutions"])
app.include_router(conferences.router, prefix="/conferences", tags=["conferences"])
app.include_router(investment.router, prefix="/investment", tags=["investment"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/")
def root() -> dict:
    return {
        "name": "OpenScout",
        "version": __version__,
        "tagline": "All The Researchers Fit To Watch",
        "endpoints": [
            "/health",
            "/researchers",
            "/researchers/{slug}",
            "/papers",
            "/papers/{arxiv_id}",
            "/briefs/today",
            "/briefs/list",
            "/briefs/{date}",
            "/topics",
            "/topics/{slug}",
            "/tags",
            "/tags/{label}",
            "/stats",
            "/stats/top-collaborators",
            "/stats/by-topic",
            "/search?q=",
            "/rss/daily",
            "/rss/papers",
            "/og/researchers/{slug}.svg",
            "/investment/picks",
            "/admin/ingest (POST · auth)",
        ],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/robots.txt")
def robots() -> Response:
    from fastapi import Response as R

    return R(
        content="User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n",
        media_type="text/plain",
    )
