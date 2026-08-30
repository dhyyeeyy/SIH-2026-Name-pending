"""
Unit tests for agents/vision_agent.py — covers file-type detection, the
text-rich-page skip path, sparse-page vision routing, and structured output
parsing. All httpx/model calls are mocked so these run without a GPU or
Ollama daemon.

Run with: pytest tests/test_vision_agent.py -v
"""
import asyncio
import pytest
import sys
from unittest.mock import AsyncMock, patch, MagicMock
sys.path.append('C:/Users/Dharm/Desktop/Sovereign_AI')
from vision_agent_file.vision_agent import (
    analyze_image,
    analyze_document,
    _detect_file_type,
    _extract_structured_output,
    TEXT_RICH_PAGE_THRESHOLD,
)


# ------------------------------------------------------ file-type detection

def test_detect_file_type_images():
    assert _detect_file_type("scan.png") == "image"
    assert _detect_file_type("photo.JPG") == "image"      # case-insensitive
    assert _detect_file_type("drawing.tiff") == "image"
    assert _detect_file_type("pic.webp") == "image"


def test_detect_file_type_pdf():
    assert _detect_file_type("report.pdf") == "pdf"
    assert _detect_file_type("REPORT.PDF") == "pdf"        # case-insensitive


def test_detect_file_type_rejects_unsupported():
    with pytest.raises(ValueError, match="Unsupported file type"):
        _detect_file_type("document.docx")
    with pytest.raises(ValueError, match="Unsupported file type"):
        _detect_file_type("no_extension")


# --------------------------------------------------- structured output parsing

def test_extract_structured_output_normal_case():
    text = """OBSERVED:
- Tag PT-101 visible, reading approx 4.2 bar
- Valve V-12 shown closed

UNCLEAR:
- Tag on lower-left instrument [UNCLEAR: best guess PT-102]
"""
    observed, unclear = _extract_structured_output(text)
    assert observed == [
        "Tag PT-101 visible, reading approx 4.2 bar",
        "Valve V-12 shown closed",
    ]
    assert unclear == ["Tag on lower-left instrument [UNCLEAR: best guess PT-102]"]


def test_extract_structured_output_missing_sections():
    observed, unclear = _extract_structured_output("The model rambled without the format.")
    assert observed == []
    assert unclear == []


def test_extract_structured_output_inline_unclear_tag_not_mistaken_for_header():
    # Regression test: an inline "[UNCLEAR: ...]" tag inside an OBSERVED
    # line must not be treated as the start of the UNCLEAR section.
    text = "OBSERVED:\n- Reading shows 4.2 [UNCLEAR: possibly 4.3] bar\n\nUNCLEAR:\n- none\n"
    observed, unclear = _extract_structured_output(text)
    assert observed == ["Reading shows 4.2 [UNCLEAR: possibly 4.3] bar"]
    assert unclear == ["none"]


# ------------------------------------------------------------- analyze_image

@pytest.mark.asyncio
async def test_analyze_image_success(tmp_path):
    fake_image = tmp_path / "test.jpg"
    fake_image.write_bytes(b"fake image bytes")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": "OBSERVED:\n- Tag PT-101 visible\n\nUNCLEAR:\n- none\n"
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        result = await analyze_image(str(fake_image), "what do you see?", context={})

    assert result["observed"] == ["Tag PT-101 visible"]
    assert result["unclear"] == ["none"]


@pytest.mark.asyncio
async def test_analyze_image_raises_on_unparseable_response(tmp_path):
    fake_image = tmp_path / "test.jpg"
    fake_image.write_bytes(b"fake image bytes")

    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "I cannot help with that."}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        with pytest.raises(ValueError, match="no OBSERVED/UNCLEAR block"):
            await analyze_image(str(fake_image), "what do you see?", context={})


@pytest.mark.asyncio
async def test_analyze_image_missing_file():
    with pytest.raises(FileNotFoundError):
        await analyze_image("/nonexistent/path.jpg", "question", context={})


# ---------------------------------------------------- analyze_document (image)

@pytest.mark.asyncio
async def test_analyze_document_routes_image_to_analyze_image(tmp_path):
    fake_image = tmp_path / "scan.png"
    fake_image.write_bytes(b"fake bytes")

    fake_result = {"observed": ["found it"], "unclear": [], "raw": "raw text"}
    with patch("agents.vision_agent.analyze_image", new=AsyncMock(return_value=fake_result)) as mock_ai:
        result = await analyze_document(str(fake_image), "question", context={})

    mock_ai.assert_awaited_once()
    assert result == fake_result


# ---------------------------------------------------- analyze_document (pdf)

def _make_pdf(path, num_repeats=1):
    """Small helper: builds a PDF with real extractable text via reportlab."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 9)
    y = 750
    text = ("Sample inspection paragraph with enough characters to exceed "
            "the text-rich threshold for testing purposes only. ") * num_repeats
    for i in range(0, len(text), 90):
        c.drawString(50, y, text[i:i + 90])
        y -= 12
    c.save()


def _make_sparse_pdf(path):
    """PDF with minimal text — simulates a diagram/photo page."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, "FIG 3")
    c.save()


@pytest.mark.asyncio
async def test_analyze_document_text_rich_pdf_skips_vision_model(tmp_path):
    pdf_path = tmp_path / "text_rich.pdf"
    _make_pdf(pdf_path, num_repeats=5)  # comfortably over TEXT_RICH_PAGE_THRESHOLD

    vision_calls = []

    async def fake_analyze_image(image_path, question, context):
        vision_calls.append(question)
        return {"observed": ["SHOULD NOT BE CALLED"], "unclear": [], "raw": "x"}

    with patch("agents.vision_agent.analyze_image", new=fake_analyze_image):
        result = await analyze_document(str(pdf_path), "summarize", context={})

    assert vision_calls == [], "vision model should not be called for a text-rich page"
    assert any("(from document text)" in line for line in result["observed"])
    assert result["observed"][0].startswith("[p1]")


@pytest.mark.asyncio
async def test_analyze_document_sparse_pdf_routes_to_vision(tmp_path):
    pdf_path = tmp_path / "sparse.pdf"
    _make_sparse_pdf(pdf_path)

    vision_calls = []

    async def fake_analyze_image(image_path, question, context):
        vision_calls.append(question)
        return {"observed": ["Diagram FIG 3 visible"], "unclear": [], "raw": "vision raw"}

    with patch("agents.vision_agent.analyze_image", new=fake_analyze_image):
        result = await analyze_document(str(pdf_path), "what is shown", context={})

    assert len(vision_calls) == 1, "sparse page should trigger exactly one vision call"
    assert result["observed"] == ["[p1] Diagram FIG 3 visible"]


@pytest.mark.asyncio
async def test_analyze_document_pdf_missing_file():
    with pytest.raises(Exception):
        await analyze_document("/nonexistent/file.pdf", "question", context={})


@pytest.mark.asyncio
async def test_analyze_document_rejects_unsupported_extension(tmp_path):
    bad_file = tmp_path / "notes.docx"
    bad_file.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported file type"):
        await analyze_document(str(bad_file), "question", context={})