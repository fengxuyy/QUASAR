"""
Rigorous tests for the get_resource_usage function and its integration
into the periodic check-in flow.

Tests cover:
1. get_resource_usage() with no pid (system-wide only)
2. get_resource_usage(pid) with real processes
3. Mocked psutil process trees (controlled per-process CPU/RSS values)
4. Edge cases: dead PIDs, AccessDenied, partial child failures, single process
5. GPU parsing: CUDA, ROCm, missing, timeout, malformed output
6. Integration: execute_python check-in dict, resume_execution check-in dict
7. Operator prompt injection of resource usage
8. Usage tracker hardware-change-on-resume (no stale notice when hardware unchanged)
9. Usage tracker elapsed-time exclusions for retry waits
10. Lazy wrapper for resource usage in execution
11. Usage report generation
"""

import json
import subprocess
import os
import signal
import sys
import time
import psutil
import pytest
from unittest.mock import patch, MagicMock, PropertyMock, call
from pathlib import Path

import src.usage_tracker as usage_tracker

DEFAULT_TIMEOUT_MINUTES = 60.0


def _can_enumerate_process_tree() -> bool:
    """Return True when psutil process-tree enumeration is permitted."""
    try:
        psutil.Process(os.getpid()).children(recursive=True)
        return True
    except (psutil.AccessDenied, PermissionError, OSError):
        return False
    except Exception:
        return False


def _make_mock_proc(pid: int, name: str, cpu_pct: float, rss_bytes: int) -> MagicMock:
    """Create a mock psutil.Process-like object for fallback process-tree tests."""
    proc = MagicMock()
    proc.pid = pid
    proc.name.return_value = name
    proc.cpu_percent.side_effect = [0.0, cpu_pct]
    mem_info = MagicMock()
    mem_info.rss = rss_bytes
    proc.memory_info.return_value = mem_info
    return proc


class _FakeClock:
    """Deterministic clock used for elapsed-time accounting tests."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ============================================================================
# 1. SYSTEM-WIDE ONLY (no pid)
# ============================================================================

class TestSystemWideResourceUsage:
    """Tests for get_resource_usage() with no pid argument."""

    def test_returns_system_cpu_and_ram(self):
        """System CPU and RAM info should always be present."""
        from src.agents.utils.system import get_resource_usage
        result = get_resource_usage()
        assert "System CPU:" in result
        assert "System RAM:" in result
        assert "GB" in result

    def test_no_process_tree_when_no_pid(self):
        """Should NOT contain process tree lines when no pid given."""
        from src.agents.utils.system import get_resource_usage
        result = get_resource_usage()
        assert "Execution Process Tree" not in result
        assert "PID" not in result
        assert "Total:" not in result

    def test_always_returns_nonempty_string(self):
        """Should always return a non-empty string."""
        from src.agents.utils.system import get_resource_usage
        result = get_resource_usage()
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_system_cpu_is_percentage(self):
        """System CPU value should be a parseable percentage."""
        from src.agents.utils.system import get_resource_usage
        result = get_resource_usage()
        # Extract the CPU line
        for line in result.split('\n'):
            if line.startswith("System CPU:"):
                # Should contain a % sign
                assert "%" in line
                break
        else:
            pytest.fail("No 'System CPU:' line found")

    def test_system_ram_shows_usage_and_total(self):
        """System RAM should show used/total format."""
        from src.agents.utils.system import get_resource_usage
        result = get_resource_usage()
        for line in result.split('\n'):
            if "System RAM:" in line:
                assert "/" in line  # used/total format
                assert "GB" in line
                break
        else:
            pytest.fail("No 'System RAM:' line found")

    def test_psutil_failure_returns_na(self):
        """If psutil crashes entirely, should return N/A gracefully."""
        from src.agents.utils.system import get_resource_usage
        with patch('src.agents.utils.system.psutil.cpu_percent', side_effect=RuntimeError("broken")):
            result = get_resource_usage()
        assert "N/A" in result


# ============================================================================
# 2. REAL PROCESS MONITORING
# ============================================================================

class TestRealProcessMonitoring:
    """Tests using actual live processes (our own PID and spawned children)."""

    def test_own_pid_shows_process_tree(self):
        """Monitoring our own PID should show a process tree."""
        from src.agents.utils.system import get_resource_usage

        if _can_enumerate_process_tree():
            result = get_resource_usage(pid=os.getpid())
        else:
            parent = _make_mock_proc(9001, "python", 42.0, 512 * 1024**2)
            parent.children.return_value = []
            with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
                 patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
                result = get_resource_usage(pid=9001)

        assert "Execution Process Tree" in result
        if _can_enumerate_process_tree():
            assert f"PID {os.getpid()}" in result
        else:
            assert "PID 9001" in result
        assert "Total:" in result

    def test_own_pid_shows_job_cpu_but_not_system_cpu(self):
        """PID-based monitoring should keep CPU job-scoped while still showing host RAM."""
        from src.agents.utils.system import get_resource_usage

        if _can_enumerate_process_tree():
            result = get_resource_usage(pid=os.getpid())
        else:
            parent = _make_mock_proc(9002, "python", 15.0, 256 * 1024**2)
            parent.children.return_value = []
            with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
                 patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
                result = get_resource_usage(pid=9002)

        assert "Execution Process Tree" in result
        assert "System RAM:" in result
        assert "System CPU:" not in result

    def test_child_processes_are_listed(self):
        """Spawned child processes should each appear in the tree."""
        from src.agents.utils.system import get_resource_usage
        if _can_enumerate_process_tree():
            children = []
            try:
                for _ in range(3):
                    children.append(subprocess.Popen(['sleep', '30']))
                time.sleep(0.3)

                result = get_resource_usage(pid=os.getpid())

                # All child PIDs should appear
                for child in children:
                    assert f"PID {child.pid}" in result, \
                        f"Child PID {child.pid} not found in output:\n{result}"

                # Should report multiple processes
                assert "processes" in result
            finally:
                for child in children:
                    child.terminate()
                    child.wait()
        else:
            parent = _make_mock_proc(9100, "python", 3.0, 100 * 1024**2)
            c1 = _make_mock_proc(9101, "sleep", 0.0, 8 * 1024**2)
            c2 = _make_mock_proc(9102, "sleep", 0.0, 8 * 1024**2)
            c3 = _make_mock_proc(9103, "sleep", 0.0, 8 * 1024**2)
            parent.children.return_value = [c1, c2, c3]
            with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
                 patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
                result = get_resource_usage(pid=9100)

            for pid in (9101, 9102, 9103):
                assert f"PID {pid}" in result
            assert "processes" in result

    def test_cpu_busy_process_shows_nonzero(self):
        """A CPU-busy child should report measurable CPU usage."""
        from src.agents.utils.system import get_resource_usage

        if _can_enumerate_process_tree():
            # Start a CPU-burning child
            busy_proc = subprocess.Popen(
                [sys.executable, '-c', 'while True: pass'],
            )
            try:
                time.sleep(1.0)  # Let it spin up
                result = get_resource_usage(pid=busy_proc.pid)
            finally:
                busy_proc.terminate()
                busy_proc.wait()
        else:
            parent = _make_mock_proc(9200, "python", 88.0, 128 * 1024**2)
            parent.children.return_value = []
            with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
                 patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
                result = get_resource_usage(pid=9200)

        # The busy process should show nonzero CPU
        assert "Execution Process Tree" in result
        for line in result.split('\n'):
            if "Total:" in line:
                cpu_str = line.split("CPU")[1].split("%")[0].strip()
                assert float(cpu_str) > 0, f"Expected nonzero CPU, got: {line}"
                break

    def test_dead_pid_returns_na(self):
        """A PID that doesn't exist should return N/A."""
        from src.agents.utils.system import get_resource_usage
        result = get_resource_usage(pid=999999999)
        assert "N/A" in result
        # Host memory context should still work without reintroducing host CPU.
        assert "System RAM:" in result
        assert "System CPU:" not in result

    def test_recently_exited_process(self):
        """A process that exits between the call should be handled gracefully."""
        from src.agents.utils.system import get_resource_usage
        
        proc = subprocess.Popen(['echo', 'done'])
        proc.wait()  # Ensure it's dead
        time.sleep(0.1)
        
        result = get_resource_usage(pid=proc.pid)
        # Should handle gracefully (N/A or partial)
        assert isinstance(result, str)
        assert "System RAM:" in result
        assert "System CPU:" not in result


