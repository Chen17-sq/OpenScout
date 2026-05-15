"""SVG banner generator — Newsprint masthead.

Writes `web/static/banner.svg` and `web/static/og-card.svg` with today's date stamp.
Called from `openscout banner` CLI; can be wired into the daily cron.
"""

from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[3] / "web" / "static"


def render_banner_svg(brief_date: Date, issue: int) -> str:
    weekday = brief_date.strftime("%A").upper()
    pretty = brief_date.strftime("%B %-d, %Y").upper()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 480" font-family="Playfair Display, Times New Roman, serif">
  <rect width="1280" height="480" fill="#F9F9F7"/>
  <pattern id="dots" width="4" height="4" patternUnits="userSpaceOnUse">
    <path d="M1 3h1v1H1V3zm2-2h1v1H3V1z" fill="#111" fill-opacity="0.06"/>
  </pattern>
  <rect width="1280" height="480" fill="url(#dots)"/>

  <rect x="0" y="0" width="1280" height="40" fill="#111"/>
  <text x="40" y="26" fill="#F9F9F7" font-family="Inter, sans-serif" font-size="13" font-weight="700" letter-spacing="3">LIVE EDITION · VOL. 1 · NO. {issue:03d} · {weekday}</text>
  <text x="1240" y="26" fill="#F9F9F7" font-family="Inter, sans-serif" font-size="13" font-weight="700" letter-spacing="3" text-anchor="end">BEIJING / GLOBAL</text>

  <text x="640" y="240" font-size="180" font-weight="900" fill="#111" text-anchor="middle" letter-spacing="-8">OpenScout</text>

  <line x1="40" y1="290" x2="1240" y2="290" stroke="#111" stroke-width="1"/>
  <text x="40" y="320" font-family="JetBrains Mono, monospace" font-size="14" font-weight="500" fill="#111" letter-spacing="2">VOL. 1 · NO. {issue:03d}</text>
  <text x="640" y="320" font-family="Playfair Display, serif" font-size="18" font-style="italic" fill="#111" text-anchor="middle">"All The Researchers Fit To Watch."</text>
  <text x="1240" y="320" font-family="JetBrains Mono, monospace" font-size="14" font-weight="500" fill="#111" letter-spacing="2" text-anchor="end">{pretty}</text>
  <line x1="40" y1="335" x2="1240" y2="335" stroke="#111" stroke-width="1"/>

  <text x="640" y="395" font-family="Lora, serif" font-size="20" font-style="italic" fill="#525252" text-anchor="middle">一份每日发行的报纸 — 早期发现具身智能 · 世界模型 · AI for Science 中的高潜研究者。</text>

  <rect x="0" y="476" width="1280" height="4" fill="#111"/>
</svg>
"""


def render_og_card_svg(brief_date: Date, issue: int, tracked: int, papers: int) -> str:
    pretty = brief_date.strftime("%B %-d, %Y").upper()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640" font-family="Playfair Display, Times New Roman, serif">
  <rect width="1280" height="640" fill="#F9F9F7"/>
  <rect x="0" y="0" width="1280" height="56" fill="#111"/>
  <text x="640" y="38" fill="#F9F9F7" font-family="Inter, sans-serif" font-size="18" font-weight="700" letter-spacing="6" text-anchor="middle">OPENSCOUT · DAILY · VOL. 1 · NO. {issue:03d}</text>

  <text x="640" y="240" font-size="180" font-weight="900" fill="#111" text-anchor="middle" letter-spacing="-8">OpenScout</text>
  <text x="640" y="295" font-family="Playfair Display, serif" font-size="22" font-style="italic" fill="#525252" text-anchor="middle">"All The Researchers Fit To Watch."</text>

  <line x1="100" y1="360" x2="1180" y2="360" stroke="#111" stroke-width="2"/>

  <g transform="translate(180, 410)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">TRACKED</text>
    <text y="60" font-size="64" font-weight="900" fill="#111">{tracked:,}</text>
  </g>
  <g transform="translate(540, 410)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#CC0000" letter-spacing="3">PAPERS TODAY</text>
    <text y="60" font-size="64" font-weight="900" fill="#CC0000">{papers:,}</text>
  </g>
  <g transform="translate(900, 410)">
    <text font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#737373" letter-spacing="3">EDITION</text>
    <text y="60" font-size="64" font-weight="900" fill="#111">{pretty.split()[0][:3]} {brief_date.day}</text>
  </g>

  <line x1="100" y1="560" x2="1180" y2="560" stroke="#111" stroke-width="2"/>
  <text x="640" y="600" font-family="Lora, serif" font-size="16" font-style="italic" fill="#525252" text-anchor="middle">具身智能 · 世界模型 · AI for Science · 每天 09:00 北京</text>
</svg>
"""


def write_banners(brief_date: Date | None = None, *, tracked: int = 0, papers: int = 0) -> dict[str, Path]:
    """Generate banner.svg + og-card.svg in web/static/."""
    if brief_date is None:
        brief_date = datetime.now(timezone.utc).date()
    issue = (brief_date - Date(2026, 5, 15)).days + 1

    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    banner = STATIC_DIR / "banner.svg"
    banner.write_text(render_banner_svg(brief_date, issue), encoding="utf-8")

    og = STATIC_DIR / "og-card.svg"
    og.write_text(render_og_card_svg(brief_date, issue, tracked, papers), encoding="utf-8")

    return {"banner": banner, "og_card": og}
