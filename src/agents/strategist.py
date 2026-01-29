"""
Strategist agent node implementation.
"""

import os
import re
import time
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage

from langchain_openai import ChatOpenAI

from ..state import State, create_initial_state
from ..tools import WORKSPACE_DIR, LOGS_DIR, read_file, list_directory, analyze_image, search_web, fetch_web_page, grep_search
from ..tools.base import get_all_files
from .utils import (
    _write_input_messages,
    _write_to_log,
    execute_with_timeout,
    _extract_text,
    is_api_connection_error,
    handle_api_retry,
    log_agent_header,
    log_tool_call,
    MAX_LOG_CHARS,
    truncate_content,
    send_agent_event,
    send_json,
    send_plan_stream,
    send_thought_stream,
    APIConnectionError,
    extract_tool_call_info,
    extract_target_name,
    execute_tool_with_logging,
    detect_repeated_tool_calls,
    MAX_REPEATED_TOOL_CALLS,
    stream_with_token_tracking,
)
from ..usage_tracker import record_api_call
from ..debug_logger import (
    log_strategist_start,
    log_strategist_plan_extracted,
    log_strategist_events_sent,
    log_strategist_return,
    log_exception,
    log_custom,
)


VALID_GRANULARITY_LEVELS = {"low", "medium", "high"}
DEFAULT_GRANULARITY_LEVEL = "medium"

VALID_ACCURACY_MODES = {"eco", "pro"}

# Regex patterns for parsing plan tasks
TASK_PATTERNS = [
    # Markdown headers with Task (e.g., "### **Task 1:" or "## Task 2:")
    r'^#+\s*(?:\*\*)?\s*Task\s+\d+\s*[:：]',          # Markdown header: Task N:
    r'^#+\s*(?:\*\*)?\s*Task\s*[:：]',                # Markdown header: Task:
    # Numbered lists with Task
    r'^\d+[\.\)]\s*(?:\*\*)?\s*Task\s+\d+\s*[:：]',  # Numbered with Task N:
    r'^\d+[\.\)]\s*(?:\*\*)?\s*Task\s*[:：]',        # Numbered with Task:
    # Plain Task (no prefix)
    r'^(?:\*\*)?\s*Task\s+\d+\s*[:：]',              # Task N: (no number prefix)
    r'^(?:\*\*)?\s*Task\s*[:：]',                    # Task: (no number prefix)
]

def _get_archived_context():
    """Get context from archived runs."""
    archive_dir = WORKSPACE_DIR / "archive"
    if not archive_dir.exists():
        return None
    
    context = []
    runs = []
    
    try:
        for item in archive_dir.iterdir():
            if item.is_dir() and item.name.startswith("run_"):
                try:
                    run_num = int(item.name.split("_", 1)[1])
                    runs.append((run_num, item))
                except (ValueError, IndexError):
                    continue
    except (OSError, PermissionError):
        return None
    
    runs.sort()
    
    for run_num, run_path in runs:
        final_results_path = run_path / "final_results"
        log_path = run_path / "logs" / "execution_overview.md"
        summary_path = final_results_path / "summary.md"
        
        run_content = ""
        
        # Read Log
        if log_path.exists():
            try:
                log_content = log_path.read_text(encoding='utf-8')
                run_content += f"{log_content}\n\n"
            except Exception:
                pass
        
        # Read Summary
        if summary_path.exists():
            try:
                summary_content = summary_path.read_text(encoding='utf-8')
                run_content += f"{summary_content}\n"
            except Exception:
                pass
        
        if run_content:
            context.append(f"### Archived Run {run_num}:\n\n{run_content}")
    
    return "\n".join(context) if context else None


def _is_valid_message(msg):
    """Check if a message has valid content."""
    if isinstance(msg, dict):
        content = msg.get('content', '')
    elif isinstance(msg, (SystemMessage, HumanMessage, AIMessage)):
        content = getattr(msg, 'content', '') or ''
    else:
        return True
    
    return isinstance(content, str) and bool(content.strip())


def _normalize_task_line(line):
    """Normalize a task line to consistent format while preserving structure.
    
    For display format like "### **Task 1:** description", we preserve the
    markdown structure but normalize to a consistent internal format.
    """
    # Preserve the original line structure - just clean up extra whitespace
    # The format should be: "### **Task X:** description" or "Task X: description"
    step = line.strip()
    
    # If it's a markdown header format, keep the structure but normalize spacing
    if re.match(r'^#+\s*\*\*', step):
        # Format: "### **Task 1:** description"
        # Normalize to: "### **Task X:** description" (preserve markdown)
        step = re.sub(r'^#+\s+', '### ', step)  # Normalize header level to ###
        # Note: Do NOT remove trailing ** - it's the closing marker for "**Task X:**"
        return step.strip()
    elif re.match(r'^#+', step):
        # Format: "### Task 1:" (no bold)
        step = re.sub(r'^#+\s+', '### ', step)
        return step.strip()
    else:
        # Plain format: "Task 1:" or "1. Task 1:"
        # Drop leading numbering
        step = re.sub(r'^\d+[\.\)]\s*', '', step)
        # Normalize Task N: format
        step = re.sub(r'^Task\s+\d+\s*[:：]\s*', 'Task: ', step, flags=re.IGNORECASE)
        step = re.sub(r'^(?:\*\*)?\s*Task\s*[:：]\s*', 'Task: ', step, flags=re.IGNORECASE)
        return step.strip()


