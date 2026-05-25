"""Tests for modular prompt assembly."""

from langchain_core.messages import HumanMessage, SystemMessage

from src.prompting import (
    PROMPT_PROFILE,
    PROMPT_VERSION,
    build_checkin_control_reminder_injection,
    build_checkin_empty_response_injection,
    build_checkin_history_message,
    build_checkin_prompt_injection,
    build_evaluation_feedback_injection,
    build_evaluator_messages,
    build_evaluator_repeated_tool_warning_injection,
    build_hardware_change_injection,
    build_operator_messages,
    build_operator_repeated_tool_warning_injection,
    build_resume_steering_injection,
    build_strategist_review_prompt,
    build_strategist_messages,
    build_strategist_repeated_tool_warning_injection,
    build_summarized_checkin_reminder_injection,
    clear_prompt_runtime_events_for_task,
    initial_prompt_metadata,
    prompt_identity_from_state,
    prompt_metadata_update,
    rehydrate_prompt_runtime_events,
    upsert_prompt_runtime_event,
)
from src.prompting.registry import PromptContext, PromptSectionSpec, PromptSelector
from src.prompting.types import append_injection


def test_strategist_builder_preserves_plan_contract_and_files_note():
    assembly = build_strategist_messages(
        user_input="Study methane adsorption",
        granularity_level="medium",
        accuracy_mode="standard",
        gpu_info="No GPU detected",
        archived_context=None,
        is_replanning=False,
        has_user_files=True,
    )

    assert isinstance(assembly.messages[0], SystemMessage)
    assert isinstance(assembly.messages[1], HumanMessage)
    system = assembly.messages[0].content
    assert "# Role: QUASAR Strategist Agent" in system
    assert "Strategist agent in QUASAR" in system
    assert "The user has uploaded several files" in system
    assert "<PLAN>" in system
    assert "**Assigned Accuracy Mode:** standard" in system
    assert "**Assigned Granularity Level:** medium" in system
    assert assembly.messages[1].content == "Study methane adsorption"
    assert [section.id for section in assembly.sections] == [
        "strategist.standard_role",
        "strategist.common",
        "strategist.user_request",
    ]
    assert assembly.phase == "initial"
    assert assembly.render_order == [
        "strategist.standard_role",
        "strategist.common",
        "strategist.user_request",
    ]
    assert assembly.skipped_sections[0]["id"] == "strategist.replanning_role"


def test_strategist_replanning_builder_includes_archived_context():
    assembly = build_strategist_messages(
        user_input="Improve prior run",
        granularity_level="high",
        accuracy_mode="pro",
        gpu_info="A100",
        archived_context="### Archived Run 1\nOld summary",
        is_replanning=True,
        has_user_files=False,
    )

    system = assembly.messages[0].content
    assert "# QUASAR Strategist Agent — Replanning Mode" in system
    assert "Strategist agent in QUASAR" in system
    assert "### Archived Run 1" in system
    assert "Archive Investigation Protocol" in system
    assert "Previous Run Review" in system
    assert "do not rely only on the provided context or generated summaries" in system
    assert "strict sequential gate" in system
    assert "**Assigned Accuracy Mode:** pro" in system


def test_strategist_replanning_builder_uses_replanning_role_without_summary_context():
    assembly = build_strategist_messages(
        user_input="Improve prior run",
        granularity_level="medium",
        accuracy_mode="standard",
        gpu_info="No GPU detected",
        archived_context=None,
        is_replanning=True,
        has_user_files=False,
    )

    system = assembly.messages[0].content
    assert "# QUASAR Strategist Agent — Replanning Mode" in system
    assert "No pre-rendered archive summary was available" in system
    assert "Archive Investigation Protocol" in system
    assert [section.id for section in assembly.sections] == [
        "strategist.replanning_role",
        "strategist.common",
        "strategist.user_request",
    ]


