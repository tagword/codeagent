"""Web UI cron + allowlist endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. Handlers need ``project_root`` (via factory). The
``_allowlist_path`` helper defined in ``webui_api_app`` is imported lazily
inside each handler to avoid a circular import.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from seed.integrations.cron_sched import (
    delete_cron_job,
    load_cron_config,
    reload_cron_scheduler,
    save_cron_job,
    write_cron_config,
)

logger = logging.getLogger(__name__)


def build_cronallow_routes(project_root: Path) -> list[Route]:
    """Return the cron + allowlist routes for ``webui_api_app``."""

    async def api_cron_toggle(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        cfg = load_cron_config()
        cfg["enabled"] = bool(body.get("enabled"))
        write_cron_config(cfg)
        reload_cron_scheduler()
        return JSONResponse({"ok": True})

    async def api_cron_job(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        try:
            save_cron_job(body)
        except Exception as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return JSONResponse({"ok": True})

    async def api_cron_job_delete(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        jid = str(body.get("job_id") or "").strip()
        try:
            delete_cron_job(jid)
        except Exception as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return JSONResponse({"ok": True})

    async def api_allowlist_get(_: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _allowlist_path
        p = _allowlist_path(project_root)
        if not p.is_file():
            return JSONResponse({"mode": "all", "paths": []})
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return JSONResponse({"mode": "all", "paths": []})
        if not isinstance(data, dict):
            return JSONResponse({"mode": "all", "paths": []})
        mode = str(data.get("mode") or "all")
        paths = data.get("paths") if isinstance(data.get("paths"), list) else []
        paths = [str(x) for x in paths if isinstance(x, str)]
        return JSONResponse({"mode": mode, "paths": paths})

    async def api_allowlist_post(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _allowlist_path
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        mode = str(body.get("mode") or "all")
        paths = body.get("paths") if isinstance(body.get("paths"), list) else []
        paths = [str(x).strip() for x in paths if str(x).strip()]
        p = _allowlist_path(project_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"mode": mode, "paths": paths}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return JSONResponse({"ok": True})



    return [
        Route("/cron/toggle", api_cron_toggle, methods=["POST"]),
        Route("/cron/job", api_cron_job, methods=["POST"]),
        Route("/cron/job/delete", api_cron_job_delete, methods=["POST"]),
        Route("/allowlist", api_allowlist_get, methods=["GET"]),
        Route("/allowlist", api_allowlist_post, methods=["POST"]),
    ]
