import importlib


def test_coder_package_imports():
    module = importlib.import_module("coder_agent.coder")
    assert hasattr(module, "run_coder_task")
    assert hasattr(module, "CoderTaskResult")
