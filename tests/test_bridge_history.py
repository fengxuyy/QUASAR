from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from bridge_history import extract_checkpoint_history, format_tool_display


class _Snapshot:
    def __init__(self, values):
        self.values = values


def _build_task_messages(task_num: int):
    tool_id = f"read-{task_num}"
    return [
        AIMessage(
            content=f"Inspecting task {task_num} inputs.",
            tool_calls=[{
                "name": "read_file",
                "args": {"file_path": f"task_{task_num}.txt"},
                "id": tool_id,
            }],
        ),
        ToolMessage(content="Loaded task data.", tool_call_id=tool_id),
    ]


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
                "args": {"file_path": "task_1/run.py", "check_in_after": 30},
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
    code_results = [item for item in current_task_items if item["type"] == "code-result"]
    assert len(code_results) == 1
    cr = code_results[0]["content"]
    assert cr.get("status") == "Executed run.py"
    assert "Execution completed successfully" in cr["output"]
    assert not any("Read qe.out" in str(item.get("content", "")) for item in current_task_items)
    assert not any("converging" in str(item.get("content", "")).lower() for item in current_task_items)


def test_extract_checkpoint_history_merges_execute_python_validation_without_tool_message():
    """Invoke-time ValidationError yields AIMessage error only — merge into tool row for UI."""
    state_values = {
        "plan": ["Task 1: Run"],
        "completed_steps": [],
        "step_results": {},
    }
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "execute_python",
                "args": {},
                "id": "call-exec-bad",
            }],
        ),
        AIMessage(
            content="Validation error (1 issue): Field 'code': Field required",
        ),
    ]
    history = extract_checkpoint_history(state_values, messages)
    current = history["ordered_items_by_task"]["0"]
    assert len(current) == 1
    row = current[0]
    assert row["type"] == "tool"
    assert row["content"] == "Execute Python Failed"
    assert row.get("isError") is True
    assert row.get("output", "").startswith("Error: Validation error")


def test_extract_checkpoint_history_merges_temp_python_validation_without_tool_message():
    """execute_temporary_python validation failures should not recover as successful Executed rows."""
    state_values = {
        "plan": ["Task 1: Evaluate"],
        "completed_steps": [],
        "step_results": {},
    }
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "execute_temporary_python",
                "args": {},
                "id": "call-temp-bad",
            }],
        ),
        AIMessage(
            content="Validation error (1 issue): Field 'code': Field required",
        ),
    ]
    history = extract_checkpoint_history(state_values, messages)
    current = history["ordered_items_by_task"]["0"]
    assert len(current) == 1
    row = current[0]
    assert row["type"] == "tool"
    assert row["content"] == "Temporary Python Parse Failed"
    assert row.get("isError") is True
    assert row.get("output", "").startswith("Error: Validation error")


def test_extract_checkpoint_history_skips_removed_file_tools():
    state_values = {
        "plan": ["Task 1: Update files"],
        "completed_steps": [],
        "step_results": {},
    }
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"file_path": "out.py", "content": "print(1)"},
                    "id": "write-1",
                },
                {
                    "name": "move_file",
                    "args": {"source_path": "out.py", "destination_path": "archive/out.py"},
                    "id": "move-1",
                },
                {
                    "name": "rename_file",
                    "args": {"file_path": "old.py", "new_name": "new.py"},
                    "id": "rename-1",
                },
                {
                    "name": "delete_file",
                    "args": {"file_path": "old.tmp"},
                    "id": "delete-1",
                },
                {
                    "name": "execute_python",
                    "args": {"file_path": "run.py"},
                    "id": "exec-1",
                },
            ],
        ),
        ToolMessage(content="ok", tool_call_id="write-1"),
        ToolMessage(content="ok", tool_call_id="move-1"),
        ToolMessage(content="ok", tool_call_id="rename-1"),
        ToolMessage(content="ok", tool_call_id="delete-1"),
        ToolMessage(content="**Execution Result:**\n\nok", tool_call_id="exec-1"),
    ]

    history = extract_checkpoint_history(state_values, messages)
    current = history["ordered_items_by_task"]["0"]

    assert not any(
        item.get("name") in {"write_file", "move_file", "rename_file", "delete_file"}
        for item in current
    )
    assert any(
        item["type"] == "tool" and item["content"] == "Executed run.py"
        for item in current
    )


def test_extract_checkpoint_history_preserves_resume_steering_item():
    steering = "Let it run for another 30 minutes before interrupting."
    state_values = {
        "plan": ["Task 1: Run the simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [
            HumanMessage(content=(
                "[USER STEERING WHILE RESUMING]\n"
                "The user sent this message while the interrupted run was paused:\n\n"
                f"{steering}\n\n"
                "Use this to steer the remaining work from the current checkpoint."
            )),
        ],
    }

    history = extract_checkpoint_history(state_values, [])
    current = history["ordered_items_by_task"]["0"]

    assert any(
        item["type"] == "tool"
        and item["content"] == "User Steering Received"
        and item.get("output") == steering
        for item in current
    )


