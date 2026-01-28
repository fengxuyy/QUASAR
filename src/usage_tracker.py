"""Usage tracking for API calls, tokens, and costs.

This module provides centralized tracking of:
- Run timing (with interruption handling)
- API request counts
- Token usage (input/output)
- Cost estimation
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional


@dataclass
class UsageStats:
    """Track usage statistics for a run."""
    start_time: float = 0.0
    end_time: float = 0.0
    cumulative_elapsed_time: float = 0.0  # Total elapsed time across all sessions (excluding interruptions)
    last_session_start: float = 0.0  # Start time of current session
    api_request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    
    # Cost rates per 1M tokens (None = unknown model, display as N/A)
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    
    # Run configuration settings (saved to ensure accurate historical reports)
    model_name: str = ""
    accuracy: str = ""
    granularity: str = ""
    enable_rag: Optional[bool] = None
    run_status: Optional[str] = None  # "success", "interrupted", "fail", or None
    
    # Hardware signature for detecting environment changes
    hardware_signature: Optional[dict] = None



# Global tracker instance with thread-safe operations
_tracker: UsageStats = UsageStats()
_lock = Lock()


def start_run(model_name: str = "", preserve_start_time: bool = False) -> None:
    """Start timing a run.
    
    Args:
        model_name: Name of the model being used (for cost estimation)
        preserve_start_time: If True, don't overwrite existing start_time (useful when resuming)
    """
    global _tracker
    
    # Get hardware signature before acquiring lock (it may do I/O)
    hw_sig = get_hardware_signature()
    
    with _lock:
        current_time = time.time()
        
        # If resuming, add elapsed time from previous session to cumulative
        if preserve_start_time and _tracker.last_session_start > 0:
            session_elapsed = current_time - _tracker.last_session_start
            _tracker.cumulative_elapsed_time += session_elapsed
        
        # Set start_time only for the very first start
        if not preserve_start_time or _tracker.start_time == 0:
            _tracker.start_time = current_time
            _tracker.cumulative_elapsed_time = 0.0
        
        # Start new session
        _tracker.last_session_start = current_time
        _tracker.end_time = 0.0
        _tracker.run_status = None  # Reset status when starting
        
        if model_name:
            _tracker.model_name = model_name
        
        # Capture current settings from environment
        _tracker.accuracy = os.getenv('ACCURACY', '')
        _tracker.granularity = os.getenv('GRANULARITY', '')
        
        enable_rag_env = os.getenv('ENABLE_RAG', '').lower()
        if enable_rag_env in ['true', '1', 'yes']:
            _tracker.enable_rag = True
        elif enable_rag_env in ['false', '0', 'no']:
            _tracker.enable_rag = False
        
        # Set cost rates based on model
        if model_name:
            _set_cost_rates(model_name)
        
        # Set hardware signature (includes model_name from environment)
        _tracker.hardware_signature = hw_sig


def _set_cost_rates(model_name: str) -> None:
    """Set cost rates based on model name (called within lock).
    
    Uses exact pricing for known models. Unknown models get None (displayed as N/A).
    Pricing uses ≤200k context rates for context-dependent models.
    """
    global _tracker
    model_lower = model_name.lower() if model_name else ""
    
    # Gemini model pricing ($ per 1M tokens, ≤200k context)
    GEMINI_PRICING = {
        "gemini-3-pro-preview": (2.00, 12.00),
        "gemini-2.5-pro": (1.25, 10.00),
        "gemini-3-flash-preview": (0.50, 3.00),
        "gemini-2.5-flash": (0.30, 2.50),
    }
    
    # Check for exact model match
    if model_lower in GEMINI_PRICING:
        _tracker.input_cost_per_million, _tracker.output_cost_per_million = GEMINI_PRICING[model_lower]
        return
    
    # Check for partial match (e.g., "gemini-2.5-pro-exp" matches "gemini-2.5-pro")
    for model_key, (input_cost, output_cost) in GEMINI_PRICING.items():
        if model_key in model_lower or model_lower in model_key:
            _tracker.input_cost_per_million = input_cost
            _tracker.output_cost_per_million = output_cost
            return
    
    # Unknown model - set to None (will display as N/A)
    _tracker.input_cost_per_million = None
    _tracker.output_cost_per_million = None


def end_run() -> None:
    """End timing a run."""
    global _tracker
    with _lock:
        if _tracker.start_time > 0 and _tracker.end_time == 0:
            current_time = time.time()
            # Add current session elapsed time to cumulative before ending
            if _tracker.last_session_start > 0:
                session_elapsed = current_time - _tracker.last_session_start
                _tracker.cumulative_elapsed_time += session_elapsed
                _tracker.last_session_start = 0.0  # Clear session start
            _tracker.end_time = current_time


def set_run_status(status: str) -> None:
    """Set the run status.
    
    Args:
        status: One of "success", "interrupted", or "fail"
    """
    global _tracker
    with _lock:
        _tracker.run_status = status


def record_api_call(input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Record an API call with token counts.
    
    Automatically persists stats to checkpoint after recording to ensure
    SIGKILL resilience - stats are never lost even if process is killed.
    
    Args:
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
    """
    global _tracker
    with _lock:
        _tracker.api_request_count += 1
        _tracker.input_tokens += input_tokens
        _tracker.output_tokens += output_tokens
    
    # Persist stats immediately after recording (outside lock to avoid deadlock)
    # This ensures stats survive SIGKILL interruptions
    save_stats_to_checkpoint()


