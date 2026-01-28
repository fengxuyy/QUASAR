import pytest
import sys
import os
import signal
import time
from unittest.mock import patch, MagicMock
from src.tools.execution import execute_python

def test_execute_python_code_snippet(mock_workspace):
    """Test executing a simple code snippet."""
    code = "print('Hello Execution')"
    result = execute_python.invoke({"code": code})
    assert "**Execution Result:**" in result
    assert "Code executed successfully" in result
    assert "Hello Execution" in result

def test_execute_python_file(mock_workspace):
    """Test executing a python file."""
    script_path = mock_workspace / "myscript.py"
    script_path.write_text("print('File Execution')")
    
    result = execute_python.invoke({"file_path": "myscript.py"})
    assert "**Execution Result:**" in result
    assert "Code executed successfully" in result
    assert "File Execution" in result

def test_execute_python_error(mock_workspace):
    """Test executing code with syntax error."""
    code = "print('Unclosed string"
    result = execute_python.invoke({"code": code})
    assert "**Execution Result:**" in result
    assert "failed" in result
    assert "SyntaxError" in result

def test_execute_python_create_file_and_run(mock_workspace):
    """Test providing both code and file_path."""
    code = "print('Created and Ran')"
    filename = "new_script.py"
    result = execute_python.invoke({"file_path": filename, "code": code})
    
    assert "**Execution Result:**" in result
    assert "Created and Ran" in result
    assert (mock_workspace / filename).exists()

def test_execute_python_environment_variables(mock_workspace):
    """Test that environment variables (like OMP_NUM_THREADS) are passed correctly."""
    # We create a script that prints the env var
    code = "import os; print(f'THREADS={os.environ.get(\"OMP_NUM_THREADS\")}')"
    
    # Test default
    result = execute_python.invoke({"code": code})
    assert "THREADS=1" in result # Default is 1
    
    # Test explicit
    result_explicit = execute_python.invoke({"code": code, "omp_num_threads": 4})
    assert "THREADS=4" in result_explicit

def test_execute_outside_workspace(mock_workspace):
    """Test that execution prevents running files outside workspace."""
    # This is tricky since _resolve_path might resolve it, but we want to fail the security check
    # inside execute_python which checks if resolved path starts with WORKSPACE_DIR.
    # We rely on relative paths like ../ that point outside.
    
    # Try to execute a hypothetical file outside
    filename = "../outside_script.py"
    result = execute_python.invoke({"file_path": filename, "code": "print('bad')"})
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
            result = execute_python.invoke({"code": "import time; time.sleep(10)"})
            
            # Verify it returned a check-in request, not complete success
            assert isinstance(result, dict)
            assert result.get('status') == "check_in_required"