def test_extract_checkpoint_history_keeps_edit_file_status_on_not_found_error():
    state_values = {
        "plan": ["Task 1: Update file"],
        "completed_steps": [],
        "step_results": {},
    }
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "edit_file",
                "args": {
                    "file_path": "src/example.py",
                    "old_string": "print('old')",
                    "new_string": "print('new')",
                },
                "id": "edit-1",
            }],
        ),
        ToolMessage(
            content=(
                "**Edit File:** `src/example.py`\n\n> Error: The specified text to replace "
                "was not found in 'src/example.py'."
            ),
            tool_call_id="edit-1",
        ),
    ]

    history = extract_checkpoint_history(state_values, messages)
    current = history["ordered_items_by_task"]["0"]

    row = next(item for item in current if item["type"] == "tool")
    assert row["content"] == "Edited src/example.py"
    assert row.get("isError") is True
    assert row.get("output", "").startswith("```diff\n- print('old')\n+ print('new')\n```")


def test_extract_checkpoint_history_preserves_query_rag_output_for_collapsible_display():
    state_values = {
        "plan": ["Task 1: Query the local docs"],
        "completed_steps": [],
        "step_results": {},
    }
    rag_output = "## Match 1\n\nUse the embedding dimension from the model metadata."
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "query_rag",
                "args": {
                    "query": "embedding dimension",
                    "library": "docs",
                },
                "id": "rag-1",
            }],
        ),
        ToolMessage(content=rag_output, tool_call_id="rag-1"),
    ]

    history = extract_checkpoint_history(state_values, messages)
    current = history["ordered_items_by_task"]["0"]

    row = next(item for item in current if item["type"] == "tool")
    assert row["content"] == "Queried RAG embedding dimension in docs"
    assert row.get("output") == rag_output


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


def test_extract_checkpoint_history_marks_user_revised_final_plan():
    initial_plan = "<PLAN>\n### **Task 1:** Initial plan\n* **Guidance:** Start here.\n</PLAN>"
    reviewed_plan = "<PLAN>\n### **Task 1:** Reviewed plan\n* **Guidance:** Improved once.\n</PLAN>"
    revised_plan = "<PLAN>\n### **Task 1:** Revised plan\n* **Guidance:** Updated from user feedback.\n</PLAN>"

    state_values = {
        "plan": ["### **Task 1:** Revised plan\n**Guidance:** Updated from user feedback."],
        "completed_steps": [],
        "step_results": {},
    }
    messages = [
        HumanMessage(content="Original request"),
        AIMessage(content=initial_plan),
        HumanMessage(content="Please review your plan above and provide an improved version with the same format."),
        AIMessage(content=reviewed_plan),
        HumanMessage(
            content=(
                "Please revise your latest reviewed plan above based on the user's feedback below."
                " Keep the same format, preserve scientific rigor, and return the full updated plan.\n\n"
                "User feedback:\nSplit validation into a separate task."
            )
        ),
        AIMessage(content=revised_plan),
    ]

    history = extract_checkpoint_history(state_values, messages)

    assert history["initial_plan_text"] == initial_plan
    assert history["full_plan_text"] == revised_plan
    assert history["reviewed_plan_text"] == reviewed_plan
    assert history["final_plan_status"] == "Revised Plan from user feedback"
    assert history["final_plan_update_status"] == "Revising plan from user feedback"
    assert history["user_revised_plan_texts"] == [revised_plan]
    assert history["user_revised_plan_feedbacks"] == ["Split validation into a separate task."]


def test_extract_checkpoint_history_multiple_user_revisions_preserve_each_round():
    initial_plan = "<PLAN>\n### **Task 1:** Initial\n* **Guidance:** A\n</PLAN>"
    reviewed_plan = "<PLAN>\n### **Task 1:** Reviewed\n* **Guidance:** B\n</PLAN>"
    revised_once = "<PLAN>\n### **Task 1:** After feedback 1\n* **Guidance:** C\n</PLAN>"
    revised_twice = "<PLAN>\n### **Task 1:** After feedback 2\n* **Guidance:** D\n</PLAN>"
    revision_human = (
        "Please revise your latest reviewed plan above based on the user's feedback below."
        " Keep the same format, preserve scientific rigor, and return the full updated plan.\n\n"
        "User feedback:\n{fb}"
    )

    state_values = {
        "plan": ["### **Task 1:** After feedback 2\n**Guidance:** D."],
        "completed_steps": [],
        "step_results": {},
    }
    messages = [
        HumanMessage(content="Original request"),
        AIMessage(content=initial_plan),
        HumanMessage(content="Please review your plan above and provide an improved version with the same format."),
        AIMessage(content=reviewed_plan),
        HumanMessage(content=revision_human.format(fb="First round")),
        AIMessage(content=revised_once),
        HumanMessage(content=revision_human.format(fb="Second round")),
        AIMessage(content=revised_twice),
    ]

    history = extract_checkpoint_history(state_values, messages)

    assert history["reviewed_plan_text"] == reviewed_plan
    assert history["user_revised_plan_texts"] == [revised_once, revised_twice]
    assert history["user_revised_plan_feedbacks"] == ["First round", "Second round"]
    assert history["full_plan_text"] == revised_twice
    assert history["final_plan_status"] == "Revised Plan from user feedback"


