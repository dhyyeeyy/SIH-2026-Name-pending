import asyncio
import dataclasses
import logging
import tempfile
from pathlib import Path
from typing import Optional

from router import route
from instruct_agent.instruct import run_instruct
from instruct_agent.instruct_agent import InstructAgentError, follow_instruction
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


def _format_vision_answer(result: dict) -> str:
    # run_vision_task returns structured findings (observed/unclear), not
    # a natural-language "answer" -- main.py's _normalize_agent_result
    # falls back to "I couldn't generate a response" when neither
    # "final_answer" nor "answer" is set, which made a successful
    # extraction look like a failure to the end user. Render the
    # structured findings into the answer field instead.
    observed = result.get("observed") or []
    unclear = result.get("unclear") or []
    parts = []
    if observed:
        parts.append("\n".join(f"- {line}" for line in observed))
    real_unclear = [line for line in unclear if line.strip().upper() not in {"NONE", "NONE."}]
    if real_unclear:
        parts.append("Unclear:\n" + "\n".join(f"- {line}" for line in real_unclear))
    return "\n\n".join(parts) if parts else "No content could be extracted from this document."


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
    use_rag: bool = False,
) -> dict:
    # --- Attachment present: vision, unconditionally. -------------------
    # Vision is the only agent that reads a file. It internally decides,
    # per page, whether to actually invoke the vision model or defer to
    # already-extracted text (see vision_agent._analyze_pdf) -- the
    # orchestrator does not need to (and should not try to) replicate
    # that decision here.
    if attachment_path:
        trace: list[dict] = [{
            "step": "router_decision",
            "detail": f"attachment present ({Path(attachment_path).name}) -> forced route to vision",
        }]
        logger.info("orchestrator: attachment present -> vision")
        result = run_vision_task(
            file_path=attachment_path,
            question=prompt,
            context=context,
            cross_reference=cross_reference,
            source_id=source_id,
        )
        trace.append({
            "step": "vision_extraction",
            "detail": f"{len(result.get('observed', []))} observed, "
                      f"{len(result.get('unclear', []))} unclear findings",
        })
        if cross_reference:
            trace.append({
                "step": "cross_reference_lookup",
                "detail": f"{len(result.get('prior_findings', []))} prior findings from knowledge base",
            })
        trace.append({
            "step": "knowledge_base_ingest",
            "detail": f"{result.get('chunks_stored', 0)} chunks stored",
        })

        # Vision's own output is intentionally raw/literal (see
        # Modelfile.vision_thinking -- "only report what is present", no
        # interpretation), which is right for what gets stored in the KB
        # but reads as a disconnected bullet dump when handed back as the
        # answer to an actual question like "what does this PDF say?".
        # Run it through the general model exactly like a normal RAG
        # answer, using the vision findings as the retrieved context --
        # this is the same follow_instruction() the no-attachment general
        # path below uses, just with vision's findings standing in for a
        # KB lookup.
        vision_findings = result.get("raw", "")
        try:
            answer = asyncio.run(follow_instruction(
                instruction=prompt,
                context_chunks=[{
                    "text": vision_findings,
                    "metadata": {
                        "source_id": source_id or Path(attachment_path).stem,
                        "content_type": "vision_extraction",
                    },
                }],
                use_rag=True,
            ))
            trace.append({"step": "generation", "detail": "answer generated from vision findings"})
        except InstructAgentError as e:
            logger.warning("orchestrator: vision answer generation failed, falling back to raw findings: %s", e)
            answer = _format_vision_answer(result)
            trace.append({"step": "generation", "detail": f"summarization failed ({e}) -- returned raw findings"})

        result["answer"] = answer
        result["handled_by"] = "vision"
        result["trace"] = trace
        return result

    # --- No attachment: ask the router to pick code vs. general. --------
    logger.info("orchestrator: use_rag=%s", use_rag)

    routing = route(prompt)
    role = routing["role"]
    logger.info(
        "orchestrator: no attachment -> router picked role=%s (confidence=%.3f)",
        role, routing["confidence"],
    )
    trace = [{
        "step": "router_decision",
        "detail": f"role={role} (confidence={routing['confidence']:.3f})",
    }]

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
        trace.append({
            "step": "code_execution",
            "detail": (
                f"sandbox run succeeded, {len(coder_result.output_files)} file(s) produced"
                if coder_result.success
                else f"sandbox run failed: {coder_result.stderr.strip()[:200]}"
            ),
        })
        result["trace"] = trace
        return result

    # role == "general" (router is strictly binary now -- code or general,
    # nothing else it can return)
    if not use_rag:
        trace.append({"step": "rag_skipped", "detail": "disabled by user"})
    instruction = prompt if not context else f"{prompt}\n\nAdditional context: {context}"
    result = run_instruct(
        instruction=instruction,
        query=prompt,
        source_id=source_id,
        content_types=content_types,
        n_results=n_results,
        use_rag=use_rag,
    )
    if use_rag:
        trace.append({
            "step": "rag_retrieval",
            "detail": f"{result.get('n_sources_retrieved', 0)} relevant chunks found",
        })
    trace.append({
        "step": "generation",
        "detail": (
            "insufficient context -- model declined to answer"
            if result.get("insufficient_context")
            else "answer generated"
        ),
    })
    result["handled_by"] = "general"
    result["trace"] = trace
    return result