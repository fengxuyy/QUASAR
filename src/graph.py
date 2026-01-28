"""Workflow graph definition and routing."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from .state import State
from .agents import strategist_initial_node, strategist_review_node, operator_node, evaluator_setup_node, evaluator_loop_node
from .tools import (
    get_all_tools,
    read_file,
    list_directory,
    analyze_image,
    search_web,
    fetch_web_page,
    submit_evaluation,
    complete_task,
    grep_search,
)
from .debug_logger import log_route_after_planning, log_custom


def build_graph(llm):
    """Build and configure the state graph.
    
    Args:
        llm: The initialized LLM object to use for agents.
    """
    log_custom("GRAPH", "Building graph")
    
    all_tools = get_all_tools()
    # Normal mode strategist tools (no web search)
    strategist_tools_normal = [read_file, list_directory, analyze_image, grep_search]
    # Replanning mode strategist tools (includes web search)
    strategist_tools_replanning = [read_file, list_directory, analyze_image, grep_search, search_web, fetch_web_page]
    evaluator_tools = [read_file, list_directory, analyze_image, search_web, fetch_web_page, submit_evaluation, grep_search]
    operator_tools = all_tools + [complete_task]
    
    # Bind tools once for each agent to ensure proper tool binding
    # Strategist uses replanning tools (superset) - filtering happens inside the node
    strategist_llm_normal = llm.bind_tools(strategist_tools_normal)
    strategist_llm_replanning = llm.bind_tools(strategist_tools_replanning)
    operator_llm = llm.bind_tools(operator_tools)
    evaluator_llm = llm.bind_tools(evaluator_tools)
    
    graph_builder = StateGraph(State)
    
    # Two strategist nodes for checkpointing between initial plan and review
    # Pass both tool sets - node will choose based on is_replanning
    graph_builder.add_node("strategist_initial", lambda s: strategist_initial_node(
        s, llm, 
        strategist_llm_normal, strategist_tools_normal,
        strategist_llm_replanning, strategist_tools_replanning
    ))
    graph_builder.add_node("strategist_review", lambda s: strategist_review_node(s, llm))
    graph_builder.add_node("operator", lambda s: operator_node(s, operator_llm, operator_tools))
    
    # Two evaluator nodes for checkpointing between setup and each iteration
    graph_builder.add_node("evaluator_setup", lambda s: evaluator_setup_node(s, evaluator_llm))
    graph_builder.add_node("evaluator_loop", lambda s: evaluator_loop_node(s, evaluator_llm))
    
    # Start with initial strategist
    graph_builder.add_edge(START, "strategist_initial")

    def route_after_initial(state: State) -> str:
        """Route after initial strategist: to review (standard) or operator (replanning)."""
        is_replanning = state.get("is_replanning", False)
        plan = state.get("plan", [])
        initial_plan_content = state.get("initial_plan_content", "")
        
        log_custom("GRAPH", "route_after_initial", {
            "is_replanning": is_replanning,
            "has_plan": bool(plan),
            "has_initial_content": bool(initial_plan_content),
        })
        
        # In replanning mode, initial node already extracted plan, go to operator
        if is_replanning:
            return "operator" if plan else "end"
        
        # In standard mode, go to review phase if we have initial content
        if initial_plan_content:
            return "review"
        
        # No content, end
        return "end"

    def route_after_review(state: State) -> str:
        """Route after review: to operator if plan exists, else end."""
        plan = state.get("plan")
        result = "operator" if plan else "end"
        log_route_after_planning(state, result)
        return result

    def route_after_execution(state: State) -> str:
        messages = state.get('messages', [])
        current_task_messages = state.get('current_task_messages', [])
        
        if not messages:
            return "continue"
        
        # Check if we just came from evaluator (last message is HumanMessage from evaluator)
        # If so, don't route back to evaluator immediately - let operator work first
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, HumanMessage):
                # Check if this is a message from evaluator (indicating task completion or feedback)
                raw_content = getattr(last_msg, 'content', '')
                content = raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()
                if ("completed successfully" in content.lower() or 
                    "please start working on" in content.lower() or
                    "EVALUATION_FEEDBACK" in content):
                    # Just came from evaluator - continue with operator, don't route to evaluator
                    return "continue"
        
        # Log routing decision
        log_custom("ROUTING", "route_after_execution called", {
            "messages_count": len(messages),
            "current_task_messages_count": len(current_task_messages),
            "last_msg_type": type(messages[-1]).__name__ if messages else "None",
            "last_msg_content": str(messages[-1].content)[:100] if messages and hasattr(messages[-1], 'content') else "None",
        })
        
        # Find the index of the most recent EVALUATION_FEEDBACK in current_task_messages
        # Only consider DONE/GIVE_UP messages that come AFTER this index
        last_feedback_index = -1
        for i, msg in enumerate(current_task_messages):
            if isinstance(msg, HumanMessage):
                content = getattr(msg, 'content', '')
                if 'EVALUATION_FEEDBACK' in content:
                    last_feedback_index = i
        
        # ONLY check current task messages for DONE or GIVE_UP
        # Start from the end, but only consider messages AFTER last_feedback_index
        messages_to_check = current_task_messages[last_feedback_index + 1:] if last_feedback_index >= 0 else current_task_messages
        
        for msg in reversed(messages_to_check):
            if isinstance(msg, AIMessage):
                raw_content = getattr(msg, 'content', '')
                content = raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()
                if content == "GIVE_UP":
                    return "evaluator_setup"  # Route to evaluator setup to record failure
                if content == "DONE":
                    # Only route to evaluator if operator has actually worked on the current task
                    # Check if current_task_messages has operator work (after last feedback if any)
                    completed_steps = state.get('completed_steps', [])
                    current_task_index = len(completed_steps)
                    
                    # If operator has worked (has meaningful AIMessage or ToolMessage in current_task_messages), route to evaluator
                    # Exclude DONE/GIVE_UP messages as they don't count as actual work
                    def is_meaningful_work(msg):
                        if isinstance(msg, SystemMessage):
                            return False
                        if isinstance(msg, ToolMessage):
                            return True  # Tool usage indicates actual work
                        if isinstance(msg, AIMessage):
                            raw_content = getattr(msg, 'content', '')
                            msg_content = raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()
                            # Exclude DONE/GIVE_UP as they're just signals, not work
                            if msg_content in ('DONE', 'GIVE_UP'):
                                return False
                            # Any other AIMessage with content or tool_calls indicates work
                            return bool(msg_content) or bool(getattr(msg, 'tool_calls', None))
                        return False
                    
                    # Check for work after the last feedback
                    has_operator_work = any(is_meaningful_work(m) for m in messages_to_check)
                    
                    if has_operator_work or current_task_index == 0:
                        log_custom("ROUTING", "Routing to evaluator_setup (DONE message found after feedback)")
                        return "evaluator_setup"
                    else:
                        log_custom("ROUTING", "DONE found but operator hasn't worked, continuing")
                        return "continue"
        
        return "continue"
    
    def route_after_evaluator_setup(state: State) -> str:
        """Route after evaluator setup: to loop if evaluation_messages exist, else based on completion."""
        evaluation_messages = state.get('evaluation_messages', [])
        
        log_custom("GRAPH", "route_after_evaluator_setup", {
            "has_evaluation_messages": bool(evaluation_messages),
            "messages_count": len(evaluation_messages),
        })
        
        # If we have evaluation messages, go to loop
        if evaluation_messages:
            return "loop"
        
        # No evaluation messages means setup handled the case (operator hasn't worked, gave up, etc.)
        # Check if we should continue to operator or end
        plan = state.get('plan', [])
        completed = state.get('completed_steps', [])
        step_results = state.get('step_results', {})
        
        # Check if operator gave up
        if completed:
            current_task_index = len(completed) - 1
            recent_summary = step_results.get(current_task_index, "")
            if "Operator failed to execute this step" in recent_summary:
                return "end"
        
        messages = state.get('messages', [])
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage):
                raw_content = getattr(last_msg, 'content', '')
                content = raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()
                if content == "GIVE_UP" or "Operator failed to execute this step" in content:
                    return "end"
        
        return "operator" if len(completed) < len(plan) else "end"
    
    def route_after_evaluator_loop(state: State) -> str:
        """Route after evaluator loop: continue looping if evaluation_messages exist, else operator/end."""
        evaluation_messages = state.get('evaluation_messages', [])
        
        log_custom("GRAPH", "route_after_evaluator_loop", {
            "has_evaluation_messages": bool(evaluation_messages),
        })
        
        # If we still have evaluation messages, continue looping
        if evaluation_messages:
            return "continue"
        
        # No more evaluation messages - evaluation complete
        # Route based on completion status
        plan = state.get('plan', [])
        completed = state.get('completed_steps', [])
        step_results = state.get('step_results', {})
        
        # Check if operator gave up
        if completed:
            current_task_index = len(completed) - 1
            recent_summary = step_results.get(current_task_index, "")
            if "Operator failed to execute this step" in recent_summary:
                return "end"
        
        messages = state.get('messages', [])
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage):
                raw_content = getattr(last_msg, 'content', '')
                content = raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()
                if content == "GIVE_UP" or "Operator failed to execute this step" in content:
                    return "end"
        
        return "operator" if len(completed) < len(plan) else "end"
    
    # Conditional edges for strategist phases
    graph_builder.add_conditional_edges("strategist_initial", route_after_initial, {
        "review": "strategist_review",
        "operator": "operator",
        "end": END
    })
    graph_builder.add_conditional_edges("strategist_review", route_after_review, {"operator": "operator", "end": END})
    
    # Operator edges - now routes to evaluator_setup
    graph_builder.add_conditional_edges("operator", route_after_execution, {
        "continue": "operator", "evaluator_setup": "evaluator_setup", "end": END
    })
    
    # Evaluator edges - setup uses conditional routing, loop can self-loop or exit
    graph_builder.add_conditional_edges("evaluator_setup", route_after_evaluator_setup, {
        "loop": "evaluator_loop",
        "operator": "operator",
        "end": END
    })
    graph_builder.add_conditional_edges("evaluator_loop", route_after_evaluator_loop, {
        "continue": "evaluator_loop",  # Self-loop for more iterations
        "operator": "operator",
        "end": END
    })
    
    log_custom("GRAPH", "Graph built successfully", {
        "nodes": ["strategist_initial", "strategist_review", "operator", "evaluator_setup", "evaluator_loop"],
        "edges": ["START->strategist_initial", "strategist_initial->review/operator/end", "strategist_review->operator/end", 
                  "operator->continue/evaluator_setup/end", "evaluator_setup->loop/operator/end", "evaluator_loop->continue/operator/end"]
    })
    
    return graph_builder
