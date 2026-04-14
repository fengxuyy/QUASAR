from langchain_core.messages import AIMessageChunk

from src.agents.utils.streaming import stream_with_token_tracking


class FakeChunk:
    def __init__(self, content: str):
        self.content = content
        self.tool_call_chunks = []
        self.usage_metadata = None

    def __add__(self, other):
        return FakeChunk(f"{self.content}{other.content}")


class FakeLLM:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, _messages):
        yield from self._chunks


def test_stream_with_token_tracking_appends_delta_chunks():
    llm = FakeLLM([FakeChunk("Hello"), FakeChunk(" world")])

    full_content, tool_calls, response, was_stopped_early = stream_with_token_tracking(
        llm,
        messages=[],
        agent_name="operator",
    )

    assert full_content == "Hello world"
    assert tool_calls == []
    assert response is not None
    assert was_stopped_early is False


def test_stream_with_token_tracking_replaces_nearly_cumulative_snapshots():
    initial = (
        "Now let me create the Quantum ESPRESSO inputs for the convergence tests. "
        "I'll create a Python script to generate the convergence test inputs:"
    )
    revised = (
        "Now let me create the Quantum ESPRESSO input inputs for the convergence tests. "
        "I'll create a Python script to generate the convergence test inputs:"
    )
    llm = FakeLLM([FakeChunk(initial), FakeChunk(revised)])

    full_content, tool_calls, response, was_stopped_early = stream_with_token_tracking(
        llm,
        messages=[],
        agent_name="operator",
    )

    assert full_content == revised
    assert tool_calls == []
    assert response is not None
    assert was_stopped_early is False


def test_stream_with_token_tracking_emits_openai_reasoning_from_additional_kwargs():
    llm = FakeLLM([
        AIMessageChunk(content="", additional_kwargs={"reasoning": "Thinking "}),
        AIMessageChunk(content="", additional_kwargs={"reasoning": "through it"}),
        AIMessageChunk(content="hello"),
    ])

    thought_chunks = []
    full_content, tool_calls, response, was_stopped_early = stream_with_token_tracking(
        llm,
        messages=[],
        on_thought=thought_chunks.append,
        agent_name="operator",
    )

    assert thought_chunks == ["Thinking ", "through it"]
    assert full_content == "hello"
    assert tool_calls == []
    assert response is not None
    assert response.additional_kwargs["reasoning"] == "Thinking through it"
    assert was_stopped_early is False


def test_stream_with_token_tracking_emits_reasoning_summary_blocks():
    llm = FakeLLM([
        AIMessageChunk(
            content=[
                {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "Plan "},
                        {"type": "summary_text", "text": "ready"},
                    ],
                }
            ]
        ),
        AIMessageChunk(content="Done"),
    ])

    thought_chunks = []
    full_content, tool_calls, response, was_stopped_early = stream_with_token_tracking(
        llm,
        messages=[],
        on_thought=thought_chunks.append,
        agent_name="operator",
    )

    assert thought_chunks == ["Plan ready"]
    assert full_content == "Done"
    assert tool_calls == []
    assert response is not None
    assert was_stopped_early is False
