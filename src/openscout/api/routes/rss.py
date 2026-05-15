"""RSS feed — daily brief + recent papers.

Two endpoints:
  GET /rss/daily   → last 30 daily briefs (permalinks to /daily/{date})
  GET /rss/papers  → last 50 papers ingested
"""

from datetime import UTC, datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import DailyBrief, Paper

router = APIRouter()

PUBLIC_BASE = "https://openscout.app"


def _xml_response(root: Element) -> Response:
    body = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="utf-8")
    return Response(content=body, media_type="application/rss+xml; charset=utf-8")


def _rss_skeleton(title: str, description: str, link: str) -> tuple[Element, Element]:
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = link
    SubElement(channel, "description").text = description
    SubElement(channel, "language").text = "zh-CN"
    SubElement(channel, "lastBuildDate").text = datetime.now(UTC).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    return rss, channel


@router.get("/daily")
def rss_daily(db: Session = Depends(get_db)) -> Response:
    rss, channel = _rss_skeleton(
        title="OpenScout · Daily Brief",
        description="A daily newspaper tracking early-stage AI researchers in embodied AI, world models, and AI for Science.",
        link=PUBLIC_BASE,
    )
    briefs = list(
        db.execute(select(DailyBrief).order_by(desc(DailyBrief.brief_date)).limit(30))
        .scalars()
        .all()
    )
    for b in briefs:
        item = SubElement(channel, "item")
        SubElement(
            item, "title"
        ).text = f"OpenScout · Vol. {b.volume}, No. {b.issue:03d} · {b.brief_date.isoformat()}"
        SubElement(item, "link").text = f"{PUBLIC_BASE}/daily/{b.brief_date.isoformat()}"
        SubElement(item, "guid").text = f"{PUBLIC_BASE}/daily/{b.brief_date.isoformat()}"
        if b.generated_at:
            SubElement(item, "pubDate").text = b.generated_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
        desc_text = (b.rendered_md or "")[:600].replace("\n", " ")
        SubElement(item, "description").text = desc_text
    return _xml_response(rss)


@router.get("/papers")
def rss_papers(db: Session = Depends(get_db)) -> Response:
    rss, channel = _rss_skeleton(
        title="OpenScout · Recent Papers",
        description="Recent arXiv papers ingested by OpenScout across embodied AI, world models, and AI for Science.",
        link=PUBLIC_BASE,
    )
    papers = list(
        db.execute(select(Paper).order_by(desc(Paper.first_seen_at)).limit(50)).scalars().all()
    )
    for p in papers:
        if not p.arxiv_id:
            continue
        item = SubElement(channel, "item")
        SubElement(item, "title").text = p.title
        SubElement(item, "link").text = f"https://arxiv.org/abs/{p.arxiv_id}"
        SubElement(item, "guid").text = f"arxiv:{p.arxiv_id}"
        if p.first_seen_at:
            SubElement(item, "pubDate").text = p.first_seen_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
        SubElement(item, "description").text = (p.abstract or "")[:600]
    return _xml_response(rss)
