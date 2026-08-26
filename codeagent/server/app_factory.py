"""Starlette HTTP / WebSocket application factory."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def create_app():
    import logging as logging_mod

    from codeagent.core import env as ca_env

    if not logging_mod.getLogger().handlers:
        logging_mod.basicConfig(
            level=ca_env.pick_default("INFO", ca_env.LOG_LEVEL).upper(),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    from contextlib import asynccontextmanager

    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse, Response
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.websockets import WebSocket

    from codeagent.server.webui_api_app import build_webui_api_app
    from codeagent.core.bootstrap import bootstrap_codeagent_runtime

    bootstrap_codeagent_runtime()

    try:
        from seed.core.config_plane import ensure_default_config_files
        from seed.core.config_plane import project_root as _pr

        ensure_default_config_files(_pr())
    except Exception:
        logger.exception("bootstrap config failed")

    from codeagent.web.auth_impl import WebUIAuthMiddleware, get_webui_token
    from seed.core.config_plane import project_root as project_root_fn

    from . import _memkey, get_app_html, get_setup_html

    project_root = project_root_fn()

    # ── WebSocket 广播基础设施 ──
    ws_by_session: dict[str, set] = defaultdict(set)

    async def _broadcast_session_event(aid: str, sid: str, payload: dict) -> None:
        mkey = _memkey(aid, sid)
        msg = dict(payload)
        msg.setdefault("session_id", sid)
        msg.setdefault("agent_id", aid)
        for ws in list(ws_by_session.get(mkey, ())):
            with contextlib.suppress(Exception):
                await ws.send_json(msg)

    async def homepage(request: Request) -> HTMLResponse:
        from starlette.responses import RedirectResponse, Response

        setup_marker = project_root / "config" / "setup.json"
        if not setup_marker.is_file():
            setup_marker = project_root / "config" / "codeagent.setup.json"
        done = False
        if setup_marker.is_file():
            try:
                j = json.loads(setup_marker.read_text(encoding="utf-8") or "{}")
                done = bool(j.get("done"))
            except Exception:
                done = False
        if not done:
            return RedirectResponse("/setup", status_code=302)
        html, etag = get_app_html()
        if_none = request.headers.get("if-none-match")
        if if_none and if_none == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return HTMLResponse(
            html,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=0, must-revalidate",
            },
        )

    async def setup_page(_: Request) -> HTMLResponse:
        return HTMLResponse(get_setup_html())

    async def api_chat(request: Request) -> JSONResponse:
        """WebUI 聊天入口：HTTP 解析/多模态校验/``/skill`` 命令 → run_chat_turn。

        核心逻辑见 :func:`codeagent.server.chat_turn.run_chat_turn`（WebUI 与
        cron 共用）。薄壳只做请求层工作，不持有会话状态。
        """
        from codeagent.server.chat_turn import run_chat_turn
        from seed.core.llm_exec import LLMError

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)

        session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
        from codeagent.core import env as ca_env

        agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
        body["agent_id"] = agent_id
        body["session_id"] = session_id

        llm_id = str(body.get("llm_id") or "").strip()
        vision_llm_id = str(body.get("vision_llm_id") or "").strip()
        image_gen_llm_id = str(body.get("image_gen_llm_id") or "").strip()
        audio_llm_id = str(body.get("audio_llm_id") or "").strip()
        music_llm_id = str(body.get("music_llm_id") or "").strip()
        video_gen_llm_id = str(body.get("video_gen_llm_id") or "").strip()

        from codeagent.server.attachment_api import parse_chat_multimodal_body

        try:
            user_msg, _att_ids, has_image, _extra = parse_chat_multimodal_body(body)
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)

        has_video = bool(_extra.get("has_video"))
        has_audio = bool(_extra.get("has_audio"))

        message = str(user_msg.get("content") or "").strip()
        from codeagent.core.image_understanding import (
            image_attachment_allowed,
            video_attachment_allowed,
        )
        from codeagent.core.audio_models import preset_supports_audio_id

        if has_image and not image_attachment_allowed(vision_llm_id):
            return JSONResponse(
                {
                    "detail": (
                        "发送图片需要 supports_vision 的多模态预设，"
                        "或已配置 MiniMax MCP（understand_image）"
                    )
                },
                status_code=400,
            )
        if has_video and not video_attachment_allowed(vision_llm_id):
            return JSONResponse(
                {"detail": "发送视频需要选择支持多模态的模型 (vision_llm_id)"},
                status_code=400,
            )
        if has_audio:
            if not audio_llm_id or not preset_supports_audio_id(audio_llm_id):
                return JSONResponse(
                    {"detail": "需要选择支持音频转写的模型 (audio_llm_id)"},
                    status_code=400,
                )

        project_id = str(body.get("project_id") or "").strip()
        if project_id == "__unassigned__":
            project_id = ""

        _forced_mcp_skill_suffix = ""
        if message.startswith("/skill") or (message.startswith("/") and ":" in message.split(None, 1)[0]):
            from codeagent.server.webui_api_app import _parse_mcp_skill_slash_command
            from seed_tools.mcp import mcp_skill_handler

            try:
                _mcp_sid, _mcp_skill, _mcp_args = _parse_mcp_skill_slash_command(message)
            except ValueError as e:
                return JSONResponse({"detail": str(e)}, status_code=400)
            _mcp_skill_text = await asyncio.to_thread(
                mcp_skill_handler,
                _mcp_sid,
                _mcp_skill,
                _mcp_args,
            )
            if len(_mcp_skill_text) > 30000:
                _mcp_skill_text = _mcp_skill_text[:30000] + "\n\n[已截断：MCP skill 输出超过 30000 字符]"
            _forced_mcp_skill_suffix = (
                "\n\n## MCP Skill\n\n"
                f"本轮已显式加载 MCP skill `{_mcp_sid}/{_mcp_skill}`。"
                "请按该 skill 的内容处理用户请求。\n\n"
                f"{_mcp_skill_text}\n"
            )
            message = f"请使用 MCP skill `{_mcp_sid}/{_mcp_skill}` 处理本轮请求。"
            user_msg["content"] = message

        try:
            result = await run_chat_turn(
                agent_id=agent_id,
                session_id=session_id,
                user_msg=user_msg,
                llm_id=llm_id,
                vision_llm_id=vision_llm_id,
                image_gen_llm_id=image_gen_llm_id,
                audio_llm_id=audio_llm_id,
                music_llm_id=music_llm_id,
                video_gen_llm_id=video_gen_llm_id,
                project_id=project_id,
                enable_thinking=body.get("enable_thinking"),
                reasoning_effort=str(body.get("reasoning_effort") or ""),
                clear_vision_context=bool(body.get("clear_vision_context")),
                if_busy="queue",
                emit_ws=True,
                broadcast_fn=_broadcast_session_event,
                forced_skill_suffix=_forced_mcp_skill_suffix,
            )
            if result.get("queued") or result.get("skipped"):
                return JSONResponse(result, status_code=202)
            return JSONResponse(result)
        except LLMError as e:
            return JSONResponse({"detail": str(e)}, status_code=502)

    async def api_chat_stop(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        from . import ACTIVE_CHAT_CANCELS, _memkey, _running_contains
        session_id = (body.get("session_id") or "web-chat").strip()
        agent_id = (body.get("agent_id") or "").strip() or "default"
        _run_mkey = _memkey(agent_id, session_id)
        # 以 _running_sessions 为唯一判断源，ACTIVE_CHAT_CANCELS 只负责取消
        if not _running_contains(_run_mkey):
            return JSONResponse({"cancelled": False, "reason": "not_running"})
        cancel_event = ACTIVE_CHAT_CANCELS.get(_run_mkey)
        if cancel_event:
            cancel_event.set()
            with contextlib.suppress(Exception):
                await _broadcast_session_event(agent_id, session_id, {
                    "type": "chat_stop_requested",
                })
            return JSONResponse({"cancelled": True})
        return JSONResponse({"cancelled": False, "reason": "not_running"})

    # ---- Per-session model stack override (Session.metadata) ----
    # Stored keys on Session.metadata:
    #   llm_id, vision_llm_id, image_gen_llm_id,
    #   audio_llm_id, music_llm_id, video_gen_llm_id
    _MODEL_STACK_KEYS = (
        "llm_id",
        "vision_llm_id",
        "image_gen_llm_id",
        "audio_llm_id",
        "music_llm_id",
        "video_gen_llm_id",
    )

    def _read_model_stack_from_metadata(metadata):
        if not isinstance(metadata, dict):
            return {}
        out = {}
        for k in _MODEL_STACK_KEYS:
            v = metadata.get(k)
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()
        return out

    def _resolve_session_agent_id(body):
        from codeagent.core import env as ca_env
        return (
            str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
        )

    async def api_session_model_stack_get(request: Request) -> JSONResponse:
        """GET /api/ui/session/model-stack?session_id=...&agent_id=...

        Returns the per-session model overrides stored in Session.metadata.
        Empty fields mean "use the global default".
        """
        from seed.core.llm_sess import load_or_create_chat_session
        try:
            body = dict(request.query_params)
        except Exception:
            body = {}
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse({"detail": "session_id required"}, status_code=400)
        agent_id = _resolve_session_agent_id(body)
        chat_sess = load_or_create_chat_session(session_id, agent_id)
        overrides = _read_model_stack_from_metadata(chat_sess.metadata)
        return JSONResponse(
            {"ok": True, "session_id": session_id, "agent_id": agent_id, "overrides": overrides}
        )

    async def api_session_model_stack_set(request: Request) -> JSONResponse:
        """POST /api/ui/session/model-stack

        Body: {"session_id": "...", "agent_id": "...", "overrides": {<key>: <preset_id|"" >, ...}}

        Empty string or null for a key clears that override (back to global default).
        Unknown keys are ignored. Returns the persisted overrides.
        """
        from seed.core.llm_sess import load_or_create_chat_session, persist_chat_session
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse({"detail": "session_id required"}, status_code=400)
        agent_id = _resolve_session_agent_id(body)
        overrides_in = body.get("overrides")
        if not isinstance(overrides_in, dict):
            return JSONResponse({"detail": "overrides must be an object"}, status_code=400)
        # Running sessions must be stopped first (consistency with rollback endpoint)
        from . import _running_contains, _memkey
        if _running_contains(_memkey(agent_id, session_id)):
            return JSONResponse(
                {"detail": "session is currently running, stop it first"}, status_code=409
            )
        chat_sess = load_or_create_chat_session(session_id, agent_id)
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        for k in _MODEL_STACK_KEYS:
            if k not in overrides_in:
                continue
            v = overrides_in.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                chat_sess.metadata.pop(k, None)
            else:
                chat_sess.metadata[k] = str(v).strip()
        persist_chat_session(chat_sess, agent_id)
        persisted = _read_model_stack_from_metadata(chat_sess.metadata)
        return JSONResponse(
            {"ok": True, "session_id": session_id, "agent_id": agent_id, "overrides": persisted}
        )

    async def api_session_model_stack_clear(request: Request) -> JSONResponse:
        """POST /api/ui/session/model-stack/clear — convenience: remove all 6 overrides."""
        from seed.core.llm_sess import load_or_create_chat_session, persist_chat_session
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse({"detail": "session_id required"}, status_code=400)
        agent_id = _resolve_session_agent_id(body)
        from . import _running_contains, _memkey
        if _running_contains(_memkey(agent_id, session_id)):
            return JSONResponse(
                {"detail": "session is currently running, stop it first"}, status_code=409
            )
        chat_sess = load_or_create_chat_session(session_id, agent_id)
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        for k in _MODEL_STACK_KEYS:
            chat_sess.metadata.pop(k, None)
        persist_chat_session(chat_sess, agent_id)
        return JSONResponse({"ok": True, "session_id": session_id, "agent_id": agent_id, "overrides": {}})

    async def api_compact_config_get(request: Request) -> JSONResponse:
        """GET /api/ui/compact-config — return current compact min tokens."""
        from seed.core.agent_runtime import _get_compact_min_tokens, _compact_min_tokens_override
        return JSONResponse({
            "compact_min_tokens": _get_compact_min_tokens(),
            "runtime_override": _compact_min_tokens_override,
        })

    async def api_compact_config_set(request: Request) -> JSONResponse:
        """POST /api/ui/compact-config — set compact min tokens at runtime."""
        from seed.core.agent_runtime import set_compact_min_tokens
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        val = body.get("compact_min_tokens")
        if val is None:
            return JSONResponse({"detail": "compact_min_tokens required"}, status_code=400)
        try:
            val = int(val)
        except (ValueError, TypeError):
            return JSONResponse({"detail": "compact_min_tokens must be integer"}, status_code=400)
        set_compact_min_tokens(val)
        return JSONResponse({"ok": True, "compact_min_tokens": max(0, val)})

    async def api_chat_rollback(request: Request) -> JSONResponse:
        """Roll back session to a given message index — subsequent turns will project from there.

        POST body::

            {"session_id": "...", "agent_id": "...", "message_idx": 42}

        Response::

            {"ok": true, "message_idx": 42, "messages_since": [<messages from idx onwards>]}
        """
        from seed.core.llm_sess import load_or_create_chat_session, persist_chat_session
        from . import _running_contains, _memkey

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)

        session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
        from codeagent.core import env as ca_env
        from seed.core.env_access import (
            CHAT_AUTO_CONTINUE_MAX_SEGMENTS,
            CHAT_AUTO_CONTINUE_ON_LIMIT,
            MAX_TOOL_ROUNDS,
            env_truthy,
            pick_int,
        )

        agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
        # 0 = system message, so minimal sensible value is 1
        message_idx = int(body.get("message_idx", 1))

        _run_mkey = _memkey(agent_id, session_id)
        if _running_contains(_run_mkey):
            return JSONResponse({"detail": "session is currently running, stop it first"}, status_code=409)

        chat_sess = load_or_create_chat_session(session_id, agent_id)

        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}

        # Clamp to valid range
        max_idx = len(chat_sess.messages) - 1
        if message_idx < 0:
            message_idx = 0
        if message_idx > max_idx:
            return JSONResponse(
                {"detail": f"message_idx {message_idx} out of range (max {max_idx})"},
                status_code=422,
            )

        chat_sess.metadata["cursor"] = {
            "mode": "head",
            "from_idx": message_idx,
        }
        chat_sess.metadata.pop("vision_context", None)
        persist_chat_session(chat_sess, agent_id)

        # Broadcast rollback event via websocket
        try:
            await _broadcast_session_event(agent_id, session_id, {
                "type": "rollback",
                "message_idx": message_idx,
            })
        except Exception:
            pass

        # Return messages from rollback point for UI refresh
        messages_since = chat_sess.messages[message_idx:]
        return JSONResponse({
            "ok": True,
            "message_idx": message_idx,
            "messages_since": messages_since,
        })

    def _resolve_site_icon_path() -> Path | None:
        """``icon.png`` may live next to the ``codeagent`` package, inside ``server/``, or at the repo root."""
        pkg_root = Path(__file__).resolve().parent.parent
        for candidate in (
            pkg_root / "server" / "icon.png",   # shipped with the package
            pkg_root / "icon.png",               # next to the codeagent package
            pkg_root.parent / "icon.png",        # at the repo / project root
        ):
            if candidate.is_file():
                return candidate
        return None

    async def icon_png(_: Request) -> Response:
        p = _resolve_site_icon_path()
        if p is None:
            return Response(status_code=404)
        return Response(content=p.read_bytes(), media_type="image/png")

    async def favicon_ico(_: Request) -> Response:
        """Browsers default to /favicon.ico; serve same PNG as /icon.png."""
        p = _resolve_site_icon_path()
        if p is None:
            return Response(status_code=404)
        return Response(
            content=p.read_bytes(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def websocket_chat(websocket: WebSocket) -> None:
        await websocket.accept()
        sid = (websocket.query_params.get("session_id") or "").strip()
        aid = (websocket.query_params.get("agent_id") or "").strip() or "default"
        if sid:
            mkey = _memkey(aid, sid)
            ws_by_session[mkey].add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            if sid:
                ws_by_session[mkey].discard(websocket)

    middleware: list[Any] = []
    tok = get_webui_token(project_root)
    if tok:
        middleware.append(Middleware(WebUIAuthMiddleware, project_root=project_root))

    # ── Cron 执行：复用 WebUI 消息口（run_chat_turn） ──
    # seed 只负责"何时触发"（crontab 解析/防重入）；执行走 codeagent 的 chat
    # 管道，cron 获得与 WebUI 一致的 running 状态、消息注入（插话）、可停止、
    # 上下文压缩与持久化。通过 seed 的 register_cron_job_handler 单向注入
    # （seed 不反向依赖 codeagent）。
    async def _cron_run_via_chat_turn(job: dict) -> dict:
        from codeagent.server.chat_turn import run_chat_turn
        from datetime import datetime, timezone

        jid = str(job.get("id") or "").strip() or "cron-job"
        agent_id = str(job.get("agent_id") or "").strip() or "default"
        sid = str(job.get("session_id") or "").strip() or f"cron-{jid}"
        prompt = str(job.get("prompt") or "").strip()
        if not prompt:
            return {"skipped": True, "reason": "empty_prompt"}
        max_rounds_raw = job.get("max_tool_rounds")
        try:
            max_rounds = (
                max(1, int(max_rounds_raw)) if max_rounds_raw is not None else None
            )
        except (TypeError, ValueError):
            max_rounds = None
        user_msg = {
            "role": "user",
            "content": f"[cron:{jid}] {prompt}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        return await run_chat_turn(
            agent_id=agent_id,
            session_id=sid,
            user_msg=user_msg,
            project_id=str(job.get("project_id") or "").strip() or "",
            max_tool_rounds=max_rounds,
            channel="Cron",
            source=f"cron:{jid}",
            refresh_title=False,
            log_diary=False,
            emit_ws=True,
            broadcast_fn=_broadcast_session_event,
            if_busy="skip",
        )

    # ── Cron：Starlette 1.x 用 lifespan（on_startup 已移除）；且 AsyncIOScheduler 需要已有运行中的 loop ──
    @asynccontextmanager
    async def _lifespan(_app: Starlette):
        # 兼容旧版 seed：register_main_loop 是 v1.0.8+ 才有的线程安全 reload 前置；
        # 缺失时降级（reload 走自身线程的 loop，仍可用），但绝不因 ImportError 吞掉整个调度器。
        try:
            from seed.integrations import cron_sched as _cron_sched

            _register_main_loop = getattr(_cron_sched, "register_main_loop", None)
            _start_cron_scheduler = getattr(_cron_sched, "start_cron_scheduler", None)
            if _start_cron_scheduler is None:
                logger.error(
                    "cron: installed seed (%s) too old — no start_cron_scheduler; "
                    "scheduled jobs will not run",
                    getattr(_cron_sched, "__file__", "?"),
                )
            else:
                if _register_main_loop is not None:
                    try:
                        # 记录主事件循环：让 worker 线程（agent 工具环境）也能安全触发 cron reload
                        _register_main_loop()
                    except Exception as exc:
                        logger.warning("cron: register_main_loop failed: %s", exc)
                # cron 复用 WebUI 消息口：注入 run_chat_turn handler
                # （seed 无 register_cron_job_handler 时降级为内置实现）
                try:
                    _register_handler = getattr(
                        _cron_sched, "register_cron_job_handler", None
                    )
                    if _register_handler is not None:
                        _register_handler(_cron_run_via_chat_turn)
                except Exception as exc:
                    logger.warning("cron: register_cron_job_handler failed: %s", exc)
                try:
                    _start_cron_scheduler()
                except Exception as exc:
                    logger.exception("cron scheduler startup failed: %s", exc)
        except Exception as exc:
            logger.exception("cron scheduler startup failed: %s", exc)
        yield
        try:
            from seed.core._session_cache import cancel_all_active_chats

            n = cancel_all_active_chats()
            if n:
                logger.info("shutdown: signalled %s active chat(s) to stop", n)
        except Exception:
            pass
        try:
            from seed.integrations.cron_sched import shutdown_cron_scheduler

            shutdown_cron_scheduler()
        except Exception:
            pass

    from codeagent.server.attachment_api import (
        api_attachment_batch,
        api_attachment_get,
        api_attachment_upload,
        api_file_serve,
    )
    from codeagent.server.tts_api import api_tts

    routes = [
        Route("/", homepage),
        Route("/setup", setup_page),
        Route("/health", health),
        Route("/api/health", health),
        Route("/icon.png", icon_png),
        Route("/favicon.ico", favicon_ico),
        # NOTE: routes under /api/ui/session/model-stack must be registered
        # BEFORE the /api/ui Mount, otherwise Starlette will dispatch them
        # to build_webui_api_app first.
        Route(
            "/api/ui/session/model-stack",
            api_session_model_stack_get,
            methods=["GET"],
        ),
        Route(
            "/api/ui/session/model-stack",
            api_session_model_stack_set,
            methods=["POST"],
        ),
        Route(
            "/api/ui/session/model-stack/clear",
            api_session_model_stack_clear,
            methods=["POST"],
        ),
        Route(
            "/api/ui/compact-config",
            api_compact_config_get,
            methods=["GET"],
        ),
        Route(
            "/api/ui/compact-config",
            api_compact_config_set,
            methods=["POST"],
        ),
        Mount("/api/ui", app=build_webui_api_app(project_root)),
        Route("/api/attachments", api_attachment_upload, methods=["POST"]),
        Route("/api/attachments/batch", api_attachment_batch, methods=["POST"]),
        Route("/api/attachments/{attachment_id}", api_attachment_get, methods=["GET"]),
        Route("/api/file-serve", api_file_serve, methods=["GET"]),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/chat/stop", api_chat_stop, methods=["POST"]),
        Route("/api/chat/rollback", api_chat_rollback, methods=["POST"]),
        Route("/api/tts", api_tts, methods=["POST"]),
        WebSocketRoute("/ws", websocket_chat),
        WebSocketRoute("/ws/{path:path}", websocket_chat),
    ]

    return Starlette(debug=False, routes=routes, middleware=middleware, lifespan=_lifespan)
