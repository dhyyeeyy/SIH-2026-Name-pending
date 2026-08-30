"""
coder.py

Single entry point for the coding pipeline: Master Agent (B) calls
`run_coder_task()`, which generates code via eng-coder and executes it
in the sandbox. One attempt, no retries -- caller decides what happens
on failure (surface to user, log, re-route, etc).
"""

from dataclasses import dataclass

from coder_agent import generate_code
from sandbox_runner import run_in_sandbox, SandboxResult, SandboxViolation


@dataclass
class CoderTaskResult:
    success: bool
    stdout: str
    stderr: str
    output_files: list[str]
    generated_code: str | None   # kept for logging/debugging even on failure


async def run_coder_task(task_prompt: str, context: dict, timeout: int = 20) -> CoderTaskResult:
    """
    Runs the full coder pipeline for one task:
      1. Ask eng-coder to generate code for `task_prompt`
      2. Run that code once in the sandbox, confined to context['output_dir']
      3. Return the outcome -- success/failure, logs, and produced files

    No retries. If generation fails to produce a valid code block, or the
    sandbox rejects/fails the code, this returns success=False with the
    reason in stderr -- it's up to the Master Agent what to do next.
    """
    output_dir = context.get("output_dir", "./output")

    # Step 1: generation
    try:
        code = await generate_code(task_prompt, context)
    except ValueError as e:
        return CoderTaskResult(
            success=False, stdout="", stderr=str(e),
            output_files=[], generated_code=None
        )

    # Step 2: execution
    try:
        result: SandboxResult = run_in_sandbox(code, output_dir, timeout=timeout)
    except SandboxViolation as e:
        return CoderTaskResult(
            success=False, stdout="", stderr=f"Rejected before execution: {e}",
            output_files=[], generated_code=code
        )

    # Step 3: return outcome
    return CoderTaskResult(
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        output_files=result.output_files,
        generated_code=code,
    )