def get_stats() -> UsageStats:
    """Get a copy of current usage statistics."""
    with _lock:
        # Calculate current session elapsed time if running
        current_elapsed = 0.0
        if _tracker.last_session_start > 0 and _tracker.end_time == 0:
            current_elapsed = time.time() - _tracker.last_session_start
        
        return UsageStats(
            start_time=_tracker.start_time,
            end_time=_tracker.end_time,
            cumulative_elapsed_time=_tracker.cumulative_elapsed_time + current_elapsed,
            last_session_start=_tracker.last_session_start,
            api_request_count=_tracker.api_request_count,
            input_tokens=_tracker.input_tokens,
            output_tokens=_tracker.output_tokens,
            input_cost_per_million=_tracker.input_cost_per_million,
            output_cost_per_million=_tracker.output_cost_per_million,
            model_name=_tracker.model_name,
            run_status=_tracker.run_status,
        )


def reset() -> None:
    """Reset all tracking data."""
    global _tracker
    with _lock:
        _tracker = UsageStats()
        _tracker.cumulative_elapsed_time = 0.0
        _tracker.last_session_start = 0.0


def get_hardware_signature() -> dict:
    """Get current hardware signature for detecting environment changes.
    
    Returns:
        Dictionary with cpu_model, cpu_cores, gpu_info, and model_name
    """
    import os
    try:
        from .agents.utils import get_cpu_info, get_gpu_info
        cpu_info = get_cpu_info()
        gpu_info = get_gpu_info()
    except Exception:
        cpu_info = "N/A"
        gpu_info = "N/A"
    
    # Extract just the core values for comparison
    # CPU info format: "- CPU: Model\n- Physical cores: N"
    cpu_model = "N/A"
    cpu_cores = "N/A"
    for line in cpu_info.split('\n'):
        if line.startswith('- CPU:'):
            cpu_model = line.replace('- CPU:', '').strip()
        elif line.startswith('- Physical cores:'):
            cpu_cores = line.replace('- Physical cores:', '').strip()
    
    # GPU info format: "- GPU: CUDA - Model" or "- GPU: N/A"
    gpu_value = gpu_info.replace('- GPU:', '').strip() if gpu_info.startswith('- GPU:') else gpu_info
    
    return {
        'cpu_model': cpu_model,
        'cpu_cores': cpu_cores,
        'gpu_info': gpu_value,
    }


