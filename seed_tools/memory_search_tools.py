"""Memory search tool"""
import json
import logging
import os
from typing import List

from seed_tools.models import Tool

logger = logging.getLogger(__name__)

def memory_search_handler(
    query: str,
    scope: str = "all",
    max_results: int = 12,
) -> str:
    """Search episodic logs and stored LLM transcripts by substring."""

    from seed.agent_context import (
        active_episodic_project_id,
        episodic_project_scope_active,
        get_active_llm_session,
    )
    from seed.llm_sess import (
        list_stored_llm_session_ids,
        load_llm_messages,
        llm_sessions_dir,
        read_stored_session_project_id,
    )
    from seed.mem_bridge import parsed_experience_project_id
    from seed.mem_sys import MemorySystem

    q = (query or "").strip().lower()
    if not q:
        return "Error: empty query"
    scope_l = (scope or "all").strip().lower()
    from codeagent.core.paths import agent_id_default, agent_memory_dir

    aid = agent_id_default()
    base = agent_memory_dir(aid)
    lines: List[str] = []
    cap = max(1, min(int(max_results), 40))
    active = get_active_llm_session()
    scoped = episodic_project_scope_active()
    want_proj = active_episodic_project_id() if scoped else ""

    def _exp_in_scope(text: str) -> bool:
        if not scoped:
            return True
        exp_proj = parsed_experience_project_id(text)
        if want_proj:
            return exp_proj == want_proj
        return exp_proj is None

    def _sid_in_scope(sid: str) -> bool:
        if not scoped:
            return True
        got = read_stored_session_project_id(sid, aid).strip()
        return got == want_proj

    def take(line: str) -> None:
        if len(lines) >= cap:
            return
        lines.append(line)

    if scope_l in ("all", "experiences", "experience"):
        try:
            ms = MemorySystem(base_path=base)
            exp_dir = ms.memory_path / "experiences"
            if exp_dir.is_dir():
                for p in sorted(exp_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
                    if len(lines) >= cap:
                        break
                    try:
                        text = p.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    if os.environ.get("CODEAGENT_MEMORY_SEARCH_INCLUDE_EXPIRED", "").lower() not in (
                        "1",
                        "true",
                        "yes",
                    ):
                        try:
                            from seed.mem_bridge import experience_file_expired

                            if experience_file_expired(p, text):
                                continue
                        except Exception:
                            pass
                    if q not in text.lower():
                        continue
                    if not _exp_in_scope(text):
                        continue
                    snip = text.strip().replace("\n", " ")[:320]
                    take(f"[experience] {p.name}: {snip}")
        except Exception as e:
            take(f"[experience] error listing: {e}")

    if scope_l in ("all", "sessions", "session", "chats"):
        try:
            if scope_l == "session":
                ids = [active] if (active and _sid_in_scope(active)) else []
            else:
                ids = list_stored_llm_session_ids(agent_id=aid)
            for sid in ids:
                if len(lines) >= cap:
                    break
                if not _sid_in_scope(sid):
                    continue
                msgs = load_llm_messages(sid, agent_id=aid)
                if not msgs:
                    continue
                blob = json.dumps(msgs, ensure_ascii=False).lower()
                if q not in blob:
                    continue
                take(f"[llm_session] {sid}: … match in {len(msgs)} messages …")
        except Exception as e:
            take(f"[llm_session] error: {e}")

    if not lines:
        return f"No matches for {query!r} (scope={scope}). Sessions dir: {llm_sessions_dir(aid)}"
    return "\n".join(lines[:cap])

memory_search_def = Tool(
    name="memory_search",
    description=(
        "Search long-term episodic memory (memory/experiences) and saved LLM chat sessions on disk; "
        "use to recall facts across sessions"
    ),
    parameters={
        "query": {"type": "string", "required": True, "description": "Substring to search (case-insensitive)"},
        "scope": {
            "type": "string",
            "required": False,
            "description": "all | experiences | sessions | session (current session transcripts only)",
            "default": "all",
        },
        "max_results": {
            "type": "integer",
            "required": False,
            "description": "Max hit lines",
            "default": 12,
        },
    },
    returns="string: newline-separated hits",
    category="memory",
)

