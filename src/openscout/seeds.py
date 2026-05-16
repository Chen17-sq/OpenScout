"""Seed loader — reads seeds/*.yaml and idempotently inserts rows."""

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Institution, Researcher, Topic

SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"


def _load_yaml(name: str) -> dict | None:
    path = SEEDS_DIR / name
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_topics(db: Session) -> int:
    data = _load_yaml("topics.yaml")
    if not data:
        return 0
    n = 0
    for t in data.get("topics", []):
        existing = db.execute(select(Topic).where(Topic.slug == t["slug"])).scalar_one_or_none()
        if existing:
            continue
        db.add(
            Topic(
                slug=t["slug"],
                name=t["name"],
                name_zh=t.get("name_zh"),
                description=t.get("description"),
            )
        )
        n += 1
    db.flush()
    return n


def load_institutions(db: Session) -> int:
    data = _load_yaml("institutions.yaml")
    if not data:
        return 0
    n = 0
    for inst in data.get("institutions", []):
        existing = db.execute(
            select(Institution).where(Institution.name == inst["name"])
        ).scalar_one_or_none()
        if existing:
            continue
        db.add(Institution(**inst))
        n += 1
    db.flush()
    return n


# YAML keys that map to columns. We pop the affiliation name separately because
# it has to be resolved to an id.
_RESEARCHER_KEYS = {
    "slug",
    "name_en",
    "name_zh",
    "name_zh_source",
    "email",
    "homepage_url",
    "twitter_handle",
    "github_handle",
    "zhihu_url",
    "linkedin_url",
    "photo_url",
    "current_role",
    "career_stage_year",
    "graduation_year_estimate",
    "bio",
    "bio_zh",
    "country",
    "confidence_level",
    "tags",
    "projects",
    "current_affiliation_id",
}


def load_researchers(db: Session) -> int:
    data = _load_yaml("researchers.yaml")
    if not data:
        return 0
    n = 0
    for r in data.get("researchers", []):
        existing = db.execute(
            select(Researcher).where(Researcher.slug == r["slug"])
        ).scalar_one_or_none()
        # Resolve current_affiliation by name if given as string
        affil_name = r.pop("current_affiliation", None)
        if affil_name:
            inst = db.execute(
                select(Institution).where(Institution.name == affil_name)
            ).scalar_one_or_none()
            if inst:
                r["current_affiliation_id"] = inst.id

        if existing:
            # Upsert hand-curated fields that may have been added since first seed
            # (e.g. projects added to the YAML after initial load).
            if r.get("projects") and not existing.projects:
                existing.projects = r["projects"]
                n += 1
            if r.get("photo_url") and not existing.photo_url:
                existing.photo_url = r["photo_url"]
            continue

        # Filter to only valid columns; ignore stray fields gracefully
        clean = {k: v for k, v in r.items() if k in _RESEARCHER_KEYS}
        db.add(Researcher(**clean))
        n += 1
    db.flush()
    return n


def load_all(db: Session) -> dict[str, int]:
    return {
        "topics": load_topics(db),
        "institutions": load_institutions(db),
        "researchers": load_researchers(db),
    }