def save_stats_to_checkpoint() -> None:
    """Save current token usage stats to checkpoint_settings.json.
    
    This is called after every API call to ensure stats persist even if the
    process is killed with SIGKILL. Hardware signature is saved to detect
    environment changes between sessions.
    """
    global _tracker
    from .tools.base import WORKSPACE_DIR
    
    checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
    
    with _lock:
        # Don't call get_stats() here - it would deadlock since it also acquires _lock
        # Access _tracker directly since we already hold the lock
        
        # Load existing settings if file exists
        settings = {}
        if checkpoint_settings_path.exists():
            try:
                with open(checkpoint_settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except Exception:
                pass
        
        # Calculate elapsed time for current session before saving
        # We need to include this in cumulative so it's preserved across interruptions
        current_session_elapsed = 0.0
        if _tracker.last_session_start > 0:
            current_session_elapsed = time.time() - _tracker.last_session_start
        
        # Get hardware signature (call outside lock context - but we're already in lock)
        # Cache the hardware signature to avoid repeated calls
        if _tracker.hardware_signature is None:
            # Release lock temporarily to get hardware signature
            pass  # We'll set it from start_run instead
        
        # Save token usage stats with cumulative elapsed time (including current session)
        settings['_usage_stats'] = {
            'api_request_count': _tracker.api_request_count,
            'input_tokens': _tracker.input_tokens,
            'output_tokens': _tracker.output_tokens,
            'model_name': _tracker.model_name,
            'accuracy': _tracker.accuracy,
            'granularity': _tracker.granularity,
            'enable_rag': _tracker.enable_rag,
            'input_cost_per_million': _tracker.input_cost_per_million,
            'output_cost_per_million': _tracker.output_cost_per_million,
            'start_time': _tracker.start_time,
            'cumulative_elapsed_time': _tracker.cumulative_elapsed_time + current_session_elapsed,
            # Don't save last_session_start - we'll start fresh when resuming
            'run_status': _tracker.run_status,
            'hardware_signature': _tracker.hardware_signature,
        }

        
        # Write back to file
        try:
            with open(checkpoint_settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass  # Silently fail if we can't save


def load_stats_from_checkpoint() -> bool:
    """Load token usage stats from checkpoint_settings.json and accumulate.
    
    Handles hardware/model changes:
    - If hardware signature matches, accumulate stats normally
    - If hardware signature differs, move old stats to history and start fresh
    
    Returns:
        True if stats were loaded and accumulated, False otherwise
    """
    global _tracker
    from .tools.base import WORKSPACE_DIR
    
    checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
    
    if not checkpoint_settings_path.exists():
        return False
    
    try:
        with open(checkpoint_settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        saved_stats = settings.get('_usage_stats')
        if not saved_stats:
            return False
        
        # Get current hardware signature for comparison
        current_hw_sig = get_hardware_signature()
        saved_hw_sig = saved_stats.get('hardware_signature')
        
        # Check if hardware/model has changed
        hardware_changed = False
        current_model = os.getenv('MODEL', '')
        
        # 1. Check for model change (top-level field)
        if saved_stats.get('model_name') != current_model:
            hardware_changed = True
            
        # 2. Check for hardware change (nested signature)
        elif saved_hw_sig and current_hw_sig:
            # Compare key fields that indicate a significant environment change
            if (saved_hw_sig.get('cpu_model') != current_hw_sig.get('cpu_model') or
                saved_hw_sig.get('cpu_cores') != current_hw_sig.get('cpu_cores') or
                saved_hw_sig.get('gpu_info') != current_hw_sig.get('gpu_info')):
                hardware_changed = True
        
        if hardware_changed:
            # Hardware changed - move old stats to history, don't accumulate
            # First, generate a report for the interrupted session
            _generate_report_for_saved_stats(saved_stats)
            
            # Move saved stats to history
            history = settings.get('_usage_stats_history', [])
            history.append(saved_stats)
            settings['_usage_stats_history'] = history
            
            # Clear current stats (will be reset by start_run)
            settings['_usage_stats'] = {}
            
            # Save updated settings
            try:
                with open(checkpoint_settings_path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2)
            except Exception:
                pass
            
            return False  # Don't accumulate - starting fresh
        
        # Accumulate saved stats with current stats (hardware unchanged)
        with _lock:
            _tracker.api_request_count += saved_stats.get('api_request_count', 0)
            _tracker.input_tokens += saved_stats.get('input_tokens', 0)
            _tracker.output_tokens += saved_stats.get('output_tokens', 0)
            
            # Restore cumulative elapsed time (this includes all previous sessions)
            saved_cumulative = saved_stats.get('cumulative_elapsed_time', 0)
            if saved_cumulative > 0:
                _tracker.cumulative_elapsed_time = saved_cumulative
            
            # Don't restore last_session_start - it will be set by start_run() when resuming
            # This ensures we don't double-count time when resuming
            
            # Preserve model name and cost rates if not already set
            if not _tracker.model_name and saved_stats.get('model_name'):
                _tracker.model_name = saved_stats['model_name']
            if _tracker.input_cost_per_million is None and saved_stats.get('input_cost_per_million') is not None:
                _tracker.input_cost_per_million = saved_stats['input_cost_per_million']
            if _tracker.output_cost_per_million is None and saved_stats.get('output_cost_per_million') is not None:
                _tracker.output_cost_per_million = saved_stats['output_cost_per_million']
            
            # Use the earliest start_time if available
            saved_start_time = saved_stats.get('start_time', 0)
            if saved_start_time > 0 and (_tracker.start_time == 0 or saved_start_time < _tracker.start_time):
                _tracker.start_time = saved_start_time
            
            # Preserve run status if not already set
            if _tracker.run_status is None and saved_stats.get('run_status'):
                _tracker.run_status = saved_stats['run_status']
            
            # Preserve hardware signature
            if saved_hw_sig:
                _tracker.hardware_signature = saved_hw_sig
                
            # Preserve run settings
            if not _tracker.accuracy: _tracker.accuracy = saved_stats.get('accuracy', '')
            if not _tracker.granularity: _tracker.granularity = saved_stats.get('granularity', '')
            if _tracker.enable_rag is None: _tracker.enable_rag = saved_stats.get('enable_rag')
        
        return True
    except Exception:
        return False


def _generate_report_for_saved_stats(saved_stats: dict) -> None:
    """Generate usage report directly from saved stats and save it to usage_report.md.
    
    This generates a report using the saved checkpoint data, without requiring
    the global tracker to be loaded first. This is important for generating
    reports on startup before the run is resumed.
    """
    from .tools.base import LOGS_DIR
    
    # Create a UsageStats object from saved data
    stats = UsageStats(
        start_time=saved_stats.get('start_time', 0),
        end_time=0,  # Interrupted runs don't have end_time
        cumulative_elapsed_time=saved_stats.get('cumulative_elapsed_time', 0),
        api_request_count=saved_stats.get('api_request_count', 0),
        input_tokens=saved_stats.get('input_tokens', 0),
        output_tokens=saved_stats.get('output_tokens', 0),
        input_cost_per_million=saved_stats.get('input_cost_per_million'),
        output_cost_per_million=saved_stats.get('output_cost_per_million'),
        model_name=saved_stats.get('model_name', ''),
        accuracy=saved_stats.get('accuracy', ''),
        granularity=saved_stats.get('granularity', ''),
        enable_rag=saved_stats.get('enable_rag'),
        run_status=saved_stats.get('run_status', 'interrupted'),  # Default to interrupted
        hardware_signature=saved_stats.get('hardware_signature'),
    )
    
    # Generate report from this stats object
    report_content = _generate_report_from_stats(stats)
    
    # Save the report
    report_path = LOGS_DIR / "usage_report.md"
    try:
        report_path.write_text(report_content, encoding='utf-8')
    except Exception:
        pass



def generate_interrupted_report_if_needed() -> bool:
    """Generate usage report for interrupted run if stats exist without a report.
    
    Called on resume to ensure interrupted runs get their usage reports.
    
    Returns:
        True if a report was generated, False otherwise
    """
    from .tools.base import WORKSPACE_DIR, LOGS_DIR
    
    checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
    report_path = LOGS_DIR / "usage_report.md"
    
    # Check if we have stats but no report (indicates interrupted run)
    if not checkpoint_settings_path.exists():
        return False
    
    try:
        with open(checkpoint_settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        saved_stats = settings.get('_usage_stats')
        if not saved_stats:
            return False
        
        # If report already exists and run was successful, don't regenerate
        if report_path.exists():
            # Check if the existing report is for a successful run
            # If so, don't overwrite it
            if saved_stats.get('run_status') == 'success':
                return False
        
        # Generate report for the interrupted run
        _generate_report_for_saved_stats(saved_stats)
        return True
        
    except Exception:
        return False


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}h {minutes}m {secs}s"


def _generate_report_from_stats(stats: UsageStats, completed_steps_count: Optional[int] = None) -> str:
    """Generate markdown report from a UsageStats object.
    
    This is a helper that generates report content from stats data,
    used both for live stats and for saved/interrupted sessions.
    
    Args:
        stats: UsageStats object with the data to report
        completed_steps_count: Number of completed steps (optional)
    
    Returns:
        Formatted markdown string with usage report
    """
    # Calculate duration using cumulative elapsed time (which handles interruptions)
    if stats.cumulative_elapsed_time > 0:
        duration_secs = stats.cumulative_elapsed_time
        duration_str = _format_duration(duration_secs)
    elif stats.start_time > 0:
        # Fallback to start_time calculation for legacy compatibility
        end = stats.end_time if stats.end_time > 0 else time.time()
        duration_secs = end - stats.start_time
        duration_str = _format_duration(duration_secs)
    else:
        duration_str = "N/A"
    
    # Determine status based on run_status field
    if stats.run_status == "success":
        status = "success"
    elif stats.run_status == "interrupted":
        status = "interrupted"
    elif stats.run_status == "fail":
        status = "fail"
    elif stats.end_time > 0:
        # If end_time is set but no status, assume interrupted (legacy behavior)
        status = "interrupted"
    else:
        # Still running
        status = "In Progress"
    
    total_tokens = stats.input_tokens + stats.output_tokens
    
    # Calculate average tokens per step if we have step count
    avg_input_tokens = None
    avg_output_tokens = None
    if completed_steps_count and completed_steps_count > 0:
        avg_input_tokens = stats.input_tokens / completed_steps_count
        avg_output_tokens = stats.output_tokens / completed_steps_count
    
    # Model info
    model_info = stats.model_name if stats.model_name else "Unknown"
    
    # Check if costs are available
    has_costs = stats.input_cost_per_million is not None and stats.output_cost_per_million is not None
    
    # Load run settings
    settings = _load_run_settings()
    
    # Override with stats-specific settings if available (especially for historical blocks)
    if stats.model_name:
        settings['MODEL'] = stats.model_name
    if stats.accuracy:
        settings['ACCURACY'] = stats.accuracy
    if stats.granularity:
        settings['GRANULARITY'] = stats.granularity
    if stats.enable_rag is not None:
        settings['ENABLE_RAG'] = str(stats.enable_rag).lower()
    
    # Check Materials Project API key availability
    mp_api_available = "Yes" if settings.get('PMG_MAPI_KEY') else "No"
    
    # Get hardware info from stats if available, otherwise fetch live
    if stats.hardware_signature:
        hw_sig = stats.hardware_signature
        hardware_info = f"- CPU: {hw_sig.get('cpu_model', 'N/A')}\n- Physical cores: {hw_sig.get('cpu_cores', 'N/A')}\n- GPU: {hw_sig.get('gpu_info', 'N/A')}"
    else:
        try:
            from .agents.utils import get_hardware_info
            hardware_info = get_hardware_info()
        except Exception:
            hardware_info = "N/A"
    
    # Generate report
    report = f"""# QUASAR Usage Report

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Model:** {model_info}  
**Run Duration:** {duration_str}  
**Status:** {status}

## Run Settings

| Setting | Value |
|---------|-------|
| Model | {settings.get('MODEL', 'N/A')} |
| Accuracy Mode | {settings.get('ACCURACY', 'N/A')} |
| Granularity | {settings.get('GRANULARITY', 'N/A')} |
| Check-in Interval | {settings.get('CHECK_INTERVAL', '15')} minutes |
| RAG Enabled | {settings.get('ENABLE_RAG', 'N/A')} |
| Materials Project API | {mp_api_available} |

## System Information

{hardware_info}

## API Usage

| Metric | Value |
|--------|-------|
| Total API Requests | {stats.api_request_count:,} |
| Input Tokens | {stats.input_tokens:,} |
| Output Tokens | {stats.output_tokens:,} |
| **Total Tokens** | **{total_tokens:,}** |
"""
    
    # Add average tokens per step if available
    if avg_input_tokens is not None and avg_output_tokens is not None:
        report += f"""| Completed Steps | {completed_steps_count} |
| Avg Input Tokens/Step | {avg_input_tokens:,.1f} |
| Avg Output Tokens/Step | {avg_output_tokens:,.1f} |

"""
    else:
        report += "\n"
    
    # Only include cost estimate section if costs are available
    if has_costs:
        input_cost = (stats.input_tokens / 1_000_000) * stats.input_cost_per_million
        output_cost = (stats.output_tokens / 1_000_000) * stats.output_cost_per_million
        total_cost = input_cost + output_cost
        
        report += f"""## Cost Estimate

| Type | Tokens | Rate ($/1M) | Cost |
|------|--------|-------------|------|
| Input | {stats.input_tokens:,} | ${stats.input_cost_per_million:.2f} | ${input_cost:.4f} |
| Output | {stats.output_tokens:,} | ${stats.output_cost_per_million:.2f} | ${output_cost:.4f} |
| **Total** | {total_tokens:,} | | **${total_cost:.4f}** |

*Note: Cost estimates based on ≤200k context pricing.*
"""
    
    return report


def _load_run_settings() -> dict:
    """Load run settings from checkpoint_settings.json or environment variables.
    
    Returns:
        Dictionary with run settings (MODEL, ACCURACY, GRANULARITY, etc.)
    """
    from .tools.base import WORKSPACE_DIR
    
    settings = {}
    
    # Try to load from checkpoint_settings.json first
    checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
    if checkpoint_settings_path.exists():
        try:
            with open(checkpoint_settings_path, 'r', encoding='utf-8') as f:
                checkpoint_settings = json.load(f)
                
                # Check top level first
                for key in ['MODEL', 'ACCURACY', 'GRANULARITY', 'ENABLE_RAG', 'CHECK_INTERVAL']:
                    if key in checkpoint_settings:
                        settings[key] = checkpoint_settings[key]
                
                # Overwrite with values from _usage_stats if present (more accurate for resumed runs)
                usage_stats = checkpoint_settings.get('_usage_stats', {})
                if usage_stats.get('model_name'):
                    settings['MODEL'] = usage_stats['model_name']
                if usage_stats.get('accuracy'):
                    settings['ACCURACY'] = usage_stats['accuracy']
                if usage_stats.get('granularity'):
                    settings['GRANULARITY'] = usage_stats['granularity']
                if usage_stats.get('enable_rag') is not None:
                    settings['ENABLE_RAG'] = str(usage_stats['enable_rag']).lower()
        except Exception:
            pass
    
    # Fall back to environment variables for any missing settings
    if 'MODEL' not in settings:
        settings['MODEL'] = os.getenv('MODEL', 'N/A')
    if 'ACCURACY' not in settings:
        settings['ACCURACY'] = os.getenv('ACCURACY', 'N/A')
    if 'GRANULARITY' not in settings:
        settings['GRANULARITY'] = os.getenv('GRANULARITY', 'N/A')
    if 'CHECK_INTERVAL' not in settings:
        settings['CHECK_INTERVAL'] = os.getenv('CHECK_INTERVAL', '15')
    if 'ENABLE_RAG' not in settings:
        settings['ENABLE_RAG'] = os.getenv('ENABLE_RAG', 'N/A')
    if 'PMG_MAPI_KEY' not in settings:
        settings['PMG_MAPI_KEY'] = os.getenv('PMG_MAPI_KEY', '')
    
    return settings


def generate_report(completed_steps_count: Optional[int] = None) -> str:
    """Generate markdown report of usage statistics, including history.
    
    Args:
        completed_steps_count: Number of completed steps (optional, for calculating averages)
    
    Returns:
        Formatted markdown string with current usage report and historical entries
    """
    stats = get_stats()
    
    # Try to get completed steps count from state if not provided
    if completed_steps_count is None:
        try:
            from .checkpoint import get_thread_config
            from .graph import get_or_create_graph
            from .llm_config import get_llm
            
            # Try to access the graph state to get completed steps
            llm = get_llm()
            graph = get_or_create_graph(llm)
            config = get_thread_config()
            state_values = graph.get_state(config).values if graph else {}
            completed_steps = state_values.get('completed_steps', [])
            completed_steps_count = len(completed_steps) if completed_steps else None
        except Exception:
            # If we can't access state, leave it as None
            pass
    
    # Generate the current session report
    current_report = _generate_report_from_stats(stats, completed_steps_count)
    
    # Load history from checkpoint_settings.json
    from .tools.base import WORKSPACE_DIR
    checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
    
    historical_reports = []
    if checkpoint_settings_path.exists():
        try:
            with open(checkpoint_settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            history = settings.get('_usage_stats_history', [])
            # Process history in reverse order (latest first) to prepend
            for hist_entry in reversed(history):
                # Create a temporary UsageStats from saved data
                hist_stats = UsageStats(
                    start_time=hist_entry.get('start_time', 0),
                    end_time=0,  # History entries usually don't have end_time set
                    cumulative_elapsed_time=hist_entry.get('cumulative_elapsed_time', 0),
                    api_request_count=hist_entry.get('api_request_count', 0),
                    input_tokens=hist_entry.get('input_tokens', 0),
                    output_tokens=hist_entry.get('output_tokens', 0),
                    input_cost_per_million=hist_entry.get('input_cost_per_million'),
                    output_cost_per_million=hist_entry.get('output_cost_per_million'),
                    model_name=hist_entry.get('model_name', ''),
                    accuracy=hist_entry.get('accuracy', ''),
                    granularity=hist_entry.get('granularity', ''),
                    enable_rag=hist_entry.get('enable_rag'),
                    run_status='interrupted', # Past entries were interrupted
                    hardware_signature=hist_entry.get('hardware_signature'),
                )
                hist_report = _generate_report_from_stats(hist_stats)
                historical_reports.append(hist_report)
        except Exception:
            pass
            
    # Combine reports. The current session (A) is prepended before history (B).
    if historical_reports:
        return current_report + "\n\n---\n\n" + "\n\n---\n\n".join(historical_reports)
    
    return current_report