def _is_task_line(line):
    """Check if a line matches task patterns."""
    return any(re.match(pattern, line, flags=re.IGNORECASE) for pattern in TASK_PATTERNS)


def _get_granularity_level():
    """Get and validate granularity level from environment."""
    level = os.getenv("GRANULARITY", DEFAULT_GRANULARITY_LEVEL).lower()
    if level not in VALID_GRANULARITY_LEVELS:
        log_custom("STRATEGIST", f"Warning: Invalid GRANULARITY '{level}', defaulting to '{DEFAULT_GRANULARITY_LEVEL}'")
        return DEFAULT_GRANULARITY_LEVEL
    return level


def _get_accuracy_mode():
    """Get and validate accuracy mode from environment. Required."""
    mode = os.getenv("ACCURACY")
    if not mode:
        raise ValueError("ACCURACY environment variable is required. Valid values: 'eco' or 'pro'")
    mode = mode.lower()
    if mode not in VALID_ACCURACY_MODES:
        raise ValueError(f"Invalid ACCURACY '{mode}'. Valid values: {VALID_ACCURACY_MODES}")
    return mode


def _create_empty_plan_state(error_msg="Received empty response from strategist."):
    """Create state dict for empty plan."""
    return {
        'messages': [AIMessage(content=error_msg)],
        'plan': [],
        'completed_steps': [],
        'step_results': {},
    }


# Wrapper for strategist to exclude docs folder
def _list_directory_no_docs(directory_path: str = ".", pattern: str = "*") -> str:
    """List files and directories, excluding the docs folder."""
    return list_directory.invoke({"directory_path": directory_path, "pattern": pattern, "exclude_docs": True})


# Tool execution mapping for strategist (normal mode - no web search)
STRATEGIST_TOOL_MAP_NORMAL = {
    'read_file': read_file,
    'list_directory': _list_directory_no_docs,
    'analyze_image': analyze_image,
    'grep_search': grep_search,
}

# Tool execution mapping for strategist (replanning mode - with web search)
STRATEGIST_TOOL_MAP_REPLANNING = {
    'read_file': read_file,
    'list_directory': _list_directory_no_docs,
    'analyze_image': analyze_image,
    'grep_search': grep_search,
    'search_web': search_web,
    'fetch_web_page': fetch_web_page,
}

STRATEGIST_TOOL_TIMEOUT = 180  # 3 minute timeout for strategist tools
MAX_TOOL_ITERATIONS = 30


def _execute_tool_calls(tool_calls, is_replanning=False):
    """Execute tool calls and return tool messages."""
    from .utils import send_tool_status
    
    # Select appropriate tool map based on mode
    tool_map = STRATEGIST_TOOL_MAP_REPLANNING if is_replanning else STRATEGIST_TOOL_MAP_NORMAL
    
    tool_messages = []
    for tool_call in tool_calls:
        tool_name, tool_args, _ = extract_tool_call_info(tool_call)
        
        # Skip tools not available in current mode
        if tool_name not in tool_map:
            log_custom("STRATEGIST", f"Tool '{tool_name}' not available in {'replanning' if is_replanning else 'normal'} mode, skipping")
            continue
        
        log_custom("STRATEGIST", f"Using tool: {tool_name}")
        
        # Send status update to web UI - starting tool
        send_tool_status("strategist", tool_name, tool_args, is_complete=False)
        
        # Use shared tool execution function
        result, tool_message = execute_tool_with_logging(
            tool_call=tool_call,
            tool_map=tool_map,
            timeout=STRATEGIST_TOOL_TIMEOUT,
            agent_name="strategist",
            status_messages=None,
            on_status_update=None,
            log_result=True,
            max_result_chars=MAX_LOG_CHARS
        )
        
        log_custom("STRATEGIST", f"Tool '{tool_name}' completed")
        
        # Send step_complete event to web UI
        send_tool_status(
            "strategist", tool_name, tool_args, 
            is_complete=True, 
            tool_result=result,
            idle_status="Analysing Request"
        )
        
        tool_messages.append(tool_message)
    
    return tool_messages


