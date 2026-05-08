"""LLM / HTTP chat session persistence — uses models.Session (same shape as TurnLoopEngine).

存储策略（两层结构）：
  - 无项目关联的会话 → agents/<agent_id>/sessions/llm_sessions/<id>.json
  - 有项目关联的会话 → agents/<agent_id>/projects-data/<project-id>/sessions/<id>.json
"""
from __future__ import annotations
from __future__ import annotations
from __future__ import annotations
from __future__ import annotations


import os
import re
from pathlib import Path
from typing import Optional

from src.config_plane_pkg import project_root
from src.models_pkg import Session
from src.sess_store_pkg import SessionStore
from src.codeagent.core.paths import agent_id_default, agent_home

_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _legacy_llm_sessions_dir() -> Path:
    return (project_root() / "llm_sessions").resolve()


def llm_sessions_dir(agent_id: Optional[str] = None) -> Path:
    """
    LLM session storage directory (default, for non-project sessions).

    Priority:
    - CODEAGENT_LLM_SESSIONS_DIR (explicit override)
    - <project_root>/agents/<agent_id>/sessions/llm_sessions (multi-agent layout; always used)

    On first access, if legacy ``<project_root>/llm_sessions`` exists and the new agent
    directory is empty, we best-effort migrate ``*.json`` into the agent directory.
    """
    raw = os.environ.get("CODEAGENT_LLM_SESSIONS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    aid = (agent_id or "").strip() or agent_id_default()
    d = (agent_home(aid) / "sessions" / "llm_sessions").resolve()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        # If we cannot create it, fall back to legacy as last resort.
        return _legacy_llm_sessions_dir()

    legacy = _legacy_llm_sessions_dir()
    try:
        if legacy.is_dir():
            legacy_json = sorted(legacy.glob("*.json"))
            # Only migrate when the agent dir has no sessions yet (avoid mixing).
            if legacy_json and not any(d.glob("*.json")):
                for p in legacy_json:
                    try:
                        target = d / p.name
                        if target.exists():
                            continue
                        p.replace(target)
                    except OSError:
                        # Best-effort: ignore individual file move errors.
                        pass
    except OSError:
        pass
    return d


def _project_sessions_dir(project_id: str, agent_id: Optional[str] = None) -> Path:
    """项目关联会话的存储目录。"""
    from src.codeagent.core.paths import agent_project_data_subdir
    aid = (agent_id or "").strip() or agent_id_default()
    return agent_project_data_subdir(aid, project_id, "sessions")


def _safe_session_filename(session_id: str) -> str:
    s = _SAFE_RE.sub("_", session_id).strip("._-") or "session"
    return s[:128]


def _session_store(agent_id: Optional[str] = None) -> SessionStore:
    return SessionStore(str(llm_sessions_dir(agent_id)))


def _project_session_store(project_id: str, agent_id: Optional[str] = None) -> SessionStore:
    """创建指向项目会话目录的 SessionStore。"""
    return SessionStore(str(_project_sessions_dir(project_id, agent_id)))


def _resolve_session_store(session: Session, agent_id: Optional[str] = None) -> SessionStore:
    """根据 session 的 metadata.project_id 解析正确的 SessionStore。"""
    pid = ""
    if isinstance(session.metadata, dict):
        pid = str(session.metadata.get("project_id") or "").strip()
    if pid:
        return _project_session_store(pid, agent_id)
    return _session_store(agent_id)





import json
from typing import Any, Dict, List, Optional

from src.codeagent.core.paths import agent_id_default
from src.models_pkg import Session
from src.sess_store_pkg._sess_store_pkg_merged import SessionStore


def _session_from_stored_json(data: Dict[str, Any], slug: str, handle: str) -> Session:
    """Build ``models_pkg.Session`` from on-disk JSON (no ``SessionStore._dict_to_session``).

    Web UI transcript only needs ``messages``; ``turns`` are omitted to avoid brittle deserialization.
    """
    msgs = data.get("messages")
    if not isinstance(msgs, list):
        msgs = []
    dict_msgs = [m for m in msgs if isinstance(m, dict)]
    dict_msgs = _scrub_history_for_model(dict_msgs)

    sess_id = str(data.get("id") or slug)
    sid = data.get("session_id") or data.get("name") or handle
    name = str(data.get("name") or (sid if isinstance(sid, str) else handle))
    cfg = data.get("config") if isinstance(data.get("config"), dict) else {}
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    ca = str(data.get("created_at") or "")
    ua = str(data.get("updated_at") or ca)

    return Session(
        id=sess_id,
        name=name,
        created_at=ca,
        updated_at=ua,
        messages=list(dict_msgs),
        turns=[],
        config=dict(cfg),
        metadata=dict(meta),
    )


def _scrub_history_for_model(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip <think>/chain-of-thought markup from assistant content before it is
    replayed to the model.

    We keep the JSON on disk untouched (that is the forensic ground truth) but
    never let stray chain-of-thought leak back into the next turn's context,
    because that caused self-reinforcing exploratory repetition (same file
    sliced 5 different ways, same port re-queried, etc.).
    """
    try:
        from src.agent_runtime_pkg import strip_inline_tool_markup_from_assistant_text as _strip
    except Exception:  # pragma: no cover - defensive; runtime always has this
        return msgs
    out: List[Dict[str, Any]] = []
    for m in msgs:
        if not isinstance(m, dict):
            out.append(m)
            continue
        if m.get("role") != "assistant":
            out.append(m)
            continue
        c = m.get("content")
        if isinstance(c, str) and c:
            cleaned = _strip(c)
            if cleaned != c:
                m = {**m, "content": cleaned}
        out.append(m)
    return out


def _try_load_from_store(store: SessionStore, handle: str) -> Optional[Session]:
    """尝试从指定的 SessionStore 加载会话。"""
    slug = _safe_session_filename(handle)
    path = store.base_path / f"{slug}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    msgs = data.get("messages")
    if not isinstance(msgs, list):
        return None

    if data.get("id") and all(isinstance(m, dict) for m in msgs):
        return _session_from_stored_json(data, slug, handle)

    sid = data.get("session_id") or handle
    raw_ts = data.get("updated_at") or ""
    dict_msgs = [m for m in msgs if isinstance(m, dict)]
    dict_msgs = _scrub_history_for_model(dict_msgs)
    return Session(
        id=slug,
        name=sid if isinstance(sid, str) else handle,
        created_at=str(raw_ts),
        updated_at=str(raw_ts),
        messages=list(dict_msgs),
        turns=[],
        config={"kind": "llm_chat", "migrated_from": "legacy_messages_only"},
        metadata={},
    )


def load_chat_session_from_disk(
    handle: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Optional[Session]:
    """
    Load Session JSON from disk.

    查找顺序：
    1. 如果指定了 project_id → 先从项目会话目录找
    2. 如果没找到或没指定 → 从默认 llm_sessions 目录找
    3. 如果还没找到且未指定 project_id → 搜索所有项目目录

    ``handle`` is the user-visible key (CLI --session or browser session_id).
    """
    aid = (agent_id or "").strip() or agent_id_default()

    # 如果指定了项目，先查项目目录
    pid = (project_id or "").strip() if project_id else ""
    if pid:
        pstore = _project_session_store(pid, aid)
        found = _try_load_from_store(pstore, handle)
        if found is not None:
            return found

    # 再查默认目录
    store = _session_store(aid)
    found = _try_load_from_store(store, handle)
    if found is not None:
        return found

    # 如果未指定 project_id，搜索所有项目目录作为后备
    if not pid:
        from src.proj_reg_pkg import list_projects
        for proj in list_projects(aid):
            pstore = _project_session_store(proj["id"], aid)
            found = _try_load_from_store(pstore, handle)
            if found is not None:
                return found

    return None





import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.codeagent.core.paths import agent_id_default



def _scan_session_dir(
    d: Path,
    *,
    limit: int,
    filter_by_project: bool,
    filter_project_id: str,
) -> List[Dict[str, Any]]:
    """扫描单个目录的会话 JSON，返回元信息列表。"""
    if not d.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(rows) >= limit:
            break
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        msgs = data.get("messages")
        n_msg = _count_user_messages(msgs)
        name = data.get("name")
        sid = str(name).strip() if isinstance(name, str) and name.strip() else path.stem
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        cfg = data.get("config") if isinstance(data.get("config"), dict) else {}
        sess_proj = str(meta.get("project_id") or "").strip()
        if filter_by_project:
            want = (filter_project_id or "").strip()
            if want:
                if sess_proj != want:
                    continue
            else:
                if sess_proj:
                    continue
        preview = ""
        if isinstance(msgs, list):
            for m in reversed(msgs):
                if isinstance(m, dict) and m.get("role") == "user":
                    preview = str(m.get("content") or "")[:120]
                    break
        display_title = _session_display_title(preview, meta)
        channel = _infer_channel(sid, meta, cfg)
        rows.append(
            {
                "session_id": sid,
                "file_id": str(data.get("id") or path.stem),
                "updated_at": str(data.get("updated_at") or ""),
                "message_count": n_msg,
                "preview": preview,
                "display_title": display_title,
                "channel": channel,
                "project_id": sess_proj,
            }
        )
    return rows


def list_stored_llm_sessions_meta(
    *,
    limit: int = 100,
    agent_id: Optional[str] = None,
    filter_by_project: bool = False,
    filter_project_id: str = "",
) -> List[Dict[str, Any]]:
    """
    Recent LLM chat sessions from disk (for Web UI / tooling).

    When ``filter_by_project`` is True:
      - If ``filter_project_id`` is set → scan that project's session dir
      - If ``filter_project_id`` is empty → scan default (non-project) sessions
    When ``filter_by_project`` is False:
      - Scan default directory + all project directories
    """
    aid = (agent_id or "").strip() or agent_id_default()
    lim = max(1, min(int(limit), 500))

    # 仅在过滤指定项目时，扫描该项目目录
    if filter_by_project:
        want = (filter_project_id or "").strip()
        if want:
            pdir = _project_sessions_dir(want, aid)
            return _scan_session_dir(
                pdir, limit=lim,
                filter_by_project=True, filter_project_id=want,
            )
        else:
            # 过滤无项目的会话 → 只扫默认目录
            d = llm_sessions_dir(aid)
            return _scan_session_dir(
                d, limit=lim,
                filter_by_project=True, filter_project_id="",
            )

    # 不按项目过滤 → 合并默认目录 + 所有项目目录
    rows: List[Dict[str, Any]] = []

    # 1. 默认目录
    d = llm_sessions_dir(aid)
    rows.extend(_scan_session_dir(
        d, limit=lim,
        filter_by_project=False, filter_project_id="",
    ))

    if len(rows) >= lim:
        return rows[:lim]

    # 2. 扫描所有项目的会话目录
    from src.proj_reg_pkg import list_projects
    projects = list_projects(aid)
    for proj in projects:
        if len(rows) >= lim:
            break
        pid = proj["id"]
        pdir = _project_sessions_dir(pid, aid)
        rows.extend(_scan_session_dir(
            pdir, limit=lim - len(rows),
            filter_by_project=False, filter_project_id="",
        ))

    # 按更新时间降序排列
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return rows[:lim]


def list_stored_llm_session_ids(
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[str]:
    """列出会话 ID。如果指定 project_id，则只扫描项目目录。"""
    aid = (agent_id or "").strip() or agent_id_default()

    if project_id:
        d = _project_sessions_dir(project_id, aid)
    else:
        d = llm_sessions_dir(aid)

    if not d.is_dir():
        return []
    seen: List[str] = []
    for path in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.get("name")
            sid = data.get("session_id")
            oid = data.get("id")
            if isinstance(name, str) and name.strip():
                seen.append(name.strip())
            elif isinstance(sid, str) and sid.strip():
                seen.append(sid.strip())
            elif isinstance(oid, str) and oid.strip():
                seen.append(oid.strip())
            else:
                seen.append(path.stem)
        except (json.JSONDecodeError, OSError):
            seen.append(path.stem)
    return seen


def _strip_non_leading_system(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop system roles after index 0 — strict chat servers allow only one leading system."""
    if not msgs:
        return msgs
    out: List[Dict[str, Any]] = [msgs[0]]
    for m in msgs[1:]:
        if isinstance(m, dict) and m.get("role") == "system":
            continue
        out.append(m)
    return out


def merge_fresh_system(
    loaded: List[Dict[str, Any]],
    fresh_system: str,
) -> List[Dict[str, Any]]:
    """Use latest config/system text while restoring transcript tail."""
    if not loaded:
        return [{"role": "system", "content": fresh_system}]
    loaded = _strip_non_leading_system(loaded)
    if loaded and loaded[0].get("role") == "system":
        return [{"role": "system", "content": fresh_system}] + loaded[1:]
    return [{"role": "system", "content": fresh_system}] + loaded



import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.codeagent.core.paths import agent_id_default
from src.models_pkg import Session


def load_or_create_chat_session(
    handle: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Session:
    found = load_chat_session_from_disk(handle, agent_id, project_id)
    if found is not None:
        return found
    sess = Session.for_llm_handle(handle, _safe_session_filename(handle))
    if project_id:
        if not isinstance(sess.metadata, dict):
            sess.metadata = {}
        sess.metadata["project_id"] = project_id
    return sess


def read_stored_session_project_id(handle: str, agent_id: Optional[str] = None) -> str:
    s = load_chat_session_from_disk(handle, agent_id)
    if s is None:
        return ""
    md = s.metadata if isinstance(s.metadata, dict) else {}
    return str(md.get("project_id") or "").strip()


def persist_chat_session(session: Session, agent_id: Optional[str] = None) -> Path:
    """持久化会话。

    根据 session.metadata.project_id 自动路由到：
      - 有项目 → projects-data/<project-id>/sessions/
      - 无项目 → sessions/llm_sessions/
    """
    session.touch_updated()
    store = _resolve_session_store(session, agent_id)
    store.save_session(session)
    return store.base_path / f"{session.id}.json"


def _llm_session_json_path(handle: str) -> Path:
    slug = _safe_session_filename(handle)
    return llm_sessions_dir() / f"{slug}.json"


def _find_session_file(
    handle: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Optional[Path]:
    """查找会话文件路径，优先项目目录。"""
    slug = _safe_session_filename(handle)
    aid = (agent_id or "").strip() or agent_id_default()

    pid = (project_id or "").strip() if project_id else ""
    if pid:
        pdir = _project_sessions_dir(pid, aid)
        pp = pdir / f"{slug}.json"
        if pp.is_file():
            return pp

    default = llm_sessions_dir(aid) / f"{slug}.json"
    if default.is_file():
        return default
    return None


def delete_stored_llm_session(
    handle: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bool:
    """Remove persisted LLM chat JSON for this session id."""
    path = _find_session_file(handle, agent_id, project_id)
    if path is None:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def archive_stored_llm_session(
    handle: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bool:
    """Move session JSON to ``archived/`` under its storage directory."""
    path = _find_session_file(handle, agent_id, project_id)
    if path is None:
        return False
    arch = path.parent / "archived"
    try:
        arch.mkdir(parents=True, exist_ok=True)
        dest = arch / path.name
        if dest.is_file():
            dest.unlink()
        path.replace(dest)
    except OSError:
        return False
    return True


def rename_stored_llm_session(
    handle: str,
    new_title: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bool:
    """Update display_title in session metadata and persist."""
    sess = load_chat_session_from_disk(handle, agent_id, project_id)
    if sess is None:
        return False
    if not isinstance(sess.metadata, dict):
        sess.metadata = {}
    sess.metadata["display_title"] = (new_title or "").strip()[:80] or "未命名对话"
    sess.metadata["display_title_source"] = "manual"
    try:
        persist_chat_session(sess, agent_id)
    except OSError:
        return False
    return True


def save_llm_messages(
    session_id: str,
    messages: List[Dict[str, Any]],
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Path:
    """Upsert Session.messages and persist."""
    sess = load_chat_session_from_disk(session_id, agent_id, project_id)
    if sess is None:
        sess = Session.for_llm_handle(session_id, _safe_session_filename(session_id))
        if project_id:
            if not isinstance(sess.metadata, dict):
                sess.metadata = {}
            sess.metadata["project_id"] = project_id
    sess.messages = messages
    return persist_chat_session(sess, agent_id)


def load_llm_messages(
    session_id: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    sess = load_chat_session_from_disk(session_id, agent_id, project_id)
    if sess is None:
        return None
    return sess.messages


def _looks_like_cot_title(s: str) -> bool:
    """已写入 metadata 但实为思维链/英文 CoT 的标题，列表展示时回退到用户预览。"""
    t = (s or "").strip()
    if not t:
        return True
    low = t.lower()
    if "thinking process" in low or "analyze the" in low:
        return True
    if re.match(r"^\d+\.\s*\*+", t):
        return True
    if t.startswith("**") and "analyze" in low[:80]:
        return True
    return False


def _session_display_title(preview: str, metadata: Dict[str, Any]) -> str:
    dt = metadata.get("display_title")
    if isinstance(dt, str) and dt.strip():
        cand = dt.strip()[:80]
        if not _looks_like_cot_title(cand):
            return cand
    line = (preview or "").strip().replace("\n", " ")
    if line:
        return (line[:40] + "…") if len(line) > 40 else line
    return "未命名对话"


def _infer_channel(session_id: str, metadata: Dict[str, Any], config: Dict[str, Any]) -> str:
    ch = metadata.get("channel")
    if isinstance(ch, str) and ch.strip():
        return ch.strip()[:48]
    src = metadata.get("source")
    if isinstance(src, str) and src.strip():
        return src.strip()[:48]
    sid = (session_id or "").lower()
    cfg_kind = (config.get("kind") or "") if isinstance(config, dict) else ""
    if cfg_kind == "webhook" or "webhook" in sid:
        return "Webhook"
    return "Web 聊天"


def _count_user_messages(msgs: Any) -> int:
    if not isinstance(msgs, list):
        return 0
    return sum(1 for m in msgs if isinstance(m, dict) and m.get("role") == "user")


