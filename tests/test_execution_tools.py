import pytest
import sys
import os
import signal
import time
from collections import deque
from unittest.mock import patch, MagicMock
from src.tools.execution import execute_python
from src.tools.execution import _find_processes_in_group

DEFAULT_TIMEOUT_MINUTES = 60.0


def test_execute_python_code_snippet(mock_workspace):
    """Test executing a simple code snippet."""
    code = "print('Hello Execution')"
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": code})
    assert "**Execution Result:**" in result
    assert "Code executed successfully" in result
    assert "Hello Execution" in result

def test_execute_python_file(mock_workspace):
    """Test executing a python file."""
    script_path = mock_workspace / "myscript.py"
    script_path.write_text("print('File Execution')")
    
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "file_path": "myscript.py"})
    assert "**Execution Result:**" in result
    assert "Code executed successfully" in result
    assert "File Execution" in result

def test_execute_python_error(mock_workspace):
    """Test executing code with syntax error."""
    code = "print('Unclosed string"
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": code})
    assert "**Execution Result:**" in result
    assert "failed" in result
    assert "SyntaxError" in result

def test_execute_python_create_file_and_run(mock_workspace):
    """Test providing both code and file_path."""
    code = "print('Created and Ran')"
    filename = "new_script.py"
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "file_path": filename, "code": code})
    
    assert "**Execution Result:**" in result
    assert "Created and Ran" in result
    assert (mock_workspace / filename).exists()

def test_execute_python_environment_variables(mock_workspace):
    """Test that environment variables (like OMP_NUM_THREADS) are passed correctly."""
    # We create a script that prints the env var
    code = "import os; print(f'THREADS={os.environ.get(\"OMP_NUM_THREADS\")}')"
    
    # Test default
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": code})
    assert "THREADS=1" in result # Default is 1
    
    # Test explicit
    result_explicit = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": code, "omp_num_threads": 4})
    assert "THREADS=4" in result_explicit

def test_execute_outside_workspace(mock_workspace):
    """Test that execution prevents running files outside workspace."""
    # This is tricky since _resolve_path might resolve it, but we want to fail the security check
    # inside execute_python which checks if resolved path starts with WORKSPACE_DIR.
    # We rely on relative paths like ../ that point outside.
    
    # Try to execute a hypothetical file outside
    filename = "../outside_script.py"
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "file_path": filename, "code": "print('bad')"})
    assert "Error" in result
    assert "outside workspace" in result

@patch('subprocess.Popen')
def test_simulation_timeout_handling(mock_popen, mock_workspace):
    """Test that long running processes are handled/timed out appropriately."""
    # This mock is complex because execute_python polls process.poll()
    
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    mock_process.pid = 12345
    
    # Scenario: Process runs forever. 
    # execute_python has a loop that checks:
    # 1. process.poll() -> None (running)
    # 2. time.time() - start_time >= check_interval
    
    # We want to force it to hit the check interval (default 3600s, but can be mocked).
    # Easier: Mock _get_check_interval to return very small value.
    
    # Easier: Mock _get_check_interval to return very small value.
    
    with patch('src.tools.execution._get_check_interval', return_value=0.1):
        with patch('os.getpgid', return_value=12345): # Mock pgid to avoid ProcessLookupError
            
            # Mock communicate to avoid ValueError. return (stdout, stderr)
            mock_process.communicate.return_value = ("", "")
            
            # IMPORTANT: process.poll() must return None to simulate running process
            mock_process.poll.return_value = None
            
            # We need process.poll() to return None (running) initially, 
            # but execution loop needs to hit the interval logic.
            
            # We can test that it returns the check-in dict
            result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": "import time; time.sleep(10)"})
            
            # Verify it returned a check-in request, not complete success
            assert isinstance(result, dict)
            assert result.get('status') == "check_in_required"

@patch('subprocess.Popen')
def test_execute_python_test_timeout(mock_popen, mock_workspace):
    """Test that timeout terminates long-running executions."""
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    mock_process.pid = 12345
    mock_process.poll.return_value = None
    mock_process.communicate.return_value = ("partial output", "")
    mock_process.returncode = -9

    time_calls = {"count": 0}

    def fake_time():
        time_calls["count"] += 1
        return 0.2 * time_calls["count"]

    with patch('os.getpgid', return_value=12345), \
         patch('src.tools.execution._get_check_interval', return_value=999), \
         patch('src.tools.execution._kill_process_and_children') as mock_kill, \
         patch('src.tools.execution.time.time', side_effect=fake_time):

        result = execute_python.invoke({"code": "import time; time.sleep(10)", "timeout": 0.001})

    assert "**Execution Timeout:**" in result
    assert mock_kill.called


def test_execute_python_rejects_non_positive_timeout(mock_workspace):
    """Timeout must be a positive number when it is provided."""
    result = execute_python.func(code="print('hi')", timeout=0)
    assert result == "Error: 'timeout' must be a positive number of minutes."


