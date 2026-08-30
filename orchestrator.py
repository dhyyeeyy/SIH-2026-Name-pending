import asyncio
import dataclasses
import logging
import tempfile
from typing import Optional

from router import route
from instruct_agent.instruct import run_instruct
from vision_agent.vision import run_vision_task

try:
    from coder_agent.coder import run_coder_task
except ImportError:  # coder_agent/coder.py entry point not importable in
    # this environment -- stub kept so the "code" branch fails loudly and
    # specifically instead of the orchestrator import crashing outright.
    async def run_coder_task(task_prompt: str, context: dict, timeout: int = 20):
        raise NotImplementedError(
            "coder_agent.coder.run_coder_task() could not be imported -- "
            "check that coder_agent/ is on the path and __init__.py exists."
        )

logger = logging.getLogger(__name__)


def _format_coder_answer(result: "dataclasses.dataclass") -> str:
    if result.success:
        parts = [result.stdout.strip()] if result.stdout.strip() else ["Code ran successfully with no output."]
        if result.output_files:
            parts.append("Files produced: " + ", ".join(result.output_files))
        return "\n\n".join(parts)
    return f"Code generation/execution failed: {result.stderr}"


def handle_request(
    prompt: str,
    context: Optional[str] = None,
    attachment_path: Optional[str] = None,
    source_id: Optional[str] = None,
    content_types: Optional[list[str]] = None,
    n_results: int = 5,
    cross_reference: bool = False,
) -> dict:
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
        # run_coder_task needs a dict context with 'output_dir', and is
        # async -- neither matches what handle_request receives/is, so
        # both get bridged here rather than in coder_agent/coder.py.
        output_dir = tempfile.mkdtemp(prefix="coder_output_")
        coder_context: dict = {"output_dir": output_dir}
        if context:
            # orchestrator.context is free-text framing (see handle_request
            # docstring); coder.py doesn't define a slot for that, so it
            # rides along under its own key rather than overloading
            # 'output_dir' or being silently dropped.
            coder_context["notes"] = context

        coder_result = asyncio.run(run_coder_task(task_prompt=prompt, context=coder_context))

        result = dataclasses.asdict(coder_result)
        result["answer"] = _format_coder_answer(coder_result)
        result["insufficient_context"] = None  # not a meaningful concept for the code path
        result["error"] = not coder_result.success
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