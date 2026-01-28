"""
Shared utilities for agent nodes.

This package contains utilities organized into the following modules:
- system: CPU, GPU, and Slurm detection
- bridge: CLI/web interface communication
- text: Text extraction and formatting
- errors: Exception handling and API retry
- logging: Conversation and execution logging
- streaming: LLM streaming with token tracking
- tool_helpers: Tool status, extraction, and execution

All public APIs are re-exported here for backwards compatibility.
"""

# Re-export from system
from .system import (
    get_cpu_info,
    get_gpu_info,
    get_hardware_info,
    get_usable_physical_cores,
    _get_gpu_info,
)

# Re-export from bridge
from .bridge import (
    send_agent_event,
    send_json,
    send_plan_stream,
    send_text_stream,
    send_thought_stream,
)

# Re-export from text
from .text import (
    _extract_text,
    _safe_utf8_text,
    _get_message_content,
    _get_message_type,
    extract_project_request,
    format_plan,
    format_history,
    truncate_content,
)

# Re-export from errors
from .errors import (
    StreamingTimeoutError,
    APIConnectionError,
    FatalAPIError,
    ValidationError,
    format_validation_error,
    _sanitize_error_message,
    is_api_connection_error,
    handle_api_retry,
    _save_stats_on_system_interrupt,
)

# Re-export from logging
from .logging import (
    MAX_LOG_CHARS,
    _write_to_log,
    log_agent_header,
    log_tool_call,
    log_code_block,
    log_result,
    log_message,
    get_project_context,
    write_execution_log,
    _write_input_messages,
)

# Re-export from streaming
from .streaming import (
    stream_with_token_tracking,
    RepetitionDetector,
    StopGenerationException,
)

# Re-export from tool_helpers
from .tool_helpers import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_REPEATED_TOOL_CALLS,
    TOOL_STATUS_MESSAGES,
    AGENT_IDLE_STATUS,
    extract_tool_call_info,
    extract_target_name,
    extract_analyze_image_output,
    handle_analyze_image_status,
    format_tool_status,
    send_tool_status,
    update_agent_status,
    update_operator_status,
    detect_repeated_tool_calls,
    _execute_with_timeout,
    execute_with_timeout,
    execute_tool_with_logging,
)

__all__ = [
    # system
    'get_cpu_info',
    'get_gpu_info',
    'get_hardware_info',
    'get_usable_physical_cores',
    '_get_gpu_info',
    # bridge
    'send_agent_event',
    'send_json',
    'send_plan_stream',
    'send_text_stream',
    'send_thought_stream',
    # text
    '_extract_text',
    '_safe_utf8_text',
    '_get_message_content',
    '_get_message_type',
    'extract_project_request',
    'format_plan',
    'format_history',
    'truncate_content',
    # errors
    'StreamingTimeoutError',
    'APIConnectionError',
    'FatalAPIError',
    'ValidationError',
    'format_validation_error',
    '_sanitize_error_message',
    'is_api_connection_error',
    'handle_api_retry',
    '_save_stats_on_system_interrupt',
    # logging
    'MAX_LOG_CHARS',
    '_write_to_log',
    'log_agent_header',
    'log_tool_call',
    'log_code_block',
    'log_result',
    'log_message',
    'get_project_context',
    'write_execution_log',
    '_write_input_messages',
    # streaming
    'stream_with_token_tracking',
    'RepetitionDetector',
    'StopGenerationException',
    # tool_helpers
    'DEFAULT_TIMEOUT_SECONDS',
    'MAX_REPEATED_TOOL_CALLS',
    'TOOL_STATUS_MESSAGES',
    'AGENT_IDLE_STATUS',
    'extract_tool_call_info',
    'extract_target_name',
    'extract_analyze_image_output',
    'handle_analyze_image_status',
    'format_tool_status',
    'send_tool_status',
    'update_agent_status',
    'update_operator_status',
    'detect_repeated_tool_calls',
    '_execute_with_timeout',
    'execute_with_timeout',
    'execute_tool_with_logging',
]
