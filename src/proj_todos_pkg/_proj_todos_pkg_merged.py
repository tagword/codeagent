"""Project-scoped todo items, split by session.

Storage layout:
  agents/<agent_id>/projects/todos/<project_id>/
    session_<session_id_1>.json   -- one file per session
    session_<session_id_2>.json
    ...

Legacy single-file format (todos/<project_id>.json) is read on fallback
but never written; first write migrates to per-session files.
"""
from __future__ import annotations
from __future__ import annotations


import json
from pathlib import Path

from src.codeagent.core.paths import agent_projects_registry_dir


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _todos_dir(agent_id: str) -> Path:
    return agent_projects_registry_dir(agent_id) / "todos"


def _project_dir(agent_id: str, project_id: str) -> Path:
    slug = (project_id or "").strip()
    if not slug:
        slug = "__global__"
    return _todos_dir(agent_id) / slug


def _session_path(agent_id: str, project_id: str, session_id: str) -> Path:
    """Path to the JSON file for a specific session's todos."""
    sid = (session_id or "").strip()
    if not sid:
        sid = "__orphan__"
    return _project_dir(agent_id, project_id) / f"session_{sid}.json"


def _legacy_path(agent_id: str, project_id: str) -> Path:
    """Old single-file path (for backward-compat reads)."""
    slug = (project_id or "").strip()
    if not slug:
        slug = "__global__"
    return _todos_dir(agent_id) / f"{slug}.json"


def _load_json(path: Path) -> list:
    """Return 'todos' list from a JSON file, or [] on any failure."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("todos")
        return rows if isinstance(rows, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _dump_json(path: Path, rows: list) -> None:
    """Atomically write a 'todos' JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"todos": rows}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _read_session_todos(agent_id: str, project_id: str, session_id: str) -> list:
    """Read todos for *one* session (returns [] if file missing)."""
    return _load_json(_session_path(agent_id, project_id, session_id))


def _read_all_todos(agent_id: str, project_id: str) -> list:
    """Aggregate todos from ALL session files under this project.

    Falls back to the legacy single-file format when no per-session
    directory exists yet.
    """
    d = _project_dir(agent_id, project_id)
    if d.is_dir():
        rows: list = []
        for f in sorted(d.glob("session_*.json")):
            rows.extend(_load_json(f))
        return rows

    # Legacy fallback
    return _load_json(_legacy_path(agent_id, project_id))


def _write_session_todos(
    agent_id: str, project_id: str, session_id: str, rows: list
) -> None:
    """Write todos for a specific session."""
    _dump_json(_session_path(agent_id, project_id, session_id), rows)





import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional



def _migrate_legacy_if_needed(agent_id: str, project_id: str) -> None:
    """One-shot migration: move todos from old flat file into per-session
    files so subsequent writes don't conflict."""
    legacy = _legacy_path(agent_id, project_id)
    if not legacy.is_file():
        return
    d = _project_dir(agent_id, project_id)
    if d.is_dir():
        return  # already migrated
    # Migrate: group legacy items by session_id
    rows = _load_json(legacy)
    if not rows:
        # Empty legacy file – just remove it
        legacy.unlink(missing_ok=True)
        return
    by_session: dict = {}
    for item in rows:
        sid = str(item.get("session_id") or "").strip() or "__orphan__"
        by_session.setdefault(sid, []).append(item)
    for sid, items in by_session.items():
        _dump_json(_session_path(agent_id, project_id, sid), items)
    # Rename legacy file as backup so we know it's migrated
    legacy.rename(legacy.with_suffix(".json.migrated"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_todos(
    agent_id: str,
    project_id: str,
    status: Optional[str] = None,
    session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List todo items for a project.

    Parameters
    ----------
    session_id : str, optional
        If provided, only return todos belonging to this session.
        If omitted (or empty), return aggregated todos from all sessions
        (project scope).
    status : str, optional
        Filter by status (pending / in_progress / completed / cancelled).
    """
    _migrate_legacy_if_needed(agent_id, project_id)

    if session_id:
        rows = _read_session_todos(agent_id, project_id, session_id)
    else:
        rows = _read_all_todos(agent_id, project_id)

    if status:
        st = status.strip().lower()
        rows = [r for r in rows if str(r.get("status") or "").strip().lower() == st]

    rows.sort(key=lambda r: r.get("created_at", ""))
    return rows


def create_todo(
    agent_id: str,
    project_id: str,
    content: str,
    session_id: str = "",
) -> Dict[str, Any]:
    """Create a new todo item for the given session.

    The item is stored in the session's own file, so concurrent writes
    from different sessions do not conflict.
    """
    raw = (content or "").strip()
    if not raw:
        raise ValueError("todo content required")
    _migrate_legacy_if_needed(agent_id, project_id)

    sid = (session_id or "").strip()
    rows = _read_session_todos(agent_id, project_id, sid)
    now = datetime.now(timezone.utc).isoformat()
    item: Dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "content": raw,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "session_id": sid,
    }
    rows.append(item)
    _write_session_todos(agent_id, project_id, sid, rows)
    return item


def _find_todo_in_all(
    agent_id: str, project_id: str, todo_id: str
) -> tuple[Optional[str], Optional[Dict[str, Any]], list]:
    """Search all session files for a todo by ID.

    Returns (session_id, item, all_rows_of_that_session) or
    (None, None, []) if not found.
    """
    d = _project_dir(agent_id, project_id)
    if not d.is_dir():
        return None, None, []
    tid = (todo_id or "").strip()
    if not tid:
        return None, None, []
    for f in sorted(d.glob("session_*.json")):
        rows = _load_json(f)
        for item in rows:
            if str(item.get("id") or "").strip() == tid:
                # Extract session_id from filename: session_<sid>.json
                sid = f.stem[len("session_"):]  # remove "session_" prefix
                if sid == "__orphan__":
                    sid = ""
                return sid, item, rows
    return None, None, []




from typing import Dict, Any, Optional
from datetime import datetime, timezone

def update_todo(
    agent_id: str,
    project_id: str,
    todo_id: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Update a todo item by its ID.

    Scans all session files to locate the todo, then writes back to
    the correct session file.
    """
    _migrate_legacy_if_needed(agent_id, project_id)

    sid, item, rows = _find_todo_in_all(agent_id, project_id, todo_id)
    if item is None:
        return None

    if "content" in updates:
        c = str(updates["content"] or "").strip()
        if c:
            item["content"] = c
    if "status" in updates:
        s = str(updates["status"] or "").strip().lower()
        if s in ("pending", "in_progress", "completed", "cancelled"):
            item["status"] = s

    item["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_session_todos(agent_id, project_id, sid, rows)
    return item


def delete_todo(
    agent_id: str,
    project_id: str,
    todo_id: str,
) -> bool:
    """Delete a todo item by its ID.

    Scans all session files to locate the todo, then writes back the
    filtered list to the correct session file.
    """
    _migrate_legacy_if_needed(agent_id, project_id)

    sid, item, rows = _find_todo_in_all(agent_id, project_id, todo_id)
    if item is None:
        return False

    rows = [r for r in rows if str(r.get("id") or "").strip() != todo_id]
    _write_session_todos(agent_id, project_id, sid, rows)
    return True
