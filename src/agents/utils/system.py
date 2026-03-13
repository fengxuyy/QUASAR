"""
System information utilities for CPU, GPU, and Slurm detection.
"""

import os
import subprocess
import time
import platform
from collections import Counter

import psutil


def get_usable_physical_cores() -> int:
    """Get the number of usable physical cores.
    
    Handles Slurm, Docker, taskset restrictions on Linux.
    Falls back to psutil for Windows/Mac/unrestricted Linux.
    
    Returns:
        Number of usable physical cores, or None if unavailable.
    """


    system = platform.system()
    
    # Get the baseline from psutil (Works on Windows/Mac/Linux)
    total_physical = psutil.cpu_count(logical=False)
    total_logical = psutil.cpu_count(logical=True)

    # Check for Linux-specific Affinity (Slurm, Docker, taskset)
    if system == "Linux":
        try:
            # os.sched_getaffinity(0) returns the set of CPUs the 
            # current process is restricted to (e.g., by Slurm or Docker)
            affinity = os.sched_getaffinity(0)
            
            # If affinity is restricted (not seeing all logical cores)
            if len(affinity) < total_logical:
                # Map restricted logical IDs to unique physical cores
                unique_physical_cores = set()
                for cpu_id in affinity:
                    try:
                        # Find which physical core this logical ID belongs to
                        with open(f"/sys/devices/system/cpu/cpu{cpu_id}/topology/core_id") as f_core:
                            c_id = f_core.read().strip()
                        with open(f"/sys/devices/system/cpu/cpu{cpu_id}/topology/physical_package_id") as f_pkg:
                            p_id = f_pkg.read().strip()
                        
                        # A core is unique only within its socket (package)
                        unique_physical_cores.add((p_id, c_id))
                    except FileNotFoundError:
                        # Fallback if /sys is not accessible
                        continue
                
                if unique_physical_cores:
                    return len(unique_physical_cores)
                return len(affinity)  # Fallback to logical if topology fails
        except AttributeError:
            pass

    # Final Fallback for Windows, Mac, or unrestricted Linux
    return total_physical


