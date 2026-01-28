"""
Agent nodes for strategist-operator architecture.

This module re-exports agent nodes from the agents package for backward compatibility.
New code should import directly from src.agents.
"""

# Re-export all agent nodes from the new modular structure
from .agents import (
    strategist_node,
    operator_node,
    evaluator_node
)

__all__ = ['strategist_node', 'operator_node', 'evaluator_node']