# ============================================================================
# 3. MOCKED PSUTIL PROCESS TREE
# ============================================================================

class TestMockedProcessTree:
    """Tests with fully mocked psutil to control exact per-process values."""

    def _make_mock_proc(self, pid, name, cpu_pct, rss_bytes):
        """Create a mock psutil.Process-like object."""
        proc = MagicMock()
        proc.pid = pid
        proc.name.return_value = name
        # cpu_percent returns 0 on first call, then the real value
        proc.cpu_percent.side_effect = [0.0, cpu_pct]
        mem_info = MagicMock()
        mem_info.rss = rss_bytes
        proc.memory_info.return_value = mem_info
        return proc

    def test_mpi_job_with_4_ranks(self):
        """Simulate a parent python + mpirun + 4 pw.x ranks."""
        from src.agents.utils.system import get_resource_usage
        
        parent = self._make_mock_proc(1000, "python", 5.0, 100 * 1024**2)
        mpirun = self._make_mock_proc(1001, "mpirun", 1.0, 50 * 1024**2)
        pw1 = self._make_mock_proc(1002, "pw.x", 99.5, 2048 * 1024**2)
        pw2 = self._make_mock_proc(1003, "pw.x", 98.7, 2048 * 1024**2)
        pw3 = self._make_mock_proc(1004, "pw.x", 99.1, 2048 * 1024**2)
        pw4 = self._make_mock_proc(1005, "pw.x", 97.8, 2048 * 1024**2)
        
        parent.children.return_value = [mpirun, pw1, pw2, pw3, pw4]
        
        with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
             patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
            result = get_resource_usage(pid=1000)
        
        # Verify structure
        assert "Execution Process Tree (6 processes):" in result
        assert "PID 1000 (python):" in result
        assert "PID 1001 (mpirun):" in result
        assert "PID 1002 (pw.x):" in result
        assert "PID 1003 (pw.x):" in result
        assert "PID 1004 (pw.x):" in result
        assert "PID 1005 (pw.x):" in result
        assert "Total:" in result
        
        # Verify CPU values appear
        assert "CPU 100%" in result or "CPU 99%" in result  # pw.x ranks
        assert "CPU 5%" in result  # parent
        assert "CPU 1%" in result  # mpirun
        
        # Total CPU should be ~401
        for line in result.split('\n'):
            if "Total:" in line:
                cpu_str = line.split("CPU")[1].split("%")[0].strip()
                total_cpu = float(cpu_str)
                assert 395 < total_cpu < 410, f"Expected ~401% total CPU, got {total_cpu}"
                break

    def test_single_process_no_children(self):
        """A single process with no children should report '1 process'."""
        from src.agents.utils.system import get_resource_usage
        
        parent = self._make_mock_proc(2000, "python", 50.0, 500 * 1024**2)
        parent.children.return_value = []
        
        with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
             patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
            result = get_resource_usage(pid=2000)
        
        assert "1 process)" in result
        assert "PID 2000 (python):" in result
        assert "CPU 50%" in result

    def test_child_dies_mid_collection(self):
        """If a child dies between priming and collection, should be skipped gracefully."""
        from src.agents.utils.system import get_resource_usage
        
        parent = self._make_mock_proc(3000, "python", 10.0, 100 * 1024**2)
        
        dying_child = MagicMock()
        dying_child.pid = 3001
        dying_child.name.return_value = "pw.x"
        dying_child.cpu_percent.side_effect = [0.0, psutil.NoSuchProcess(3001)]
        
        healthy_child = self._make_mock_proc(3002, "pw.x", 99.0, 1024 * 1024**2)
        
        parent.children.return_value = [dying_child, healthy_child]
        
        with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
             patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
            result = get_resource_usage(pid=3000)
        
        # Should still work with surviving processes
        assert "Execution Process Tree" in result
        assert "PID 3000 (python):" in result
        assert "PID 3002 (pw.x):" in result
        # Dying child should be skipped
        assert "PID 3001" not in result
        # Should show 2 processes (parent + healthy_child)
        assert "2 processes" in result

    def test_access_denied_on_child(self):
        """If AccessDenied on a child, should skip it and continue."""
        from src.agents.utils.system import get_resource_usage
        
        parent = self._make_mock_proc(4000, "python", 20.0, 200 * 1024**2)
        
        denied_child = MagicMock()
        denied_child.pid = 4001
        denied_child.name.return_value = "pw.x"
        denied_child.cpu_percent.side_effect = [0.0, psutil.AccessDenied(4001)]
        
        parent.children.return_value = [denied_child]
        
        with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
             patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
            result = get_resource_usage(pid=4000)
        
        assert "PID 4000 (python):" in result
        assert "PID 4001" not in result
        assert "1 process)" in result

    def test_all_children_die_shows_na(self):
        """If parent and all children are dead during collection, report N/A."""
        from src.agents.utils.system import get_resource_usage
        
        parent = MagicMock()
        parent.pid = 5000
        parent.name.return_value = "python"
        parent.children.return_value = []
        parent.cpu_percent.side_effect = [0.0, psutil.NoSuchProcess(5000)]
        
        with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
             patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
            result = get_resource_usage(pid=5000)
        
        assert "N/A" in result

    def test_rss_conversion_to_mb_and_gb(self):
        """Verify RSS is shown in MB per process and GB in total."""
        from src.agents.utils.system import get_resource_usage
        
        # 2 GB RSS
        parent = self._make_mock_proc(6000, "python", 50.0, 2 * 1024**3)
        parent.children.return_value = []
        
        with patch('src.agents.utils.system.psutil.Process', return_value=parent), \
             patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
            result = get_resource_usage(pid=6000)
        
        # Per-process should be in MB: 2048 MB
        assert "RSS 2048 MB" in result
        # Total should be in GB: 2.0 GB
        assert "RAM 2.0 GB" in result


