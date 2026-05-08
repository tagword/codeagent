"""Tool module: misc_tools"""
import logging
import os
import subprocess
from typing import List

from src.models_pkg import Tool
from src.tools.shell_helpers import _prepare_shell_invocation, _windows_no_window_kwargs

logger = logging.getLogger(__name__)

def echo_tool(message: str) -> str:
    """Echo back what you were told"""
    return message

echo_tool_def = Tool(
    name="echo",
    description="Echo back what you were told",
    parameters={"message": {"type": "string", "required": True, "description": "Message to echo"}},
    returns="string"
)

# Tool 2: calculate

def calculate_tool(operation: str, a: int, b: int) -> int:
    """Perform basic mathematical operations"""
    operations = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else 0
    }
    op = operations.get(operation)
    if op:
        return op(a, b)
    raise ValueError(f"Unknown operation: {operation}")

calc_tool_def = Tool(
    name="calculate",
    description="Perform basic mathematical operations",
    parameters={
        "operation": {"type": "string", "required": True, "description": "Operation: add, subtract, multiply, divide"},
        "a": {"type": "integer", "required": True, "description": "First number"},
        "b": {"type": "integer", "required": True, "description": "Second number"}
    },
    returns="integer: Result of calculation"
)

# Tool 3: counter

def counter_tool(count: int, prefix: str = "Item") -> List[str]:
    """Generate a list of numbered items"""
    return [f"{prefix} {i+1}" for i in range(count)]

counter_tool_def = Tool(
    name="counter",
    description="Generate a list of numbered items",
    parameters={
        "count": {"type": "integer", "required": True, "description": "Number of items to generate"},
        "prefix": {"type": "string", "required": False, "description": "Item prefix", "default": "Item"}
    },
    returns="list[str]: List of item strings"
)

# Tool 4: whoami

def whoami_tool() -> str:
    """Return the current user identity"""
    return os.environ.get('USER', 'unknown')

whoami_tool_def = Tool(
    name="whoami",
    description="Return the current user identity",
    parameters={},
    returns="string: User identity"
)

# Core MVP Tool 5: file_read

def wbs_draft_tool(goal: str, depth: int = 2) -> str:
    """Starter work-breakdown template for planning (expand with the user or LLM)."""
    g = (goal or "").strip()[:500]
    d = max(1, min(int(depth or 2), 5))
    lines = [
        f"# WBS draft: {g or '(no goal)'}",
        "",
        "1. Clarify requirements and success criteria",
        "2. Gather context (code, docs, system)",
        "3. Design minimal approach / risks",
        "4. Implement and verify (tests, manual checks)",
        "5. Summarize, document, next steps",
        "",
        f"_Template depth hint: {d} — subdivide each item as needed._",
    ]
    return "\n".join(lines)

wbs_def = Tool(
    name="wbs_draft",
    description="Propose a starter work breakdown structure for a goal (human/LLM refines)",
    parameters={
        "goal": {"type": "string", "required": True, "description": "High-level goal or task title"},
        "depth": {
            "type": "integer",
            "required": False,
            "description": "Planning depth hint 1–5",
            "default": 2,
        },
    },
    returns="string: markdown outline",
    category="planning",
)


def workspace_verify_handler(command: str = "") -> str:
    """Run a one-shot verify command (tests/lint) in project root; command from arg or env."""
    try:
        from src.config_plane_pkg import project_root as _pr

        root = str(_pr().resolve())
    except Exception:
        root = os.getcwd()
    cmd = (command or "").strip() or os.environ.get("CODEAGENT_WORKSPACE_VERIFY_CMD", "").strip()
    if not cmd:
        pkg = os.path.join(root, "package.json")
        if os.path.isfile(pkg):
            cmd = "npm test"
        else:
            return (
                "No verify command: pass command=..., set CODEAGENT_WORKSPACE_VERIFY_CMD, "
                "or add package.json for default `npm test`."
            )
    try:
        timeout = int(os.environ.get("CODEAGENT_WORKSPACE_VERIFY_TIMEOUT", "300") or 300)
    except Exception:
        timeout = 300
    timeout = max(15, min(timeout, 3600))
    try:
        popen_arg, shell_flag = _prepare_shell_invocation(cmd)
        proc = subprocess.run(
            popen_arg,
            shell=shell_flag,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            **_windows_no_window_kwargs(),
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        bits = [f"exit={proc.returncode}", f"cwd={root}", f"cmd={cmd!r}"]
        body = "\n".join(x for x in (out, err) if x)
        if not body:
            body = "(no output)"
        return "\n".join(bits) + "\n\n" + body[:24000]
    except subprocess.TimeoutExpired:
        return f"Verify timed out after {timeout}s: {cmd!r}"
    except Exception as e:
        return f"Verify error: {e}"

workspace_verify_def = Tool(
    name="workspace_verify",
    description=(
        "Run a non-interactive project check (e.g. tests or lint) in CODEAGENT_PROJECT_ROOT. "
        "Uses ``command`` if provided, else ``CODEAGENT_WORKSPACE_VERIFY_CMD``, else ``npm test`` when package.json exists."
    ),
    parameters={
        "command": {
            "type": "string",
            "required": False,
            "description": "Shell command to run (default: env or npm test)",
        },
    },
    returns="string: exit code, cwd, and combined stdout/stderr (truncated)",
    category="dev",
)

# Core MVP Tool 9: web_fetch

