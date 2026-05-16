"""LLM topic classifier — Anthropic Claude as a hard filter after arXiv query.

arXiv category filters are coarse (cs.RO catches some non-robotics; q-bio.BM
catches non-ML biology; etc.). This classifier reads each paper's title +
abstract and decides whether it's actually about the topic, with a confidence
in [0, 1].

Critical safety: an API error (model 404, rate limit, account out of credit,
network) **must NOT** be treated as "not relevant" — that would silently delete
paper-topic links. On any API failure we leave the link alone.
"""

import time

from sqlalchemy import desc, select

from ..config import settings
from ..db import session_scope
from ..models import Paper, PaperTopic, Topic

TOPIC_DESCRIPTIONS = {
    "embodied": (
        "Embodied AI / robotics: physical robot manipulation, locomotion, "
        "dexterous skills, sim-to-real, VLA (vision-language-action), humanoid "
        "policies, foundation models for control."
    ),
    "world_models": (
        "World models: video prediction, learned dynamics models, latent "
        "dynamics, JEPA-family, generative simulators for embodied / driving."
    ),
    "ai4sci": (
        "AI for Science: ML-driven protein structure / drug design, molecular "
        "generation, materials discovery, ML potentials, scientific foundation "
        "models. NOT generic physics / chemistry without ML focus."
    ),
}

# Current Anthropic model alias — tracked here so we can update in one place.
MODEL = "claude-haiku-4-5"


def _classify_one(client, title: str, abstract: str, topic_slug: str) -> tuple[bool | None, float]:
    """Return (relevant, confidence). `relevant=None` means API error — caller
    MUST NOT remove the topic link in this case."""
    desc_text = TOPIC_DESCRIPTIONS.get(topic_slug, topic_slug)
    prompt = f"""Topic: {topic_slug}
Definition: {desc_text}

Paper:
Title: {title}
Abstract: {abstract[:1800]}

Question: Is this paper centrally about the topic above? Respond with ONLY a JSON object:
{{"relevant": true|false, "confidence": 0.0-1.0, "reason": "<one short sentence>"}}"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        # API/network/credit/model-id failure. Skip — do not touch the topic link.
        return None, 0.0

    try:
        text = (resp.content[0].text if resp.content else "").strip()
        import json
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return False, 0.0
        data = json.loads(m.group(0))
        return bool(data.get("relevant")), float(data.get("confidence", 0.0))
    except Exception:
        # Parse failure on a successful API call — treat as inconclusive (skip).
        return None, 0.0


def filter_topic_papers(topic_slug: str, limit: int = 30) -> dict[str, int]:
    """Run LLM filter on papers currently linked to `topic_slug`.

    Removes the PaperTopic link only when the LLM explicitly judges the paper
    irrelevant. API failures are skipped (no removal).
    """
    counts = {
        "checked": 0,
        "kept": 0,
        "removed": 0,
        "skipped_no_key": 0,
        "skipped_api_error": 0,
        "errors": 0,
    }

    if not settings.anthropic_api_key:
        counts["skipped_no_key"] = limit
        return counts

    try:
        import anthropic
    except ImportError:
        return {**counts, "errors": limit}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    with session_scope() as db:
        topic = db.execute(select(Topic).where(Topic.slug == topic_slug)).scalar_one_or_none()
        if not topic:
            return counts

        papers = list(
            db.execute(
                select(Paper)
                .join(PaperTopic, PaperTopic.paper_id == Paper.id)
                .where(PaperTopic.topic_id == topic.id)
                .order_by(desc(Paper.first_seen_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )

        # Stop early if API errors pile up — likely a systemic problem (auth,
        # credit, model id). No point burning through the queue.
        consecutive_errors = 0

        for p in papers:
            counts["checked"] += 1
            relevant, conf = _classify_one(client, p.title, p.abstract or "", topic_slug)
            if relevant is None:
                counts["skipped_api_error"] += 1
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    # 3 in a row → bail; don't waste more API calls.
                    counts["errors"] = limit - counts["checked"]
                    break
                time.sleep(0.5)
                continue
            consecutive_errors = 0
            if relevant and conf > 0.5:
                counts["kept"] += 1
            else:
                db.execute(
                    PaperTopic.__table__.delete().where(
                        PaperTopic.paper_id == p.id,
                        PaperTopic.topic_id == topic.id,
                    )
                )
                counts["removed"] += 1
            time.sleep(0.2)

    return counts
