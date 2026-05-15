"""Semantic Scholar enrichment — author disambiguation + paper metadata.

Stub for now. Will:
- Resolve arXiv paper → S2 paperId, attach authors with S2 author IDs
- For each S2 author: pull h-index, paper count, recent papers
- Match S2 author IDs to existing researchers (by name + affiliation) or create new
"""

# TODO: implement enrichment using `semanticscholar` Python package
# https://github.com/danielnsilva/semanticscholar


def enrich_recent_papers(limit: int = 100) -> int:
    """Enrich the most recently ingested papers with S2 author data.

    Returns: number of papers enriched.
    """
    raise NotImplementedError("Semantic Scholar enrichment — TODO")
