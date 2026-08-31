from unittest.mock import patch

import orchestrator
from router import route


@patch("orchestrator.run_instruct")
@patch("orchestrator.route")
def test_handle_request_defaults_to_rag_off_when_not_specified(mock_route, mock_run_instruct):
    mock_route.return_value = {"role": "general", "confidence": 0.9}
    mock_run_instruct.return_value = {
        "answer": "ok",
        "insufficient_context": False,
        "sources_used": [],
        "n_sources_retrieved": 0,
    }

    orchestrator.handle_request("What is the project status?")

    assert mock_run_instruct.call_args.kwargs["use_rag"] is False


def test_route_keeps_plain_natural_language_out_of_code_path(monkeypatch):
    monkeypatch.setattr("router._route_with_ollama", lambda _prompt: "CODE")

    result = route("What are three magical words")

    assert result["role"] == "general"
    assert result["confidence"] >= 0.8
