"""Web UI project + todo endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. Handlers need ``project_root`` (via factory) and the
seed project-registry APIs. Pure helpers defined in ``webui_api_app``
(``_UNASSIGNED_PROJECT_ID``, ``_default_agent_id``) are imported lazily inside
each handler to avoid a circular import.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from seed.core.proj_reg import (
    create_project,
    delete_project,
    get_project,
    list_project_plan_files,
    list_projects,
    rename_project,
    update_project_path,
)
from seed.core.proj_todos import delete_todo, list_todos, update_todo

logger = logging.getLogger(__name__)


def build_projects_routes(project_root: Path) -> list[Route]:
    """Return the project + todo routes for ``webui_api_app``."""

    async def api_projects_list(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID, _default_agent_id
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        try:
            from codeagent.core.paths import ensure_agent_scaffold

            ensure_agent_scaffold(aid)
            rows = list_projects(aid, include_virtual=False)
            # 检查默认目录是否有未分类会话，有则添加虚拟项目
            from seed.core.llm_sess import list_stored_sessions_meta

            unassigned = list_stored_sessions_meta(
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
        from codeagent.server.webui_api_app import _default_agent_id
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        aid = str(body.get("agent_id") or "").strip() or _default_agent_id()
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

            from codeagent.core.paths import (
                agent_projects_data_dir,
                ensure_agent_scaffold,
                ensure_project_dirs,
            )

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
            proj_path = str(row.get("path") or proj_path or "").strip()
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

            if project_dir:
                git_dir = project_dir
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
                    # Create .codeagent/ working directory in the project
                    ensure_project_dirs(agent_id=aid, root=project_dir)
                    messages.append("📁 已创建 .codeagent/ 工作目录")
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
            elif source in ("scratch", "template"):
                messages.append("ℹ️ 未设置工作目录；可在项目菜单中绑定后再使用 Git / 文件树")

            if project_dir and remote and isinstance(remote, dict):
                git_dir = project_dir
                provider = remote.get("provider", "github")
                owner = remote.get("owner", "")
                repo = remote.get("repo", "")
                protocol = remote.get("protocol", "ssh")
                auto_push = remote.get("autoPush", False)
                if owner and repo:
                    host = remote.get("host", "")
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
                        "custom": {
                            "ssh": f"git@{host}:{owner}/{repo}.git",
                            "https": f"https://{host}/{owner}/{repo}.git",
                        },
                    }
                    tmpl_dict = templates.get(provider, templates.get("custom") if host else templates["github"])
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
        from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID
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
        from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID
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
        from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        aid = str(body.get("agent_id") or "").strip()
        pid = str(body.get("project_id") or "").strip()
        if pid == _UNASSIGNED_PROJECT_ID:
            return JSONResponse({"detail": "virtual project has no path"}, status_code=400)
        path = str(body.get("path") or "").strip()
        if not path:
            return JSONResponse({"detail": "path required"}, status_code=400)
        resolved = str(Path(os.path.expandvars(os.path.expanduser(path))).resolve())
        p = Path(resolved)
        if not p.is_dir():
            with contextlib.suppress(OSError):
                p.mkdir(parents=True, exist_ok=True)
        if not p.is_dir():
            return JSONResponse({"detail": "path is not a directory"}, status_code=400)
        if not update_project_path(aid, pid, resolved):
            return JSONResponse({"detail": "update failed"}, status_code=400)
        row = get_project(aid, pid)
        return JSONResponse({"ok": True, "project": row})

    async def api_projects_plans(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID, _default_agent_id
        pid = (request.query_params.get("project_id") or "").strip()
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        if not pid or pid == _UNASSIGNED_PROJECT_ID:
            return JSONResponse({"plans": []})
        try:
            from seed.core.paths import agent_project_data_subdir
            from seed.core.proj_reg import resolve_project_path

            plans: list[dict[str, Any]] = []

            # 1. Project-level plans (agents/{aid}/projects-data/{pid}/plans/)
            plans_dir = Path(agent_project_data_subdir(aid, pid, "plans"))
            for rel in list_project_plan_files(aid, pid):
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
                        "source": "project_plans",
                        "modified_at": int(st.st_mtime),
                        "size": st.st_size,
                        "content": content[:80000],
                    }
                )

            # 2. Agent-level docs/ and plans/ under project root (.codeagent/{aid}/)
            proj_path = resolve_project_path(aid, pid)
            if proj_path:
                agent_dir = Path(proj_path) / ".codeagent" / aid

                # docs/ — requirement.md, design.md, task.md
                docs_dir = agent_dir / "docs"
                if docs_dir.is_dir():
                    for fp in sorted(docs_dir.glob("*.md")):
                        if not fp.is_file():
                            continue
                        try:
                            st = fp.stat()
                            content = fp.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            continue
                        plans.append(
                            {
                                "name": fp.name,
                                "source": "docs",
                                "modified_at": int(st.st_mtime),
                                "size": st.st_size,
                                "content": content[:80000],
                            }
                        )

                # plans/ — *-plan.md
                plans_dir2 = agent_dir / "plans"
                if plans_dir2.is_dir():
                    for fp in sorted(plans_dir2.glob("*.md")):
                        if not fp.is_file():
                            continue
                        try:
                            st = fp.stat()
                            content = fp.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            continue
                        plans.append(
                            {
                                "name": fp.name,
                                "source": "plans",
                                "modified_at": int(st.st_mtime),
                                "size": st.st_size,
                                "content": content[:80000],
                            }
                        )

                # rules/ — .codeagent/rules.md (global) + .codeagent/{aid}/rules.md (agent)
                ca_root = Path(proj_path) / ".codeagent"
                for rname, rpath in [("rules.md", ca_root / "rules.md"), (f"rules.md ({aid})", ca_root / aid / "rules.md")]:
                    if rpath.is_file():
                        try:
                            st = rpath.stat()
                            content = rpath.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            continue
                        plans.append(
                            {
                                "name": rname,
                                "source": "rules",
                                "modified_at": int(st.st_mtime),
                                "size": st.st_size,
                                "content": content[:80000] if content.strip() else "",
                            }
                        )

            return JSONResponse({"plans": plans})
        except Exception as e:
            logger.exception("api_projects_plans")
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def api_projects_todos_list(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID, _default_agent_id
        pid = (request.query_params.get("project_id") or "").strip()
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
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
        from codeagent.server.webui_api_app import _default_agent_id
        todo_id = (request.path_params.get("todo_id") or "").strip()
        pid = (request.query_params.get("project_id") or "").strip()
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        if not delete_todo(aid, pid, todo_id):
            return JSONResponse({"detail": "not found"}, status_code=404)
        return JSONResponse({"ok": True})


    return [
        Route("/projects", api_projects_list, methods=["GET"]),
        Route("/projects", api_projects_create, methods=["POST"]),
        Route("/projects/rename", api_projects_rename, methods=["POST"]),
        Route("/projects/delete", api_projects_delete, methods=["POST"]),
        Route("/projects/path", api_projects_path, methods=["POST"]),
        Route("/projects/plans", api_projects_plans, methods=["GET"]),
        Route("/projects/todos/{todo_id}", api_projects_todos_patch, methods=["PATCH"]),
        Route("/projects/todos/{todo_id}", api_projects_todos_delete, methods=["DELETE"]),
        Route("/projects/todos", api_projects_todos_list, methods=["GET"]),
    ]
