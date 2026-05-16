"""Wikidata photo enrichment.

OpenAlex authors may have a Wikidata Q-id (via `external_ids.wikidata`). Wikidata
exposes P18 (image) per entity, hosted on Wikimedia Commons. We grab it as
`Researcher.photo_url` only when unambiguous (single P18 value).

Polite: 0.4s per request, conservative quota. Wikidata is public and CC-licensed
metadata; images are typically CC-BY-SA so we should attribute on render.
"""

import time
from typing import Optional

import httpx
from sqlalchemy import select

from ..db import session_scope
from ..models import Researcher

WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_BASE = "https://upload.wikimedia.org/wikipedia/commons/thumb"


def _image_url(filename: str, width: int = 256) -> str:
    """Build a Wikimedia Commons thumbnail URL from a P18 filename."""
    import hashlib

    name = filename.replace(" ", "_")
    md5 = hashlib.md5(name.encode("utf-8")).hexdigest()
    return f"{COMMONS_BASE}/{md5[0]}/{md5[:2]}/{name}/{width}px-{name}"


def _wikidata_p18(qid: str, client: httpx.Client) -> Optional[str]:
    """For a Wikidata Q-id, return the URL to the P18 (image) thumbnail."""
    try:
        r = client.get(
            WD_API,
            params={
                "action": "wbgetclaims",
                "entity": qid,
                "property": "P18",
                "format": "json",
            },
            timeout=15.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        claims = (data.get("claims") or {}).get("P18") or []
        if not claims:
            return None
        filename = (
            claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        )
        if not filename:
            return None
        return _image_url(filename)
    except Exception:
        return None


def _openalex_wikidata_id(openalex_url: str, client: httpx.Client) -> Optional[str]:
    """Query OpenAlex author API for the wikidata external id."""
    try:
        author_id = openalex_url.rsplit("/", 1)[-1]
        r = client.get(
            f"https://api.openalex.org/authors/{author_id}",
            params={"select": "ids,display_name"},
            timeout=15.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        wd = (data.get("ids") or {}).get("wikidata")
        if not wd:
            return None
        # Wikidata URLs look like https://www.wikidata.org/wiki/Q12345
        return wd.rsplit("/", 1)[-1]
    except Exception:
        return None


def enrich_photos(limit: int = 50, sleep_between: float = 0.4) -> dict[str, int]:
    counts = {"attempted": 0, "found_wikidata": 0, "found_photo": 0, "errors": 0}

    client = httpx.Client(
        headers={"User-Agent": "OpenScout/0.6 (+https://github.com/Chen17-sq/OpenScout)"}
    )
    try:
        with session_scope() as db:
            rs = list(
                db.execute(
                    select(Researcher)
                    .where(
                        Researcher.openalex_id.is_not(None),
                        Researcher.photo_url.is_(None),
                        Researcher.confidence_level.in_(["high", "medium"]),
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            for r in rs:
                counts["attempted"] += 1
                qid = _openalex_wikidata_id(r.openalex_id, client)
                if not qid:
                    continue
                counts["found_wikidata"] += 1
                photo = _wikidata_p18(qid, client)
                if photo:
                    r.photo_url = photo
                    counts["found_photo"] += 1
                time.sleep(sleep_between)
    finally:
        client.close()
    return counts
