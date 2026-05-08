"""Cron apply tool"""
import json
import logging
from src.models_pkg import Tool
logger = logging.getLogger(__name__)

def codeagent_cron_apply_handler(content: str) -> str:
    """Write full cron JSON and reload scheduler."""
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            return "Error: root JSON value must be an object"
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON: {e}"
    try:
        from src.config_plane_pkg import project_root
        from src.cron_sched_pkg import reload_cron_scheduler

        cfg = project_root() / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        path = cfg / "codeagent.cron.json"
        path.write_text(content, encoding="utf-8")
        reload_cron_scheduler()
        jobs = data.get("jobs")
        n = len(jobs) if isinstance(jobs, list) else 0
        return (
            f"codeagent_cron_apply: wrote {path} ({len(content)} chars); scheduler reloaded. "
            f"enabled={data.get('enabled')!r}; jobs={n}."
        )
    except Exception as e:
        logger.exception("codeagent_cron_apply")
        return f"codeagent_cron_apply error: {e}"

codeagent_cron_apply_def = Tool(
    name="codeagent_cron_apply",
    description=(
        "Replace entire codeagent.cron.json with the given UTF-8 JSON string and hot-reload the cron scheduler. "
        "Use codeagent_cron_path or file_read first if you need the current file. "
        "Schema: enabled (bool), jobs (array of {id, enabled, cron, timezone?, agent_id, session_id, prompt, max_tool_rounds?}); "
        "optional _readme and _example_job keys are ignored by the scheduler."
    ),
    parameters={
        "content": {
            "type": "string",
            "required": True,
            "description": "Complete JSON document for codeagent.cron.json",
        }
    },
    returns="string: result summary",
    category="codeagent",
)

