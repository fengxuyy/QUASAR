"""
System information utilities for CPU, GPU, and Slurm detection.
"""

import os
import subprocess
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
