"""Tests for replaying cached context-usage snapshots across bridge updates."""

import os
from unittest.mock import patch

import pytest

from src.agents.utils.bridge import (
    build_replayed_context_usage_payload,
    get_last_context_usage_seed,
    reset_context_usage_seed,
    send_context_usage,
)


@pytest.fixture(autouse=True)
def clear_context_usage_seed():
    reset_context_usage_seed()
    yield
    reset_context_usage_seed()


class TestBridgeContextUsageReplay:
    def test_send_context_usage_records_latest_seed(self):
        send_context_usage(
            {
                "input_tokens": 321_000,
                "agent": "operator",
                "model": "gemini-2.5-pro",
            }
        )

        assert get_last_context_usage_seed() == {
            "input_tokens": 321_000,
            "agent_name": "operator",
        }

    def test_replayed_payload_preserves_tokens_after_threshold_change(self):
        send_context_usage(
            {
                "input_tokens": 300_000,
                "agent": "operator",
                "model": "gemini-2.5-pro",
            }
        )

        with patch.dict(
            os.environ,
            {
                "MODEL": "gemini-2.5-pro",
                "OPERATOR_MODEL": "gemini-2.5-pro",
                "CONTEXT_THRESHOLD": "high",
            },
            clear=False,
        ):
            payload = build_replayed_context_usage_payload()

        assert payload["input_tokens"] == 300_000
        assert payload["agent"] == "operator"
        assert payload["model"] == "gemini-2.5-pro"
        assert payload["threshold_percent"] == 80
        assert payload["threshold_tokens"] == int(1_048_576 * 0.80)

    def test_replayed_payload_uses_current_env_model(self):
        send_context_usage(
            {
                "input_tokens": 200_000,
                "agent": "",
                "model": "gemini-2.5-pro",
            }
        )

        with patch.dict(
            os.environ,
            {
                "MODEL": "gemini-2.5-flash",
                "CONTEXT_THRESHOLD": "medium",
            },
            clear=False,
        ):
            payload = build_replayed_context_usage_payload()

        assert payload["input_tokens"] == 200_000
        assert payload["agent"] == ""
        assert payload["model"] == "gemini-2.5-flash"
        assert payload["threshold_percent"] == 60

    def test_reset_seed_replays_zero_snapshot(self):
        send_context_usage(
            {
                "input_tokens": 150_000,
                "agent": "operator",
                "model": "gemini-2.5-pro",
            }
        )
        reset_context_usage_seed()

        with patch.dict(os.environ, {"MODEL": "gemini-2.5-pro"}, clear=False):
            payload = build_replayed_context_usage_payload()

        assert payload["input_tokens"] == 0
        assert payload["agent"] == ""
        assert payload["model"] == "gemini-2.5-pro"