def test_execute_python_with_state_preserved_restores_env_and_state_after_success(mock_workspace, monkeypatch):
    """The preserved-state wrapper should suppress nested check-ins and restore live state."""
    import src.tools.execution as execution_module

    original_capture = execution_module.OutputCaptureState(
        stdout_chunks=deque(["live stdout\n"]),
        stderr_chunks=deque(["live stderr\n"]),
        stdout_size=len("live stdout\n"),
        stderr_size=len("live stderr\n"),
    )
    sentinel_process = MagicMock()

    execution_module._running_process = sentinel_process
    execution_module._process_pgid = 4242
    execution_module._process_start_time = 123.0
    execution_module._process_script_path = mock_workspace / "live.py"
    execution_module._process_timeout_seconds = 3600.0
    execution_module._process_timeout_minutes = 60.0
    execution_module._process_use_temp_file = False
    execution_module._process_output_capture = original_capture

    monkeypatch.setenv("CHECK_INTERVAL", "0.02")

    try:
        result = execution_module.execute_python_with_state_preserved(
            timeout=5.0,
            code="import time; time.sleep(1.3); print('done')",
        )

        assert isinstance(result, str)
        assert "done" in result
        assert os.environ["CHECK_INTERVAL"] == "0.02"
        assert execution_module._running_process is sentinel_process
        assert execution_module._process_pgid == 4242
        assert execution_module._process_start_time == 123.0
        assert execution_module._process_script_path == mock_workspace / "live.py"
        assert execution_module._process_timeout_seconds == 3600.0
        assert execution_module._process_timeout_minutes == 60.0
        assert execution_module._process_use_temp_file is False
        assert execution_module._process_output_capture is original_capture
        assert list(original_capture.stdout_chunks) == ["live stdout\n"]
        assert list(original_capture.stderr_chunks) == ["live stderr\n"]
    finally:
        execution_module._running_process = None
        execution_module._process_pgid = None
        execution_module._process_start_time = None
        execution_module._process_script_path = None
        execution_module._process_timeout_seconds = None
        execution_module._process_timeout_minutes = None
        execution_module._process_use_temp_file = False
        execution_module._process_output_capture = None


def test_execute_python_with_state_preserved_keeps_check_interval_unset_when_absent(mock_workspace, monkeypatch):
    """The preserved-state wrapper should not leave CHECK_INTERVAL behind if it started unset."""
    import src.tools.execution as execution_module

    sentinel_process = MagicMock()
    execution_module._running_process = sentinel_process
    execution_module._process_pgid = 4242
    execution_module._process_start_time = 123.0
    execution_module._process_script_path = mock_workspace / "live.py"
    execution_module._process_timeout_seconds = 3600.0
    execution_module._process_timeout_minutes = 60.0
    execution_module._process_use_temp_file = False
    execution_module._process_output_capture = execution_module.OutputCaptureState()

    monkeypatch.delenv("CHECK_INTERVAL", raising=False)

    def fake_execute_python(*, timeout, code, omp_num_threads):
        assert "CHECK_INTERVAL" not in os.environ
        assert timeout == 5.0
        assert code == "print('x')"
        assert omp_num_threads == 1
        return "wrapped result"

    try:
        with patch('src.tools.execution.execute_python.func', side_effect=fake_execute_python) as mock_exec:
            result = execution_module.execute_python_with_state_preserved(
                timeout=5.0,
                code="print('x')",
            )

        assert result == "wrapped result"
        assert "CHECK_INTERVAL" not in os.environ
        mock_exec.assert_called_once_with(timeout=5.0, code="print('x')", omp_num_threads=1)
        assert execution_module._running_process is sentinel_process
        assert execution_module._process_pgid == 4242
        assert execution_module._process_start_time == 123.0
        assert execution_module._process_script_path == mock_workspace / "live.py"
        assert execution_module._process_timeout_seconds == 3600.0
        assert execution_module._process_timeout_minutes == 60.0
        assert execution_module._process_use_temp_file is False
    finally:
        execution_module._running_process = None
        execution_module._process_pgid = None
        execution_module._process_start_time = None
        execution_module._process_script_path = None
        execution_module._process_timeout_seconds = None
        execution_module._process_timeout_minutes = None
        execution_module._process_use_temp_file = False
        execution_module._process_output_capture = None


