"""Generate 小红书-style 9-image grid (3×3) for daily sharing.

One SVG per researcher in the day's top-9 list. The grid (as a single big SVG)
is also produced for users who want one image to share. Written to:
  web/static/social/{date}/card_{n}.svg     # n in 1..9
  web/static/social/{date}/grid.svg         # 3x3 composite

Picks (v1.4+): top 9 from `top_investment_picks(limit=9)` — researchers ranked
by `investability_score_v2`. If that source returns nothing, falls back to the
original "today's first-author papers" path so we always emit something.
"""

from datetime import UTC, datetime
from datetime import date as Date
from pathlib import Path
from xml.sax.saxutils import escape

from sqlalchemy import desc, func, select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher
from .work_scoring import top_investment_picks

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


def _truncate(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _pillar_bar(x: int, y: int, label: str, value: float, accent: str) -> str:
    """Render a small horizontal bar with a tiny caps label.

    value is clamped to [0, 1]. Bars are 200px wide and 10px tall.
    """
    v = max(0.0, min(1.0, float(value or 0)))
    fill_w = int(200 * v)
    pct = f"{int(round(v * 100))}"
    return (
        f'<g transform="translate({x}, {y})">'
        f'<text font-family="Inter, sans-serif" font-size="11" font-weight="700" '
        f'letter-spacing="2" fill="#737373">{escape(label)}</text>'
        f'<text x="200" y="0" text-anchor="end" font-family="JetBrains Mono, monospace" '
        f'font-size="11" font-weight="700" fill="#111">{pct}</text>'
        f'<rect x="0" y="8" width="200" height="10" fill="#E5E5E0" stroke="#111" stroke-width="1.2"/>'
        f'<rect x="0" y="8" width="{fill_w}" height="10" fill="{accent}"/>'
        f"</g>"
    )


def _top_two_pillars(breakthrough: float, commercial: float, buzz: float) -> list[tuple]:
    """Pick the top 2 of the three pillar scores by absolute value.

    Returns list of (label, value, color). Always preserves the canonical
    short labels B / C / Z used elsewhere in the codebase.
    """
    pillars = [
        ("B · BREAKTHROUGH", breakthrough or 0.0, "#CC0000"),
        ("C · COMMERCIAL", commercial or 0.0, "#0B6B3A"),
        ("Z · BUZZ", buzz or 0.0, "#B45309"),
    ]
    pillars.sort(key=lambda p: p[1], reverse=True)
    return pillars[:2]


def _signal_or_first_tag(tags: list[dict] | None) -> str:
    """Pick the top signal tag label; else the first tag's label."""
    tags = tags or []
    signals = sorted(
        (t for t in tags if t.get("type") == "signal"),
        key=lambda t: t.get("score") or 0,
        reverse=True,
    )
    if signals:
        return (signals[0].get("label") or "")[:32]
    if tags:
        return (tags[0].get("label") or "")[:32]
    return ""


def _card_svg(
    rank: int,
    *,
    name_en: str,
    name_zh: str | None,
    country: str | None,
    role: str | None,
    slug: str,
    score_v2: float | None,
    cites: int,
    h_index: int,
    tags: list[dict] | None,
    paper_title: str,
    breakthrough: float,
    commercial: float,
    buzz: float,
    date_label: str,
) -> str:
    name = escape(name_en)
    name_zh_e = escape(name_zh or "")
    flag = _flag(country)
    role_e = escape((role or "").upper().replace("_", " ") or "")
    score_str = f"{score_v2:.2f}" if score_v2 is not None else "—"

    title_lines = _wrap(_truncate(paper_title, 70), 34)
    title_svg = ""
    y = 360
    for line in title_lines:
        title_svg += (
            f'<text x="36" y="{y}" font-family="Playfair Display, serif" '
            f'font-size="26" font-weight="700" fill="#111">{escape(line)}</text>\n'
        )
        y += 32

    top2 = _top_two_pillars(breakthrough, commercial, buzz)
    bars_svg = ""
    for i, (label, value, color) in enumerate(top2):
        bars_svg += _pillar_bar(36, 480 + i * 40, label, value, color)

    tag = escape(_signal_or_first_tag(tags))

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

  <!-- Invest score (top-right, under the flag) -->
  <text x="{CARD_W - 36}" y="160" font-family="Inter, sans-serif" font-size="11" font-weight="700" letter-spacing="3" fill="#CC0000" text-anchor="end">INVEST SCORE</text>
  <text x="{CARD_W - 36}" y="220" font-family="Playfair Display, serif" font-weight="900" font-size="64" fill="#CC0000" text-anchor="end" letter-spacing="-2">{score_str}</text>

  <!-- Name -->
  <text x="36" y="280" font-family="Playfair Display, serif" font-weight="900" font-size="44" fill="#111" letter-spacing="-1">{name}</text>
  {f'<text x="36" y="312" font-family="Lora, serif" font-style="italic" font-size="22" fill="#525252">{name_zh_e}</text>' if name_zh_e else ""}

  <!-- Country flag + role -->
  <text x="{CARD_W - 36}" y="280" font-family="JetBrains Mono, monospace" font-size="22" font-weight="700" fill="#111" text-anchor="end">{flag}</text>
  {f'<text x="{CARD_W - 36}" y="308" font-family="Inter, sans-serif" font-size="12" font-weight="700" letter-spacing="2" fill="#737373" text-anchor="end">{role_e}</text>' if role_e else ""}

  <!-- Paper title -->
  {title_svg}

  <!-- Pillar bars -->
  {bars_svg}

  <!-- Bottom: stats -->
  <line x1="36" y1="580" x2="{CARD_W - 36}" y2="580" stroke="#111" stroke-width="2"/>
  <text x="36" y="624" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#737373" letter-spacing="3">CITATIONS</text>
  <text x="36" y="666" font-family="Playfair Display, serif" font-weight="900" font-size="36" fill="#111">{cites:,}</text>

  <text x="220" y="624" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#737373" letter-spacing="3">H-INDEX</text>
  <text x="220" y="666" font-family="Playfair Display, serif" font-weight="900" font-size="36" fill="#111">{h_index}</text>

  <text x="360" y="624" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#CC0000" letter-spacing="3">TAG</text>
  <text x="360" y="660" font-family="Inter, sans-serif" font-size="16" font-weight="700" fill="#111">{tag}</text>

  <text x="{CARD_W - 36}" y="690" font-family="JetBrains Mono, monospace" font-size="11" fill="#737373" text-anchor="end">openscout.app/researchers/{escape(slug)}</text>
</svg>
"""


def _fallback_rows(db, brief_date: Date) -> list[tuple[Researcher, Paper]]:
    """Original behavior: today's first-author papers, ranked by author count."""
    author_count_sq = (
        select(PaperAuthor.paper_id, func.count(PaperAuthor.researcher_id).label("n"))
        .group_by(PaperAuthor.paper_id)
        .subquery()
    )
    candidates_stmt = (
        select(Researcher, Paper)
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
    return [(r, p) for (r, p) in db.execute(candidates_stmt).all()]


def write_daily_cards(brief_date: Date | None = None) -> dict[str, int | str]:
    """Generate today's 9-card grid. Returns count of cards written."""
    if brief_date is None:
        brief_date = datetime.now(UTC).date()

    out_dir = SOCIAL_DIR / brief_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    date_label = brief_date.strftime("%b %-d %Y").upper()

    # Primary path: Investment Lens picks.
    picks = top_investment_picks(limit=9)

    card_count = 0
    with session_scope() as db:
        if picks:
            for i, p in enumerate(picks, start=1):
                # Refresh ORM lookup so we get full citation/h-index/tags fields.
                r = db.execute(
                    select(Researcher).where(Researcher.slug == p["slug"])
                ).scalar_one_or_none()
                if r is None:
                    continue
                tp = p.get("top_paper") or {}
                svg = _card_svg(
                    i,
                    name_en=r.name_en,
                    name_zh=r.name_zh,
                    country=r.country,
                    role=r.current_role,
                    slug=r.slug,
                    score_v2=r.investability_score_v2,
                    cites=r.citation_count or 0,
                    h_index=r.h_index or 0,
                    tags=r.tags,
                    paper_title=tp.get("title", ""),
                    breakthrough=tp.get("breakthrough") or 0.0,
                    commercial=tp.get("commercial") or 0.0,
                    buzz=tp.get("buzz") or 0.0,
                    date_label=date_label,
                )
                (out_dir / f"card_{i:02d}.svg").write_text(svg, encoding="utf-8")
                card_count += 1
        else:
            # Fallback path: yesterday's brief-style first-author rows.
            rows = _fallback_rows(db, brief_date)
            for i, (r, paper) in enumerate(rows, start=1):
                svg = _card_svg(
                    i,
                    name_en=r.name_en,
                    name_zh=r.name_zh,
                    country=r.country,
                    role=r.current_role,
                    slug=r.slug,
                    score_v2=r.investability_score_v2,
                    cites=r.citation_count or 0,
                    h_index=r.h_index or 0,
                    tags=r.tags,
                    paper_title=paper.title or "",
                    breakthrough=paper.breakthrough_score or 0.0,
                    commercial=paper.commercial_score or 0.0,
                    buzz=round(min(1.0, (paper.buzz_score or 0) / 3.0), 3),
                    date_label=date_label,
                )
                (out_dir / f"card_{i:02d}.svg").write_text(svg, encoding="utf-8")
                card_count += 1

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

    return {"cards": card_count, "out_dir": str(out_dir)}
