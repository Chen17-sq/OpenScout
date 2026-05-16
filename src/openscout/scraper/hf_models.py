"""HuggingFace models endpoint — track model releases.

For each anchor researcher, search HF for their author/org and look at recent
models. Stores results as Signal rows of type='hf_model_release'.

HF's public API: https://huggingface.co/api/models?search=<name>&limit=20
"""

import time

import httpx
from sqlalchemy import select

from ..db import session_scope
from ..models import Researcher, Signal


def discover_models(limit: int = 30, sleep_between: float = 0.6) -> dict[str, int]:
    counts = {"attempted": 0, "hits": 0, "errors": 0, "signals_added": 0}
    client = httpx.Client(
        headers={"User-Agent": "OpenScout/0.6 (+https://github.com/Chen17-sq/OpenScout)"},
        timeout=15.0,
    )
    try:
        with session_scope() as db:
            anchors = list(
                db.execute(
                    select(Researcher).where(
                        Researcher.confidence_level.in_(["high", "medium"]),
                        Researcher.github_handle.is_not(None),
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            # Fall back: try by name when GH handle is missing
            if len(anchors) < limit:
                others = list(
                    db.execute(
                        select(Researcher)
                        .where(
                            Researcher.confidence_level.in_(["high", "medium"]),
                            Researcher.github_handle.is_(None),
                        )
                        .limit(limit - len(anchors))
                    )
                    .scalars()
                    .all()
                )
                anchors.extend(others)

            for r in anchors:
                counts["attempted"] += 1
                # Search HF for the researcher's name; many AI researchers have HF accounts
                try:
                    resp = client.get(
                        "https://huggingface.co/api/models",
                        params={"search": r.name_en, "limit": 5, "sort": "lastModified"},
                    )
                except Exception:
                    counts["errors"] += 1
                    continue
                if resp.status_code != 200:
                    counts["errors"] += 1
                    continue
                try:
                    data = resp.json() or []
                except Exception:
                    counts["errors"] += 1
                    continue
                if not data:
                    continue
                counts["hits"] += 1

                for model in data[:3]:
                    model_id = model.get("id") or model.get("modelId")
                    if not model_id:
                        continue
                    existing = db.execute(
                        select(Signal).where(
                            Signal.researcher_id == r.id,
                            Signal.type == "hf_model_release",
                            Signal.source == model_id,
                        )
                    ).scalar_one_or_none()
                    if existing:
                        continue
                    db.add(
                        Signal(
                            researcher_id=r.id,
                            type="hf_model_release",
                            payload={
                                "model_id": model_id,
                                "downloads": model.get("downloads"),
                                "likes": model.get("likes"),
                                "lastModified": model.get("lastModified"),
                            },
                            source=model_id,
                        )
                    )
                    counts["signals_added"] += 1
                time.sleep(sleep_between)
    finally:
        client.close()
    return counts
