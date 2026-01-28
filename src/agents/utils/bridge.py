"""
Bridge communication utilities for CLI/web interface.
"""


def send_agent_event(agent: str, event: str, status: str = "", is_error: bool = False, output: str = "") -> None:
    """Send agent lifecycle event to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        event: Event type (e.g., 'step_complete', 'update', 'start', 'complete')
        status: Status text to display
        is_error: Whether this event represents an error (for step_complete display)
        output: Optional output text to show in collapsible section (for step_complete events)
    """
    try:
        import bridge
        bridge.send_agent_event(agent, event, status, is_error, output)
    except ImportError:
        pass  # Running outside bridge context
    except Exception:
        pass  # Events are for UI only, don't fail


def send_json(type_: str, payload: dict) -> None:
    """Send JSON message to CLI."""
    try:
        import bridge
        bridge.send_json(type_, payload)
    except ImportError:
        pass  # Running outside bridge context


def send_plan_stream(content: str, is_complete: bool = False, parsed_plan: list = None, is_replanning: bool = False) -> None:
    """Send streaming plan content to CLI.
    
    Args:
        content: Raw streaming content (for display during streaming)
        is_complete: Whether the plan is complete
        parsed_plan: Optional list of parsed task strings (sent when complete)
        is_replanning: Whether this is a replanning operation (vs initial plan or review)
    """
    try:
        import bridge
        bridge.send_plan_stream(content, is_complete, parsed_plan, is_replanning)
    except ImportError:
        pass  # Running outside bridge context


def send_text_stream(agent: str, content: str, is_complete: bool = False) -> None:
    """Send streaming LLM text content to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        content: Accumulated text content
        is_complete: Whether the streaming is complete
    """
    try:
        import bridge
        bridge.send_text_stream(agent, content, is_complete)
    except ImportError:
        pass  # Running outside bridge context


def send_thought_stream(agent: str, content: str, is_complete: bool = False) -> None:
    """Send streaming LLM thought content to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        content: Accumulated thought content
        is_complete: Whether the streaming is complete
    """
    try:
        import bridge
        bridge.send_thought_stream(agent, content, is_complete)
    except ImportError:
        pass  # Running outside bridge context
