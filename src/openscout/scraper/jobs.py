"""Async deep-dive runner.

Pre-v1.12 the deep-dive endpoint ran synchronously — blocked the API thread
for 30s, terrible UX. This module enqueues a job, returns a job_id, and
runs the dive in a background thread. The frontend polls
`GET /jobs/{id}` (or subscribes via SSE) to watch progress.

Why threads not async asyncio: the deep_dive scrapers use `arxiv` lib which
is sync + has internal time.sleep — wrapping in asyncio.to_thread would
serialize anyway, so plain Threads are simpler.

Why a SQLite-backed job table instead of an in-memory dict: surviving an
API restart matters in production (Fly.io re-deploys every push). One
running job per process; for higher concurrency, swap for Celery later.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from sqlalchemy import desc, select

from ..db import session_scope
from ..models import DeepDiveJob, Researcher

# Cap on simultaneously-running threads. SQLite handles a couple of writers
# fine; OpenAlex / S2 rate-limit any harder. Beyond 4 we'd just queue at the
# upstream APIs.
MAX_CONCURRENT_JOBS = 4
_active_lock = threading.Lock()
_active_count = 0


def enqueue(slug: str, ip_address: str | None = None, force: bool = False) -> dict:
    """Insert a queued row + spin a thread. Returns the new job dict.

    Returns the EXISTING running job if one is already running for this slug
    (don't double-dive a single researcher).
    """
    with session_scope() as db:
        # Already-running job dedupe — return the existing one
        existing = db.execute(
            select(DeepDiveJob)
            .where(DeepDiveJob.slug == slug, DeepDiveJob.state.in_(("queued", "running")))
            .order_by(desc(DeepDiveJob.enqueued_at))
            .limit(1)
        ).scalar_one_or_none()
        if existing:
            return _serialize(existing)

        # Verify researcher exists
        r = db.execute(select(Researcher).where(Researcher.slug == slug)).scalar_one_or_none()
        if not r:
            return {"error": f"researcher {slug!r} not found"}

        job = DeepDiveJob(
            slug=slug,
            state="queued",
            progress=[],
            ip_address=ip_address,
        )
        db.add(job)
        db.flush()
        job_id = int(job.id)
        result = _serialize(job)

    # Start worker AFTER the session commits, so the row is visible to the thread.
    threading.Thread(target=_run, args=(job_id, force), daemon=True).start()
    return result


def get(job_id: int) -> dict | None:
    with session_scope() as db:
        job = db.execute(select(DeepDiveJob).where(DeepDiveJob.id == job_id)).scalar_one_or_none()
        return _serialize(job) if job else None


def _serialize(job: DeepDiveJob) -> dict:
    return {
        "id": int(job.id),
        "slug": job.slug,
        "state": job.state,
        "progress": job.progress or [],
        "result": job.result,
        "error": job.error,
        "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _run(job_id: int, force: bool) -> None:
    """Background thread: pull the job, run deep_dive_one, write progress."""
    global _active_count

    # Cap concurrent jobs. If at cap, mark as queued; the next finishing job
    # could in principle promote one — but for simplicity here we just fail
    # fast with a clear message. (Future: real queue worker.)
    with _active_lock:
        if _active_count >= MAX_CONCURRENT_JOBS:
            with session_scope() as db:
                job = db.execute(
                    select(DeepDiveJob).where(DeepDiveJob.id == job_id)
                ).scalar_one_or_none()
                if job:
                    job.state = "failed"
                    job.error = f"queue full (>{MAX_CONCURRENT_JOBS} concurrent dives)"
                    job.finished_at = datetime.now(UTC)
            return
        _active_count += 1

    try:
        with session_scope() as db:
            job = db.execute(
                select(DeepDiveJob).where(DeepDiveJob.id == job_id)
            ).scalar_one_or_none()
            if not job:
                return
            slug = job.slug
            job.state = "running"
            job.started_at = datetime.now(UTC)

        # Run the dive. We can't easily stream per-source from inside
        # deep_dive_one without refactoring; for now we run it whole and
        # write the result at the end. SSE in v1.13 will refactor for true
        # incremental streaming. Polling already works fine.
        from .deep_dive import deep_dive_one

        try:
            result = deep_dive_one(slug, force=force)
            terminal_state = "succeeded"
            err: str | None = None
        except Exception as exc:  # noqa: BLE001
            result = {"slug": slug, "error": str(exc)}
            terminal_state = "failed"
            err = f"{type(exc).__name__}: {exc}"

        with session_scope() as db:
            job = db.execute(
                select(DeepDiveJob).where(DeepDiveJob.id == job_id)
            ).scalar_one_or_none()
            if not job:
                return
            job.state = terminal_state
            job.result = result
            job.error = err
            job.progress = [
                {"source": name, **info} for name, info in (result.get("sources") or {}).items()
            ]
            job.finished_at = datetime.now(UTC)
    finally:
        with _active_lock:
            _active_count -= 1
