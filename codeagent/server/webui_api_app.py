"""Mounted at ``/api/ui`` — implements Web UI ``fetch('/api/ui/...')`` endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)


def _default_agent_id() -> str:
    from codeagent.core import env as ca_env

    return ca_env.default_agent_id()


def _json_default_history(o: Any) -> Any:
    """Best-effort encoder for session history payloads (tool_trace may hold bytes, sets, etc.)."""
    if isinstance(o, bytes):
        return o.decode("utf-8", errors="replace")
    if isinstance(o, (set, frozenset)):
        return list(o)
    return str(o)


def _history_payload_json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Round-trip through JSON so Starlette JSONResponse never raises TypeError."""
    try:
        return json.loads(json.dumps(payload, default=_json_default_history))
    except (TypeError, ValueError) as e:
        logger.warning("session history JSON sanitize fallback: %s", e)
        return json.loads(json.dumps(payload, default=str))


# 左侧栏「未分类」虚拟项目 ID
_UNASSIGNED_PROJECT_ID = "__unassigned__"

def _env_chat_specs() -> list[tuple[tuple[str, ...], str]]:
    from codeagent.core import env as ca_env

    return [
        ((ca_env.CHAT_AUTO_CONTINUE_ON_LIMIT,), "0"),
        ((ca_env.CHAT_AUTO_CONTINUE_MAX_SEGMENTS,), "4"),
        ((ca_env.CHAT_MAX_TOOL_ROUNDS_DEFAULT,), "16"),
        ((ca_env.CONTEXT_COMPACT,), ""),
        ((ca_env.CONTEXT_COMPACT_MIN_TOKENS,), "30000"),
        ((ca_env.CONTEXT_COMPACT_KEEP_USER_ROUNDS,), "2"),
        ((ca_env.CONTEXT_COMPACT_MID_LOOP,), "1"),
        ((ca_env.CONTEXT_COMPACT_ADAPTIVE_KEEP,), "0"),
        ((ca_env.CONTEXT_COMPACT_SUMMARIZER_PROMPT_FILE,), ""),
        ((ca_env.CONTEXT_COMPACT_SUMMARIZER_BASEURL,), ""),
        ((ca_env.CONTEXT_COMPACT_SUMMARIZER_MODEL,), ""),
        ((ca_env.CONTEXT_COMPACT_SUMMARIZER_MAX_TOKENS,), "4096"),
        ((ca_env.CHAT_MAX_TOKENS,), "8192"),
    ]


