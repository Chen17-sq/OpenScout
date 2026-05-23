"""Send the daily brief as an HTML email via Resend.

Graceful no-op when RESEND_API_KEY or NOTIFY_EMAIL_TO is unset.

The email body is built from the latest DailyBrief's rendered Markdown plus a
freshly-queried "Investment Lens · Today's Picks" board (the investor wants
this at the top — it's the highest-value section for the audience). The Lens
is injected between Section A (KPI band) and Section B (new first authors),
matching the home-page reading order.

Email-client constraints we honor:
  - <table> for layout (not flex/grid — Outlook chokes)
  - inline styles (no external stylesheet)
  - hex colors only (no CSS vars)
  - <= 600px width
  - unicode emoji only (no SVG / font icons)
"""

import html
import re

import httpx
from sqlalchemy import desc, select

from ..config import settings
from ..db import session_scope
from ..models import DailyBrief
from .work_scoring import top_investment_picks

# Mirrors web/src/lib/api.ts → roleLabel(), so the chip text matches the UI.
_ROLE_LABEL: dict[str, str] = {
    "phd": "PhD",
    "postdoc": "Postdoc",
    "incoming_ap": "Incoming AP",
    "ap": "AP",
    "associate": "Associate",
    "full": "Full Prof",
    "senior": "Senior",
    "industry": "Industry",
}

# Pillar colours match InvestmentLens.svelte (purple / green / accent-orange).
_PILLAR_COLORS = {
    "b": "#6b3f9c",  # breakthrough
    "c": "#2f7a3a",  # commercial
    "z": "#c1440e",  # buzz (matches the brand accent used elsewhere)
}

_INK = "#111111"
_PAPER = "#fffdf7"
_MUTED = "#e6e2d6"
_N400 = "#9a9485"
_N500 = "#6b6657"
_N600 = "#4d4a3f"
_N700 = "#34322a"


def send_latest_digest() -> dict:
    """Send the most recent daily brief as HTML email.

    Returns {sent: bool, reason: str, brief_date: str?}.
    """
    if not settings.resend_api_key or not settings.notify_email_to:
        return {"sent": False, "reason": "missing RESEND_API_KEY or NOTIFY_EMAIL_TO"}

    with session_scope() as db:
        brief = db.execute(
            select(DailyBrief).order_by(desc(DailyBrief.brief_date)).limit(1)
        ).scalar_one_or_none()
        if not brief:
            return {"sent": False, "reason": "no briefs in DB"}

        # Investment Lens runs the same query the home page does — top 8, 30d
        # window. Failure here must NOT block the digest: the rest of the brief
        # is still valuable.
        try:
            picks = top_investment_picks(limit=8, window_days=30)
        except Exception:
            picks = []

        html_body = _build_html_body(brief.rendered_md or "", picks)
        subject = f"OpenScout · Vol. {brief.volume}, No. {brief.issue:03d} · {brief.brief_date}"

        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                # `from` must be a domain you've verified in Resend. Default to
                # Resend's shared sender (`onboarding@resend.dev`) which works
                # without any DNS setup but ONLY delivers to the email address
                # that owns the Resend account. Override via EMAIL_FROM env to
                # use your own verified domain once you have one.
                "from": settings.email_from or "OpenScout <onboarding@resend.dev>",
                "to": [settings.notify_email_to],
                "subject": subject,
                "html": html_body,
            },
            timeout=20.0,
        )
        if resp.status_code >= 400:
            return {"sent": False, "reason": f"Resend {resp.status_code}: {resp.text[:200]}"}
        return {"sent": True, "brief_date": brief.brief_date.isoformat()}


def _build_html_body(md: str, picks: list[dict] | None = None) -> str:
    """Render the full email HTML — markdown body with the Investment Lens
    section injected between Section A (KPI band) and Section B.

    `picks` is the structured list from `top_investment_picks`. When empty
    or None, the Lens section is suppressed so we don't render an empty
    placeholder for the user.
    """
    picks = picks or []
    lens_html = _render_investment_lens(picks) if picks else ""
    md_html = _md_to_html(md, lens_html=lens_html)
    return md_html