# ============================================================================
# 4. GPU PARSING
# ============================================================================

class TestGPUParsing:
    """Tests for GPU/VRAM parsing from nvidia-smi and rocm-smi."""

    def test_single_nvidia_gpu(self):
        """Parse a single NVIDIA GPU."""
        from src.agents.utils.system import get_resource_usage
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0, 75, 20480, 40960\n"
        
        with patch('src.agents.utils.system.subprocess.run', return_value=mock_result):
            result = get_resource_usage()
        
        assert "GPU 0: 75% util" in result
        assert "VRAM:" in result
        # 20480 MiB = 20.0 GiB, 40960 MiB = 40.0 GiB
        assert "20.0/40.0 GB" in result
        assert "50%" in result  # 20480/40960 * 100

    def test_multiple_nvidia_gpus(self):
        """Parse multiple NVIDIA GPUs."""
        from src.agents.utils.system import get_resource_usage
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0, 92, 35000, 40960\n1, 15, 1024, 40960\n2, 0, 512, 40960\n"
        
        with patch('src.agents.utils.system.subprocess.run', return_value=mock_result):
            result = get_resource_usage()
        
        assert "GPU 0:" in result
        assert "GPU 1:" in result
        assert "GPU 2:" in result
        assert "92%" in result
        assert "15%" in result

    def test_nvidia_smi_fails_falls_to_rocm_then_na(self):
        """If both nvidia-smi and rocm-smi fail, show GPU: N/A."""
        from src.agents.utils.system import get_resource_usage
        
        with patch('src.agents.utils.system.subprocess.run', side_effect=FileNotFoundError):
            result = get_resource_usage()
        
        assert "GPU: N/A" in result

    def test_nvidia_smi_returns_nonzero(self):
        """If nvidia-smi returns non-zero exit code, should fall through."""
        from src.agents.utils.system import get_resource_usage
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        
        with patch('src.agents.utils.system.subprocess.run', return_value=mock_result):
            result = get_resource_usage()
        
        # Should show N/A since nvidia-smi failed and rocm-smi will also fail (same mock)
        # The mock returns the same for all calls, but rocm-smi also gets returncode=1
        assert "GPU" in result

    def test_nvidia_smi_malformed_output(self):
        """Malformed nvidia-smi output should be handled without crashing."""
        from src.agents.utils.system import get_resource_usage
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "garbage, data\nnot, enough, columns\n"
        
        with patch('src.agents.utils.system.subprocess.run', return_value=mock_result):
            result = get_resource_usage()
        
        # Should not crash, may show N/A or partial data
        assert isinstance(result, str)

    def test_nvidia_vram_zero_total_no_division_error(self):
        """Zero total VRAM should not cause a ZeroDivisionError."""
        from src.agents.utils.system import get_resource_usage
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0, 50, 1024, 0\n"
        
        with patch('src.agents.utils.system.subprocess.run', return_value=mock_result):
            result = get_resource_usage()
        
        # Should not crash
        assert isinstance(result, str)
        assert "GPU 0:" in result


