# vision_agent/vision_kb_lookup.py
"""
Lets the vision agent look up prior findings in the shared knowledge base
before or after analyzing a new image — e.g. "has this tag/equipment been
flagged before" for cross-referencing across inspection visits.

Kept as a thin, separate function rather than baked into analyze_image()
itself: querying the KB is a distinct action from extracting observations
from THIS image, and the vision model's own OBSERVED/UNCLEAR output should
never be silently blended with retrieved historical text in the same call.
"""

from knowledge.retriever import query_knowledge, query_knowledge_with_metadata


def find_prior_findings(equipment_tag_or_question: str, n: int = 5) -> list[str]:
    """
    Search only past vision observations (never UNCLEAR guesses) for
    cross-reference. E.g. find_prior_findings("PT-101") to see if this tag
    was previously noted as abnormal.
    """
    return query_knowledge(
        equipment_tag_or_question,
        n=n,
        content_types=["vision_observed"],
    )


def find_prior_findings_with_source(equipment_tag_or_question: str, n: int = 5) -> list[dict]:
    """
    Same as above but includes metadata (source_file, source_id) so the
    caller can say "this tag was also flagged in scan_2024_03.png" rather
    than just repeating the finding with no provenance.
    """
    return query_knowledge_with_metadata(
        equipment_tag_or_question,
        n=n,
        content_types=["vision_observed"],
    )