# knowledge/embeddings.py
"""
Shared embedding function for ChromaDB, backed by nomic-embed-text served
locally through Ollama. This is the CPU/always-resident model per the
architecture doc — it does NOT hot-swap with the GPU workers, so calling it
doesn't unload eng-coder/eng-vision/eng-general.

Chroma's embedding_functions interface expects a callable class with
__call__(self, input: list[str]) -> list[list[float]]. We implement it
directly against Ollama's HTTP API rather than depending on chromadb's
built-in OllamaEmbeddingFunction, so behavior (timeouts, error handling,
zero-outbound guarantee) is explicit and in our control.
"""

import httpx
from chromadb import Documents, EmbeddingFunction, Embeddings

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
REQUEST_TIMEOUT_SECONDS = 30


class OllamaLocalEmbeddingFunction(EmbeddingFunction):
    """Embeds text via the local Ollama nomic-embed-text model. No network
    calls other than to localhost:11434."""

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: Embeddings = []
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            for text in input:
                resp = client.post(
                    OLLAMA_EMBED_URL,
                    json={"model": EMBED_MODEL, "prompt": text},
                )
                resp.raise_for_status()
                embeddings.append(resp.json()["embedding"])
        return embeddings