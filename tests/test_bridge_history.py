from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from bridge_history import extract_checkpoint_history


def test_extract_checkpoint_history_skips_transient_checkin_session_messages():
    state_values = {
        "plan": ["Task 1: Run the simulation"],
        "completed_steps": [],
        "step_results": {},
    }
    messages = [
        AIMessage(
            content="Launching the simulation now.",
            tool_calls=[{
                "name": "execute_python",
                "args": {"file_path": "task_1/run.py", "timeout": 600},
                "id": "exec-1",
            }],
        ),
        HumanMessage(
            content=(
                "The Python script `run.py` has been running for 30 minutes.\n\n"
                "**Current Resource Usage:**\nCPU 0%"
            )
        ),
        AIMessage(
            content="I will inspect the output before deciding.",
            tool_calls=[{
                "name": "read_file",
                "args": {"file_path": "task_1/qe.out"},
                "id": "check-read-1",
            }],
        ),
        ToolMessage(content="Found 20 lines", tool_call_id="check-read-1"),
        AIMessage(
            content="The run is still converging and should continue.",
            tool_calls=[{
                "name": "continue_execution",
                "args": {"summary": "Converging normally"},
                "id": "check-continue-1",
            }],
        ),
        ToolMessage(
            content="CONTINUE_EXECUTION\nSUMMARY: Converging normally",
            tool_call_id="check-continue-1",
        ),
        ToolMessage(
            content="**Execution Result:**\n\nExecution completed successfully.",
            tool_call_id="exec-1",
        ),
    ]

    history = extract_checkpoint_history(state_values, messages)
    current_task_items = history["ordered_items_by_task"]["0"]

    assert any(
        item["type"] == "tool" and item["content"] == "Executed task_1/run.py"
        for item in current_task_items
    )
    assert any(item["type"] == "code-result" for item in current_task_items)
    assert not any("Read qe.out" in str(item.get("content", "")) for item in current_task_items)
    assert not any("converging" in str(item.get("content", "")).lower() for item in current_task_items)


def test_extract_checkpoint_history_adds_interrupt_reason_from_compact_checkin_summary():
    state_values = {
        "plan": ["Task 1: Run the simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [
            HumanMessage(
                content=(
                    "[EXECUTION CHECK-IN SUMMARY]\n"
                    "Script: `run.py`\n"
                    "Elapsed: 42 minutes\n"
                    "Decision: interrupt_execution\n"
                    "Reason: The job appears stalled with no meaningful progress.\n"
                    "Summary: CPU utilization is near idle."
                )
            )
        ],
    }

    history = extract_checkpoint_history(state_values, [])
    current_task_items = history["ordered_items_by_task"]["0"]

    assert current_task_items == [{
        "type": "tool",
        "content": "Interrupted Execution",
        "output": "The job appears stalled with no meaningful progress.",
        "agent": "operator",
        "isError": True,
    }]
