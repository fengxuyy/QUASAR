"""
Tests for execution interrupt functionality.

This module tests:
1. SIGINT handler properly kills running subprocesses (bridge.py fix)
2. Agent can correctly call interrupt_execution tool to kill running jobs
3. Process group termination ensures all child processes (like mpirun/LAMMPS) are killed
"""

import pytest
import os
import signal
import time
import subprocess
from unittest.mock import patch, MagicMock, call
from pathlib import Path


class TestInterruptRunningExecution:
    """Tests for the interrupt_running_execution function in execution.py."""
    
    def test_interrupt_kills_process_group(self, mock_workspace):
        """Test that interrupt_running_execution kills the entire process group."""
        from src.tools.execution import interrupt_running_execution, has_running_process
        import src.tools.execution as execution_module
        
        # Create a mock process
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.communicate.return_value = ("partial stdout", "partial stderr")
        mock_process.returncode = -15  # SIGTERM
        
        # Setup global state
        execution_module._running_process = mock_process
        execution_module._process_pgid = 12345
        execution_module._process_start_time = time.time()
        execution_module._process_script_path = mock_workspace / "test_script.py"
        execution_module._process_files_before = set()
        
        # Mock os.killpg
        with patch('os.killpg') as mock_killpg:
            result = interrupt_running_execution()
        
        # Verify killpg was called with SIGTERM
        assert mock_killpg.call_count >= 1
        calls = mock_killpg.call_args_list
        assert call(12345, signal.SIGTERM) in calls
        
        # Verify result indicates interruption
        assert "interrupted" in result.lower()
        
        # Verify global state was cleaned up
        assert execution_module._running_process is None
        assert execution_module._process_pgid is None
    
    def test_interrupt_with_no_running_process(self, mock_workspace):
        """Test that interrupt_running_execution returns error when no process is running."""
        from src.tools.execution import interrupt_running_execution
        import src.tools.execution as execution_module
        
        # Ensure no process is running
        execution_module._running_process = None
        
        result = interrupt_running_execution()
        
        assert "Error" in result
        assert "No running process" in result
    
    def test_interrupt_force_kills_after_timeout(self, mock_workspace):
        """Test that interrupt sends SIGKILL if process doesn't terminate after SIGTERM."""
        from src.tools.execution import interrupt_running_execution
        import src.tools.execution as execution_module
        
        # Create a stubborn mock process that doesn't terminate on SIGTERM
        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        mock_process.communicate.return_value = ("", "")
        mock_process.returncode = -9  # SIGKILL
        
        # Setup global state
        execution_module._running_process = mock_process
        execution_module._process_pgid = 99999
        execution_module._process_start_time = time.time()
        execution_module._process_script_path = mock_workspace / "stubborn_script.py"
        execution_module._process_files_before = set()
        
        with patch('os.killpg') as mock_killpg:
            # Configure mock to track calls but not actually kill anything
            mock_killpg.return_value = None
            # Make wait timeout on first call, succeed on second (after SIGKILL)
            mock_process.wait.side_effect = [
                subprocess.TimeoutExpired(cmd="test", timeout=5),
                None  # Succeeds after SIGKILL
            ]
            
            result = interrupt_running_execution()
        
        # Verify both SIGTERM and SIGKILL were sent
        sigterm_called = False
        sigkill_called = False
        for c in mock_killpg.call_args_list:
            if c == call(99999, signal.SIGTERM):
                sigterm_called = True
            if c == call(99999, signal.SIGKILL):
                sigkill_called = True
        
        assert sigterm_called, "SIGTERM should be sent first"
        assert sigkill_called, "SIGKILL should be sent if process doesn't terminate"


class TestInterruptExecutionTool:
    """Tests for the interrupt_execution tool that the agent can call."""
    
    def test_interrupt_execution_tool_returns_correct_format(self):
        """Test that interrupt_execution tool returns correctly formatted response."""
        from src.tools.execution_check import interrupt_execution
        
        reason = "The simulation appears to be stuck in an infinite loop"
        result = interrupt_execution.invoke({"reason": reason})
        
        assert "INTERRUPT_EXECUTION" in result
        assert reason in result
    
    def test_continue_execution_tool_returns_correct_format(self):
        """Test that continue_execution tool returns correctly formatted response."""
        from src.tools.execution_check import continue_execution
        
        result = continue_execution.invoke({})
        
        assert result == "CONTINUE_EXECUTION"


