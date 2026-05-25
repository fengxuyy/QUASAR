import json
import sys
from unittest.mock import MagicMock

for module_name in (
    "langchain_google_genai",
    "langchain_anthropic",
    "langchain_xai",
):
    sys.modules.setdefault(module_name, MagicMock())

import bridge
from src.runner import PromptRunResult


def _read_checkpoint_settings(workspace):
    settings_path = workspace / "quasar_logs" / "checkpoint_settings.json"
    if not settings_path.exists():
        return {}
    return json.loads(settings_path.read_text(encoding="utf-8"))


def _capture_send_json(monkeypatch):
    events = []

    def fake_send_json(type_, payload):
        events.append((type_, payload))

    monkeypatch.setattr(bridge, "send_json", fake_send_json)
    return events


def _configure_bridge(monkeypatch):
    bridge._clear_auto_improve_state(persist=False)
    monkeypatch.setattr(bridge, "_bridge_llm_state", {"llm": object(), "agent_llms": {}})
    monkeypatch.setattr(bridge, "_graph_cache_stale", False)
    monkeypatch.setattr(bridge, "_emit_final_summary_if_needed", lambda: None)


def _install_process_prompt(monkeypatch, outcomes):
    calls = []
    iterator = iter(outcomes)

    def fake_process_prompt(prompt, llm, if_restart=False, agent_llms=None):
        calls.append({"prompt": prompt, "restart": if_restart})
        outcome = next(iterator)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(bridge.runner, "process_prompt", fake_process_prompt)
    return calls


def test_execute_prompt_sequence_with_zero_cycles_runs_once(mock_workspace, monkeypatch):
    monkeypatch.setenv("AUTO_IMPROVE_CYCLES", "0")
    _configure_bridge(monkeypatch)
    events = _capture_send_json(monkeypatch)
    calls = _install_process_prompt(
        monkeypatch,
        [PromptRunResult(status="success", auto_improve_eligible=True)],
    )

    bridge._execute_prompt_sequence("Initial request", restart=False)

    assert [call["prompt"] for call in calls] == ["Initial request"]
    assert [payload for type_, payload in events if type_ == "done"] == [{"status": "completed"}]
    settings = _read_checkpoint_settings(mock_workspace)
    assert settings["AUTO_IMPROVE_CYCLES"] == "0"
    assert bridge.AUTO_IMPROVE_STATE_KEY not in settings


def test_execute_prompt_sequence_chains_configured_auto_improve_cycles(mock_workspace, monkeypatch):
    monkeypatch.setenv("AUTO_IMPROVE_CYCLES", "2")
    _configure_bridge(monkeypatch)
    events = _capture_send_json(monkeypatch)
    calls = _install_process_prompt(
        monkeypatch,
        [
            PromptRunResult(status="success", auto_improve_eligible=True),
            PromptRunResult(status="success", auto_improve_eligible=True),
            PromptRunResult(status="success", auto_improve_eligible=True),
        ],
    )

    bridge._execute_prompt_sequence("Initial request", restart=False)

    assert [call["prompt"] for call in calls] == [
        "Initial request",
        bridge.runner.AUTO_IMPROVE_MESSAGE,
        bridge.runner.AUTO_IMPROVE_MESSAGE,
    ]
    assert len([payload for type_, payload in events if type_ == "done"]) == 1
    assert [payload for type_, payload in events if type_ == "done"] == [{"status": "completed"}]
    settings = _read_checkpoint_settings(mock_workspace)
    assert settings["AUTO_IMPROVE_CYCLES"] == "2"
    assert bridge.AUTO_IMPROVE_STATE_KEY not in settings


def test_begin_plan_confirmation_wait_auto_confirms_only_for_automatic_cycles(monkeypatch):
    _configure_bridge(monkeypatch)
    events = _capture_send_json(monkeypatch)

    bridge._set_auto_improve_state(
        {"remaining_cycles": 1, "current_run_is_automatic": True},
        persist=False,
    )
    assert bridge.begin_plan_confirmation_wait() == {"action": "confirm", "feedback": ""}
    assert [type_ for type_, _ in events] == []

    bridge._set_auto_improve_state(
        {"remaining_cycles": 0, "current_run_is_automatic": False},
        persist=False,
    )

    def fake_wait():
        bridge.set_plan_confirmation("confirm")

    monkeypatch.setattr(bridge._plan_confirm_event, "wait", fake_wait)
    events.clear()

    assert bridge.begin_plan_confirmation_wait() == {"action": "confirm", "feedback": ""}
    assert events == [("plan_awaiting_confirm", {})]


