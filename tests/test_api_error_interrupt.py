import pytest
from unittest.mock import MagicMock, patch

from src.agents.utils import FatalAPIError
from src.agents.utils import errors as errors_utils
from src.agents.utils import logging as logging_utils
from src.checkpoint import checkpoint_has_progress


@pytest.mark.parametrize(
    "error_message",
    [
        "Error code: 401 - {'error': {'message': 'Incorrect API key provided', 'code': 401}}",
        "Error code: 403 - PERMISSION_DENIED",
        "Error code: 404 - {'error': {'message': 'Model not found', 'code': 404}}",
        "400 INVALID_ARGUMENT: API key not valid. Please pass a valid API key.",
    ],
)
def test_non_retriable_auth_and_model_errors_fail_immediately(monkeypatch, error_message):
    saved = []
    status_events = []

    monkeypatch.setattr(logging_utils, "_write_to_log", lambda message: None)
    monkeypatch.setattr(errors_utils, "_save_stats_on_system_interrupt", lambda: saved.append(True))
    monkeypatch.setattr(
        errors_utils,
        "send_agent_event",
        lambda *args, **kwargs: status_events.append((args, kwargs)),
    )

    with pytest.raises(FatalAPIError) as exc_info:
        errors_utils.handle_api_retry(
            "strategist",
            Exception(error_message),
            current_count=1,
            max_retries=3,
            wait_seconds=120,
        )

    assert exc_info.value.agent == "strategist"
    assert saved == [True]
    assert status_events == []


def test_transient_api_error_retries_while_budget_remains(monkeypatch):
    error_message = "Error code: 503 - Service Unavailable"
    saved = []
    status_events = []

    monkeypatch.setattr(logging_utils, "_write_to_log", lambda message: None)
    monkeypatch.setattr(errors_utils, "_save_stats_on_system_interrupt", lambda: saved.append(True))
    monkeypatch.setattr(
        errors_utils,
        "send_agent_event",
        lambda *args, **kwargs: status_events.append((args, kwargs)),
    )

    should_retry = errors_utils.handle_api_retry(
        "strategist",
        Exception(error_message),
        current_count=1,
        max_retries=3,
        wait_seconds=0,
    )

    assert should_retry is True
    assert saved == []
    assert status_events[0][0] == (
        "strategist",
        "update",
        "API Error - Retrying (1/3)...",
    )
    assert status_events[0][1]["is_error"] is True
    assert status_events[0][1]["output"] == error_message


def test_exhausted_retriable_api_error_raises_fatal_with_last_error(monkeypatch):
    monkeypatch.setattr(logging_utils, "_write_to_log", lambda message: None)
    monkeypatch.setattr(errors_utils, "_save_stats_on_system_interrupt", lambda: None)
    monkeypatch.setattr(errors_utils, "send_agent_event", lambda *args, **kwargs: None)

    with pytest.raises(FatalAPIError) as exc_info:
        errors_utils.handle_api_retry(
            "operator",
            Exception("503 Service Unavailable"),
            current_count=3,
            max_retries=3,
            wait_seconds=0,
        )

    assert "persistent API connection errors" in str(exc_info.value)
    assert "503 Service Unavailable" in str(exc_info.value)
    assert exc_info.value.agent == "operator"


def test_strategist_propagates_terminal_api_error_instead_of_returning_empty_plan(
    monkeypatch,
    mock_workspace,
):
    from src.agents.strategist import strategist_initial_node

    error_message = "Error code: 404 - {'error': {'message': 'Not Found', 'code': 404}}"
    fatal_error = FatalAPIError(error_message, agent="strategist")
    retry_handler = MagicMock(side_effect=fatal_error)

    monkeypatch.setenv("ACCURACY", "standard")
    monkeypatch.setenv("GRANULARITY", "medium")

    with patch("src.agents.strategist.WORKSPACE_DIR", mock_workspace), \
         patch("src.agents.strategist.get_all_files", return_value=set()), \
         patch("src.agents.strategist.has_archive_runs", return_value=False), \
         patch("src.agents.strategist.stream_with_token_tracking", side_effect=Exception(error_message)), \
         patch("src.agents.strategist.handle_api_retry", retry_handler), \
         patch("src.agents.strategist.send_agent_event"), \
         patch("src.agents.strategist._write_input_messages"), \
         patch("src.agents.strategist.log_strategist_start"), \
         patch("src.agents.strategist.log_exception"), \
         patch("src.agents.strategist.log_custom"):
        with pytest.raises(FatalAPIError) as exc_info:
            strategist_initial_node(
                {"user_input": "calculate the band gap of silicon"},
                MagicMock(),
            )

    assert exc_info.value is fatal_error
    assert retry_handler.call_count == 1


def test_transient_api_operation_succeeds_on_third_attempt(monkeypatch):
    attempts = []

    monkeypatch.setattr(logging_utils, "_write_to_log", lambda message: None)
    monkeypatch.setattr(errors_utils, "_save_stats_on_system_interrupt", lambda: None)
    monkeypatch.setattr(errors_utils, "send_agent_event", lambda *args, **kwargs: None)

    def operation():
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise Exception("Error code: 503 - Service Unavailable")
        return "recovered"

    result = errors_utils.run_with_api_retries(
        "evaluator",
        operation,
        max_retries=3,
        wait_seconds=0,
    )

    assert result == "recovered"
    assert attempts == [1, 2, 3]


def test_checkpoint_has_progress():
    assert checkpoint_has_progress(None) is False
    assert checkpoint_has_progress({}) is False
    assert checkpoint_has_progress({"user_input": "hi", "plan": [], "completed_steps": []}) is False
    assert checkpoint_has_progress({"plan": ["Step 1"]}) is True
    assert checkpoint_has_progress({"completed_steps": ["Step 1"]}) is True
    assert checkpoint_has_progress({"current_task_messages": ["msg"]}) is True
