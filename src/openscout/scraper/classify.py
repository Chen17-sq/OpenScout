"""LLM topic classifier — Anthropic Claude as a hard filter after arXiv query.

arXiv category filters are coarse (cs.RO catches some non-robotics; q-bio.BM
catches non-ML biology; etc.). This classifier reads each paper's title +
abstract and decides whether it's actually about the topic, with a confidence
in [0, 1].

Re-uses on cache: once a (paper_id, topic_id) pair is classified, we don't
re-call. Graceful skip without ANTHROPIC_API_KEY.

Effect on the pipeline: only papers that pass the LLM filter remain linked
to the topic via paper_topics. Borderline papers get unlinked.
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


def _classify_one(client, title: str, abstract: str, topic_slug: str) -> tuple[bool, float]:
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
            model="claude-haiku-4-5",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (resp.content[0].text if resp.content else "").strip()
        # Extract JSON
        import json
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return False, 0.0
        data = json.loads(m.group(0))
        return bool(data.get("relevant")), float(data.get("confidence", 0.0))
    except Exception:
        return False, 0.0


def filter_topic_papers(topic_slug: str, limit: int = 30) -> dict[str, int]:
    """Run LLM filter on papers currently linked to `topic_slug` but unverified.

    Removes the PaperTopic link for papers the LLM judges irrelevant.
    """
    counts = {"checked": 0, "kept": 0, "removed": 0, "skipped_no_key": 0, "errors": 0}

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

        for p in papers:
            counts["checked"] += 1
            relevant, conf = _classify_one(client, p.title, p.abstract or "", topic_slug)
            if relevant and conf > 0.5:
                counts["kept"] += 1
            else:
                # Remove the PaperTopic link
                db.execute(
                    PaperTopic.__table__.delete().where(
                        PaperTopic.paper_id == p.id, PaperTopic.topic_id == topic.id
                    )
                )
                counts["removed"] += 1
            time.sleep(0.2)

    return counts
