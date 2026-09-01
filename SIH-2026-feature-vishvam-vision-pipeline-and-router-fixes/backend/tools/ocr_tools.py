"""
tools/ocr_tools.py

Per-page text extraction for PDFs, used by vision_agent._analyze_pdf to
decide whether a page is text-rich (trust the extracted text, skip the
vision model) or sparse (hand the rendered page image to the vision model
instead). See TEXT_RICH_PAGE_THRESHOLD in vision_agent.py for that cutoff.

Deliberately does not attempt OCR on scanned/image pages itself -- a page
with no extractable text layer naturally comes back with empty/near-empty
text, which already routes it to the vision model in vision_agent.py. That
model reads the rendered page directly, which covers the scanned-document
case without a second, separate OCR engine (PaddleOCR was considered and
dropped -- see requirements.txt -- specifically because this path already
handles it).
"""
from dataclasses import dataclass

import pdfplumber


@dataclass
class PageText:
    page_number: int  # 1-indexed, matches vision_agent.py's page numbering
    text: str


@dataclass
class Extraction:
    pages: list[PageText]


def extract_text(pdf_path: str) -> Extraction:
    pages: list[PageText] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(PageText(page_number=i, text=text))
    return Extraction(pages=pages)
