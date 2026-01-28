"""
Operator agent node implementation.
"""

import os
import re
import time
from pathlib import Path
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage
from ..debug_logger import log_operator_start, log_exception, log_custom
from ..pending_execution import save_pending_execution, load_pending_execution, clear_pending_execution
from .utils import update_operator_status, TOOL_STATUS_MESSAGES

from ..state import State
from ..tools import (
    query_rag,
    read_file,
    write_file,
    edit_file,
    delete_file,
    list_directory,
    move_file,
    rename_file,
    analyze_image,
    execute_python,
    resume_execution,
    interrupt_running_execution,
    has_running_process,
    continue_execution,
    interrupt_execution,
    search_web,
    fetch_web_page,
    complete_task,
    is_rag_enabled,
    grep_search,
    get_hardware_info,
)
from .utils import (
    _write_input_messages,
    _extract_text,
    execute_with_timeout,
    StreamingTimeoutError,
    _write_to_log,
    log_agent_header,
    log_tool_call,
    get_project_context,
    write_execution_log,
    is_api_connection_error,
    handle_api_retry,
    MAX_LOG_CHARS,
    truncate_content,
    send_agent_event,
    send_json,
    send_text_stream,
    send_thought_stream,
    APIConnectionError,
    extract_tool_call_info,
    extract_target_name,
    extract_project_request,
    format_plan,
    format_history,
    execute_tool_with_logging,
    ValidationError,
    format_validation_error,
    detect_repeated_tool_calls,
    MAX_REPEATED_TOOL_CALLS,
    stream_with_token_tracking,
)
from ..tools.base import get_all_files

# Tool execution mapping
TOOL_MAP = {
    'query_rag': query_rag,
    'read_file': read_file,
    'write_file': write_file,
    'edit_file': edit_file,
    'delete_file': delete_file,
    'list_directory': list_directory,
    'move_file': move_file,
    'rename_file': rename_file,
    'analyze_image': analyze_image,
    'search_web': search_web,
    'fetch_web_page': fetch_web_page,
    'execute_python': execute_python,
    'complete_task': complete_task,
    'grep_search': grep_search,
    'get_hardware_info': get_hardware_info,
}

OTHER_TOOL_TIMEOUT = 600
LLM_RESPONSE_TIMEOUT = 600
MAX_RETRIES = 2


