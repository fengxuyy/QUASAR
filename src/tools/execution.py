import os
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import io
import threading
import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union, Dict, Any

import psutil
from langchain_core.tools import tool

from .base import WORKSPACE_DIR, truncate_content, PROTECTED_SYSTEM_FILES


# Global state for tracking running process during check-in
_running_process: Optional[subprocess.Popen] = None
_process_pgid: Optional[int] = None  # Process group ID for killing child processes
_process_start_time: Optional[float] = None
_process_script_path: Optional[Path] = None
_process_timeout_seconds: Optional[float] = None
_process_timeout_minutes: Optional[float] = None
_process_use_temp_file: bool = False
_process_output_capture: Optional["OutputCaptureState"] = None


_MAX_CAPTURE_CHARS = 500_000


@dataclass
class OutputCaptureState:
    """Bounded stdout/stderr capture for a single subprocess."""
    stdout_chunks: Optional[deque[str]] = None
    stderr_chunks: Optional[deque[str]] = None
    stdout_size: int = 0
    stderr_size: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    threads: list[threading.Thread] = field(default_factory=list)





def _parse_check_in_after_seconds(
    value: Optional[float],
    field_name: str = "check_in_after",
) -> tuple[Optional[float], Optional[str]]:
    """Convert an agent-provided check-in delay in minutes to seconds."""
    if value is None:
        return None, None

    try:
        minutes = float(value)
    except (TypeError, ValueError):
        return None, f"Error: '{field_name}' must be a positive number of minutes."

    if not math.isfinite(minutes) or minutes <= 0:
        return None, f"Error: '{field_name}' must be a positive number of minutes."

    return minutes * 60.0, None


