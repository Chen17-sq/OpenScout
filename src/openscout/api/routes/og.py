"""Per-researcher Open Graph card endpoint.

GET /og/researchers/{slug}.svg → 1200×630 SVG sharing card with name + stats.
The browser / preview bot fetches this URL when the researcher detail page is
shared on social. The page sets it via <meta property="og:image" content="...">.
"""

from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Researcher

router = APIRouter()


def _flag(cc: str | None) -> str:
    if not cc or len(cc) != 2:
        return ""
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in cc.upper())


@router.get("/researchers/{slug}.svg")
def og_researcher(slug: str, db: Session = Depends(get_db)) -> Response:
    r = db.execute(select(Researcher).where(Researcher.slug == slug)).scalar_one_or_none()
    if not r:
        raise HTTPException(404)

    name = xml_escape(r.name_en)
    name_zh = xml_escape(r.name_zh or "")
    flag = _flag(r.country)
    cites = r.citation_count or 0
    h = r.h_index or 0
    role = (r.current_role or "").upper().replace("_", " ")
    tags = r.tags or []
    tag1 = xml_escape((tags[0].get("label") if tags else "") or "")
    tag2 = xml_escape((tags[1].get("label") if len(tags) > 1 else "") or "")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" font-family="Playfair Display, Times New Roman, serif">
  <rect width="1200" height="630" fill="#F9F9F7"/>
  <pattern id="d" width="4" height="4" patternUnits="userSpaceOnUse">
    <path d="M1 3h1v1H1V3zm2-2h1v1H3V1z" fill="#111" fill-opacity="0.06"/>
  </pattern>
  <rect width="1200" height="630" fill="url(#d)"/>

  <rect x="0" y="0" width="1200" height="48" fill="#111"/>
  <text x="40" y="32" fill="#F9F9F7" font-family="Inter, sans-serif" font-size="14" font-weight="700" letter-spacing="4">OPENSCOUT · ALL THE RESEARCHERS FIT TO WATCH</text>

  <text x="40" y="180" font-family="Playfair Display, serif" font-weight="900" font-size="108" fill="#111" letter-spacing="-3">{name}</text>
  {f'<text x="40" y="232" font-family="Lora, serif" font-style="italic" font-size="36" fill="#525252">{name_zh}</text>' if name_zh else ""}

  <text x="1160" y="180" font-family="JetBrains Mono, monospace" font-size="56" fill="#111" text-anchor="end">{flag}</text>

  <line x1="40" y1="290" x2="1160" y2="290" stroke="#111" stroke-width="2"/>

  <g transform="translate(40, 350)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">ROLE</text>
    <text y="56" font-size="38" font-weight="700" fill="#111">{role or "—"}</text>
  </g>
  <g transform="translate(340, 350)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#CC0000" letter-spacing="3">CITATIONS</text>
    <text y="56" font-size="64" font-weight="900" fill="#CC0000">{cites:,}</text>
  </g>
  <g transform="translate(700, 350)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">H-INDEX</text>
    <text y="56" font-size="64" font-weight="900" fill="#111">{h}</text>
  </g>
  <g transform="translate(900, 350)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">TAGS</text>
    <text y="56" font-size="24" font-weight="700" fill="#111">{tag1}</text>
    {f'<text y="84" font-size="22" font-weight="500" fill="#525252">{tag2}</text>' if tag2 else ""}
  </g>

  <line x1="40" y1="540" x2="1160" y2="540" stroke="#111" stroke-width="2"/>
  <text x="40" y="585" font-family="Lora, serif" font-style="italic" font-size="20" fill="#525252">openscout.app/researchers/{xml_escape(r.slug)}</text>
</svg>
"""
    return Response(content=svg, media_type="image/svg+xml")