# ============================================================================
# 5. EXECUTION.PY INTEGRATION (execute_python check-in dict)
# ============================================================================

class TestExecutePythonCheckIn:
    """Tests that execute_python includes resource_usage in check-in dicts."""

    @patch('subprocess.Popen')
    def test_check_in_dict_contains_resource_usage(self, mock_popen, mock_workspace):
        """execute_python check-in dict should contain resource_usage key."""
        from src.tools.execution import execute_python
        
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_process.pid = 55555
        mock_process.poll.return_value = None
        mock_process.communicate.return_value = ("", "")
        
        mock_usage = "Execution Process Tree (1 process):\n  PID 55555 (python): CPU 50% | RSS 256 MB\n  Total: CPU 50% | RAM 0.2 GB\nSystem RAM: 4.0/8.0 GB (50%)\nGPU: N/A"
        
        with patch('os.getpgid', return_value=55555), \
             patch('src.tools.execution._get_check_interval', return_value=0.01), \
             patch('src.tools.execution._get_resource_usage_lazy', return_value=mock_usage), \
             patch('time.sleep'):
            result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": "import time; time.sleep(100)"})
        
        assert isinstance(result, dict)
        assert result['status'] == 'check_in_required'
        assert result['resource_usage'] == mock_usage
        assert 'elapsed_seconds' in result
        assert 'elapsed_display' in result

    @patch('subprocess.Popen')
    def test_resource_usage_lazy_called_with_pid(self, mock_popen, mock_workspace):
        """_get_resource_usage_lazy should be called with the process PID."""
        from src.tools.execution import execute_python
        
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_process.pid = 77777
        mock_process.poll.return_value = None
        
        with patch('os.getpgid', return_value=77777), \
             patch('src.tools.execution._get_check_interval', return_value=0.01), \
             patch('src.tools.execution._get_resource_usage_lazy', return_value="test") as mock_lazy, \
             patch('time.sleep'):
            execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": "pass"})
        
        mock_lazy.assert_called_once_with(pid=77777)

    @patch('subprocess.Popen')
    def test_check_in_dict_has_all_expected_keys(self, mock_popen, mock_workspace):
        """Check-in dict should have all required keys."""
        from src.tools.execution import execute_python
        
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_process.pid = 88888
        mock_process.poll.return_value = None
        
        with patch('os.getpgid', return_value=88888), \
             patch('src.tools.execution._get_check_interval', return_value=0.01), \
             patch('src.tools.execution._get_resource_usage_lazy', return_value="data"), \
             patch('time.sleep'):
            result = execute_python.invoke({"timeout": DEFAULT_TIMEOUT_MINUTES, "code": "pass"})
        
        expected_keys = {'status', 'elapsed_seconds', 'elapsed_display', 'file_path', 'use_temp_file', 'resource_usage'}
        assert set(result.keys()) == expected_keys


# ============================================================================
# 6. RESUME EXECUTION CHECK-IN
# ============================================================================

class TestResumeExecutionCheckIn:
    """Tests that resume_execution also includes resource_usage."""

    def test_resume_check_in_has_resource_usage(self, mock_workspace):
        """resume_execution should include resource_usage in its check-in dict."""
        import src.tools.execution as execution_module
        from src.tools.execution import resume_execution
        
        mock_process = MagicMock()
        mock_process.pid = 66666
        mock_process.poll.return_value = None  # Still running
        
        # Setup global state as if execute_python had started
        execution_module._running_process = mock_process
        execution_module._process_pgid = 66666
        execution_module._process_start_time = time.time() - 100
        execution_module._process_script_path = mock_workspace / "test.py"
        
        mock_usage = "Execution Process Tree (2 processes):\n  PID 66666 (python): CPU 10% | RSS 128 MB\n  PID 66667 (pw.x): CPU 99% | RSS 2048 MB\n  Total: CPU 109% | RAM 2.1 GB"
        
        try:
            with patch('src.tools.execution._get_check_interval', return_value=0.01), \
                 patch('src.tools.execution._get_resource_usage_lazy', return_value=mock_usage) as mock_lazy, \
                 patch('time.sleep'):
                result = resume_execution()
            
            assert isinstance(result, dict)
            assert result['status'] == 'check_in_required'
            assert result['resource_usage'] == mock_usage
            mock_lazy.assert_called_once_with(pid=66666)
        finally:
            # Clean up global state
            execution_module._running_process = None
            execution_module._process_pgid = None
            execution_module._process_start_time = None
            execution_module._process_script_path = None
            execution_module._process_timeout_seconds = None
            execution_module._process_timeout_minutes = None
            execution_module._process_use_temp_file = False


