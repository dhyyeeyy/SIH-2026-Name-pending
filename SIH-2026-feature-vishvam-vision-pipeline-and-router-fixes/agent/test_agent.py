"""
Tests for agent.py. Integration tests against real Ollama models --
requires all 4 pulled models available locally.
"""

import os

import pytest
from PIL import Image

import agent
from agent import _downscale_for_vision, run


def test_run_returns_agent_result_shape():
    result = run("What is 2+2?", user_id="test-user")
    assert "final_answer" in result
    assert "trace" in result
    assert "files_to_generate" in result
    assert isinstance(result["final_answer"], str)
    assert isinstance(result["trace"], list)


def test_run_trace_includes_router_decision():
    result = run("Summarize this SOP.", user_id="test-user")
    steps = [entry["step"] for entry in result["trace"]]
    assert "router_decision" in steps


def test_run_code_query_routes_to_code_model():
    result = run("Write a function that reverses a string.", user_id="test-user")
    router_entry = next(e for e in result["trace"] if e["step"] == "router_decision")
    assert router_entry["detail"]["role"] == "code"


def test_run_general_query_produces_nonempty_answer():
    result = run("Explain what a checksum is.", user_id="test-user")
    assert len(result["final_answer"]) > 0


def test_run_with_image_attachment_triggers_vision_override():
    """
    Regression test: agent.run() must actually detect image attachments
    and route to vision, not silently fall through to the general/RAG
    path and ignore the attached image.
    """
    scratch_dir = os.environ.get("TEMP", ".")
    image_path = os.path.join(scratch_dir, "regression_test_image.png")
    Image.new("RGB", (100, 100), color="white").save(image_path)

    result = run("What does this say?", user_id="test-user", attachments=[image_path])
    router_entry = next(e for e in result["trace"] if e["step"] == "router_decision")
    assert router_entry["detail"]["role"] == "vision"
    assert router_entry["detail"]["override"] is True
    steps = [e["step"] for e in result["trace"]]
    assert "vision_extraction" in steps


def test_downscale_leaves_small_image_untouched():
    scratch_dir = os.environ.get("TEMP", ".")
    image_path = os.path.join(scratch_dir, "small_test_image.png")
    Image.new("RGB", (500, 300), color="white").save(image_path)

    result_path = _downscale_for_vision(image_path)
    assert result_path == image_path


def test_downscale_resizes_large_image():
    scratch_dir = os.environ.get("TEMP", ".")
    image_path = os.path.join(scratch_dir, "large_test_image.png")
    Image.new("RGB", (4000, 3000), color="white").save(image_path)

    result_path = _downscale_for_vision(image_path)
    try:
        assert result_path != image_path
        with Image.open(result_path) as resized:
            assert max(resized.size) == 1280
            # aspect ratio preserved (4000x3000 -> 4:3)
            assert resized.size == (1280, 960)
    finally:
        if result_path != image_path and os.path.exists(result_path):
            os.remove(result_path)


def _make_test_image():
    scratch_dir = os.environ.get("TEMP", ".")
    image_path = os.path.join(scratch_dir, "retry_test_image.png")
    Image.new("RGB", (100, 100), color="white").save(image_path)
    return image_path


def test_vision_retry_recovers_from_malformed_json(monkeypatch):
    """
    Regression test for the recursion/retry-cap requirement: the graph
    must retry vision extraction on malformed JSON rather than crashing,
    and succeed once the model produces valid JSON.
    """
    image_path = _make_test_image()
    call_count = {"n": 0}
    real_chat = agent.ollama.chat

    def fake_chat(*args, **kwargs):
        if "images" not in kwargs["messages"][0]:
            return real_chat(*args, **kwargs)  # let the final generate() call hit the real model
        call_count["n"] += 1
        if call_count["n"] < 3:
            return {"message": {"content": "not valid json{{{"}}
        return {
            "message": {
                "content": '{"document_type": "test", "key_findings": ["ok"], '
                '"recommended_action": "none", "raw_text": "test content"}'
            }
        }

    monkeypatch.setattr(agent.ollama, "chat", fake_chat)

    result = run("What does this say?", user_id="test-user", attachments=[image_path])

    steps = [e["step"] for e in result["trace"]]
    assert steps.count("vision_extraction_failed") == 2
    assert "rag_ingest" in steps
    assert call_count["n"] == 3


def test_vision_gives_up_gracefully_after_max_retries(monkeypatch):
    """
    Regression test: once malformed JSON exceeds MAX_STEP_RETRIES, the
    graph must fail gracefully with a clear message instead of crashing
    or looping forever.
    """
    image_path = _make_test_image()
    call_count = {"n": 0}

    def always_broken_chat(*args, **kwargs):
        call_count["n"] += 1
        return {"message": {"content": "still not valid json"}}

    monkeypatch.setattr(agent.ollama, "chat", always_broken_chat)

    result = run("What does this say?", user_id="test-user", attachments=[image_path])

    steps = [e["step"] for e in result["trace"]]
    assert steps.count("vision_extraction_failed") == agent.MAX_STEP_RETRIES
    assert "failed" in steps
    assert call_count["n"] == agent.MAX_STEP_RETRIES
    assert len(result["final_answer"]) > 0  # graceful message, not a crash


def test_run_with_use_rag_false_skips_retrieval():
    """
    Regression test for the RAG toggle: use_rag=False must skip
    retrieve_node entirely (no rag_retrieval step) and log rag_skipped
    instead, rather than silently retrieving anyway.
    """
    result = run("Explain what a checksum is.", user_id="test-user", use_rag=False)
    steps = [e["step"] for e in result["trace"]]
    assert "rag_skipped" in steps
    assert "rag_retrieval" not in steps


def test_run_with_use_rag_true_retrieves():
    result = run("Explain what a checksum is.", user_id="test-user", use_rag=True)
    steps = [e["step"] for e in result["trace"]]
    assert "rag_retrieval" in steps
    assert "rag_skipped" not in steps


def test_rag_skipped_not_logged_for_vision():
    """
    The RAG toggle is about searching *other* stored documents, not
    about whether an attached image gets read -- vision extraction
    must proceed regardless of use_rag.
    """
    image_path = _make_test_image()
    result = run("What does this say?", user_id="test-user", attachments=[image_path], use_rag=False)
    steps = [e["step"] for e in result["trace"]]
    assert "rag_skipped" not in steps
    assert "vision_extraction" in steps


def test_retrieve_filters_irrelevant_chunks(monkeypatch):
    """
    rag.retrieve() must drop chunks beyond RELEVANCE_THRESHOLD rather
    than always returning the top-k regardless of actual relevance --
    a query unrelated to anything ingested should surface as zero
    hits, not the k least-bad matches.
    """
    import rag

    def fake_query(*args, **kwargs):
        return {
            "documents": [["irrelevant chunk one", "irrelevant chunk two"]],
            "metadatas": [[{}, {}]],
            "distances": [[0.9, 1.4]],  # both beyond RELEVANCE_THRESHOLD (0.6)
        }

    class FakeCollection:
        def query(self, *args, **kwargs):
            return fake_query()

    monkeypatch.setattr(rag, "_get_collection", lambda: FakeCollection())
    hits = rag.retrieve("some unrelated query")
    assert hits == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
