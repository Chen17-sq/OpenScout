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


def _pick_chip_tags(tags: list[dict] | None, n: int = 3) -> list[dict]:
    """Pick the top-n tags to show as chips.

    Priority: type=="signal" (highest score first); else type=="topic" (highest
    score first). Falls back to whatever tags exist if neither is typed.
    """
    tags = tags or []
    signals = sorted(
        (t for t in tags if t.get("type") == "signal"),
        key=lambda t: t.get("score") or 0,
        reverse=True,
    )
    if signals:
        return signals[:n]
    topics = sorted(
        (t for t in tags if t.get("type") == "topic"),
        key=lambda t: t.get("score") or 0,
        reverse=True,
    )
    if topics:
        return topics[:n]
    return tags[:n]


def _chip(x: int, y: int, label: str, *, signal: bool) -> str:
    """Render a single chip pill at (x, y). Returns the chip SVG and its width.

    Amber fill for signal chips; cream fill with hairline border for topics.
    Width is approximated from the label length (Inter ~9px per char at 20px).
    """
    text = xml_escape(label)
    w = max(120, int(len(label) * 13) + 40)
    fill = "#F5C518" if signal else "#F9F9F7"
    stroke = "#111"
    fg = "#111"
    return (
        f'<g transform="translate({x}, {y})">'
        f'<rect width="{w}" height="48" rx="24" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        f'<text x="{w // 2}" y="32" text-anchor="middle" '
        f'font-family="Inter, sans-serif" font-size="20" font-weight="700" '
        f'fill="{fg}">{text}</text>'
        f"</g>",
        w,
    )


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
    works = r.works_count or 0
    role = (r.current_role or "").upper().replace("_", " ")
    score_v2 = r.investability_score_v2
    score_str = f"{score_v2:.2f}" if score_v2 is not None else "—"

    chip_tags = _pick_chip_tags(r.tags, n=3)
    has_signal = bool(chip_tags) and chip_tags[0].get("type") == "signal"
    chips_svg = ""
    cx = 40
    for t in chip_tags:
        label = (t.get("label") or "").strip()
        if not label:
            continue
        # Trim very long topic labels so chips don't overflow the canvas.
        if len(label) > 28:
            label = label[:27] + "…"
        chip_markup, w = _chip(cx, 470, label, signal=has_signal)
        # If a chip would overflow the safe area, stop adding more.
        if cx + w > 1160:
            break
        chips_svg += chip_markup
        cx += w + 16

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

  <line x1="40" y1="280" x2="1160" y2="280" stroke="#111" stroke-width="2"/>

  <g transform="translate(40, 340)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">ROLE</text>
    <text y="56" font-size="30" font-weight="700" fill="#111">{role or "—"}</text>
  </g>
  <g transform="translate(340, 340)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#CC0000" letter-spacing="3">INVEST SCORE</text>
    <text y="60" font-family="Playfair Display, serif" font-size="64" font-weight="900" fill="#CC0000">{score_str}</text>
  </g>
  <g transform="translate(620, 340)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">CITATIONS</text>
    <text y="60" font-family="Playfair Display, serif" font-size="48" font-weight="900" fill="#111">{cites:,}</text>
  </g>
  <g transform="translate(880, 340)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">H-INDEX</text>
    <text y="60" font-family="Playfair Display, serif" font-size="48" font-weight="900" fill="#111">{h}</text>
  </g>
  <g transform="translate(1040, 340)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">WORKS</text>
    <text y="60" font-family="Playfair Display, serif" font-size="48" font-weight="900" fill="#111">{works}</text>
  </g>

  {chips_svg}

  <line x1="40" y1="540" x2="1160" y2="540" stroke="#111" stroke-width="2"/>
  <text x="40" y="585" font-family="Lora, serif" font-style="italic" font-size="20" fill="#525252">openscout.app/researchers/{xml_escape(r.slug)}</text>
</svg>
"""
    return Response(content=svg, media_type="image/svg+xml")
