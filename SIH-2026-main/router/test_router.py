"""
Tests for router.py. Requires Ollama running locally with nomic-embed-text
pulled -- these are integration tests against the real embedding model,
not mocked, since routing quality is the thing we actually care about.
"""

import pytest

from router import route


def test_vision_override_when_no_extractable_text():
    result = route(
        "what does this say?",
        attachments=["scan.png"],
        has_extractable_text=False,
    )
    assert result["role"] == "vision"
    assert result["override"] is True


def test_vision_override_skips_when_text_present():
    result = route(
        "summarize this document",
        attachments=["report.pdf"],
        has_extractable_text=True,
    )
    assert result["override"] is False


def test_general_query_routes_to_general():
    result = route("Summarize the key findings from this maintenance report.")
    assert result["role"] == "general"


def test_code_query_routes_to_code():
    result = route("Write a Python function that validates an email address.")
    assert result["role"] == "code"


def test_no_attachments_never_triggers_override():
    result = route("hello")
    assert result["override"] is False


def test_route_returns_confidence_score():
    result = route("Explain this SOP to me.")
    assert isinstance(result["confidence"], float)
    assert -1.0 <= result["confidence"] <= 1.0


def test_empty_query_does_not_crash():
    result = route("")
    assert result["role"] in ("general", "code")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
