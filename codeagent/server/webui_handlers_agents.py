"""Web UI agent-management endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. Handlers need ``project_root`` (via factory). Agent/team
metadata helpers come from ``webui_handlers_agentmeta``. ``_sanitize_agent_id``
and ``tools_for_agent`` are imported lazily inside handlers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from seed.core.llm_sess import list_stored_sessions_meta

from .webui_handlers_agentmeta import (
    _agents_dir,
    _list_agent_metas,
    _read_agent_file,
    _write_agent_file,
)

logger = logging.getLogger(__name__)


def build_agents_routes(project_root: Path) -> list[Route]:
    """Return the agent-management routes for ``webui_api_app``."""

    async def api_agent_presets(_: Request) -> JSONResponse:
        """Return predefined agent template presets."""
        presets = [
            {
                "id": "translator",
                "name": "译员",
                "description": "中英翻译，只输出翻译结果",
                "system_prompt": "翻译中文到英文，只输出翻译",
                "tools": {"acquired": {"allow": []}},
            },
            {
                "id": "summarizer",
                "name": "总结师",
                "description": "总结长文本，提取关键信息",
                "system_prompt": "请总结以下内容，提取关键信息，输出简洁的总结。",
                "tools": {"acquired": {"allow": []}},
            },
            {
                "id": "polisher",
                "name": "润色师",
                "description": "润色文本，优化表达",
                "system_prompt": "请润色以下文本，优化表达，保持原意。",
                "tools": {"acquired": {"allow": []}},
            },
            {
                "id": "code-reviewer",
                "name": "代码审查专家",
                "description": "审查代码安全性、性能、正确性",
                "system_prompt": "你是严格的代码审查专家。检查安全性（SQL注入/XSS/路径遍历）、性能（N+1查询/内存泄漏）、命名一致性、错误处理完整性。只输出需要修改的具体点。",
                "tools": {"acquired": {"allow": ["file_read", "code_check"]}},
            },
            {
                "id": "data-analyst",
                "name": "数据分析师",
                "description": "分析数据并生成报告",
                "system_prompt": "你是一名数据分析师。分析用户提供的数据，发现规律和异常，生成结构化报告。",
                "tools": {"acquired": {"allow": ["db", "file_read", "code_check"]}},
            },
            {
                "id": "debugger",
                "name": "调试专家",
                "description": "诊断代码问题，定位根因",
                "system_prompt": "你是调试专家。分析错误信息、日志和代码上下文，定位根因并给出修复方案。",
                "tools": {"acquired": {"allow": ["file_read", "bash", "grep"]}},
            },
        ]
        return JSONResponse({"presets": presets})

    async def api_agents_list(request: Request) -> JSONResponse:
        agents = _list_agent_metas(project_root)
        return JSONResponse({"agents": agents})

    async def api_tools_available(_: Request) -> JSONResponse:
        """Return all available tool names from the runtime."""
        try:
            from codeagent.server import tools_for_agent
            reg, _ = tools_for_agent("default")
            tools = sorted(t.name for t in reg.list_all())
        except Exception:
            tools = [
                "file_read", "file_write", "file_edit", "bash",
                "web_fetch", "web_search", "code_check", "code_analyze",
                "grep", "glob", "file_search",
                "db", "git", "todo", "tool_search",
                "memory_search", "self_reflect", "notebook_edit",
                "project", "refactor", "scaffold", "test_gen", "test_run",
                "symbol_search", "symbol_index_refresh",
                "lsp_definition", "lsp_diagnostics",
                "apply_patch", "deploy", "deps_check", "api_docs", "diagram", "pipeline",
                "browser_status", "browser_connect", "browser_ensure_running",
                "browser_targets", "browser_new_page", "browser_navigate", "browser_screenshot",
                "vision_analyze", "vision_analyze_directory",
                "image_generate", "music_generate", "video_generate",
                "attachment_resolve_path", "audio_transcribe", "video_analyze",
                "mcp_servers", "mcp_list_tools", "mcp_call", "mcp_list_skills", "mcp_skill",
                "seed_cron_path", "seed_cron_reload", "seed_cron_apply",
                "hub_send", "instruction_read",
                "whoami", "calculate", "counter", "workspace_verify",
                "wbs_draft",
            ]
        return JSONResponse({"tools": tools})

    async def api_agents_create(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        agent_id = (body.get("id") or "").strip()
        if not agent_id:
            return JSONResponse({"detail": "agent id is required"}, status_code=400)
        from codeagent.core.paths import _sanitize_agent_id
        safe_id = _sanitize_agent_id(agent_id)
        if not safe_id:
            return JSONResponse({"detail": "invalid agent id"}, status_code=400)
        agent_id = safe_id
        # Check for conflict
        ad = _agents_dir(project_root)
        if (ad / agent_id).exists():
            return JSONResponse({"detail": f"agent '{agent_id}' already exists"}, status_code=409)
        # Create agent scaffolding
        from codeagent.core.paths import ensure_agent_scaffold
        ensure_agent_scaffold(agent_id, base=project_root)
        # Write description if provided
        desc = (body.get("description") or "").strip()
        if desc:
            (ad / agent_id / "description.txt").write_text(desc, encoding="utf-8")
        # Write system prompt if provided
        sp = (body.get("system_prompt") or "").strip()
        if sp:
            _write_agent_file(agent_id, sp, "persona", "system.md", project_root=project_root)
        # Write tools if provided
        tools = body.get("tools")
        if tools is not None:
            tools_file = ad / agent_id / "tools.json"
            tools_file.write_text(json.dumps(tools, indent=2, ensure_ascii=False), encoding="utf-8")
        # 让新 agent 立即可被 chat 团队工具调用（call_agent/dispatch/parallel）
        try:
            from codeagent.runtime.agent_bootstrap import register_disk_agents

            register_disk_agents(
                agent_ids=[agent_id], overwrite=True, project_root=project_root
            )
        except Exception:
            logger.warning("failed to register new agent '%s' in AgentRegistry", agent_id, exc_info=True)
        return JSONResponse({"agent": {"id": agent_id, "name": agent_id}}, status_code=201)

    async def api_agents_get(request: Request) -> JSONResponse:
        agent_id = request.path_params.get("agent_id", "")
        ad = _agents_dir(project_root) / agent_id
        if not ad.is_dir() or not (ad / "persona").is_dir():
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        desc_file = ad / "description.txt"
        description = desc_file.read_text(encoding="utf-8").strip() if desc_file.is_file() else ""
        system_prompt = _read_agent_file(agent_id, "persona", "system.md", project_root=project_root) or ""
        tools_raw = _read_agent_file(agent_id, "tools.json", project_root=project_root)
        tools = {}
        tools_configured = False
        if tools_raw:
            try:
                tools = json.loads(tools_raw)
                tools_configured = True
            except json.JSONDecodeError:
                tools = {}
        return JSONResponse({
            "agent": {
                "id": agent_id,
                "name": agent_id,
                "description": description,
                "system_prompt": system_prompt,
                "tools": tools,
                "tools_configured": tools_configured,
            }
        })

    async def api_agents_update(request: Request) -> JSONResponse:
        agent_id = request.path_params.get("agent_id", "")
        from codeagent.core.paths import _sanitize_agent_id
        safe_id = _sanitize_agent_id(agent_id)
        if not safe_id:
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        ad = _agents_dir(project_root) / safe_id
        if not ad.is_dir() or not (ad / "persona").is_dir():
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        # Update system prompt
        if "system_prompt" in body:
            sp = (body["system_prompt"] or "").strip()
            _write_agent_file(safe_id, sp, "persona", "system.md", project_root=project_root)
        # Update description
        if "description" in body:
            desc = (body["description"] or "").strip()
            desc_file = ad / "description.txt"
            if desc:
                desc_file.write_text(desc, encoding="utf-8")
            else:
                desc_file.unlink(missing_ok=True)
        # Update tools
        if "tools" in body:
            tools = body["tools"]
            tools_file = ad / "tools.json"
            if tools:
                tools_file.write_text(json.dumps(tools, indent=2, ensure_ascii=False), encoding="utf-8")
            else:
                tools_file.unlink(missing_ok=True)
        return JSONResponse({"agent": {"id": safe_id, "name": safe_id}})

    async def api_agents_delete(request: Request) -> JSONResponse:
        agent_id = request.path_params.get("agent_id", "")
        from codeagent.core.paths import _sanitize_agent_id
        safe_id = _sanitize_agent_id(agent_id)
        if not safe_id:
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        ad = _agents_dir(project_root) / safe_id
        if not ad.is_dir():
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        # Cannot delete default agent
        if safe_id == "default":
            return JSONResponse({"detail": "cannot delete default agent"}, status_code=403)
        # Recursive delete
        import shutil
        shutil.rmtree(ad, ignore_errors=True)
        return JSONResponse({"detail": "deleted"})

    async def api_agents_sessions(request: Request) -> JSONResponse:
        """Return sessions for a specific agent."""
        agent_id = request.path_params.get("agent_id", "")
        ad = _agents_dir(project_root) / agent_id
        if not ad.is_dir() or not (ad / "persona").is_dir():
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        try:
            lim = int(request.query_params.get("limit") or "40")
        except ValueError:
            lim = 40
        rows = list_stored_sessions_meta(limit=lim, agent_id=agent_id, filter_by_project=False)
        return JSONResponse({"sessions": rows, "agent_id": agent_id})

    async def api_agents_switch(request: Request) -> JSONResponse:
        """Switch active agent. Validates the agent exists, returns its info + sessions."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        target = (body.get("agent_id") or "").strip()
        if not target:
            return JSONResponse({"detail": "agent_id is required"}, status_code=400)
        ad = _agents_dir(project_root) / target
        if not ad.is_dir() or not (ad / "persona").is_dir():
            return JSONResponse({"detail": f"agent '{target}' not found"}, status_code=404)
        system_prompt = _read_agent_file(target, "persona", "system.md", project_root=project_root) or ""
        tools_raw = _read_agent_file(target, "tools.json", project_root=project_root)
        tools = {}
        if tools_raw:
            try:
                tools = json.loads(tools_raw)
            except json.JSONDecodeError:
                tools = {}
        rows = list_stored_sessions_meta(limit=20, agent_id=target, filter_by_project=False)
        return JSONResponse({
            "agent": {"id": target, "name": target, "system_prompt": system_prompt, "tools": tools},
            "sessions": rows,
        })

    # ── Hub SSE ─────────────────────────────────────────────────



    return [
        Route("/agent-presets", api_agent_presets, methods=["GET"]),
        Route("/agents", api_agents_list, methods=["GET"]),
        Route("/agents", api_agents_create, methods=["POST"]),
        Route("/agents/{agent_id}", api_agents_get, methods=["GET"]),
        Route("/agents/{agent_id}", api_agents_update, methods=["PUT"]),
        Route("/agents/{agent_id}", api_agents_delete, methods=["DELETE"]),
        Route("/agents/{agent_id}/sessions", api_agents_sessions, methods=["GET"]),
        Route("/session/switch-agent", api_agents_switch, methods=["POST"]),
        Route("/tools/available", api_tools_available, methods=["GET"]),
    ]
