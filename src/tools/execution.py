import os
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional, Union, Dict, Any

from langchain_core.tools import tool

from .base import WORKSPACE_DIR, truncate_content, get_all_files, format_file_list, PROTECTED_SYSTEM_FILES


# Global state for tracking running process during check-in
_running_process: Optional[subprocess.Popen] = None
_process_pgid: Optional[int] = None  # Process group ID for killing child processes
_process_start_time: Optional[float] = None
_process_script_path: Optional[Path] = None
_process_files_before: Optional[set] = None


def _get_check_interval() -> int:
    """Get check-in interval from environment variable.
    
    CHECK_INTERVAL is specified in minutes (matching the UI settings).
    Returns the interval in seconds.
    Default: 15 minutes = 900 seconds.
    """
    minutes = float(os.getenv("CHECK_INTERVAL", "15"))
    return int(minutes * 60)


def _format_elapsed_time(seconds: float) -> str:
    """Format elapsed time in a human-readable way."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def _collect_execution_result(
    process: subprocess.Popen,
    script_path: Path,
    files_before: set,
    was_interrupted: bool = False
) -> str:
    """Collect and format execution result from a completed/terminated process."""
    stdout, stderr = process.communicate()
    
    # Capture files after execution to detect changes
    files_after = get_all_files()
    new_files = sorted(list(files_after - files_before))
    deleted_files = sorted(list(files_before - files_after))
    
    # Build success/failure header
    if was_interrupted:
        header = "Code execution was interrupted by user"
    else:
        status = "successfully" if process.returncode == 0 else "failed"
        header = f"Code executed {status} (exit code: {process.returncode})"
    
    md_result = f"**Execution Result:**\n\n> {header}\n"
    
    if stdout:
        truncated_stdout = truncate_content(stdout)
        md_result += f"\n**Output:**\n\n```\n{truncated_stdout}\n```\n"
        
    if stderr:
        truncated_stderr = truncate_content(stderr)
        stderr_header = "**Error Output:**" if process.returncode != 0 else "**Warnings / Logs:**"
        md_result += f"\n{stderr_header}\n\n```\n{truncated_stderr}\n```\n"
    
    # Add file changes information
    file_changes_log = ""
    if new_files:
        formatted_files = format_file_list(new_files)
        file_changes_log += f"\n**Files Created:**\n{formatted_files}\n"
    
    if deleted_files:
        formatted_deleted = format_file_list(deleted_files)
        file_changes_log += f"\n**Files Deleted:**\n{formatted_deleted}\n"
    
    if not file_changes_log:
        file_changes_log = "\n**File System:**\nNo changes detected.\n"
    
    md_result += file_changes_log
    
    return md_result.strip()


@tool
def execute_python(
    file_path: Optional[str] = None,
    code: Optional[str] = None,
    omp_num_threads: int = 1
) -> Union[str, Dict[str, Any]]:
    """Execute Python code directly or from a file.
    
    The code will have access to ASE, pymatgen, MACE, RASPA3, Quantum ESPRESSO, and standard libraries.
    
    For long-running scripts, the LLM will be prompted periodically to decide whether to continue
    or interrupt the execution. The check-in interval is controlled by the CHECK_INTERVAL 
    environment variable (default: 900 seconds = 15 minutes).
    
    Args:
        file_path: Optional path to the Python file. If provided with `code`, the code will be written 
                   to this file before execution. If provided without `code`, the existing file will be executed.
        code: Optional Python code to execute directly. If provided without `file_path`, a temporary file 
              will be used (recommended only for simple, quick scripts). If provided with `file_path`, 
              the code will be written to that file before execution.
        omp_num_threads: Number of OpenMP threads per MPI process (default: 1). Set this when running 
                        hybrid MPI+OpenMP codes. Constraint: Concurrent Jobs x MPI_ranks x OMP_NUM_THREADS <= Total Physical cores
    
    Returns:
        Execution results including stdout, stderr, and return code. For long-running scripts,
        may return a check-in request dict that prompts the LLM to decide whether to continue.
    
    Examples:
        - execute_python(file_path="script.py") - Execute existing file
        - execute_python(code="print('hello')", file_path="hello.py") - Write code to file then execute
        - execute_python(code="print(2+2)") - Execute simple code via temp file (for quick tests only)
    """
    global _running_process, _process_start_time, _process_script_path, _process_files_before
    
    # Validate arguments
    if file_path is None and code is None:
        return "Error: Either 'file_path' or 'code' must be provided."
    
    # Get check-in interval
    check_interval = _get_check_interval()
    
    # Capture files before execution to track changes
    files_before = get_all_files()
    
    use_temp_file = False
    
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
                return f"Error: File '{file_path}' does not exist. Create the file using write_file first, or provide the 'code' argument."

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
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            cwd=str(WORKSPACE_DIR), 
            env=env,
            start_new_session=True
        )
        
        # Get the process group ID for later cleanup
        pgid = os.getpgid(process.pid)
        
        start_time = time.time()
        
        # Store global state for potential resume
        _running_process = process
        _process_pgid = pgid
        _process_start_time = start_time
        _process_script_path = script_path
        _process_files_before = files_before
        
        # Poll until process completes or check-in interval reached
        while True:
            # Check if process has completed
            poll_result = process.poll()
            if poll_result is not None:
                # Process completed - clean up global state
                _running_process = None
                _process_pgid = None
                _process_start_time = None
                _process_script_path = None
                _process_files_before = None
                
                # Clean up temp file if used
                if use_temp_file and script_path.exists():
                    try:
                        script_path.unlink()
                    except Exception:
                        pass
                
                return _collect_execution_result(process, script_path, files_before)
            
            # Check if we've reached the check-in interval
            elapsed = time.time() - start_time
            if elapsed >= check_interval:
                # Return check-in request - operator will handle prompting LLM
                return {
                    "status": "check_in_required",
                    "elapsed_seconds": elapsed,
                    "elapsed_display": _format_elapsed_time(elapsed),
                    "file_path": str(script_path),
                    "use_temp_file": use_temp_file
                }
            
            # Sleep briefly before next poll (100ms)
            time.sleep(0.1)
            
    except subprocess.TimeoutExpired as e:
        # Special handling for subprocess timeout - kill all child processes and return to LLM
        # This catches when user's script has an uncaught subprocess.wait(timeout=X) that expires
        
        # Try to kill all child processes spawned by the script
        if _process_pgid is not None:
            try:
                os.killpg(_process_pgid, signal.SIGTERM)
                time.sleep(2)  # Give processes time to terminate
                try:
                    os.killpg(_process_pgid, signal.SIGKILL)  # Force kill any remaining
                except ProcessLookupError:
                    pass  # Already terminated
            except (ProcessLookupError, PermissionError):
                pass  # Process group already terminated
        
        # Collect any partial output
        result_msg = _collect_execution_result(
            _running_process, 
            _process_script_path, 
            _process_files_before,
            was_interrupted=False
        )
        
        # Clean up global state
        _running_process = None
        _process_pgid = None
        _process_start_time = None
        _process_script_path = None
        _process_files_before = None
        
        # Return helpful message with partial output
        timeout_info = f"\n\n**Subprocess Timeout:**\n\n> A subprocess in your script timed out after {e.timeout} seconds.\n> All child processes have been terminated.\n> You can:\n> - Increase the timeout value if the process needs more time\n> - Check the partial output below to diagnose issues\n> - Modify your approach if the process is stuck\n\n"
        
        return timeout_info + result_msg
    
    except Exception as e:
        # Clean up temp file on error too
        if use_temp_file and _process_script_path and _process_script_path.exists():
            try:
                _process_script_path.unlink()
            except Exception:
                pass
                
        # Clean up global state on error
        _running_process = None
        _process_pgid = None
        _process_start_time = None
        _process_script_path = None
        _process_files_before = None
        
        return f"**Execution Result:**\n\n> Error executing code: {str(e)}\n\n**Traceback:**\n\n```\n{traceback.format_exc()}```"


def resume_execution() -> Union[str, Dict[str, Any]]:
    """Resume monitoring a running Python process after check-in.
    
    This is called by the operator after LLM decides to continue execution.
    Returns the result when process completes, or another check-in request.
    """
    global _running_process, _process_pgid, _process_start_time, _process_script_path, _process_files_before
    
    if _running_process is None:
        return "Error: No running process to resume."
    
    process = _running_process
    start_time = _process_start_time
    script_path = _process_script_path
    files_before = _process_files_before
    
    check_interval = _get_check_interval()
    last_check_time = time.time()
    
    # Poll until process completes or next check-in interval reached
    while True:
        poll_result = process.poll()
        if poll_result is not None:
            # Process completed - clean up global state
            _running_process = None
            _process_pgid = None
            _process_start_time = None
            _process_script_path = None
            _process_files_before = None
            
            return _collect_execution_result(process, script_path, files_before)
        
        # Check if we've reached the next check-in interval
        elapsed_since_check = time.time() - last_check_time
        total_elapsed = time.time() - start_time
        
        if elapsed_since_check >= check_interval:
            # Return check-in request
            return {
                "status": "check_in_required",
                "elapsed_seconds": total_elapsed,
                "elapsed_display": _format_elapsed_time(total_elapsed),
                "file_path": str(script_path),
                "use_temp_file": False  # Temp files don't get resumed
            }
        
        # Sleep briefly before next poll
        time.sleep(0.1)


def interrupt_running_execution() -> str:
    """Interrupt and terminate the currently running Python process and all its children.
    
    Called by the operator when LLM decides to interrupt execution.
    Uses process group to ensure all child processes (including MPI jobs) are terminated.
    Returns the partial output collected before termination.
    """
    global _running_process, _process_pgid, _process_start_time, _process_script_path, _process_files_before
    
    if _running_process is None:
        return "Error: No running process to interrupt."
    
    process = _running_process
    pgid = _process_pgid
    script_path = _process_script_path
    files_before = _process_files_before
    
    # Terminate the entire process group (kills all child processes including MPI jobs)
    try:
        if pgid is not None:
            # Send SIGTERM to entire process group
            os.killpg(pgid, signal.SIGTERM)
            # Give processes a moment to terminate gracefully
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if they don't terminate
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)
        else:
            # Fallback to single process termination
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    except (ProcessLookupError, PermissionError):
        # Process/group already terminated
        pass
    except Exception:
        pass
    
    # Clean up global state
    _running_process = None
    _process_pgid = None
    _process_start_time = None
    _process_script_path = None
    _process_files_before = None
    
    return _collect_execution_result(process, script_path, files_before, was_interrupted=True)


def has_running_process() -> bool:
    """Check if there's a currently running Python process."""
    return _running_process is not None
