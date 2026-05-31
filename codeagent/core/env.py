"""Code Agent product environment variables (``CODEAGENT_*`` only)."""

from __future__ import annotations

import os
from pathlib import Path

# --- Product data root (Code Agent home, not Seed generic ``~/.seed``) ---

HOME = "CODEAGENT_HOME"
PROJECT_ROOT = "CODEAGENT_PROJECT_ROOT"

# --- Product keys (not read by Seed) ---

AGENT_ID = "CODEAGENT_AGENT_ID"
LOG_LEVEL = "CODEAGENT_LOG_LEVEL"
SKILLS_AUTO = "CODEAGENT_SKILLS_AUTO"
SKILLS_TOP_K = "CODEAGENT_SKILLS_TOP_K"
DIARY = "CODEAGENT_DIARY"
DIARY_KEEP_DAYS = "CODEAGENT_DIARY_KEEP_DAYS"
CHAT_USER_ROUNDS = "CODEAGENT_CHAT_USER_ROUNDS"
MAX_TOOL_ROUNDS = "CODEAGENT_MAX_TOOL_ROUNDS"
CHAT_AUTO_CONTINUE_ON_LIMIT = "CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT"
CHAT_AUTO_CONTINUE_MAX_SEGMENTS = "CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS"
CHAT_MAX_TOOL_ROUNDS_DEFAULT = "CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT"
CONTEXT_COMPACT = "CODEAGENT_CONTEXT_COMPACT"
CONTEXT_COMPACT_MIN_BYTES = "CODEAGENT_CONTEXT_COMPACT_MIN_BYTES"
CONTEXT_COMPACT_MIN_ROUNDS = "CODEAGENT_CONTEXT_COMPACT_MIN_ROUNDS"
CONTEXT_COMPACT_SUMMARIZER_BASEURL = "CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL"
CONTEXT_COMPACT_SUMMARIZER_MODEL = "CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MODEL"
WEBUI_SESSION_HISTORY_MAX_CHARS = "CODEAGENT_WEBUI_SESSION_HISTORY_MAX_CHARS"
WEBUI_SESSION_HISTORY_USER_BLOCKS = "CODEAGENT_WEBUI_SESSION_HISTORY_USER_BLOCKS"
WEBUI_SESSION_HISTORY_MAX_MESSAGES = "CODEAGENT_WEBUI_SESSION_HISTORY_MAX_MESSAGES"
WEBUI_SESSION_HISTORY_REASONING_MAX_CHARS = "CODEAGENT_WEBUI_SESSION_HISTORY_REASONING_MAX_CHARS"
WEBUI_TOKEN = "CODEAGENT_WEBUI_TOKEN"
SKIP_FOLDER_PICKER = "CODEAGENT_SKIP_FOLDER_PICKER"
AGENT_TOOLS_NO_CACHE = "CODEAGENT_AGENT_TOOLS_NO_CACHE"
AGENT_TOOLS_MODE = "CODEAGENT_AGENT_TOOLS_MODE"
ORCHESTRATOR_AUTO_SPLIT = "CODEAGENT_ORCHESTRATOR_AUTO_SPLIT"


def pick_default(default: str, key: str) -> str:
    if key in os.environ:
        return os.environ[key]
    return default


def pick_nonempty(key: str) -> str:
    raw = os.environ.get(key)
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return ""


def pick_int(default: int, key: str) -> int:
    raw = pick_default(str(default), key).strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default




def env_truthy(key: str, default: str = "0") -> bool:
    val = pick_default(default, key).strip().lower()
    return val in ("1", "true", "yes", "on")


def env_falsy(key: str, default: str = "1") -> bool:
    val = pick_default(default, key).strip().lower()
    return val in ("0", "false", "no", "off")


def default_agent_id() -> str:
    return pick_default("default", AGENT_ID).strip() or "default"


def product_home() -> Path:
    """Default ``~/.codeagent``; override with ``CODEAGENT_HOME`` or ``CODEAGENT_PROJECT_ROOT``."""
    raw = pick_nonempty(PROJECT_ROOT) or pick_nonempty(HOME)
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".codeagent").resolve()


def apply_default_product_home() -> Path:
    """
    Ensure product home exists and set ``SEED_PROJECT_ROOT`` for the Seed kernel.

    Other products (e.g. designagent) should use their own ``~/.<product>`` and set
    ``SEED_PROJECT_ROOT`` the same way in their bootstrap.
    """
    home = product_home()
    os.environ.setdefault(HOME, str(home))
    if "SEED_PROJECT_ROOT" not in os.environ:
        os.environ["SEED_PROJECT_ROOT"] = str(home)
    home.mkdir(parents=True, exist_ok=True)
    (home / "config").mkdir(parents=True, exist_ok=True)
    return home
