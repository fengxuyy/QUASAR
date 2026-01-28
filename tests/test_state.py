"""Tests for state definition and creation."""
import pytest

from src.state import State, create_initial_state


def test_create_initial_state():
    """Test creating initial state with user input."""
    user_input = "Analyze the crystal structure of NaCl"
    
    state = create_initial_state(user_input)
    
    # Verify all fields
    assert state["messages"] == []
    assert state["user_input"] == user_input
    assert state["current_task_messages"] == []
    assert state["plan"] == []
    assert state["completed_steps"] == []
    assert state["step_results"] == {}
    assert state["files_at_task_start"] == []
    assert state["evaluation_attempts"] == 0
    assert state["initial_plan_content"] == ""
    assert state["is_replanning"] is False
    assert state["evaluation_messages"] == []


def test_create_initial_state_empty_input():
    """Test creating initial state with empty user input."""
    state = create_initial_state("")
    
    assert state["user_input"] == ""
    assert state["messages"] == []


def test_state_has_correct_keys():
    """Test that State TypedDict has all expected keys."""
    expected_keys = {
        "messages",
        "user_input", 
        "current_task_messages",
        "plan",
        "completed_steps",
        "step_results",
        "files_at_task_start",
        "evaluation_attempts",
        "initial_plan_content",
        "is_replanning",
        "evaluation_messages",
    }
    
    # Get keys from annotations
    state_keys = set(State.__annotations__.keys())
    
    assert state_keys == expected_keys


def test_state_is_mutable():
    """Test that state fields are mutable as expected."""
    state = create_initial_state("test")
    
    # Add to plan
    state["plan"].append("Task 1: Do something")
    assert len(state["plan"]) == 1
    
    # Add completed step
    state["completed_steps"].append("Task 1 done")
    assert len(state["completed_steps"]) == 1
    
    # Add step result
    state["step_results"][1] = "Success"
    assert state["step_results"][1] == "Success"
    
    # Toggle replanning
    state["is_replanning"] = True
    assert state["is_replanning"] is True
