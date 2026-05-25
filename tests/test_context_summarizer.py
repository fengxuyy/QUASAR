"""Tests for context summarization module."""
import os
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, AIMessageChunk

from src.context_summarizer import (
    is_gemini_model,
    should_summarize_context,
    summarize_messages,
    maybe_summarize_messages,
    get_effective_model_name,
    _format_messages_for_summary,
    _get_model_max_context,
    MODEL_MAX_CONTEXT,
    CONTEXT_THRESHOLD_RATIO,
)
from src.context_budget import (
    DEFAULT_CONTEXT_THRESHOLD_LEVEL,
    CONTEXT_THRESHOLD_RATIOS,
    build_context_usage_snapshot,
    get_context_threshold_ratio,
)
from src.prompting import build_resume_steering_injection, upsert_prompt_runtime_event


class TestIsGeminiModel:
    """Test is_gemini_model function."""
    
    def test_gemini_pro(self):
        assert is_gemini_model("gemini-2.5-pro") is True
    
    def test_gemini_flash(self):
        assert is_gemini_model("gemini-2.5-flash") is True

    def test_gemini_35_flash(self):
        assert is_gemini_model("gemini-3.5-flash") is True
    
    def test_gemini_preview(self):
        assert is_gemini_model("gemini-3.1-pro-preview") is True
    
    def test_gemini_case_insensitive(self):
        assert is_gemini_model("Gemini-2.5-Pro") is True
    
    def test_gpt_not_gemini(self):
        assert is_gemini_model("gpt-4o") is False
    
    def test_claude_not_gemini(self):
        assert is_gemini_model("claude-sonnet-4-5-20250929") is False
    
    def test_empty_string(self):
        assert is_gemini_model("") is False
    
    def test_none(self):
        assert is_gemini_model(None) is False


class TestShouldSummarizeContext:
    """Test should_summarize_context function."""
    
    def test_constants(self):
        """Verify threshold dict and ratio are correctly set."""
        assert "gemini-2.5-pro" in MODEL_MAX_CONTEXT
        assert "gemini-3.5-flash" in MODEL_MAX_CONTEXT
        assert MODEL_MAX_CONTEXT["gemini-2.5-pro"] == 1_048_576
        assert MODEL_MAX_CONTEXT["gemini-3.5-flash"] == 1_048_576
        assert DEFAULT_CONTEXT_THRESHOLD_LEVEL == "medium"
        assert CONTEXT_THRESHOLD_RATIOS == {"low": 0.20, "medium": 0.40, "hard": 0.60}
        assert CONTEXT_THRESHOLD_RATIO == 0.40
    
    def test_get_model_max_context_gemini(self):
        """Gemini model should resolve to 1,048,576."""
        assert _get_model_max_context("gemini-3.5-flash") == 1_048_576
    
    def test_get_model_max_context_unknown(self):
        """Unknown models should return None."""
        assert _get_model_max_context("gpt-4o") is None
        assert _get_model_max_context("") is None
    
    def test_below_threshold_gemini(self):
        """Below threshold, should not summarize even for Gemini."""
        assert should_summarize_context(100_000, "gemini-2.5-pro") is False
    
    def test_at_threshold_gemini(self):
        """At exactly the threshold, should summarize."""
        threshold = int(MODEL_MAX_CONTEXT["gemini-2.5-pro"] * get_context_threshold_ratio())
        assert should_summarize_context(threshold, "gemini-2.5-pro") is True
    
    def test_above_threshold_gemini(self):
        """Above threshold, should summarize."""
        assert should_summarize_context(800_000, "gemini-2.5-pro") is True
    
    def test_above_threshold_non_gemini(self):
        """Above threshold but non-Gemini model, should not summarize."""
        assert should_summarize_context(800_000, "gpt-4o") is False
    
    def test_zero_tokens(self):
        """Zero tokens should not trigger summarization."""
        assert should_summarize_context(0, "gemini-2.5-pro") is False
    
    def test_reads_model_from_env(self):
        """When model_name is None, should read from MODEL env var."""
        with patch.dict(os.environ, {"MODEL": "gemini-2.5-flash"}):
            assert should_summarize_context(800_000) is True
        
        with patch.dict(os.environ, {"MODEL": "gpt-4o"}):
            assert should_summarize_context(800_000) is False
    
    def test_just_below_threshold(self):
        """One token below threshold should not trigger."""
        threshold = int(MODEL_MAX_CONTEXT["gemini-2.5-pro"] * get_context_threshold_ratio())
        assert should_summarize_context(threshold - 1, "gemini-2.5-pro") is False


