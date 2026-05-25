import sys
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from src.runner import PromptRunResult
from src.resume_steering import checkpoint_allows_resume_steering, checkpoint_is_strategist_stage


class _FakeInterruptEvent:
    def clear(self):
        pass

    def is_set(self):
        return False


class _FakeGraph:
    def __init__(self, state_values, next_nodes=("operator",)):
        self.state_values = state_values
        self.next_nodes = next_nodes
        self.stream_inputs = []
        self.state_updates = []

    def get_state(self, _config):
        return SimpleNamespace(values=self.state_values, next=self.next_nodes)

    def update_state(self, config, values):
        self.state_updates.append(values)
        self.state_values.update(values)
        return {**config, "updated": True}

    def stream(self, inputs, config=None):
        self.stream_inputs.append(inputs)
        return iter(())


def test_resume_steering_allowed_for_operator_activity_without_next_node():
    state_values = {
        "plan": ["Task 1: Continue current simulation"],
        "completed_steps": [],
        "current_task_messages": [
            HumanMessage(content="Run the current simulation task."),
            AIMessage(content="I am inspecting the running job."),
        ],
    }

    assert checkpoint_allows_resume_steering((), state_values) is True


def test_resume_steering_not_allowed_for_evaluator_checkpoint_with_operator_history():
    state_values = {
        "plan": ["Task 1: Continue current simulation"],
        "completed_steps": [],
        "current_task_messages": [
            HumanMessage(content="Run the current simulation task."),
            AIMessage(content="DONE"),
        ],
    }

    assert checkpoint_allows_resume_steering(("evaluator_setup",), state_values) is False


def test_resume_steering_not_allowed_when_evaluator_has_active_context():
    state_values = {
        "plan": ["Task 1: Continue current simulation"],
        "completed_steps": [],
        "current_task_messages": [AIMessage(content="I am inspecting the running job.")],
        "evaluation_messages": [HumanMessage(content="Evaluate the result.")],
    }

    assert checkpoint_allows_resume_steering((), state_values) is False


