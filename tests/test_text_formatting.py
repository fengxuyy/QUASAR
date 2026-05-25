from src.agents.utils.text import format_history


def test_format_history_uses_markdown_task_summary_titles():
    output = format_history(
        {0: "Relaxation converged and produced final coordinates."},
        ["Task 1: Relax structure"],
    )

    assert "### **Task 1: Relax structure**" in output
    assert "Task 1: Task 1:" not in output
    assert "Relaxation converged" in output


def test_format_history_handles_missing_task_description():
    output = format_history({0: "Summary only."}, [""])

    assert "### **Task 1**" in output
    assert "Summary only." in output
