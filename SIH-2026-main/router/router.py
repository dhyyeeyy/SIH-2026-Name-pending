"""
Semantic router: classifies an incoming query into a model role
(general / code / vision) using embedding similarity against a small
labelled example set, with a hard override to vision when there's no
extractable text and an attachment is present.

Does NOT use a full LLM to classify -- reuses the CPU-pinned embedding
model so classification costs no VRAM and runs in milliseconds.
"""

import json
import math
from pathlib import Path

import ollama

CONFIG_PATH = Path(__file__).parent / "model_config.json"

# Labelled examples per role. Keep these short and varied -- the router
# compares the incoming query's embedding against each example and takes
# the closest match by average similarity per category.
CATEGORY_EXAMPLES = {
    "general": [
        "Summarize this inspection report for me.",
        "What are the key findings in this document?",
        "Explain the maintenance procedure described in the SOP.",
        "Draft a memo based on this correspondence.",
        "What does this manual say about safety protocols?",
    ],
    "code": [
        "Write a Python function to parse this log file.",
        "Fix the bug in this script.",
        "Generate a script that calculates the load tolerance.",
        "Refactor this function to be more efficient.",
        "Write unit tests for this module.",
    ],
}


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_embedding_cache: dict[tuple[str, str], list[float]] = {}


def _embed(text: str, embedding_model: str) -> list[float]:
    key = (embedding_model, text)
    if key not in _embedding_cache:
        response = ollama.embeddings(model=embedding_model, prompt=text)
        _embedding_cache[key] = response["embedding"]
    return _embedding_cache[key]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def route(
    query: str,
    attachments: list[str] | None = None,
    has_extractable_text: bool = True,
) -> dict:
    """
    Classify a query into a model role.

    Returns a dict: {"role": str, "confidence": float, "override": bool}

    Hard override: if attachments are present and there's no extractable
    text layer (i.e. a scanned image/PDF), always route to vision --
    skip the embedding classification step entirely.
    """
    if attachments and not has_extractable_text:
        return {"role": "vision", "confidence": 1.0, "override": True}

    config = _load_config()
    embedding_model = config["models"]["embedding"]["ollama_tag"]

    query_vec = _embed(query, embedding_model)

    best_role = "general"
    best_score = -1.0
    for role, examples in CATEGORY_EXAMPLES.items():
        scores = [
            _cosine_similarity(query_vec, _embed(example, embedding_model))
            for example in examples
        ]
        avg_score = sum(scores) / len(scores)
        if avg_score > best_score:
            best_score = avg_score
            best_role = role

    return {"role": best_role, "confidence": best_score, "override": False}
