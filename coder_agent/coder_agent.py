# agents/coder_agent.py
import re
import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "eng-coder"


async def generate_code(task_prompt: str, context: dict) -> str:
    """
    Calls the coder SLM, enforces hot-swap policy, and extracts runnable code.
    This is intentionally strict: the model is instructed to return only a
    Python code block so the sandbox can execute it without extra parsing.
    """
    output_dir = context.get("output_dir", "./output")
    full_prompt = (
        "Return only valid Python code in a single fenced ```python block. "
        "Do not include markdown prose before or after the code. "
        "The code must be runnable non-interactively in a sandbox and must not call input() or wait for console input.\n\n"
        f"Task: {task_prompt}\n\nOUTPUT_DIR = {output_dir!r}"
    )

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": full_prompt,
                "stream": False,
                "keep_alive": 0,
                "options": {"num_ctx": 8192},
            },
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")

    code = _extract_code_block(raw)
    if not code:
        raise ValueError(f"Coder model returned no valid code block:\n{raw[:500]}")
    return code


def _extract_code_block(text: str) -> str | None:
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # Prefer fenced code blocks first; this is the standard format the model
    # is asked to return and is the most robust result from Ollama.
    match = re.search(r"```(?:python)?\s*(.*?)```", cleaned, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        if candidate:
            return candidate

    # Some models echo code without a fence, or produce a mixed response. If the
    # text clearly looks like Python, keep it instead of failing the whole flow.
    python_markers = (
        "def ", "class ", "import ", "from ", "print(", "if __name__ ==",
        "return ", "for ", "while ", "try:", "async def ", "lambda ",
        "with ", "match ", "raise ", "yield "
    )
    lowered = cleaned.lower()
    if any(marker in lowered for marker in python_markers):
        return cleaned

    # Final fallback: a fenced block may be split across prose; extract the last
    # code-looking segment if one exists.
    fallback = re.search(r"```(?:python)?\s*(.*)\s*```?", cleaned, re.DOTALL)
    if fallback:
        candidate = fallback.group(1).strip()
        if candidate and any(marker in candidate.lower() for marker in python_markers):
            return candidate

    return None