def test_begin_plan_confirmation_wait_returns_revision_feedback(monkeypatch):
    _configure_bridge(monkeypatch)
    events = _capture_send_json(monkeypatch)

    bridge._set_auto_improve_state(
        {"remaining_cycles": 0, "current_run_is_automatic": False},
        persist=False,
    )

    def fake_wait():
        bridge.set_plan_confirmation({"action": "revise", "feedback": "Split the validation into a separate task."})

    monkeypatch.setattr(bridge._plan_confirm_event, "wait", fake_wait)

    assert bridge.begin_plan_confirmation_wait() == {
        "action": "revise",
        "feedback": "Split the validation into a separate task.",
    }
    assert events == [("plan_awaiting_confirm", {})]


def test_fail_stops_auto_improve_chain_and_clears_runtime_state(mock_workspace, monkeypatch):
    monkeypatch.setenv("AUTO_IMPROVE_CYCLES", "2")
    _configure_bridge(monkeypatch)
    events = _capture_send_json(monkeypatch)
    calls = _install_process_prompt(
        monkeypatch,
        [
            PromptRunResult(status="success", auto_improve_eligible=True),
            PromptRunResult(status="fail", auto_improve_eligible=False),
        ],
    )

    bridge._execute_prompt_sequence("Initial request", restart=False)

    assert [call["prompt"] for call in calls] == [
        "Initial request",
        bridge.runner.AUTO_IMPROVE_MESSAGE,
    ]
    assert [payload for type_, payload in events if type_ == "done"] == [{"status": "gave_up"}]
    settings = _read_checkpoint_settings(mock_workspace)
    assert settings["AUTO_IMPROVE_CYCLES"] == "2"
    assert bridge.AUTO_IMPROVE_STATE_KEY not in settings


def test_interrupted_automatic_cycle_preserves_remaining_budget_across_resume(mock_workspace, monkeypatch):
    monkeypatch.setenv("AUTO_IMPROVE_CYCLES", "2")
    _configure_bridge(monkeypatch)
    events = _capture_send_json(monkeypatch)
    initial_calls = _install_process_prompt(
        monkeypatch,
        [
            PromptRunResult(status="success", auto_improve_eligible=True),
            KeyboardInterrupt(),
        ],
    )

    bridge._execute_prompt_sequence("Initial request", restart=False)

    assert [call["prompt"] for call in initial_calls] == [
        "Initial request",
        bridge.runner.AUTO_IMPROVE_MESSAGE,
    ]
    settings = _read_checkpoint_settings(mock_workspace)
    assert settings[bridge.AUTO_IMPROVE_STATE_KEY] == {
        "remaining_cycles": 1,
        "current_run_is_automatic": True,
    }
    assert [payload for type_, payload in events if type_ == "done"][-1] == {"status": "interrupted"}

    checkpoint_path = mock_workspace / "quasar_logs" / "checkpoints.sqlite"
    checkpoint_path.parent.mkdir(exist_ok=True)
    checkpoint_path.touch()
    original_prepare = bridge._prepare_auto_improve_state_for_prompt

    def prepare_and_drop_checkpoint(*, restart):
        state = original_prepare(restart=restart)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        return state

    monkeypatch.setattr(bridge, "_prepare_auto_improve_state_for_prompt", prepare_and_drop_checkpoint)

    resume_calls = _install_process_prompt(
        monkeypatch,
        [
            PromptRunResult(status="success", auto_improve_eligible=True),
            PromptRunResult(status="success", auto_improve_eligible=True),
        ],
    )

    bridge._execute_prompt_sequence("", restart=False)

    assert [call["prompt"] for call in resume_calls] == [
        "",
        bridge.runner.AUTO_IMPROVE_MESSAGE,
    ]
    settings = _read_checkpoint_settings(mock_workspace)
    assert bridge.AUTO_IMPROVE_STATE_KEY not in settings


def test_auto_improve_state_persists_to_checkpoint_settings(mock_workspace, monkeypatch):
    monkeypatch.setenv("AUTO_IMPROVE_CYCLES", "3")
    _configure_bridge(monkeypatch)

    seeded = bridge._prepare_auto_improve_state_for_prompt(restart=False)
    assert seeded == {
        "remaining_cycles": 3,
        "current_run_is_automatic": False,
    }

    settings = _read_checkpoint_settings(mock_workspace)
    assert settings["AUTO_IMPROVE_CYCLES"] == "3"
    assert settings[bridge.AUTO_IMPROVE_STATE_KEY] == seeded

    bridge._clear_auto_improve_state(persist=False)
    restored = bridge._load_auto_improve_state_from_checkpoint()
    assert restored == seeded
