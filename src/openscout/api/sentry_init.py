"""Sentry initialization — opt-in via env var.

If `SENTRY_DSN` is set, captures backend errors + 5% performance traces.
If unset, the function no-ops cleanly (no startup error in local dev where
nobody's set the DSN).

Free tier is enough for low-traffic launch.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def init_sentry() -> bool:
    """Return True if Sentry was actually initialized."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        log.warning("SENTRY_DSN set but sentry-sdk not installed; skipping init")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENV", "production"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        release=os.environ.get("OPENSCOUT_VERSION", "dev"),
    )
    log.info("Sentry initialized (env=%s)", os.environ.get("SENTRY_ENV", "production"))
    return True
