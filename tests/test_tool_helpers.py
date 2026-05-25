from src.agents.utils import tool_helpers
from src.agents.utils.tool_helpers import _get_execute_python_status_pair, get_execute_python_status


def test_update_agent_status_includes_query_rag_output_on_success(monkeypatch):
    calls = []

    def fake_send_agent_event(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(tool_helpers, "send_agent_event", fake_send_agent_event)

    rag_output = "## Match 1\n\nUse the embedding dimension from the model metadata."
    tool_helpers.update_agent_status(
        "operator",
        "query_rag",
        {"query": "embedding dimension", "library": "docs"},
        is_complete=True,
        tool_result=rag_output,
    )

    assert calls == [
        (
            ("operator", "step_complete", "Queried RAG embedding dimension in docs"),
            {"is_error": False, "output": rag_output},
        ),
        (("operator", "update", "Analysing Task"), {}),
    ]


def test_execute_python_status_includes_check_in_after():
    status, complete = _get_execute_python_status_pair({
        "file_path": "task_1/test.py",
        "check_in_after": 5,
    })

    assert status == "Executing test.py (5 min check-in)"
    assert complete == "Executed test.py"


def test_execute_python_status_formats_fractional_check_in_after():
    status = get_execute_python_status({
        "code": "print('hello')",
        "check_in_after": "2.5",
    })

    assert status == "Executing print('hello') (2.5 min check-in)"
