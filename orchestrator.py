import logging
from typing import Optional

from router import route
from instruct import run_instruct
from vision import run_vision_task

try:
    from coder import run_coder_task
except ImportError:  # coder.py's real signature wasn't available while
    # building this module -- stub kept so the "code" branch fails loudly
    # and specifically instead of the orchestrator import crashing outright.
    def run_coder_task(prompt: str, context: Optional[str] = None) -> dict:
        raise NotImplementedError(
            "coder.run_coder_task() not wired up yet -- replace this stub "
            "with the real import once coder.py's entry point is confirmed."
        )

logger = logging.getLogger(__name__)


def handle_request(
    prompt: str,
    context: Optional[str] = None,
    attachment_path: Optional[str] = None,
    source_id: Optional[str] = None,
    content_types: Optional[list[str]] = None,
    n_results: int = 5,
    cross_reference: bool = False,
) -> dict:
    """
    Single entry point for an incoming user request.

    Args:
        prompt: the user's question/instruction.
        context: optional free-text context supplied alongside the prompt
            (e.g. extra framing from a UI form field). NOT the same thing
            as the KB-retrieved context inside instruct_agent -- this is
            passed straight through to whichever agent handles the
            request, on top of whatever that agent retrieves/extracts
            itself.
        attachment_path: path to an image or PDF, if the user attached
            one. Presence of this alone determines routing to vision --
            see module docstring.
        source_id: optional, scoped retrieval for the general path, or
            passed to vision for KB storage/cross-reference tagging.
        content_types: optional content_type filter for general's KB
            retrieval (e.g. restrict to ["vision_observed"]).
        n_results: chunk count for general's KB retrieval.
        cross_reference: forwarded to vision -- look up prior
            vision_observed findings for the same equipment.

    Returns:
        A dict from whichever agent handled the request, plus a
        "handled_by" key ("vision" | "general" | "code") so the caller
        (UI, logs) can tell which path was taken without re-deriving it.
    """
    # --- Attachment present: vision, unconditionally. -------------------
    # Vision is the only agent that reads a file. It internally decides,
    # per page, whether to actually invoke the vision model or defer to
    # already-extracted text (see vision_agent._analyze_pdf) -- the
    # orchestrator does not need to (and should not try to) replicate
    # that decision here.
    if attachment_path:
        logger.info("orchestrator: attachment present -> vision")
        result = run_vision_task(
            file_path=attachment_path,
            question=prompt,
            context=context,
            cross_reference=cross_reference,
            source_id=source_id,
        )
        result["handled_by"] = "vision"
        return result

    # --- No attachment: ask the router to pick code vs. general. --------
    routing = route(prompt)
    role = routing["role"]
    logger.info(
        "orchestrator: no attachment -> router picked role=%s (confidence=%.3f)",
        role, routing["confidence"],
    )

    if role == "code":
        result = run_coder_task(prompt=prompt, context=context)
        result["handled_by"] = "code"
        return result

    # role == "general" (router is strictly binary now -- code or general,
    # nothing else it can return)
    instruction = prompt if not context else f"{prompt}\n\nAdditional context: {context}"
    result = run_instruct(
        instruction=instruction,
        query=prompt,
        source_id=source_id,
        content_types=content_types,
        n_results=n_results,
    )
    result["handled_by"] = "general"
    return result