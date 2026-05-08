"""Tool module: artifact_tools"""
import logging
import os
from typing import List, Tuple

from src.models_pkg import Tool
from src.tools.shell_helpers import _active_agent_and_session

logger = logging.getLogger(__name__)

def artifact_read_handler(
    path: str,
    start_line: int = 1,
    end_line: int = 0,
    pattern: str = "",
    context: int = 2,
    max_chars: int = 12000,
) -> str:
    """
    Read an artifact file (typically under llm_sessions/_artifacts/...) with either:
    - line range [start_line, end_line] (1-indexed; end_line<=0 means until EOF)
    - OR grep-like pattern matches with +/- context lines.
    """
    try:
        p = (path or "").strip()
        if not p:
            return "Error: path is required"
        if not os.path.exists(p):
            return f"Error: File not found: {p}"

        # Best-effort safety: when the path is absolute, require it under the current agent's llm_sessions_dir.
        try:
            from src.llm_sess_pkg import llm_sessions_dir

            agent_id, _sid = _active_agent_and_session()
            base = os.path.abspath(str(llm_sessions_dir(agent_id)))
            ap = os.path.abspath(p)
            if not ap.startswith(base):
                return f"Error: Refuse to read outside sessions dir: {ap}"
        except Exception:
            pass

        max_chars = int(max_chars or 12000)
        max_chars = max(500, min(max_chars, 200_000))
        ctx = int(context or 0)
        ctx = max(0, min(ctx, 50))
        start = int(start_line or 1)
        end = int(end_line or 0)
        if start < 1:
            start = 1

        needle = (pattern or "").strip()
        if needle:
            # Grep mode (simple substring match, case sensitive).
            hits: List[str] = []
            buf: List[Tuple[int, str]] = []
            buf_cap = ctx * 2 + 1
            after = 0
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for ln, line in enumerate(f, start=1):
                    # Maintain ring buffer for before-context.
                    buf.append((ln, line.rstrip("\n")))
                    if len(buf) > max(1, buf_cap):
                        buf.pop(0)
                    if after > 0:
                        hits.append(f"{ln}|{line.rstrip()}")
                        after -= 1
                        continue
                    if needle in line:
                        # Emit before-context (excluding current line if duplicated later).
                        before = buf[:-1][-ctx:] if ctx > 0 else []
                        if before:
                            hits.append("...[match context]...")
                            for b_ln, b_line in before:
                                hits.append(f"{b_ln}|{b_line}")
                        hits.append(f"{ln}|{line.rstrip()}")
                        after = ctx
            out = "\n".join(hits).strip() or "(no matches)"
            if len(out) > max_chars:
                out = out[: max_chars - 24] + "\n…[内容已截断]"
            return out

        # Range mode
        out_lines: List[str] = []
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for ln, line in enumerate(f, start=1):
                if ln < start:
                    continue
                if end > 0 and ln > end:
                    break
                out_lines.append(f"{ln}|{line.rstrip()}")
                if sum(len(x) + 1 for x in out_lines) > max_chars:
                    out_lines.append("…[内容已截断]")
                    break
        return "\n".join(out_lines).strip() or "(empty)"
    except Exception as e:
        return f"Error reading artifact: {e}"

artifact_read_def = Tool(
    name="artifact_read",
    description="Read a saved artifact file from llm_sessions/_artifacts with line range or pattern match.",
    parameters={
        "path": {"type": "string", "required": True, "description": "Absolute artifact file path (typically under llm_sessions/_artifacts/...)"},
        "start_line": {"type": "integer", "required": False, "description": "1-indexed start line (default: 1)"},
        "end_line": {"type": "integer", "required": False, "description": "1-indexed end line; <=0 means until EOF"},
        "pattern": {"type": "string", "required": False, "description": "If set, run substring match and return hits with context"},
        "context": {"type": "integer", "required": False, "description": "Context lines before/after each match (default: 2)"},
        "max_chars": {"type": "integer", "required": False, "description": "Maximum returned characters (default: 12000)"},
    },
    returns="string: Selected lines or match contexts",
)

# Core MVP Tool 6: file_write

