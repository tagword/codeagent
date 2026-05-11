"""Mounted at ``/api/ui`` — implements Web UI ``fetch('/api/ui/...')`` endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)


def _json_default_transcript(o: Any) -> Any:
    """Best-effort encoder for transcript payloads (tool_trace may hold bytes, sets, etc.)."""
    if isinstance(o, bytes):
        return o.decode("utf-8", errors="replace")
    if isinstance(o, (set, frozenset)):
        return list(o)
    return str(o)


def _transcript_payload_json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Round-trip through JSON so Starlette JSONResponse never raises TypeError."""
    try:
        return json.loads(json.dumps(payload, default=_json_default_transcript))
    except (TypeError, ValueError) as e:
        logger.warning("transcript JSON sanitize fallback: %s", e)
        return json.loads(json.dumps(payload, default=str))


# 左侧栏「未分类」虚拟项目 ID
_UNASSIGNED_PROJECT_ID = "__unassigned__"

_ENV_CHAT_KEYS = (
    "CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT",
    "CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS",
    "CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT",
    "CODEAGENT_CONTEXT_COMPACT",
    "CODEAGENT_CONTEXT_COMPACT_MIN_BYTES",
    "CODEAGENT_CONTEXT_COMPACT_MIN_ROUNDS",
    "CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL",
    "CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MODEL",
)


def _allowlist_path(root: Path) -> Path:
    return root / "config" / "codeagent.allowlist.json"


def _git_defaults_path(root: Path) -> Path:
    return root / "config" / "codeagent.git.defaults.json"


def _git_proxy_path(root: Path) -> Path:
    return root / "config" / "codeagent.git.proxy.json"


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


def _env_chat_view(root: Path) -> dict[str, str]:
    from seed.integrations.env_config import ENV_FILENAME, LEGACY_ENV_FILENAME

    p_seed = root / "config" / ENV_FILENAME
    p_leg = root / "config" / LEGACY_ENV_FILENAME
    file_vals = dict(_parse_env_file(p_leg))
    file_vals.update(_parse_env_file(p_seed))
    out: dict[str, str] = {}
    for k in _ENV_CHAT_KEYS:
        if k in os.environ:
            out[k] = os.environ[k]
        elif k in file_vals:
            out[k] = file_vals[k]
    defaults = {
        "CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT": "0",
        "CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS": "4",
        "CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT": "16",
        "CODEAGENT_CONTEXT_COMPACT": "",
        "CODEAGENT_CONTEXT_COMPACT_MIN_BYTES": "90000",
        "CODEAGENT_CONTEXT_COMPACT_MIN_ROUNDS": "0",
        "CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL": "",
        "CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MODEL": "",
    }
    for k, dv in defaults.items():
        out.setdefault(k, dv)
    return out


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
    from seed.core.proj_reg import get_project

    pr = get_project(agent_id, project_id)
    if not pr:
        return None
    raw = str(pr.get("path") or "").strip()
    if not raw:
        return None
    p = Path(os.path.expanduser(raw))
    return p if p.is_dir() else None


def _git_cwd(body: dict[str, Any], agent_id: str, project_root: Path) -> Path:
    pid = str(body.get("project_id") or "").strip()
    if pid:
        d = _project_fs_dir(agent_id, pid)
        if d is not None:
            return d
    return project_root


async def _run_git(cwd: Path, argv: list[str]) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", "git not found"
    out_b, err_b = await proc.communicate()
    out = out_b.decode("utf-8", errors="replace") if out_b else ""
    err = err_b.decode("utf-8", errors="replace") if err_b else ""
    return int(proc.returncode or 0), out, err


def _split_git_args(args: Any) -> list[str]:
    if isinstance(args, list):
        return [str(x) for x in args]
    s = str(args or "").strip()
    if not s:
        return []
    return shlex.split(s, posix=os.name != "nt")


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


def _transcript_json_for_session(
    sess: Any,
    before_block_index: int | None,
) -> dict[str, Any]:
    from . import (
        _webui_transcript_partition_user_blocks,
        _webui_transcript_rows_from_session,
    )

    try:
        max_chars = int(os.environ.get("CODEAGENT_WEBUI_TRANSCRIPT_MAX_CHARS", "12000"))
    except ValueError:
        max_chars = 12000
    try:
        max_blocks = int(os.environ.get("CODEAGENT_WEBUI_TRANSCRIPT_USER_BLOCKS", "10"))
    except ValueError:
        max_blocks = 10
    max_blocks = max(1, min(max_blocks, 200))

    rows = _webui_transcript_rows_from_session(sess, max_chars)
    blocks = _webui_transcript_partition_user_blocks(rows)
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

    try:
        max_msg = int(os.environ.get("CODEAGENT_WEBUI_TRANSCRIPT_MAX_MESSAGES", "300"))
    except ValueError:
        max_msg = 300
    max_msg = max(10, min(max_msg, 5000))
    if len(messages) > max_msg:
        messages = messages[-max_msg:]

    return _transcript_payload_json_safe(
        {
            "messages": messages,
            "first_block_index": first_idx,
            "has_more_older": has_more,
            "truncated_start": truncated_start,
        }
    )


