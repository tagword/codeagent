"""Code analyze tools"""
import logging

from seed_tools.models import Tool
from seed_tools.code_check_tool import code_check_tool

logger = logging.getLogger(__name__)


def code_analyze_handler(code: str = "", filepath: str = "", language: str = "python", focus: str = "issues") -> str:
    """Analyze code (legacy wrapper around code_check)"""
    return code_check_tool(code=code, filepath=filepath, language=language, fix=(focus == "fix"))


def code_check_handler(code: str = "", filepath: str = "", language: str = "auto", fix: bool = False) -> str:
    """Run ruff (if installed), stdlib syntax check, and built-in heuristics."""
    return code_check_tool(code=code, filepath=filepath, language=language, fix=fix)


code_check_def = Tool(
    name="code_check",
    description=(
        "Check code for issues: Python uses ruff when available (else syntax compile + built-in rules); "
        "JS/TS uses eslint when available. Install linters: pip install ruff / pip install -e '.[lint]'."
    ),
    parameters={
        "code": {"type": "string", "required": False, "description": "Code string to check"},
        "filepath": {
            "type": "string",
            "required": False,
            "description": "Path to file; language inferred from extension when language=auto",
        },
        "language": {
            "type": "string",
            "required": False,
            "description": "Language or 'auto' (default: auto)",
        },
        "fix": {
            "type": "boolean",
            "required": False,
            "description": "Auto-fix with ruff/eslint when supported (requires linter installed)",
        },
    },
    returns="string: Structured report",
    category="code",
)

code_analyze_def = Tool(
    name="code_analyze",
    description="[Legacy] Analyze code for issues. Consider using 'code_check' instead for richer results.",
    parameters={
        "code": {"type": "string", "required": False, "description": "Code to analyze"},
        "filepath": {"type": "string", "required": False, "description": "Path to file to analyze"},
        "language": {"type": "string", "required": False, "description": "Programming language (default: python)"},
        "focus": {"type": "string", "required": False, "description": "'issues', 'suggestions', 'explain', or 'fix' (default: issues)"}
    },
    returns="string: Analysis results"
)

# Claw-code Tool 1: GlobTool - File pattern matching
