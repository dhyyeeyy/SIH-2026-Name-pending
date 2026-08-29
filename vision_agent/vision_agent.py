# agents/vision_agent.py
import re
import base64
import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "eng-vision"

async def analyze_image(image_path: str, question: str) -> dict:
    """
    Calls the vision SLM (qwen3.5), enforces hot-swap policy, extracts
    OBSERVED / UNCLEAR structured output.
    """
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "prompt": question,
            "images": [image_b64],
            "stream": False,
            "keep_alive": 0,       # unload immediately — enforced here too, belt & suspenders
            "options": {"num_ctx": 8192, "temperature": 0.1}
        })
        resp.raise_for_status()
        raw = resp.json()["response"]

    observed, unclear = _extract_structured_output(raw)
    if not observed and not unclear:
        raise ValueError(f"Vision model returned no OBSERVED/UNCLEAR block:\n{raw[:300]}")
    return {"observed": observed, "unclear": unclear, "raw": raw}

def _extract_structured_output(text: str) -> tuple[list[str], list[str]]:
    def _section(label: str) -> list[str]:
        pattern = rf"{label}\s*:(.*?)(?=(?:OBSERVED|UNCLEAR)\s*:|\Z)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        return [
            re.sub(r"^[-*•]\s*", "", line).strip()
            for line in match.group(1).strip().splitlines()
            if line.strip()
        ]
    return _section("OBSERVED"), _section("UNCLEAR")