def _extract_plan_from_content(content):
    """Parse plan tasks from LLM response content.
    
    Args:
        content: Response content (string, list, or dict) - will be normalized to string
    
    The function first looks for content wrapped in <PLAN></PLAN> tags.
    If found, only the content within those tags is parsed for tasks.
    Otherwise, falls back to scanning the entire content.
    """
    # Normalize content to string (defensive check in case called directly)
    content = _extract_text(content) if content else ""
    
    # Try to extract content within <PLAN></PLAN> tags
    plan_match = re.search(r'<PLAN>\s*(.*?)\s*</PLAN>', content, flags=re.DOTALL | re.IGNORECASE)
    if plan_match:
        # Use only the content within the plan tags
        content_to_parse = plan_match.group(1).strip()
        from ..debug_logger import log_custom
        log_custom("STRATEGIST", "Found <PLAN> tags, extracting content within tags")
    else:
        # Fall back to parsing entire content
        content_to_parse = content
        from ..debug_logger import log_custom
        log_custom("STRATEGIST", "No <PLAN> tags found, parsing entire content")
    
    plan = []
    lines_checked = 0
    task_lines_found = []
    in_guidance = False
    
    # Common end-of-plan markers or unrelated sections
    STOP_MARKERS = [
        r'^---', 
        r'^\*\*\*', 
        r'^#+\s*(?:\*\*)?\s*Strategic Evaluation', 
        r'^#+\s*(?:\*\*)?\s*Evaluation', 
        r'^#+\s*(?:\*\*)?\s*Analysis',
        r'^#+\s*(?:\*\*)?\s*Conclusion'
    ]
    
    for raw_line in content_to_parse.split('\n'):
        line = raw_line.strip()
        if not line:
            # Empty line - reset guidance flag if we were in guidance
            if in_guidance:
                in_guidance = False
            continue
        
        # Check for stop markers
        if any(re.match(pattern, line, flags=re.IGNORECASE) for pattern in STOP_MARKERS):
            break

        lines_checked += 1
        if _is_task_line(line):
            # Found a new task - reset guidance flag
            in_guidance = False
            cleaned = _normalize_task_line(line)
            if cleaned:
                plan.append(cleaned)
                task_lines_found.append((lines_checked, line[:100]))  # Log first 100 chars
        elif plan and raw_line.strip():
            # If we see a header that is NOT a task line, it likely signals the end of the tasks
            if line.startswith('#') and not _is_task_line(line):
                break
                
            # This is continuation of current task (guidance, details, etc.)
            # Check if this is a guidance line (handles "**Guidance:**" format)
            if re.match(r'^\*\*Guidance[:：]\*\*', line, flags=re.IGNORECASE):
                in_guidance = True
                # Extract guidance text (remove the **Guidance:** marker)
                guidance_text = re.sub(r'^\*\*Guidance[:：]\*\*\s*', '', line, flags=re.IGNORECASE).strip()
                plan[-1] += f"\n**Guidance:** {guidance_text}"
            elif in_guidance:
                # Continue guidance section - preserve formatting
                plan[-1] += f"\n   {raw_line.strip()}"
            else:
                # Regular continuation line (details, bullet points, etc.)
                plan[-1] += f"\n   {raw_line.strip()}"
    
    log_custom("STRATEGIST", "Plan extraction details", {
        "lines_checked": lines_checked,
        "tasks_found": len(plan),
        "task_lines": task_lines_found,
        "content_preview": content_to_parse[:500] if content_to_parse else "",
        "used_plan_tags": plan_match is not None
    })
    
    return plan if plan else ([content.strip()] if content.strip() else ["Analyze task and execute"])