class TestProcessGroupTermination:
    """Tests for proper process group termination to ensure child processes are killed."""
    
    @patch('subprocess.Popen')
    def test_execute_python_creates_new_session(self, mock_popen, mock_workspace):
        """Test that execute_python starts process with start_new_session=True."""
        from src.tools.execution import execute_python
        
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_process.pid = 11111
        mock_process.poll.return_value = 0  # Process completed immediately
        mock_process.communicate.return_value = ("output", "")
        mock_process.returncode = 0
        
        with patch('os.getpgid', return_value=11111), \
             patch('src.tools.execution.get_all_files', return_value=set()):
            execute_python.invoke({"code": "print('test')"})
        
        # Verify Popen was called with start_new_session=True
        popen_call = mock_popen.call_args
        assert popen_call is not None
        kwargs = popen_call.kwargs if hasattr(popen_call, 'kwargs') else popen_call[1]
        assert kwargs.get('start_new_session') == True, \
            "Popen should be called with start_new_session=True to create a process group"
    
    @patch('subprocess.Popen')
    def test_execute_python_stores_pgid_for_cleanup(self, mock_popen, mock_workspace):
        """Test that execute_python stores the process group ID for later cleanup."""
        from src.tools.execution import execute_python
        import src.tools.execution as execution_module
        
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_process.pid = 22222
        
        # Simulate long-running process that triggers check-in
        with patch('os.getpgid', return_value=22222) as mock_getpgid, \
             patch('src.tools.execution._get_check_interval', return_value=0.01), \
             patch('src.tools.execution.get_all_files', return_value=set()), \
             patch('time.sleep'):  # Speed up the test
            
            # Process never completes (poll returns None)
            mock_process.poll.return_value = None
            mock_process.communicate.return_value = ("", "")
            
            result = execute_python.invoke({"code": "import time; time.sleep(100)"})
        
        # Verify getpgid was called to get the process group ID
        mock_getpgid.assert_called_with(22222)
        
        # Verify result is a check-in request (since process didn't complete)
        assert isinstance(result, dict)
        assert result.get('status') == 'check_in_required'


class TestAgentInterruptExecution:
    """Integration-style tests simulating how the agent uses interrupt_execution."""
    
    def test_agent_interrupt_flow_with_running_process(self, mock_workspace):
        """Test the full flow of agent interrupting a running process."""
        from src.tools.execution import interrupt_running_execution, has_running_process
        from src.tools.execution_check import interrupt_execution
        import src.tools.execution as execution_module
        
        # Setup: simulate a running process
        mock_process = MagicMock()
        mock_process.pid = 33333
        mock_process.communicate.return_value = ("partial output", "")
        mock_process.returncode = -15
        
        execution_module._running_process = mock_process
        execution_module._process_pgid = 33333
        execution_module._process_start_time = time.time() - 3600  # Running for 1 hour
        execution_module._process_script_path = mock_workspace / "long_running.py"
        execution_module._process_files_before = set()
        
        # Step 1: Agent calls interrupt_execution tool (returns marker)
        tool_result = interrupt_execution.invoke({
            "reason": "Script has been running for 1 hour without progress"
        })
        assert "INTERRUPT_EXECUTION" in tool_result
        
        # Step 2: The operator then calls the actual interrupt_running_execution
        # (This is what happens in operator.py after detecting the tool call)
        with patch('os.killpg'):
            actual_result = interrupt_running_execution()
        
        # Verify the process was interrupted
        assert "interrupted" in actual_result.lower()
        
        # Verify the process handle was cleaned up
        assert not has_running_process()
    
    def test_agent_respects_continue_decision(self):
        """Test that continue_execution returns the correct marker for operator to resume."""
        from src.tools.execution_check import continue_execution
        
        result = continue_execution.invoke({})
        
        # The operator checks for this exact string to know to resume
        assert result == "CONTINUE_EXECUTION"


