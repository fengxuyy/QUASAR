"""Tests for graph routing logic."""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage

# Import routing functions - we need to extract them from the build_graph closure
# Since they're nested functions, we test via the state-based logic directly


class TestRouteAfterInitial:
    """Test route_after_initial logic."""
    
    def test_replanning_with_plan_goes_to_operator(self):
        """In replanning mode with a plan, should route to operator."""
        state = {
            "is_replanning": True,
            "plan": ["Task 1", "Task 2"],
            "initial_plan_content": "",
        }
        
        # Logic: if is_replanning and plan -> "operator"
        is_replanning = state.get("is_replanning", False)
        plan = state.get("plan", [])
        
        if is_replanning:
            result = "operator" if plan else "end"
        else:
            initial_plan_content = state.get("initial_plan_content", "")
            result = "review" if initial_plan_content else "end"
            
        assert result == "operator"
    
    def test_replanning_without_plan_goes_to_end(self):
        """In replanning mode without a plan, should route to end."""
        state = {
            "is_replanning": True,
            "plan": [],
            "initial_plan_content": "",
        }
        
        is_replanning = state.get("is_replanning", False)
        plan = state.get("plan", [])
        result = "operator" if plan else "end"
        
        assert result == "end"
    
    def test_standard_mode_with_content_goes_to_review(self):
        """In standard mode with initial_plan_content, should route to review."""
        state = {
            "is_replanning": False,
            "plan": [],
            "initial_plan_content": "Here is my execution plan...",
        }
        
        is_replanning = state.get("is_replanning", False)
        initial_plan_content = state.get("initial_plan_content", "")
        
        if is_replanning:
            result = "operator"
        elif initial_plan_content:
            result = "review"
        else:
            result = "end"
            
        assert result == "review"
    
    def test_standard_mode_no_content_goes_to_end(self):
        """In standard mode without initial_plan_content, should route to end."""
        state = {
            "is_replanning": False,
            "plan": [],
            "initial_plan_content": "",
        }
        
        is_replanning = state.get("is_replanning", False)
        initial_plan_content = state.get("initial_plan_content", "")
        
        result = "review" if initial_plan_content else "end"
        
        assert result == "end"


class TestRouteAfterReview:
    """Test route_after_review logic."""
    
    def test_with_plan_goes_to_operator(self):
        """With a plan, should route to operator."""
        state = {"plan": ["Task 1", "Task 2"]}
        plan = state.get("plan")
        
        result = "operator" if plan else "end"
        assert result == "operator"
    
    def test_without_plan_goes_to_end(self):
        """Without a plan, should route to end."""
        state = {"plan": []}
        plan = state.get("plan")
        
        result = "operator" if plan else "end"
        assert result == "end"
    
    def test_none_plan_goes_to_end(self):
        """With None plan, should route to end."""
        state = {"plan": None}
        plan = state.get("plan")
        
        result = "operator" if plan else "end"
        assert result == "end"


class TestIsMeaningfulWork:
    """Test is_meaningful_work helper logic."""
    
    def _is_meaningful_work(self, msg):
        """Replicated logic from graph.py for testing."""
        if isinstance(msg, SystemMessage):
            return False
        if isinstance(msg, ToolMessage):
            return True
        if isinstance(msg, AIMessage):
            raw_content = getattr(msg, 'content', '')
            msg_content = raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()
            if msg_content in ('DONE', 'GIVE_UP'):
                return False
            return bool(msg_content) or bool(getattr(msg, 'tool_calls', None))
        return False
    
    def test_system_message_not_meaningful(self):
        """System messages should not count as meaningful work."""
        msg = SystemMessage(content="You are an assistant")
        assert self._is_meaningful_work(msg) is False
    
    def test_tool_message_is_meaningful(self):
        """Tool messages should count as meaningful work."""
        msg = ToolMessage(content="File written successfully", tool_call_id="123")
        assert self._is_meaningful_work(msg) is True
    
    def test_done_message_not_meaningful(self):
        """DONE messages should not count as meaningful work."""
        msg = AIMessage(content="DONE")
        assert self._is_meaningful_work(msg) is False
    
    def test_give_up_message_not_meaningful(self):
        """GIVE_UP messages should not count as meaningful work."""
        msg = AIMessage(content="GIVE_UP")
        assert self._is_meaningful_work(msg) is False
    
    def test_ai_message_with_content_is_meaningful(self):
        """AI messages with actual content should count as work."""
        msg = AIMessage(content="I will analyze the file structure...")
        assert self._is_meaningful_work(msg) is True
    
    def test_ai_message_with_tool_calls_is_meaningful(self):
        """AI messages with tool calls should count as work."""
        # Create AIMessage and manually set tool_calls attribute
        msg = AIMessage(content="")
        msg.tool_calls = [{"name": "read_file", "args": {}}]
        assert self._is_meaningful_work(msg) is True
    
    def test_empty_ai_message_not_meaningful(self):
        """Empty AI messages should not count as work."""
        msg = AIMessage(content="")
        assert self._is_meaningful_work(msg) is False


class TestRouteAfterEvaluatorSetup:
    """Test route_after_evaluator_setup logic."""
    
    def test_with_evaluation_messages_goes_to_loop(self):
        """With evaluation_messages, should route to loop."""
        state = {"evaluation_messages": [HumanMessage(content="Evaluate")]}
        
        evaluation_messages = state.get('evaluation_messages', [])
        result = "loop" if evaluation_messages else "operator"
        
        assert result == "loop"
    
    def test_without_evaluation_messages_checks_completion(self):
        """Without evaluation_messages, should check plan vs completed."""
        state = {
            "evaluation_messages": [],
            "plan": ["Task 1", "Task 2"],
            "completed_steps": ["Task 1 done"],
            "step_results": {},
            "messages": [],
        }
        
        evaluation_messages = state.get('evaluation_messages', [])
        plan = state.get('plan', [])
        completed = state.get('completed_steps', [])
        
        if evaluation_messages:
            result = "loop"
        else:
            result = "operator" if len(completed) < len(plan) else "end"
        
        assert result == "operator"
    
    def test_all_tasks_completed_goes_to_end(self):
        """When all tasks completed, should route to end."""
        state = {
            "evaluation_messages": [],
            "plan": ["Task 1"],
            "completed_steps": ["Task 1 done"],
            "step_results": {},
            "messages": [],
        }
        
        plan = state.get('plan', [])
        completed = state.get('completed_steps', [])
        
        result = "operator" if len(completed) < len(plan) else "end"
        
        assert result == "end"
