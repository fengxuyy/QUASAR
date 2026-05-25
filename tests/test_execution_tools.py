import pytest
import sys
import os
import signal
import time
from collections import deque
from unittest.mock import patch, MagicMock
from src.tools.execution import execute_python
from src.tools.execution import _find_processes_in_group


def test_execute_python_code_snippet(mock_workspace):
    """Test executing a simple code snippet."""
    code = "print('Hello Execution')"
    result = execute_python.invoke({"code": code, "check_in_after": 5})
    assert "**Execution Result:**" in result
    assert "Code executed successfully" in result
    assert "Hello Execution" in result

def test_execute_python_file(mock_workspace):
    """Test executing a python file."""
    script_path = mock_workspace / "myscript.py"
    script_path.write_text("print('File Execution')")
    
    result = execute_python.invoke({"file_path": "myscript.py", "check_in_after": 5})
    assert "**Execution Result:**" in result
    assert "Code executed successfully" in result
    assert "File Execution" in result

def test_execute_python_error(mock_workspace):
    """Test executing code with syntax error."""
    code = "print('Unclosed string"
    result = execute_python.invoke({"code": code, "check_in_after": 5})
    assert "**Execution Result:**" in result
    assert "failed" in result
    assert "SyntaxError" in result

def test_execute_python_create_file_and_run(mock_workspace):
    """Test providing both code and file_path."""
    code = "print('Created and Ran')"
    filename = "new_script.py"
    result = execute_python.invoke({"file_path": filename, "code": code, "check_in_after": 5})
    
    assert "**Execution Result:**" in result
    assert "Created and Ran" in result
    assert (mock_workspace / filename).exists()

def test_execute_python_environment_variables(mock_workspace):
    """Test that environment variables (like OMP_NUM_THREADS) are passed correctly."""
    # We create a script that prints the env var
    code = "import os; print(f'THREADS={os.environ.get(\"OMP_NUM_THREADS\")}')"
    
    # Test default
    result = execute_python.invoke({"code": code, "check_in_after": 5})
    assert "THREADS=1" in result # Default is 1
    
    # Test explicit
    result_explicit = execute_python.invoke({"code": code, "check_in_after": 5, "omp_num_threads": 4})
    assert "THREADS=4" in result_explicit

def test_execute_outside_workspace(mock_workspace):
    """Test that execution prevents running files outside workspace."""
    # This is tricky since _resolve_path might resolve it, but we want to fail the security check
    # inside execute_python which checks if resolved path starts with WORKSPACE_DIR.
    # We rely on relative paths like ../ that point outside.
    
    # Try to execute a hypothetical file outside
    filename = "../outside_script.py"
    result = execute_python.invoke({"file_path": filename, "code": "print('bad')", "check_in_after": 5})
    assert "Error" in result
    assert "outside workspace" in result

@patch('subprocess.Popen')
def test_simulation_check_in_handling(mock_popen, mock_workspace):
    """Test that long-running processes return control at the agent-selected check-in."""
    # This mock is complex because execute_python polls process.poll()
    
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    mock_process.pid = 12345
    
    # Scenario: Process runs forever. 
    # execute_python has a loop that checks:
    # 1. process.poll() -> None (running)
    # 2. time.time() - start_time >= agent-selected check-in delay
    
    # We want to force it to hit the explicit check-in delay.
    with patch('os.getpgid', return_value=12345): # Mock pgid to avoid ProcessLookupError

        # Mock communicate to avoid ValueError. return (stdout, stderr)
        mock_process.communicate.return_value = ("", "")

        # IMPORTANT: process.poll() must return None to simulate running process
        mock_process.poll.return_value = None

        # We can test that it returns the check-in dict
        result = execute_python.invoke({
            "check_in_after": 0.001,
            "code": "import time; time.sleep(10)",
        })

        # Verify it returned a check-in request, not complete success
        assert isinstance(result, dict)
        assert result.get('status') == "check_in_required"

def test_execute_python_schema_does_not_expose_timeout():
    """Execution control should be check-in based, not hard-timeout based."""
    assert "timeout" not in execute_python.args