def test_operator_builder_preserves_rag_and_accuracy_variants():
    rag_on = build_operator_messages(
        project_request="Request",
        formatted_history="Task 1 done",
        current_task="### **Task 2:** Run QE",
        is_last_step=True,
        pmg_mapi_available="; `Materials Project API` (env: PMG_MAPI_KEY); ",
        rag_enabled=True,
        accuracy_mode="adaptive",
    )
    rag_off = build_operator_messages(
        project_request="Request",
        formatted_history="Task 1 done",
        current_task="### **Task 2:** Run QE",
        is_last_step=False,
        pmg_mapi_available=".",
        rag_enabled=False,
        accuracy_mode="eco",
    )

    assert "→ query_rag" in rag_on.messages[0].content
    assert "Operator agent in QUASAR" in rag_on.messages[0].content
    assert "→ query_rag" not in rag_off.messages[0].content
    assert "Every `execute_python` call MUST include `check_in_after=<minutes>`" in rag_on.messages[0].content
    assert "**Assigned Accuracy Mode:** adaptive" in rag_on.messages[0].content
    assert "## Project Request\nRequest" in rag_on.messages[1].content
    assert "## Project Request" not in rag_off.messages[1].content
    assert "### **Task 2:** Run QE" in rag_on.messages[1].content


def test_evaluator_builder_preserves_decision_contract():
    assembly = build_evaluator_messages(
        project_context="## Project Request\nDo work\n",
        current_task="Task 1: Validate outputs",
        current_task_index=0,
        total_tasks=2,
        operator_history="Operator: ran calculation",
    )

    assert "submit_evaluation" in assembly.messages[0].content
    assert "Evaluator agent in QUASAR" in assembly.messages[0].content
    assert "### Current Task (Task 1 of 2)" in assembly.messages[1].content
    assert "<operator_history>" in assembly.messages[1].content
    assert "Operator: ran calculation" in assembly.messages[1].content


def test_strategist_review_builder_preserves_raw_review_text():
    self_review = build_strategist_review_prompt()
    revision = build_strategist_review_prompt(feedback="Add a convergence task")

    assert len(self_review.messages) == 1
    assert "Please review your plan above" in self_review.messages[0].content
    assert self_review.sections[0].id == "strategist.review.self_review"
    assert self_review.phase == "review"
    assert "User feedback:\nAdd a convergence task" in revision.messages[0].content
    assert revision.sections[0].id == "strategist.review.user_revision"


def test_runtime_injections_preserve_existing_markers_and_dedupe():
    steering = build_resume_steering_injection("Use a 15 minute cadence.")
    messages, appended = append_injection([], steering)
    messages, appended_again = append_injection(messages, steering)

    assert appended is True
    assert appended_again is False
    assert messages[0].additional_kwargs["quasar_prompt_event"]["id"] == "operator.resume_steering"
    assert messages[0].additional_kwargs["quasar_prompt_event"]["scope"] == "task"
    assert "[USER STEERING WHILE RESUMING]" in messages[0].content
    assert "15 minute cadence" in messages[0].content

    feedback = build_evaluation_feedback_injection(
        current_task_index=0,
        retry_num=1,
        max_retries=3,
        summary="Missing summary.md",
    )
    assert feedback.content.startswith("EVALUATION_FEEDBACK:")
    assert "attempt 1/4" in feedback.content
    assert "DONE only" in feedback.content


def test_warning_injections_preserve_agent_specific_text():
    strategist = build_strategist_repeated_tool_warning_injection("read_file", 3)
    operator = build_operator_repeated_tool_warning_injection("read_file", 3)
    evaluator = build_evaluator_repeated_tool_warning_injection("read_file", 3)

    assert "generate the final plan" in strategist.content
    assert "complete_task" in operator.content
    assert "submit your evaluation decision" in evaluator.content
    assert "MUST stops" in operator.content
    assert "MUST stops" in evaluator.content


def test_checkin_injections_and_history_message_preserve_contract():
    prompt = build_checkin_prompt_injection(
        script_name="run.py",
        elapsed_display="5 minutes",
    )
    assert "The Python script `run.py` has been running for 5 minutes." in prompt.content
    assert "execute_temporary_python" in prompt.content
    assert "next_check_in_after=<minutes>" in prompt.content

    assert "Continue this execution check-in" in build_summarized_checkin_reminder_injection().content
    assert "Your check-in response was empty" in build_checkin_empty_response_injection().content
    assert "Please call either `continue_execution" in build_checkin_control_reminder_injection().content

    history = build_checkin_history_message(
        "run.py",
        "10 minutes",
        decision="continue_execution",
        summary="Healthy",
        next_check_in_after=15,
    )
    assert history.content == (
        "[EXECUTION CHECK-IN SUMMARY]\n"
        "Script: `run.py`\n"
        "Elapsed: 10 minutes\n"
        "Decision: continue_execution\n"
        "Next check-in: 15 minutes\n"
        "Summary: Healthy"
    )


