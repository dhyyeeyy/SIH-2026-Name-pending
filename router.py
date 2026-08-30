import json
import math
from pathlib import Path
from typing import Optional

import ollama

CONFIG_PATH = Path(__file__).parent / "model_config.json"

DEFAULT_CODE_CONFIDENCE_THRESHOLD = 0.6

# Kept short and varied on purpose -- the router compares the incoming
# query's embedding against each example and averages similarity across
# all of them. Override via model_config.json's router.code_examples
# instead of editing this list directly, so tuning doesn't require a
# code change.
DEFAULT_CODE_EXAMPLES = [
    "Write a Python function to parse this log file.",
    "Fix the bug in this script.",
    "Generate a script that calculates the load tolerance.",
    "Refactor this function to be more efficient.",
    "Write unit tests for this module.",
]


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _router_settings(config: dict) -> tuple[list[str], float]:
    """Resolve code_examples + threshold, falling back to defaults for
    whichever piece (or all of it) is missing from model_config.json."""
    router_cfg = config.get("router", {})
    code_examples = router_cfg.get("code_examples") or DEFAULT_CODE_EXAMPLES
    threshold = router_cfg.get(
        "code_confidence_threshold", DEFAULT_CODE_CONFIDENCE_THRESHOLD
    )
    return code_examples, threshold


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


def route(query: str, config: Optional[dict] = None) -> dict:
    """
    Classify a query as "code" or "general".

    Args:
        query: the user's prompt. Never an attachment-bearing request --
            orchestrator.py filters those out before this is ever called.
        config: optional pre-loaded config dict, mainly for tests that
            want to inject a custom threshold/example set without writing
            a temp file. Defaults to loading model_config.json.

    Returns:
        {"role": "code" | "general", "confidence": float}

        confidence is the query's average cosine similarity against the
        code examples. role is "code" only if confidence clears the
        configured threshold -- otherwise "general", which is the safe
        default: an instruct_agent call on a code-ish prompt just answers
        (or says INSUFFICIENT CONTEXT) rather than failing outright, while
        a coder call on a non-code prompt could attempt to generate/run
        code that was never actually requested.
    """
    config = config if config is not None else _load_config()
    code_examples, threshold = _router_settings(config)

    embedding_model = (
        config.get("models", {}).get("embedding", {}).get("ollama_tag", "nomic-embed-text")
    )

    query_vec = _embed(query, embedding_model)
    scores = [
        _cosine_similarity(query_vec, _embed(example, embedding_model))
        for example in code_examples
    ]
    confidence = sum(scores) / len(scores)

    role = "code" if confidence >= threshold else "general"
    return {"role": role, "confidence": confidence}