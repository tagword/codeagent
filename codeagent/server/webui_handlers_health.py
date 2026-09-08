"""Web UI health / watchdog endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui/health/*`` (outer ``Mount("/api/ui")`` adds the prefix).

This module is intentionally self-contained: none of the handlers depend on
``build_webui_api_app``'s closure state (``project_root``, ``SESSIONS`` etc.),
so they can live as plain module-level functions.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)


async def api_health_heartbeat(_: Request) -> JSONResponse:
    """POST /api/health/heartbeat — update agent heartbeat."""
    import time

    from codeagent.core.paths import codeagent_home

    ts = time.time()
    hb_file = Path(codeagent_home()) / "heartbeat"
    hb_file.parent.mkdir(parents=True, exist_ok=True)
    hb_file.write_text(str(ts), encoding="utf-8")
    return JSONResponse({"ts": ts})


async def api_health_status(_: Request) -> JSONResponse:
    """GET /api/health/status — return heartbeat + process status."""
    try:
        import time

        from codeagent.core.paths import codeagent_home

        hb_file = Path(codeagent_home()) / "heartbeat"
        now = time.time()
        last_hb = 0.0
        if hb_file.is_file():
            try:
                last_hb = float(hb_file.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                pass
        elapsed = now - last_hb if last_hb > 0 else -1
        status = "alive" if 0 < elapsed < 180 else ("stuck" if elapsed >= 180 else "unknown")
        return JSONResponse(
            {
                "status": status,
                "last_heartbeat": last_hb,
                "elapsed_seconds": round(elapsed, 1) if elapsed >= 0 else None,
                "process_id": os.getpid(),
            }
        )
    except Exception as e:
        logger.exception("health/status error")
        return JSONResponse({"error": str(e), "type": type(e).__name__}, status_code=500)


async def api_health_diagnose(_: Request) -> JSONResponse:
    """GET /api/health/diagnose — run diagnostic checks."""
    from codeagent.server.self_healing import diagnose

    return JSONResponse(diagnose())


async def api_health_heal(_: Request) -> JSONResponse:
    """POST /api/health/heal — attempt self-healing."""
    from codeagent.server.self_healing import heal

    return JSONResponse(heal())


def build_health_routes() -> list[Route]:
    """Return the health/watchdog routes registered by ``webui_api_app``."""
    return [
        Route("/health/heartbeat", api_health_heartbeat, methods=["POST"]),
        Route("/health/status", api_health_status, methods=["GET"]),
        Route("/health/diagnose", api_health_diagnose, methods=["GET"]),
        Route("/health/heal", api_health_heal, methods=["POST"]),
    ]