# ============================================================================
# 7. OPERATOR PROMPT INJECTION
# ============================================================================

class TestOperatorPromptIntegration:
    """Verify the operator check-in prompt correctly embeds resource usage."""

    def test_checkin_prompt_contains_resource_usage_section(self):
        """Simulate the operator check-in prompt construction and verify resource usage is embedded."""
        # This mirrors the logic in operator.py lines 616-638
        resource_usage = (
            "Execution Process Tree (4 processes):\n"
            "  PID 1000 (python): CPU 5% | RSS 100 MB\n"
            "  PID 1001 (mpirun): CPU 1% | RSS 50 MB\n"
            "  PID 1002 (pw.x): CPU 99% | RSS 2048 MB\n"
            "  PID 1003 (pw.x): CPU 99% | RSS 2048 MB\n"
            "  Total: CPU 204% | RAM 4.1 GB\n"
            "System RAM: 10.0/32.0 GB (31%)\n"
            "GPU 0: 85% util | VRAM: 30.0/40.0 GB (75%)"
        )
        
        # Simulate the prompt construction from operator.py
        file_path_display = "/workspace/task_1/run_dft.py"
        elapsed_display = "45 minutes"
        
        checkin_prompt = f"""The Python script `{os.path.basename(file_path_display)}` has been running for {elapsed_display}.

**Current Resource Usage:**
{resource_usage}

Use the `read_file`, `grep_search` and `list_directory` tools to review the current outputs.
If you need structured parsing of existing outputs to determine simulation status, you may also use `execute_temporary_python` for short-lived temporary analysis snippets only."""
        
        # Verify all process details are in the prompt
        assert "run_dft.py" in checkin_prompt
        assert "45 minutes" in checkin_prompt
        assert "**Current Resource Usage:**" in checkin_prompt
        assert "Execution Process Tree (4 processes):" in checkin_prompt
        assert "PID 1000 (python): CPU 5%" in checkin_prompt
        assert "PID 1002 (pw.x): CPU 99%" in checkin_prompt
        assert "Total: CPU 204%" in checkin_prompt
        assert "System RAM: 10.0/32.0 GB" in checkin_prompt
        assert "System CPU:" not in checkin_prompt
        assert "GPU 0: 85% util" in checkin_prompt
        assert "VRAM: 30.0/40.0 GB" in checkin_prompt
        assert "execute_temporary_python" in checkin_prompt

    def test_checkin_prompt_with_na_resource_usage(self):
        """When resource_usage is N/A, prompt should still be well-formed."""
        resource_usage = "N/A"
        
        checkin_prompt = f"""The Python script `script.py` has been running for 15 minutes.

**Current Resource Usage:**
{resource_usage}

Based on this assessment, determine whether execution should proceed."""
        
        assert "**Current Resource Usage:**" in checkin_prompt
        assert "N/A" in checkin_prompt
        assert "script.py" in checkin_prompt


# ============================================================================
# 8. USAGE TRACKER HARDWARE-RESUME (no stale hardware-change notice)
# ============================================================================

def _write_checkpoint_settings(workspace: Path, saved_stats: dict) -> None:
    checkpoint_path = workspace / "checkpoint_settings.json"
    checkpoint_path.write_text(
        json.dumps({"_usage_stats": saved_stats}, indent=2),
        encoding="utf-8",
    )