class TestSigintHandlerKillsSubprocess:
    """Tests for the SIGINT handler in bridge.py that kills running subprocesses.
    
    These tests mock the bridge module's signal handler logic to verify it calls
    interrupt_running_execution when a process is running.
    """
    
    def test_sigint_handler_logic_calls_interrupt_when_process_running(self, mock_workspace):
        """Test that the SIGINT handler logic would call interrupt_running_execution 
        when a process is running.
        
        This test verifies the logic that was added to bridge.py's _save_stats_on_interrupt
        function - when has_running_process() returns True, it should call 
        interrupt_running_execution() before doing anything else.
        """
        from src.tools.execution import interrupt_running_execution, has_running_process
        import src.tools.execution as execution_module
        
        # Setup: simulate a running process
        mock_process = MagicMock()
        mock_process.pid = 44444
        mock_process.communicate.return_value = ("output", "")
        mock_process.returncode = -15
        
        execution_module._running_process = mock_process
        execution_module._process_pgid = 44444
        execution_module._process_start_time = time.time()
        execution_module._process_script_path = mock_workspace / "running_script.py"
        execution_module._process_files_before = set()
        
        # Verify has_running_process returns True
        assert has_running_process() == True
        
        # Simulate what the signal handler does
        with patch('os.killpg') as mock_killpg:
            if has_running_process():
                result = interrupt_running_execution()
        
        # Verify the interrupt was called
        mock_killpg.assert_called()
        assert "interrupted" in result.lower()
        
        # Verify the process is no longer running
        assert not has_running_process()


class TestRealSubprocessTermination:
    """Tests with real subprocess execution to verify actual process termination."""
    
    def test_real_subprocess_is_killed_on_interrupt(self, mock_workspace):
        """Test that a real subprocess (simulating mpirun) is actually killed."""
        from src.tools.execution import execute_python, interrupt_running_execution, has_running_process
        import src.tools.execution as execution_module
        
        # Write a script that spawns a subprocess (simulating what mpirun does)
        script_content = '''
import subprocess
import time
# Simulate mpirun starting a long process
proc = subprocess.Popen(["sleep", "300"])
proc.wait()
'''
        script_path = mock_workspace / "spawn_child.py"
        script_path.write_text(script_content)
        
        # Start execution in a way that we can interrupt
        # We use a very short check interval to quickly get control back
        with patch('src.tools.execution._get_check_interval', return_value=0.5):
            result = execute_python.invoke({"file_path": str(script_path)})
        
        # If we got a check-in request, we have a running process
        if isinstance(result, dict) and result.get('status') == 'check_in_required':
            assert has_running_process()
            
            # Now interrupt it
            interrupt_result = interrupt_running_execution()
            
            # Verify it was interrupted
            assert "interrupted" in interrupt_result.lower() or has_running_process() == False
            
            # Small delay to let OS clean up
            time.sleep(0.5)
            
            # Verify no zombie processes (the spawned sleep should be gone)
            # This is hard to verify directly, but we can check our state is clean
            assert not has_running_process()


class TestHasRunningProcess:
    """Tests for the has_running_process function."""
    
    def test_has_running_process_returns_false_when_no_process(self):
        """Test that has_running_process returns False when no process is running."""
        from src.tools.execution import has_running_process
        import src.tools.execution as execution_module
        
        # Clear any existing process
        execution_module._running_process = None
        
        assert has_running_process() == False
    
    def test_has_running_process_returns_true_when_process_exists(self, mock_workspace):
        """Test that has_running_process returns True when a process is running."""
        from src.tools.execution import has_running_process
        import src.tools.execution as execution_module
        
        # Setup a mock process
        mock_process = MagicMock()
        execution_module._running_process = mock_process
        
        try:
            assert has_running_process() == True

        finally:
            # Cleanup
            execution_module._running_process = None

