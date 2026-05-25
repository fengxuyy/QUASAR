from unittest.mock import MagicMock, patch, call

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


class _FakeLLM:
    def __init__(self):
        self.bound_tool_names = []

    def bind_tools(self, tools):
        self.bound_tool_names.append([tool.name for tool in tools])
        return self


def test_strategist_and_evaluator_tool_maps_include_temp_python_only():
    from src.agents.strategist import STRATEGIST_TOOL_MAP_NORMAL, STRATEGIST_TOOL_MAP_REPLANNING
    from src.agents.evaluator import EVALUATOR_TOOL_MAP
    from src.agents.operator import TOOL_MAP as OPERATOR_TOOL_MAP

    assert "execute_temporary_python" in STRATEGIST_TOOL_MAP_NORMAL
    assert "execute_temporary_python" in STRATEGIST_TOOL_MAP_REPLANNING
    assert "execute_temporary_python" in EVALUATOR_TOOL_MAP

    assert "execute_python" not in STRATEGIST_TOOL_MAP_NORMAL
    assert "execute_python" not in STRATEGIST_TOOL_MAP_REPLANNING
    assert "execute_python" not in EVALUATOR_TOOL_MAP

    removed_file_tools = {"write_file", "move_file", "rename_file", "delete_file"}
    assert removed_file_tools.isdisjoint(OPERATOR_TOOL_MAP)


def test_graph_binds_temp_python_for_strategist_and_evaluator_only():
    from src.graph import build_graph

    fake_llm = _FakeLLM()
    build_graph(fake_llm)

    assert len(fake_llm.bound_tool_names) == 4
    strategist_normal, strategist_replanning, operator_tools, evaluator_tools = fake_llm.bound_tool_names

    assert "execute_temporary_python" in strategist_normal
    assert "execute_temporary_python" in strategist_replanning
    assert "execute_temporary_python" in evaluator_tools
    assert "execute_python" not in strategist_normal
    assert "execute_python" not in strategist_replanning
    assert "execute_python" not in evaluator_tools
    assert "execute_python" in operator_tools

    removed_file_tools = {"write_file", "move_file", "rename_file", "delete_file"}
    assert removed_file_tools.isdisjoint(operator_tools)


