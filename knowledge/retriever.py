# knowledge/retriever.py
"""
Query interface over the local ChromaDB knowledge base built by
knowledge/ingest.py. Called by general.py (eng-general / smollm:3b) to
ground answers, and optionally usable by a vision pipeline step that wants
prior findings on the same equipment for cross-reference.

Deliberately thin: returns plain text chunks (+ optional metadata) rather
than anything Ollama/model-specific, so this module has no dependency on
which model ends up consuming the result.
"""

import chromadb

from knowledge.embeddings import OllamaLocalEmbeddingFunction
from knowledge.ingest import CHROMA_STORE_PATH, COLLECTION_NAME


def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_STORE_PATH)
    return client.get_or_create_collection(
        COLLECTION_NAME,
        embedding_function=OllamaLocalEmbeddingFunction(),
    )


def query_knowledge(
    question: str,
    n: int = 5,
    content_types: list[str] | None = None,
    source_id: str | None = None,
) -> list[str]:
    """
    Return the top-n most relevant chunks of text for `question`.

    content_types: restrict to specific content_type values, e.g.
        ["document_native", "document_ocr"] to exclude vision findings,
        or ["vision_observed"] to only pull confirmed vision observations
        and never UNCLEAR guesses.
    source_id: restrict retrieval to a single ingested document/image
        (useful in the chained inspection-report pipeline, so the general
        agent doesn't accidentally pull in an unrelated SOP chunk when
        asked to summarize *this* report).
    """
    collection = _get_collection()

    where = None
    conditions = []
    if content_types:
        conditions.append({"content_type": {"$in": content_types}})
    if source_id:
        conditions.append({"source_id": source_id})
    if len(conditions) == 1:
        where = conditions[0]
    elif len(conditions) > 1:
        where = {"$and": conditions}

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[question],
        n_results=min(n, collection.count()),
        where=where,
    )

    documents = results.get("documents", [[]])
    return documents[0] if documents else []


def query_knowledge_with_metadata(
    question: str,
    n: int = 5,
    content_types: list[str] | None = None,
    source_id: str | None = None,
) -> list[dict]:
    """
    Same as query_knowledge but returns [{"text": ..., "metadata": {...}}, ...]
    — use this when the caller needs to cite source_file/page_number, e.g.
    when drafting an approval note that should reference "per SOP 4.2, p.3".
    """
    collection = _get_collection()

    where = None
    conditions = []
    if content_types:
        conditions.append({"content_type": {"$in": content_types}})
    if source_id:
        conditions.append({"source_id": source_id})
    if len(conditions) == 1:
        where = conditions[0]
    elif len(conditions) > 1:
        where = {"$and": conditions}

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[question],
        n_results=min(n, collection.count()),
        where=where,
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    return [{"text": d, "metadata": m} for d, m in zip(docs, metas)]


def collection_stats() -> dict:
    """Quick sanity-check helper: how much is actually in the KB right now."""
    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return {"total_chunks": 0, "by_content_type": {}}

    all_meta = collection.get(include=["metadatas"])["metadatas"]
    by_type: dict[str, int] = {}
    for m in all_meta:
        ct = m.get("content_type", "unknown")
        by_type[ct] = by_type.get(ct, 0) + 1

    return {"total_chunks": count, "by_content_type": by_type}