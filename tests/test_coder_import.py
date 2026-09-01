import importlib


def test_coder_package_imports():
    module = importlib.import_module("coder_agent.coder")
    assert hasattr(module, "run_coder_task")
    assert hasattr(module, "CoderTaskResult")


def test_coder_agent_parses_runtime_code_snippet():
    module = importlib.import_module("coder_agent.coder_agent")
    raw = """
Traceback (most recent call last):
  File \"main.py\", line 3, in <module>
    print(1 / 0)

```python
print('hello from parsed snippet')
```
"""
    assert module.parse_code_snippet(raw) == "print('hello from parsed snippet')"
