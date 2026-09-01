# Backend — Engineering Assistant Backend

Dharm's FastAPI service (`backend/main.py`), orchestrating the vision/general/code
sub-agents. Copied into this repo from `github.com/dhyyeeyy/SIH-2026-Name-pending`
(2026-08-31) so the whole system lives in one place — his repo also contains
its own `/frontend`, which isn't used here; this project's `/frontend` is
separate and owned by Vishvam.

This README replaces the original (a single-line title, no run instructions) —
filled in from what was actually needed to get this running for real.

---

## Setup

Uses the same Python venv as `/router` and `/agent` (`../venv`) — no separate
environment needed. Packages that weren't already installed there:

```bash
../venv/Scripts/python.exe -m pip install fastapi pdfplumber pytest-asyncio reportlab
```

(`pytest-asyncio` and `reportlab` are only needed to run `tests/` — not the
running service itself.)

`semantic-router` is listed in `requirements.txt` but not actually imported
anywhere (`router.py` is hand-rolled specifically to avoid it) — safe to skip.

### Custom Ollama models

`orchestrator.py` and the sub-agents call Ollama by custom model names, not
the base tags — these must be built from `MODELFILES/` before anything works:

```bash
cd MODELFILES
ollama create eng-coder -f Modelfile.coder
ollama create eng-embeddings -f Modelfile.embeddings
ollama create eng-vision -f Modelfile.vision_thinking
ollama create eng-instructions -f Modelfile.instruction_follower
```

**Note:** `eng-instructions` is built `FROM alibayram/smollm3:latest` — a
different model than `qwen3:1.7b`, which is what the rest of the team's
CLAUDE.md documents as the locked general-reasoning model. Worth resolving
which one is actually final.

### Running

```bash
cd backend
../venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

No port was documented anywhere in the original delivery — 8000 is uvicorn's
default and happens to match the frontend's `VITE_API_BASE_URL` default, but
confirm this is intentional rather than coincidental.

`GET /health` and `GET /health/deep` (the latter checks real Ollama
connectivity) are good first checks. `POST /api/agent/run` is the endpoint
the frontend actually calls (`query`, `user_id`, `attachments`, `use_rag` as
multipart form fields) — see `frontend/src/api/realAgentClient.ts`.

---

## Fixes applied here (2026-08-31) to get this actually running

1. **`static/` directory didn't exist.** `main.py` does `app.mount("/static",
   StaticFiles(directory=STATIC_DIR), ...)` at import time, which raises
   immediately if the directory is missing — the app couldn't even start.
   Added a minimal `static/index.html` placeholder.
2. **`use_rag=True` crashed every request.** `instruct_agent.py` called
   `query_knowledge_with_metadata(query=..., n_results=...)`, but the actual
   function signature in `knowledge/retriever.py` is
   `(question, n, content_types, source_id)` — a parameter name mismatch.
   Fixed the call site to use `question=`/`n=`. This is significant because
   the frontend defaults RAG to *on*, so every first message in a session
   would have failed with this bug present.
3. **`tests/` couldn't even collect.** `test_vision_agent.py` imported from
   `vision_agent_file.vision_agent` (a module that doesn't exist in this
   layout — the real package is `vision_agent/`) and had a hardcoded
   `sys.path.append('C:/Users/Dharm/Desktop/Sovereign_AI')` left in from a
   different machine. Fixed the import, removed the hardcoded path. This
   single error was enough to abort the *entire* test run, not just that
   file — nothing in `tests/` could run at all before this fix.
4. **Stale `unittest.mock.patch()` targets throughout `tests/`.** Several
   tests patched `agents.vision_agent.analyze_image` and
   `vision.analyze_document` / `from vision import run_vision_task` — none
   of which exist; the real paths are `vision_agent.vision_agent.*` and
   `vision_agent.vision.*`. Fixed across `test_vision_agent.py` and
   `test_vision_task.py`.
5. **Two missing test-only dependencies**: `pytest-asyncio` (without it,
   every `@pytest.mark.asyncio` test silently failed instead of actually
   running) and `reportlab` (used only by test fixtures that build sample
   PDFs). Neither is needed by the running service, only the test suite.

After these fixes: **20/22 tests pass.** The remaining 2 failures
(`test_analyze_document_text_rich_pdf_skips_vision_model`,
`test_analyze_document_sparse_pdf_routes_to_vision`) are a genuinely missing
module, not a path issue — see below.

## Known issues NOT fixed here (flag to Dharm)

1. **`trace` isn't real.** Nothing in `orchestrator.py` or the sub-agents
   populates a genuine step-by-step trace; `main.py`'s
   `_normalize_agent_result()` synthesizes a single fallback entry
   (`{"step": "model_response", "detail": handled_by}`) when none exists —
   which is always, since nothing ever sets a real one. The frontend's trace
   view will only ever show one generic line per response against this
   backend.
2. **Vision parsing is fragile.** `vision_agent.py`'s structured-output
   parser expects an exact `OBSERVED:` / `UNCLEAR:` prefix; when the model
   wraps it in markdown bold (`**OBSERVED:**`), which it does sometimes, the
   parse fails and the whole request errors out — even though the model read
   the image correctly. Reproduced directly against a real test image.
2b. **PDF vision support is unbuilt, not just buggy.** `_analyze_pdf()` in
   `vision_agent.py` unconditionally does `from tools.ocr_tools import
   extract_text` — `tools/` doesn't exist anywhere in the delivered repo.
   `requirements.txt` already has a comment acknowledging this (PaddleOCR
   wiring was planned but never actually done). Any PDF attachment to the
   vision path will always fail until this module is written. This is the
   cause of the only 2 remaining test failures after the fixes above.
3. **Router recall on code queries is inconsistent.** "write a python
   function that checks if a number is prime" routed to `general`, not
   `code` — the general model happened to produce a fenced code block
   anyway (the frontend picked it up fine), but that's incidental, not
   guaranteed for every code-shaped request.
4. **Prompt-template leakage observed once**: a response began with a
   stray `'INSUFFICIENT CONTEXT: ...'` string that reads like an internal
   instruction/template artifact leaking into the final answer, in a case
   where context clearly wasn't actually insufficient.
5. **`use_rag` defaults to `False`** here (confirmed by
   `tests/test_rag_toggle.py`), vs. the frontend/CLAUDE.md contract's
   default of `True`. The frontend always sends the field explicitly, so
   this doesn't bite in practice, but worth aligning the documented default.