def test_hardware_injection_and_prompt_metadata_update():
    injection = build_hardware_change_injection(
        {"cpu_model": "EPYC", "cpu_cores": 64, "gpu_info": "A100"},
        "- CPU: Xeon\n- Physical cores: 32\n- GPU: none",
    )
    assert "Hardware configuration has changed" in injection.content
    assert "EPYC" in injection.content
    assert "Xeon" in injection.content

    assert initial_prompt_metadata() == {
        "profile": PROMPT_PROFILE,
        "version": PROMPT_VERSION,
        "agents": {},
    }
    assert prompt_identity_from_state({}) == (PROMPT_PROFILE, PROMPT_VERSION)

    assembly = build_evaluator_messages(
        project_context="Project",
        current_task="Task",
        current_task_index=0,
        total_tasks=1,
        operator_history="History",
    )
    update = prompt_metadata_update({}, assembly)
    assert update["prompt_profile"] == PROMPT_PROFILE
    assert update["prompt_version"] == PROMPT_VERSION
    assert "evaluator" in update["prompt_metadata"]["agents"]
    evaluator_meta = update["prompt_metadata"]["agents"]["evaluator"]
    assert evaluator_meta["message_hash"]
    assert evaluator_meta["assembly_id"]
    assert evaluator_meta["render_order"] == ["evaluator.system", "evaluator.context"]
    assert evaluator_meta["selected_sections"][0]["cache_policy"] == "session"


def test_prompt_selector_orders_sections_and_records_skips():
    selector = PromptSelector()
    context = PromptContext(agent="operator", phase="task", rag_enabled=True)
    selection = selector.select(context, [
        PromptSectionSpec(
            id="operator.second",
            agent="operator",
            layer="context",
            stability="task",
            priority=20,
            cache_policy="task",
            render=lambda _context: "second",
        ),
        PromptSectionSpec(
            id="operator.first",
            agent="operator",
            layer="system",
            stability="session",
            priority=10,
            cache_policy="session",
            render=lambda _context: "first",
        ),
        PromptSectionSpec(
            id="operator.skipped",
            agent="operator",
            layer="context",
            stability="runtime",
            priority=30,
            cache_policy="runtime",
            render=lambda _context: "skip",
            include=lambda _context: False,
        ),
    ])

    assert [section.id for section in selection.sections] == ["operator.first", "operator.second"]
    assert selection.selected[0]["reason"] == "selected"
    assert selection.selected[0]["cache_policy"] == "session"
    assert selection.skipped == [
        {
            "id": "operator.skipped",
            "agent": "operator",
            "layer": "context",
            "stability": "runtime",
            "priority": 30,
            "cache_policy": "runtime",
            "dependencies": [],
            "reason": "include_predicate_false",
        }
    ]


def test_prompt_runtime_events_rehydrate_and_clear_by_scope():
    steering = build_resume_steering_injection("Use smaller batches.")
    events = upsert_prompt_runtime_event([], steering, task_index=2)
    summarized_messages = [SystemMessage(content="System"), HumanMessage(content="[CONTEXT SUMMARY]")]

    rehydrated, count = rehydrate_prompt_runtime_events(
        summarized_messages,
        events,
        agent="operator",
        task_index=2,
    )

    assert count == 1
    assert "Use smaller batches" in rehydrated[-1].content
    assert rehydrated[-1].additional_kwargs["quasar_prompt_event"]["scope"] == "task"

    rehydrated_again, count_again = rehydrate_prompt_runtime_events(
        rehydrated,
        events,
        agent="operator",
        task_index=2,
    )
    assert count_again == 0
    assert rehydrated_again == rehydrated
    assert clear_prompt_runtime_events_for_task(events, task_index=2) == []