@patch('subprocess.Popen')
def test_execute_python_has_no_hard_timeout(mock_popen, mock_workspace):
    """Elapsed wall time alone should not terminate a running execution."""
    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    mock_process.pid = 12345
    mock_process.poll.side_effect = [None, 0]
    mock_process.communicate.return_value = ("completed", "")
    mock_process.returncode = 0

    with patch('os.getpgid', return_value=12345), \
         patch('src.tools.execution._kill_process_and_children') as mock_kill, \
         patch('src.tools.execution._find_processes_in_group', return_value=[]), \
         patch('src.tools.execution.time.time', side_effect=[0.0, 999999.0]), \
         patch('time.sleep'):

        result = execute_python.invoke({"code": "print('done')", "check_in_after": 2000000})

    assert "Code executed successfully" in result
    assert "completed" in result
    mock_kill.assert_not_called()


def test_execute_python_rejects_non_positive_check_in_after(mock_workspace):
    """Agent-selected check-in delays must be positive when provided."""
    result = execute_python.func(code="print('hi')", check_in_after=0)
    assert result == "Error: 'check_in_after' must be a positive number of minutes."


def test_execute_python_requires_check_in_after_in_schema():
    """The public execution tool should require an agent-selected check-in interval."""
    schema = execute_python.args_schema.model_json_schema()
    assert "check_in_after" in schema.get("required", [])


@patch('subprocess.Popen')
def test_check_interval_env_does_not_schedule_check_in(mock_popen, mock_workspace, monkeypatch):
    """The retired CHECK_INTERVAL setting should no longer drive check-ins."""
    monkeypatch.setenv("CHECK_INTERVAL", "0.0001")

    mock_process = MagicMock()
    mock_popen.return_value = mock_process
    mock_process.pid = 12345
    mock_process.poll.side_effect = [None, 0]
    mock_process.communicate.return_value = ("done", "")
    mock_process.returncode = 0

    with patch('os.getpgid', return_value=12345), \
         patch('src.tools.execution._find_processes_in_group', return_value=[]), \
         patch('time.sleep'):
        result = execute_python.invoke({"code": "print('done')", "check_in_after": 5})

    assert isinstance(result, str)
    assert "Code executed successfully" in result
    assert "done" in result


def test_execute_python_with_state_preserved_restores_state_after_success(mock_workspace):
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

    try:
        result = execution_module.execute_python_with_state_preserved(
            code="import time; time.sleep(1.3); print('done')",
            max_runtime_minutes=5.0,
        )

        assert isinstance(result, str)
        assert "done" in result
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


def test_execute_python_with_state_preserved_passes_arguments_without_check_in_delay(mock_workspace):
    """The preserved-state wrapper should call execute_python without scheduling nested check-ins."""
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

    def fake_execute_python(*, code, omp_num_threads, max_runtime_minutes):
        assert code == "print('x')"
        assert omp_num_threads == 1
        assert max_runtime_minutes == 5.0
        return "wrapped result"

    try:
        with patch('src.tools.execution._execute_python_impl', side_effect=fake_execute_python) as mock_exec:
            result = execution_module.execute_python_with_state_preserved(
                code="print('x')",
                max_runtime_minutes=5.0,
            )

        assert result == "wrapped result"
        mock_exec.assert_called_once_with(code="print('x')", omp_num_threads=1, max_runtime_minutes=5.0)
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


def test_execute_python_with_state_preserved_restores_state_after_exception(mock_workspace):
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

    try:
        with patch('src.tools.execution._execute_python_impl', side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                execution_module.execute_python_with_state_preserved(
                    code="print('x')",
                    max_runtime_minutes=5.0,
                )

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
        result = execute_python.invoke({"code": "raise SystemExit(1)", "check_in_after": 5})

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
    result = execute_python.invoke({"code": code, "check_in_after": 5})
    # Warnings are suppressed — no warning section and no raw code block
    assert "⚠ Warnings" not in result
    assert "beta feature" not in result
    assert "**Warnings / Logs:**" not in result


def test_format_stderr_traceback_block(mock_workspace):
    """An uncaught exception produces a ✗ Error section, not a raw code block."""
    code = "raise ValueError('something went wrong')"
    result = execute_python.invoke({"code": code, "check_in_after": 5})
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
    result = execute_python.invoke({"code": code, "check_in_after": 5})
    assert "⚠ Warnings" not in result
    assert "watch out" not in result
    assert "✗ Error:" in result
    assert "RuntimeError" in result
