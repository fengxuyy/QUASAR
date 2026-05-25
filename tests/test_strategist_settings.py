"""Tests for strategist environment setting defaults."""

from src.agents.strategist import _get_granularity_level


def test_granularity_defaults_to_adaptive(monkeypatch):
    monkeypatch.delenv("GRANULARITY", raising=False)

    assert _get_granularity_level() == "adaptive"


def test_invalid_granularity_falls_back_to_adaptive(monkeypatch):
    monkeypatch.setenv("GRANULARITY", "invalid")

    assert _get_granularity_level() == "adaptive"
