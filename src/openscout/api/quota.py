"""Per-IP daily quota for deep-dive (or any expensive endpoint).

Deep-dive burns S2 + OpenAlex + DeepSeek API quota and takes 30s. Without a
quota, the front page is trivially abusable (refresh-spam the button on a
hot researcher → thousands of dives in minutes). 3 dives/day per IP is
generous for an investor browsing a few profiles, harsh for bots.

Default: 3 dives / IP / UTC day.
Override per endpoint by passing `daily_limit=N` to `check_and_increment`.

No auth needed for v1 — IP is sufficient. When magic-link auth lands later,
swap `ip_for_request` for `user_id_for_request` without touching the
quota-counting logic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlalchemy import select

from ..db import session_scope
from ..models import DeepDiveQuota


def _ip_for_request(req: Request) -> str:
    """Pick the client IP — respect X-Forwarded-For if present (we're behind
    Vercel/Fly.io which set this), else fall back to socket addr.
    """
    xff = req.headers.get("x-forwarded-for", "")
    if xff:
        # XFF is comma-separated, first entry is the originating client
        return xff.split(",")[0].strip()
    return (req.client.host if req.client else "0.0.0.0") or "0.0.0.0"


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def check_and_increment(
    req: Request,
    *,
    daily_limit: int = 3,
    endpoint: str = "deep_dive",
) -> dict:
    """Atomically check quota + increment, or raise HTTPException(429).

    Returns the post-increment counter state so the endpoint can echo it back
    (e.g. as `X-RateLimit-Remaining` header).
    """
    ip = _ip_for_request(req)
    day = _today()

    with session_scope() as db:
        row = db.execute(
            select(DeepDiveQuota).where(
                DeepDiveQuota.ip_address == ip,
                DeepDiveQuota.day == day,
            )
        ).scalar_one_or_none()

        if row is None:
            row = DeepDiveQuota(ip_address=ip, day=day, count=1)
            db.add(row)
            db.flush()
            return {
                "ip": ip,
                "day": day,
                "count": 1,
                "limit": daily_limit,
                "remaining": daily_limit - 1,
            }

        if row.count >= daily_limit:
            # Don't mutate; just refuse
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Daily {endpoint} limit reached ({row.count}/{daily_limit}). "
                    "Resets at UTC midnight."
                ),
                headers={
                    "X-RateLimit-Limit": str(daily_limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": _seconds_until_midnight(),
                },
            )

        row.count += 1
        # touched_at auto-updates via onupdate=func.now()
        return {
            "ip": ip,
            "day": day,
            "count": row.count,
            "limit": daily_limit,
            "remaining": daily_limit - row.count,
        }


def status(req: Request, daily_limit: int = 3) -> dict:
    """Read-only quota check — what's left without incrementing.

    Used by the UI to render "you have N dives remaining today" before the
    user clicks the button.
    """
    ip = _ip_for_request(req)
    day = _today()
    with session_scope() as db:
        row = db.execute(
            select(DeepDiveQuota).where(
                DeepDiveQuota.ip_address == ip,
                DeepDiveQuota.day == day,
            )
        ).scalar_one_or_none()
        used = row.count if row else 0
    return {
        "day": day,
        "used": used,
        "limit": daily_limit,
        "remaining": max(0, daily_limit - used),
    }


def _seconds_until_midnight() -> str:
    """Seconds until the next UTC midnight, as a string (HTTP Retry-After)."""
    now = datetime.now(UTC)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return str(int((end - now).total_seconds()) + 1)
