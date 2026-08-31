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
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "open", "input"}

class SandboxViolation(Exception):
    pass

def static_check(code: str, *, strict: bool = False) -> list[str]:
    """Parse the code and optionally reject anything touching banned modules/calls.

    The default behavior is intentionally non-fatal: the generator can still show
    a user the code it produced even if the sandbox would consider it risky,
    while the caller can surface the warning in stderr without blocking output.
    """
    warnings: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        if strict:
            raise SandboxViolation(f"Code failed to parse: {e}")
        warnings.append(f"Code failed to parse: {e}")
        return warnings

    for node in ast.walk(tree):
        # import x / import x.y
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"socket", "requests", "urllib",
                                                  "subprocess", "multiprocessing", "ctypes"}:
                    msg = f"Banned import: {alias.name}"
                    if strict:
                        raise SandboxViolation(msg)
                    warnings.append(msg)
        # from x import y
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in {"socket", "requests", "urllib",
                                                               "subprocess", "multiprocessing", "ctypes"}:
                msg = f"Banned import: {node.module}"
                if strict:
                    raise SandboxViolation(msg)
                warnings.append(msg)
        # eval(...), exec(...), __import__(...), input(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__", "input"}:
                msg = f"Banned call: {node.func.id}()"
                if strict:
                    raise SandboxViolation(msg)
                warnings.append(msg)

    # 'open()' calls with a path outside output_dir aren't reliably catchable
    # statically (paths can be built dynamically) -- so open() is instead
    # restricted at RUNTIME via the wrapper below, not here.
    return warnings


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

    # Layer 1: static scan for risky patterns. These are presented as warnings
    # instead of a hard block so generated code can still reach the user.
    warnings = static_check(code)
    warning_text = "\n".join(warnings)

    full_script = RUNTIME_GUARD.format(output_dir=str(output_path)) + "\n\n" + code

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(full_script)
        script_path = f.name

    python_cmd = [sys.executable, "-I", script_path]
    env = os.environ.copy()
    if os.name != "nt":
        env["PATH"] = "/usr/bin:/bin" + os.pathsep + env.get("PATH", "")

    try:
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": str(output_path),
            "env": env,
            "stdin": subprocess.DEVNULL,
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
        combined_stderr = stderr.strip()
        if warning_text:
            combined_stderr = "\n".join(part for part in [warning_text, combined_stderr] if part).strip()
        return SandboxResult(success, stdout, combined_stderr, output_files)

    finally:
        try:
            os.unlink(script_path)
        except FileNotFoundError:
            pass