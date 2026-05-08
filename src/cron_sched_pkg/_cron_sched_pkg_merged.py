"""
Optional scheduled agent turns (cron).

Config: ``<CODEAGENT_PROJECT_ROOT>/config/codeagent.cron.json``
Copy from ``config/codeagent.cron.example.json`` in the repo.

Disable entirely: ``CODEAGENT_CRON=0`` (or ``false`` / ``no`` / ``off``).
Requires APScheduler: ``pip install 'codeagent[server]'`` or ``pip install apscheduler``.
"""
from __future__ import annotations
from __future__ import annotations
from __future__ import annotations


import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _normalize_cron_outcome(text: str) -> str:
    return " ".join((text or "").strip().split())


def _experience_session_value(text: str) -> str:
    """First non-empty line after ``## Session``."""
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == "## session":
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s:
                    return s
            return ""
    return ""


def _extract_outcome_section(text: str) -> str:
    """Body under ``## Outcome`` until the next ``## `` heading."""
    lines = (text or "").splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("## "):
            title = lines[i][3:].strip().lower()
            if title == "outcome":
                i += 1
                parts: List[str] = []
                while i < len(lines):
                    if lines[i].startswith("## "):
                        break
                    parts.append(lines[i])
                    i += 1
                return "\n".join(parts).strip()
        i += 1
    return ""


