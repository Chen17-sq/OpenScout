"""LLM topic classifier — provider-agnostic (Anthropic or DeepSeek).

arXiv category filters are coarse. This classifier reads each paper's title +
abstract and decides whether it's actually about the topic.

Critical safety: an API error must NOT be treated as "not relevant" — that
would silently delete paper-topic links. On any API failure we leave the
link alone.
"""

import json
import re
import time

from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper, PaperTopic, Topic
from . import llm

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


def _classify_one(title: str, abstract: str, topic_slug: str) -> tuple[bool | None, float]:
    """Return (relevant, confidence). `relevant=None` = API error → skip."""
    desc_text = TOPIC_DESCRIPTIONS.get(topic_slug, topic_slug)
    prompt = f"""Topic: {topic_slug}
Definition: {desc_text}

Paper:
Title: {title}
Abstract: {abstract[:1800]}

Question: Is this paper centrally about the topic above? Respond with ONLY a JSON object:
{{"relevant": true|false, "confidence": 0.0-1.0, "reason": "<one short sentence>"}}"""

    text, _err = llm.complete(prompt, max_tokens=200)
    if text is None:
        return None, 0.0

    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return False, 0.0
        data = json.loads(m.group(0))
        return bool(data.get("relevant")), float(data.get("confidence", 0.0))
    except Exception:
        return None, 0.0  # parse failure → skip, don't remove


def filter_topic_papers(topic_slug: str, limit: int = 30) -> dict[str, int]:
    """Re-classify papers under `topic_slug`; remove only explicit negatives."""
    counts = {
        "checked": 0,
        "kept": 0,
        "removed": 0,
        "skipped_no_provider": 0,
        "skipped_api_error": 0,
        "errors": 0,
    }

    if not llm.is_available():
        counts["skipped_no_provider"] = limit
        return counts

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

        consecutive_errors = 0
        for p in papers:
            counts["checked"] += 1
            relevant, conf = _classify_one(p.title, p.abstract or "", topic_slug)
            if relevant is None:
                counts["skipped_api_error"] += 1
                consecutive_errors += 1
                if consecutive_errors >= 3:
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
