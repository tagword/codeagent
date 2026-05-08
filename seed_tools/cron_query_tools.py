"""Cron path tool"""
import logging
from seed_tools.models import Tool
logger = logging.getLogger(__name__)

def codeagent_cron_path_handler() -> str:
    """Absolute path to ``config/codeagent.cron.json`` under CODEAGENT_PROJECT_ROOT (default ``~/.codeagent``)."""
    try:
        from seed.config_plane import project_root

        p = (project_root() / "config" / "codeagent.cron.json").resolve()
        return str(p)
    except Exception as e:
        return f"Error: {e}"

codeagent_cron_path_def = Tool(
    name="codeagent_cron_path",
    description=(
        "Return absolute path to codeagent.cron.json (scheduled LLM jobs). "
        "Use with file_read/file_write; after writing, call codeagent_cron_reload. "
        "Or use codeagent_cron_apply to write valid JSON and reload in one step."
    ),
    parameters={},
    returns="string: filesystem path",
    category="codeagent",
)

def codeagent_cron_reload_handler() -> str:
    """Re-read codeagent.cron.json and rebuild APScheduler (no full process restart)."""
    try:
        from seed.cron_sched import cron_status_for_ui, reload_cron_scheduler

        reload_cron_scheduler()
        st = cron_status_for_ui()
        jobs = st.get("scheduled_jobs") or []
        lines = [
            "codeagent_cron_reload: ok",
            f"scheduler_running={st.get('scheduler_running')}",
            f"config_enabled={st.get('config_enabled')}",
            f"env_disabled={st.get('env_disabled')}",
            f"registered_jobs={len(jobs)}",
        ]
        for j in jobs[:16]:
            lines.append(f"  - {j.get('id')} next={j.get('next_run')}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("codeagent_cron_reload")
        return f"codeagent_cron_reload error: {e}"

codeagent_cron_reload_def = Tool(
    name="codeagent_cron_reload",
    description=(
        "After editing config/codeagent.cron.json with file_write (or external editor), "
        "call this to apply changes without restarting codeagent serve. "
        "Requires apscheduler and CODEAGENT_CRON not disabled."
    ),
    parameters={},
    returns="string: reload summary",
    category="codeagent",
)

