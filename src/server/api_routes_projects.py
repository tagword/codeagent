async def api_ui_projects_list(request: Request) -> JSONResponse:
    if not _webui_sessions_enabled():
        return JSONResponse({"detail": "disabled"}, status_code=404)
    aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
        "CODEAGENT_AGENT_ID", "default"
    ).strip() or "default"
    try:
        from src.codeagent.core.paths import ensure_agent_scaffold
        from src.proj_reg_pkg import list_projects

        ensure_agent_scaffold(aid)
        rows = list_projects(aid)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)
    return JSONResponse({"projects": rows, "agent_id": aid})

async def api_ui_projects_create(request: Request) -> JSONResponse:
    if not _webui_sessions_enabled():
        return JSONResponse({"detail": "disabled"}, status_code=404)
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
    messages = []
    try:
        from src.codeagent.core.paths import ensure_agent_scaffold
        from src.proj_reg_pkg import create_project
        import subprocess

        ensure_agent_scaffold(aid)

        # 处理克隆模式：先 clone 再创建项目
        if source == "clone" and clone_url:
            # 从克隆 URL 提取仓库名（如 tagword-group-chat）
            import re
            m = re.search(r'/([^/]+?)(?:\.git)?$', clone_url)
            repo_dir_name = m.group(1) if m else name

            if proj_path:
                # 用户选了父目录 → 创建 <父目录>/<仓库名>/ 子文件夹
                clone_target = Path(proj_path) / repo_dir_name
            else:
                from src.codeagent.core.paths import agent_projects_data_dir
                clone_target = agent_projects_data_dir(aid) / "repos" / repo_dir_name
            # 确保父目录存在
            clone_target.parent.mkdir(parents=True, exist_ok=True)
            try:
                result = subprocess.run(
                    ["git", "clone", clone_url, str(clone_target)],
                    capture_output=True, text=True, timeout=120,
                )
            except subprocess.TimeoutExpired:
                return JSONResponse({"detail": "克隆超时（>120秒），请检查网络连接或换用 SSH 协议"}, status_code=408)
            if result.returncode != 0:
                err = result.stderr[:300].strip()
                return JSONResponse({"detail": f"克隆失败: {err}"}, status_code=400)
            proj_path = str(clone_target)
            row = create_project(aid, name, path=proj_path)
            messages.append(f"✅ 已从远程克隆到 {proj_path}")
            return JSONResponse({"ok": True, "project": row, "message": "\n".join(messages)})

        # 普通创建
        if proj_path:
            Path(proj_path).mkdir(parents=True, exist_ok=True)
        row = create_project(aid, name, path=proj_path)
        project_dir = Path(proj_path) if proj_path else None

        # 处理模板模式：scaffold 生成骨架
        if source == "template" and template:
            if project_dir and project_dir.is_dir():
                try:
                    from src.tools import setup_builtin_tools
                    reg, _ = setup_builtin_tools()
                    scaffold_fn = reg.handlers.get("scaffold")
                    if scaffold_fn:
                        scaffold_fn(template=template, name=name, path=str(project_dir))
                        messages.append(f"🏗️ 已从 {template} 模板创建")
                except Exception as e:
                    messages.append(f"⚠️ 模板创建失败: {e}")

        # Git 初始化
        git_dir = project_dir or Path.cwd()
        git_init = subprocess.run(
            ["git", "init"],
            capture_output=True, text=True, timeout=10,
            cwd=str(git_dir),
        )
        if git_init.returncode == 0:
            messages.append("📦 Git 仓库已初始化")

            # 设置 user 配置（如果不存在）
            name_check = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True, text=True, timeout=5, cwd=str(git_dir),
            )
            if name_check.returncode != 0 or not name_check.stdout.strip():
                subprocess.run(
                    ["git", "config", "user.name", "CodeAgent User"],
                    capture_output=True, timeout=5, cwd=str(git_dir),
                )
                subprocess.run(
                    ["git", "config", "user.email", "agent@codeagent.dev"],
                    capture_output=True, timeout=5, cwd=str(git_dir),
                )

            # 初始 commit（有文件时才做）
            add_out = subprocess.run(
                ["git", "add", "-A"],
                capture_output=True, text=True, timeout=10, cwd=str(git_dir),
            )
            if add_out.returncode == 0:
                commit_out = subprocess.run(
                    ["git", "commit", "-m", "feat: initial commit"],
                    capture_output=True, text=True, timeout=10, cwd=str(git_dir),
                )
                if commit_out.returncode == 0 and "nothing to commit" not in commit_out.stdout.lower():
                    messages.append("✅ 初始提交完成")

        # 关联远程仓库
        if remote and isinstance(remote, dict):
            provider = remote.get("provider", "github")
            owner = remote.get("owner", "")
            repo = remote.get("repo", "")
            protocol = remote.get("protocol", "ssh")
            auto_push = remote.get("autoPush", False)
            if owner and repo:
                templates = {
                    "github": {"ssh": f"git@github.com:{owner}/{repo}.git", "https": f"https://github.com/{owner}/{repo}.git"},
                    "gitlab": {"ssh": f"git@gitlab.com:{owner}/{repo}.git", "https": f"https://gitlab.com/{owner}/{repo}.git"},
                    "gitee": {"ssh": f"git@gitee.com:{owner}/{repo}.git", "https": f"https://gitee.com/{owner}/{repo}.git"},
                    "bitbucket": {"ssh": f"git@bitbucket.org:{owner}/{repo}.git", "https": f"https://bitbucket.org/{owner}/{repo}.git"},
                }
                tmpl_dict = templates.get(provider, templates["github"])
                remote_url = tmpl_dict.get(protocol, tmpl_dict["ssh"])
                add_remote = subprocess.run(
                    ["git", "remote", "add", "origin", remote_url],
                    capture_output=True, text=True, timeout=10, cwd=str(git_dir),
                )
                if add_remote.returncode == 0:
                    messages.append(f"🔗 远程仓库已关联: {remote_url}")
                    # 自动推送
                    if auto_push:
                        push_out = subprocess.run(
                            ["git", "push", "-u", "origin", "main"],
                            capture_output=True, text=True, timeout=30, cwd=str(git_dir),
                        )
                        if push_out.returncode == 0:
                            messages.append("📤 已推送到远程仓库")
                        else:
                            # 尝试 master 分支
                            push_out2 = subprocess.run(
                                ["git", "push", "-u", "origin", "master"],
                                capture_output=True, text=True, timeout=30, cwd=str(git_dir),
                            )
                            if push_out2.returncode == 0:
                                messages.append("📤 已推送到远程仓库 (master)")
                            else:
                                messages.append(f"⚠️ 推送失败，可到配置页重试: {push_out.stderr[:200]}")
                else:
                    messages.append(f"⚠️ 关联远程失败: {add_remote.stderr[:200]}")
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)
    return JSONResponse({"ok": True, "project": row, "message": "\n".join(messages)})

async def api_ui_projects_rename(request: Request) -> JSONResponse:
    if not _webui_sessions_enabled():
        return JSONResponse({"detail": "disabled"}, status_code=404)
