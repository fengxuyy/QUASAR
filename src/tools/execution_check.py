"""
Execution check tools for LLM to decide whether to continue or interrupt running Python executions.
"""

import ast
import re
from typing import Optional

from langchain_core.tools import tool

from .execution import execute_python_with_state_preserved


CHECKIN_TEMP_TIMEOUT_MINUTES = 5.0
# open() mode strings in the stdlib use only these characters (before encodings like 'latin-1').
_OPEN_MODE_CHARS_ONLY = re.compile(r"^[rwxabtU+]+$", re.IGNORECASE)

_OPEN_POSITIONAL_MODE_RE = re.compile(r"\bopen\s*\([^)]*,\s*(['\"])([^'\"]*)\1")
_OPEN_KEYWORD_MODE_RE = re.compile(r"\bopen\s*\([^)]*\bmode\s*=\s*(['\"])([^'\"]*)\1")
_PATH_OPEN_POSITIONAL_RE = re.compile(r"\.open\s*\(\s*(['\"])([^'\"]*)\1")
_PATH_OPEN_KEYWORD_RE = re.compile(r"\.open\s*\([^)]*\bmode\s*=\s*(['\"])([^'\"]*)\1")
_PATHLIB_CONSTRUCTOR_ATTRS = {"Path", "PosixPath", "WindowsPath"}
_PATHLIKE_RETURNING_METHODS = {"absolute", "expanduser", "home", "joinpath", "resolve", "with_name", "with_suffix"}
_PATHLIKE_RETURNING_PROPERTIES = {"parent"}
_GENERIC_PATH_MUTATION_METHODS = {
    "write_text",
    "write_bytes",
    "unlink",
    "mkdir",
    "touch",
    "chmod",
    "rmdir",
    "symlink_to",
    "hardlink_to",
}
_PATH_MUTATION_METHODS_WITH_COMMON_FALSE_POSITIVES = {"rename", "replace"}


def _open_mode_alters_file(mode: str) -> bool:
    """True iff a stdlib-style mode string opens for write/append/create or update (contains +)."""
    if not mode or not _OPEN_MODE_CHARS_ONLY.fullmatch(mode):
        return False
    if "+" in mode:
        return True
    return bool(mode) and mode[0].lower() in ("w", "a", "x")


def _iter_suspected_write_open_modes(code: str):
    for rx in (
        _OPEN_POSITIONAL_MODE_RE,
        _OPEN_KEYWORD_MODE_RE,
        _PATH_OPEN_POSITIONAL_RE,
        _PATH_OPEN_KEYWORD_RE,
    ):
        for m in rx.finditer(code):
            yield m.group(2)


class _PathMutationVisitor(ast.NodeVisitor):
    """Detect pathlib rename/replace calls without flagging common non-filesystem methods."""

    def __init__(self):
        self.path_constructor_names = set()
        self.pathlib_module_aliases = set()
        self.path_like_names = set()
        self.found_mutation = False

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name == "pathlib":
                self.pathlib_module_aliases.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module != "pathlib":
            return
        for alias in node.names:
            if alias.name in _PATHLIB_CONSTRUCTOR_ATTRS:
                self.path_constructor_names.add(alias.asname or alias.name)

    def visit_Assign(self, node: ast.Assign):
        self.visit(node.value)
        is_path_like = self._expr_is_path_like(node.value)
        for target in node.targets:
            self._set_path_like_binding(target, is_path_like)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.value is None:
            return
        self.visit(node.value)
        self._set_path_like_binding(node.target, self._expr_is_path_like(node.value))

    def visit_AugAssign(self, node: ast.AugAssign):
        self.visit(node.value)
        self._set_path_like_binding(node.target, False)

    def visit_Call(self, node: ast.Call):
        if self.found_mutation:
            return

        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _PATH_MUTATION_METHODS_WITH_COMMON_FALSE_POSITIVES
            and self._expr_is_path_like(func.value)
        ):
            self.found_mutation = True
            return

        self.generic_visit(node)

    def _set_path_like_binding(self, target: ast.expr, is_path_like: bool):
        if isinstance(target, ast.Name):
            if is_path_like:
                self.path_like_names.add(target.id)
            else:
                self.path_like_names.discard(target.id)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._set_path_like_binding(elt, is_path_like)

    def _expr_is_path_like(self, expr: ast.AST) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in self.path_like_names

        if isinstance(expr, ast.Call):
            if self._is_path_constructor_call(expr):
                return True
            if isinstance(expr.func, ast.Attribute):
                if (
                    expr.func.attr in _PATHLIKE_RETURNING_METHODS
                    and self._expr_is_path_like(expr.func.value)
                ):
                    return True
                if (
                    expr.func.attr in {"cwd", "home"}
                    and self._is_path_constructor_reference(expr.func.value)
                ):
                    return True
            return False

        if isinstance(expr, ast.Attribute):
            return (
                expr.attr in _PATHLIKE_RETURNING_PROPERTIES
                and self._expr_is_path_like(expr.value)
            )

        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
            return self._expr_is_path_like(expr.left)

        return False

    def _is_path_constructor_call(self, call: ast.Call) -> bool:
        return self._is_path_constructor_reference(call.func)

    def _is_path_constructor_reference(self, expr: ast.AST) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in self.path_constructor_names
        return (
            isinstance(expr, ast.Attribute)
            and isinstance(expr.value, ast.Name)
            and expr.value.id in self.pathlib_module_aliases
            and expr.attr in _PATHLIB_CONSTRUCTOR_ATTRS
        )