class TestFormatMessages:
    """Test _format_messages_for_summary helper."""
    
    def test_skips_system_message(self):
        """SystemMessage should be excluded from format output."""
        messages = [
            SystemMessage(content="You are an operator"),
            HumanMessage(content="Do something"),
        ]
        result = _format_messages_for_summary(messages)
        assert "You are an operator" not in result
        assert "Do something" in result
    
    def test_includes_role_labels(self):
        """Messages should have role labels."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]
        result = _format_messages_for_summary(messages)
        assert "[Human]:" in result
        assert "[AI]:" in result
    
    def test_truncates_long_messages(self):
        """Very long messages should be truncated."""
        long_content = "x" * 20000
        messages = [HumanMessage(content=long_content)]
        result = _format_messages_for_summary(messages)
        assert "... [truncated]" in result
        # Should be approximately 10000 chars max per message
        assert len(result) < 12000
    
    def test_includes_tool_call_info(self):
        """Tool calls should be mentioned."""
        msg = AIMessage(content="I'll read the file")
        msg.tool_calls = [{"name": "read_file", "args": {"file_path": "test.py"}, "id": "1"}]
        messages = [msg]
        result = _format_messages_for_summary(messages)
        assert "read_file" in result
    
    def test_includes_tool_message_id(self):
        """ToolMessages should include tool_call_id."""
        messages = [ToolMessage(content="File read success", tool_call_id="abc123")]
        result = _format_messages_for_summary(messages)
        assert "abc123" in result


class TestSummarizeMessages:
    """Test summarize_messages function."""
    
    def test_preserves_system_message(self):
        """SystemMessage should be preserved in output."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary of conversation"
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response
        
        messages = [
            SystemMessage(content="You are an operator"),
            HumanMessage(content="Task context"),
            AIMessage(content="I'll do the task"),
        ]
        
        result = summarize_messages(messages, mock_llm, "operator")
        
        # Should have exactly 2 messages: SystemMessage + summary HumanMessage
        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are an operator"
        assert isinstance(result[1], HumanMessage)
        assert "Summary of conversation" in result[1].content
    
    def test_summary_has_context_header(self):
        """Summary message should have a context header."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is the summary"
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response
        
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        
        result = summarize_messages(messages, mock_llm, "test")
        assert "[CONTEXT SUMMARY" in result[1].content
    
    def test_returns_original_on_empty_summary(self):
        """If LLM returns empty, should return original messages."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = ""
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response
        
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        
        result = summarize_messages(messages, mock_llm, "test")
        assert result == messages  # Original messages returned
    
    def test_returns_original_on_error(self):
        """If LLM call fails, should return original messages."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API error")
        
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        
        result = summarize_messages(messages, mock_llm, "test")
        assert result == messages  # Original messages returned
    
    def test_no_non_system_messages(self):
        """If only SystemMessage exists, should return original."""
        mock_llm = MagicMock()
        messages = [SystemMessage(content="System")]
        
        result = summarize_messages(messages, mock_llm, "test")
        assert result == messages
        mock_llm.invoke.assert_not_called()
    
    def test_tracks_token_usage(self):
        """Summarization call should track its own token usage."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary"
        mock_response.usage_metadata = {"input_tokens": 5000, "output_tokens": 500}
        mock_llm.invoke.return_value = mock_response
        
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        
        with patch("src.usage_tracker.record_api_call") as mock_record:
            summarize_messages(messages, mock_llm, "operator")
            mock_record.assert_called_once_with(
                input_tokens=5000,
                output_tokens=500,
                agent_name="operator",
                cache_read_tokens=0,
            )
    
    def test_multiple_system_messages_preserved(self):
        """If multiple SystemMessages exist, all should be preserved."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary"
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response
        
        messages = [
            SystemMessage(content="System 1"),
            SystemMessage(content="System 2"),
            HumanMessage(content="Hello"),
        ]
        
        result = summarize_messages(messages, mock_llm, "test")
        assert len(result) == 3  # 2 SystemMessages + summary
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], SystemMessage)
        assert isinstance(result[2], HumanMessage)

    def test_uses_unwrapped_base_llm_when_tools_are_bound(self):
        """Summarization should invoke the base model, not the tool-bound wrapper."""
        base_llm = MagicMock()
        base_response = MagicMock()
        base_response.content = "Bound summary"
        base_response.usage_metadata = None
        base_llm.invoke.return_value = base_response

        bound_llm = MagicMock()
        bound_llm.bound = base_llm

        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]

        result = summarize_messages(messages, bound_llm, "operator")

        base_llm.invoke.assert_called_once()
        bound_llm.invoke.assert_not_called()
        assert "Bound summary" in result[1].content


class TestMaybeSummarizeMessages:
    """Tests for the threshold-aware summarization helper."""

    def test_prefers_agent_specific_model_override(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Operator summary"
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response

        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        threshold = int(MODEL_MAX_CONTEXT["gemini-2.5-pro"] * get_context_threshold_ratio())

        with patch.dict(os.environ, {"MODEL": "gpt-4o", "OPERATOR_MODEL": "gemini-2.5-pro"}, clear=False):
            result, did_summarize, effective_model, trigger_input = maybe_summarize_messages(
                messages,
                mock_llm,
                agent_name="operator",
                input_tokens=threshold,
            )

        assert did_summarize is True
        assert effective_model == "gemini-2.5-pro"
        assert trigger_input == threshold
        assert result is not messages
        assert "[CONTEXT SUMMARY" in result[1].content

    def test_returns_original_when_override_is_non_gemini(self):
        mock_llm = MagicMock()
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]

        with patch.dict(os.environ, {"MODEL": "gemini-2.5-pro", "OPERATOR_MODEL": "gpt-4o"}, clear=False):
            result, did_summarize, effective_model, trigger_input = maybe_summarize_messages(
                messages,
                mock_llm,
                agent_name="operator",
                input_tokens=900_000,
            )

        assert did_summarize is False
        assert effective_model == "gpt-4o"
        assert trigger_input == 900_000
        assert result is messages
        mock_llm.invoke.assert_not_called()

    def test_get_effective_model_name_falls_back_to_primary_model(self):
        with patch.dict(os.environ, {"MODEL": "gemini-3-flash-preview"}, clear=False):
            assert get_effective_model_name(agent_name="operator") == "gemini-3-flash-preview"

    def test_uses_tracked_input_tokens_and_resets_after_summary(self):
        from src.agents.utils.streaming import get_last_input_tokens, reset_last_input_tokens, _last_input_tokens

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Condensed context"
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response

        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        threshold = int(MODEL_MAX_CONTEXT["gemini-2.5-pro"] * get_context_threshold_ratio())

        reset_last_input_tokens("operator")
        _last_input_tokens["operator"] = threshold

        with patch.dict(os.environ, {"MODEL": "gpt-4o", "OPERATOR_MODEL": "gemini-2.5-pro"}, clear=False), \
             patch("src.agents.utils.bridge.send_context_usage") as mock_send_context_usage:
            result, did_summarize, effective_model, trigger_input = maybe_summarize_messages(
                messages,
                mock_llm,
                agent_name="operator",
            )

        assert did_summarize is True
        assert effective_model == "gemini-2.5-pro"
        assert trigger_input == threshold
        assert result is not messages
        assert get_last_input_tokens("operator") == 0
        mock_send_context_usage.assert_called_once_with(
            build_context_usage_snapshot(
                input_tokens=0,
                model_name="gemini-2.5-pro",
                agent_name="operator",
            )
        )

    def test_rehydrates_active_prompt_events_after_summary(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Condensed context"
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response

        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        threshold = int(MODEL_MAX_CONTEXT["gemini-2.5-pro"] * get_context_threshold_ratio())
        events = upsert_prompt_runtime_event(
            [],
            build_resume_steering_injection("Use smaller batches."),
            task_index=0,
        )

        with patch.dict(os.environ, {"MODEL": "gemini-2.5-pro"}, clear=False):
            result, did_summarize, _, _ = maybe_summarize_messages(
                messages,
                mock_llm,
                agent_name="operator",
                input_tokens=threshold,
                runtime_events=events,
                task_index=0,
            )

        assert did_summarize is True
        assert "[CONTEXT SUMMARY" in result[1].content
        assert "Use smaller batches" in result[-1].content
        assert result[-1].additional_kwargs["quasar_prompt_event"]["id"] == "operator.resume_steering"


class TestStreamingTokenTracking:
    """Test the last-seen input token tracking in streaming.py."""
    
    def test_get_and_reset(self):
        from src.agents.utils.streaming import (
            get_last_input_tokens,
            reset_last_input_tokens,
            _last_input_tokens,
        )
        
        # Initially should be 0
        assert get_last_input_tokens("test_agent") == 0
        
        # Set a value
        _last_input_tokens["test_agent"] = 500_000
        assert get_last_input_tokens("test_agent") == 500_000
        
        # Reset
        reset_last_input_tokens("test_agent")
        assert get_last_input_tokens("test_agent") == 0
    
    def test_reset_nonexistent_agent(self):
        from src.agents.utils.streaming import reset_last_input_tokens
        
        # Should not raise
        reset_last_input_tokens("nonexistent_agent")

    def test_gemini_stream_uses_last_usage_snapshot_instead_of_summed_chunks(self):
        from src.agents.utils.streaming import (
            stream_with_token_tracking,
            get_last_input_tokens,
            reset_last_input_tokens,
        )

        class FakeGeminiLLM:
            model = "gemini-3-flash-preview"

            def stream(self, messages):
                yield AIMessageChunk(
                    content="Hel",
                    usage_metadata={
                        "input_tokens": 17,
                        "output_tokens": 1,
                        "total_tokens": 18,
                        "input_token_details": {"cache_read": 2},
                    },
                )
                yield AIMessageChunk(
                    content="lo",
                    usage_metadata={
                        "input_tokens": 17,
                        "output_tokens": 5,
                        "total_tokens": 22,
                        "input_token_details": {"cache_read": 6},
                    },
                )

        reset_last_input_tokens("operator")
        with patch("src.usage_tracker.record_api_call") as mock_record, \
             patch("src.agents.utils.bridge.send_context_usage") as mock_send_context_usage:
            content, tool_calls, full_response, was_stopped = stream_with_token_tracking(
                FakeGeminiLLM(),
                [],
                agent_name="operator",
            )

        assert content == "Hello"
        assert tool_calls == []
        assert was_stopped is False
        assert full_response.usage_metadata["input_tokens"] == 17
        assert full_response.usage_metadata["output_tokens"] == 5
        assert full_response.usage_metadata["input_token_details"]["cache_read"] == 6
        mock_record.assert_called_once_with(
            input_tokens=17,
            output_tokens=5,
            agent_name="operator",
            cache_read_tokens=6,
        )
        assert get_last_input_tokens("operator") == 17
        mock_send_context_usage.assert_called_once_with(
            build_context_usage_snapshot(
                input_tokens=17,
                model_name="gemini-3-flash-preview",
                agent_name="operator",
            )
        )

    def test_non_gemini_stream_keeps_aggregated_usage_metadata(self):
        from src.agents.utils.streaming import stream_with_token_tracking

        class FakeOtherLLM:
            model = "gpt-4o"

            def stream(self, messages):
                yield AIMessageChunk(
                    content="Hel",
                    usage_metadata={"input_tokens": 10, "output_tokens": 1, "total_tokens": 11},
                )
                yield AIMessageChunk(
                    content="lo",
                    usage_metadata={"input_tokens": 0, "output_tokens": 2, "total_tokens": 2},
                )

        with patch("src.usage_tracker.record_api_call") as mock_record:
            content, tool_calls, full_response, was_stopped = stream_with_token_tracking(
                FakeOtherLLM(),
                [],
                agent_name="operator",
            )

        assert content == "Hello"
        assert tool_calls == []
        assert was_stopped is False
        assert full_response.usage_metadata["input_tokens"] == 10
        assert full_response.usage_metadata["output_tokens"] == 3
        mock_record.assert_called_once_with(
            input_tokens=10,
            output_tokens=3,
            agent_name="operator",
            cache_read_tokens=0,
        )
