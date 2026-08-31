"""
router.py

Binary semantic router: is this prompt a coding task, or not?

Hand-rolled on purpose -- semantic-router (the third-party library) pulls
in numpy/pydantic-v2/etc. as transitive deps, which was causing install
failures in this environment. This version has no dependency beyond the
`ollama` client already used everywhere else in the system.

Fixes the real bug the earlier hand-rolled version had: it AVERAGED the
query's similarity across all code examples, so one weakly-matching
example (e.g. "write unit tests for this module" scoring low against an
unrelated-sounding query) could drag a genuinely code-shaped prompt below
threshold even when its single best-matching example scored high. This
version takes the MAX similarity across examples instead -- "does this
match ANY of the code examples well" rather than "does this match the
average of all of them" -- which is the actual right question for this
kind of few-shot classification.

Scope note, unchanged: this router only decides code vs. general. Vision
is a structural decision made in orchestrator.py before route() is ever
called (see orchestrator.py's module docstring) -- an attachment always
goes to vision, no embedding classification involved.

Reuses the CPU-pinned embedding model (nomic-embed-text) via Ollama, so
classification costs no VRAM and runs in milliseconds -- no generation
call involved.

Configurable via model_config.json's "router" section:

    {
      "models": { "embedding": { "ollama_tag": "nomic-embed-text" } },
      "router": {
        "code_confidence_threshold": 0.5,
        "code_examples": [
          "Write a Python function to parse this log file.",
          "Fix the bug in this script.",
          ...
        ]
      }
    }

Falls back to DEFAULT_CODE_EXAMPLES / DEFAULT_CODE_CONFIDENCE_THRESHOLD if
model_config.json or its "router" section doesn't exist, so this module
works out of the box.
"""

import json
import math
from pathlib import Path
from typing import Optional

import ollama

CONFIG_PATH = Path(__file__).parent / "model_config.json"

# NOTE: this threshold is compared against a MAX-over-examples score now,
# not an average -- not directly comparable to the old averaged 0.6
# cutoff. Raw cosine similarity between short phrases via nomic-embed-text
# typically lands in the ~0.4-0.7 range even for genuinely related text,
# so start here and tune against real prompts once you have some.
DEFAULT_CODE_CONFIDENCE_THRESHOLD = 0.55

DEFAULT_CODE_EXAMPLES = [
    "Write a Python function to parse this log file.",
    "Fix the bug in this script.",
    "Generate a script that calculates the load tolerance.",
    "Refactor this function to be more efficient.",
    "Write unit tests for this module.",
    "Write some code for me.",
    "Can you code this up.",
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

        confidence is the query's HIGHEST cosine similarity against any
        single code example (not an average -- see module docstring for
        why that changed). role is "code" only if that max score clears
        the configured threshold -- otherwise "general", which stays the
        safe default: a general call on a code-ish prompt just answers
        (or flags insufficient context) rather than failing outright,
        while a coder call on a non-code prompt risks generating/running
        code nobody asked for.
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
    confidence = max(scores)

    role = "code" if confidence >= threshold else "general"
    return {"role": role, "confidence": confidence}