def test_evaluator_prompt_allows_temp_python_for_parse_only():
    from src.agents.evaluator import evaluator_setup_node

    state = {
        "plan": ["Task: Evaluate outputs"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [AIMessage(content="Inspected output files and compared energies.")],
        "evaluation_attempts": 0,
        "messages": [],
        "user_input": "Check whether the calculation completed correctly.",
    }

    with patch("src.agents.evaluator.send_agent_event"), \
         patch("src.agents.evaluator._write_input_messages"):
        result = evaluator_setup_node(state, llm_with_tools=MagicMock())

    prompt = result["evaluation_messages"][0].content
    assert "execute_temporary_python" in prompt
    assert "temporary parsing of existing files only" in prompt
    assert "not to run simulations" in prompt
    assert "modify files/system state" in prompt


def test_strategist_prompt_allows_temp_python_for_parse_only(monkeypatch, mock_workspace):
    from src.agents.strategist import strategist_initial_node

    monkeypatch.setenv("ACCURACY", "standard")
    monkeypatch.setenv("GRANULARITY", "medium")

    state = {"user_input": "Plan a workflow to assess the uploaded calculation outputs."}
    llm = MagicMock()

    with patch("src.agents.strategist.WORKSPACE_DIR", mock_workspace), \
         patch("src.agents.strategist.get_all_files", return_value={"results/output.log"}), \
         patch("src.agents.strategist.stream_with_token_tracking", return_value=(
             "<PLAN>\n### **Task 1:** Inspect outputs\n**Guidance:** Parse existing files only.\n</PLAN>",
             [],
             None,
             None,
         )), \
         patch("src.agents.strategist.send_plan_stream"), \
         patch("src.agents.strategist.send_thought_stream"), \
         patch("src.agents.strategist.send_agent_event"), \
         patch("src.agents.strategist._write_input_messages"), \
         patch("src.agents.strategist.log_agent_header"), \
         patch("src.agents.strategist._write_to_log"), \
         patch("src.agents.strategist.log_strategist_start"), \
         patch("src.agents.strategist.log_strategist_return"), \
         patch("src.agents.strategist.log_custom"), \
         patch("src.agents.strategist.log_exception"):
        result = strategist_initial_node(state, llm)

    prompt = result["messages"][0].content
    assert "execute_temporary_python" in prompt
    assert "parse existing files and summarise their contents" in prompt
    assert "Never use it to run simulations" in prompt
    assert "modify files" in prompt


def test_temp_python_status_uses_execute_python_style_code_preview():
    from src.agents.utils.tool_helpers import format_tool_status

    status_msg, status_is_error = format_tool_status(
        "execute_temporary_python",
        {"code": "print('parsed')"},
        is_complete=False,
    )
    complete_msg, complete_is_error = format_tool_status(
        "execute_temporary_python",
        {"code": "print('parsed')"},
        is_complete=True,
        tool_result="**Execution Result:**\n\nCode executed successfully.",
    )

    assert status_msg == "Executing print('parsed')"
    assert complete_msg == "Executed print('parsed')"
    assert status_is_error is False
    assert complete_is_error is False


def test_temp_python_validation_status_marks_failed_with_detail():
    from src.agents.utils.tool_helpers import format_tool_status, update_agent_status

    validation = "Validation error (1 issue): Field 'code': Field required"

    status_msg, is_error = format_tool_status(
        "execute_temporary_python",
        {},
        is_complete=True,
        tool_result=validation,
    )

    assert status_msg == "Temporary Python Parse Failed: Field 'code': Field required"
    assert is_error is True

    with patch("src.agents.utils.tool_helpers.send_agent_event") as mock_send:
        update_agent_status(
            "evaluator",
            "execute_temporary_python",
            {},
            is_complete=True,
            tool_result=validation,
        )

    assert mock_send.call_args_list[0] == call(
        "evaluator",
        "step_complete",
        "Temporary Python Parse Failed: Field 'code': Field required",
        is_error=True,
        output=f"Error: {validation}",
        tool_name="execute_temporary_python",
    )


def test_operator_checkin_temp_python_uses_code_preview_status_events():
    from src.agents.operator import _send_checkin_tool_status

    with patch("src.agents.operator.send_agent_event") as mock_send:
        _send_checkin_tool_status(
            "execute_temporary_python",
            {"code": "print('parsed')"},
            is_complete=False,
        )
        _send_checkin_tool_status(
            "execute_temporary_python",
            {"code": "print('parsed')"},
            is_complete=True,
            tool_result="**Execution Result:**\n\nCode executed successfully.",
            elapsed_display="12 minutes",
        )

    assert mock_send.call_args_list == [
        call("operator", "update", "Executing print('parsed')", is_error=False),
        call("operator", "step_complete", "Executed print('parsed')", is_error=False),
        call("operator", "update", "Awaiting decision after 12 minutes"),
    ]


def test_operator_injects_resume_steering_into_llm_context(mock_workspace):
    from src.agents.operator import RESUME_STEERING_MARKER, operator_node

    steering = "Let the running job continue for 30 more minutes unless output stalls."
    state = {
        "plan": ["Task 1: Run the simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Run the current simulation task."),
        ],
        "messages": [],
        "user_input": "Run the simulation and monitor it.",
        "resume_steering": steering,
    }

    response = AIMessage(content="I will account for that steering.", tool_calls=[])
    stream_inputs = []

    def fake_stream_with_token_tracking(_llm, messages, **_kwargs):
        stream_inputs.append(messages)
        return response.content, response.tool_calls, response, False

    with patch("src.agents.operator.stream_with_token_tracking", side_effect=fake_stream_with_token_tracking), \
         patch("src.agents.operator.maybe_summarize_messages", side_effect=lambda messages, *_args, **_kwargs: (messages, False, "gemini-2.5-pro", 200_000)), \
         patch("src.agents.operator.load_pending_execution", return_value=None), \
         patch("src.agents.operator.was_hardware_changed_on_resume", return_value=False), \
         patch("src.agents.operator.detect_repeated_tool_calls", return_value=None), \
         patch("src.agents.operator.send_agent_event") as mock_send_agent_event, \
         patch("src.agents.operator.send_json"), \
         patch("src.agents.operator.send_text_stream"), \
         patch("src.agents.operator.send_thought_stream"), \
         patch("src.agents.operator._write_input_messages"), \
         patch("src.agents.operator._write_to_log"), \
         patch("src.agents.operator.log_operator_start"), \
         patch("src.agents.operator.write_execution_log"), \
         patch("src.agents.operator.log_custom"), \
         patch("src.agents.operator.update_operator_status"):
        result = operator_node(state, MagicMock(), all_tools=[])

    assert stream_inputs
    assert any(
        isinstance(message, HumanMessage)
        and RESUME_STEERING_MARKER in message.content
        and steering in message.content
        for message in stream_inputs[0]
    )
    assert result["resume_steering"] == ""
    assert call(
        "operator",
        "step_complete",
        "User Steering Received",
        output=steering,
    ) in mock_send_agent_event.call_args_list