def _cron_outcome_matches_latest(
    mem: Any,
    *,
    job_id: str,
    session_id: str,
    new_outcome: str,
) -> bool:
    """
    True if the newest experience for this cron job id + session has the same outcome text.
    Used to skip writing duplicate episodic rows for periodic checks.
    """
    exp_dir = mem.memory_path / "experiences"
    if not exp_dir.is_dir():
        return False
    needle = f"cron-{job_id}-"
    new_norm = _normalize_cron_outcome(new_outcome)
    if not new_norm:
        return False
    want_sid = (session_id or "").strip()
    files = sorted(exp_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[:120]:
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle not in body:
            continue
        if _experience_session_value(body) != want_sid:
            continue
        prev = _extract_outcome_section(body)
        return _normalize_cron_outcome(prev) == new_norm
    return False


def cron_config_path() -> Path:
    from src.config_plane_pkg import project_root

    return project_root() / "config" / "codeagent.cron.json"


def load_cron_config() -> Dict[str, Any]:
    p = cron_config_path()
    if not p.is_file():
        return {"enabled": False, "jobs": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("cron: cannot read %s: %s", p, e)
        return {"enabled": False, "jobs": []}
    if not isinstance(data, dict):
        return {"enabled": False, "jobs": []}
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        data["jobs"] = []
    return data


def cron_job_id_is_active(jid: str) -> bool:
    """Whether this job id is listed in the UI and registered with APScheduler.

    Empty ids are inactive. Ids that are *only* underscores (e.g. legacy Web UI
    slugs from pure non-ASCII names) are inactive. An id like ``_backup`` stays
    active because it contains alphanumeric characters.
    """

    s = (jid or "").strip()
    if not s:
        return False
    if s.startswith("_") and not any(c.isalnum() for c in s):
        return False
    return True


def _cron_disabled_by_env() -> bool:
    return os.environ.get("CODEAGENT_CRON", "1").lower() in (
        "0",
        "false",
        "no",
        "off",
    )


def _tools_for_agent(aid: str):
    try:
        from src.codeagent.tools.agent_tools import get_tools_for_agent

        return get_tools_for_agent(aid)
    except Exception:
        from src.tools import setup_builtin_tools

        return setup_builtin_tools()




"""APScheduler wiring + cron config persistence."""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

_scheduler: Optional[Any] = None


async def _run_cron_job_async(job: Dict[str, Any]) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_cron_job_sync, job)


def start_cron_scheduler() -> None:
    """Start APScheduler from disk config (no-op if disabled or apscheduler missing)."""
    global _scheduler
    if _scheduler is not None:
        return
    if _cron_disabled_by_env():
        logger.info("cron: disabled (CODEAGENT_CRON)")
        return

    cfg = load_cron_config()
    if not cfg.get("enabled"):
        logger.info("cron: config disabled or missing (see config/codeagent.cron.json)")
        return

    jobs: List[Dict[str, Any]] = [j for j in cfg.get("jobs") or [] if isinstance(j, dict)]
    if not jobs:
        logger.info("cron: no jobs defined")
        return

    actionable = False
    for job in jobs:
        if not job.get("enabled", True):
            continue
        jid = (str(job.get("id") or "").strip() or None)
        if not jid or not cron_job_id_is_active(jid):
            continue
        if (str(job.get("cron") or "")).strip():
            actionable = True
            break

    if not actionable:
        logger.info("cron: no enabled jobs with a cron expression")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning(
            "cron: APScheduler not installed; scheduled jobs will not run. "
            "Install with: pip install 'codeagent[server]'   or   pip install apscheduler"
        )
        return

    sched = AsyncIOScheduler()
    default_tz = os.environ.get("CODEAGENT_CRON_TZ", "UTC").strip() or "UTC"

    for job in jobs:
        if not job.get("enabled", True):
            continue
        jid = (str(job.get("id") or "").strip() or None)
        if not jid or not cron_job_id_is_active(jid):
            continue
        expr = (str(job.get("cron") or "")).strip()
        if not expr:
            logger.warning("cron: skip job (missing id or cron): %s", job)
            continue
        tz_name = (str(job.get("timezone") or "")).strip() or default_tz
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
        except Exception:
            logger.warning("cron job %s: bad timezone %r, use UTC", jid, tz_name)
            from zoneinfo import ZoneInfo

            tz = ZoneInfo("UTC")
        try:
            trigger = CronTrigger.from_crontab(expr, timezone=tz)
        except Exception as e:
            logger.warning("cron job %s: invalid cron %r: %s", jid, expr, e)
            continue
        sched.add_job(
            _run_cron_job_async,
            trigger,
            args=[job],
            id=f"oa-cron-{jid}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("cron: registered job id=%s cron=%r tz=%s", jid, expr, tz_name)

    sched.start()
    _scheduler = sched
    logger.info("cron: scheduler started (%s job(s))", len(sched.get_jobs()))


def shutdown_cron_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        logger.exception("cron: scheduler shutdown")
    _scheduler = None


def reload_cron_scheduler() -> None:
    """Re-read ``codeagent.cron.json`` and rebuild APScheduler jobs (no full process restart)."""
    shutdown_cron_scheduler()
    start_cron_scheduler()


def write_cron_config(data: Dict[str, Any]) -> None:
    """Write the full cron config dict to disk."""
    p = cron_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def save_cron_job(job: Dict[str, Any]) -> None:
    """Add or update a single job in the cron config, then reload scheduler."""
    cfg = load_cron_config()
    jobs = cfg.get("jobs") or []
    jid = str(job.get("id") or "").strip()
    prev: Optional[Dict[str, Any]] = None
    for j in jobs:
        if isinstance(j, dict) and str(j.get("id") or "").strip() == jid:
            prev = j
            break
    # ensure required fields
    entry: Dict[str, Any] = {
        "id": jid,
        "enabled": bool(job.get("enabled", True)),
        "cron": str(job.get("cron") or "0 * * * *").strip(),
        "agent_id": str(job.get("agent_id") or "default").strip() or "default",
        "session_id": str(job.get("session_id") or "").strip() or ("cron-" + jid),
        "prompt": str(job.get("prompt") or "").strip(),
        "max_tool_rounds": int(job.get("max_tool_rounds") or 12),
    }
    if job.get("timezone"):
        entry["timezone"] = str(job.get("timezone") or "").strip()
    pid = str(job.get("project_id") or "").strip()
    if pid:
        entry["project_id"] = pid
    if "title" in job:
        t = str(job.get("title") or "").strip()
        if t:
            entry["title"] = t
    elif isinstance(prev, dict):
        ot = str(prev.get("title") or "").strip()
        if ot:
            entry["title"] = ot
    # update existing or append
    found = False
    for i, j in enumerate(jobs):
        if isinstance(j, dict) and str(j.get("id") or "").strip() == jid:
            jobs[i] = entry
            found = True
            break
    if not found:
        jobs.append(entry)
    cfg["jobs"] = jobs
    write_cron_config(cfg)
    reload_cron_scheduler()


def delete_cron_job(job_id: str) -> None:
    """Remove a job by id, then reload scheduler."""
    cfg = load_cron_config()
    jobs = cfg.get("jobs") or []
    jid = job_id.strip()
    cfg["jobs"] = [j for j in jobs if not (isinstance(j, dict) and str(j.get("id") or "").strip() == jid)]
    write_cron_config(cfg)
    reload_cron_scheduler()


def apscheduler_available() -> bool:
    try:
        import apscheduler  # noqa: F401

        return True
    except ImportError:
        return False


def cron_status_for_ui() -> Dict[str, Any]:
    """Lightweight status for ``/api/ui/flags`` (no secrets, no full prompts)."""
    cfg = load_cron_config()
    jobs_config: List[Dict[str, Any]] = []
    for j in cfg.get("jobs") or []:
        if not isinstance(j, dict):
            continue
        jid = str(j.get("id") or "").strip()
        if not cron_job_id_is_active(jid):
            continue
        row = {
            "id": jid,
            "enabled": bool(j.get("enabled", True)),
            "cron": str(j.get("cron") or "").strip(),
            "timezone": str(j.get("timezone") or "").strip(),
            "agent_id": str(j.get("agent_id") or "default").strip() or "default",
            "session_id": str(j.get("session_id") or "").strip(),
            "prompt": str(j.get("prompt") or "").strip(),
            "max_tool_rounds": int(j.get("max_tool_rounds") or 12),
        }
        title = str(j.get("title") or "").strip()
        if title:
            row["title"] = title
        jobs_config.append(row)
    out: Dict[str, Any] = {
        "apscheduler": apscheduler_available(),
        "env_disabled": _cron_disabled_by_env(),
        "config_file": str(cron_config_path()),
        "config_enabled": bool(cfg.get("enabled")),
        "job_defs": len([x for x in jobs_config if x.get("enabled")]),
        "jobs_config": jobs_config,
        "scheduler_running": _scheduler is not None,
        "scheduled_jobs": [],
    }
    if _scheduler is not None:
        for j in _scheduler.get_jobs():
            nr = getattr(j, "next_run_time", None)
            out["scheduled_jobs"].append(
                {
                    "id": getattr(j, "id", "") or "",
                    "next_run": nr.isoformat() if nr is not None else None,
                }
            )
    return out



import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.server_pkg import SESSIONS, _memkey, _tools_for_agent

logger = logging.getLogger(__name__)


def run_cron_job_sync(job: Dict[str, Any]) -> None:
    """Execute one cron job: one LLM+tools turn, persist session, sync in-memory SESSIONS."""
    if not job.get("enabled", True):
        return
    jid = (str(job.get("id") or "").strip() or "cron-job")
    agent_id = (str(job.get("agent_id") or "").strip() or "default")
    sid = (str(job.get("session_id") or "").strip() or f"cron-{jid}")
    prompt = (str(job.get("prompt") or "")).strip()
    if not prompt:
        logger.warning("cron job %s: empty prompt, skip", jid)
        return
    try:
        max_rounds = int(job.get("max_tool_rounds") or 12)
    except (TypeError, ValueError):
        max_rounds = 12
    max_rounds = max(1, min(max_rounds, 32))

    try:
        from src.codeagent.core.paths import ensure_agent_scaffold

        ensure_agent_scaffold(agent_id)
    except Exception:
        pass

    project_id = (str(job.get("project_id") or "")).strip() or ""
    mkey = _memkey(agent_id, sid)
    from src.llm_sess_pkg import (
        load_or_create_chat_session,
        merge_fresh_system,
        persist_chat_session,
    )
    from src.agent_runtime_pkg import (
        build_api_projection_messages,
        default_system_prompt,
        maybe_compact_context_messages,
        merge_llm_tail_into_full,
        run_llm_tool_loop,
    )
    from src.agent_context import clear_active_project_episodic, set_active_llm_session
    from src.llm_exec_pkg import LLMError
    from src.mem_bridge_pkg import apply_episodic_to_messages
    from src.mem_sys_pkg import MemorySystem
    from src.config_plane_pkg import project_root
    from src.llm_presets import llm_executor_from_resolved, resolve_preset

    if mkey in SESSIONS:
        chat_sess = SESSIONS[mkey]
    else:
        chat_sess = load_or_create_chat_session(sid, agent_id, project_id=project_id)

    # 将 cron 会话关联到项目（如果有），并标记频道
    if not isinstance(chat_sess.metadata, dict):
        chat_sess.metadata = {}
    if project_id:
        chat_sess.metadata["project_id"] = project_id
    chat_sess.metadata["channel"] = "Cron"
    chat_sess.metadata["source"] = f"cron:{jid}"

    fresh = default_system_prompt()
    import hashlib
    cur_hash = hashlib.sha256((fresh or "").encode("utf-8")).hexdigest()
    if not isinstance(chat_sess.metadata, dict):
        chat_sess.metadata = {}
    prev_hash = str(chat_sess.metadata.get("system_hash") or "").strip()
    if not chat_sess.messages:
        chat_sess.messages = [{"role": "system", "content": fresh}]
    else:
        if (not prev_hash) or (prev_hash != cur_hash):
            chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh)
        else:
            try:
                keep = str(chat_sess.messages[0].get("content") or "")
            except Exception:
                keep = ""
            chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, keep)
    chat_sess.metadata["system_hash"] = cur_hash

    cron_line = f"[cron:{jid}] {prompt}"
    chat_sess.messages.append(
        {
            "role": "user",
            "content": cron_line,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    try:
        from src.transcript_store import append_transcript_entries

        append_transcript_entries(sid, [chat_sess.messages[-1]], agent_id=agent_id)
    except Exception:
        pass
    max_hist = int(os.environ.get("CODEAGENT_CHAT_USER_ROUNDS", "12"))

    # Resolve LLM config from presets / env (see resolve_preset)
    llm = llm_executor_from_resolved(resolve_preset(None))
    set_active_llm_session(mkey)
    tools_used: List[str] = []
    tool_trace: List[Dict[str, str]] = []
    try:
        api_msgs = build_api_projection_messages(
            chat_sess.messages,
            max_user_rounds=max_hist,
            skills_suffix=None,
        )
        maybe_compact_context_messages(api_msgs, llm)
        try:
            from src.codeagent.core.paths import agent_memory_dir

            apply_episodic_to_messages(
                api_msgs,
                agent_memory_dir(agent_id),
                sid,
                project_scope=False,
            )
        except Exception:
            apply_episodic_to_messages(
                api_msgs, project_root(), sid, project_scope=False
            )
        reg, exe = _tools_for_agent(agent_id)
        n_before = len(api_msgs)
        reply, _, tools_used, tool_trace, _loop_meta = asyncio.run(
            run_llm_tool_loop(
                llm,
                exe,
                messages=api_msgs,
                registry=reg,
                max_tool_rounds=max_rounds,
            )
        )
        tail = merge_llm_tail_into_full(chat_sess.messages, api_msgs, n_before)
        try:
            from src.transcript_store import append_transcript_entries

            if tail:
                append_transcript_entries(sid, tail, agent_id=agent_id)
        except Exception:
            pass
        try:
            persist_chat_session(chat_sess, agent_id)
        except Exception:
            logger.exception("cron persist failed job=%s", jid)
        SESSIONS[mkey] = chat_sess
        if os.environ.get("CODEAGENT_MEMORY_LOG", "1").lower() not in ("0", "false", "no"):
            try:
                from src.codeagent.core.paths import agent_memory_dir

                mem = MemorySystem(base_path=agent_memory_dir(agent_id))
                outcome = (reply or "")[:2000]
                skip_dup = os.environ.get("CODEAGENT_CRON_EXPERIENCE_SKIP_DUPLICATE", "").lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
                if skip_dup and _cron_outcome_matches_latest(
                    mem, job_id=jid, session_id=sid, new_outcome=outcome
                ):
                    logger.info(
                        "cron job id=%s: skip experience log (outcome unchanged vs latest for session=%s)",
                        jid,
                        sid,
                    )
                else:
                    ttl_raw = os.environ.get("CODEAGENT_CRON_EXPERIENCE_TTL_SECONDS", "").strip()
                    ttl_val = int(ttl_raw) if ttl_raw.isdigit() else None
                    mem.log_experience(
                        task_id=f"cron-{jid}-{datetime.now(timezone.utc).isoformat()}",
                        outcome=outcome,
                        tools_used=tools_used,
                        session_id=sid,
                        ttl_seconds=ttl_val,
                    )
            except Exception:
                pass
        logger.info(
            "cron job done id=%s agent=%s session=%s tools=%s trace_len=%s",
            jid,
            agent_id,
            sid,
            ",".join(tools_used) if tools_used else "(none)",
            len(tool_trace),
        )
    except LLMError as e:
        logger.warning("cron job LLM error id=%s: %s", jid, e)
        try:
            chat_sess.messages.pop()
        except Exception:
            pass
    except Exception:
        logger.exception("cron job crashed id=%s", jid)
        try:
            chat_sess.messages.pop()
        except Exception:
            pass
    finally:
        clear_active_project_episodic()
        set_active_llm_session(None)


