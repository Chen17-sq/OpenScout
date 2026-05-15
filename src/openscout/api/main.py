"""FastAPI app entry — `uvicorn openscout.api.main:app`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import settings
from .routes import admin, briefs, papers, researchers, rss, search, stats, tags, topics

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
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/")
def root() -> dict:
    return {
        "name": "OpenScout",
        "version": __version__,
        "tagline": "All The Researchers Fit To Watch",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