def test_operator_validation_error_is_appended_as_tool_message(mock_workspace):
    from src.agents.operator import operator_node

    state = {
        "plan": ["Task 1: Run the simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Run the current simulation task."),
        ],
        "messages": [],
        "user_input": "Run the simulation and monitor it.",
    }

    response = AIMessage(
        content="I will run the script.",
        tool_calls=[{
            "name": "execute_python",
            "args": {"code": "print('start')", "omp_num_threads": 1},
            "id": "call-missing-checkin",
        }],
    )
    written_messages = []

    def fake_stream_with_token_tracking(_llm, messages, **_kwargs):
        return response.content, response.tool_calls, response, False

    def fake_write_input_messages(messages, *_args, **_kwargs):
        written_messages.append(messages)

    with patch("src.agents.operator.stream_with_token_tracking", side_effect=fake_stream_with_token_tracking), \
         patch("src.agents.operator.load_pending_execution", return_value=None), \
         patch("src.agents.operator.was_hardware_changed_on_resume", return_value=False), \
         patch("src.agents.operator.detect_repeated_tool_calls", return_value=None), \
         patch("src.agents.operator.save_pending_execution") as mock_save_pending, \
         patch("src.agents.operator.clear_pending_execution") as mock_clear_pending, \
         patch("src.agents.operator.send_agent_event") as mock_send_agent_event, \
         patch("src.agents.operator.send_json"), \
         patch("src.agents.operator.send_text_stream"), \
         patch("src.agents.operator.send_thought_stream"), \
         patch("src.agents.operator._write_input_messages", side_effect=fake_write_input_messages), \
         patch("src.agents.operator._write_to_log"), \
         patch("src.agents.operator.log_operator_start"), \
         patch("src.agents.operator.write_execution_log"), \
         patch("src.agents.operator.log_custom"), \
         patch("src.agents.operator.update_operator_status"):
        result = operator_node(state, MagicMock(), all_tools=[])

    mock_save_pending.assert_called_once()
    mock_clear_pending.assert_called_once()

    messages_update = result["messages"]
    assert messages_update[0] is response
    assert isinstance(messages_update[1], ToolMessage)
    assert messages_update[1].tool_call_id == "call-missing-checkin"
    assert "Field 'check_in_after': Field required" in messages_update[1].content

    task_messages = result["current_task_messages"]
    assert task_messages[-2] is response
    assert task_messages[-1] is messages_update[1]
    assert written_messages[-1][-1] is messages_update[1]

    assert call(
        "operator",
        "error",
        "Error: Validation error (1 issue): Field 'check_in_after': Field required",
        tool_name="execute_python",
    ) in mock_send_agent_event.call_args_list


