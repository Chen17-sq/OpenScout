"""Job-state endpoint for the async deep-dive runner.

Frontend usage:
  1. POST /researchers/{slug}/deep-dive  → returns {id, state: "queued", ...}
  2. Poll GET /jobs/{id} every 1-2s until state in {"succeeded","failed"}
  3. Read job.result for the dive output, job.progress for per-source updates
"""

from fastapi import APIRouter, HTTPException

from ...scraper import jobs as jobs_mod

router = APIRouter()


@router.get("/{job_id}")
def get_job(job_id: int) -> dict:
    job = jobs_mod.get(job_id)
    if not job:
        raise HTTPException(404, detail=f"job {job_id} not found")
    return job