def _get_common_prompt_sections(granularity_level, accuracy_mode):
    """Get common prompt sections shared between standard and replanning modes."""
    # Import GPU info function
    from .utils import _get_gpu_info
    gpu_info = _get_gpu_info()
    
    return f"""## The "Senior Scientist" Mindset:
Before generating the plan, you must apply your deep domain knowledge to foresee and mitigate failure.

## Your Operator's Profile:
You are directing an automated Operator agent capable of running complex computational workflows. It has access to:

* **Simulation Engines:** `mace` (MLFF), `quantum-espresso` (DFT), `lammps` (MD), `raspa3` (GCMC/MD).

* **Python Stack:** `pymatgen`, `ase`, `matplotlib`/`seaborn`, `pandas`.

* **GPU Availability:** {gpu_info}

## Planning Protocol:

### **STEP 1: Adhere to Accuracy Mode**

You must strictly follow the **accuracy mode** which determines the computational methods and level of theory used. This controls the **quality** of calculations.

* **pro (High Accuracy):** "Publication-Grade Precision"
    * **Strategy:** Prioritizes physical rigor and strict numerical convergence. This mode aims to minimize approximations, ensuring results meet the standards required for peer-reviewed research and formal documentation.
    
* **eco (Balanced Speed/Accuracy):** "Efficient Discovery"
    * **Strategy:** Optimizes the balance between predictive accuracy and resource consumption. Utilizes validated approximations to maintain qualitative trends and reliable quantitative estimates without redundant overhead.
    
**Assigned Accuracy Mode:** {accuracy_mode}

### **STEP 2: Adhere to Granularity Level**

You must strictly scale the **granularity** of the workflow. Note: "low" granularity implies **broader tasks** where the Operator handles multiple logical steps in one go, NOT lower accuracy.

* **low (1-3 tasks):** "Coarse-Grained / Streamlined"
    * **Strategy:** Consolidate related operations into single, autonomous tasks. Trust the Operator to handle dependencies (e.g., `Relax` -> `SCF` -> `Bands`) within one Python script.
    * **Goal:** Maximize wall-time efficiency and minimize interruptions.
    * *Example:* "Task 1: Perform full structural relaxation and calculate electronic band structure."

* **medium (4-6 tasks):** "Standard Breakdown"
    * **Strategy:** Separate major scientific phases. Checkpoint after significant state changes (e.g., after structure change, before property calculation).
    * **Goal:** Balanced observability.
    * *Example:* "Task 1: Relax structure." -> "Task 2: SCF Calculation." -> "Task 3: Band Structure."

* **high (7-10 tasks):** "Fine-Grained"
    * **Strategy:** Explicitly isolate every substep, validation check, and post-processing action.
    * **Goal:** Maximum control and step-by-step validation.
    * *Example:* "Task 1: Convergence test." -> "Task 2: Volume relaxation." -> "Task 3: Ion relaxation." -> "Task 4: Static run." -> "Task 5: DOS."

**Assigned Granularity Level:** {granularity_level}

### **STEP 3: Workflow Plan Rules**

Create a concise list of high-level scientific tasks that captures the essential research workflow. 

**Instructions:**

1. **Output Format**
   - You must wrap the final plan in:
   ```
   <PLAN>
   </PLAN>
   ```
   - And state each task as:
   ### **Task X:** [Primary Action — Scientific Objective]
   **Guidance:** [Senior-level scientific insights in executing the task with exceptional intelligence, precision, and foresight. This encompasses a robust methodology, critical key points, and supplementary insights vital for attaining the objective while proactively mitigating risks of failure]

2. **End-of-Workflow Requirement:**  
   - The final task should aggregate results, create plots if necessary, and write a summary analysis (`summary.md`).  
   - Explicitly direct the Operator to save valuable results and plots, must explicitly inform the Operator to name the summary file `summary.md` into the `final_results/` directory under `workspace/`.

3. **Computational Efficiency:** 
    - Prioritize reduced computational cost (e.g., minimal unit cells, lower cutoffs for initial screening) when they do not compromise result accuracy.
    - You MUST not plan the use of ML potentials if GPU resources are unavailable.
"""


def _self_review_plan(initial_plan_content, messages, llm, is_replanning):
    """Automatically trigger self-review of the initial plan.
    
    Args:
        initial_plan_content: The content of the initial plan
        messages: Current message history
        llm: The LLM instance
        is_replanning: Whether in replanning mode
        
    Returns:
        Tuple of (improved_plan_content, response_message)
    """
    from ..debug_logger import log_custom
    
    # Create a concise self-review prompt as a normal user message
    review_prompt = (
        "Please review your plan above and provide an improved version with the same format."
        "Does the plan address all aspects of the original task? Are there any scientific errors or missing critical steps?"
    )
    
    log_custom("STRATEGIST", "Starting self-review of initial plan")
    
    # Append the review prompt as a HumanMessage
    review_messages = messages + [HumanMessage(content=review_prompt)]
    
    # Send update to UI
    send_agent_event("strategist", "working", "Self-reviewing plan")
    
    # Use shared streaming helper with callback for live UI updates
    improved_plan_text = ""
    accumulated_thoughts = ""
    def on_content(text):
        nonlocal improved_plan_text
        improved_plan_text += text
        send_plan_stream(improved_plan_text, is_complete=False)
    
    def on_thought(text):
        nonlocal accumulated_thoughts
        accumulated_thoughts += text
        send_thought_stream("strategist", accumulated_thoughts, is_complete=False)
    
    content, _, _, _ = stream_with_token_tracking(
        llm, review_messages, on_content=on_content, on_thought=on_thought
    )
    
    if accumulated_thoughts:
        send_thought_stream("strategist", accumulated_thoughts, is_complete=True)
    
    improved_content = content if content else None
    
    if not improved_content:
        raise ValueError("Self-review produced no content")
    
    return improved_content, AIMessage(content=improved_content)


