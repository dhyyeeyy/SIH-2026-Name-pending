"""
Integration tests for vision.py's run_vision_task() — the entry point the
orchestrator/router actually calls. Mocks analyze_document (the model/OCR
layer, already covered by test_vision_agent.py) and the embedding function
(no real Ollama needed), so these focus purely on the wiring: does
run_vision_task correctly call cross-reference and KB storage.

Run with: pytest tests/test_vision_task.py -v
"""
import os
import numpy as np
import pytest
from unittest.mock import patch, AsyncMock


FAKE_VISION_RESULT = {
    "observed": ["Tag PT-101 reading 4.2 bar", "Valve V-12 closed"],
    "unclear": [],
    "raw": "fake raw response",
}


def _fake_embed(self, input):
    """Deterministic hash-based fake embedding — no real Ollama needed."""
    out = []
    for text in input:
        rng = np.random.RandomState(abs(hash(text)) % (2**31))
        out.append(rng.rand(64).tolist())
    return out


@pytest.fixture(autouse=True)
def _isolated_chroma_store(tmp_path, monkeypatch):
    """
    Each test gets its own ChromaDB path under pytest's tmp_path, rather
    than sharing/wiping one fixed directory. ChromaDB's PersistentClient
    caches connections internally per-path; deleting and recreating the
    same path between tests corrupts that cached connection and causes
    spurious "readonly database" errors on the next test. A fresh path per
    test sidesteps that entirely, and pytest cleans tmp_path up on its own.
    """
    import knowledge.ingest as ingest_module
    import knowledge.retriever as retriever_module

    isolated_path = str(tmp_path / "chroma_store")
    monkeypatch.setattr(ingest_module, "CHROMA_STORE_PATH", isolated_path)
    monkeypatch.setattr(retriever_module, "CHROMA_STORE_PATH", isolated_path)
    yield


@pytest.fixture
def fake_file(tmp_path):
    f = tmp_path / "scan1.png"
    f.write_bytes(b"fake bytes")
    return str(f)


def test_run_vision_task_default_stores_result(fake_file):
    with patch("vision.analyze_document", new=AsyncMock(return_value=FAKE_VISION_RESULT)), \
         patch("knowledge.embeddings.OllamaLocalEmbeddingFunction.__call__", _fake_embed):
        from vision import run_vision_task
        result = run_vision_task(fake_file, "what do you see", context={})

    assert result["observed"] == FAKE_VISION_RESULT["observed"]
    assert result["chunks_stored"] == 2, "should store both OBSERVED lines by default"


def test_run_vision_task_opt_out_does_not_store(fake_file):
    with patch("vision.analyze_document", new=AsyncMock(return_value=FAKE_VISION_RESULT)), \
         patch("knowledge.embeddings.OllamaLocalEmbeddingFunction.__call__", _fake_embed):
        from vision import run_vision_task
        from knowledge.retriever import collection_stats

        result = run_vision_task(fake_file, "preview only", context={}, store_result=False)
        stats = collection_stats()

    assert result["chunks_stored"] == 0
    assert stats["total_chunks"] == 0, "opt-out call must not write anything to the KB"


def test_run_vision_task_cross_reference_finds_prior_storage(fake_file):
    with patch("vision.analyze_document", new=AsyncMock(return_value=FAKE_VISION_RESULT)), \
         patch("knowledge.embeddings.OllamaLocalEmbeddingFunction.__call__", _fake_embed):
        from vision import run_vision_task

        # first call stores findings (default store_result=True)
        run_vision_task(fake_file, "initial scan", context={}, source_id="scan1")

        # second call cross-references and should find what the first call stored
        result2 = run_vision_task(
            fake_file, "PT-101 status", context={},
            cross_reference=True, cross_reference_query="PT-101",
        )

    assert len(result2["prior_findings"]) > 0
    assert any("PT-101" in f["text"] for f in result2["prior_findings"])


def test_run_vision_task_cross_reference_off_by_default(fake_file):
    with patch("vision.analyze_document", new=AsyncMock(return_value=FAKE_VISION_RESULT)), \
         patch("knowledge.embeddings.OllamaLocalEmbeddingFunction.__call__", _fake_embed):
        from vision import run_vision_task
        result = run_vision_task(fake_file, "what do you see", context={})

    assert result["prior_findings"] == [], "cross_reference defaults to False, must return empty list"


def test_run_vision_task_source_id_defaults_to_filename_stem(fake_file):
    with patch("vision.analyze_document", new=AsyncMock(return_value=FAKE_VISION_RESULT)), \
         patch("knowledge.embeddings.OllamaLocalEmbeddingFunction.__call__", _fake_embed):
        from vision import run_vision_task
        from knowledge.retriever import query_knowledge_with_metadata

        run_vision_task(fake_file, "scan", context={})  # no source_id passed
        results = query_knowledge_with_metadata("PT-101", n=1)

    assert results[0]["metadata"]["source_id"] == "scan1"  # matches fake_file's stem


def test_run_vision_task_propagates_analyze_document_failure(fake_file):
    with patch("vision.analyze_document", new=AsyncMock(side_effect=ValueError("no OBSERVED/UNCLEAR block"))):
        from vision import run_vision_task
        with pytest.raises(ValueError, match="no OBSERVED/UNCLEAR block"):
            run_vision_task(fake_file, "what do you see", context={})