class TestUsageTrackerHardwareResume:
    """Rigorous tests for load_stats_from_checkpoint and hardware-change-on-resume state.
    Ensures the hardware-change notice is only set when hardware actually differs,
    and is cleared between load attempts so interrupted runs on unchanged hardware
    do not get a false notice.
    """

    def test_load_sets_hardware_change_notice_only_when_signature_differs(self, mock_workspace, monkeypatch):
        monkeypatch.setenv("MODEL", "gemini-2.5-pro")
        saved_stats = {
            "api_request_count": 7,
            "input_tokens": 1000,
            "output_tokens": 400,
            "model_name": "gemini-2.5-pro",
            "cumulative_elapsed_time": 12.5,
            "hardware_signature": {
                "cpu_model": "Old CPU",
                "cpu_cores": "16",
                "gpu_info": "Old GPU",
            },
        }
        _write_checkpoint_settings(mock_workspace, saved_stats)
        monkeypatch.setattr(
            usage_tracker,
            "get_hardware_signature",
            lambda: {"cpu_model": "New CPU", "cpu_cores": "32", "gpu_info": "New GPU"},
        )
        usage_tracker.reset()

        loaded = usage_tracker.load_stats_from_checkpoint()

        assert loaded is False
        assert usage_tracker.was_hardware_changed_on_resume() is True
        assert usage_tracker.get_previous_hardware_signature() == saved_stats["hardware_signature"]

    def test_load_clears_stale_hardware_change_state_between_calls(self, mock_workspace, monkeypatch):
        monkeypatch.setenv("MODEL", "gemini-2.5-pro")
        current_sig = {"cpu_model": "Stable CPU", "cpu_cores": "24", "gpu_info": "Stable GPU"}
        monkeypatch.setattr(usage_tracker, "get_hardware_signature", lambda: current_sig)
        usage_tracker.reset()

        changed_stats = {
            "api_request_count": 1,
            "input_tokens": 11,
            "output_tokens": 22,
            "model_name": "gemini-2.5-pro",
            "cumulative_elapsed_time": 3.0,
            "hardware_signature": {
                "cpu_model": "Different CPU",
                "cpu_cores": "8",
                "gpu_info": "Different GPU",
            },
        }
        _write_checkpoint_settings(mock_workspace, changed_stats)
        assert usage_tracker.load_stats_from_checkpoint() is False
        assert usage_tracker.was_hardware_changed_on_resume() is True

        unchanged_stats = {
            "api_request_count": 9,
            "input_tokens": 111,
            "output_tokens": 222,
            "model_name": "gemini-2.5-pro",
            "cumulative_elapsed_time": 30.0,
            "hardware_signature": current_sig,
        }
        _write_checkpoint_settings(mock_workspace, unchanged_stats)
        loaded = usage_tracker.load_stats_from_checkpoint()

        assert loaded is True
        assert usage_tracker.was_hardware_changed_on_resume() is False
        assert usage_tracker.get_previous_hardware_signature() is None
        stats = usage_tracker.get_stats()
        assert stats.api_request_count == 9
        assert stats.input_tokens == 111
        assert stats.output_tokens == 222
        assert stats.cumulative_elapsed_time == pytest.approx(30.0)

    def test_load_without_checkpoint_clears_previous_hardware_change_state(self, mock_workspace, monkeypatch):
        monkeypatch.setenv("MODEL", "gemini-2.5-pro")
        monkeypatch.setattr(
            usage_tracker,
            "get_hardware_signature",
            lambda: {"cpu_model": "CPU", "cpu_cores": "12", "gpu_info": "GPU"},
        )
        usage_tracker.reset()
        changed_stats = {
            "api_request_count": 3,
            "input_tokens": 10,
            "output_tokens": 20,
            "model_name": "gemini-2.5-pro",
            "hardware_signature": {
                "cpu_model": "Old CPU",
                "cpu_cores": "4",
                "gpu_info": "Old GPU",
            },
        }
        _write_checkpoint_settings(mock_workspace, changed_stats)
        assert usage_tracker.load_stats_from_checkpoint() is False
        assert usage_tracker.was_hardware_changed_on_resume() is True

        (mock_workspace / "checkpoint_settings.json").unlink()

        loaded = usage_tracker.load_stats_from_checkpoint()

        assert loaded is False
        assert usage_tracker.was_hardware_changed_on_resume() is False
        assert usage_tracker.get_previous_hardware_signature() is None

    def test_reset_clears_hardware_change_flags(self, mock_workspace, monkeypatch):
        monkeypatch.setenv("MODEL", "gemini-2.5-pro")
        monkeypatch.setattr(
            usage_tracker,
            "get_hardware_signature",
            lambda: {"cpu_model": "CPU", "cpu_cores": "12", "gpu_info": "GPU"},
        )
        usage_tracker.reset()
        changed_stats = {
            "api_request_count": 5,
            "input_tokens": 50,
            "output_tokens": 60,
            "model_name": "gemini-2.5-pro",
            "hardware_signature": {
                "cpu_model": "Old CPU",
                "cpu_cores": "2",
                "gpu_info": "Old GPU",
            },
        }
        _write_checkpoint_settings(mock_workspace, changed_stats)
        assert usage_tracker.load_stats_from_checkpoint() is False
        assert usage_tracker.was_hardware_changed_on_resume() is True

        usage_tracker.reset()

        assert usage_tracker.was_hardware_changed_on_resume() is False
        assert usage_tracker.get_previous_hardware_signature() is None


# ============================================================================
# 9. ELAPSED TIME EXCLUSIONS
# ============================================================================

