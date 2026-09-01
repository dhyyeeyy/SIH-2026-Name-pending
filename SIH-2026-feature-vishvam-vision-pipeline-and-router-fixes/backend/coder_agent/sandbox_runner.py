# sandbox/runner.py
import ast
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import resource
except ImportError:  # Windows does not provide resource
    resource = None

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
    if resource is None:
        return
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))                  # 10s CPU time
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))  # 512MB address space
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))                  # no forking/threads spawning procs
    try:
        os.setsid()  # own process group, so we can kill children on timeout too
    except (AttributeError, OSError):
        pass


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        proc.kill()
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (AttributeError, OSError, ProcessLookupError):
        proc.kill()


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

    python_cmd = [sys.executable, "-I", script_path]
    env = os.environ.copy()
    if os.name != "nt":
        env = {"PATH": "/usr/bin:/bin"}

    try:
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": str(output_path),
            "env": env,
        }
        if os.name != "nt" and resource is not None:
            popen_kwargs["preexec_fn"] = _set_resource_limits
        proc = subprocess.Popen(python_cmd, **popen_kwargs)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(proc)
            stdout, stderr = proc.communicate()
            return SandboxResult(False, stdout, f"TIMEOUT after {timeout}s\n{stderr}", [])

        success = proc.returncode == 0
        output_files = [str(p) for p in output_path.rglob("*") if p.is_file()]
        return SandboxResult(success, stdout, stderr, output_files)

    finally:
        os.unlink(script_path)  # clean up the temp script regardless of outcome