def _md_to_html(md: str, lens_html: str = "") -> str:
    """Minimal Markdown → HTML — enough for the brief's structure. No deps.

    When `lens_html` is provided, it is injected once before the first
    `## Section B` heading (the new-first-authors block). This places the
    Investment Lens between the KPI band and the rest of the brief, matching
    the home page's reading order.
    """
    html_parts = ['<div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto;">']
    lens_injected = False

    for line in md.splitlines():
        # Inject the Investment Lens right before Section B (after the KPI band).
        if lens_html and not lens_injected and line.startswith("## ") and "Section B" in line:
            html_parts.append(lens_html)
            lens_injected = True

        if line.startswith("# "):
            html_parts.append(
                f'<h1 style="font-size: 36px; margin: 24px 0 8px;">{_inline(line[2:])}</h1>'
            )
        elif line.startswith("## "):
            html_parts.append(
                f'<h2 style="font-size: 22px; border-bottom: 2px solid {_INK}; '
                f'padding-bottom: 4px; margin: 30px 0 12px;">{_inline(line[3:])}</h2>'
            )
        elif line.startswith("### "):
            html_parts.append(
                f'<h3 style="font-size: 16px; margin: 18px 0 6px;">{_inline(line[4:])}</h3>'
            )
        elif line.startswith("> "):
            html_parts.append(
                f'<blockquote style="border-left: 3px solid #ccc; padding-left: 12px; '
                f'color: #555; font-style: italic;">{_inline(line[2:])}</blockquote>'
            )
        elif line.startswith("---"):
            html_parts.append(
                f'<hr style="border: 0; border-top: 2px solid {_INK}; margin: 18px 0;">'
            )
        elif line.startswith("```"):
            continue  # skip code fences
        elif line.startswith("| "):
            # Naive table row
            cells = [c.strip() for c in line.strip("|").split("|")]
            html_parts.append(
                "<tr>"
                + "".join(f'<td style="padding: 6px 10px;">{_inline(c)}</td>' for c in cells)
                + "</tr>"
            )
        elif re.match(r"^[-*] ", line):
            html_parts.append(f'<li style="margin: 4px 0;">{_inline(line[2:])}</li>')
        elif line.strip() == "":
            html_parts.append("<br>")
        else:
            html_parts.append(f'<p style="margin: 8px 0;">{_inline(line)}</p>')

    # Fallback: if we never saw Section B (older briefs, edge cases), append
    # the Lens after the main markdown so the investor still sees the picks.
    if lens_html and not lens_injected:
        html_parts.append(lens_html)

    html_parts.append(
        '<footer style="margin-top: 40px; padding-top: 12px; border-top: 1px solid #ccc; '
        'font-size: 11px; color: #888; text-align: center;">'
        'OpenScout · <a href="https://openscout.app" style="color: #888;">openscout.app</a>'
        ' · <a href="https://openscout.app/unsubscribe" style="color: #888;">unsubscribe</a>'
        "</footer>"
    )
    html_parts.append("</div>")
    return "\n".join(html_parts)


def _inline(text: str) -> str:
    """Inline markdown: [text](url), **bold**, *italic*, `code`."""
    # Link
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # Code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


# ─── Investment Lens section ────────────────────────────────────────────────


def _flag(cc: str | None) -> str:
    """Regional-indicator flag emoji from an ISO-3166 alpha-2 country code.
    Mirrors the trick used in InvestmentLens.svelte (0x1F1A5 + 'A').
    """
    if not cc or len(cc) != 2:
        return ""
    cc = cc.upper()
    if not cc.isalpha():
        return ""
    return "".join(chr(0x1F1A5 + ord(c)) for c in cc)


def _role_chip(role: str | None) -> str:
    return _ROLE_LABEL.get(role, role) if role else ""


def _arxiv_link(arxiv_id: str | None) -> str:
    if not arxiv_id:
        return "#"
    if arxiv_id.startswith("or-"):
        return f"https://openscout.app/papers/{arxiv_id}"
    return f"https://arxiv.org/abs/{arxiv_id}"


def _pos_label(position: int | None) -> str:
    if not position:
        return ""
    if position == 1:
        return "1st"
    return f"#{position}"


def _pillar_bar(letter: str, value: float | None, color: str) -> str:
    """One pillar row, email-safe (nested table for the bar).

    Renders as: [B] [████░░░░░░] 0.42  inside a 3-column table.
    """
    v = float(value or 0.0)
    pct = max(0, min(100, int(round(v * 100))))
    # Nested table for the bar: outer cell is the muted background, inner cell
    # of width=pct% is the colored fill. Outlook respects table widths-percent
    # but not divs/spans with width.
    bar = (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse: collapse; width: 100%; height: 6px; '
        f'background: {_MUTED};">'
        f'<tr><td width="{pct}%" style="background: {color}; height: 6px; '
        f'line-height: 6px; font-size: 1px;">&nbsp;</td>'
        f'<td width="{100 - pct}%" style="height: 6px; line-height: 6px; '
        'font-size: 1px;">&nbsp;</td></tr></table>'
    )
    return (
        "<tr>"
        f"<td style=\"font-family: 'Courier New', monospace; font-size: 10px; "
        f'font-weight: 700; color: {_N600}; padding: 1px 6px 1px 0; width: 14px;">'
        f"{letter}</td>"
        f'<td style="padding: 1px 0;">{bar}</td>'
        f"<td style=\"font-family: 'Courier New', monospace; font-size: 10px; "
        f'color: {_N600}; padding: 1px 0 1px 6px; width: 32px; text-align: right;">'
        f"{v:.2f}</td>"
        "</tr>"
    )


def _why_chips(reasons: list[str]) -> str:
    if not reasons:
        return ""
    chips = "".join(
        "<span style=\"display: inline-block; font-family: 'Courier New', monospace; "
        f"font-size: 10px; border: 1px solid {_N400}; padding: 1px 5px; color: {_N700}; "
        f'background: {_PAPER}; margin: 0 4px 4px 0;">{html.escape(str(r))}</span>'
        for r in reasons
    )
    return (
        f'<div style="margin-top: 6px;">'
        f"<span style=\"font-family: 'Helvetica', sans-serif; font-size: 9px; "
        f"font-weight: 800; letter-spacing: 0.16em; color: {_N500}; "
        'margin-right: 6px;">WHY</span>'
        f"{chips}"
        "</div>"
    )


def _render_pick_row(idx: int, pick: dict) -> str:
    """Render a single pick as a self-contained <table> row.

    One pick = one outer <table> (full width). Inside: rank cell + body cell.
    Keeps Gmail/Outlook happy — no flex, no grid.
    """
    rank = f"{idx:02d}"
    name_en = html.escape(pick.get("name_en") or "")
    name_zh_raw = pick.get("name_zh")
    name_zh = (
        f'<span style="font-family: Lora, Georgia, serif; font-size: 13px; '
        f'color: {_N600}; margin-left: 6px;">{html.escape(name_zh_raw)}</span>'
        if name_zh_raw
        else ""
    )
    flag_emoji = _flag(pick.get("country"))
    flag_html = (
        f'<span style="font-size: 13px; margin-left: 6px;">{flag_emoji}</span>'
        if flag_emoji
        else ""
    )
    role_text = _role_chip(pick.get("current_role"))
    role_html = (
        f"<span style=\"display: inline-block; font-family: 'Courier New', monospace; "
        f"font-size: 9.5px; font-weight: 700; text-transform: uppercase; "
        f'border: 1px solid {_INK}; padding: 0 5px; color: {_INK}; margin-left: 8px;">'
        f"{html.escape(role_text)}</span>"
        if role_text
        else ""
    )
    score = float(pick.get("score") or 0.0)
    score_html = (
        f"<span style=\"font-family: 'Courier New', monospace; font-size: 13px; "
        f"font-weight: 700; color: {_PILLAR_COLORS['z']}; "
        'float: right;">{score:.2f}</span>'
    ).replace("{score:.2f}", f"{score:.2f}")

    profile_url = f"https://openscout.app/researchers/{pick.get('slug', '')}"
    name_link = (
        f'<a href="{profile_url}" style="font-family: \'Playfair Display\', Georgia, '
        f"serif; font-weight: 700; font-size: 17px; color: {_INK}; "
        f'text-decoration: none;">{name_en}</a>'
    )

    paper = pick.get("top_paper") or {}
    paper_html = ""
    if paper:
        pos = _pos_label(paper.get("position"))
        pos_chip = (
            f"<span style=\"display: inline-block; font-family: 'Courier New', "
            f"monospace; font-size: 9px; background: {_INK}; color: {_PAPER}; "
            f'padding: 1px 4px; margin-right: 6px; vertical-align: 2px;">{pos}</span>'
            if pos
            else ""
        )
        title = html.escape(paper.get("title") or "")
        paper_url = _arxiv_link(paper.get("arxiv_id"))
        paper_html = (
            f'<div style="font-family: Lora, Georgia, serif; font-size: 13px; '
            f'line-height: 1.4; color: {_N700}; margin: 8px 0;">'
            f"{pos_chip}"
            f'<a href="{paper_url}" style="color: {_INK}; text-decoration: underline; '
            f'text-decoration-color: {_N400};">{title}</a>'
            "</div>"
        )

        pillars = (
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'style="border-collapse: collapse; width: 100%; margin: 6px 0;">'
            + _pillar_bar("B", paper.get("breakthrough"), _PILLAR_COLORS["b"])
            + _pillar_bar("C", paper.get("commercial"), _PILLAR_COLORS["c"])
            + _pillar_bar("Z", paper.get("buzz"), _PILLAR_COLORS["z"])
            + "</table>"
        )

        why = _why_chips(paper.get("reasons") or [])
        paper_html = paper_html + pillars + why

    rank_cell = (
        f'<td valign="top" width="40" style="font-family: \'Playfair Display\', '
        f"Georgia, serif; font-weight: 900; font-size: 22px; color: {_INK}; "
        "padding: 16px 12px 16px 22px; line-height: 1; "
        f'border-bottom: 1px solid {_MUTED};">{rank}</td>'
    )
    body_cell = (
        f'<td valign="top" style="padding: 14px 22px 16px 0; '
        f'border-bottom: 1px solid {_MUTED};">'
        f'<div style="margin-bottom: 4px;">'
        f"{name_link}{name_zh}{flag_html}{role_html}{score_html}"
        "</div>"
        f"{paper_html}"
        "</td>"
    )
    return f"<tr>{rank_cell}{body_cell}</tr>"


def _render_investment_lens(picks: list[dict]) -> str:
    """Render the full Investment Lens section as an email-safe table.

    Bilingual labels match the web UI strings (zh + en title, zh meta).
    """
    rows = "".join(_render_pick_row(i + 1, p) for i, p in enumerate(picks))

    header = (
        '<tr><td colspan="2" style="padding: 22px 22px 14px; '
        f'border-bottom: 1px solid {_INK};">'
        f"<div style=\"font-family: 'Helvetica', sans-serif; font-size: 10px; "
        f"font-weight: 800; letter-spacing: 0.28em; text-transform: uppercase; "
        f'color: {_PILLAR_COLORS["z"]};">Investment Lens</div>'
        f"<div style=\"font-family: 'Playfair Display', Georgia, serif; "
        f"font-weight: 900; font-size: 26px; line-height: 1.1; color: {_INK}; "
        'margin-top: 4px;">'
        '投资视角 · 今日重点 <span style="font-size: 18px; font-weight: 700; '
        f"color: {_N600};\">/ Today's Picks</span></div>"
        f"<div style=\"font-family: 'Courier New', monospace; font-size: 11px; "
        f'color: {_N500}; margin-top: 4px;">'
        "按 突破 × 商业化 × 热度 三轴 · 30d window</div>"
        "</td></tr>"
    )

    legend_about = (
        '<tr><td colspan="2" style="padding: 12px 22px 14px; '
        f'background: {_MUTED}; border-top: 1px solid {_MUTED};">'
        f"<div style=\"font-family: 'Courier New', monospace; font-size: 10.5px; "
        f'color: {_N600};">'
        f'<strong style="color: {_INK}; margin-right: 4px;">B</strong> 突破 '
        "(S2 高质量引用 / oral) &nbsp; "
        f'<strong style="color: {_INK}; margin-right: 4px;">C</strong> 商业化 '
        "(代码 / star / 工业邮箱) &nbsp; "
        f'<strong style="color: {_INK}; margin-right: 4px;">Z</strong> 热度 '
        "(HF likes / alphaXiv)"
        "</div>"
        f'<div style="font-family: Georgia, serif; font-size: 11.5px; '
        f'color: {_N600}; margin-top: 8px; line-height: 1.5;">'
        "<strong>About the Lens</strong> — Ranked by breakthrough × commercial "
        "× buzz over the last 30 days. "
        f'<a href="https://openscout.app/investment" style="color: {_PILLAR_COLORS["z"]};">'
        "See web for full breakdown</a>."
        "</div>"
        "</td></tr>"
    )

    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'width="100%" style="border-collapse: collapse; width: 100%; max-width: 600px; '
        f"margin: 24px 0; border-top: 4px double {_INK}; "
        f'border-bottom: 1px solid {_INK}; background: {_PAPER};">'
        f"{header}{rows}{legend_about}"
        "</table>"
    )