class TestUsageTrackerExcludedIntervals:
    """Tests for elapsed-time accounting when retry waits are excluded."""

    def test_api_retry_wait_is_excluded_from_checkpoint_and_report(self, mock_workspace, monkeypatch):
        import src.agents.utils.errors as errors_utils
        import src.agents.utils.logging as logging_utils

        clock = _FakeClock()

        monkeypatch.setenv("MODEL", "gemini-2.5-pro")
        monkeypatch.setattr(usage_tracker, "get_hardware_signature", lambda: {
            "cpu_model": "CPU",
            "cpu_cores": "8",
            "gpu_info": "GPU",
        })
        monkeypatch.setattr(usage_tracker.time, "time", clock.time)
        monkeypatch.setattr(errors_utils.time, "sleep", clock.sleep)
        monkeypatch.setattr(errors_utils, "send_agent_event", lambda *args, **kwargs: None)
        monkeypatch.setattr(errors_utils, "send_json", lambda *args, **kwargs: None)
        monkeypatch.setattr(logging_utils, "_write_to_log", lambda *args, **kwargs: None)

        usage_tracker.reset()
        usage_tracker.start_run("gemini-2.5-pro")
        clock.advance(30.0)

        should_retry = errors_utils.handle_api_retry(
            "operator",
            Exception("429 RESOURCE_EXHAUSTED"),
            current_count=1,
            max_retries=3,
            wait_seconds=120,
        )

        assert should_retry is True

        clock.advance(15.0)
        usage_tracker.save_stats_to_checkpoint()

        checkpoint = json.loads((mock_workspace / "checkpoint_settings.json").read_text(encoding="utf-8"))
        saved_stats = checkpoint["_usage_stats"]
        assert saved_stats["cumulative_elapsed_time"] == pytest.approx(45.0)

        with patch("src.usage_tracker._load_run_settings", return_value={
            "MODEL": "gemini-2.5-pro",
            "ACCURACY": "standard",
            "GRANULARITY": "medium",
            "CHECK_INTERVAL": "Disabled",
            "ENABLE_RAG": "false",
            "PMG_MAPI_KEY": "",
        }):
            report = usage_tracker.generate_report()

        assert "**Run Duration:** 45.0s" in report

    def test_active_excluded_interval_is_omitted_from_checkpoint_and_report(self, mock_workspace, monkeypatch):
        clock = _FakeClock()

        monkeypatch.setenv("MODEL", "gemini-2.5-pro")
        monkeypatch.setattr(usage_tracker, "get_hardware_signature", lambda: {
            "cpu_model": "CPU",
            "cpu_cores": "8",
            "gpu_info": "GPU",
        })
        monkeypatch.setattr(usage_tracker.time, "time", clock.time)

        usage_tracker.reset()
        usage_tracker.start_run("gemini-2.5-pro")
        clock.advance(20.0)

        usage_tracker.begin_excluded_interval()
        clock.advance(120.0)
        usage_tracker.save_stats_to_checkpoint()

        checkpoint = json.loads((mock_workspace / "checkpoint_settings.json").read_text(encoding="utf-8"))
        saved_stats = checkpoint["_usage_stats"]
        assert saved_stats["cumulative_elapsed_time"] == pytest.approx(20.0)

        with patch("src.usage_tracker._load_run_settings", return_value={
            "MODEL": "gemini-2.5-pro",
            "ACCURACY": "standard",
            "GRANULARITY": "medium",
            "CHECK_INTERVAL": "Disabled",
            "ENABLE_RAG": "false",
            "PMG_MAPI_KEY": "",
        }):
            report = usage_tracker.generate_report()

        assert "**Run Duration:** 20.0s" in report

        usage_tracker.end_excluded_interval()


# ============================================================================
# 10. LAZY WRAPPER
# ============================================================================

class TestLazyWrapper:
    """Tests for the _get_resource_usage_lazy wrapper in execution.py."""

    def test_lazy_wrapper_delegates_to_real_function(self):
        """The lazy wrapper should call get_resource_usage with the pid."""
        from src.tools.execution import _get_resource_usage_lazy
        
        with patch('src.agents.utils.system.get_resource_usage', return_value="mocked") as mock_fn:
            result = _get_resource_usage_lazy(pid=12345)
        
        mock_fn.assert_called_once_with(pid=12345)
        assert result == "mocked"

    def test_lazy_wrapper_without_pid(self):
        """The lazy wrapper should pass pid=None when not specified."""
        from src.tools.execution import _get_resource_usage_lazy
        
        with patch('src.agents.utils.system.get_resource_usage', return_value="mocked") as mock_fn:
            result = _get_resource_usage_lazy()
        
        mock_fn.assert_called_once_with(pid=None)
        assert result == "mocked"


# ============================================================================
# 11. USAGE REPORT GENERATION (agent breakdown + cost estimate)
# ============================================================================

