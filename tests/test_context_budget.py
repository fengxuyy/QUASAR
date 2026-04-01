"""Tests for shared context-budget configuration and snapshot helpers."""

import os
from unittest.mock import patch

import pytest

from src.context_budget import (
    CONTEXT_THRESHOLD_RATIOS,
    DEFAULT_CONTEXT_THRESHOLD_LEVEL,
    build_context_usage_snapshot,
    get_context_threshold_level,
    get_context_threshold_ratio,
    get_model_max_context,
    get_restricted_context_limit,
)
from src.context_summarizer import should_summarize_context


class TestContextThresholdParsing:
    def test_defaults_to_medium(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTEXT_THRESHOLD", None)
            assert get_context_threshold_level() == DEFAULT_CONTEXT_THRESHOLD_LEVEL
            assert get_context_threshold_ratio() == CONTEXT_THRESHOLD_RATIOS["medium"]

    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            ("low", "low"),
            ("LOW", "low"),
            (" medium ", "medium"),
            ("high", "high"),
            ("invalid", "medium"),
            ("", "medium"),
            (None, "medium"),
        ],
    )
    def test_normalizes_threshold_levels(self, raw_value, expected):
        if raw_value is None:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("CONTEXT_THRESHOLD", None)
                assert get_context_threshold_level() == expected
        else:
            with patch.dict(os.environ, {"CONTEXT_THRESHOLD": raw_value}, clear=False):
                assert get_context_threshold_level() == expected


class TestRestrictedContextLimit:
    @pytest.mark.parametrize(
        ("level", "expected_ratio"),
        [("low", 0.40), ("medium", 0.60), ("high", 0.80)],
    )
    def test_uses_expected_ratio_for_registered_model(self, level, expected_ratio):
        max_context = get_model_max_context("gemini-2.5-pro")
        assert max_context == 1_048_576
        assert get_restricted_context_limit("gemini-2.5-pro", level) == int(max_context * expected_ratio)

    def test_unknown_models_have_no_limit(self):
        assert get_model_max_context("gpt-4o") is None
        assert get_restricted_context_limit("gpt-4o", "medium") is None

    @pytest.mark.parametrize(
        ("level", "ratio"),
        [("low", 0.40), ("medium", 0.60), ("high", 0.80)],
    )
    def test_should_summarize_context_respects_context_threshold_env(self, level, ratio):
        threshold = int(1_048_576 * ratio)
        with patch.dict(os.environ, {"CONTEXT_THRESHOLD": level}, clear=False):
            assert should_summarize_context(threshold - 1, "gemini-2.5-pro") is False
            assert should_summarize_context(threshold, "gemini-2.5-pro") is True


class TestContextUsageSnapshot:
    def test_builds_supported_model_snapshot(self):
        snapshot = build_context_usage_snapshot(
            input_tokens=300_000,
            model_name="gemini-2.5-pro",
            agent_name="operator",
            threshold_level="medium",
        )

        assert snapshot == {
            "agent": "operator",
            "model": "gemini-2.5-pro",
            "threshold_level": "medium",
            "threshold_ratio": 0.60,
            "threshold_percent": 60,
            "max_context_tokens": 1_048_576,
            "threshold_tokens": 629_145,
            "input_tokens": 300_000,
            "usage_percent": 47.7,
            "max_context_percent": 28.6,
            "remaining_tokens": 329_145,
            "is_supported_model": True,
            "is_over_limit": False,
        }

    def test_snapshot_can_exceed_hundred_percent(self):
        snapshot = build_context_usage_snapshot(
            input_tokens=700_000,
            model_name="gemini-2.5-pro",
            threshold_level="medium",
        )

        assert snapshot["usage_percent"] == 111.3
        assert snapshot["remaining_tokens"] == 0
        assert snapshot["is_over_limit"] is True

    def test_snapshot_for_unknown_model_marks_usage_unavailable(self):
        snapshot = build_context_usage_snapshot(
            input_tokens=123_456,
            model_name="gpt-4o",
            agent_name="operator",
            threshold_level="high",
        )

        assert snapshot["is_supported_model"] is False
        assert snapshot["threshold_tokens"] is None
        assert snapshot["usage_percent"] is None
        assert snapshot["remaining_tokens"] is None
        assert snapshot["max_context_percent"] is None
        assert snapshot["threshold_percent"] == 80

    def test_snapshot_reads_level_from_environment(self):
        with patch.dict(os.environ, {"CONTEXT_THRESHOLD": "low"}, clear=False):
            snapshot = build_context_usage_snapshot(
                input_tokens=100_000,
                model_name="gemini-2.5-pro",
            )

        assert snapshot["threshold_level"] == "low"
        assert snapshot["threshold_tokens"] == int(1_048_576 * 0.40)
