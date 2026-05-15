"""Generate 小红书-style 9-image grid (3×3) for daily sharing.

One SVG per researcher in the day's top-9 list. The grid (as a single big SVG)
is also produced for users who want one image to share. Written to:
  web/static/social/{date}/card_{n}.svg     # n in 1..9
  web/static/social/{date}/grid.svg         # 3x3 composite

Picks: Top 9 from today's brief (new_first_authors first, then anchor_activity,
then hot_papers — deduped).
"""

from datetime import UTC, datetime
from datetime import date as Date
from pathlib import Path
from xml.sax.saxutils import escape

from sqlalchemy import desc, func, select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher

SOCIAL_DIR = Path(__file__).resolve().parents[3] / "web" / "static" / "social"

CARD_W, CARD_H = 720, 720  # square, 1:1 — 小红书 standard


def _flag(cc: str | None) -> str:
    if not cc or len(cc) != 2:
        return ""
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in cc.upper())


def _wrap(text: str, max_chars: int = 36) -> list[str]:
    """Naive line wrapping for SVG <text> rendering."""
    if not text:
        return []
    text = " ".join(text.split())
    out: list[str] = []
    while text:
        if len(text) <= max_chars:
            out.append(text)
            break
        cut = text.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        out.append(text[:cut])
        text = text[cut + 1 :].lstrip()
    return out[:4]


def _card_svg(rank: int, researcher: Researcher, paper: Paper, date_label: str) -> str:
    name = escape(researcher.name_en)
    name_zh = escape(researcher.name_zh or "")
    flag = _flag(researcher.country)
    cites = researcher.citation_count or 0
    h_index = researcher.h_index or 0
    title_lines = _wrap(paper.title, 34)
    title_svg = ""
    y = 360
    for line in title_lines:
        title_svg += (
            f'<text x="36" y="{y}" font-family="Playfair Display, serif" '
            f'font-size="30" font-weight="700" fill="#111">{escape(line)}</text>\n'
        )
        y += 36

    tag = ""
    tags = researcher.tags or []
    if tags:
        tag = escape((tags[0].get("label") or "")[:32])

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CARD_W} {CARD_H}" font-family="Playfair Display, Times New Roman, serif">
  <rect width="{CARD_W}" height="{CARD_H}" fill="#F9F9F7"/>
  <pattern id="d" width="4" height="4" patternUnits="userSpaceOnUse">
    <path d="M1 3h1v1H1V3zm2-2h1v1H3V1z" fill="#111" fill-opacity="0.05"/>
  </pattern>
  <rect width="{CARD_W}" height="{CARD_H}" fill="url(#d)"/>

  <!-- Top bar -->
  <rect x="0" y="0" width="{CARD_W}" height="56" fill="#111"/>
  <text x="36" y="36" fill="#F9F9F7" font-family="Inter, sans-serif" font-size="14" font-weight="700" letter-spacing="3">OPENSCOUT · DAILY · {date_label}</text>
  <text x="{CARD_W - 36}" y="36" fill="#F9F9F7" font-family="Inter, sans-serif" font-size="14" font-weight="700" letter-spacing="3" text-anchor="end">№ {rank:02d} / 09</text>

  <!-- Rank number -->
  <text x="36" y="220" font-family="Playfair Display, serif" font-weight="900" font-size="180" fill="#CC0000" letter-spacing="-6">{rank:02d}</text>

  <!-- Name -->
  <text x="36" y="280" font-family="Playfair Display, serif" font-weight="900" font-size="48" fill="#111" letter-spacing="-1">{name}</text>
  {f'<text x="36" y="316" font-family="Lora, serif" font-style="italic" font-size="22" fill="#525252">{name_zh}</text>' if name_zh else ""}

  <!-- Country + role -->
  <text x="{CARD_W - 36}" y="280" font-family="JetBrains Mono, monospace" font-size="22" font-weight="700" fill="#111" text-anchor="end">{flag}</text>

  <!-- Title block -->
  {title_svg}

  <!-- Bottom: stats -->
  <line x1="36" y1="580" x2="{CARD_W - 36}" y2="580" stroke="#111" stroke-width="2"/>
  <text x="36" y="624" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#737373" letter-spacing="3">CITATIONS</text>
  <text x="36" y="666" font-family="Playfair Display, serif" font-weight="900" font-size="44" fill="#111">{cites:,}</text>

  <text x="240" y="624" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#737373" letter-spacing="3">H-INDEX</text>
  <text x="240" y="666" font-family="Playfair Display, serif" font-weight="900" font-size="44" fill="#111">{h_index}</text>

  <text x="420" y="624" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#CC0000" letter-spacing="3">TAG</text>
  <text x="420" y="660" font-family="Inter, sans-serif" font-size="18" font-weight="700" fill="#111">{tag}</text>

  <text x="{CARD_W - 36}" y="690" font-family="JetBrains Mono, monospace" font-size="11" fill="#737373" text-anchor="end">openscout.app/researchers/{escape(researcher.slug)}</text>
</svg>
"""


def write_daily_cards(brief_date: Date | None = None) -> dict[str, int]:
    """Generate today's 9-card grid. Returns count of cards written."""
    if brief_date is None:
        brief_date = datetime.now(UTC).date()

    out_dir = SOCIAL_DIR / brief_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    with session_scope() as db:
        # Top researchers today: rank by paper.author_count + recency of researcher's first_seen_at
        author_count_sq = (
            select(PaperAuthor.paper_id, func.count(PaperAuthor.researcher_id).label("n"))
            .group_by(PaperAuthor.paper_id)
            .subquery()
        )
        candidates_stmt = (
            select(Researcher, Paper, author_count_sq.c.n)
            .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
            .join(Paper, Paper.id == PaperAuthor.paper_id)
            .outerjoin(author_count_sq, author_count_sq.c.paper_id == Paper.id)
            .where(
                PaperAuthor.position == 1,
                func.date(Paper.first_seen_at) == brief_date,
            )
            .order_by(desc(author_count_sq.c.n), desc(Paper.first_seen_at))
            .limit(9)
        )
        rows = list(db.execute(candidates_stmt).all())

        date_label = brief_date.strftime("%b %-d %Y").upper()

        # Per-card SVGs
        for i, (r, p, _n) in enumerate(rows, start=1):
            (out_dir / f"card_{i:02d}.svg").write_text(
                _card_svg(i, r, p, date_label), encoding="utf-8"
            )

    # 3x3 grid wrapper
    grid_svg_parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2160 2160">']
    for i in range(9):
        col, row = i % 3, i // 3
        path = out_dir / f"card_{i + 1:02d}.svg"
        if not path.exists():
            continue
        # Inline each card as nested svg via <image> with embedded data isn't ideal — easier
        # is <use> with href pointing to the file in the same dir.
        grid_svg_parts.append(
            f'<image x="{col * 720}" y="{row * 720}" width="720" height="720" href="card_{i + 1:02d}.svg"/>'
        )
    grid_svg_parts.append("</svg>")
    (out_dir / "grid.svg").write_text("\n".join(grid_svg_parts), encoding="utf-8")

    return {"cards": len(rows), "out_dir": str(out_dir)}
