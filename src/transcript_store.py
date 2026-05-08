"""Append-only full transcript (JSONL) under ``llm_sessions/_transcript/``.

Separate from the API projection: ``Session.messages`` keeps the full chain;
trim/compact apply only to a deep-copied list sent to the LLM.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.llm_sess_pkg import _safe_session_filename, llm_sessions_dir


def transcript_jsonl_path(session_id: str, agent_id: Optional[str] = None) -> Path:
    base = llm_sessions_dir(agent_id)
    d = base / "_transcript"
    d.mkdir(parents=True, exist_ok=True)
    slug = _safe_session_filename(session_id)
    return d / f"{slug}.jsonl"


def append_transcript_entries(
    session_id: str,
    entries: List[Dict[str, Any]],
    *,
    agent_id: Optional[str] = None,
) -> None:
    """Append each message dict as one JSON line (best-effort)."""
    if os.environ.get("CODEAGENT_TRANSCRIPT", "1").lower() in ("0", "false", "no"):
        return
    if not entries:
        return
    p = transcript_jsonl_path(session_id, agent_id)
    try:
        with open(p, "a", encoding="utf-8") as f:
            for m in entries:
                if not isinstance(m, dict):
                    continue
                f.write(json.dumps(m, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass
