"""Send the daily brief as an HTML email via Resend.

Graceful no-op when RESEND_API_KEY or NOTIFY_EMAIL_TO is unset.
"""

import httpx
from sqlalchemy import desc, select

from ..config import settings
from ..db import session_scope
from ..models import DailyBrief


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

        html = _md_to_html(brief.rendered_md or "")
        subject = f"OpenScout · Vol. {brief.volume}, No. {brief.issue:03d} · {brief.brief_date}"

        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": "OpenScout <noreply@openscout.app>",
                "to": [settings.notify_email_to],
                "subject": subject,
                "html": html,
            },
            timeout=20.0,
        )
        if resp.status_code >= 400:
            return {"sent": False, "reason": f"Resend {resp.status_code}: {resp.text[:200]}"}
        return {"sent": True, "brief_date": brief.brief_date.isoformat()}


def _md_to_html(md: str) -> str:
    """Minimal Markdown → HTML — enough for the brief's structure. No deps."""
    import re

    html_parts = ['<div style="font-family: Georgia, serif; max-width: 720px; margin: 0 auto;">']
    for line in md.splitlines():
        if line.startswith("# "):
            html_parts.append(
                f'<h1 style="font-size: 36px; margin: 24px 0 8px;">{_inline(line[2:])}</h1>'
            )
        elif line.startswith("## "):
            html_parts.append(
                f'<h2 style="font-size: 22px; border-bottom: 2px solid #111; padding-bottom: 4px; margin: 30px 0 12px;">{_inline(line[3:])}</h2>'
            )
        elif line.startswith("### "):
            html_parts.append(
                f'<h3 style="font-size: 16px; margin: 18px 0 6px;">{_inline(line[4:])}</h3>'
            )
        elif line.startswith("> "):
            html_parts.append(
                f'<blockquote style="border-left: 3px solid #ccc; padding-left: 12px; color: #555; font-style: italic;">{_inline(line[2:])}</blockquote>'
            )
        elif line.startswith("---"):
            html_parts.append('<hr style="border: 0; border-top: 2px solid #111; margin: 18px 0;">')
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
    html_parts.append(
        '<footer style="margin-top: 40px; padding-top: 12px; border-top: 1px solid #ccc; font-size: 11px; color: #888; text-align: center;">OpenScout · openscout.app</footer>'
    )
    html_parts.append("</div>")
    return "\n".join(html_parts)


def _inline(text: str) -> str:
    """Inline markdown: [text](url), **bold**, *italic*, `code`."""
    import re

    # Link
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # Code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text
