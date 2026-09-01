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
import re
from typing import Optional

import aiohttp

from knowledge.retriever import query_knowledge_with_metadata

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
# The local Ollama install contains `eng-instructions:latest`, not
# `eng-general`. Using the actual installed name avoids the 404s from the
# `/api/generate` call.
MODEL_NAME = "eng-instructions"
DEFAULT_N_RESULTS = 5
DEFAULT_TEMPERATURE = 0.3

INSUFFICIENT_CONTEXT_PREFIX = "INSUFFICIENT CONTEXT:"

# Some backends (reasoning-mode models) emit a <think>...</think> block
# ahead of the actual answer. That's fine for humans reading it, but it
# breaks answer.startswith(INSUFFICIENT_CONTEXT_PREFIX) below -- the
# response no longer starts with the phrase, it starts with the think
# block, so insufficient_context would silently come back False even when
# the model correctly flagged insufficient context after its reasoning.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _strip_think_block(text: str) -> str:
    """Remove a leading <think>...</think> reasoning block, if present."""
    return _THINK_BLOCK_RE.sub("", text, count=1).strip()

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


def _build_prompt(instruction: str, context_chunks: list[dict], use_rag: bool = True) -> str:
    """
    Build the numbered [Source N] prompt fed to the model.

    When document search is disabled, we explicitly tell the model to answer
    using general knowledge only and do not force the insufficient-context
    phrase, since that prefix is only meaningful when RAG is active.
    """
    if not context_chunks:
        if use_rag:
            sources_block = "(no matching sources were found in the knowledge base)"
            insufficient_instruction = (
                "If the sources above do not contain enough information to follow this instruction, "
                f"respond with exactly: '{INSUFFICIENT_CONTEXT_PREFIX} [what is missing]'."
            )
        else:
            sources_block = "(No document retrieval was requested; answer using general knowledge only.)"
            insufficient_instruction = (
                "Answer using general knowledge only. Do not claim 'INSUFFICIENT CONTEXT' because "
                "document search was intentionally turned off."
            )
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
        insufficient_instruction = (
            "If the sources above do not contain enough information to follow this instruction, "
            f"respond with exactly: '{INSUFFICIENT_CONTEXT_PREFIX} [what is missing]'."
        )

    return (
        f"{sources_block}\n\n"
        f"Instruction: {instruction}\n\n"
        f"{insufficient_instruction}"
    )


async def follow_instruction(
    instruction: str,
    context_chunks: list[dict],
    temperature: float = DEFAULT_TEMPERATURE,
    use_rag: bool = True,
) -> str:
    """
    Single model call: given an instruction and pre-retrieved context
    chunks, produce the output. Does not touch the knowledge base itself —
    callers are responsible for retrieval (see run_instruct_task below).
    """
    prompt = _build_prompt(instruction, context_chunks, use_rag=use_rag)

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "5m",    # was 0 -- see vision_agent.py for why (cold-load latency
        # measured in minutes on this hardware; kept short since general/code/vision
        # still compete for the same 4GB VRAM budget and can't all stay resident).
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

    return _strip_think_block(response_text)


async def run_instruct_task(
    instruction: str,
    query: Optional[str] = None,
    source_id: Optional[str] = None,
    content_types: Optional[list[str]] = None,
    n_results: int = DEFAULT_N_RESULTS,
    use_rag: bool = False,
) -> dict:
    """
    Entry point: optionally retrieve relevant chunks from the KB, then follow
    the instruction over them. Mirrors general.py's run_general_task, kept as
    the single function other modules should call rather than composing
    retrieval + follow_instruction themselves.

    Args:
        instruction: what the user wants done ("summarize this and that",
            "extract only the dates", "make it shorter", ...).
        query: text used for the vector search. Defaults to `instruction`
            itself if not given.
        source_id: optional, scopes retrieval to one ingested
            document/image.
        content_types: optional filter, e.g. ["vision_observed"].
        n_results: how many chunks to retrieve.
        use_rag: when False, skip all knowledge-base retrieval and answer
            from the model without retrieved context.

    Returns:
        {
            "answer": str,
            "insufficient_context": bool,
            "sources_used": [ {source_id, content_type, ...}, ... ],
            "n_sources_retrieved": int,
        }
    """
    search_query = query or instruction

    if use_rag:
        try:
            context_chunks = query_knowledge_with_metadata(
                question=search_query,
                n=n_results,
                source_id=source_id,
                content_types=content_types,
            )
        except Exception as e:
            raise InstructAgentError(f"Knowledge base retrieval failed: {e}") from e
    else:
        context_chunks = []

    answer = await follow_instruction(instruction, context_chunks, use_rag=use_rag)

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