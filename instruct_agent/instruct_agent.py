"""
instruct_agent.py

Instruction-following reasoning over the shared knowledge base.

Model: smolLM:3B (Modelfile: `eng-general`) — chosen specifically because
this module's job is to follow an instruction *exactly* ("summarize this",
"extract only the dates", "make it shorter", "list only failures") against
retrieved context, without drifting into parametric knowledge or ignoring
the requested output shape. Instruction-following fidelity matters more
here than raw reasoning depth.

Import boundary (deliberate, enforced by what is and isn't imported below):
  - This module imports ONLY `knowledge.retriever` (read-only queries).
  - It NEVER imports `knowledge.ingest`. It has no code path that can write
    to ChromaDB. A summary or extraction produced here is not re-ingested
    into the KB — doing so would blend derived/interpreted content in with
    raw observations, the same problem vision_kb_lookup.py avoids on the
    vision side by keeping `vision_observed` separate from `vision_unclear`.

If you find yourself adding an `ingest` call to this file, stop — that
almost certainly belongs in vision.py / knowledge/ingest.py instead.
"""

import json
import logging
from typing import Optional

import aiohttp
import sys 
sys.path.append("C:/Users/Dharm/Desktop/Sovereign_AI")
from knowledge.retriever import query_knowledge_with_metadata

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "eng-instructions"  # smolLM:3B, general-reasoning Modelfile
DEFAULT_N_RESULTS = 5
DEFAULT_TEMPERATURE = 0.3

INSUFFICIENT_CONTEXT_PREFIX = "INSUFFICIENT CONTEXT:"

# NOTE: the eng-general Modelfile's system prompt already enforces:
#   - answer only from provided context, never invent facts/figures
#   - say so explicitly (rather than guess) when context is insufficient
#   - no filler / no restating the question
#   - no code generation, no file/network access
#   - follow the user's requested output format exactly
# The per-request prompt below deliberately does NOT repeat those rules.
# It only supplies what the system prompt can't know ahead of time: the
# actual numbered sources for this call, and the exact INSUFFICIENT
# CONTEXT phrasing so this module can detect it programmatically
# (see `insufficient` check in run_instruct_task).


class InstructAgentError(Exception):
    """Raised when the instruct agent cannot complete a task."""


def _build_prompt(instruction: str, context_chunks: list[dict]) -> str:
    """
    Build the numbered [Source N] prompt fed to the model.

    context_chunks: list of dicts with at least a "text" key, as returned
    by knowledge.retriever.query_knowledge_with_metadata(). Metadata
    (source_id, content_type) is included per-source so the model can
    reference *which* source something came from if asked to.
    """
    if not context_chunks:
        sources_block = "(no matching sources were found in the knowledge base)"
    else:
        parts = []
        for i, chunk in enumerate(context_chunks, start=1):
            meta = chunk.get("metadata", {}) or {}
            tag_bits = []
            if meta.get("source_id"):
                tag_bits.append(f"source_id={meta['source_id']}")
            if meta.get("content_type"):
                tag_bits.append(f"type={meta['content_type']}")
            tag = f" ({', '.join(tag_bits)})" if tag_bits else ""
            parts.append(f"[Source {i}{tag}]\n{chunk.get('text', '').strip()}")
        sources_block = "\n\n".join(parts)

    return (
        f"{sources_block}\n\n"
        f"Instruction: {instruction}\n\n"
        "If the sources above do not contain enough information to follow "
        f"this instruction, respond with exactly: "
        f"'{INSUFFICIENT_CONTEXT_PREFIX} [what is missing]'."
    )


async def follow_instruction(
    instruction: str,
    context_chunks: list[dict],
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """
    Single model call: given an instruction and pre-retrieved context
    chunks, produce the output. Does not touch the knowledge base itself —
    callers are responsible for retrieval (see run_instruct_task below).
    """
    prompt = _build_prompt(instruction, context_chunks)

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "keep_alive": 0,
        "options": {
            "temperature": temperature,
            "num_ctx": 8192,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except aiohttp.ClientError as e:
        raise InstructAgentError(f"Ollama call to {MODEL_NAME} failed: {e}") from e
    except json.JSONDecodeError as e:
        raise InstructAgentError(f"Ollama returned non-JSON response: {e}") from e

    response_text = data.get("response", "").strip()
    if not response_text:
        raise InstructAgentError(f"Empty response from {MODEL_NAME}")

    return response_text


async def run_instruct_task(
    instruction: str,
    query: Optional[str] = None,
    source_id: Optional[str] = None,
    content_types: Optional[list[str]] = None,
    n_results: int = DEFAULT_N_RESULTS,
) -> dict:
    search_query = query or instruction

    try:
        context_chunks = query_knowledge_with_metadata(
            query=search_query,
            n_results=n_results,
            source_id=source_id,
            content_types=content_types,
        )
    except Exception as e:
        raise InstructAgentError(f"Knowledge base retrieval failed: {e}") from e

    answer = await follow_instruction(instruction, context_chunks)

    insufficient = answer.startswith(INSUFFICIENT_CONTEXT_PREFIX)
    if insufficient:
        logger.info(
            "instruct_agent: insufficient context for instruction=%r "
            "(query=%r, source_id=%r, content_types=%r)",
            instruction, search_query, source_id, content_types,
        )

    sources_used = [
        chunk.get("metadata", {}) for chunk in context_chunks
    ]

    return {
        "answer": answer,
        "insufficient_context": insufficient,
        "sources_used": sources_used,
        "n_sources_retrieved": len(context_chunks),
    }