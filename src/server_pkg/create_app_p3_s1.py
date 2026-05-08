async def api_ui_md_get(request: Request) -> JSONResponse:
    name = (request.path_params.get("name") or "").strip()
    if name not in CONFIG_FILENAMES:
        return JSONResponse({"detail": "unknown file"}, status_code=404)
    aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
        "CODEAGENT_AGENT_ID", "default"
    ).strip() or "default"
    ensure_default_config_files(project_root)
    try:
        from src.codeagent.core.paths import agent_persona_dir, ensure_agent_scaffold

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

async def api_ui_md_post(request: Request) -> JSONResponse:
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
                {"detail": "invalid json：请检查是否为合法 JSON，或改用纯文本保存（Web UI 已用 text/plain）。"},
                status_code=400,
            )
        except Exception:
            return JSONResponse({"detail": "invalid json body"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "JSON body must be an object"}, status_code=400)
        content = body.get("content")
        if not isinstance(content, str):
            return JSONResponse(
                {"detail": "JSON 中缺少字符串字段 content"},
                status_code=400,
            )
    else:
        raw = await request.body()
        try:
            content = raw.decode("utf-8")
        except Exception:
            content = raw.decode("utf-8", errors="replace")
    ensure_default_config_files(project_root)
    try:
        from src.codeagent.core.paths import agent_persona_dir, ensure_agent_scaffold

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

def _read_skills_state(state_path: Path) -> dict:
    """Read skills enabled-state JSON, return {name: bool}."""
    if state_path.is_file():
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {k: bool(v) for k, v in raw.items()}
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_skills_state(state_path: Path, state: dict) -> None:
    """Write skills enabled-state JSON atomically."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(state_path)


async def api_ui_skills_get(request: Request) -> JSONResponse:
    """List agent-private skill .md files (editable, with enabled/disable state)."""
    aid = (request.query_params.get("agent_id") or "").strip() or os.environ.get(
        "CODEAGENT_AGENT_ID", "default"
    ).strip() or "default"
    try:
        from src.codeagent.core.paths import agent_skills_dir, ensure_agent_scaffold
        ensure_agent_scaffold(aid, base=project_root)
        sdir = agent_skills_dir(aid, base=project_root)
        skills_dir = project_root / "config" / "skills"
        state_path = sdir / "_state.json"
        state = _read_skills_state(state_path)
        files = []
        seen = set()
        # Agent-specific skills
        if sdir.is_dir():
            for fp in sorted(sdir.iterdir()):
                if fp.name == "_state.json" or fp.name.startswith("."):
                    continue
                if fp.suffix.lower() in (".md", ".txt"):
                    enabled = state.get(fp.name, True)
                    files.append({"name": fp.name, "path": str(fp), "content": fp.read_text(encoding="utf-8"), "enabled": enabled, "scope": "agent"})
                    seen.add(fp.name)
        # Global config/skills files
        if skills_dir.is_dir():
            for fp in sorted(skills_dir.iterdir()):
                if fp.name.startswith("."):
                    continue
                if fp.suffix.lower() in (".md", ".txt") and fp.name not in seen:
                    enabled = state.get(fp.name, True)
                    files.append({"name": fp.name, "path": str(fp), "content": fp.read_text(encoding="utf-8"), "enabled": enabled, "scope": "global"})
        return JSONResponse({"skills": files})
    except Exception as e:
        logger.exception("api_ui_skills_get failed")
        return JSONResponse({"detail": str(e)}, status_code=500)

async def api_ui_skills_post(request: Request) -> JSONResponse:
    """Save (create/update/delete) an agent-private skill file, and toggle enabled state."""
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
        from src.codeagent.core.paths import agent_skills_dir, ensure_agent_scaffold
        ensure_agent_scaffold(aid, base=project_root)
        sdir = agent_skills_dir(aid, base=project_root)
        sdir.mkdir(parents=True, exist_ok=True)
        state_path = sdir / "_state.json"
        fp = sdir / name

        # Load current state
        state = _read_skills_state(state_path)

        if action == "delete":
            if fp.is_file():
                fp.unlink()
            state.pop(name, None)
            _write_skills_state(state_path, state)
            return JSONResponse({"ok": True, "hint": f"已删除 {name}"})

        # Save file content
        content = body.get("content", "")
        fp.write_text(content, encoding="utf-8")

        # Update enabled state if provided in request body
        if "enabled" in body:
            state[name] = bool(body["enabled"])
            _write_skills_state(state_path, state)

        return JSONResponse({"ok": True, "path": str(fp), "hint": f"已保存 {name}，新会话生效。"})
    except Exception as e:
        logger.exception("api_ui_skills_post failed")
        return JSONResponse({"detail": str(e)}, status_code=500)

async def api_ui_config_paths(_: Request) -> JSONResponse:
    """Return important paths for the config page."""
    root = str(project_root.resolve())
    try:
        from src.codeagent.core.paths import agent_skills_dir, agent_persona_dir
        aid = os.environ.get("CODEAGENT_AGENT_ID", "default")
        skills_path = str(agent_skills_dir(aid, base=project_root).resolve())
        persona_path = str(agent_persona_dir(aid, base=project_root).resolve())
    except Exception:
        skills_path = ""
        persona_path = ""
    return JSONResponse({
        "codeagent_root_path": root,
        "skills_path": skills_path,
        "persona_path": persona_path,
    })

async def api_ui_projects_plans(request: Request) -> JSONResponse:
    """List *-plan.md files from both user project dir and Agent data dir."""
    params = dict(request.query_params)
    project_id = params.get("project_id", "")
    aid = params.get("agent_id", "") or os.environ.get("CODEAGENT_AGENT_ID", "default")

    plans = []
    seen_names: set = set()