class TestUsageReportGeneration:
    """Tests for _generate_report_from_stats covering the two fixed bugs:
    1. Agent breakdown is hidden when all agents share the same model.
    2. Cost estimate sums per-agent costs when agents use different models.
    """

    def _make_stats(self, primary_model: str, per_agent: dict,
                    input_tokens: int = 1_000_000, output_tokens: int = 100_000) -> "src.usage_tracker.UsageStats":
        import src.usage_tracker as ut
        stats = ut.UsageStats(
            start_time=0,
            end_time=0,
            cumulative_elapsed_time=120.0,
            api_request_count=sum(a.get('api_request_count', 0) for a in per_agent.values()),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=primary_model,
            run_status="success",
            per_agent_stats=per_agent,
        )
        in_rate, out_rate = ut._get_cost_rates_for_model(primary_model)
        stats.input_cost_per_million = in_rate
        stats.output_cost_per_million = out_rate
        return stats

    # --- Bug 1: agent breakdown visibility ---

    def test_no_breakdown_when_all_agents_same_model(self):
        """Per-agent breakdown table should NOT appear when all agents share the primary model."""
        import src.usage_tracker as ut
        model = "gemini-3-flash-preview"
        per_agent = {
            'operator':  {'api_request_count': 187, 'input_tokens': 8_252_414, 'output_tokens': 76_218, 'model_name': model},
            'evaluator': {'api_request_count':  14, 'input_tokens':   636_902, 'output_tokens':  7_318, 'model_name': model},
        }
        stats = self._make_stats(model, per_agent,
                                 input_tokens=8_889_316, output_tokens=83_536)
        with patch('src.usage_tracker._load_run_settings', return_value={
            'MODEL': model, 'ACCURACY': 'standard', 'GRANULARITY': 'medium',
            'CHECK_INTERVAL': '0', 'ENABLE_RAG': 'true', 'PMG_MAPI_KEY': 'key',
        }):
            report = ut._generate_report_from_stats(stats)

        assert "### Per-Agent Breakdown" not in report

    def test_no_breakdown_when_no_agent_stats(self):
        """Per-agent breakdown should not appear when per_agent_stats is empty."""
        import src.usage_tracker as ut
        model = "gemini-3-flash-preview"
        stats = self._make_stats(model, {})
        with patch('src.usage_tracker._load_run_settings', return_value={
            'MODEL': model, 'ACCURACY': 'standard', 'GRANULARITY': 'medium',
            'CHECK_INTERVAL': '0', 'ENABLE_RAG': 'true', 'PMG_MAPI_KEY': '',
        }):
            report = ut._generate_report_from_stats(stats)

        assert "### Per-Agent Breakdown" not in report

    def test_breakdown_shown_when_agents_use_different_models(self):
        """Per-agent breakdown SHOULD appear when agents use different models."""
        import src.usage_tracker as ut
        primary_model = "gemini-3-flash-preview"
        per_agent = {
            'operator':  {'api_request_count': 187, 'input_tokens': 8_252_414, 'output_tokens': 76_218, 'model_name': 'gemini-3-flash-preview'},
            'evaluator': {'api_request_count':  14, 'input_tokens':   636_902, 'output_tokens':  7_318, 'model_name': 'gemini-3.1-pro-preview'},
        }
        stats = self._make_stats(primary_model, per_agent,
                                 input_tokens=8_889_316, output_tokens=83_536)
        with patch('src.usage_tracker._load_run_settings', return_value={
            'MODEL': primary_model, 'ACCURACY': 'standard', 'GRANULARITY': 'medium',
            'CHECK_INTERVAL': '0', 'ENABLE_RAG': 'true', 'PMG_MAPI_KEY': 'key',
        }):
            report = ut._generate_report_from_stats(stats)

        assert "### Per-Agent Breakdown" in report
        assert "gemini-3-flash-preview" in report
        assert "gemini-3.1-pro-preview" in report

    # --- Bug 2: cost estimate ---

    def test_cost_uses_primary_rate_when_same_model(self):
        """Single-model run: cost table should use the primary model rate."""
        import src.usage_tracker as ut
        model = "gemini-3-flash-preview"   # $0.50 in, $3.00 out
        per_agent = {
            'operator':  {'api_request_count': 187, 'input_tokens': 8_252_414, 'output_tokens': 76_218, 'model_name': model},
            'evaluator': {'api_request_count':  14, 'input_tokens':   636_902, 'output_tokens':  7_318, 'model_name': model},
        }
        stats = self._make_stats(model, per_agent,
                                 input_tokens=8_889_316, output_tokens=83_536)
        with patch('src.usage_tracker._load_run_settings', return_value={
            'MODEL': model, 'ACCURACY': 'standard', 'GRANULARITY': 'medium',
            'CHECK_INTERVAL': '0', 'ENABLE_RAG': 'true', 'PMG_MAPI_KEY': 'key',
        }):
            report = ut._generate_report_from_stats(stats)

        assert "## Cost Estimate" in report
        # Input rate for gemini-3-flash-preview is $0.50
        assert "$0.50" in report
        # Simple top-level rows (not per-agent rows)
        assert "| Input |" in report
        assert "| Output |" in report

    def test_cost_summed_per_agent_model_when_models_differ(self):
        """Mixed-model run: cost must be computed per agent and summed correctly."""
        import src.usage_tracker as ut

        # operator: gemini-3-flash-preview  ($0.50 in / $3.00 out)
        # evaluator: gemini-3.1-pro-preview ($1.25 in / $10.00 out)
        op_in  = 8_252_414
        op_out = 76_218
        ev_in  = 636_902
        ev_out = 7_318

        op_in_cost  = (op_in  / 1_000_000) * 0.50
        op_out_cost = (op_out / 1_000_000) * 3.00
        ev_in_cost  = (ev_in  / 1_000_000) * 1.25
        ev_out_cost = (ev_out / 1_000_000) * 10.00
        expected_total = op_in_cost + op_out_cost + ev_in_cost + ev_out_cost

        per_agent = {
            'operator':  {'api_request_count': 187, 'input_tokens': op_in, 'output_tokens': op_out, 'model_name': 'gemini-3-flash-preview'},
            'evaluator': {'api_request_count':  14, 'input_tokens': ev_in, 'output_tokens': ev_out, 'model_name': 'gemini-3.1-pro-preview'},
        }
        stats = self._make_stats("gemini-3-flash-preview", per_agent,
                                 input_tokens=op_in + ev_in, output_tokens=op_out + ev_out)
        with patch('src.usage_tracker._load_run_settings', return_value={
            'MODEL': 'gemini-3-flash-preview', 'ACCURACY': 'standard', 'GRANULARITY': 'medium',
            'CHECK_INTERVAL': '0', 'ENABLE_RAG': 'true', 'PMG_MAPI_KEY': 'key',
        }):
            report = ut._generate_report_from_stats(stats)

        assert "## Cost Estimate" in report
        # The total cost row should contain the expected total formatted to 4dp
        expected_total_str = f"${expected_total:.4f}"
        assert expected_total_str in report, (
            f"Expected total cost {expected_total_str} not found in report:\n{report}"
        )
        # Per-agent rows should appear
        assert "Operator (gemini-3-flash-preview)" in report
        assert "Evaluator (gemini-3.1-pro-preview)" in report
