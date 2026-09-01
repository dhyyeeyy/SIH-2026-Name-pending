# agents/vision_agent.py
import os
import re
import base64
import tempfile
import httpx
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "eng-vision"

# 180s was measured too short on the target hardware (Section 3 of
# CLAUDE.md: 4GB dedicated VRAM / CPU-only) -- a cold load of eng-vision
# alone measured ~4.5 minutes end to end (keep_alive is now "5m", not 0,
# but the FIRST call after any idle period is still a cold load). 600s
# gives headroom without hanging forever on a genuinely dead Ollama
# instance.
VISION_TIMEOUT_SECONDS = 600

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
PDF_EXTENSIONS = {".pdf"}

TEXT_RICH_PAGE_THRESHOLD = 400


def _detect_file_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    raise ValueError(
        f"Unsupported file type '{ext}' for vision_agent. "
        f"Supported: {sorted(IMAGE_EXTENSIONS | PDF_EXTENSIONS)}"
    )


async def analyze_image(image_path: str, question: str, context: dict) -> dict:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    async with httpx.AsyncClient(timeout=VISION_TIMEOUT_SECONDS) as client:
        resp = await client.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "prompt": question,
            "images": [image_b64],
            "stream": False,
            "think": False,        # eng-vision (qwen3.5) is thinking-capable;
            # observed live spending its entire num_predict budget on the
            # <think> block and returning an EMPTY "response" (done_reason
            # "length") -- this task just needs the structured OBSERVED/
            # UNCLEAR answer, not a reasoning trace, so skip it entirely.
            "keep_alive": "5m",    # was 0 (unload immediately) -- on this hardware every
            # call was a full cold load from disk (measured 1-4+ minutes). Only one of
            # general/code/vision fits in the 4GB VRAM budget at a time regardless, so
            # this doesn't cause contention beyond what already exists -- it just avoids
            # reloading THIS model if it's called again (e.g. a second vision question,
            # or the follow-up general-model call in orchestrator.py's vision answer
            # step) within 5 minutes. Also means a pre-demo warm-up query genuinely
            # keeps the model warm instead of unloading the instant it responds.
            "options": {"num_ctx": 8192, "temperature": 0.1}
        })
        resp.raise_for_status()
        raw = resp.json()["response"]

    observed, unclear = _extract_structured_output(raw)
    if not observed and not unclear:
        raise ValueError(f"Vision model returned no OBSERVED/UNCLEAR block:\n{raw[:300]}")
    return {"observed": observed, "unclear": unclear, "raw": raw}


async def analyze_document(file_path: str, question: str, context: dict) -> dict:
    file_type = _detect_file_type(file_path)

    if file_type == "image":
        return await analyze_image(file_path, question, context)

    return await _analyze_pdf(file_path, question, context)


async def _analyze_pdf(pdf_path: str, question: str, context: dict) -> dict:
    from tools.ocr_tools import extract_text as ocr_extract_text
    import fitz  # PyMuPDF -- pure-Python PDF rendering, no poppler binary needed

    extraction = ocr_extract_text(pdf_path)
    text_by_page = {p.page_number: p.text for p in extraction.pages}

    all_observed: list[str] = []
    all_unclear: list[str] = []
    raw_chunks: list[str] = []

    doc = fitz.open(pdf_path)
    try:
        images = [page.get_pixmap(dpi=200) for page in doc]
    finally:
        doc.close()

    for i, img in enumerate(images, start=1):
        page_text = text_by_page.get(i, "")

        if len(page_text) >= TEXT_RICH_PAGE_THRESHOLD:
            # Text-dense page — trust pdfplumber/OCR, skip the vision call.
            all_observed.append(f"[p{i}] (from document text) {page_text}")
            raw_chunks.append(f"--- Page {i} (text-extracted, vision skipped) ---\n{page_text}")
            continue

        augmented_question = question
        if page_text.strip():
            augmented_question = (
                f"Extracted text context for this page (from OCR/document parsing):\n"
                f"{page_text}\n\n{question}"
            )

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)  # release the handle before img.save() -- MuPDF's
            # pixmap writer removes-then-recreates the target file, which
            # fails with a Windows file-lock error if we're still holding
            # it open (as tempfile.NamedTemporaryFile would).
            img.save(tmp_path)
            page_result = await analyze_image(tmp_path, augmented_question, context)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

        all_observed.extend(f"[p{i}] {line}" for line in page_result["observed"])
        all_unclear.extend(f"[p{i}] {line}" for line in page_result["unclear"])
        raw_chunks.append(f"--- Page {i} (vision) ---\n{page_result['raw']}")

    if not all_observed and not all_unclear:
        raise ValueError(f"No content extracted from any page of {pdf_path}")

    return {
        "observed": all_observed,
        "unclear": all_unclear,
        "raw": "\n\n".join(raw_chunks),
    }


def _extract_structured_output(text: str) -> tuple[list[str], list[str]]:
    def _section(label: str) -> list[str]:
        # ^ + re.MULTILINE anchors the header to the start of a line, so an
        # inline "[UNCLEAR: best guess ...]" tag inside an OBSERVED bullet
        # doesn't get mistaken for the UNCLEAR section header itself.
        pattern = rf"^{label}\s*:(.*?)(?=^(?:OBSERVED|UNCLEAR)\s*:|\Z)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if not match:
            return []
        return [
            re.sub(r"^[-*•]\s*", "", line).strip()
            for line in match.group(1).strip().splitlines()
            if line.strip()
        ]
    return _section("OBSERVED"), _section("UNCLEAR")