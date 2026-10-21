"""Web UI auth + bootstrap-flag endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui`` (outer ``Mount("/api/ui")`` adds the prefix).

Unlike the self-contained health handlers, these need ``project_root`` (to read
the configured webui token), so they live behind a ``build_routes(project_root)``
factory that closes over it — the same closure style as the original
``build_webui_api_app``, but scoped to just this domain.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from codeagent.web.auth_impl import (
    COOKIE_TTL_SEC,
    LEGACY_COOKIE_NAME,
    cookie_name_for,
    cookie_secure,
    get_webui_cookie_value,
    get_webui_token,
    make_webui_cookie_value,
)
from seed.integrations.cron_sched import cron_status_for_ui

logger = logging.getLogger(__name__)


def build_auth_routes(project_root: Path) -> list[Route]:
    """Return the auth + bootstrap-flag routes for ``webui_api_app``."""

    async def api_flags(request: Request) -> JSONResponse:
        try:
            cron = cron_status_for_ui()
        except Exception as e:
            logger.exception("cron_status_for_ui")
            cron = {"error": str(e)}
        return JSONResponse(
            {
                "sessions_ui": True,
                "ws_enabled": True,
                "cron": cron,
            }
        )

    async def api_auth_status(request: Request) -> JSONResponse:
        from codeagent.web.auth_impl import verify_webui_cookie

        tok = get_webui_token(project_root)
        if not tok:
            return JSONResponse({"auth_required": False, "authenticated": True})
        ok = bool(verify_webui_cookie(tok, get_webui_cookie_value(request.cookies, tok)))
        return JSONResponse({"auth_required": True, "authenticated": ok})

    async def api_auth_login(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        tok = get_webui_token(project_root)
        if not tok:
            return JSONResponse({"detail": "webui token not configured"}, status_code=400)
        if str(body.get("token") or "").strip() != tok:
            return JSONResponse({"detail": "invalid token"}, status_code=401)
        from codeagent.web.auth_impl import ws_query_token_bridge_enabled

        payload: dict[str, Any] = {"ok": True}
        if ws_query_token_bridge_enabled():
            # Lets embedded / cookie-less WebSocket clients pass ?webui_token= on /ws (opt-in; see webui_auth).
            payload["ws_query_token"] = tok

        resp = JSONResponse(payload)
        resp.set_cookie(
            cookie_name_for(tok),
            make_webui_cookie_value(tok),
            max_age=COOKIE_TTL_SEC,
            httponly=True,
            samesite="lax",
            secure=cookie_secure(),
            path="/",
        )
        # 清理旧固定名残留：老用户升级后首个请求会带 ca_webui，登录成功后抹掉
        resp.delete_cookie(LEGACY_COOKIE_NAME, path="/")
        return resp

    async def api_auth_logout(request: Request) -> JSONResponse:
        resp = JSONResponse({"ok": True})
        tok = get_webui_token(project_root)
        resp.delete_cookie(cookie_name_for(tok) if tok else LEGACY_COOKIE_NAME, path="/")
        resp.delete_cookie(LEGACY_COOKIE_NAME, path="/")
        return resp

    return [
        Route("/flags", api_flags, methods=["GET"]),
        Route("/auth/status", api_auth_status, methods=["GET"]),
        Route("/auth", api_auth_login, methods=["POST"]),
        Route("/auth/logout", api_auth_logout, methods=["POST"]),
    ]