def build_webui_api_app(project_root: Path) -> Starlette:
    project_root = project_root.resolve()

    from codeagent.core.settings import plugins_public_view, save_plugins_from_ui
    from codeagent.web.auth_impl import COOKIE_NAME, get_webui_token, make_webui_cookie_value
    from seed.core.config_plane import CONFIG_FILENAMES, ensure_default_config_files
    from seed.core.config_plane import project_root as project_root_fn
    from seed.core.llm_presets import (
        _validate_preset,
        get_default_preset_id,
        load_presets,
        save_presets,
        set_default_preset_id,
    )
    from seed.core.llm_sess import (
        archive_stored_llm_session,
        delete_stored_llm_session,
        list_stored_llm_sessions_meta,
        load_chat_session_from_disk,
    )
    from seed.core.proj_reg import (
        create_project,
        delete_project,
        list_project_plan_files,
        list_projects,
        rename_project,
        update_project_path,
    )
    from seed.core.proj_todos import delete_todo, list_todos, update_todo
    from seed.integrations.cron_sched import (
        cron_status_for_ui,
        delete_cron_job,
        load_cron_config,
        reload_cron_scheduler,
        save_cron_job,
        write_cron_config,
    )
    from seed.integrations.env_config import ENV_FILENAME

    from . import SESSIONS, _memkey, _running_sessions

    ensure_default_config_files(project_root_fn())

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
        ok = bool(verify_webui_cookie(tok, request.cookies.get(COOKIE_NAME)))
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
            COOKIE_NAME,
            make_webui_cookie_value(tok),
            max_age=604800,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return resp

    async def api_auth_logout(_: Request) -> JSONResponse:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

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

    async def api_md_get(request: Request) -> JSONResponse:
        name = (request.path_params.get("name") or "").strip()
        if name not in CONFIG_FILENAMES:
            return JSONResponse({"detail": "unknown file"}, status_code=404)
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
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
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
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

    def _api_read_skills_state(state_path: Path) -> dict:
        """Read skills enabled-state JSON, return {name: bool}."""
        if state_path.is_file():
            try:
                raw = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return {k: bool(v) for k, v in raw.items()}
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _api_write_skills_state(state_path: Path, state: dict) -> None:
        """Write skills enabled-state JSON atomically."""
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(state_path)

    async def api_skills_get(request: Request) -> JSONResponse:
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        try:
            from codeagent.core.paths import agent_skills_dir, ensure_agent_scaffold

            ensure_agent_scaffold(aid, base=project_root)
            sdir = agent_skills_dir(aid, base=project_root)
            skills_dir = project_root / "config" / "skills"
            state_path = sdir / "_state.json"
            state = _api_read_skills_state(state_path)
            files = []
            seen: set[str] = set()
            if sdir.is_dir():
                for fp in sorted(sdir.iterdir()):
                    if fp.name == "_state.json" or fp.name.startswith("."):
                        continue
                    if fp.suffix.lower() in (".md", ".txt"):
                        enabled = state.get(fp.name, True)
                        files.append(
                            {
                                "name": fp.name,
                                "path": str(fp),
                                "content": fp.read_text(encoding="utf-8"),
                                "enabled": enabled,
                                "scope": "agent",
                            }
                        )
                        seen.add(fp.name)
            if skills_dir.is_dir():
                for fp in sorted(skills_dir.iterdir()):
                    if fp.name.startswith("."):
                        continue
                    if fp.suffix.lower() in (".md", ".txt") and fp.name not in seen:
                        enabled = state.get(fp.name, True)
                        files.append(
                            {
                                "name": fp.name,
                                "path": str(fp),
                                "content": fp.read_text(encoding="utf-8"),
                                "enabled": enabled,
                                "scope": "global",
                            }
                        )
            return JSONResponse({"skills": files})
        except Exception as e:
            logger.exception("api_skills_get")
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def api_skills_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        action = body.get("action", "save")
        name = (body.get("name") or "").strip()
        if not name or "/" in name or "\\" in name:
            return JSONResponse({"detail": "invalid name"}, status_code=400)
        try:
            from codeagent.core.paths import agent_skills_dir, ensure_agent_scaffold

            ensure_agent_scaffold(aid, base=project_root)
            sdir = agent_skills_dir(aid, base=project_root)
            sdir.mkdir(parents=True, exist_ok=True)
            state_path = sdir / "_state.json"
            fp = sdir / name

            # Load current state
            state = _api_read_skills_state(state_path)

            if action == "delete":
                if fp.is_file():
                    fp.unlink()
                state.pop(name, None)
                _api_write_skills_state(state_path, state)
                return JSONResponse({"ok": True, "hint": f"已删除 {name}"})
            content = body.get("content", "")
            fp.write_text(str(content), encoding="utf-8")

            # Update enabled state if provided
            if "enabled" in body:
                state[name] = bool(body["enabled"])
                _api_write_skills_state(state_path, state)

            return JSONResponse({"ok": True, "path": str(fp), "hint": f"已保存 {name}，新会话生效。"})
        except Exception as e:
            logger.exception("api_skills_post")
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def api_config_paths(_: Request) -> JSONResponse:
        root = str(project_root.resolve())
        try:
            from codeagent.core.paths import agent_persona_dir, agent_skills_dir

            aid = os.environ.get("CODEAGENT_AGENT_ID", "default")
            skills_path = str(agent_skills_dir(aid, base=project_root).resolve())
            persona_path = str(agent_persona_dir(aid, base=project_root).resolve())
        except Exception:
            skills_path = ""
            persona_path = ""
        return JSONResponse(
            {
                "codeagent_root_path": root,
                "skills_path": skills_path,
                "persona_path": persona_path,
            }
        )

    async def api_projects_list(request: Request) -> JSONResponse:
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        try:
            from codeagent.core.paths import ensure_agent_scaffold

            ensure_agent_scaffold(aid)
            rows = list_projects(aid)
            # 检查默认目录是否有未分类会话，有则添加虚拟项目
            from seed.core.llm_sess import list_stored_llm_sessions_meta

            unassigned = list_stored_llm_sessions_meta(
                limit=1, agent_id=aid,
                filter_by_project=True, filter_project_id="",
            )
            if unassigned:
                rows = list(rows)
                rows.insert(0, {
                    "id": _UNASSIGNED_PROJECT_ID,
                    "name": "未分类",
                    "path": "",
                })
        except Exception as e:
            return JSONResponse({"detail": str(e)}, status_code=500)
        return JSONResponse({"projects": rows, "agent_id": aid})

    async def api_projects_create(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        aid = str(body.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        name = str(body.get("name") or "").strip()
        if not name:
            return JSONResponse({"detail": "name required"}, status_code=400)
        proj_path = os.path.expanduser(str(body.get("path") or "").strip())
        source = str(body.get("source") or "scratch").strip()
        clone_url = str(body.get("clone_url") or "").strip()
        template = str(body.get("template") or "").strip()
        remote = body.get("remote")
        messages: list[str] = []
        row: dict[str, Any] = {}
        try:
            from seed_tools import setup_builtin_tools

            from codeagent.core.paths import agent_projects_data_dir, ensure_agent_scaffold

            ensure_agent_scaffold(aid)

            if source == "clone" and clone_url:
                m = re.search(r"/([^/]+?)(?:\.git)?$", clone_url)
                repo_dir_name = m.group(1) if m else name
                if proj_path:
                    clone_target = Path(proj_path) / repo_dir_name
                else:
                    clone_target = agent_projects_data_dir(aid) / "repos" / repo_dir_name
                clone_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["git", "clone", clone_url, str(clone_target)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                except subprocess.TimeoutExpired:
                    return JSONResponse(
                        {"detail": "克隆超时（>120秒），请检查网络连接或换用 SSH 协议"},
                        status_code=408,
                    )
                if result.returncode != 0:
                    err = (result.stderr or "")[:300].strip()
                    return JSONResponse({"detail": f"克隆失败: {err}"}, status_code=400)
                proj_path = str(clone_target)
                row = create_project(aid, name, path=proj_path)
                messages.append(f"✅ 已从远程克隆到 {proj_path}")
                return JSONResponse({"ok": True, "project": row, "message": "\n".join(messages)})

            if proj_path:
                Path(proj_path).mkdir(parents=True, exist_ok=True)
            row = create_project(aid, name, path=proj_path)
            project_dir = Path(proj_path) if proj_path else None

            if source == "template" and template and project_dir and project_dir.is_dir():
                try:
                    reg, _ = setup_builtin_tools()
                    scaffold_fn = reg.handlers.get("scaffold")
                    if scaffold_fn:
                        scaffold_fn(template=template, name=name, path=str(project_dir))
                        messages.append(f"🏗️ 已从 {template} 模板创建")
                except Exception as e:
                    messages.append(f"⚠️ 模板创建失败: {e}")

            git_dir = project_dir or Path.cwd()
            git_init = await asyncio.to_thread(
                subprocess.run,
                ["git", "init"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(git_dir),
            )
            if git_init.returncode == 0:
                messages.append("📦 项目目录已初始化")
                name_check = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "config", "user.name"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=str(git_dir),
                )
                if name_check.returncode != 0 or not name_check.stdout.strip():
                    await asyncio.to_thread(
                        subprocess.run,
                        ["git", "config", "user.name", "CodeAgent User"],
                        capture_output=True,
                        timeout=5,
                        cwd=str(git_dir),
                    )
                    await asyncio.to_thread(
                        subprocess.run,
                        ["git", "config", "user.email", "agent@codeagent.dev"],
                        capture_output=True,
                        timeout=5,
                        cwd=str(git_dir),
                    )
                add_out = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "add", "-A"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=str(git_dir),
                )
                if add_out.returncode == 0:
                    commit_out = await asyncio.to_thread(
                        subprocess.run,
                        ["git", "commit", "-m", "feat: initial commit"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=str(git_dir),
                    )
                    if commit_out.returncode == 0 and "nothing to commit" not in (
                        commit_out.stdout or ""
                    ).lower():
                        messages.append("✅ 初始化完成")

            if remote and isinstance(remote, dict):
                provider = remote.get("provider", "github")
                owner = remote.get("owner", "")
                repo = remote.get("repo", "")
                protocol = remote.get("protocol", "ssh")
                auto_push = remote.get("autoPush", False)
                if owner and repo:
                    templates = {
                        "github": {
                            "ssh": f"git@github.com:{owner}/{repo}.git",
                            "https": f"https://github.com/{owner}/{repo}.git",
                        },
                        "gitlab": {
                            "ssh": f"git@gitlab.com:{owner}/{repo}.git",
                            "https": f"https://gitlab.com/{owner}/{repo}.git",
                        },
                        "gitee": {
                            "ssh": f"git@gitee.com:{owner}/{repo}.git",
                            "https": f"https://gitee.com/{owner}/{repo}.git",
                        },
                        "bitbucket": {
                            "ssh": f"git@bitbucket.org:{owner}/{repo}.git",
                            "https": f"https://bitbucket.org/{owner}/{repo}.git",
                        },
                    }
                    tmpl_dict = templates.get(provider, templates["github"])
                    remote_url = tmpl_dict.get(protocol, tmpl_dict["ssh"])
                    add_remote = await asyncio.to_thread(
                        subprocess.run,
                        ["git", "remote", "add", "origin", remote_url],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=str(git_dir),
                    )
                    if add_remote.returncode == 0:
                        messages.append(f"🔗 远程仓库已关联: {remote_url}")
                        if auto_push:
                            push_out = await asyncio.to_thread(
                                subprocess.run,
                                ["git", "push", "-u", "origin", "main"],
                                capture_output=True,
                                text=True,
                                timeout=30,
                                cwd=str(git_dir),
                            )
                            if push_out.returncode != 0:
                                push_out2 = await asyncio.to_thread(
                                    subprocess.run,
                                    ["git", "push", "-u", "origin", "master"],
                                    capture_output=True,
                                    text=True,
                                    timeout=30,
                                    cwd=str(git_dir),
                                )
                                if push_out2.returncode == 0:
                                    messages.append("📤 已推送到远程仓库 (master)")
                                else:
                                    messages.append(
                                        f"⚠️ 推送失败，可到配置页重试: {(push_out.stderr or '')[:200]}"
                                    )
                            else:
                                messages.append("📤 已推送到远程仓库")
                    else:
                        messages.append(f"⚠️ 关联远程失败: {(add_remote.stderr or '')[:200]}")
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        except Exception as e:
            return JSONResponse({"detail": str(e)}, status_code=500)
        return JSONResponse({"ok": True, "project": row, "message": "\n".join(messages)})

    async def api_projects_rename(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        aid = str(body.get("agent_id") or "").strip()
        pid = str(body.get("project_id") or "").strip()
        if pid == _UNASSIGNED_PROJECT_ID:
            return JSONResponse({"detail": "cannot rename virtual project"}, status_code=400)
        new_name = str(body.get("name") or "").strip()
        if not rename_project(aid, pid, new_name):
            return JSONResponse({"detail": "rename failed"}, status_code=400)
        return JSONResponse({"ok": True})

    async def api_projects_delete(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        aid = str(body.get("agent_id") or "").strip()
        pid = str(body.get("project_id") or "").strip()
        if pid == _UNASSIGNED_PROJECT_ID:
            return JSONResponse({"detail": "cannot delete virtual project"}, status_code=400)
        if not delete_project(aid, pid):
            return JSONResponse({"detail": "delete failed"}, status_code=400)
        return JSONResponse({"ok": True})

    async def api_projects_path(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        aid = str(body.get("agent_id") or "").strip()
        pid = str(body.get("project_id") or "").strip()
        if pid == _UNASSIGNED_PROJECT_ID:
            return JSONResponse({"detail": "virtual project has no path"}, status_code=400)
        path = str(body.get("path") or "").strip()
        if not update_project_path(aid, pid, path):
            return JSONResponse({"detail": "update failed"}, status_code=400)
        return JSONResponse({"ok": True})

    async def api_projects_plans(request: Request) -> JSONResponse:
        pid = (request.query_params.get("project_id") or "").strip()
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        if not pid or pid == _UNASSIGNED_PROJECT_ID:
            return JSONResponse({"plans": []})
        try:
            from seed.core.paths import agent_project_data_subdir

            plans_dir = Path(agent_project_data_subdir(aid, pid, "plans"))
            rels = list_project_plan_files(aid, pid)
            plans = []
            for rel in rels:
                fp = plans_dir / rel
                if not fp.is_file():
                    continue
                try:
                    st = fp.stat()
                    content = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                plans.append(
                    {
                        "name": rel,
                        "modified_at": int(st.st_mtime),
                        "size": st.st_size,
                        "content": content[:80000],
                    }
                )
            return JSONResponse({"plans": plans})
        except Exception as e:
            logger.exception("api_projects_plans")
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def api_projects_todos_list(request: Request) -> JSONResponse:
        pid = (request.query_params.get("project_id") or "").strip()
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        sid = (request.query_params.get("session_id") or "").strip()
        if not pid or pid == _UNASSIGNED_PROJECT_ID:
            return JSONResponse({"todos": []})
        rows = list_todos(aid, pid, session_id=sid or None)
        return JSONResponse({"todos": rows})

    async def api_projects_todos_patch(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        todo_id = (request.path_params.get("todo_id") or "").strip()
        aid = str(body.get("agent_id") or "").strip()
        pid = str(body.get("project_id") or "").strip()
        updates = {k: body[k] for k in ("content", "status") if k in body}
        item = update_todo(aid, pid, todo_id, updates)
        if item is None:
            return JSONResponse({"detail": "not found"}, status_code=404)
        return JSONResponse({"ok": True, "todo": item})

    async def api_projects_todos_delete(request: Request) -> JSONResponse:
        todo_id = (request.path_params.get("todo_id") or "").strip()
        pid = (request.query_params.get("project_id") or "").strip()
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        if not delete_todo(aid, pid, todo_id):
            return JSONResponse({"detail": "not found"}, status_code=404)
        return JSONResponse({"ok": True})

    async def api_sessions(request: Request) -> JSONResponse:
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        try:
            lim = int(request.query_params.get("limit") or "80")
        except ValueError:
            lim = 80
        pid = (request.query_params.get("project_id") or "").strip()
        if pid == _UNASSIGNED_PROJECT_ID:
            rows = list_stored_llm_sessions_meta(
                limit=lim, agent_id=aid,
                filter_by_project=True, filter_project_id="",
            )
        elif pid:
            rows = list_stored_llm_sessions_meta(
                limit=lim,
                agent_id=aid,
                filter_by_project=True,
                filter_project_id=pid,
            )
        else:
            rows = list_stored_llm_sessions_meta(limit=lim, agent_id=aid, filter_by_project=False)
        return JSONResponse({"sessions": rows})

    async def api_sessions_running(request: Request) -> JSONResponse:
        """返回当前正在执行中的会话 ID 列表（用于页面刷新后恢复心跳指示）。"""
        aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
            "CODEAGENT_AGENT_ID", "default"
        ).strip() or "default"
        # _running_sessions 中存的是 mkey（agent_id::session_id）, 按 agent_id 过滤
        prefix = f"{aid}::"
        running = [
            mkey.removeprefix(prefix)
            for mkey in _running_sessions
            if mkey.startswith(prefix)
        ]
        return JSONResponse({"running": running})

    async def api_session_transcript(request: Request) -> JSONResponse:
        try:
            sid = (request.query_params.get("session_id") or "").strip()
            aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
                "CODEAGENT_AGENT_ID", "default"
            ).strip() or "default"
            pid = _resolve_project_id((request.query_params.get("project_id") or "").strip())
            bb = request.query_params.get("before_block_index")
            before_i: int | None = None
            if bb is not None and str(bb).strip() != "":
                try:
                    before_i = int(bb)
                except ValueError:
                    before_i = None

            if not sid:
                return JSONResponse({"detail": "session_id required"}, status_code=400)

            mkey = _memkey(aid, sid)
            sess = SESSIONS.get(mkey)
            if sess is None:
                sess = load_chat_session_from_disk(sid, aid, pid or None)
            if sess is None:
                return JSONResponse(
                    {
                        "messages": [],
                        "first_block_index": None,
                        "has_more_older": False,
                        "truncated_start": False,
                    }
                )
            return JSONResponse(_transcript_json_for_session(sess, before_i))
        except Exception as e:
            logger.exception("api_session_transcript failed")
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def api_session_archive(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        sid = str(body.get("session_id") or "").strip()
        aid = str(body.get("agent_id") or "").strip()
        pid = _resolve_project_id(str(body.get("project_id") or "").strip())
        ok = archive_stored_llm_session(sid, aid, pid or None)
        if not ok:
            loc = _locate_session_file(sid, aid, pid)
            ok = bool(loc and loc.is_file() and _archive_session_path(loc))
        if not ok:
            return JSONResponse({"detail": "archive failed"}, status_code=400)
        SESSIONS.pop(_memkey(aid, sid), None)
        return JSONResponse({"ok": True})

    async def api_session_delete(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        sid = str(body.get("session_id") or "").strip()
        aid = str(body.get("agent_id") or "").strip()
        pid = _resolve_project_id(str(body.get("project_id") or "").strip())
        ok = delete_stored_llm_session(sid, aid, pid or None)
        if not ok:
            loc = _locate_session_file(sid, aid, pid)
            if loc and loc.is_file():
                try:
                    loc.unlink()
                    ok = True
                except OSError:
                    ok = False
        if not ok:
            return JSONResponse({"detail": "delete failed"}, status_code=400)
        SESSIONS.pop(_memkey(aid, sid), None)
        return JSONResponse({"ok": True})

    async def api_env_chat_get(_: Request) -> JSONResponse:
        return JSONResponse(_env_chat_view(project_root))

    async def api_env_chat_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        updates = {k: str(body.get(k)) for k in _ENV_CHAT_KEYS if k in body}
        if not updates:
            return JSONResponse({"detail": "no known keys"}, status_code=400)
        p = project_root / "config" / ENV_FILENAME
        _write_env_file_merge(p, updates)
        return JSONResponse({"ok": True, "hint": "已写入 config/seed.env；重启进程后完全生效。"})

    async def api_llm_presets_get(_: Request) -> JSONResponse:
        return JSONResponse({"presets": load_presets(), "default_id": get_default_preset_id()})

    async def api_llm_presets_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        err = _validate_preset(body)
        if err:
            return JSONResponse({"detail": err}, status_code=400)
        pid = str(body.get("id") or "").strip()
        presets = load_presets()
        replaced = False
        for i, p in enumerate(presets):
            if str(p.get("id") or "").strip() == pid:
                presets[i] = body
                replaced = True
                break
        if not replaced:
            presets.append(body)
        save_presets(presets)
        return JSONResponse({"ok": True})

    async def api_llm_presets_default(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        set_default_preset_id(str(body.get("preset_id") or ""))
        return JSONResponse({"ok": True})

    async def api_llm_presets_delete(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        pid = str(body.get("preset_id") or "").strip()
        presets = [p for p in load_presets() if str(p.get("id") or "").strip() != pid]
        save_presets(presets)
        if get_default_preset_id() == pid:
            set_default_preset_id("")
        return JSONResponse({"ok": True})

    async def api_llm_presets_test(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        return await _llm_probe_response(body)

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

    async def api_git_defaults_get(_: Request) -> JSONResponse:
        p = _git_defaults_path(project_root)
        if not p.is_file():
            return JSONResponse({"defaults": {}})
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        return JSONResponse({"defaults": data if isinstance(data, dict) else {}})

    async def api_git_defaults_put(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "expected JSON object"}, status_code=400)
        p = _git_defaults_path(project_root)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            return JSONResponse({"detail": str(e)}, status_code=500)
        return JSONResponse({"ok": True})

    async def api_git_proxy_config(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        method = str(body.get("method") or "get")
        path = _git_proxy_path(project_root)
        if method == "get":
            if not path.is_file():
                return JSONResponse({"ok": True, "enabled": False, "http": "", "https": ""})
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            return JSONResponse(
                {
                    "ok": True,
                    "enabled": bool(data.get("enabled")),
                    "http": str(data.get("http") or ""),
                    "https": str(data.get("https") or ""),
                }
            )
        if method == "set":
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "enabled": bool(body.get("enabled")),
                "http": str(body.get("http") or ""),
                "https": str(body.get("https") or ""),
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return JSONResponse({"ok": True})
        return JSONResponse({"detail": "bad method"}, status_code=400)

    async def api_git_proxy_unset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        scheme = str(body.get("scheme") or "http")
        key = "http" if scheme == "http" else "https"
        path = _git_proxy_path(project_root)
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = raw
            except (json.JSONDecodeError, OSError):
                pass
        data[key] = ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        arg = "http.proxy" if scheme == "http" else "https.proxy"
        await asyncio.to_thread(
            subprocess.run,
            ["git", "config", "--global", "--unset-all", arg],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return JSONResponse({"ok": True})

    async def api_git_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        cmd = str(body.get("command") or "").strip()
        args = body.get("args", "")
        aid = os.environ.get("CODEAGENT_AGENT_ID", "default").strip() or "default"
        cwd = _git_cwd(body, aid, project_root)

        if cmd == "remote":
            extra = _split_git_args(args)
            if not extra:
                rc, out, err = await _run_git(cwd, ["remote", "-v"])
                if rc != 0:
                    return JSONResponse({"result": "未配置远程仓库（git remote 不可用）\n" + err})
                return JSONResponse({"result": out or err})
            rc, out, err = await _run_git(cwd, ["remote", *extra])
            text = (out or "") + (err or "")
            return JSONResponse({"result": text, "error": err if rc != 0 else ""})

        if cmd == "test-remote":
            name = str(args or "").strip()
            rc, out, err = await _run_git(cwd, ["ls-remote", "--heads", name])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "ssh":
            ssh_dir = Path.home() / ".ssh"
            arg = str(args or "").strip()
            if arg == "status":
                lines = []
                for nm in ("id_ed25519.pub", "id_rsa.pub"):
                    p = ssh_dir / nm
                    lines.append(f"{nm}: {'存在' if p.is_file() else '缺失'}")
                return JSONResponse({"result": "\n".join(lines)})
            if arg == "cat":
                pub = ssh_dir / "id_ed25519.pub"
                if not pub.is_file():
                    pub = ssh_dir / "id_rsa.pub"
                if not pub.is_file():
                    return JSONResponse({"result": "", "error": "未找到公钥"})
                try:
                    return JSONResponse({"result": pub.read_text(encoding="utf-8")})
                except OSError as e:
                    return JSONResponse({"error": str(e)})
            if arg == "generate":
                ssh_dir.mkdir(parents=True, exist_ok=True)
                key_path = ssh_dir / "id_ed25519"
                if key_path.is_file():
                    return JSONResponse({"result": "已有 id_ed25519，跳过生成"})
                proc = await asyncio.create_subprocess_exec(
                    "ssh-keygen",
                    "-t",
                    "ed25519",
                    "-f",
                    str(key_path),
                    "-N",
                    "",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out_b, err_b = await proc.communicate()
                text = (out_b or b"").decode() + (err_b or b"").decode()
                return JSONResponse({"result": text.strip() or "完成"})
            if arg == "test":
                proc = await asyncio.create_subprocess_exec(
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-T",
                    "git@github.com",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out_b, err_b = await proc.communicate()
                text = (out_b or b"").decode() + (err_b or b"").decode()
                return JSONResponse({"result": text.strip() or "完成"})

        # ---- 核心 git 命令：log / diff / status / commit / branch / push / pull ----
        if cmd == "log":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["log", *extra])
            if rc != 0:
                return JSONResponse({"result": out, "error": err.strip() or "git log 失败"})
            return JSONResponse({"result": out})

        if cmd == "diff":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["diff", *extra])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "status":
            rc, out, err = await _run_git(cwd, ["status"])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "commit":
            msg = str(body.get("message") or "").strip()
            if not msg:
                return JSONResponse({"error": "提交信息不能为空"}, status_code=400)
            # 先 add -A，再 commit
            rc1, out1, err1 = await _run_git(cwd, ["add", "-A"])
            if rc1 != 0:
                return JSONResponse({"result": out1, "error": err1.strip() or "git add 失败"})
            rc2, out2, err2 = await _run_git(cwd, ["commit", "-m", msg])
            if rc2 != 0:
                return JSONResponse({"result": out2, "error": err2.strip() or "git commit 失败"})
            return JSONResponse({"result": (out2 or err2).strip() or "提交成功"})

        if cmd == "branch":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["branch", *extra])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "push":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["push", *extra])
            return JSONResponse({"result": (out or err).strip(), "error": err if rc != 0 else ""})

        if cmd == "pull":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["pull", *extra])
            return JSONResponse({"result": (out or err).strip(), "error": err if rc != 0 else ""})

        return JSONResponse({"detail": "unsupported git command"}, status_code=400)

    async def api_pick_directory(_: Request) -> JSONResponse:
        path = ""
        skip = str(os.environ.get("CODEAGENT_SKIP_FOLDER_PICKER", "") or "").strip().lower()
        if skip in ("1", "true", "yes", "on"):
            return JSONResponse({"path": "", "skipped": True})
        try:
            if sys.platform == "darwin":
                script = (
                    'POSIX path of (choose folder with prompt '
                    '"选择目录" default location (path to desktop folder))'
                )
                proc = await asyncio.create_subprocess_exec(
                    "osascript",
                    "-e",
                    script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out_b, _ = await proc.communicate()
                cand = (out_b or b"").decode("utf-8").strip()
                if cand and Path(cand).is_dir():
                    path = cand
            elif sys.platform == "win32":
                ps = r"""
                Add-Type -AssemblyName System.Windows.Forms
                $top = New-Object System.Windows.Forms.Form
                $top.TopMost = $true
                $top.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
                $top.ShowInTaskbar = $false
                $top.Size = New-Object System.Drawing.Size(0, 0)
                $top.StartPosition = "Manual"
                $top.Location = New-Object System.Drawing.Point(-32000, -32000)
                $null = $top.Show()
                [System.Windows.Forms.Application]::DoEvents()
                try {
                  $d = New-Object System.Windows.Forms.FolderBrowserDialog
                  $d.Description = "选择项目目录"
                  $d.ShowNewFolderButton = $true
                  if ($d.ShowDialog($top) -eq "OK") { Write-Output $d.SelectedPath }
                } finally { $top.Close(); $top.Dispose() }
                """
                proc = await asyncio.create_subprocess_exec(
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    ps,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out_b, _ = await proc.communicate()
                cand = (out_b or b"").decode("utf-8", errors="replace").strip()
                if cand and Path(cand).is_dir():
                    path = cand
            else:
                for bin_name in ("zenity", "kdialog"):
                    cmd = (
                        [bin_name, "--file-selection", "--directory"]
                        if bin_name == "zenity"
                        else [bin_name, "--getexistingdirectory"]
                    )
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        out_b, _ = await proc.communicate()
                        cand = (out_b or b"").decode().strip()
                        if cand and Path(cand).is_dir():
                            path = cand
                            break
                    except FileNotFoundError:
                        continue
        except Exception as e:
            logger.exception("pick_directory")
            return JSONResponse({"detail": str(e)}, status_code=500)
        return JSONResponse({"path": path})

    async def api_files_list(request: Request) -> JSONResponse:
        pid = (request.query_params.get("project_id") or "").strip()
        dir_q = (request.query_params.get("dir") or "").strip()
        aid = os.environ.get("CODEAGENT_AGENT_ID", "default").strip() or "default"
        base = _project_fs_dir(aid, pid) if pid else None
        if base is None:
            return JSONResponse({"files": [], "detail": "no project path"})
        base = base.resolve()
        # dir_q 可能是绝对路径或相对路径，统一处理
        target = base
        if dir_q:
            p = Path(dir_q)
            if p.is_absolute():
                # 绝对路径：确保在 base 下
                p = p.resolve()
                if p == base or base in p.parents:
                    target = p
            else:
                # 相对路径：join 到 base
                target = _safe_under(base, dir_q)
        if target is None or not target.is_dir():
            return JSONResponse({"files": []})
        items = []
        try:
            for ch in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                try:
                    st = ch.stat()
                    items.append(
                        {
                            "name": ch.name,
                            "path": str(ch.resolve()),
                            "is_dir": ch.is_dir(),
                            "size": st.st_size if ch.is_file() else 0,
                        }
                    )
                except OSError:
                    continue
        except OSError:
            pass
        return JSONResponse({"files": items})

    async def api_files_read(request: Request) -> JSONResponse:
        pid = (request.query_params.get("project_id") or "").strip()
        rel = (request.query_params.get("path") or "").strip()
        aid = os.environ.get("CODEAGENT_AGENT_ID", "default").strip() or "default"
        base = _project_fs_dir(aid, pid) if pid else None
        if base is None:
            return JSONResponse({"detail": "no project path"}, status_code=400)
        base = base.resolve()
        # 支持绝对路径或相对路径
        p = Path(rel)
        if p.is_absolute():
            p = p.resolve()
            if p == base or base in p.parents:
                fp = p
            else:
                return JSONResponse({"detail": "path not under project"}, status_code=400)
        else:
            fp = _safe_under(base, rel.lstrip("/"))
        if fp is None or not fp.is_file():
            return JSONResponse({"detail": "not found"}, status_code=404)
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return JSONResponse({"detail": str(e)}, status_code=500)
        # 简单推断语言类型
        ext = fp.suffix.lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".html": "html", ".css": "css", ".json": "json",
            ".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
            ".sql": "sql", ".sh": "shell", ".bash": "shell", ".xml": "xml",
            ".svg": "xml", ".ini": "ini", ".cfg": "ini", ".conf": "ini",
            ".txt": "plaintext", ".rst": "rst",
        }
        language = lang_map.get(ext, "plaintext")
        try:
            st = fp.stat()
            size = st.st_size
        except OSError:
            size = len(text.encode("utf-8"))
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        return JSONResponse({"path": str(fp), "content": text, "language": language, "size": size, "lines": lines})

    async def api_setup_finish(_: Request) -> JSONResponse:
        tok = secrets.token_urlsafe(32)
        cfg = project_root / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        from codeagent.web.auth_impl import TOKEN_FILENAME

        (cfg / TOKEN_FILENAME).write_text(tok + "\n", encoding="utf-8")
        marker = cfg / "codeagent.setup.json"
        marker.write_text(json.dumps({"done": True}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return JSONResponse({"webui_token": tok})

    async def api_setup_test_llm(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        mapped = {
            "base_url": body.get("llm_baseurl") or body.get("base_url"),
            "model": body.get("llm_model") or body.get("model"),
            "api_key": body.get("llm_api_key") or body.get("api_key"),
            "auth_scheme": body.get("llm_auth_scheme") or body.get("auth_scheme") or "Bearer",
        }
        return await _llm_probe_response(mapped)

    routes = [
        Route("/flags", api_flags, methods=["GET"]),
        Route("/auth/status", api_auth_status, methods=["GET"]),
        Route("/auth", api_auth_login, methods=["POST"]),
        Route("/auth/logout", api_auth_logout, methods=["POST"]),
        Route("/plugins", api_plugins_get, methods=["GET"]),
        Route("/plugins", api_plugins_post, methods=["POST"]),
        Route("/md/{name}", api_md_get, methods=["GET"]),
        Route("/md/{name}", api_md_post, methods=["POST"]),
        Route("/skills", api_skills_get, methods=["GET"]),
        Route("/skills", api_skills_post, methods=["POST"]),
        Route("/config/paths", api_config_paths, methods=["GET"]),
        Route("/projects", api_projects_list, methods=["GET"]),
        Route("/projects", api_projects_create, methods=["POST"]),
        Route("/projects/rename", api_projects_rename, methods=["POST"]),
        Route("/projects/delete", api_projects_delete, methods=["POST"]),
        Route("/projects/path", api_projects_path, methods=["POST"]),
        Route("/projects/plans", api_projects_plans, methods=["GET"]),
        Route("/projects/todos/{todo_id}", api_projects_todos_patch, methods=["PATCH"]),
        Route("/projects/todos/{todo_id}", api_projects_todos_delete, methods=["DELETE"]),
        Route("/projects/todos", api_projects_todos_list, methods=["GET"]),
        Route("/sessions", api_sessions, methods=["GET"]),
        Route("/sessions/running", api_sessions_running, methods=["GET"]),
        Route("/session/transcript", api_session_transcript, methods=["GET"]),
        Route("/session/archive", api_session_archive, methods=["POST"]),
        Route("/session/delete", api_session_delete, methods=["POST"]),
        Route("/env/chat", api_env_chat_get, methods=["GET"]),
        Route("/env/chat", api_env_chat_post, methods=["POST"]),
        Route("/llm/presets", api_llm_presets_get, methods=["GET"]),
        Route("/llm/presets", api_llm_presets_post, methods=["POST"]),
        Route("/llm/presets/default", api_llm_presets_default, methods=["POST"]),
        Route("/llm/presets/delete", api_llm_presets_delete, methods=["POST"]),
        Route("/llm/presets/test", api_llm_presets_test, methods=["POST"]),
        Route("/cron/toggle", api_cron_toggle, methods=["POST"]),
        Route("/cron/job", api_cron_job, methods=["POST"]),
        Route("/cron/job/delete", api_cron_job_delete, methods=["POST"]),
        Route("/allowlist", api_allowlist_get, methods=["GET"]),
        Route("/allowlist", api_allowlist_post, methods=["POST"]),
        Route("/git/defaults", api_git_defaults_get, methods=["GET"]),
        Route("/git/defaults", api_git_defaults_put, methods=["PUT"]),
        Route("/git/proxy-config", api_git_proxy_config, methods=["POST"]),
        Route("/git/proxy", api_git_proxy_unset, methods=["POST"]),
        Route("/git", api_git_post, methods=["POST"]),
        Route("/pick-directory", api_pick_directory, methods=["POST"]),
        Route("/files/list", api_files_list, methods=["GET"]),
        Route("/files/read", api_files_read, methods=["GET"]),
        Route("/setup/finish", api_setup_finish, methods=["POST"]),
        Route("/setup/test-llm", api_setup_test_llm, methods=["POST"]),
    ]

    return Starlette(debug=False, routes=routes)
