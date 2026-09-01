# knowledge/ingest.py
"""
Ingests extracted document content into a local, persistent ChromaDB
collection so it can be retrieved later by:
  - eng-general (smollm:3b) — grounding answers/approval-note drafts in SOPs,
    manuals, and past correspondence
  - eng-vision (qwen3.5) — optionally pulling prior findings on the same
    equipment/document for cross-reference, though this agent should still
    only report what it currently observes, not what it retrieves

Two input sources feed this:
  1. tools/ocr_tools.extract_text() results — native + OCR'd document text
  2. agents/qwen_agent.analyze_image() results — vision OBSERVED/UNCLEAR
     findings, kept as their own content_type so a retriever/reader can
     tell "this came from a document" apart from "this came from a
     vision-model's read of an image," which matters for trust/audit.

Chunking is simple word-count based with overlap — adequate for SOP/manual
prose. Table content (from pdfplumber) is kept as whole chunks, not split,
since splitting a table mid-row destroys its meaning.
"""

import uuid
from pathlib import Path

import chromadb

from knowledge.embeddings import OllamaLocalEmbeddingFunction

# Anchored to this file's location, NOT the caller's cwd. Without this,
# coder_agent/vision_agent/instruct_agent launched from different working
# directories would each silently create their own separate chroma_store,
# and cross-agent retrieval would return nothing with no error.
CHROMA_STORE_PATH = str(Path(__file__).parent / "chroma_store")
COLLECTION_NAME = "org_knowledge"

CHUNK_WORD_SIZE = 250
CHUNK_WORD_OVERLAP = 40


def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_STORE_PATH)
    return client.get_or_create_collection(
        COLLECTION_NAME,
        embedding_function=OllamaLocalEmbeddingFunction(),
    )


def _chunk_text(text: str, size: int = CHUNK_WORD_SIZE, overlap: int = CHUNK_WORD_OVERLAP) -> list[str]:
    """Word-count chunking with overlap. Returns [] for empty/whitespace text."""
    words = text.split()
    if not words:
        return []
    if len(words) <= size:
        return [text.strip()]

    chunks = []
    start = 0
    while start < len(words):
        end = start + size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def ingest_ocr_result(extraction_result, source_id: str | None = None) -> int:
    """
    Ingest a tools.ocr_tools.ExtractionResult into ChromaDB.
    One chunk group per page: prose is chunked, tables are kept whole.
    Returns the number of chunks written.
    """
    if not extraction_result.success:
        return 0

    source_id = source_id or Path(extraction_result.file_path).stem
    collection = _get_collection()

    ids, docs, metadatas = [], [], []

    for page in extraction_result.pages:
        if page.text:
            for chunk_idx, chunk in enumerate(_chunk_text(page.text)):
                ids.append(f"{source_id}-p{page.page_number}-c{chunk_idx}-{uuid.uuid4().hex[:8]}")
                docs.append(chunk)
                metadatas.append({
                    "source_file": extraction_result.file_path,
                    "source_id": source_id,
                    "page_number": page.page_number,
                    "content_type": f"document_{page.method}",  # document_native | document_ocr
                    "chunk_index": chunk_idx,
                })

        for t_idx, table in enumerate(page.tables):
            table_str = "\n".join(" | ".join(cell or "" for cell in row) for row in table)
            ids.append(f"{source_id}-p{page.page_number}-table{t_idx}-{uuid.uuid4().hex[:8]}")
            docs.append(table_str)
            metadatas.append({
                "source_file": extraction_result.file_path,
                "source_id": source_id,
                "page_number": page.page_number,
                "content_type": "document_table",
                "chunk_index": t_idx,
            })

    if not ids:
        return 0

    collection.add(ids=ids, documents=docs, metadatas=metadatas)
    return len(ids)


def ingest_vision_result(vision_result: dict, source_id: str, image_path: str) -> int:
    """
    Ingest a qwen_agent.analyze_image()-style result dict
    ({"observed": [...], "unclear": [...], "raw": "..."}) into ChromaDB.

    OBSERVED and UNCLEAR findings are stored as separate content_types so a
    downstream reasoning step (or a human reviewer) can weight/filter them
    differently — an UNCLEAR finding should never be treated with the same
    confidence as an OBSERVED one, including at retrieval time.
    """
    collection = _get_collection()
    ids, docs, metadatas = [], [], []

    for i, line in enumerate(vision_result.get("observed", [])):
        ids.append(f"{source_id}-observed-{i}-{uuid.uuid4().hex[:8]}")
        docs.append(line)
        metadatas.append({
            "source_file": image_path,
            "source_id": source_id,
            "content_type": "vision_observed",
            "chunk_index": i,
        })

    for i, line in enumerate(vision_result.get("unclear", [])):
        ids.append(f"{source_id}-unclear-{i}-{uuid.uuid4().hex[:8]}")
        docs.append(line)
        metadatas.append({
            "source_file": image_path,
            "source_id": source_id,
            "content_type": "vision_unclear",
            "chunk_index": i,
        })

    if not ids:
        return 0

    collection.add(ids=ids, documents=docs, metadatas=metadatas)
    return len(ids)


def ingest_file(file_path: str, force_ocr: bool = False) -> int:
    """
    Convenience one-shot: run OCR extraction on a file and ingest the
    result. This is the function a bulk-ingestion script (e.g. "load every
    SOP in this folder") should call per file.
    """
    from tools.ocr_tools import extract_text
    result = extract_text(file_path, force_ocr=force_ocr)
    return ingest_ocr_result(result)


def ingest_directory(directory: str, extensions: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg")) -> dict:
    """
    Bulk-ingest every matching file in a directory (non-recursive).
    Returns a summary dict: {filename: chunk_count}. Failures are recorded
    with a chunk_count of 0 rather than raising, so one bad file doesn't
    abort ingestion of the rest of the manual/SOP folder.
    """
    summary = {}
    dir_path = Path(directory)
    for file_path in sorted(dir_path.iterdir()):
        if file_path.suffix.lower() not in extensions:
            continue
        try:
            count = ingest_file(str(file_path))
        except Exception as e:
            count = 0
            print(f"  FAILED: {file_path.name} — {e}")
        summary[file_path.name] = count
        print(f"  {file_path.name}: {count} chunks")
    return summary