def operator_node(state: State, llm_with_tools, all_tools) -> State:
    """Operator agent that executes individual steps from the plan."""
    log_operator_start(state)

    plan = state.get('plan', [])
    completed_steps = state.get('completed_steps', [])
    step_results = state.get('step_results', {})
    current_task_messages = state.get('current_task_messages', [])
    current_task_index = len(completed_steps)
    
    if current_task_index >= len(plan):
        send_json("task_progress", {"current": len(plan), "total": len(plan)})
        return {"messages": [AIMessage(content="DONE")]}

    if plan:
        current_task = plan[current_task_index]
        # Extract clean task title for progress event
        task_title = current_task.split('\n')[0].strip()
        # Remove markdown headers
        while task_title.startswith('#'):
            task_title = task_title.lstrip('#').strip()
        # Remove all ** pairs (markdown bold)
        task_title = task_title.replace('**', '')
        # Remove single * at start/end
        task_title = task_title.strip().lstrip('*').rstrip('*').strip()
        # Remove Task N: prefix
        task_title = re.sub(r'^Task\s+\d+[:：]\s*', '', task_title, flags=re.IGNORECASE).strip()
        send_json("task_progress", {"current": current_task_index + 1, "total": len(plan), "title": task_title})
    
    send_agent_event("operator", "start", "Analysing Task")
    current_task = plan[current_task_index]
    
    if not current_task_messages:
        task_desc = current_task.split('\n')[0].strip()
        
        # Remove markdown prefixes
        while task_desc.startswith('#'):
            task_desc = task_desc.lstrip('#').strip()
        # Remove all ** pairs (markdown bold)
        task_desc = task_desc.replace('**', '')
        # Remove single * at start/end
        task_desc = task_desc.strip().lstrip('*').rstrip('*').strip()
        # Remove Task N: prefix
        task_desc = re.sub(r'^Task\s+\d+[:：]\s*', '', task_desc, flags=re.IGNORECASE).strip()
        
        log_agent_header("Operator", current_task_index, f"Executing: **{task_desc}**")
    
    formatted_plan = format_plan(plan)
    formatted_history = format_history(step_results, completed_steps)
    messages = state.get('messages', [])
    project_request = extract_project_request(messages)
    write_execution_log(project_request, formatted_plan, formatted_history)
    
    initial_files = None
    if not current_task_messages:
        initial_files = list(get_all_files())
        
        is_last_step = current_task_index == len(plan) - 1
        project_request_section = f"## Project Request\n{project_request}\n\n" if is_last_step else ""
        
        operator_context = f"""[PROJECT STATE]

{project_request_section}## Previous Task Summaries
{formatted_history}

## Current Task
{current_task}
"""
        
        pmg_mapi_available = "; `Materials Project API` (env: PMG_MAPI_KEY); " if os.getenv("PMG_MAPI_KEY") else "."
        rag_enabled = is_rag_enabled()
        
        if rag_enabled:
            level_2_section = """ELSE
    IF (tool ∈ {Quantum ESPRESSO, LAMMPS, RASPA3, MACE, pymatgen, ASE})
        → query_rag
        IF (result truncated AND relevant)
            → read_file(path)

    IF (tool == Quantum ESPRESSO AND example required)
        → navigate ./docs/q-e/{PW,PHonon,PP}/examples
        → read README.md
        → inspect example input/output files

    IF (tool == RASPA3 AND example required)
        → navigate ./docs/RASPA3/examples/{basic,advanced,auxiliary,non_basic,reduced_units}
        → inspect example input/output files

    IF (tool == LAMMPS AND example required)
        → navigate ./docs/lammps/examples
        → read README.md
        → inspect example input/output files

    IF (no relevant example found OR error unresolved)
        → search_web
        → fetch_web_page
"""
        else:
            level_2_section = """ELSE
    IF (tool == Quantum ESPRESSO AND example required)
        → navigate ./docs/q-e/{PW,PHonon,PP}/examples
        → read README.md
        → inspect example input/output files

    IF (tool == RASPA3 AND example required)
        → navigate ./docs/RASPA3/examples/{basic,advanced,auxiliary,non_basic,reduced_units}
        → inspect example input/output files

    IF (tool == LAMMPS AND example required)
        → navigate ./docs/lammps/examples
        → read README.md
        → inspect example input/output files

    IF (no relevant example found OR error unresolved)
        → search_web
        → fetch_web_page
"""
        
        operator_system_prompt = f"""### Role: Computational Chemistry Operator
You are responsible for fulfilling high-level scientific objectives in computational chemistry with rigor, accuracy, and reproducibility.

### 1. Operational Environment & Resources
**Simulation Engines:** `mace` (ML Potential), `quantum-espresso` (DFT), `raspa3` (GCMC), `lammps` (MD).
**Python Stack:** `pymatgen`, `ase`, `matplotlib`, `seaborn`, `pandas`.
**Data Access:**
* **Local Filesystem:** read/write access.
* **Remote:** `wget`/`curl` for external files{pmg_mapi_available}
* **Web:** `search_web` and `fetch_web_page` for live information gathering.
* **Pre-provided QE Pseudopotentials:** `./docs/q-e/SSSP` and `./docs/q-e/PseudoDojo`.
    * Must use **SSSP** for PBE calculations.
    * Must use **PseudoDojo** for hybrid calculations (e.g., HSE06/PBE0).

### 2. Tool Protocols & Information Hierarchy
IF (syntax AND physics are known with high confidence)
    → write_file
{level_2_section}

### 3. Simulation Concurrency & Parallelism Strategy
Apply parallelization intelligently based on the software and your specific calculation to maxmise performance:

**MPI Parallelization:**
    * **Execution:** `mpirun -np <N_CORES> <COMMAND>`
    * **Quantum ESPRESSO:** Start by maximizing k-point parallelism using -npool. For example: `mpirun -np 128 pw.x -npool 8 < input.in > output.out` where n_kpoints must be divisible by n_pools; n_cores should align. If FFT or real-space operations dominate the runtime, introduce task groups with -ntg to further reduce FFT bottlenecks.
    * **LAMMPS:** Aim for 400-1000 atoms per rank. Avoid low atoms/rank to prevent communication overhead.

**OpenMP Parallelization:**
    * **Quantum ESPRESSO & LAMMPS:** Set `OMP_NUM_THREADS` to enable hybrid MPI/OpenMP when MPI communication limits scaling and there is heavy intra-rank computation (FFT/BLAS) on many-core CPUs.
    * **MACE ML Potential:** 
        * **Execution:** When running on CPU, explicitly set `OMP_NUM_THREADS` to <N_CORES> before executing the command to fully utilize available cores. When running on GPU, this setting should be ignored.
    * **Set OMP_NUM_THREADS:** The OMP_NUM_THREADS environment variable can be defined through the execute_python argument or explicitly in the script. The default setting is 1.

**Job Concurrency:**
    * **RASPA3:**
        * **Core Configure:** Single-core executable. To utilize multiple cores, write Python scripts using `multiprocessing` or `concurrent.futures` to run distinct simulations (e.g., different pressure points) simultaneously
        * **Execution:** Run via `raspa3` command in python for the folder containing the required input files.
    * **Quantum ESPRESSO & LAMMPS:** When running multiple independent calculations (e.g., different structures, compositions, or parameters), Python `multiprocessing` or `concurrent.futures` can be employed to execute jobs concurrently across available resources. Always optimize MPI and OpenMP settings first then consider job concurrency.

IMPORTANT: Always use `get_hardware_info` function to check available cores before running simulations. Avoid hard-coding core counts; ensure the parallelization strategy scales dynamically with the detected hardware. Do NOT attempt to detect hardware using Python code (e.g., multiprocessing.cpu_count(), os.cpu_count(), psutil) - these return incorrect values in containerized/Slurm environments. ONLY use the `get_hardware_info` tool.

### 4. Execution Rules (CRITICAL)
1. **Simulation Verification:** Before running the production calculation, you must do the following:
    * **Step 1: Input Parameters:** Verify that the simulation parameters are appropriate for achieving high-quality results and reasonable computational speed.
    * **Step 2: Execute Script:** Run the script using `execute_python` function.
    * **Step 3: Analyze Output:** Inspect the output to confirm error-free execution, correct physics, and reasonable computational performance. If errors, bottlenecks, or poor scaling are observed, adjust runtime parameters and re-run.

2. **Restart Calculations:** You should and must enable the restart mode for all calculations to ensure recovery from long or interrupted jobs
    - Quantum ESPRESSO: Set `restart_mode = 'restart'` in the input file even for the first run.
    - LAMMPS: enable periodic restart writing using the command `restart <Nsteps> <restart_filename>` in the input file.
    - RASPA3: restart files are written automatically.

3. **Hard Constraints:** 
    - Focus solely on the `## CURRENT TASK` and execute all actions within a dedicated folder named `task_N` for that task.
    - Once the designated task is finished, you MUST call the `complete_task` tool to officially mark it as complete.
    - Do NOT use `pymatgen` or `ase` wrappers such as `ase.calculators.espresso` for running qe or lammps calculations. You must generate input files in their native format.
    - Concurrent Jobs x MPI_ranks x OMP_NUM_THREADS <= Total Physical cores.
    - Remove outdated or failed scripts and any crash-generated output related to this task.

4. **Golden Rules:**
    - A simulation completion does not mean the outputs are correct, always verify the output quality
    - If a simulation is interrupted or fails and valid partial data exists, resume execution from the last checkpoint rather than restarting from scratch.
    - If exhaustive checks determine that the task requirements are infeasible, identify and implement an appropriate workaround or alternative solution.
"""
        
        current_task_messages = [
            SystemMessage(content=operator_system_prompt),
            HumanMessage(content=operator_context)
        ]
    else:
        # Check for pending execution from SIGKILL scenario (file-based recovery)
        pending_exec = load_pending_execution()
        if pending_exec and pending_exec.get('task_index') == current_task_index:
            # Found a pending execution that was interrupted by SIGKILL
            # Inject AIMessage + synthetic ToolMessage to inform the LLM
            tool_call = pending_exec['tool_call']
            ai_msg = AIMessage(
                content=pending_exec.get('ai_message_content', ''),
                tool_calls=[tool_call]
            )
            tool_msg = ToolMessage(
                content="""The Python execution was forcefully terminated (e.g., SIGKILL, timeout). Partial output may exist. Inspect the output: 
- If the output is invalid, fix the script and rerun.
- If valid partial data is present, resume execution from the last checkpoint rather than restarting from scratch.
- Before resuming, you MUST verify using `get_hardware_info` to ensure the hardware configuration has not changed since the interruption.

Restart mechanisms:
1. **Quantum ESPRESSO**:
Ensure restart_mode = 'restart' is set in the &CONTROL section of the input file to allow continuation. If not, update the input file accordingly and re-execute the calculation.

2. **LAMMPS**:
Inspect the output directory for existing restart files and resume from the most recent one rather than restarting from the initial data file. If a restart mechanism is not already defined, configure it in the input script and re-execute the run.

3. **RASPA3**:
Review the restart instructions at `./docs/RASPA3/docs/manual/restart.md` and resume the simulation using the generated restart files.""",
                tool_call_id=tool_call['id']
            )
            
            # Check if already added to avoid duplicates
            last_ai_msg = None
            for msg in reversed(current_task_messages):
                if isinstance(msg, AIMessage):
                    last_ai_msg = msg
                    break
            
            # Only add if the AI message isn't already there
            if not last_ai_msg or getattr(last_ai_msg, 'tool_calls', None) != [tool_call]:
                current_task_messages.append(ai_msg)
                current_task_messages.append(tool_msg)
                _write_input_messages(current_task_messages, "OPERATOR", current_task_index)
                log_custom("OPERATOR", "Injected interrupted execution messages", {"tool_call_id": tool_call['id']})
            
            # Clear the pending execution file
            clear_pending_execution()
        
        # Check for repeated identical tool calls (infinite loop detection)
        repeated_tool = detect_repeated_tool_calls(current_task_messages)
        if repeated_tool:
            tool_name, count = repeated_tool
            loop_warning = f"""SYSTEM WARNING: Potentially infinite loop detected.
You have called the tool `{tool_name}` {count} times consecutively with the EXACT SAME arguments.
This suggests your current approach is not working or you are stuck.

You MUST stops this immediately and:
1. Analyze why the previous tool calls didn't produce the expected result
2. Change your approach, parameters, or tool usage
3. If the task seems impossible with current tools, report the issue using complete_task

Do NOT call `{tool_name}` with the same arguments again.
"""
            already_has_loop_warning = any(
                isinstance(m, HumanMessage) and getattr(m, "content", "") == loop_warning
                for m in current_task_messages
            )
            if not already_has_loop_warning:
                _write_to_log(f"\n**[SYSTEM]** Detected {count} repeated calls to `{tool_name}`. Injecting warning.\n")
                current_task_messages.append(HumanMessage(content=loop_warning))
    
    _update_operator_status = update_operator_status
    
    try:
        response = None
        full_content = ""
        tool_calls = []
        completion_request = None
        seen_tool_calls = set()
        
        def on_tool_call_detected(tool_name: str, tool_args: dict):
            """Called immediately when a tool call is first detected in the stream."""
            file_path = tool_args.get('file_path', '') if isinstance(tool_args, dict) else ''
            tool_call_key = (tool_name, str(file_path))
            
            if tool_call_key not in seen_tool_calls:
                seen_tool_calls.add(tool_call_key)
                _update_operator_status(tool_name, tool_args, is_complete=False)
        
        retry_count = 0
        api_error_count = 0
        
        while retry_count <= MAX_RETRIES:
            try:
                if retry_count > 0:
                    retry_msg = f"Retrying ({retry_count}/{MAX_RETRIES})..."
                    send_agent_event("operator", "update", retry_msg)

                saw_tool_calls = False
                full_content = ""
                tool_calls = []
                
                start_time = time.time()
                
                try:
                    # Use shared streaming helper with timeout wrapper
                    accumulated_text = ""
                    accumulated_thoughts = ""
                    
                    def on_content(text):
                        nonlocal accumulated_text
                        accumulated_text += text
                        # Check timeout during streaming
                        if time.time() - start_time > LLM_RESPONSE_TIMEOUT:
                            raise StreamingTimeoutError(f"LLM response generation timed out (exceeded {LLM_RESPONSE_TIMEOUT // 60} minutes)")
                        # Stream text to UI for real-time display
                        send_text_stream("operator", accumulated_text, is_complete=False)
                    
                    def on_thought(text):
                        nonlocal accumulated_thoughts
                        accumulated_thoughts += text
                        send_thought_stream("operator", accumulated_thoughts, is_complete=False)
                    
                    full_content, tool_calls, response, was_stopped_early = stream_with_token_tracking(
                        llm_with_tools, current_task_messages, on_content=on_content, on_thought=on_thought,
                        detect_repetition=True  # Auto-stop on repetitive output
                    )
                    
                    if was_stopped_early:
                        log_custom("OPERATOR", "Generation stopped early due to repetition detection")
                    
                    # Update UI with detected tool calls after streaming completes
                    for tc in tool_calls:
                        tool_name = tc.get('name', '')
                        tool_args = tc.get('args', {})
                        if tool_name:
                            on_tool_call_detected(tool_name, tool_args if isinstance(tool_args, dict) else {})
                    
                    if accumulated_thoughts:
                        send_thought_stream("operator", accumulated_thoughts, is_complete=True)
                    
                    if tool_calls:
                        saw_tool_calls = True
                    
                    
                    # Create AIMessage if response is None
                    if not response:
                        response = AIMessage(content=full_content)
                    elif full_content and getattr(response, 'content', '') != full_content:
                        response.content = full_content
                    elif not isinstance(getattr(response, 'content', ''), str):
                        response.content = str(full_content) if full_content else ""
                        
                    if tool_calls and (not hasattr(response, 'tool_calls') or not response.tool_calls):
                        response.tool_calls = tool_calls
                    
                    break
                    
                except StreamingTimeoutError as e:
                    retry_count += 1
                    timeout_msg = f"\n[OPERATOR] LLM response generation timed out: {str(e)}\n"
                    _write_to_log(timeout_msg)

                    
                    if retry_count > MAX_RETRIES:
                        raise
                
                except ValueError as e:
                    # Handle empty response errors from LangChain
                    error_msg_str = str(e)
                    if "empty" in error_msg_str.lower() or "must contain" in error_msg_str.lower():
                        retry_count += 1
                        _write_to_log(f"\n[OPERATOR] Empty response from LLM: {error_msg_str}. Retrying ({retry_count}/{MAX_RETRIES})...\n")
                        send_agent_event("operator", "update", "Empty response, retrying...")
                        if retry_count > MAX_RETRIES:
                            # Return error to prompt retry
                            _write_to_log("\n[OPERATOR] Max retries exceeded for empty response.\n")
                            error_msg = "Error: Received empty response from LLM after retries. Please retry your last step."
                            update = {
                                'messages': [HumanMessage(content=error_msg)],
                                'current_task_messages': current_task_messages + [HumanMessage(content=error_msg)]
                            }
                            if initial_files is not None:
                                update["files_at_task_start"] = initial_files
                            return update
                        continue  # Retry the while loop
                    else:
                        raise
                    
                except APIConnectionError as e:
                    api_error_count += 1
                    if handle_api_retry("operator", e, api_error_count, max_retries=3):
                        continue
                    # handle_api_retry already sent error to UI
                    error_message = f"API Error executing step: {str(e)}"
                    error_msg = AIMessage(content=error_message)
                    update = {
                        'messages': [error_msg],
                        'current_task_messages': current_task_messages + [error_msg]
                    }
                    if initial_files is not None:
                        update["files_at_task_start"] = initial_files
                    return update
                    
                except Exception as e:
                    _write_to_log(f"\n---\n\n**[OPERATOR] Error during LangChain streaming:**\n\n> {str(e)}\n\n")
                    raise
            except Exception as e:
                if is_api_connection_error(e):
                    api_error_count += 1
                    if handle_api_retry("operator", e, api_error_count, max_retries=3):
                        continue
                    # handle_api_retry already sent error to UI
                    error_message = f"API Error executing step: {str(e)}"
                    error_msg = AIMessage(content=error_message)
                    update = {
                        'messages': [error_msg],
                        'current_task_messages': current_task_messages + [error_msg]
                    }
                    if initial_files is not None:
                        update["files_at_task_start"] = initial_files
                    return update
                raise
        
        if response is None or (not full_content.strip() and not tool_calls):
            _write_to_log("\n---\n\n**[OPERATOR] Warning:**\n\n> Received empty response from LLM. Prompting to retry...\n\n")
            error_msg = "Error: You sent an empty response. Please retry your last step or provide a status update."
            update = {
                'messages': [HumanMessage(content=error_msg)],
                'current_task_messages': current_task_messages + [HumanMessage(content=error_msg)]
            }
            if initial_files is not None:
                update["files_at_task_start"] = initial_files
            return update
        
        tool_messages = []
        called_tools = set()
        
        # Send text stream completion signal if there was content
        if full_content.strip():
            send_text_stream("operator", full_content, is_complete=True)
        
        # Add response to current_task_messages immediately (before tool execution)
        # This ensures the AIMessage is persisted to checkpoint if interrupted during tool execution
        if response:
            current_task_messages = current_task_messages + [response]
            _write_input_messages(current_task_messages, "OPERATOR", current_task_index)
        
        if tool_calls:
            # First pass: detect write_file calls and send content to CLI
            for tc in tool_calls:
                tool_name, tool_args, _ = extract_tool_call_info(tc)
                if tool_name == 'write_file' and isinstance(tool_args, dict) and 'content' in tool_args:
                    content = tool_args.get('content', '')
                    if content:
                        target_name = extract_target_name(tool_name, tool_args) if tool_args else None
                        file_name = target_name or tool_args.get('file_path', 'file')
                        # Skip summary.md as it will be displayed as a special "Run Summary" item
                        if not file_name.endswith('summary.md'):
                            send_json("file_content", {"name": file_name, "content": content[:5000]})
                        _update_operator_status(tool_name, tool_args, is_complete=False)
                
            for tc in tool_calls:
                tool_name, tool_args, _ = extract_tool_call_info(tc)
                called_tools.add(tool_name)
                if tool_name == 'complete_task':
                    completion_request = True
            
            def on_operator_status_update(tool_name: str, tool_args: dict, is_complete: bool):
                """Update operator status - preserves special handling for various tools."""
                if not is_complete:
                    skip_update = tool_name == 'write_file' and isinstance(tool_args, dict) and 'content' in tool_args
                    if not skip_update:
                        _update_operator_status(tool_name, tool_args, is_complete=False, tool_result=None)
                else:
                    # Skip these tools here - we handle them specially after execution to pass tool_result for error detection
                    skip_step_complete = tool_name in ('complete_task', 'read_file', 'query_rag', 'list_directory', 'search_web', 'fetch_web_page', 'grep_search', 'get_hardware_info')
                    if not skip_step_complete:
                        _update_operator_status(tool_name, tool_args, is_complete=True, tool_result=None)

            
            for tool_call in tool_calls:
                tool_name, tool_args, tool_call_id = extract_tool_call_info(tool_call)
                tool = TOOL_MAP.get(tool_name)
                
                if tool_name == 'execute_python' and tool:
                    target_name = extract_target_name(tool_name, tool_args) if tool_args else None
                    
                    # Save pending execution state in case of SIGKILL
                    save_pending_execution(
                        ai_message_content=getattr(response, 'content', ''),
                        tool_call={
                            "id": tool_call_id,
                            "name": tool_name,
                            "args": tool_args
                        },
                        task_index=current_task_index
                    )
                    
                    log_tool_call(tool_name, target_name, status="started", agent="operator")
                    
                    result = tool.invoke(tool_args)
                    
                    # Handle check-in flow if result is a dict with check_in_required status
                    while isinstance(result, dict) and result.get('status') == 'check_in_required':
                        elapsed_display = result.get('elapsed_display', 'unknown time')
                        file_path_display = result.get('file_path', 'script')
                        
                        # Update status to show waiting for decision
                        send_agent_event("operator", "update", f"Awaiting decision after {elapsed_display}")
                        
                        # Log the check-in
                        checkin_msg = f"\n[OPERATOR] Python script has been running for {elapsed_display}. Prompting for continue/interrupt decision.\n"
                        _write_to_log(checkin_msg)
                        
                        # Create check-in prompt for LLM
                        checkin_prompt = f"""The Python script `{os.path.basename(file_path_display)}` has been running for {elapsed_display}.

Use the `read_file`, `grep_search` and `list_directory` tools to review the current outputs for the script and evaluate the simulation status:

1. Convergence/Progress: Is the simulation actually moving toward a valid and stable termination?

2. Anomalies: Are there any unexpected values or warnings that contradict the simulation's goals?

Based on this assessment, determine whether execution should proceed or be terminated.

After you have performed the internal assessment, you must submit a decision by invoking exactly one of the following tools:
- `continue_execution()` — Allow the simulation to proceed (status will be re-evaluated at the next interval).
- `interrupt_execution(reason="...")` — Halt execution and retrieve partial results. A clear justification for interruption is required.
"""
                        
                        # Create tool set for check-in decision (includes filesystem tools for inspection)
                        checkin_tools = [continue_execution, interrupt_execution, read_file, list_directory, grep_search]
                        checkin_llm = llm_with_tools.bind_tools(checkin_tools)
                        
                        # Tool map for check-in filesystem tools
                        checkin_tool_map = {
                            'read_file': read_file,
                            'list_directory': list_directory,
                            'grep_search': grep_search,
                        }
                        
                        # Build check-in messages (add to current context)
                        checkin_human_msg = HumanMessage(content=checkin_prompt)
                        checkin_messages = current_task_messages + [checkin_human_msg]
                        
                        try:
                            # Loop until LLM makes a continue/interrupt decision
                            # LLM may call filesystem tools first to inspect output files
                            decision_made = False
                            should_continue = True  # Default to continue
                            interrupt_reason = ""
                            max_checkin_iterations = 15  # Prevent infinite loops
                            checkin_iteration = 0
                            
                            while not decision_made and checkin_iteration < max_checkin_iterations:
                                checkin_iteration += 1
                                
                                # Get LLM decision with timeout (default to continue if timeout)
                                start_decision_time = time.time()
                                decision_timeout = 120  # 2 minutes per iteration
                                
                                decision_response = None
                                decision_tool_calls = []
                                
                                # Stream the decision
                                def on_checkin_content(text):
                                    if time.time() - start_decision_time > decision_timeout:
                                        raise StreamingTimeoutError("Decision timeout")
                                
                                _, decision_tool_calls, decision_response, _ = stream_with_token_tracking(
                                    checkin_llm, checkin_messages, on_content=on_checkin_content,
                                    detect_repetition=False
                                )
                                
                                # Handle empty response - default to continue
                                if not decision_tool_calls and (not decision_response or not getattr(decision_response, 'content', '').strip()):
                                    _write_to_log("\n[OPERATOR] Empty LLM response during check-in, defaulting to continue.\n")
                                    decision_made = True
                                    should_continue = True
                                    break
                                
                                # Add decision response to messages
                                if decision_response:
                                    checkin_messages = checkin_messages + [decision_response]
                                
                                # Process tool calls
                                if decision_tool_calls:
                                    checkin_tool_messages = []
                                    
                                    for dtc in decision_tool_calls:
                                        dtc_name = dtc.get('name', '') if isinstance(dtc, dict) else getattr(dtc, 'name', '')
                                        dtc_args = dtc.get('args', {}) if isinstance(dtc, dict) else getattr(dtc, 'args', {})
                                        dtc_id = dtc.get('id', '') if isinstance(dtc, dict) else getattr(dtc, 'id', '')
                                        
                                        if dtc_name == 'continue_execution':
                                            decision_made = True
                                            should_continue = True
                                            _write_to_log("\n[OPERATOR] LLM decided to continue execution.\n")
                                            # Add tool message for continue_execution
                                            checkin_tool_messages.append(ToolMessage(
                                                content="CONTINUE_EXECUTION",
                                                tool_call_id=dtc_id
                                            ))
                                            break
                                        elif dtc_name == 'interrupt_execution':
                                            decision_made = True
                                            should_continue = False
                                            interrupt_reason = dtc_args.get('reason', 'No reason provided') if isinstance(dtc_args, dict) else 'No reason provided'
                                            _write_to_log(f"\n[OPERATOR] LLM decided to interrupt execution. Reason: {interrupt_reason}\n")
                                            # Add tool message for interrupt_execution
                                            checkin_tool_messages.append(ToolMessage(
                                                content=f"INTERRUPT_EXECUTION: {interrupt_reason}",
                                                tool_call_id=dtc_id
                                            ))
                                            break
                                        elif dtc_name in checkin_tool_map:
                                            # Execute filesystem tool
                                            _write_to_log(f"\n[OPERATOR] Check-in: Executing {dtc_name}...\n")
                                            send_agent_event("operator", "update", f"Inspecting files ({dtc_name})...")
                                            
                                            try:
                                                tool_func = checkin_tool_map[dtc_name]
                                                tool_result = execute_with_timeout(
                                                    tool_func.invoke, 
                                                    180,  # 3 minute timeout for filesystem tools
                                                    dtc_args if isinstance(dtc_args, dict) else {}
                                                )
                                                checkin_tool_messages.append(ToolMessage(
                                                    content=str(tool_result)[:10000],  # Limit result size
                                                    tool_call_id=dtc_id
                                                ))
                                                _write_to_log(f"\n[OPERATOR] Check-in {dtc_name} result:\n{str(tool_result)[:2000]}\n")
                                            except Exception as tool_err:
                                                error_result = f"Error executing {dtc_name}: {str(tool_err)}"
                                                checkin_tool_messages.append(ToolMessage(
                                                    content=error_result,
                                                    tool_call_id=dtc_id
                                                ))
                                                _write_to_log(f"\n[OPERATOR] Check-in {dtc_name} error: {str(tool_err)}\n")
                                    
                                    # Add tool messages to conversation
                                    if checkin_tool_messages:
                                        checkin_messages = checkin_messages + checkin_tool_messages
                                else:
                                    # No tool calls - LLM responded with text only, prompt again
                                    _write_to_log("\n[OPERATOR] Check-in: LLM responded without tool call, prompting for decision...\n")
                                    reminder_msg = HumanMessage(content="Please call either `continue_execution()` or `interrupt_execution(reason='...')` to submit your decision.")
                                    checkin_messages = checkin_messages + [reminder_msg]
                            
                            # Check if we hit max iterations without decision
                            if not decision_made:
                                _write_to_log(f"\n[OPERATOR] Check-in max iterations ({max_checkin_iterations}) reached, defaulting to continue.\n")
                                should_continue = True
                            
                            if should_continue:
                                send_agent_event("operator", "update", "Continuing execution...")
                                send_agent_event("operator", "update", f"Executing {target_name or 'script'}...")
                                result = resume_execution()
                            else:
                                # Persist the check-in interaction to operator history
                                # Add the check-in prompt as HumanMessage
                                current_task_messages = current_task_messages + [checkin_human_msg]
                                
                                # Add all intermediate messages from check-in (AI responses and tool results)
                                for msg in checkin_messages[len(current_task_messages):]:
                                    current_task_messages = current_task_messages + [msg]
                                
                                # Log the updated messages
                                _write_input_messages(current_task_messages, "OPERATOR", current_task_index)
                                
                                result = interrupt_running_execution()
                                
                        except (StreamingTimeoutError, ValueError) as e:
                            # Default to continue on any error/timeout (including empty response errors)
                            error_msg = str(e)
                            _write_to_log(f"\n[OPERATOR] Check-in decision error: {error_msg}. Defaulting to continue.\n")
                            send_agent_event("operator", "update", f"Check-in error ({error_msg[:50]}...), continuing execution...")
                            send_agent_event("operator", "update", f"Executing {target_name or 'script'}...")
                            result = resume_execution()
                        except Exception as e:
                            # Catch-all for any other exceptions
                            error_msg = str(e)
                            _write_to_log(f"\n[OPERATOR] Unexpected check-in error: {error_msg}. Defaulting to continue.\n")
                            send_agent_event("operator", "update", f"Unexpected error, continuing execution...")
                            send_agent_event("operator", "update", f"Executing {target_name or 'script'}...")
                            result = resume_execution()
                    
                    # Clear pending execution after completion
                    clear_pending_execution()
                    
                    if result and isinstance(result, str):
                        is_error = 'exit code: 1' in result.lower() or ('error' in result.lower() and 'successfully' not in result.lower())
                        if 'executed successfully' in result.lower():
                            is_error = False
                        elif 'executed failed' in result.lower() or 'code executed failed' in result.lower():
                            is_error = True
                        elif 'was interrupted' in result.lower():
                            is_error = False  # Intentional interruption is not an error
                        send_json("code_result", {
                            "output": result,
                            "success": not is_error,
                            "file_path": tool_args.get('file_path', '') if isinstance(tool_args, dict) else ''
                        })
                    
                    log_tool_call(tool_name, target_name, status="completed", agent="operator")
                    
                    if result and isinstance(result, str):
                        log_content = result
                        truncated_log = truncate_content(
                            log_content, 
                            MAX_LOG_CHARS, 
                            "\n\n*... [Output truncated for log brevity]*"
                        )
                        # Wrap content in blockquotes
                        lines = truncated_log.split('\n')
                        blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
                        _write_to_log(f"\n{blockquote}\n\n")
                    
                    _update_operator_status(tool_name, tool_args, is_complete=True, tool_result=result)
                    
                    if isinstance(result, list):
                        tool_messages.append(ToolMessage(content=result, tool_call_id=tool_call_id))
                    else:
                        max_tool_content_chars = 20000
                        truncated_result = result if len(result) <= max_tool_content_chars else (
                            result[:max_tool_content_chars] + "... [truncated]"
                        )
                        tool_messages.append(ToolMessage(content=truncated_result, tool_call_id=tool_call_id))
                
                elif tool_name == 'complete_task' and tool:
                    target_name = extract_target_name(tool_name, tool_args) if tool_args else None
                    log_tool_call(tool_name, target_name, status="started", agent="operator")
                    
                    result = execute_with_timeout(tool.invoke, OTHER_TOOL_TIMEOUT, {})
                    
                    log_tool_call(tool_name, target_name, status="completed", agent="operator")
                    
                    if result and isinstance(result, str):
                        log_content = "\n" + result + "\n"
                        truncated_log = truncate_content(
                            log_content, 
                            MAX_LOG_CHARS, 
                            "\n... [Output truncated for log brevity]\n"
                        )
                        _write_to_log(truncated_log)
                    
                    # Don't update status for complete_task - transitioning to evaluator
                    tool_messages.append(ToolMessage(content=result, tool_call_id=tool_call_id))
                
                # Use shared function for all other tools
                else:
                    logging_tools = [
                        'read_file', 'write_file', 'edit_file', 
                        'delete_file', 'list_directory', 'move_file', 'rename_file', 
                        'analyze_image', 'query_rag', 'search_web', 'fetch_web_page', 'grep_search',
                        'get_hardware_info'
                    ]
                    
                    result, tool_message = execute_tool_with_logging(
                        tool_call=tool_call,
                        tool_map=TOOL_MAP,
                        timeout=OTHER_TOOL_TIMEOUT,
                        agent_name="operator",
                        status_messages=TOOL_STATUS_MESSAGES,
                        on_status_update=on_operator_status_update,
                        log_result=tool_name in logging_tools if logging_tools else True,
                        max_result_chars=MAX_LOG_CHARS
                    )
                    
                    # These tools are skipped in callback - handle step_complete here with tool_result for error detection
                    if tool_name in ('read_file', 'query_rag', 'list_directory', 'search_web', 'fetch_web_page', 'grep_search', 'get_hardware_info'):
                        _update_operator_status(tool_name, tool_args, is_complete=True, tool_result=result)

                    
                    tool_messages.append(tool_message)
            
            # Log incrementally after tools complete to capture progress in case of interruption
            # Note: current_task_messages already includes response
            if tool_messages:
                interim_messages = current_task_messages + tool_messages
                _write_input_messages(interim_messages, "OPERATOR", current_task_index)

        completion_message = None
        if completion_request:
            completion_message = AIMessage(content="DONE")
            send_agent_event("operator", "complete", "")
            log_custom("OPERATOR", "complete_task called, adding DONE message", {
                "completion_request": completion_request,
                "has_completion_message": completion_message is not None
            })

        # Update state
        # Note: current_task_messages already includes response (added before tool execution)
        messages_update = [response] + tool_messages
        if completion_message:
            messages_update.append(completion_message)
        
        # current_task_messages already has response, so only add tool_messages and completion_message
        updated_task_messages = current_task_messages + tool_messages
        if completion_message:
            updated_task_messages = updated_task_messages + [completion_message]
        
        # Log updated messages (including AI response and tool results) to input_messages.md
        _write_input_messages(updated_task_messages, "OPERATOR", current_task_index)
        
        update = {
            "messages": messages_update,
            "current_task_messages": updated_task_messages
        }
        if initial_files is not None:
            update["files_at_task_start"] = initial_files
        return update

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        _write_to_log(f"\n[DEBUG OPERATOR] Exception: {e}\n{error_trace}\n")
        
        if is_api_connection_error(e):
            raise e
            
        if ValidationError and isinstance(e, ValidationError):
            error_message = format_validation_error(e)
        else:
            error_message = f"Error executing step: {str(e)}"
            
        send_agent_event("operator", "error", error_message)
        _write_to_log(f"\n[OPERATOR] Error: {error_message}\n")
        error_msg = AIMessage(content=error_message)
        update = {
            'messages': [error_msg],
            'current_task_messages': current_task_messages + [error_msg]
        }
        if initial_files is not None:
            update["files_at_task_start"] = initial_files
        return update
