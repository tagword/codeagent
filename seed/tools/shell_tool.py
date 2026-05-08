"""Bash tool wrapper"""
import logging
import subprocess
from typing import Optional

from seed.models import Tool
from seed.tools.shell_helpers import _windows_no_window_kwargs

logger = logging.getLogger(__name__)


def bash_tool_handler(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """Execute a shell command with safety checks"""
    from seed.safety import check_bash_command, enforce_bash_timeout

    # Enhanced safety: regex-based pattern matching (before try to avoid var scope issues)
    err = check_bash_command(command, cwd=cwd)
    if err is not None:
        return err

    # Safe timeout clamping
    safe_timeout = enforce_bash_timeout(timeout)

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=safe_timeout, cwd=cwd,
            **_windows_no_window_kwargs(),
        )

        output = result.stdout + result.stderr
        if result.returncode == 0:
            return output
        return f"Command failed with exit code {result.returncode}:\n{output}"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {safe_timeout} seconds"
    except Exception as e:
        return f"Error executing command: {e}"

bash_def = Tool(
    name="bash_tool",
    description="Execute shell commands with safety checks",
    parameters={
        "command": {"type": "string", "required": True, "description": "Shell command to execute"},
        "timeout": {"type": "integer", "required": False, "description": "Timeout in seconds", "default": 30},
        "cwd": {"type": "string", "required": False, "description": "Working directory"}
    },
    returns="string: Command output or error message"
)