def _format_elapsed_time(seconds: float) -> str:
    """Format elapsed time in a human-readable way."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def _format_timeout_minutes(timeout_minutes: float) -> str:
    """Format an internal runtime-limit value in minutes without unnecessary trailing zeros."""
    timeout_value = float(timeout_minutes)
    if timeout_value.is_integer():
        return str(int(timeout_value))
    return f"{timeout_value:g}"


def _cleanup_temp_script(script_path: Optional[Path], use_temp_file: bool) -> None:
    """Remove temporary execution scripts when they are no longer needed."""
    if not use_temp_file or script_path is None or not script_path.exists():
        return

    try:
        script_path.unlink()
    except Exception:
        pass


def _clear_execution_state(cleanup_temp_file: bool = False) -> None:
    """Reset tracked execution state after a run completes or is terminated."""
    global _running_process, _process_pgid, _process_start_time, _process_script_path
    global _process_timeout_seconds, _process_timeout_minutes, _process_use_temp_file
    global _process_output_capture

    script_path = _process_script_path
    use_temp_file = _process_use_temp_file

    _running_process = None
    _process_pgid = None
    _process_start_time = None
    _process_script_path = None
    _process_timeout_seconds = None
    _process_timeout_minutes = None
    _process_use_temp_file = False
    _process_output_capture = None

    if cleanup_temp_file:
        _cleanup_temp_script(script_path, use_temp_file)


def _reset_output_capture(capture_state: OutputCaptureState) -> None:
    """Reset buffered stdout/stderr state for the active execution."""
    capture_state.stdout_chunks = None
    capture_state.stderr_chunks = None
    capture_state.stdout_size = 0
    capture_state.stderr_size = 0
    capture_state.threads = []


def _append_captured_output(capture_state: OutputCaptureState, stream_name: str, chunk: str) -> None:
    """Append output while keeping memory bounded for long-running jobs."""
    with capture_state.lock:
        if stream_name == "stdout":
            if capture_state.stdout_chunks is None:
                capture_state.stdout_chunks = deque()
            capture_state.stdout_chunks.append(chunk)
            capture_state.stdout_size += len(chunk)
            while capture_state.stdout_size > _MAX_CAPTURE_CHARS and capture_state.stdout_chunks:
                capture_state.stdout_size -= len(capture_state.stdout_chunks.popleft())
        else:
            if capture_state.stderr_chunks is None:
                capture_state.stderr_chunks = deque()
            capture_state.stderr_chunks.append(chunk)
            capture_state.stderr_size += len(chunk)
            while capture_state.stderr_size > _MAX_CAPTURE_CHARS and capture_state.stderr_chunks:
                capture_state.stderr_size -= len(capture_state.stderr_chunks.popleft())


def _drain_process_stream(capture_state: OutputCaptureState, stream: io.TextIOBase, stream_name: str) -> None:
    """Continuously drain a subprocess pipe so verbose jobs do not block."""
    try:
        for chunk in iter(stream.readline, ""):
            if not chunk:
                break
            _append_captured_output(capture_state, stream_name, chunk)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _start_output_capture(process: subprocess.Popen, capture_state: OutputCaptureState) -> None:
    """Start background readers for stdout/stderr when real pipes are available."""
    _reset_output_capture(capture_state)

    for stream_name in ("stdout", "stderr"):
        stream = getattr(process, stream_name, None)
        if isinstance(stream, io.TextIOBase):
            reader = threading.Thread(
                target=_drain_process_stream,
                args=(capture_state, stream, stream_name),
                daemon=True,
            )
            reader.start()
            capture_state.threads.append(reader)


def _consume_captured_output(process: subprocess.Popen) -> tuple[str, str]:
    """Collect buffered stdout/stderr, falling back to communicate for mocked processes."""
    capture_state = _process_output_capture

    if capture_state and capture_state.threads:
        for reader in capture_state.threads:
            reader.join(timeout=1.0)

        with capture_state.lock:
            stdout = "".join(capture_state.stdout_chunks) if capture_state.stdout_chunks else ""
            stderr = "".join(capture_state.stderr_chunks) if capture_state.stderr_chunks else ""

        _reset_output_capture(capture_state)
        return stdout, stderr

    stdout, stderr = process.communicate()
    if capture_state:
        _reset_output_capture(capture_state)
    return stdout, stderr


def _snapshot_execution_state() -> Dict[str, Any]:
    """Capture the currently tracked execution state so it can be restored later."""
    return {
        "running_process": _running_process,
        "process_pgid": _process_pgid,
        "process_start_time": _process_start_time,
        "process_script_path": _process_script_path,
        "process_timeout_seconds": _process_timeout_seconds,
        "process_timeout_minutes": _process_timeout_minutes,
        "process_use_temp_file": _process_use_temp_file,
        "process_output_capture": _process_output_capture,
    }


def _restore_execution_state(snapshot: Dict[str, Any]) -> None:
    """Restore a previously captured execution state."""
    global _running_process, _process_pgid, _process_start_time, _process_script_path
    global _process_timeout_seconds, _process_timeout_minutes, _process_use_temp_file
    global _process_output_capture

    _running_process = snapshot["running_process"]
    _process_pgid = snapshot["process_pgid"]
    _process_start_time = snapshot["process_start_time"]
    _process_script_path = snapshot["process_script_path"]
    _process_timeout_seconds = snapshot["process_timeout_seconds"]
    _process_timeout_minutes = snapshot["process_timeout_minutes"]
    _process_use_temp_file = snapshot["process_use_temp_file"]
    _process_output_capture = snapshot["process_output_capture"]


# Lines whose *sole content* is library noise we already suppress via env vars.
# When ALL non-blank stderr lines match these patterns, the stderr is omitted.
_NOISE_PATTERNS = [
    "tokenizers",
    "huggingface",
    "hf_hub",
    "transformers",
    "__warningregistry__",
    "tqdm",
]

# Python warning category names (as they appear before the colon in stderr).
_WARNING_CATEGORIES = (
    "UserWarning",
    "DeprecationWarning",
    "FutureWarning",
    "RuntimeWarning",
    "SyntaxWarning",
    "ResourceWarning",
    "PendingDeprecationWarning",
    "ImportWarning",
    "UnicodeWarning",
    "BytesWarning",
    "Warning",
)


def _is_noise_line(line: str) -> bool:
    """Return True if the line is pure library noise that should be suppressed."""
    lower = line.lower()
    return any(pat in lower for pat in _NOISE_PATTERNS)


def _format_stderr(stderr: str, is_failure: bool) -> str:
    """Parse Python stderr into structured, readable markdown sections.

    Categorises lines into:
    - Python warnings  → blockquoted warning block with count
    - Tracebacks/exceptions → blockquoted error block
    - Other output    → fenced code block (as before)

    Suppresses the stderr section entirely when all non-blank lines are noise.

    Args:
        stderr: Raw stderr string from the subprocess.
        is_failure: True when the process exited with a non-zero return code.

    Returns:
        Formatted markdown string (may be empty when only noise is present).
    """
    import re

    lines = stderr.splitlines()

    # --- Fast path: suppress-only noise ---
    meaningful = [l for l in lines if l.strip()]
    if not meaningful:
        return ""
    if all(_is_noise_line(l) for l in meaningful):
        return ""

    # --- Classify lines into buckets ---
    # Each bucket is a list of (kind, [lines]) where kind ∈ {"warning", "traceback", "other"}
    sections: list[tuple[str, list[str]]] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip noise lines
        if _is_noise_line(line):
            i += 1
            continue

        # --- Traceback block ---
        if line.strip().startswith("Traceback (most recent call last):"):
            tb_lines = [line]
            i += 1
            while i < len(lines):
                tb_line = lines[i]
                if _is_noise_line(tb_line):
                    i += 1
                    continue
                tb_lines.append(tb_line)
                # Traceback ends at the exception line (no leading whitespace, contains ':')
                # except for the header and "File" / continuation lines
                stripped = tb_line.strip()
                if (
                    stripped
                    and not stripped.startswith("File ")
                    and not stripped.startswith("^")
                    and not stripped.startswith("~")
                    and not stripped.startswith("During handling")
                    and not tb_line.startswith(" ")  # indented → part of traceback body
                ):
                    i += 1
                    break
                i += 1
            sections.append(("traceback", tb_lines))
            continue

        # --- Python warning block (warnings module format) ---
        # Suppress all warnings — they are noisy and rarely actionable for the LLM.
        # Format: "path/file.py:N: WarningCategory: message" or "WarningCategory: message"
        warning_match = re.match(
            r'^(?:.+\.py:\d+: )?(' + '|'.join(_WARNING_CATEGORIES) + r'): (.+)$',
            line.strip(),
        )
        if warning_match or any(
            line.strip().startswith(cat + ":") for cat in _WARNING_CATEGORIES
        ):
            i += 1
            # Also skip the source-context line the warnings module appends (indented)
            if i < len(lines) and lines[i].startswith("  "):
                i += 1
            continue

        # --- Other output ---
        # Merge consecutive "other" lines into one block
        if sections and sections[-1][0] == "other":
            sections[-1][1].append(line)
        else:
            sections.append(("other", [line]))
        i += 1

    if not sections:
        return ""

    # --- Render sections ---
    parts: list[str] = []

    for kind, block in sections:
        if kind == "traceback":
            header = "**✗ Error:**" if is_failure else "**⚠ Exception (non-fatal):**"
            blockquote = "\n".join(
                f"> {l}" if l.strip() else ">" for l in block
            )
            parts.append(f"{header}\n\n{blockquote}")

        else:  # other
            other_text = "\n".join(block).strip()
            if other_text:
                other_text = truncate_content(other_text)
                label = "**Error Output:**" if is_failure else "**Logs / Info:**"
                parts.append(f"{label}\n\n```\n{other_text}\n```")

    return "\n\n".join(parts)

def _build_execution_result(stdout: str, stderr: str, header: str, *, is_failure: bool) -> str:
    """Render execution output into the standard markdown result format."""
    md_result = f"**Execution Result:**\n\n> {header}\n"

    if stdout:
        truncated_stdout = truncate_content(stdout)
        md_result += f"\n**Output:**\n\n```\n{truncated_stdout}\n```\n"

    if stderr:
        formatted_stderr = _format_stderr(stderr, is_failure=is_failure)
        if formatted_stderr:
            md_result += f"\n{formatted_stderr}\n"

    return md_result.strip()


def _collect_execution_result(
    process: subprocess.Popen,
    script_path: Path,
    was_interrupted: bool = False,
    interruption_reason: Optional[str] = None
) -> str:
    """Collect and format execution result from a completed/terminated process."""
    stdout, stderr = _consume_captured_output(process)
    
    # Build success/failure header
    if was_interrupted:
        header = "Code execution was interrupted by user"
        if interruption_reason:
            header += f" (reason: {interruption_reason})"
    else:
        status = "successfully" if process.returncode == 0 else "failed"
        header = f"Code executed {status} (exit code: {process.returncode})"

    return _build_execution_result(
        stdout,
        stderr,
        header,
        is_failure=(not was_interrupted) and (process.returncode != 0),
    )

def _kill_process_and_children(process: subprocess.Popen, pgid: Optional[int]) -> None:
    """Recursively kill a process, its children, and its process group."""
    processes_to_kill = set()
    
    # 1. Collect process tree using psutil
    try:
        parent = psutil.Process(process.pid)
        processes_to_kill.add(parent)
        try:
            children = parent.children(recursive=True)
        except Exception:
            children = []
        processes_to_kill.update(children)
    except Exception:
        pass
    
    # 2. Try graceful termination first (SIGTERM)
    # Send to specific processes we found
    for p in processes_to_kill:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
            
    # Also send to process group if we have it
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
            
    # Brief wait for graceful exit
    if processes_to_kill:
        psutil.wait_procs(processes_to_kill, timeout=2.0)
    else:
        time.sleep(1.0)
        
    # 3. Force kill anything still alive (SIGKILL)
    for p in processes_to_kill:
        try:
            if p.is_running():
                p.kill()
        except psutil.NoSuchProcess:
            pass
            
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
            
    # Try one final wait on the main subprocess
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass


def _find_processes_in_group(pgid: Optional[int], exclude_pids: Optional[set[int]] = None) -> list[psutil.Process]:
    """Return processes that are still in the given process group."""
    if pgid is None:
        return []

    exclude_pids = exclude_pids or set()
    matches: list[psutil.Process] = []
    try:
        for proc in psutil.process_iter(['pid']):
            try:
                if proc.pid in exclude_pids:
                    continue
                if os.getpgid(proc.pid) == pgid:
                    matches.append(proc)
            except (ProcessLookupError, PermissionError, psutil.Error, OSError):
                continue
    except (psutil.Error, OSError, PermissionError):
        return matches
    return matches


def _handle_internal_runtime_limit(process: subprocess.Popen, script_path: Path) -> str:
    """Terminate an internal helper execution after exceeding its runtime guard."""
    timeout_minutes = _process_timeout_minutes

    _kill_process_and_children(process, _process_pgid)
    result = _collect_execution_result(process, script_path)
    _clear_execution_state(cleanup_temp_file=True)

    timeout_info = "\n\n**Internal Runtime Limit:**\n\n"
    if timeout_minutes is None:
        timeout_info += "> Internal helper execution exceeded its configured runtime limit.\n"
    else:
        timeout_info += (
            f"> Internal helper execution exceeded the configured runtime limit of "
            f"{_format_timeout_minutes(timeout_minutes)} minutes.\n"
        )
    timeout_info += "> The process was terminated.\n"
    timeout_info += "> Use a narrower helper snippet if more inspection is needed.\n\n"

    return timeout_info + result


def execute_python_with_state_preserved(
    *,
    code: str,
    omp_num_threads: int = 1,
    max_runtime_minutes: Optional[float] = None,
) -> Union[str, Dict[str, Any]]:
    """Run execute_python while preserving any currently tracked long-running execution."""
    snapshot = _snapshot_execution_state()

    try:
        return _execute_python_impl(
            code=code,
            omp_num_threads=omp_num_threads,
            max_runtime_minutes=max_runtime_minutes,
        )
    finally:
        _restore_execution_state(snapshot)


@tool
def execute_python(
    check_in_after: float,
    file_path: Optional[str] = None,
    code: Optional[str] = None,
    omp_num_threads: int = 1,
) -> Union[str, Dict[str, Any]]:
    """Execute Python code directly or from a file.
    
    The code will have access to ASE, pymatgen, MACE, RASPA3, Quantum ESPRESSO, LAMMPS, RDKit, and command-line tools such as ORCA and xTB, plus standard libraries.
    
    **Note:** Including `code` together with `file_path` is HIGHLY recommended. This ensures the script 
    is saved to a named file for traceability and reproducibility, rather than using a disposable temp file.
    
    Args:
        file_path: Optional path to the Python file. If provided with `code`, the code will be written 
                   to this file before execution. If provided without `code`, the existing file will be executed.
        code: Optional Python code to execute directly. If provided without `file_path`, a temporary file 
              will be used (recommended only for simple, quick scripts). If provided with `file_path`, 
              the code will be written to that file before execution.
        check_in_after: Required agent-selected delay in minutes before asking the agent to review
                        whether a still-running execution should continue or be interrupted.
        omp_num_threads: Number of OpenMP threads per MPI process (default: 1). Set this when running 
                        hybrid MPI+OpenMP codes. Constraint: Concurrent Jobs x MPI_ranks x OMP_NUM_THREADS <= Total Physical cores
    
    Returns:
        Execution results including stdout, stderr, and return code. Still-running
        executions are never terminated by a tool timeout; they return a check-in
        request when the agent-selected check-in delay is reached.
    
    Examples:
        - execute_python(file_path="production.py", code="...", check_in_after=30) - Production run with an agent-scheduled check-in after 30 minutes
        - execute_python(code="print('smoke')", check_in_after=2.0) - Quick smoke test with agent review after 2 minutes if still running
    """
    if check_in_after is None:
        return "Error: 'check_in_after' is required and must be an agent-selected positive number of minutes."

    return _execute_python_impl(
        file_path=file_path,
        code=code,
        check_in_after=check_in_after,
        omp_num_threads=omp_num_threads,
    )


def _execute_python_impl(
    file_path: Optional[str] = None,
    code: Optional[str] = None,
    max_runtime_minutes: Optional[float] = None,
    check_in_after: Optional[float] = None,
    omp_num_threads: int = 1,
) -> Union[str, Dict[str, Any]]:
    """Internal Python execution implementation.

    The public execute_python tool has no hard runtime timeout. The private
    max_runtime_minutes guard is reserved for short-lived internal helper
    snippets such as execute_temporary_python.
    """
    global _running_process, _process_pgid, _process_start_time, _process_script_path
    global _process_timeout_seconds, _process_timeout_minutes, _process_use_temp_file
    global _process_output_capture

    execution_timeout_seconds = None
    timeout_minutes = None
    if max_runtime_minutes is not None:
        try:
            timeout_minutes = float(max_runtime_minutes)
        except (TypeError, ValueError):
            return "Error: internal runtime limit must be a positive number of minutes."
        if timeout_minutes <= 0:
            return "Error: internal runtime limit must be a positive number of minutes."
        execution_timeout_seconds = timeout_minutes * 60.0

    # Validate arguments
    if file_path is None and code is None:
        return "Error: Either 'file_path' or 'code' must be provided."
    
    check_interval, check_interval_error = _parse_check_in_after_seconds(check_in_after)
    if check_interval_error:
        return check_interval_error

    use_temp_file = False
    script_path: Optional[Path] = None
    
    try:
        # Case 1: Code provided with file_path - write code to file then execute
        if code is not None and file_path is not None:
            if os.path.isabs(file_path):
                script_path = Path(file_path)
            else:
                script_path = WORKSPACE_DIR / file_path
            
            # Security check
            script_path = script_path.resolve()
            if not str(script_path).startswith(str(WORKSPACE_DIR.resolve())):
                return f"Error: Cannot create files outside workspace directory."
            
            # Create parent directories if needed
            script_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write code to file
            script_path.write_text(code)
        
        # Case 2: Code provided without file_path - use temp file (for simple scripts only)
        elif code is not None and file_path is None:
            use_temp_file = True
            # Create temp file in workspace directory
            temp_fd, temp_path = tempfile.mkstemp(suffix='.py', dir=str(WORKSPACE_DIR), prefix='_temp_exec_')
            script_path = Path(temp_path)
            try:
                os.write(temp_fd, code.encode('utf-8'))
            finally:
                os.close(temp_fd)
        
        # Case 3: No code provided - execute existing file
        else:
            if os.path.isabs(file_path):
                script_path = Path(file_path)
            else:
                script_path = WORKSPACE_DIR / file_path

            # Security check
            script_path = script_path.resolve()
            if not str(script_path).startswith(str(WORKSPACE_DIR.resolve())):
                return f"Error: Cannot execute files outside workspace directory."

            if not script_path.exists() or not script_path.is_file():
                return f"Error: File '{file_path}' does not exist. Create the file with Python/pathlib or provide the 'code' argument."

        # Protect internal/hidden files from being executed or written to during execution
        if script_path.name in PROTECTED_SYSTEM_FILES:
            return (
                f"**Execution Error:** `{file_path}`\n\n> "
                f"Error: Execution of '{script_path.name}' is not permitted because it is an "
                "internal system file."
            )
        
        exec_path = str(script_path)
        
        # Setup execution environment using the system Python
        python_executable = sys.executable
        env = os.environ.copy()
        env["TOKENIZERS_PARALLELISM"] = "false"
        # Set OMP_NUM_THREADS from the argument (ensures LLM explicitly controls threading)
        env["OMP_NUM_THREADS"] = str(max(1, omp_num_threads))
        project_bin = WORKSPACE_DIR.parent / "bin"
        if project_bin.exists() and project_bin.is_dir():
            current_path = env.get("PATH", "")
            env["PATH"] = f"{project_bin}{os.pathsep}{current_path}"

        cmd = [python_executable, exec_path]
        
        # Start process with Popen for non-blocking execution
        # Use start_new_session=True to create a new process group
        # This allows us to kill all child processes (MPI jobs) together
        process = subprocess.Popen(
            cmd, 
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            bufsize=1,
            text=True, 
            cwd=str(WORKSPACE_DIR), 
            env=env,
            start_new_session=True
        )
        capture_state = OutputCaptureState()
        _start_output_capture(process, capture_state)
        
        # Get the process group ID for later cleanup
        pgid = os.getpgid(process.pid)
        
        start_time = time.time()
        
        # Store global state for potential resume
        _running_process = process
        _process_pgid = pgid
        _process_start_time = start_time
        _process_script_path = script_path
        _process_timeout_seconds = execution_timeout_seconds
        _process_timeout_minutes = timeout_minutes
        _process_use_temp_file = use_temp_file
        _process_output_capture = capture_state
        
        # Poll until process completes or the agent-selected check-in delay is reached
        while True:
            # Check for external interrupt (e.g. from web UI)
            try:
                import bridge
                if bridge.interrupt_event.is_set():
                    # Kill process and return interrupted result
                    _kill_process_and_children(process, _process_pgid)
                    
                    # Collect partial result with interrupted flag
                    result = _collect_execution_result(process, script_path, was_interrupted=True)
                    
                    _clear_execution_state(cleanup_temp_file=True)
                    
                    return result

            except ImportError:
                 pass

            # Check if process has completed
            poll_result = process.poll()
            if poll_result is not None:
                leftover = _find_processes_in_group(_process_pgid, exclude_pids={process.pid})
                if leftover:
                    # Ensure any stray child processes are terminated (even if the script exits cleanly).
                    _kill_process_and_children(process, _process_pgid)

                result = _collect_execution_result(process, script_path)
                _clear_execution_state(cleanup_temp_file=True)
                return result
            
            # Check if we've reached the internal helper guard or agent-selected check-in delay
            elapsed = time.time() - start_time
            if _process_timeout_seconds is not None and elapsed >= _process_timeout_seconds:
                return _handle_internal_runtime_limit(process, script_path)
            if check_interval is not None and elapsed >= check_interval:
                # Return check-in request - operator will handle prompting LLM
                return {
                    "status": "check_in_required",
                    "elapsed_seconds": elapsed,
                    "elapsed_display": _format_elapsed_time(elapsed),
                    "file_path": str(script_path),
                    "use_temp_file": use_temp_file,
                }
            
            # Sleep briefly before next poll (100ms)
            time.sleep(0.1)
            
    except subprocess.TimeoutExpired as e:
        # Special handling for script-level subprocess timeouts. QUASAR no longer
        # exposes a hard execution timeout, but a generated script can still raise
        # TimeoutExpired if it used subprocess.run(..., timeout=...).
        
        # Try to kill all child processes spawned by the script using psutil + killpg
        if _running_process is not None:
            _kill_process_and_children(_running_process, _process_pgid)
        
        # Collect any partial output
        result_msg = _collect_execution_result(
            _running_process, 
            _process_script_path,
            was_interrupted=False
        )
        
        _clear_execution_state(cleanup_temp_file=True)
        
        # Return helpful message with partial output
        timeout_info = f"\n\n**Subprocess Timeout:**\n\n> A subprocess in your script timed out after {e.timeout} seconds.\n> All child processes have been terminated.\n> Use `check_in_after` and the check-in decision tools for runtime control instead of script-level hard timeouts.\n> Check the partial output below to diagnose the issue.\n\n"
        
        return timeout_info + result_msg
    
    except Exception as e:
        # Clean up temp file on error too
        _cleanup_temp_script(script_path, use_temp_file)

        if _process_output_capture is not None:
            _reset_output_capture(_process_output_capture)
        _clear_execution_state()
        
        return f"**Execution Result:**\n\n> Error executing code: {str(e)}\n\n**Traceback:**\n\n```\n{traceback.format_exc()}```"


def resume_execution(check_in_after: float) -> Union[str, Dict[str, Any]]:
    """Resume monitoring a running Python process after check-in.
    
    This is called by the operator after LLM decides to continue execution.
    Args:
        check_in_after: Required agent-selected delay in minutes before the next
                        check-in.

    Returns the result when process completes, or another check-in request.
    """
    global _running_process, _process_pgid, _process_start_time, _process_script_path
    global _process_timeout_seconds, _process_timeout_minutes, _process_use_temp_file
    
    if _running_process is None:
        return "Error: No running process to resume."
    
    process = _running_process
    start_time = _process_start_time if _process_start_time is not None else time.time()
    script_path = _process_script_path

    if check_in_after is None:
        return "Error: 'next_check_in_after' is required and must be an agent-selected positive number of minutes."
    
    check_interval, check_interval_error = _parse_check_in_after_seconds(
        check_in_after,
        field_name="next_check_in_after",
    )
    if check_interval_error:
        return check_interval_error

    last_check_time = time.time()
    
    # Poll until process completes or the next agent-selected check-in delay is reached
    while True:
        poll_result = process.poll()
        if poll_result is not None:
            leftover = _find_processes_in_group(_process_pgid, exclude_pids={process.pid})
            if leftover:
                _kill_process_and_children(process, _process_pgid)

            result = _collect_execution_result(process, script_path)
            _clear_execution_state(cleanup_temp_file=True)
            return result
        
        # Check if we've reached the next agent-selected check-in delay
        elapsed_since_check = time.time() - last_check_time
        total_elapsed = time.time() - start_time

        if _process_timeout_seconds is not None and total_elapsed >= _process_timeout_seconds:
            return _handle_internal_runtime_limit(process, script_path)
        
        if check_interval is not None and elapsed_since_check >= check_interval:
            # Return check-in request
            return {
                "status": "check_in_required",
                "elapsed_seconds": total_elapsed,
                "elapsed_display": _format_elapsed_time(total_elapsed),
                "file_path": str(script_path),
                "use_temp_file": _process_use_temp_file,
            }
        
        # Sleep briefly before next poll
        time.sleep(0.1)


def interrupt_running_execution(reason: Optional[str] = None) -> str:
    """Interrupt and terminate the currently running Python process and all its children.
    
    Called by the operator when LLM decides to interrupt execution.
    Uses process group to ensure all child processes (including MPI jobs) are terminated.
    Returns the partial output collected before termination.
    """
    global _running_process, _process_pgid, _process_start_time, _process_script_path
    
    if _running_process is None:
        return "Error: No running process to interrupt."
    
    process = _running_process
    pgid = _process_pgid
    script_path = _process_script_path
    
    # Terminate the entire process tree using psutil (kills all child processes including MPI jobs)
    _kill_process_and_children(process, pgid)
    
    result = _collect_execution_result(
        process,
        script_path,
        was_interrupted=True,
        interruption_reason=reason
    )
    _clear_execution_state(cleanup_temp_file=True)
    return result


def has_running_process() -> bool:
    """Check if there's a currently running Python process."""
    return _running_process is not None