def get_cpu_info() -> str:
    """Extract essential CPU information.
    
    Uses get_usable_physical_cores() to determine physical cores.
    Uses lscpu to get model name and vendor ID.
    
    Returns a formatted string with:
    - CPU: Model name (or Vendor ID if model name is "-")
    - Physical cores: usable physical cores
    
    Returns "- CPU: N/A" only if physical cores cannot be determined.
    """
    # Get physical cores using the robust detection function
    physical_cores = get_usable_physical_cores()
    
    # If we can't determine physical cores, return N/A
    if physical_cores is None:
        return "- CPU: N/A"
    
    # Get CPU model and vendor from lscpu (Linux only)
    cpu_model = "-"
    vendor_id = "-"
    
    try:
        result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('Model name:'):
                    cpu_model = line.split(':', 1)[1].strip()
                elif line.startswith('Vendor ID:'):
                    vendor_id = line.split(':', 1)[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # If model name is "-", use vendor ID instead
    display_cpu = cpu_model if cpu_model != "-" else vendor_id
    
    # Check if running under Slurm for labeling
    is_slurm = any([
        os.environ.get('SLURM_CPUS_PER_TASK'),
        os.environ.get('SLURM_JOB_CPUS_PER_NODE'),
        os.environ.get('SLURM_NTASKS'),
        os.environ.get('SLURM_CPUS_ON_NODE')
    ])
    
    cores_label = f"{physical_cores} (allocated from Slurm)" if is_slurm else str(physical_cores)
    
    info_lines = [
        f"- CPU: {display_cpu}",
        f"- Physical cores: {cores_label}"
    ]
    
    return "\n".join(info_lines)


def get_gpu_info() -> str:
    """Extract GPU information using system commands.
    
    Checks for CUDA (nvidia-smi) first, then ROCm (rocm-smi).
    
    Returns a formatted string like:
    - GPU: CUDA - 2 x NVIDIA A100-SXM4-40GB
    - GPU: ROCm - AMD Instinct MI250X
    - GPU: N/A (if no GPU detected)
    """
    gpu_info = _get_gpu_info()
    return f"- GPU: {gpu_info}"


def get_hardware_info() -> str:
    """Extract combined CPU and GPU information.
    
    Combines get_cpu_info() and get_gpu_info() results.
    
    Returns a formatted string with all hardware information.
    """
    cpu_info = get_cpu_info()
    gpu_info = get_gpu_info()
    return f"{cpu_info}\n{gpu_info}"


def get_resource_usage(pid: int = None) -> str:
    """Get live resource usage metrics for monitoring running processes.
    
    Args:
        pid: Optional process ID to monitor. When provided, reports CPU and memory
             usage for that specific process and all its children (e.g. MPI ranks).
             When None, reports system-wide CPU/RAM only.
    
    Collects:
    - Process-specific CPU% and RSS memory (when pid is provided)
    - System-wide CPU and RAM (always)
    - GPU utilization and VRAM (if CUDA or ROCm GPUs are available)
    
    Returns a formatted string like:
        Process CPU: 780% (across 8 processes) | Process RAM: 12.4 GB
        System CPU: 87% | System RAM: 14.2/31.9 GB (45%)
        GPU 0: 92% util | VRAM: 35.1/40.0 GB (88%)
    """
    lines = []
    
    # Process-specific metrics (when pid is provided)
    if pid is not None:
        try:
            parent = psutil.Process(pid)
            # Collect the process tree (parent + all children including MPI ranks)
            all_procs = [parent] + parent.children(recursive=True)
            
            # Prime cpu_percent for all processes (first call always returns 0)
            for p in all_procs:
                try:
                    p.cpu_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Brief interval for meaningful CPU measurement
            time.sleep(0.5)
            
            # Collect per-process values
            proc_details = []
            total_cpu = 0.0
            total_rss = 0
            for p in all_procs:
                try:
                    cpu = p.cpu_percent()
                    mem_info = p.memory_info()
                    rss = mem_info.rss
                    name = p.name()
                    p_pid = p.pid
                    total_cpu += cpu
                    total_rss += rss
                    rss_mb = rss / (1024 ** 2)
                    proc_details.append(
                        f"  PID {p_pid} ({name}): CPU {cpu:.0f}% | RSS {rss_mb:.0f} MB"
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            alive_count = len(proc_details)
            rss_gb = total_rss / (1024 ** 3)
            
            if proc_details:
                lines.append(f"Execution Process Tree ({alive_count} process{'es' if alive_count != 1 else ''}):")
                lines.extend(proc_details)
                lines.append(
                    f"  Total: CPU {total_cpu:.0f}% | RAM {rss_gb:.1f} GB"
                )
            else:
                lines.append("Process: N/A (no active processes found)")
        except psutil.NoSuchProcess:
            lines.append("Process: N/A (process ended)")
        except Exception:
            lines.append("Process: N/A")
    
    # System-wide CPU and RAM (always included for context)
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        mem_used_gb = mem.used / (1024 ** 3)
        mem_total_gb = mem.total / (1024 ** 3)
        lines.append(
            f"System CPU: {cpu_percent:.0f}% | System RAM: {mem_used_gb:.1f}/{mem_total_gb:.1f} GB ({mem.percent:.0f}%)"
        )
    except Exception:
        lines.append("System CPU: N/A | System RAM: N/A")
    
    # GPU utilization & VRAM — try CUDA (nvidia-smi) first, then ROCm
    gpu_found = False
    
    # CUDA
    try:
        result = subprocess.run(
            [
                'nvidia-smi',
                '--query-gpu=index,utilization.gpu,memory.used,memory.total',
                '--format=csv,noheader,nounits'
            ],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            for row in result.stdout.strip().split('\n'):
                parts = [p.strip() for p in row.split(',')]
                if len(parts) == 4:
                    idx, util, mem_used, mem_total = parts
                    try:
                        mem_used_f = float(mem_used) / 1024  # MiB -> GiB
                        mem_total_f = float(mem_total) / 1024
                        mem_pct = (float(mem_used) / float(mem_total) * 100) if float(mem_total) > 0 else 0
                        lines.append(
                            f"GPU {idx}: {util}% util | VRAM: {mem_used_f:.1f}/{mem_total_f:.1f} GB ({mem_pct:.0f}%)"
                        )
                    except (ValueError, ZeroDivisionError):
                        lines.append(f"GPU {idx}: {util}% util | VRAM: {mem_used}/{mem_total} MiB")
                    gpu_found = True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass
    
    # ROCm
    if not gpu_found:
        try:
            result = subprocess.run(
                ['rocm-smi', '--showuse', '--showmeminfo', 'vram'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                lines.append(f"GPU (ROCm): see rocm-smi for details")
                gpu_found = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception:
            pass
    
    if not gpu_found:
        lines.append("GPU: N/A")
    
    return "\n".join(lines)


def _get_gpu_info() -> str:
    """Detect GPU availability and return formatted info.
    
    Checks for CUDA (nvidia-smi) first, then ROCm (rocm-smi).
    Returns formatted string like "CUDA - 2 x NVIDIA A100-SXM4-40GB"
    """
    # Try CUDA first (nvidia-smi)
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            gpu_names = [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
            if gpu_names:
                # Count GPUs by model
                gpu_counts = Counter(gpu_names)
                gpu_list = []
                for name, count in gpu_counts.items():
                    if count > 1:
                        gpu_list.append(f"{count} x {name}")
                    else:
                        gpu_list.append(name)
                return f"CUDA - {', '.join(gpu_list)}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass
    
    # Try ROCm (rocm-smi)
    try:
        result = subprocess.run(
            ['rocm-smi', '--showproductname'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # Parse rocm-smi output for GPU names
            gpu_names = []
            for line in result.stdout.strip().split('\n'):
                # ROCm output format varies, look for card info
                if 'Card' in line or 'GPU' in line:
                    # Try to extract the model name
                    parts = line.split(':')
                    if len(parts) > 1:
                        gpu_names.append(parts[-1].strip())
                    elif 'gfx' in line.lower() or 'mi' in line.lower():
                        gpu_names.append(line.strip())
            
            if not gpu_names:
                # Fallback: try alternative rocm-smi command
                result2 = subprocess.run(
                    ['rocm-smi', '-i'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result2.returncode == 0:
                    for line in result2.stdout.strip().split('\n'):
                        if 'GPU' in line and ':' in line:
                            parts = line.split(':')
                            if len(parts) > 1:
                                gpu_names.append(parts[-1].strip())
            
            if gpu_names:
                gpu_counts = Counter(gpu_names)
                gpu_list = []
                for name, count in gpu_counts.items():
                    if count > 1:
                        gpu_list.append(f"{count} x {name}")
                    else:
                        gpu_list.append(name)
                return f"ROCm - {', '.join(gpu_list)}"
            else:
                # ROCm is available but couldn't parse GPU names
                return "ROCm - Available (model unknown)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass
    
    return "N/A"
