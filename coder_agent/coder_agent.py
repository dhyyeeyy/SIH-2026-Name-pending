# agents/coder_agent.py
import re
import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "eng-coder"

async def generate_code(task_prompt: str, context: dict) -> str:
    """
    Calls the coder SLM, enforces hot-swap policy, extracts the code block.
    """
    full_prompt = f"{task_prompt}\n\nOUTPUT_DIR = {context.get('output_dir', './output')!r}"

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "prompt": full_prompt,
            "stream": False,
            "keep_alive": 0,       # unload immediately — enforced here too, belt & suspenders
            "options": {"num_ctx": 8192}
        })
        resp.raise_for_status()
        raw = resp.json()["response"]

    code = _extract_code_block(raw)
    if not code:
        raise ValueError(f"Coder model returned no valid code block:\n{raw[:300]}")
    return code

def _extract_code_block(text: str) -> str | None:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else None