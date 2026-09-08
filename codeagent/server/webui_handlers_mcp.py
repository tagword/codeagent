"""Web UI integration-config endpoints (plugins / MCP / hooks / markdown docs).

Split out of ``webui_api_app``. Mounted at ``/api/ui`` (outer Mount adds prefix).

These handlers need ``project_root``, so they live behind a
``build_mcp_routes(project_root)`` factory that closes over it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from codeagent.core.settings import plugins_public_view, save_plugins_from_ui
from seed.core.config_plane import (
    CONFIG_FILENAMES,
    ensure_default_config_files,
)
from seed.core.config_plane import (
    project_root as project_root_fn,
)

logger = logging.getLogger(__name__)


def _default_agent_id() -> str:
    from codeagent.core import env as ca_env

    return ca_env.default_agent_id()


def build_mcp_routes(project_root: Path) -> list[Route]:
    """Return the plugins / MCP / hooks / markdown routes for ``webui_api_app``."""

    async def api_plugins_get(_: Request) -> JSONResponse:
        return JSONResponse(plugins_public_view())

    async def api_plugins_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        try:
            save_plugins_from_ui(body)
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return JSONResponse({"ok": True})

    async def api_mcp_get(_: Request) -> JSONResponse:
        import shutil

        from seed.integrations.mcp_client import get_mcp_manager, mcp_globally_enabled
        from seed.integrations.mcp_config import (
            MINIMAX_MCP_SERVER_ID,
            build_minimax_token_plan_mcp_server,
            load_mcp_config,
            mcp_config_path,
            minimax_mcp_output_dir,
        )

        # ⚡ 快速返回：不 probe，不阻塞。probe 由独立端点 /mcp/probe 异步处理
        try:
            status = get_mcp_manager().list_servers_status(probe=False)
        except Exception as e:
            logger.exception("api_mcp_get status")
            status = []
            err = str(e)
        else:
            err = None
        uvx = shutil.which("uvx") or ""
        from codeagent.core.image_understanding import image_understanding_status

        return JSONResponse(
            {
                "enabled": mcp_globally_enabled(),
                "path": str(mcp_config_path(project_root)),
                "config": load_mcp_config(project_root),
                "servers_status": status,
                "error": err,
                "minimax_server_id": MINIMAX_MCP_SERVER_ID,
                "minimax_output_dir": str(minimax_mcp_output_dir(project_root)),
                "minimax_template": build_minimax_token_plan_mcp_server(
                    api_key="",
                    base=project_root,
                    uvx_command=uvx or "uvx",
                ),
                "uvx_path": uvx,
                # probe=False：只判断"是否已配置"，不做连接探测
                "image_understanding": image_understanding_status(
                    project_root, probe=False, servers_status=status
                ),
            }
        )

    async def api_mcp_probe(_: Request) -> JSONResponse:
        """独立探测端点，不阻塞 WebUI 主加载流程。

        由前端在页面渲染完成后异步调用，更新 MCP 连接状态。
        asyncio.to_thread 防止同步阻塞 event loop。
        """
        import shutil

        from seed.integrations.mcp_client import get_mcp_manager, mcp_globally_enabled
        from seed.integrations.mcp_config import (
            MINIMAX_MCP_SERVER_ID,
            build_minimax_token_plan_mcp_server,
            load_mcp_config,
            mcp_config_path,
            minimax_mcp_output_dir,
        )

        try:
            status = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: get_mcp_manager().list_servers_status(probe=True)
                ),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.warning("api_mcp_probe timeout (>15s)")
            status = []
            err = "MCP 探测超时（>15s）"
        except Exception as e:
            logger.exception("api_mcp_probe error")
            status = []
            err = str(e)
        else:
            err = None

        uvx = shutil.which("uvx") or ""
        from codeagent.core.image_understanding import image_understanding_status

        return JSONResponse(
            {
                "enabled": mcp_globally_enabled(),
                "path": str(mcp_config_path(project_root)),
                "config": load_mcp_config(project_root),
                "servers_status": status,
                "error": err,
                "minimax_server_id": MINIMAX_MCP_SERVER_ID,
                "minimax_output_dir": str(minimax_mcp_output_dir(project_root)),
                "minimax_template": build_minimax_token_plan_mcp_server(
                    api_key="",
                    base=project_root,
                    uvx_command=uvx or "uvx",
                ),
                "uvx_path": uvx,
                "image_understanding": image_understanding_status(
                    project_root, probe=True, servers_status=status
                ),
            }
        )

    async def api_hooks_get(_: Request) -> JSONResponse:
        from seed.integrations.hooks import hooks_globally_enabled
        from seed.integrations.hooks_config import hooks_config_path, load_hooks_config

        return JSONResponse(
            {
                "enabled": hooks_globally_enabled(),
                "path": str(hooks_config_path(project_root)),
                "config": load_hooks_config(project_root),
            }
        )

    async def api_hooks_post(request: Request) -> JSONResponse:
        from seed.integrations.hooks_config import save_hooks_config

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        try:
            path = save_hooks_config(body, base=project_root)
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "path": str(path)})

    async def api_mcp_post(request: Request) -> JSONResponse:
        from seed.integrations.mcp_client import reset_mcp_manager
        from seed.integrations.mcp_config import save_mcp_config

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        servers = body.get("servers")
        if servers is None and isinstance(body.get("config"), dict):
            servers = body["config"].get("servers")
        if not isinstance(servers, dict):
            return JSONResponse({"detail": "servers object required"}, status_code=400)
        try:
            path = save_mcp_config({"servers": servers}, base=project_root)
            reset_mcp_manager()
            from codeagent.tools.agent_tools import reset_agent_tools_cache

            reset_agent_tools_cache()
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "path": str(path)})

    async def api_mcp_test(request: Request) -> JSONResponse:
        from seed.integrations.mcp_client import probe_mcp_server_config
        from seed.integrations.mcp_config import server_config_from_dict

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "invalid body"}, status_code=400)
        sid = str(body.get("id") or body.get("server_id") or "").strip()
        try:
            cfg = server_config_from_dict(sid, body)
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        if cfg.transport == "stdio" and not cfg.command:
            return JSONResponse({"detail": "command required"}, status_code=400)
        if cfg.transport == "sse" and not cfg.url:
            return JSONResponse({"detail": "url required"}, status_code=400)
        if cfg.transport == "streamable-http" and not cfg.url:
            return JSONResponse({"detail": "url required"}, status_code=400)
        result = probe_mcp_server_config(cfg)
        if not result.get("ok"):
            return JSONResponse(
                {"ok": False, "detail": result.get("error") or "probe failed"},
                status_code=502,
            )
        return JSONResponse({"ok": True, **result})

    async def api_mcp_skills(request: Request) -> JSONResponse:
        from seed.integrations.mcp_client import MCPError, get_mcp_manager

        sid = str(request.query_params.get("server_id") or "").strip()
        if not sid:
            return JSONResponse({"detail": "server_id required"}, status_code=400)
        try:
            skills = get_mcp_manager().get_session(sid).list_skills()
        except MCPError as e:
            return JSONResponse({"detail": str(e)}, status_code=502)
        return JSONResponse(
            {
                "server_id": sid,
                "skills": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "arguments": s.arguments,
                    }
                    for s in skills
                ],
            }
        )

    async def api_mcp_skill(request: Request) -> JSONResponse:
        from seed_tools.mcp import mcp_skill_handler

        # 延迟 import：_parse_mcp_skill_slash_command 定义于 webui_api_app（本模块被它 import），避免循环
        from codeagent.server.webui_api_app import _parse_mcp_skill_slash_command

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "invalid body"}, status_code=400)
        command = str(body.get("command") or "").strip()
        if command:
            try:
                sid, skill_name, args = _parse_mcp_skill_slash_command(command)
            except ValueError as e:
                return JSONResponse({"detail": str(e)}, status_code=400)
        else:
            sid = str(body.get("server_id") or "").strip()
            skill_name = str(body.get("skill_name") or body.get("name") or "").strip()
            raw_args = body.get("arguments", {})
            if isinstance(raw_args, str):
                args = raw_args.strip() or "{}"
            elif isinstance(raw_args, dict):
                args = json.dumps(raw_args, ensure_ascii=False)
            else:
                return JSONResponse({"detail": "arguments must be object or JSON string"}, status_code=400)
        if not sid or not skill_name:
            return JSONResponse({"detail": "server_id and skill_name required"}, status_code=400)
        result = await asyncio.to_thread(mcp_skill_handler, sid, skill_name, args)
        return JSONResponse(
            {
                "ok": True,
                "server_id": sid,
                "skill_name": skill_name,
                "result": result,
            }
        )

    async def api_md_get(request: Request) -> JSONResponse:
        name = (request.path_params.get("name") or "").strip()
        if name not in CONFIG_FILENAMES:
            return JSONResponse({"detail": "unknown file"}, status_code=404)
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        ensure_default_config_files(project_root_fn())
        try:
            from codeagent.core.paths import agent_persona_dir, ensure_agent_scaffold

            ensure_agent_scaffold(aid, base=project_root)
            path = agent_persona_dir(aid, base=project_root) / name
        except Exception:
            path = project_root / "config" / name
        if not path.is_file():
            return JSONResponse({"path": str(path), "content": "", "exists": False})
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return JSONResponse({"detail": "read failed"}, status_code=500)
        return JSONResponse({"path": str(path), "content": text, "exists": True})

    async def api_md_post(request: Request) -> JSONResponse:
        name = (request.path_params.get("name") or "").strip()
        if name not in CONFIG_FILENAMES:
            return JSONResponse({"detail": "unknown file"}, status_code=404)
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if mime == "application/json":
            try:
                body = await request.json()
            except json.JSONDecodeError:
                return JSONResponse(
                    {
                        "detail": "invalid json：请检查是否为合法 JSON，或改用纯文本保存（Web UI 已用 text/plain）。",
                    },
                    status_code=400,
                )
            except Exception:
                return JSONResponse({"detail": "invalid json body"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"detail": "JSON body must be an object"}, status_code=400)
            content = body.get("content")
            if not isinstance(content, str):
                return JSONResponse({"detail": "JSON 中缺少字符串字段 content"}, status_code=400)
        else:
            raw = await request.body()
            try:
                content = raw.decode("utf-8")
            except Exception:
                content = raw.decode("utf-8", errors="replace")
        ensure_default_config_files(project_root_fn())
        try:
            from codeagent.core.paths import agent_persona_dir, ensure_agent_scaffold

            ensure_agent_scaffold(aid, base=project_root)
            persona = agent_persona_dir(aid, base=project_root)
            persona.mkdir(parents=True, exist_ok=True)
            path = persona / name
        except Exception:
            cfg = project_root / "config"
            cfg.mkdir(parents=True, exist_ok=True)
            path = cfg / name
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return JSONResponse({"detail": str(e)}, status_code=500)
        return JSONResponse(
            {
                "ok": True,
                "path": str(path),
                "hint": "已写入磁盘；新对话或下一轮合并 system 时会使用该内容。",
            }
        )



    return [
        Route("/plugins", api_plugins_get, methods=["GET"]),
        Route("/plugins", api_plugins_post, methods=["POST"]),
        Route("/mcp", api_mcp_get, methods=["GET"]),
        Route("/mcp", api_mcp_post, methods=["POST"]),
        Route("/mcp/probe", api_mcp_probe, methods=["GET"]),
        Route("/mcp/test", api_mcp_test, methods=["POST"]),
        Route("/mcp/skills", api_mcp_skills, methods=["GET"]),
        Route("/mcp/skill", api_mcp_skill, methods=["POST"]),
        Route("/hooks", api_hooks_get, methods=["GET"]),
        Route("/hooks", api_hooks_post, methods=["POST"]),
        Route("/md/{name}", api_md_get, methods=["GET"]),
        Route("/md/{name}", api_md_post, methods=["POST"]),
    ]
