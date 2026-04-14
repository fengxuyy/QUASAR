from langchain_core.messages import AIMessageChunk

from src.openai_compat import QuasarChatOpenAI


def test_convert_chunk_to_generation_chunk_preserves_reasoning_delta():
    llm = object.__new__(QuasarChatOpenAI)
    llm.output_version = None

    generation_chunk = llm._convert_chunk_to_generation_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": "",
                        "reasoning": "Thinking step",
                    }
                }
            ]
        },
        AIMessageChunk,
        None,
    )

    assert generation_chunk is not None
    assert generation_chunk.message.content == ""
    assert generation_chunk.message.additional_kwargs["reasoning"] == "Thinking step"


def test_convert_chunk_to_generation_chunk_preserves_reasoning_content_delta():
    llm = object.__new__(QuasarChatOpenAI)
    llm.output_version = None

    generation_chunk = llm._convert_chunk_to_generation_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "Reasoning payload",
                    }
                }
            ]
        },
        AIMessageChunk,
        None,
    )

    assert generation_chunk is not None
    assert generation_chunk.message.additional_kwargs["reasoning"] == "Reasoning payload"