def test_checkpoint_is_strategist_stage_before_workspace_work():
    state_values = {
        "plan": ["Task 1: Prepare the workspace"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [],
        "evaluation_messages": [],
        "files_at_task_start": [],
    }

    assert checkpoint_is_strategist_stage(("strategist_review",), state_values) is True
    assert checkpoint_is_strategist_stage(("plan_review_confirm",), state_values) is True


def test_checkpoint_is_not_strategist_stage_after_workspace_work_started():
    state_values = {
        "plan": ["Task 1: Prepare the workspace"],
        "completed_steps": ["Task 1: Prepare the workspace"],
        "step_results": {1: "Created input files"},
        "current_task_messages": [],
        "evaluation_messages": [],
        "files_at_task_start": ["input.in"],
    }

    assert checkpoint_is_strategist_stage(("strategist_initial",), state_values) is False


def test_checkpoint_is_not_strategist_stage_for_operator_node():
    state_values = {
        "plan": ["Task 1: Prepare the workspace"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [],
        "evaluation_messages": [],
        "files_at_task_start": [],
    }

    assert checkpoint_is_strategist_stage(("operator",), state_values) is False


def test_resume_steering_updates_current_task_not_global_messages(monkeypatch):
    import src.runner as runner

    existing_task_message = HumanMessage(content="Current task context")
    state_values = {
        "messages": [],
        "plan": ["Task 1: Continue current simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [existing_task_message],
    }
    graph = _FakeGraph(state_values)

    bridge_events = []
    fake_bridge = SimpleNamespace(
        interrupt_event=_FakeInterruptEvent(),
        send_checkpoint_status=lambda *_args, **_kwargs: None,
        consume_plan_declined=lambda: None,
        send_agent_event=lambda *args, **kwargs: bridge_events.append((args, kwargs)),
    )
    monkeypatch.setitem(sys.modules, "bridge", fake_bridge)

    monkeypatch.setattr(runner, "checkpoint_file_exists", lambda: True)
    monkeypatch.setattr(runner, "archive_exists_without_checkpoint", lambda: False)
    monkeypatch.setattr(runner, "is_connection_valid", lambda: True)
    monkeypatch.setattr(runner, "has_checkpoint_history", lambda _graph, _config: True)
    monkeypatch.setattr(runner, "get_thread_config", lambda: {"configurable": {"thread_id": "test"}})
    monkeypatch.setattr(runner, "get_or_create_graph", lambda _llm, agent_llms=None: graph)
    monkeypatch.setattr(runner, "log_resume_steering", lambda _text: None)
    monkeypatch.setattr(runner, "log_graph_stream_start", lambda _inputs: None)
    monkeypatch.setattr(runner, "log_custom", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "log_runner_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "set_run_status", lambda _status: None)

    import src.usage_tracker as usage_tracker

    monkeypatch.setattr(usage_tracker, "start_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(usage_tracker, "end_run", lambda: None)
    monkeypatch.setattr(usage_tracker, "load_stats_from_checkpoint", lambda: None)
    monkeypatch.setattr(usage_tracker, "generate_interrupted_report_if_needed", lambda: None)

    result = runner.process_prompt(
        "Let this continue, but use a 15 minute review cadence.",
        llm=object(),
        if_restart=False,
    )

    assert result == PromptRunResult(status="incomplete", auto_improve_eligible=False)
    assert len(graph.state_updates) == 1
    assert len(graph.stream_inputs) == 1

    state_update = graph.state_updates[0]
    assert "messages" not in state_update
    assert state_update["resume_steering"] == ""
    assert state_update["current_task_messages"][0] is existing_task_message
    assert any(
        isinstance(message, HumanMessage)
        and "[USER STEERING WHILE RESUMING]" in message.content
        and "15 minute review cadence" in message.content
        for message in state_update["current_task_messages"]
    )
    assert graph.stream_inputs[0] is None
    assert bridge_events == [
        (
            ("operator", "step_complete", "User Steering Received"),
            {"output": "Let this continue, but use a 15 minute review cadence."},
        )
    ]


def test_resume_steering_ignored_when_checkpoint_not_operator(monkeypatch):
    import src.runner as runner

    existing_task_message = HumanMessage(content="Current task context")
    state_values = {
        "messages": [],
        "plan": ["Task 1: Continue current simulation"],
        "completed_steps": [],
        "step_results": {},
        "current_task_messages": [existing_task_message],
    }
    graph = _FakeGraph(state_values, next_nodes=("evaluator_loop",))

    bridge_events = []
    fake_bridge = SimpleNamespace(
        interrupt_event=_FakeInterruptEvent(),
        send_checkpoint_status=lambda *_args, **_kwargs: None,
        consume_plan_declined=lambda: None,
        send_agent_event=lambda *args, **kwargs: bridge_events.append((args, kwargs)),
    )
    monkeypatch.setitem(sys.modules, "bridge", fake_bridge)

    monkeypatch.setattr(runner, "checkpoint_file_exists", lambda: True)
    monkeypatch.setattr(runner, "archive_exists_without_checkpoint", lambda: False)
    monkeypatch.setattr(runner, "is_connection_valid", lambda: True)
    monkeypatch.setattr(runner, "has_checkpoint_history", lambda _graph, _config: True)
    monkeypatch.setattr(runner, "get_thread_config", lambda: {"configurable": {"thread_id": "test"}})
    monkeypatch.setattr(runner, "get_or_create_graph", lambda _llm, agent_llms=None: graph)

    logged_steering = []
    monkeypatch.setattr(runner, "log_resume_steering", lambda text: logged_steering.append(text))
    monkeypatch.setattr(runner, "log_graph_stream_start", lambda _inputs: None)
    monkeypatch.setattr(runner, "log_custom", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "log_runner_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "set_run_status", lambda _status: None)

    import src.usage_tracker as usage_tracker

    monkeypatch.setattr(usage_tracker, "start_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(usage_tracker, "end_run", lambda: None)
    monkeypatch.setattr(usage_tracker, "load_stats_from_checkpoint", lambda: None)
    monkeypatch.setattr(usage_tracker, "generate_interrupted_report_if_needed", lambda: None)

    result = runner.process_prompt(
        "Change the evaluation criteria before continuing.",
        llm=object(),
        if_restart=False,
    )

    assert result == PromptRunResult(status="incomplete", auto_improve_eligible=False)
    assert graph.state_updates == []
    assert graph.stream_inputs == [None]
    assert graph.state_values["current_task_messages"] == [existing_task_message]
    assert bridge_events == []
    assert logged_steering == []
