import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orchestrator import handle_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Engineering Assistant Backend",
    description=(
        "Self-hosted, air-gapped multi-agent backend (vision / general / "
        "code) for SIH 2026. Zero external network calls -- all inference "
        "runs through a local Ollama instance."
    ),
    version="0.1.0",
)

# Demo-only: the static HTML page below calls this API from the browser
# via fetch(), which needs CORS enabled. Fine for an air-gapped local demo
# on one machine -- tighten this (specific origins, not "*") before this
# is ever exposed beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def demo_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


class QueryResponse(BaseModel):
    answer: Optional[str] = None
    handled_by: str
    insufficient_context: Optional[bool] = None
    error: bool = False
    raw: dict


class AgentRunResponse(BaseModel):
    final_answer: str
    trace: list[dict]
    files_to_generate: Optional[list[dict]] = None
    handled_by: Optional[str] = None
    error: bool = False
    raw: Optional[dict] = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/health/deep")
async def health_deep() -> dict:
    try:
        import ollama
        ollama.list()
        ollama_ok = True
        ollama_error = None
    except Exception as e:
        ollama_ok = False
        ollama_error = str(e)

    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama_reachable": ollama_ok,
        "ollama_error": ollama_error,
    }


def _normalize_agent_result(raw: dict) -> dict:
    final_answer = (
        raw.get("final_answer")
        or raw.get("answer")
        or "I couldn't generate a response from the local models."
    )
    trace = raw.get("trace") or [
        {
            "step": "model_response",
            "detail": raw.get("handled_by") or "local_model",
        }
    ]
    return {
        "final_answer": final_answer,
        "trace": trace,
        "files_to_generate": raw.get("files_to_generate") or None,
        "handled_by": raw.get("handled_by"),
        "error": raw.get("error", False),
        "raw": raw,
    }


@app.post("/query", response_model=QueryResponse)
async def query(
    prompt: str = Form(...),
    attachment: Optional[list[UploadFile]] = File(default=None),
    context: Optional[str] = Form(None),
    source_id: Optional[str] = Form(None),
    cross_reference: bool = Form(False),
    use_rag: Optional[bool] = Form(False),
) -> JSONResponse:
    tmp_path: Optional[str] = None
    try:
        rag_enabled = use_rag if isinstance(use_rag, bool) else str(use_rag).lower() not in {"0", "false", "no"}
        files = attachment or []
        if files:
            first = files[0]
            suffix = Path(first.filename or "").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(first.file, tmp)
                tmp_path = tmp.name

        logger.info("/query: use_rag=%s -> rag_enabled=%s", use_rag, rag_enabled)
        result = await asyncio.to_thread(
            handle_request,
            prompt=prompt,
            context=context,
            attachment_path=tmp_path,
            source_id=source_id,
            cross_reference=cross_reference,
            use_rag=rag_enabled,
        )

        agent_result = _normalize_agent_result(result)
        answer = agent_result["final_answer"]

        return JSONResponse(
            content={
                "answer": answer,
                "handled_by": agent_result.get("handled_by") or result.get("handled_by", "unknown"),
                "insufficient_context": result.get("insufficient_context"),
                "error": bool(agent_result["error"] or result.get("error", False)),
                "raw": result,
            }
        )

    except Exception as e:
        # Catch-all so a bug in one agent doesn't take down the whole
        # request with an unhandled 500 stack trace in front of a demo
        # audience -- logged in full, returned to the caller as a clean
        # error shape instead.
        logger.exception("orchestrator.handle_request failed")
        return JSONResponse(
            status_code=500,
            content={
                "answer": None,
                "handled_by": "unknown",
                "insufficient_context": None,
                "error": True,
                "raw": {"exception": str(e)},
            },
        )

    finally:
        # Uploaded file is only needed for the duration of this request --
        # vision.py's run_vision_task reads it synchronously inside
        # handle_request above, so it's safe to delete once that returns.
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@app.post("/api/agent/run")
async def agent_run(
    query: str = Form(...),
    user_id: str = Form("demo-user"),
    attachments: Optional[list[UploadFile]] = File(default=None),
    use_rag: Optional[bool] = Form(False),
) -> JSONResponse:
    tmp_path: Optional[str] = None
    try:
        rag_enabled = use_rag if isinstance(use_rag, bool) else str(use_rag).lower() not in {"0", "false", "no"}
        files = attachments or []
        first_file = files[0] if files else None
        if first_file is not None:
            suffix = Path(first_file.filename or "").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(first_file.file, tmp)
                tmp_path = tmp.name

        logger.info("/api/agent/run: use_rag=%s -> rag_enabled=%s", use_rag, rag_enabled)
        result = await asyncio.to_thread(
            handle_request,
            prompt=query,
            context=None,
            attachment_path=tmp_path,
            source_id=None,
            cross_reference=False,
            use_rag=rag_enabled,
        )

        agent_result = _normalize_agent_result(result)
        return JSONResponse(
            content={
                "final_answer": agent_result["final_answer"],
                "trace": agent_result["trace"],
                "files_to_generate": agent_result["files_to_generate"],
                "handled_by": agent_result.get("handled_by") or result.get("handled_by", "unknown"),
                "error": bool(agent_result["error"] or result.get("error", False)),
                "raw": result,
            }
        )
    except Exception as e:
        logger.exception("agent_run failed")
        return JSONResponse(
            status_code=500,
            content={
                "final_answer": None,
                "trace": [],
                "files_to_generate": None,
                "handled_by": "unknown",
                "error": True,
                "raw": {"exception": str(e)},
            },
        )
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)