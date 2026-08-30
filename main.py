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


@app.post("/query", response_model=QueryResponse)
async def query(
    prompt: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    context: Optional[str] = Form(None),
    source_id: Optional[str] = Form(None),
    cross_reference: bool = Form(False),
) -> JSONResponse:
    tmp_path: Optional[str] = None
    try:
        if attachment is not None:
            suffix = Path(attachment.filename or "").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(attachment.file, tmp)
                tmp_path = tmp.name

        result = handle_request(
            prompt=prompt,
            context=context,
            attachment_path=tmp_path,
            source_id=source_id,
            cross_reference=cross_reference,
        )

        return JSONResponse(
            content={
                "answer": result.get("answer"),
                "handled_by": result.get("handled_by"),
                "insufficient_context": result.get("insufficient_context"),
                "error": result.get("error", False),
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