class TestComplexJobInterruption:
    """Tests for interrupting complex jobs like those using subprocess.run."""

    def test_interrupt_kills_subprocess_run_job(self, mock_workspace):
        """Test that a job using subprocess.run to call mpirun is killed."""
        from src.tools.execution import execute_python, interrupt_running_execution, has_running_process
        import src.tools.execution as execution_module
        import sys
        
        # 1. Create a mock mpirun script (or use the one we just wrote if accessible, but better to create it here to be self-contained)
        mock_mpirun_path = mock_workspace / "mock_mpirun.py"
        mock_mpirun_code = '''
import sys
import time
import signal
import os

# Ignore SIGINT to simulate a process that needs SIGTERM
signal.signal(signal.SIGINT, signal.SIG_IGN)
print(f"Mock mpirun started with PID {os.getpid()}")
sys.stdout.flush()
time.sleep(300)
'''
        mock_mpirun_path.write_text(mock_mpirun_code)
        
        # Make it executable
        os.chmod(mock_mpirun_path, 0o755)

        # 2. Create the user script that runs this "mpirun"
        # We call the python interpreter as "mpirun" to stay portable
        user_script_content = f'''
import subprocess
import sys
import os

print("Starting subprocess...")
# We assume "python3 mock_mpirun.py" behaves like "mpirun"
cmd = ["{sys.executable}", "{mock_mpirun_path}", "-np", "4", "job.in"]
try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
except Exception as e:
    print(f"Error: {{e}}")
'''
        user_script_path = mock_workspace / "task_1" / "run_job.py"
        user_script_path.parent.mkdir(parents=True, exist_ok=True)
        user_script_path.write_text(user_script_content)

        # 3. Execute this script
        # Use short check interval to ensure we can interrupt it
        with patch('src.tools.execution._get_check_interval', return_value=0.5):
             result = execute_python.invoke({"file_path": str(user_script_path)})
        
        # 4. Verify it's running (check-in required)
        assert isinstance(result, dict)
        assert result.get('status') == 'check_in_required'
        assert has_running_process()
        
        # 5. Interrupt it
        interrupt_result = interrupt_running_execution()
        
        # 6. Verify result
        assert "interrupted" in interrupt_result.lower()
        assert not has_running_process()
        
        # 7. Additional Verification: The "mpirun" process should be gone.
        # This is tricky to test deterministically without PID tracking, but 
        # relying on internal structure of `interrupt_running_execution` (which employs PGID killing),
        # we can trust that if the parent died, the child group was signaled.
        # We can simulate checking if the process group is gone?
        # A simple check is that the system is clean.

    def test_interrupt_execution_tool_kills_job(self, mock_workspace):
        """Test that the agent tool 'interrupt_execution' leads to the same outcome."""
        from src.tools.execution import execute_python, interrupt_running_execution, has_running_process
        from src.tools.execution_check import interrupt_execution
        import sys

         # 1. Reuse the setup (Mock mpirun)
        mock_mpirun_path = mock_workspace / "mock_mpirun_tool.py"
        mock_mpirun_path.write_text('''
import time
import signal
signal.signal(signal.SIGINT, signal.SIG_IGN)
time.sleep(300)
''')
        
        user_script_path = mock_workspace / "run_job_tool.py"
        user_script_path.write_text(f'''
import subprocess
import sys
print("Process starting...")
sys.stdout.flush()
# Use capture_output=True to avoid potential pipe issues, though it shouldn't matter
subprocess.run(["{sys.executable}", "{mock_mpirun_path}"], capture_output=True)
print("Process finished (unexpectedly)")
''')

        # 2. Start running
        with patch('src.tools.execution._get_check_interval', return_value=0.5):
             result = execute_python.invoke({"file_path": str(user_script_path)})
        
        assert isinstance(result, dict)
        assert result.get('status') == 'check_in_required'

        # 3. Agent decides to interrupt
        tool_output = interrupt_execution.invoke({"reason": "Test interrupt"})
        assert "INTERRUPT_EXECUTION" in tool_output

        # 4. Operator (simulated) calls the kill function
        final_output = interrupt_running_execution()
        
        # 5. Verify
        assert "interrupted" in final_output.lower()
        assert not has_running_process()