def _allowlist_path(root: Path) -> Path:
    return root / "config" / "codeagent.allowlist.json"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def _write_env_file_merge(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cur = _parse_env_file(path)
    cur.update(updates)
    lines = [f"{k}={v}" for k, v in sorted(cur.items())]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _resolve_env_value(keys: tuple[str, ...], file_vals: dict[str, str], default: str) -> str:
    for k in keys:
        if k in os.environ:
            return os.environ[k]
    for k in keys:
        if k in file_vals:
            return file_vals[k]
    return default


def _env_view_from_specs(root: Path, specs: list[tuple[tuple[str, ...], str]]) -> dict[str, str]:
    """按 specs（env key→默认值）构造 env 配置视图。

    读取 legacy 与当前 env 文件（后者优先），再按 _resolve_env_value
    （os.environ 优先）解析每个 key。env_chat 与 env_mcp 共用。
    """
    from seed.integrations.env_config import ENV_FILENAME, LEGACY_ENV_FILENAME

    p_seed = root / "config" / ENV_FILENAME
    p_leg = root / "config" / LEGACY_ENV_FILENAME
    file_vals = dict(_parse_env_file(p_leg))
    file_vals.update(_parse_env_file(p_seed))
    out: dict[str, str] = {}
    for keys, default in specs:
        val = _resolve_env_value(keys, file_vals, default)
        for k in keys:
            out[k] = val
    return out


def _env_chat_view(root: Path) -> dict[str, str]:
    return _env_view_from_specs(root, _env_chat_specs())


def _safe_under(base: Path, rel: str) -> Path | None:
    rel = (rel or "").strip().lstrip("/").replace("\\", "/")
    if not rel or ".." in Path(rel).parts:
        return None
    try:
        cand = (base / rel).resolve()
        base_r = base.resolve()
        if cand == base_r or base_r in cand.parents:
            return cand
    except OSError:
        return None
    return None


def _resolve_project_id(pid: str) -> str:
    """将 ``__unassigned__`` 映射为空字符串，其余原样返回。"""
    return "" if pid == _UNASSIGNED_PROJECT_ID else pid


def _project_fs_dir(agent_id: str, project_id: str) -> Path | None:
    from seed.core.proj_reg import resolve_project_path

    pid = _resolve_project_id(project_id)
    if not pid:
        return None
    raw = resolve_project_path(agent_id, pid)
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def _locate_session_file(
    handle: str,
    agent_id: str,
    project_id_hint: str,
) -> Path | None:
    from seed.core.llm_sess import _find_session_file
    from seed.core.proj_reg import list_projects

    if project_id_hint:
        p = _find_session_file(handle, agent_id, project_id_hint)
        if p is not None:
            return p
    p = _find_session_file(handle, agent_id, None)
    if p is not None:
        return p
    for proj in list_projects(agent_id):
        pid = str(proj.get("id") or "").strip()
        if not pid:
            continue
        p = _find_session_file(handle, agent_id, pid)
        if p is not None:
            return p
    return None


async def _llm_probe_response(body: dict[str, Any]) -> JSONResponse:
    base = str(body.get("base_url") or "").rstrip("/")
    model = str(body.get("model") or "").strip()
    key = str(body.get("api_key") or "").strip()
    scheme = str(body.get("auth_scheme") or "Bearer").strip() or "Bearer"
    if not base:
        return JSONResponse({"detail": "base_url required"}, status_code=400)
    if not (base.startswith("http://") or base.startswith("https://")):
        return JSONResponse({"detail": "base_url must be an http(s) URL"}, status_code=400)

    def probe() -> tuple[bool, str]:
        url = base + "/models"
        req = urllib.request.Request(url, method="GET")
        if key and scheme.lower() != "none":
            req.add_header("Authorization", f"{scheme} {key}".strip())
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return True, raw[:500]
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code}: {(e.read() or b'').decode('utf-8', errors='replace')[:400]}"
        except Exception as e:
            return False, str(e)

    ok, hint = await asyncio.to_thread(probe)
    if not ok:
        return JSONResponse({"detail": hint}, status_code=502)
    return JSONResponse({"ok": True, "model_hint": f"连通性正常（{model or 'model'}）"})


def _archive_session_path(path: Path) -> bool:
    arch = path.parent / "archived"
    try:
        arch.mkdir(parents=True, exist_ok=True)
        dest = arch / path.name
        if dest.is_file():
            dest.unlink()
        path.replace(dest)
        return True
    except OSError:
        return False


def _session_history_json_for_session(
    sess: Any,
    before_block_index: int | None,
) -> dict[str, Any]:
    from codeagent.core import env as ca_env

    from . import (
        _webui_history_partition_user_blocks,
        _webui_history_rows_from_session,
    )

    max_chars = ca_env.pick_int(12000, ca_env.WEBUI_SESSION_HISTORY_MAX_CHARS)
    max_blocks = ca_env.pick_int(10, ca_env.WEBUI_SESSION_HISTORY_USER_BLOCKS)
    max_blocks = max(1, min(max_blocks, 200))

    rows = _webui_history_rows_from_session(sess, max_chars)
    blocks = _webui_history_partition_user_blocks(rows)
    n = len(blocks)
    if n == 0:
        return {
            "messages": [],
            "first_block_index": None,
            "has_more_older": False,
            "truncated_start": False,
        }

    if before_block_index is None:
        start = max(0, n - max_blocks)
        sel = blocks[start:]
        first_idx = start
        has_more = start > 0
        truncated_start = has_more
    else:
        bi = max(0, int(before_block_index))
        start = max(0, bi - max_blocks)
        end = bi
        sel = blocks[start:end]
        first_idx = start
        has_more = start > 0
        truncated_start = has_more

    messages: list[dict[str, Any]] = []
    for b in sel:
        messages.extend(b)

    max_msg = ca_env.pick_int(300, ca_env.WEBUI_SESSION_HISTORY_MAX_MESSAGES)
    max_msg = max(10, min(max_msg, 5000))
    if len(messages) > max_msg:
        messages = messages[-max_msg:]

    return _history_payload_json_safe(
        {
            "messages": messages,
            "first_block_index": first_idx,
            "has_more_older": has_more,
            "truncated_start": truncated_start,
            "accumulated_usage": (
                sess.metadata.get("accumulated_usage")
                if isinstance(sess.metadata, dict)
                else None
            ),
            "context_usage": (
                sess.metadata.get("context_usage")
                if isinstance(sess.metadata, dict)
                else None
            ),
        }
    )