def test_execute_python_with_state_preserved_restores_env_and_state_after_exception(mock_workspace, monkeypatch):
    """The preserved-state wrapper should restore live state even if execute_python raises."""
    import src.tools.execution as execution_module

    original_capture = execution_module.OutputCaptureState(
        stdout_chunks=deque(["live stdout\n"]),
        stdout_size=len("live stdout\n"),
    )
    sentinel_process = MagicMock()

    execution_module._running_process = sentinel_process
    execution_module._process_pgid = 4242
    execution_module._process_start_time = 123.0
    execution_module._process_script_path = mock_workspace / "live.py"
    execution_module._process_timeout_seconds = 3600.0
    execution_module._process_timeout_minutes = 60.0
    execution_module._process_use_temp_file = False
    execution_module._process_output_capture = original_capture

    monkeypatch.setenv("CHECK_INTERVAL", "15")

    try:
        with patch('src.tools.execution.execute_python.func', side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                execution_module.execute_python_with_state_preserved(
                    timeout=5.0,
                    code="print('x')",
                )

        assert os.environ["CHECK_INTERVAL"] == "15"
        assert execution_module._running_process is sentinel_process
        assert execution_module._process_pgid == 4242
        assert execution_module._process_start_time == 123.0
        assert execution_module._process_script_path == mock_workspace / "live.py"
        assert execution_module._process_timeout_seconds == 3600.0
        assert execution_module._process_timeout_minutes == 60.0
        assert execution_module._process_use_temp_file is False
        assert execution_module._process_output_capture is original_capture
        assert list(original_capture.stdout_chunks) == ["live stdout\n"]
    finally:
        execution_module._running_process = None
        execution_module._process_pgid = None
        execution_module._process_start_time = None
        execution_module._process_script_path = None
        execution_module._process_timeout_seconds = None
        execution_module._process_timeout_minutes = None
        execution_module._process_use_temp_file = False
        execution_module._process_output_capture = None


def test_resume_execution_enforces_timeout(mock_workspace):
    """resume_execution should enforce the configured timeout across check-ins."""
    from src.tools.execution import resume_execution
    import src.tools.execution as execution_module

    mock_process = MagicMock()
    mock_process.pid = 54321
    mock_process.poll.return_value = None
    mock_process.communicate.return_value = ("partial output", "")
    mock_process.returncode = -9

    execution_module._running_process = mock_process
    execution_module._process_pgid = 54321
    execution_module._process_start_time = 0.0
    execution_module._process_script_path = mock_workspace / "long_run.py"
    execution_module._process_timeout_seconds = 60.0
    execution_module._process_timeout_minutes = 1.0
    execution_module._process_use_temp_file = False

    try:
        with patch('src.tools.execution._get_check_interval', return_value=999), \
             patch('src.tools.execution._kill_process_and_children') as mock_kill, \
             patch('src.tools.execution.time.time', return_value=61.0):
            result = resume_execution()

        assert "**Execution Timeout:**" in result
        assert mock_kill.called
        assert execution_module._running_process is None
        assert execution_module._process_timeout_seconds is None
        assert execution_module._process_timeout_minutes is None
    finally:
        execution_module._running_process = None
        execution_module._process_pgid = None
        execution_module._process_start_time = None
        execution_module._process_script_path = None
        execution_module._process_timeout_seconds = None
        execution_module._process_timeout_minutes = None
        execution_module._process_use_temp_file = False

@patch('subprocess.Popen')
def test_execute_python_kills_children_on_error(mock_popen, mock_workspace):
    """Test that failed executions trigger child process cleanup."""
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    mock_process.pid = 12345
    mock_process.poll.return_value = 1
    mock_process.returncode = 1
    mock_process.communicate.return_value = ("", "error")

    with patch('os.getpgid', return_value=12345), \
         patch('src.tools.execution._find_processes_in_group', return_value=[MagicMock()]), \
         patch('src.tools.execution._kill_process_and_children') as mock_kill:
        result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": "raise SystemExit(1)"})

    assert "**Execution Result:**" in result
    assert mock_kill.called


@patch('src.tools.execution.psutil.process_iter', side_effect=PermissionError("blocked"))
def test_find_processes_in_group_handles_process_iter_permission_errors(mock_process_iter):
    """Permission errors while enumerating processes should not break execution cleanup."""
    assert _find_processes_in_group(12345) == []


# ============================================================
# _format_stderr unit tests
# ============================================================
from src.tools.execution import _format_stderr


def test_format_stderr_suppresses_noise():
    """Stderr consisting entirely of tokenizer/HF noise is omitted."""
    noise = (
        "huggingface/tokenizers: The current process just forked ...\n"
        "To avoid this warning disable Parallelism by setting TOKENIZERS_PARALLELISM=false\n"
    )
    result = _format_stderr(noise, is_failure=False)
    assert result == ""


def test_format_stderr_warning_block(mock_workspace):
    """Python warnings are suppressed — no stderr section should appear."""
    code = (
        "import warnings\n"
        "warnings.warn('beta feature', UserWarning, stacklevel=1)\n"
    )
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": code})
    # Warnings are suppressed — no warning section and no raw code block
    assert "⚠ Warnings" not in result
    assert "beta feature" not in result
    assert "**Warnings / Logs:**" not in result


def test_format_stderr_traceback_block(mock_workspace):
    """An uncaught exception produces a ✗ Error section, not a raw code block."""
    code = "raise ValueError('something went wrong')"
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": code})
    assert "✗ Error:" in result
    assert "ValueError" in result
    assert "something went wrong" in result
    # Should not have the old raw block header
    assert "**Error Output:**" not in result


def test_format_stderr_mixed_warning_and_traceback(mock_workspace):
    """A warning followed by a traceback: warning is suppressed, error is shown."""
    code = (
        "import warnings\n"
        "warnings.warn('watch out', DeprecationWarning)\n"
        "raise RuntimeError('boom')\n"
    )
    result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": code})
    assert "⚠ Warnings" not in result
    assert "watch out" not in result
    assert "✗ Error:" in result
    assert "RuntimeError" in result