def strategist_initial_node(
    state: State, 
    llm: ChatOpenAI, 
    llm_with_tools_normal=None, tools_normal=None,
    llm_with_tools_replanning=None, tools_replanning=None
) -> State:
    """Strategist initial planning node - generates the initial plan.
    
    In replanning mode: generates and extracts plan directly, sets is_replanning=True.
    In standard mode: generates initial plan and stores content for review phase.
    
    Args:
        state: Current state
        llm: Base LLM without tools
        llm_with_tools_normal: LLM with normal mode tools (no web search)
        tools_normal: Normal mode tools list
        llm_with_tools_replanning: LLM with replanning mode tools (with web search)
        tools_replanning: Replanning mode tools list
    """
    from ..debug_logger import log_custom
    log_strategist_start(state)
    
    
    # Get user input from state
    user_input = state.get('user_input', '')
    if not user_input:
        return {
            'messages': [AIMessage(content="Please provide a valid input or question.")],
            'plan': [],
            'completed_steps': [],
            'step_results': {},
            'initial_plan_content': '',
            'is_replanning': False,
        }
    
    # Check if we're in replanning mode (archive exists)
    archive_dir = WORKSPACE_DIR / "archive"
    is_replanning = archive_dir.exists() and archive_dir.is_dir()
    
    # Select appropriate LLM and tools based on mode
    llm_with_tools = llm_with_tools_replanning if is_replanning else llm_with_tools_normal
    tools = tools_replanning if is_replanning else tools_normal
    
    # Build system prompt
    granularity_level = _get_granularity_level()
    accuracy_mode = _get_accuracy_mode()
    archived_context = _get_archived_context()
    
    if archived_context and is_replanning:
        common_sections = _get_common_prompt_sections(granularity_level, accuracy_mode)
        strategist_prompt = f"""# Research Strategist — Replanning Mode

You are the lead computational senior chemist refining a research strategy based on previous computational runs. Use file inspection tools for detailed exploration and search for key information as needed.

## Responsibilities Checklist

- **Assess the Previous Run**
    - Decide: Did it **Succeed** / **Partially Succeed** / **Fail** in its scientific objective?

- **If the Run Failed:**
    - Diagnose the root cause, using:
        1. **User's original message**
        2. **Archived run context**
        3. **Logs/output files:**  
    - Produce a **corrected, improved plan** that directly resolves the issue and increases likelihood of success.

- **If the Run Partially Succeeded:**
    - Identify: What was achieved?  
      What still requires work?
    - Propose **next logical scientific steps** to deepen, extend, or complete the investigation.

## Context from Previous Runs
{archived_context}


## Key Directories for Previous Runs
- `./archive/run_N/`: Full file outputs from run N.
- `./archive/run_N/final_results/`: Results and analysis files from run N.

{common_sections}
"""
    else:
        common_sections = _get_common_prompt_sections(granularity_level, accuracy_mode)
        
        # Check if user has uploaded files to the workspace (excluding docs folder)
        workspace_files = get_all_files()
        # Filter out files in the docs folder
        user_files = {f for f in workspace_files if not f.startswith('docs/')}
        files_note = ""
        if user_files:
            files_note = "The user has uploaded several files to the workspace. Use file inspection tools to examine them as needed."
        
        strategist_prompt = f"""# Role: Research Strategist

You are the lead computational senior chemist designing a computational research strategy. Your goal is to design a robust, scientifically defensible workflow that yields publication-quality insights. {files_note}
{common_sections}
"""
    
    # Build messages with correct order: SystemMessage first, then HumanMessage
    messages = [
        SystemMessage(content=strategist_prompt),
        HumanMessage(content=user_input)
    ]
    
    # Write input messages to file for debugging
    _write_input_messages(messages, "STRATEGIST")
    
    # Send agent start event to Node.js CLI
    status_text = "Replanning" if is_replanning else "Analysing Request"
    send_agent_event("strategist", "start", status_text)

    try:
        api_error_count = 0
        max_api_retries = 3
        
        while api_error_count < max_api_retries:
            try:
                content = None
                response = None
                
                # If tools are available, allow tool calling in both normal and replanning modes
                if llm_with_tools and tools:
                    iteration_count = 0
                    MAX_SAFETY_ITERATIONS = 50 # Safety ceiling, but rely on repeated detection logic
                    
                    while iteration_count < MAX_SAFETY_ITERATIONS:
                        iteration_count += 1
                        
                        # Use shared streaming helper with callback for live UI updates
                        # Use accumulated content for plan_stream (same as no-tools case)
                        accumulated_content = ""
                        accumulated_thoughts = ""
                        def on_content(text):
                            nonlocal accumulated_content
                            accumulated_content += text
                            send_plan_stream(accumulated_content, is_complete=False, is_replanning=is_replanning)
                        
                        def on_thought(text):
                            nonlocal accumulated_thoughts
                            accumulated_thoughts += text
                            send_thought_stream("strategist", accumulated_thoughts, is_complete=False)
                        
                        full_content, tool_calls, _, _ = stream_with_token_tracking(
                            llm_with_tools, messages, on_content=on_content, on_thought=on_thought
                        )
                        
                        if accumulated_thoughts:
                            send_thought_stream("strategist", accumulated_thoughts, is_complete=True)
                        
                        # Create AIMessage with content and tool_calls and append to messages
                        ai_response = AIMessage(content=full_content)
                        if tool_calls:
                            ai_response.tool_calls = tool_calls
                        messages.append(ai_response)
                        
                        if not tool_calls:
                            break
                        
                        tool_messages = _execute_tool_calls(tool_calls, is_replanning=is_replanning)
                        messages.extend(tool_messages)
                        
                        # Check for repeated identical tool calls
                        repeated_tool = detect_repeated_tool_calls(messages)
                        if repeated_tool:
                            tool_name, count = repeated_tool
                            loop_warning = f"""SYSTEM WARNING: Potentially infinite loop detected.
You have called the tool `{tool_name}` {count} times consecutively with the EXACT SAME arguments.
This suggests your current approach is not working.

You MUST stop this immediately and:
1. Analyze why the previous tool calls didn't produce the expected result
2. Change your approach or conclusion
3. If you have enough information, generate the final plan

Do NOT call `{tool_name}` with the same arguments again.
"""
                            already_has_loop_warning = any(
                                isinstance(m, HumanMessage) and getattr(m, "content", "") == loop_warning
                                for m in messages
                            )
                            if not already_has_loop_warning:
                                log_custom("STRATEGIST", f"Detected {count} repeated calls to {tool_name}, injecting warning")
                                messages.append(HumanMessage(content=loop_warning))
                    
                    # Extract final plan from last AI response
                    response = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
                    if not response or not response.content:
                        return {
                            'messages': [AIMessage(content="No plan generated after tool exploration.")],
                            'plan': [],
                            'completed_steps': [],
                            'step_results': {},
                            'initial_plan_content': '',
                            'is_replanning': is_replanning,
                        }
                    content = _extract_text(response.content)
                    
                    # Stream the plan content to CLI for display
                    send_plan_stream(content, is_complete=False, is_replanning=is_replanning)
                    
                    if is_replanning:
                        # In replanning mode, extract plan directly (no review phase)
                        plan = _extract_plan_from_content(content)
                        log_strategist_plan_extracted(plan, content)
                        
                        if plan:
                            send_plan_stream(content, is_complete=True, parsed_plan=plan, is_replanning=True)
                            send_json("task_progress", {"current": 1, "total": len(plan)})
                            
                            log_agent_header("Strategist", 0, "Replanning Complete")
                            formatted_plan = "\n".join(plan)
                            lines = formatted_plan.split('\n')
                            blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
                            _write_to_log(f"{blockquote}\n\n")
                            
                            # Send events to CLI for plan box and status checkmark
                            send_agent_event("strategist", "step_complete", "Created Replan", output=formatted_plan)
                            send_agent_event("strategist", "complete")
                        
                        return_state = {
                            'messages': [response],
                            'plan': plan,
                            'completed_steps': [],
                            'step_results': {},
                            'initial_plan_content': '',  # Not needed in replanning
                            'is_replanning': True,
                        }
                        log_strategist_return(return_state)
                        return return_state
                    else:
                        # In normal mode with tools, return initial_plan_content for review phase
                        initial_plan = _extract_plan_from_content(content)
                        log_custom("STRATEGIST", "Initial plan generated with tools, checkpoint for review phase")
                        
                        send_plan_stream(content, is_complete=True, parsed_plan=initial_plan if initial_plan else None)
                        if initial_plan:
                            log_agent_header("Strategist", 0, "Initial Execution Plan")
                            formatted_initial_plan = "\n".join(initial_plan)
                            lines = formatted_initial_plan.split('\n')
                            blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
                            _write_to_log(f"{blockquote}\n\n")
                            
                            send_agent_event("strategist", "step_complete", "Created Initial Plan", output=formatted_initial_plan)
                        
                        return_state = {
                            'messages': messages,
                            'plan': [],  # Plan not yet finalized - goes to review
                            'completed_steps': [],
                            'step_results': {},
                            'initial_plan_content': content,  # Store for review phase
                            'is_replanning': False,
                        }
                        log_strategist_return(return_state)
                        return return_state
                    
                else:
                    # Standard planning mode (no tools) - use shared streaming helper
                    full_plan_text = ""
                    accumulated_thoughts = ""
                    def on_content(text):
                        nonlocal full_plan_text
                        full_plan_text += text
                        send_plan_stream(full_plan_text, is_complete=False)
                    
                    def on_thought(text):
                        nonlocal accumulated_thoughts
                        accumulated_thoughts += text
                        send_thought_stream("strategist", accumulated_thoughts, is_complete=False)

                    try:
                        content, _, _, _ = stream_with_token_tracking(
                            llm, messages, on_content=on_content, on_thought=on_thought
                        )
                    except Exception as e:
                        # Re-raise API connection errors so they reach the retry logic
                        if is_api_connection_error(e):
                            raise
                        # For non-API errors, try to use accumulated content
                        log_exception("STRATEGIST", e, {"context": "streaming failed, using accumulated content"})
                        content = full_plan_text if full_plan_text else None
                    
                    if not content:
                        return {
                            'messages': [AIMessage(content="Received empty response from strategist.")],
                            'plan': [],
                            'completed_steps': [],
                            'step_results': {},
                            'initial_plan_content': '',
                            'is_replanning': False,
                        }
                    
                    initial_response = AIMessage(content=content)
                    
                    if accumulated_thoughts:
                        send_thought_stream("strategist", accumulated_thoughts, is_complete=True)
                    
                    # Log the initial plan to conversation.md
                    log_custom("STRATEGIST", "Initial plan generated, checkpoint for review phase")
                    initial_plan = _extract_plan_from_content(content)
                    
                    # Send final plan stream update for initial plan phase with parsed_plan
                    # This ensures the frontend displays it with the same task-list styling as reviewed plan
                    send_plan_stream(content, is_complete=True, parsed_plan=initial_plan if initial_plan else None)
                    if initial_plan:
                        log_agent_header("Strategist", 0, "Initial Execution Plan")
                        formatted_initial_plan = "\n".join(initial_plan)
                        lines = formatted_initial_plan.split('\n')
                        blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
                        _write_to_log(f"{blockquote}\n\n")
                        
                        # Send initial plan as step_complete for collapsible display in web UI
                        send_agent_event("strategist", "step_complete", "Created Initial Plan", output=formatted_initial_plan)
                    
                    # Return state with initial_plan_content for review phase
                    # Don't set plan yet - that happens in review phase
                    # Initial state has empty messages, so return full conversation:
                    # [SystemMessage, HumanMessage, AIMessage]
                    messages.append(initial_response)
                    return_state = {
                        'messages': messages,
                        'plan': [],  # Plan not yet finalized
                        'completed_steps': [],
                        'step_results': {},
                        'initial_plan_content': content,  # Store for review phase
                        'is_replanning': False,
                    }
                    
                    log_strategist_return(return_state)
                    return return_state
                    
            except Exception as e:
                log_exception("STRATEGIST", e, {"api_error_count": api_error_count, "is_replanning": is_replanning})
                
                if is_api_connection_error(e):
                    api_error_count += 1
                    if handle_api_retry("strategist", e, api_error_count, max_api_retries):
                        continue
                    # handle_api_retry already sent error to UI, return error state
                    error_state = {
                        'messages': [AIMessage(content=f"API Error: {str(e)}")],
                        'plan': [],
                        'completed_steps': [],
                        'step_results': {},
                        'initial_plan_content': '',
                        'is_replanning': is_replanning,
                    }
                    log_strategist_return(error_state)
                    return error_state
                else:
                    error_state = {
                        'messages': [AIMessage(content=f"Error in planning: {str(e)}")],
                        'plan': [],
                        'completed_steps': [],
                        'step_results': {},
                        'initial_plan_content': '',
                        'is_replanning': is_replanning,
                    }
                    log_strategist_return(error_state)
                    return error_state
        
        final_error_state = {
            'messages': [AIMessage(content="Exceeded max retries for API connection errors.")],
            'plan': [],
            'completed_steps': [],
            'step_results': {},
            'initial_plan_content': '',
            'is_replanning': is_replanning,
        }
        log_strategist_return(final_error_state)
        return final_error_state
        
    except Exception as e:
        log_exception("STRATEGIST", e, {"outer_exception": True})
        if is_api_connection_error(e):
            raise e
        error_state = {
            'messages': [AIMessage(content=f"Error in planning: {str(e)}")],
            'plan': [],
            'completed_steps': [],
            'step_results': {},
            'initial_plan_content': '',
            'is_replanning': False,
        }
        log_strategist_return(error_state)
        return error_state


