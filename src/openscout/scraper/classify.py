"""Topic classifier — LLM-based hard filter for papers in our target topics.

KS uses brand whitelist + location matching; OpenScout uses LLM because researcher
topics aren't as clean as "is this a Chinese hardware project."

Two stages:
1. Cheap keyword pre-filter (in arxiv.py — done by the query itself)
2. LLM verification (here) — given title + abstract + topic, returns yes/no + confidence
"""

# TODO: implement via Anthropic Claude Haiku 4.5
# - Prompt: "Is this paper centrally about {topic}?" with topic descriptions
# - Cache by (arxiv_id, topic) since results don't change


def classify_paper(arxiv_id: str, title: str, abstract: str, topic_slug: str) -> tuple[bool, float]:
    """Return (is_relevant, confidence). Confidence in [0, 1]."""
    raise NotImplementedError("LLM topic classification — TODO")
