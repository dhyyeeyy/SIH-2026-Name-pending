# sandbox/runner.py
import ast
import subprocess
import tempfile
import os
import resource
import signal
from pathlib import Path
from dataclasses import dataclass

# --- 1. Static analysis: reject before ever running ---

BANNED_MODULES = {
    "socket", "requests", "urllib", "urllib2", "http", "ftplib",
    "subprocess", "multiprocessing", "os.system", "ctypes", "shutil.rmtree"
}
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "open"}  # 'open' handled separately below

class SandboxViolation(Exception):
    pass

def static_check(code: str) -> None:
    """Parse the code and reject anything touching banned modules/calls
    before it ever runs as a subprocess."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxViolation(f"Code failed to parse: {e}")

    for node in ast.walk(tree):
        # import x / import x.y
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"socket", "requests", "urllib",
                                                  "subprocess", "multiprocessing", "ctypes"}:
                    raise SandboxViolation(f"Banned import: {alias.name}")
        # from x import y
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in {"socket", "requests", "urllib",
                                                               "subprocess", "multiprocessing", "ctypes"}:
                raise SandboxViolation(f"Banned import: {node.module}")
        # eval(...), exec(...), __import__(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise SandboxViolation(f"Banned call: {node.func.id}()")

    # 'open()' calls with a path outside output_dir aren't reliably catchable
    # statically (paths can be built dynamically) -- so open() is instead
    # restricted at RUNTIME via the wrapper below, not here.


# --- 2 & 3. Runtime wrapper injected around the model's code ---

RUNTIME_GUARD = """
import builtins, os as _os

_ALLOWED_DIR = _os.path.abspath({output_dir!r})
_real_open = builtins.open

def _guarded_open(path, mode="r", *args, **kwargs):
    abspath = _os.path.abspath(path)
    if not abspath.startswith(_ALLOWED_DIR):
        raise PermissionError(f"Sandbox: write/read outside OUTPUT_DIR blocked: {{abspath}}")
    return _real_open(path, mode, *args, **kwargs)

builtins.open = _guarded_open
OUTPUT_DIR = _ALLOWED_DIR
"""

def _set_resource_limits():
    """Called in the child process (preexec_fn) before exec — caps CPU, memory,
    and blocks forking so a runaway script can't fork-bomb or eat all RAM."""
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))                  # 10s CPU time
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))  # 512MB address space
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))                  # no forking/threads spawning procs
    os.setsid()  # own process group, so we can kill children on timeout too


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    output_files: list[str]


def run_in_sandbox(code: str, output_dir: str, timeout: int = 20) -> SandboxResult:
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    # Layer 1: static reject before touching disk
    static_check(code)

    full_script = RUNTIME_GUARD.format(output_dir=str(output_path)) + "\n\n" + code

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(full_script)
        script_path = f.name

    try:
        proc = subprocess.Popen(
            ["python3", "-I", script_path],   # -I = isolated mode: ignores env vars, user site-packages
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=_set_resource_limits,   # Linux only
            cwd=str(output_path),              # relative paths land inside output_dir
            env={"PATH": "/usr/bin:/bin"},     # minimal env, no secrets leak via os.environ
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # kill whole process group
            stdout, stderr = proc.communicate()
            return SandboxResult(False, stdout, f"TIMEOUT after {timeout}s\n{stderr}", [])

        success = proc.returncode == 0
        output_files = [str(p) for p in output_path.rglob("*") if p.is_file()]
        return SandboxResult(success, stdout, stderr, output_files)

    finally:
        os.unlink(script_path)  # clean up the temp script regardless of outcome