def _uses_forbidden_path_mutation_helper(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    visitor = _PathMutationVisitor()
    visitor.visit(tree)
    return visitor.found_mutation


FORBIDDEN_TEMP_PYTHON_PATTERNS = (
    (r"\bimport\s+subprocess\b|\bfrom\s+subprocess\b", "the subprocess module"),
    (r"\b(?:__import__|importlib\.import_module)\s*\(\s*['\"]subprocess['\"]\s*\)", "the subprocess module"),
    (r"\bos\.system\s*\(", "os.system"),
    (r"\bos\.popen\s*\(", "os.popen"),
    (r"\bimport\s+multiprocessing\b|\bfrom\s+multiprocessing\b", "multiprocessing"),
    (r"\b(?:__import__|importlib\.import_module)\s*\(\s*['\"]multiprocessing['\"]\s*\)", "multiprocessing"),
    (r"\basyncio\.create_subprocess(?:_exec|_shell)?\b", "asyncio subprocess helpers"),
    (rf"\.(?:{'|'.join(sorted(_GENERIC_PATH_MUTATION_METHODS))})\s*\(", "filesystem mutation helpers"),
    (r"\bos\.(?:remove|unlink|rename|replace|mkdir|makedirs|rmdir|removedirs|chmod)\s*\(", "os filesystem mutation helpers"),
    (r"\bshutil\.(?:rmtree|move|copy|copy2|copytree)\s*\(", "shutil filesystem mutation helpers"),
)


@tool
def continue_execution(summary: str = "") -> str:
    """Continue the currently running Python execution.
    
    Call this when the execution should continue running for another check-in interval.
    The script will continue running and you will be prompted again after the next interval.

    Args:
        summary: Brief summary of the current execution stage and why it is safe to continue.
    
    Returns:
        Confirmation message that execution will continue.
    """
    return "CONTINUE_EXECUTION"


@tool
def execute_temporary_python(
    code: str,
    file_path: str = "",
    timeout: Optional[float] = None,
) -> str:
    """Execute a short-lived temporary Python snippet during a check-in.

    Use this only to parse existing result files and determine simulation status.
    Do not launch subprocesses, start new simulations, or make long-running changes.
    This always runs with a fixed 5-minute timeout.

    Args:
        code: Temporary Python code that reads/parses existing outputs.
        file_path: Not allowed for this tool. Temporary check-in parsing must use inline code only.
        timeout: Not allowed for this tool. The timeout is fixed at 5 minutes.

    Returns:
        Execution results including stdout, stderr, and exit code.
    """
    if not code or not code.strip():
        return "Error: 'code' must be provided."
    if file_path:
        return (
            "Error: 'file_path' is not supported for execute_temporary_python. "
            "Use inline code only so check-in parsing remains temporary."
        )
    if timeout is not None:
        return (
            "Error: 'timeout' is fixed for execute_temporary_python. "
            "Do not override it; this tool always uses a 5-minute timeout."
        )

    for pattern, label in FORBIDDEN_TEMP_PYTHON_PATTERNS:
        if re.search(pattern, code):
            return (
                f"Error: Temporary check-in Python cannot use {label}. "
                "Use it only to parse existing results and determine simulation status without modifying files or the system."
            )

    if _uses_forbidden_path_mutation_helper(code):
        return (
            "Error: Temporary check-in Python cannot use filesystem mutation helpers. "
            "Use it only to parse existing results and determine simulation status without modifying files or the system."
        )

    for mode in _iter_suspected_write_open_modes(code):
        if _open_mode_alters_file(mode):
            return (
                "Error: Temporary check-in Python cannot use file writes via open(...). "
                "Reading existing files with open(..., 'r') or similar read-only modes is allowed; "
                "do not open files for writing, appending, exclusive creation, or read/write (+)."
            )

    return execute_python_with_state_preserved(
        timeout=CHECKIN_TEMP_TIMEOUT_MINUTES,
        code=code,
    )


@tool
def interrupt_execution(reason: str) -> str:
    """Interrupt and terminate the currently running Python execution.
    
    Call this when the execution should be stopped. The process will be terminated
    and any partial output will be returned.
    
    # Use this when:
    # - Anomalies are detected: For example, calculations not converging, unphysical values, important warnings, or errors that undermine the goals of the current simulation.
    # - Resource health issues occur: If you observe the system is idle, unresponsive, or exhibiting sustained low CPU/GPU utilization (which may indicate the process is stuck or has stalled), interrupt the execution.
    
    Args:
        reason: A clear explanation of why the execution is being interrupted.
                This will be recorded in the execution history.
    
    Returns:
        Confirmation message that execution will be interrupted, including the reason.
    """
    return f"INTERRUPT_EXECUTION: {reason}"
