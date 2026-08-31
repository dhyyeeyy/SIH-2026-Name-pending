"""Router that classifies prompts as CODE or INSTRUCT via the local Ollama router model."""

import re

import ollama

ROUTER_MODEL = "eng-router"


def _looks_like_code_request(prompt: str) -> bool:
    """Return True only for prompts with clear code-generation intent."""
    text = (prompt or "").lower()
    if not text:
        return False

    obvious_code_markers = [
        "python",
        "javascript",
        "typescript",
        "code",
        "script",
        "function",
        "class",
        "debug",
        "refactor",
        "fix this bug",
        "write a program",
        "generate code",
        "implement",
        "api",
        "sql",
        "bash",
        "shell",
        "html",
        "css",
        "json",
        "yaml",
        "regex",
        "dockerfile",
        "command line",
        "import ",
        "def ",
        "class ",
        "print(",
        "return ",
        "for ",
        "while ",
        "if ",
        "else ",
    ]

    if any(marker in text for marker in obvious_code_markers):
        return True

    pattern = re.compile(
        r"\b(?:write|create|generate|build|debug|fix|refactor|optimize|explain)\b.*\b(?:python|script|code|function|program|class|module|api|sql|html|css|json|yaml|regex)\b"
    )
    return bool(pattern.search(text))


def _route_with_ollama(prompt: str) -> str:
    """Classify one prompt at a time using the dedicated router model.

    The model is kept alive with keep_alive so it does not need to reload for
    each user prompt. We never pass prior history; each prompt is a fresh
    single-turn request so previous context does not contaminate the next run.
    """
    try:
        response = ollama.generate(
            model=ROUTER_MODEL,
            prompt=(
                "Classify this request as exactly one word: CODE or INSTRUCT.\n\n"
                f"Request: {prompt}\n\n"
                "Rules:\n"
                "- CODE = asks for code generation, debugging, code explanation, refactoring, or work involving code files or functions.\n"
                "- INSTRUCT = asks for general advice, planning, or explanations not specifically about code.\n"
                "Return only CODE or INSTRUCT."
            ),
            keep_alive="1h",
            options={"temperature": 0.0, "num_ctx": 2048},
            stream=False,
        )
    except Exception:
        return "INSTRUCT"

    text = (response.get("response") or "").strip().upper()
    cleaned = re.sub(r"[^A-Z]", "", text)

    if cleaned in {"CODE", "INSTRUCT"}:
        return cleaned
    if "INSTRUCT" in cleaned:
        return "INSTRUCT"
    if "CODE" in cleaned:
        return "CODE"
    return "INSTRUCT"


def route(query: str, config: dict | None = None) -> dict:
    """Return a binary route: code or general."""
    prompt = (query or "").strip()
    if not prompt:
        return {"role": "general", "confidence": 0.0}

    # Be conservative: ordinary natural-language questions should not be
    # routed to the code path just because an LLM classifier is over-eager.
    if not _looks_like_code_request(prompt):
        return {"role": "general", "confidence": 0.92}

    label = _route_with_ollama(prompt)
    if label == "CODE" and not _looks_like_code_request(prompt):
        label = "INSTRUCT"

    role = "code" if label == "CODE" else "general"
    return {"role": role, "confidence": 0.95 if label == "CODE" else 0.9}