def test_extract_checkpoint_history_user_revision_from_state_history_when_messages_truncated():
    """Summarized checkpoints may drop strategist revision prompts; snapshots can retain them."""
    initial_plan = "<PLAN>\n### **Task 1:** Initial\n* **Guidance:** A\n</PLAN>"
    reviewed_plan = "<PLAN>\n### **Task 1:** Reviewed\n* **Guidance:** B\n</PLAN>"
    revised_plan = "<PLAN>\n### **Task 1:** Revised\n* **Guidance:** C\n</PLAN>"
    revision_human = (
        "Please revise your latest reviewed plan above based on the user's feedback below."
        " Keep the same format, preserve scientific rigor, and return the full updated plan.\n\n"
        "User feedback:\nPlease add validation."
    )

    full_planner_messages = [
        HumanMessage(content="Original request"),
        AIMessage(content=initial_plan),
        HumanMessage(
            content="Please review your plan above and provide an improved version with the same format."
        ),
        AIMessage(content=reviewed_plan),
        HumanMessage(content=revision_human),
        AIMessage(content=revised_plan),
        AIMessage(
            content="",
            tool_calls=[{"name": "read_file", "args": {"file_path": "x.txt"}, "id": "t1"}],
        ),
        ToolMessage(content="ok", tool_call_id="t1"),
    ]
    truncated_messages = full_planner_messages[-2:]

    state_values = {
        "plan": ["### **Task 1:** Revised\n**Guidance:** C."],
        "completed_steps": [],
        "step_results": {},
    }
    state_history = [
        _Snapshot({
            "messages": full_planner_messages,
            "plan": state_values["plan"],
            "completed_steps": [],
            "step_results": {},
        })
    ]

    history = extract_checkpoint_history(
        state_values,
        truncated_messages,
        state_history=state_history,
    )

    assert history["final_plan_status"] == "Revised Plan from user feedback"
    assert history["user_revised_plan_texts"] == [revised_plan]
    assert history["user_revised_plan_feedbacks"] == ["Please add validation."]
    assert history["reviewed_plan_text"] == reviewed_plan


def test_extract_checkpoint_history_recovers_full_task_timelines_from_state_history():
    plan = [f"Task {i}: Step {i}" for i in range(1, 7)]
    completed_steps = plan[:5]
    step_results = {i: f"Summary {i + 1}" for i in range(5)}

    state_values = {
        "plan": plan,
        "completed_steps": completed_steps,
        "step_results": step_results,
        "current_task_messages": _build_task_messages(6),
        "evaluation_messages": [],
    }

    state_history = [
        _Snapshot({
            "plan": plan,
            "completed_steps": plan[:4],
            "step_results": {i: f"Summary {i + 1}" for i in range(4)},
            "current_task_messages": _build_task_messages(5),
            "evaluation_messages": [],
        }),
        _Snapshot({
            "plan": plan,
            "completed_steps": plan[:3],
            "step_results": {i: f"Summary {i + 1}" for i in range(3)},
            "current_task_messages": _build_task_messages(4),
            "evaluation_messages": [],
        }),
        _Snapshot({
            "plan": plan,
            "completed_steps": plan[:2],
            "step_results": {i: f"Summary {i + 1}" for i in range(2)},
            "current_task_messages": _build_task_messages(3),
            "evaluation_messages": [],
        }),
        _Snapshot({
            "plan": plan,
            "completed_steps": plan[:1],
            "step_results": {0: "Summary 1"},
            "current_task_messages": _build_task_messages(2),
            "evaluation_messages": [],
        }),
        _Snapshot({
            "plan": plan,
            "completed_steps": [],
            "step_results": {},
            "current_task_messages": _build_task_messages(1),
            "evaluation_messages": [],
        }),
    ]

    history = extract_checkpoint_history(
        state_values,
        [],
        state_history=state_history,
    )

    assert set(history["ordered_items_by_task"].keys()) == {"0", "1", "2", "3", "4", "5"}
    assert any(
        item["type"] == "tool" and item["content"] == "Read task_2.txt"
        for item in history["ordered_items_by_task"]["1"]
    )
    assert any(
        item["type"] == "tool" and item["content"] == "Read task_4.txt"
        for item in history["ordered_items_by_task"]["3"]
    )
    assert any(
        item["type"] == "tool" and item["content"] == "Read task_6.txt"
        for item in history["ordered_items_by_task"]["5"]
    )