def test_operator_checkin_compacts_history_and_summarizes_before_next_iteration(mock_workspace):
    from src.agents.operator import operator_node

    script_path = mock_workspace / "task_1" / "run.py"
    checkin_result = {
        "status": "check_in_required",
        "elapsed_display": "10 minutes",
        "file_path": str(script_path),
        "resource_usage": "PID 1234 (python): CPU 99%",
    }
    final_result = "**Execution Result:**\n\nCompleted successfully."

    initial_messages = [
        SystemMessage(content="System prompt"),
        HumanMessage(content="Run the current simulation task."),
    ]
    state = {
        "plan": ["Task 1: Run the simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": initial_messages,
        "messages": [],
        "user_input": "Run the simulation and monitor it.",
    }

    operator_response = AIMessage(
        content="Launching the simulation now.",
        tool_calls=[{
            "name": "execute_python",
            "args": {"code": "print('start')", "check_in_after": 10},
            "id": "call-exec",
        }],
    )
    decision_response = AIMessage(
        content="The run is still progressing normally.",
        tool_calls=[{
            "name": "continue_execution",
            "args": {
                "summary": (
                    "SCF iterations are still advancing, CPU utilization remains high, "
                    "and no convergence warnings were observed."
                ),
                "next_check_in_after": 20,
            },
            "id": "call-continue",
        }],
    )

    stream_inputs = []

    def fake_stream_with_token_tracking(_llm, messages, **_kwargs):
        stream_inputs.append(messages)
        if len(stream_inputs) == 1:
            return operator_response.content, operator_response.tool_calls, operator_response, False

        assert any(
            isinstance(message, HumanMessage) and "Continue this execution check-in" in message.content
            for message in messages
        )
        return decision_response.content, decision_response.tool_calls, decision_response, False

    summarize_inputs = []

    def fake_maybe_summarize_messages(
        messages,
        _llm,
        agent_name="",
        model_name=None,
        input_tokens=None,
        runtime_events=None,
        task_index=None,
    ):
        summarize_inputs.append({
            "messages": messages,
            "agent_name": agent_name,
            "model_name": model_name,
            "input_tokens": input_tokens,
        })
        if len(summarize_inputs) == 1:
            return (
                [
                    messages[0],
                    HumanMessage(content="[CONTEXT SUMMARY - condensed check-in context]"),
                ],
                True,
                "gemini-2.5-pro",
                800_000,
            )
        return messages, False, "gemini-2.5-pro", 200_000

    fake_execute_python_tool = MagicMock()
    fake_execute_python_tool.invoke.return_value = checkin_result

    llm_with_tools = MagicMock()
    llm_with_tools.bind_tools.return_value = MagicMock(name="checkin_llm")

    with patch("src.agents.operator.stream_with_token_tracking", side_effect=fake_stream_with_token_tracking), \
         patch("src.agents.operator.maybe_summarize_messages", side_effect=fake_maybe_summarize_messages), \
         patch("src.agents.operator.resume_execution", return_value=final_result) as mock_resume, \
         patch("src.agents.operator.save_pending_execution"), \
         patch("src.agents.operator.clear_pending_execution"), \
         patch("src.agents.operator.load_pending_execution", return_value=None), \
         patch("src.agents.operator.was_hardware_changed_on_resume", return_value=False), \
         patch("src.agents.operator.detect_repeated_tool_calls", return_value=None), \
         patch("src.agents.operator.send_agent_event") as mock_send, \
         patch("src.agents.operator.send_json"), \
         patch("src.agents.operator.send_text_stream"), \
         patch("src.agents.operator.send_thought_stream"), \
         patch("src.agents.operator._write_input_messages"), \
         patch("src.agents.operator._write_to_log"), \
         patch("src.agents.operator.log_operator_start"), \
         patch("src.agents.operator.write_execution_log"), \
         patch("src.agents.operator.log_tool_call"), \
         patch("src.agents.operator.log_custom"), \
         patch("src.agents.operator.update_operator_status"), \
         patch.dict("src.agents.operator.TOOL_MAP", {"execute_python": fake_execute_python_tool}, clear=False):
        result = operator_node(state, llm_with_tools, all_tools=[])

    mock_resume.assert_called_once_with(check_in_after=20)
    assert call(
        "operator",
        "update",
        "Executing print('start') (20 min check-in)",
    ) in mock_send.call_args_list
    assert len(stream_inputs) == 2
    assert len(summarize_inputs) == 2
    assert summarize_inputs[0]["agent_name"] == "operator"
    assert "The Python script `run.py` has been running for 10 minutes." in summarize_inputs[0]["messages"][-1].content

    persisted_messages = result["current_task_messages"]
    compact_history = [
        message for message in persisted_messages
        if isinstance(message, HumanMessage) and "[EXECUTION CHECK-IN SUMMARY]" in message.content
    ]
    assert len(compact_history) == 1
    assert "Decision: continue_execution" in compact_history[0].content
    assert "Next check-in: 20 minutes" in compact_history[0].content
    assert "SCF iterations are still advancing" in compact_history[0].content

    assert not any(
        isinstance(message, HumanMessage)
        and "The Python script `run.py` has been running for 10 minutes." in message.content
        for message in persisted_messages
    )
    assert not any(
        isinstance(message, HumanMessage)
        and "Continue this execution check-in" in message.content
        for message in persisted_messages
    )
    assert not any(
        isinstance(message, ToolMessage) and "CONTINUE_EXECUTION" in message.content
        for message in persisted_messages
    )


def test_operator_checkin_interrupt_compacts_history_with_reason_and_summary(mock_workspace):
    from src.agents.operator import operator_node

    script_path = mock_workspace / "task_1" / "run.py"
    checkin_result = {
        "status": "check_in_required",
        "elapsed_display": "42 minutes",
        "file_path": str(script_path),
        "resource_usage": "PID 1234 (python): CPU 1%",
    }
    interrupt_result = "**Execution Result:**\n\nExecution was interrupted."

    state = {
        "plan": ["Task 1: Run the simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Run the current simulation task."),
        ],
        "messages": [],
        "user_input": "Run the simulation and monitor it.",
    }

    operator_response = AIMessage(
        content="Launching the simulation now.",
        tool_calls=[{
            "name": "execute_python",
            "args": {"code": "print('start')", "check_in_after": 10},
            "id": "call-exec",
        }],
    )
    decision_response = AIMessage(
        content=(
            "The output is idle and appears stalled. Output growth stopped, CPU utilization "
            "is near idle, and the run should be stopped."
        ),
        tool_calls=[{
            "name": "interrupt_execution",
            "args": {
                "reason": "The job appears stalled with no meaningful progress.",
            },
            "id": "call-interrupt",
        }],
    )

    stream_inputs = []

    def fake_stream_with_token_tracking(_llm, messages, **_kwargs):
        stream_inputs.append(messages)
        if len(stream_inputs) == 1:
            return operator_response.content, operator_response.tool_calls, operator_response, False
        return decision_response.content, decision_response.tool_calls, decision_response, False

    fake_execute_python_tool = MagicMock()
    fake_execute_python_tool.invoke.return_value = checkin_result

    llm_with_tools = MagicMock()
    llm_with_tools.bind_tools.return_value = MagicMock(name="checkin_llm")

    with patch("src.agents.operator.stream_with_token_tracking", side_effect=fake_stream_with_token_tracking), \
         patch("src.agents.operator.maybe_summarize_messages", side_effect=lambda messages, *_args, **_kwargs: (messages, False, "gemini-2.5-pro", 200_000)), \
         patch("src.agents.operator.interrupt_running_execution", return_value=interrupt_result) as mock_interrupt, \
         patch("src.agents.operator.save_pending_execution"), \
         patch("src.agents.operator.clear_pending_execution"), \
         patch("src.agents.operator.load_pending_execution", return_value=None), \
         patch("src.agents.operator.was_hardware_changed_on_resume", return_value=False), \
         patch("src.agents.operator.detect_repeated_tool_calls", return_value=None), \
         patch("src.agents.operator.send_agent_event") as mock_send_agent_event, \
         patch("src.agents.operator.send_json"), \
         patch("src.agents.operator.send_text_stream"), \
         patch("src.agents.operator.send_thought_stream"), \
         patch("src.agents.operator._write_input_messages"), \
         patch("src.agents.operator._write_to_log"), \
         patch("src.agents.operator.log_operator_start"), \
         patch("src.agents.operator.write_execution_log"), \
         patch("src.agents.operator.log_tool_call"), \
         patch("src.agents.operator.log_custom"), \
         patch("src.agents.operator.update_operator_status"), \
         patch.dict("src.agents.operator.TOOL_MAP", {"execute_python": fake_execute_python_tool}, clear=False):
        result = operator_node(state, llm_with_tools, all_tools=[])

    mock_interrupt.assert_called_once_with("The job appears stalled with no meaningful progress.")
    assert call(
        "operator",
        "step_complete",
        "Interrupted Execution",
        is_error=True,
        output="The job appears stalled with no meaningful progress.",
    ) in mock_send_agent_event.call_args_list

    persisted_messages = result["current_task_messages"]
    compact_history = [
        message for message in persisted_messages
        if isinstance(message, HumanMessage) and "[EXECUTION CHECK-IN SUMMARY]" in message.content
    ]
    assert len(compact_history) == 1
    assert "Decision: interrupt_execution" in compact_history[0].content
    assert "Reason: The job appears stalled with no meaningful progress." in compact_history[0].content
    assert "CPU utilization is near idle" in compact_history[0].content
    assert not any(
        isinstance(message, ToolMessage) and "INTERRUPT_EXECUTION" in message.content
        for message in persisted_messages
    )