def _parse_mcp_skill_slash_command(text: str) -> tuple[str, str, str]:
    raw = str(text or "").strip()
    if raw.startswith("/skill"):
        rest = raw[len("/skill"):].strip()
        if not rest:
            raise ValueError("usage: /skill <server_id> <skill_name> [json_arguments]")
        parts = rest.split(None, 2)
        if len(parts) == 1 and "/" in parts[0]:
            server_id, _, skill_name = parts[0].partition("/")
            args = "{}"
        elif len(parts) >= 2:
            server_id = parts[0]
            skill_name = parts[1]
            args = parts[2].strip() if len(parts) > 2 else "{}"
        else:
            raise ValueError("usage: /skill <server_id> <skill_name> [json_arguments]")
    elif raw.startswith("/") and ":" in raw:
        head, _, tail = raw[1:].partition(":")
        server_id = head.strip()
        skill_part, _, arg_part = tail.strip().partition(" ")
        skill_name = skill_part.strip()
        args = arg_part.strip() or "{}"
    else:
        raise ValueError("usage: /<server_id>:<skill_name> [json_arguments]")
    server_id = server_id.strip()
    skill_name = skill_name.strip()
    if not server_id or not skill_name:
        raise ValueError("server_id and skill_name are required")
    return server_id, skill_name, args


def _agents_dir() -> Path:
    """Return the agents root directory (~/.codeagent/agents)."""
    from codeagent.core.paths import codeagent_home
    return codeagent_home() / "agents"


def _list_agent_metas() -> list[dict]:
    """Scan all agents on the filesystem and return metadata list."""
    ad = _agents_dir()
    if not ad.is_dir():
        return []
    agents: list[dict] = []
    for entry in sorted(ad.iterdir()):
        if not entry.is_dir():
            continue
        persona_dir = entry / "persona"
        if not persona_dir.is_dir():
            continue
        agent_id = entry.name
        # Read description
        desc_file = entry / "description.txt"
        description = desc_file.read_text(encoding="utf-8").strip() if desc_file.is_file() else ""
        # Read system prompt
        sys_file = persona_dir / "system.md"
        system_prompt = sys_file.read_text(encoding="utf-8") if sys_file.is_file() else ""
        # Read tools.json (runtime may fall back to "all tools" when absent)
        tools = {}
        tools_configured = False
        tools_file = entry / "tools.json"
        if tools_file.is_file():
            try:
                tools = json.loads(tools_file.read_text(encoding="utf-8"))
                tools_configured = True
            except (json.JSONDecodeError, OSError):
                tools = {}
        agents.append({
            "id": agent_id,
            "name": agent_id,
            "description": description,
            "system_prompt": system_prompt,
            "tools": tools,
            "tools_configured": tools_configured,
        })
    return agents


def _teams_dir() -> Path:
    """Return the teams root directory (~/.codeagent/teams)."""
    from codeagent.core.paths import codeagent_home
    return codeagent_home() / "teams"


def _list_team_metas() -> list[dict]:
    """Scan all teams and return metadata list."""
    td = _teams_dir()
    if not td.is_dir():
        return []
    teams: list[dict] = []
    for entry in sorted(td.iterdir()):
        if entry.suffix != ".json":
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            data["id"] = entry.stem
            teams.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return teams


