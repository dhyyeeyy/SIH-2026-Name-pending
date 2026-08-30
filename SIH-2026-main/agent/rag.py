"""
Local vector store for RAG: ingestion and retrieval over SOPs, manuals,
correspondence, and vision-derived document summaries + raw OCR text.

Uses Chroma with a persistent local directory (no network calls) and
the CPU-pinned nomic-embed-text model for embeddings.
"""

import json
import uuid
from pathlib import Path

import chromadb
import ollama

CONFIG_PATH = Path(__file__).parent.parent / "router" / "model_config.json"
DB_PATH = Path(__file__).parent / "chroma_store"

# Cosine distance (1 - cosine_similarity), explicitly set rather than
# Chroma's raw-L2 default -- keeps this consistent with router.py, which
# already reasons in cosine similarity for classification. Range is
# 0 (identical) to 2 (opposite); a chunk beyond this distance is treated
# as unrelated to the query, not "weakly relevant".
RELEVANCE_THRESHOLD = 0.6

_client = None
_collection = None


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(DB_PATH))
        _collection = _client.get_or_create_collection(
            "documents", metadata={"hnsw:space": "cosine"}
        )
    return _collection


def _embed_text(text: str) -> list[float]:
    config = _load_config()
    embedding_model = config["models"]["embedding"]["ollama_tag"]
    response = ollama.embeddings(model=embedding_model, prompt=text)
    return response["embedding"]


def ingest(text: str, metadata: dict) -> str | None:
    """
    Embed and store a chunk of text with metadata. Used both for plain
    document ingestion and for vision-derived output -- callers should
    ingest the structured summary and the raw OCR text as two separate
    calls, tagged via metadata["content_type"] (e.g. "summary" | "raw_ocr" | "document").

    Returns None (and stores nothing) for empty/whitespace-only text --
    e.g. a blank or text-less scanned image legitimately produces empty
    raw OCR text, and embedding an empty string returns a malformed
    zero-length vector that crashes Chroma downstream with a cryptic
    IndexError rather than a clear failure.
    """
    if not text.strip():
        return None

    collection = _get_collection()
    doc_id = str(uuid.uuid4())
    embedding = _embed_text(text)
    collection.add(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata],
    )
    return doc_id


def retrieve(query: str, k: int = 5) -> list[dict]:
    """
    Return the top-k matching chunks for a query, each as
    {"text": str, "metadata": dict, "distance": float} -- filtered to
    chunks within RELEVANCE_THRESHOLD. A query genuinely unrelated to
    anything ingested returns an empty list rather than the k
    least-bad matches, so callers can distinguish "nothing relevant"
    from "here's weakly-related context".
    """
    collection = _get_collection()
    query_embedding = _embed_text(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=k)

    hits = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    for text, metadata, distance in zip(documents, metadatas, distances):
        if distance <= RELEVANCE_THRESHOLD:
            hits.append({"text": text, "metadata": metadata, "distance": distance})
    return hits
