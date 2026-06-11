"""Sitemap — `GET /sitemap.xml` for crawlers.

Lists the static frontend pages, the top 500 researcher detail pages
(by investability_score_v2 desc), and every topic page. Base URL comes
from `settings.site_base_url` (SITE_BASE_URL env) since the sitemap is
served by the API but the pages live on the frontend origin.

`/robots.txt` (main.py) already points crawlers at `/sitemap.xml`.
"""

from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ...config import settings
from ...db import get_db
from ...models import Researcher, Topic

router = APIRouter()

# Static frontend pages worth indexing ("" = home).
STATIC_PATHS = ["", "/researchers", "/papers", "/topics", "/tags", "/investment", "/editions"]

MAX_RESEARCHER_URLS = 500


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)) -> Response:
    base = settings.site_base_url.rstrip("/")

    urlset = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    def add(loc: str) -> None:
        url = SubElement(urlset, "url")
        SubElement(url, "loc").text = loc

    for path in STATIC_PATHS:
        add(f"{base}{path}")

    researcher_slugs = (
        db.execute(
            select(Researcher.slug)
            .order_by(desc(Researcher.investability_score_v2).nulls_last(), Researcher.id)
            .limit(MAX_RESEARCHER_URLS)
        )
        .scalars()
        .all()
    )
    for slug in researcher_slugs:
        add(f"{base}/researchers/{slug}")

    topic_slugs = db.execute(select(Topic.slug).order_by(Topic.slug)).scalars().all()
    for slug in topic_slugs:
        add(f"{base}/topics/{slug}")

    body = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(urlset, encoding="utf-8")
    return Response(content=body, media_type="application/xml; charset=utf-8")
