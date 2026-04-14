from src.agents.utils import tool_helpers


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
