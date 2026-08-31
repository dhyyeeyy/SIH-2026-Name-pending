import asyncio

import pytest

from coder_agent.coder_agent import _extract_code_block


def test_extract_code_block_accepts_raw_python_without_fence():
    text = "Here is a small example:\n\nprint('hello from raw python')\n"
    assert _extract_code_block(text) == "print('hello from raw python')"


@pytest.mark.asyncio
async def test_generate_code_instructions_require_python_only(monkeypatch):
    class FakeResponse:
        def __init__(self):
            self._json = {"response": "```python\nprint('done')\n```"}

        def raise_for_status(self):
            return None

        def json(self):
            return self._json

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            assert "Return only valid Python code" in json["prompt"]
            return FakeResponse()

    monkeypatch.setattr("coder_agent.coder_agent.httpx.AsyncClient", FakeClient)

    from coder_agent.coder_agent import generate_code

    code = await generate_code("build a tiny hello script", {"output_dir": "./tmp"})
    assert code == "print('done')"