def strategist_review_node(state: State, llm: ChatOpenAI) -> State:
    """Strategist review node - performs self-review of the initial plan.
    
    Takes initial_plan_content from state and generates an improved plan.
    Only called in standard mode (not replanning).
    """
    from ..debug_logger import log_custom
    
    initial_plan_content = state.get('initial_plan_content', '')
    
    if not initial_plan_content:
        log_custom("STRATEGIST_REVIEW", "No initial plan content found, skipping review")
        # If no initial plan content, just pass through
        return {
            'messages': state.get('messages', []),
            'plan': state.get('plan', []),
            'completed_steps': state.get('completed_steps', []),
            'step_results': state.get('step_results', {}),
            'initial_plan_content': '',
            'is_replanning': state.get('is_replanning', False),
        }
    
    log_custom("STRATEGIST_REVIEW", "Starting self-review of initial plan")
    
    # Use messages from state - they are now in correct order:
    # [SystemMessage, HumanMessage, AIMessage]
    messages = list(state.get('messages', []))

    # Write input messages to file for debugging
    review_prompt = (
        "Please review your plan above and provide an improved version with the same format."
        "Does the plan address all aspects of the original task? Are there any scientific errors or missing critical steps?"
    )
    # Create a separate list for logging to include the prompt that _self_review_plan will add
    log_messages = messages + [HumanMessage(content=review_prompt)]
    _write_input_messages(log_messages, "STRATEGIST_REVIEW")
    
    try:
        # Perform self-review and get improved plan
        improved_content, improved_response = _self_review_plan(
            initial_plan_content=initial_plan_content,
            messages=messages,
            llm=llm,
            is_replanning=False
        )
        
        # Extract final plan from improved content
        plan = _extract_plan_from_content(improved_content)
        log_strategist_plan_extracted(plan, improved_content)
        
        if plan:
            events_to_send = [
                {"type": "plan_stream", "is_complete": True},
                {"type": "agent_event", "agent": "strategist", "event": "complete", "status": "Reviewed Plan"},
                {"type": "task_progress", "current": 1, "total": len(plan)}
            ]
            log_strategist_events_sent(events_to_send)
            
            send_plan_stream(improved_content, is_complete=True, parsed_plan=plan)
            
            log_agent_header("Strategist", 0, "Reviewed Plan")
            formatted_plan = "\n".join(plan)
            lines = formatted_plan.split('\n')
            blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
            _write_to_log(f"{blockquote}\n\n")
            
            send_agent_event("strategist", "step_complete", "Reviewed Plan", output=formatted_plan)  # For execution history
            send_agent_event("strategist", "complete")  # For agent state transition (empty status avoids duplicate log)
            send_json("task_progress", {"current": 1, "total": len(plan)})
        
        # Prepare return messages - include ALL messages from initial phase plus review exchange
        # This preserves strategist's tool-calling AIMessages and ToolMessages for history retrieval
        return_messages = list(messages)  # Copy all messages from initial phase
        # Add the review prompt and improved response
        review_prompt = (
            "Does the plan address all aspects of the original task? Are there any scientific errors or missing critical steps? "
            "Please review your plan above and provide an improved version with the same format"
        )
        return_messages.append(HumanMessage(content=review_prompt))
        return_messages.append(improved_response)
        
        return_state = {
            'messages': return_messages,
            'plan': plan,
            'completed_steps': [],
            'step_results': {},
            'initial_plan_content': '',  # Clear, no longer needed
            'is_replanning': False,
        }
        
        log_strategist_return(return_state)
        return return_state
        
    except Exception as e:
        log_exception("STRATEGIST_REVIEW", e, {"context": "self-review failed"})
        
        # Fall back to using initial plan if review fails
        plan = _extract_plan_from_content(initial_plan_content)
        
        if plan:
            send_plan_stream(initial_plan_content, is_complete=True, parsed_plan=plan)
            send_agent_event("strategist", "complete", "Initial Plan (Review Failed)")
            send_json("task_progress", {"current": 1, "total": len(plan)})
        
        return_state = {
            'messages': state.get('messages', []),
            'plan': plan,
            'completed_steps': [],
            'step_results': {},
            'initial_plan_content': '',
            'is_replanning': False,
        }
        log_strategist_return(return_state)
        return return_state


# Keep old function name as alias for backward compatibility (deprecated)
def strategist_node(state: State, llm: ChatOpenAI, llm_with_tools=None, tools=None) -> State:
    """DEPRECATED: Use strategist_initial_node and strategist_review_node instead.
    
    This function is kept for backward compatibility but should not be used.
    It now just calls strategist_initial_node.
    """
    from ..debug_logger import log_custom
    log_custom("STRATEGIST", "WARNING: Using deprecated strategist_node, use strategist_initial_node instead")
    return strategist_initial_node(state, llm, llm_with_tools, tools)