def _read_agent_file(agent_id: str, *rel_parts: str) -> str | None:
    """Read a file inside an agent's directory if it exists.

    agent_id 用户可控，先净化防路径穿越（含 ../ 或 / 则拒绝）。
    """
    from codeagent.core.paths import _sanitize_agent_id

    safe_id = _sanitize_agent_id(agent_id)
    if not safe_id:
        return None
    p = _agents_dir() / safe_id
    for part in rel_parts:
        p = p / part
    try:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return None


def _write_agent_file(agent_id: str, content: str, *rel_parts: str) -> bool:
    """Write a file inside an agent's directory. Returns True on success.

    agent_id 用户可控，先净化防路径穿越（含 ../ 或 / 则拒绝）。
    """
    from codeagent.core.paths import _sanitize_agent_id

    safe_id = _sanitize_agent_id(agent_id)
    if not safe_id:
        return False
    p = _agents_dir() / safe_id
    for part in rel_parts:
        p = p / part
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


def build_webui_api_app(project_root: Path) -> Starlette:
    project_root = project_root.resolve()

    from seed.core.config_plane import ensure_default_config_files
    from seed.core.config_plane import project_root as project_root_fn
    from seed.core.llm_sess import (
        list_stored_sessions_meta,
    )

    from .webui_handlers_auth import build_auth_routes
    from .webui_handlers_cronallow import build_cronallow_routes
    from .webui_handlers_health import build_health_routes
    from .webui_handlers_envllm import build_envllm_routes
    from .webui_handlers_files import build_files_routes
    from .webui_handlers_git import build_git_routes
    from .webui_handlers_mcp import build_mcp_routes
    from .webui_handlers_projects import build_projects_routes
    from .webui_handlers_sessions import build_sessions_routes
    from .webui_handlers_skills import build_skills_routes

    ensure_default_config_files(project_root_fn())

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
        agents = _list_agent_metas()
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
        ad = _agents_dir()
        if (ad / agent_id).exists():
            return JSONResponse({"detail": f"agent '{agent_id}' already exists"}, status_code=409)
        # Create agent scaffolding
        from codeagent.core.paths import ensure_agent_scaffold
        ensure_agent_scaffold(agent_id)
        # Write description if provided
        desc = (body.get("description") or "").strip()
        if desc:
            (ad / agent_id / "description.txt").write_text(desc, encoding="utf-8")
        # Write system prompt if provided
        sp = (body.get("system_prompt") or "").strip()
        if sp:
            _write_agent_file(agent_id, sp, "persona", "system.md")
        # Write tools if provided
        tools = body.get("tools")
        if tools is not None:
            tools_file = ad / agent_id / "tools.json"
            tools_file.write_text(json.dumps(tools, indent=2, ensure_ascii=False), encoding="utf-8")
        return JSONResponse({"agent": {"id": agent_id, "name": agent_id}}, status_code=201)

    async def api_agents_get(request: Request) -> JSONResponse:
        agent_id = request.path_params.get("agent_id", "")
        ad = _agents_dir() / agent_id
        if not ad.is_dir() or not (ad / "persona").is_dir():
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        desc_file = ad / "description.txt"
        description = desc_file.read_text(encoding="utf-8").strip() if desc_file.is_file() else ""
        system_prompt = _read_agent_file(agent_id, "persona", "system.md") or ""
        tools_raw = _read_agent_file(agent_id, "tools.json")
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
        ad = _agents_dir() / safe_id
        if not ad.is_dir() or not (ad / "persona").is_dir():
            return JSONResponse({"detail": "agent not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        # Update system prompt
        if "system_prompt" in body:
            sp = (body["system_prompt"] or "").strip()
            _write_agent_file(safe_id, sp, "persona", "system.md")
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
        ad = _agents_dir() / safe_id
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
        ad = _agents_dir() / agent_id
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
        ad = _agents_dir() / target
        if not ad.is_dir() or not (ad / "persona").is_dir():
            return JSONResponse({"detail": f"agent '{target}' not found"}, status_code=404)
        system_prompt = _read_agent_file(target, "persona", "system.md") or ""
        tools_raw = _read_agent_file(target, "tools.json")
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

    async def api_hub_send(request: Request) -> JSONResponse:
        """POST /api/hub/send — send a message to the hub."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        frm = (body.get("frm") or body.get("from") or "").strip()
        to = (body.get("to") or "").strip()
        content = (body.get("content") or body.get("message") or "").strip()
        if not frm or not content:
            return JSONResponse({"detail": "frm and content are required"}, status_code=400)
        from codeagent.server.hub import send_message
        msg = send_message(frm, to or "all", content)
        return JSONResponse({"message": msg})

    async def api_hub_events(request: Request) -> JSONResponse:
        """GET /api/hub/events — SSE stream of hub messages."""
        last_event_id = (request.headers.get("last-event-id") or
                         request.query_params.get("lastEventId") or
                         request.query_params.get("last_id") or None)
        from codeagent.server.hub import sse_generator, subscribe
        sid, q = subscribe()
        logger.info("hub SSE subscriber %s connected (last_id=%s)", sid, last_event_id)
        return StreamingResponse(
            sse_generator(sid, q, last_event_id=last_event_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def api_hub_messages(request: Request) -> JSONResponse:
        """GET /api/hub/messages — list recent hub messages."""
        limit_s = request.query_params.get("limit", "50")
        try:
            limit = int(limit_s)
        except ValueError:
            limit = 50
        filter_agent = request.query_params.get("agent_id") or None
        from codeagent.server.hub import load_messages
        msgs = load_messages(limit=limit, filter_agent=filter_agent)
        return JSONResponse({"messages": msgs})

    # ── Team CRUD ───────────────────────────────────────────────

    async def api_teams_list(_: Request) -> JSONResponse:
        teams = _list_team_metas()
        return JSONResponse({"teams": teams})

    async def api_teams_create(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        team_id = (body.get("id") or "").strip()
        if not team_id:
            return JSONResponse({"detail": "team id is required"}, status_code=400)
        td = _teams_dir()
        team_file = td / f"{team_id}.json"
        if team_file.exists():
            return JSONResponse({"detail": f"team '{team_id}' already exists"}, status_code=409)
        team_data = {
            "name": body.get("name", team_id),
            "description": body.get("description", ""),
            "members": body.get("members", []),
            "manager_id": body.get("manager_id", ""),
            "mode": body.get("mode", "sequential"),
            "error_policy": body.get("error_policy", "stop"),
            "timeout_seconds": body.get("timeout_seconds", 300),
        }
        td.mkdir(parents=True, exist_ok=True)
        team_file.write_text(json.dumps(team_data, indent=2, ensure_ascii=False), encoding="utf-8")
        team_data["id"] = team_id
        return JSONResponse({"team": team_data}, status_code=201)

    async def api_teams_get(request: Request) -> JSONResponse:
        team_id = request.path_params.get("team_id", "")
        team_file = _teams_dir() / f"{team_id}.json"
        if not team_file.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        try:
            data = json.loads(team_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return JSONResponse({"detail": "invalid team data"}, status_code=500)
        data["id"] = team_id
        return JSONResponse({"team": data})

    async def api_teams_update(request: Request) -> JSONResponse:
        team_id = request.path_params.get("team_id", "")
        team_file = _teams_dir() / f"{team_id}.json"
        if not team_file.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        try:
            data = json.loads(team_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for k in ("name", "description", "members", "manager_id", "mode", "error_policy", "timeout_seconds"):
            if k in body:
                data[k] = body[k]
        team_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        data["id"] = team_id
        return JSONResponse({"team": data})

    async def api_teams_delete(request: Request) -> JSONResponse:
        team_id = request.path_params.get("team_id", "")
        team_file = _teams_dir() / f"{team_id}.json"
        if not team_file.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        team_file.unlink()
        return JSONResponse({"detail": "deleted"})

    # ── Team Run ────────────────────────────────────────────────

    async def api_teams_run(request: Request) -> JSONResponse:
        """Execute a team workflow asynchronously."""
        team_id = request.path_params.get("team_id", "")
        tf = _teams_dir() / f"{team_id}.json"
        if not tf.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        user_input = (body.get("input") or body.get("user_input") or "").strip()
        if not user_input:
            return JSONResponse({"detail": "input is required"}, status_code=400)
        try:
            from codeagent.server.team_engine import run_team
            run = run_team(team_id, user_input)
            return JSONResponse({"run": run})
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        except Exception as e:
            logger.exception("team run failed")
            return JSONResponse({"detail": f"run failed: {e}"}, status_code=500)

    async def api_runs_list(request: Request) -> JSONResponse:
        team_id = request.query_params.get("team_id", "")
        from codeagent.server.team_engine import list_runs
        runs = list_runs(team_id=team_id or None)
        return JSONResponse({"runs": runs})

    async def api_runs_get(request: Request) -> JSONResponse:
        run_id = request.path_params.get("run_id", "")
        from codeagent.server.team_engine import get_run
        run = get_run(run_id)
        if run is None:
            return JSONResponse({"detail": "run not found"}, status_code=404)
        return JSONResponse({"run": run})

    # ── Health / Watchdog ──────────────────────────────────────

    async def api_runs_recover(request: Request) -> JSONResponse:
        """POST /api/ui/runs/{run_id}/recover — mark a failed run for recovery."""
        run_id = request.path_params.get("run_id", "")
        from codeagent.server.team_engine import get_run, update_run
        run = get_run(run_id)
        if run is None:
            return JSONResponse({"detail": "run not found"}, status_code=404)
        if run.get("status") not in ("failed", "timeout"):
            return JSONResponse({"detail": "only failed/timeout runs can be recovered"}, status_code=400)
        update_run(run_id, {"status": "pending", "error": None})
        return JSONResponse({"detail": f"run {run_id} marked for recovery", "run": update_run(run_id, {})})

    # ── Routes ─────────────────────────────────────────────────

    routes = [
        *build_auth_routes(project_root),
        *build_mcp_routes(project_root),
        *build_skills_routes(project_root),
        *build_projects_routes(project_root),
        *build_sessions_routes(project_root),
        *build_envllm_routes(project_root),
        *build_cronallow_routes(project_root),
        *build_git_routes(project_root),
        *build_files_routes(project_root),
        # Agent CRUD
        Route("/agent-presets", api_agent_presets, methods=["GET"]),
        Route("/agents", api_agents_list, methods=["GET"]),
        Route("/agents", api_agents_create, methods=["POST"]),
        Route("/agents/{agent_id}", api_agents_get, methods=["GET"]),
        Route("/agents/{agent_id}", api_agents_update, methods=["PUT"]),
        Route("/agents/{agent_id}", api_agents_delete, methods=["DELETE"]),
        Route("/agents/{agent_id}/sessions", api_agents_sessions, methods=["GET"]),
        Route("/session/switch-agent", api_agents_switch, methods=["POST"]),
        Route("/tools/available", api_tools_available, methods=["GET"]),
        # Team CRUD
        Route("/teams", api_teams_list, methods=["GET"]),
        Route("/teams", api_teams_create, methods=["POST"]),
        Route("/teams/{team_id}", api_teams_get, methods=["GET"]),
        Route("/teams/{team_id}", api_teams_update, methods=["PUT"]),
        Route("/teams/{team_id}", api_teams_delete, methods=["DELETE"]),
        # Team Run
        Route("/teams/{team_id}/run", api_teams_run, methods=["POST"]),
        Route("/runs", api_runs_list, methods=["GET"]),
        Route("/runs/{run_id}", api_runs_get, methods=["GET"]),
        # Hub SSE
        Route("/hub/send", api_hub_send, methods=["POST"]),
        Route("/hub/events", api_hub_events, methods=["GET"]),
        Route("/hub/messages", api_hub_messages, methods=["GET"]),
        # Health / Watchdog
        *build_health_routes(),
        Route("/runs/{run_id}/recover", api_runs_recover, methods=["POST"]),
    ]

    return Starlette(debug=False, routes=routes)
