"""Web UI skills + config-paths endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui`` (outer Mount adds prefix). These handlers need
``project_root``, so they live behind a ``build_skills_routes(project_root)``
factory that closes over it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)


def _default_agent_id() -> str:
    from codeagent.core import env as ca_env

    return ca_env.default_agent_id()


def build_skills_routes(project_root: Path) -> list[Route]:
    """Return the skills + config-paths routes for ``webui_api_app``."""

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

    def _api_scan_skills_dir(
        directory: Path,
        state: dict[str, bool],
        scope: str,
        seen: set[str] | None = None,
    ) -> list[dict]:
        """Scan a single skills directory for flat .md and skills/<name>/SKILL.md."""
        if seen is None:
            seen = set()
        files: list[dict] = []
        if not directory.is_dir():
            return files

        # 1st pass: flat .md files
        for fp in sorted(directory.iterdir()):
            if fp.name == "_state.json" or fp.name.startswith("."):
                continue
            if fp.suffix.lower() not in (".md", ".txt"):
                continue
            if fp.name in seen:
                continue
            enabled = state.get(fp.name, True)
            files.append(
                {
                    "name": fp.name,
                    "path": str(fp),
                    "content": fp.read_text(encoding="utf-8"),
                    "enabled": enabled,
                    "scope": scope,
                }
            )
            seen.add(fp.name)

        # 2nd pass: directory format skills/<name>/SKILL.md
        for fp in sorted(directory.glob("*/SKILL.md")):
            dirname = fp.parent.name
            if dirname.startswith("."):
                continue
            state_key = f"{dirname}.md"
            if state_key in seen:
                continue
            enabled = state.get(state_key, True)
            files.append(
                {
                    "name": state_key,
                    "path": str(fp),
                    "content": fp.read_text(encoding="utf-8"),
                    "enabled": enabled,
                    "scope": scope,
                    "format": "dir",
                }
            )
            seen.add(state_key)

        return files

    async def api_skills_get(request: Request) -> JSONResponse:
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        project_path_str = (request.query_params.get("project_path") or "").strip()
        project_id_str = (request.query_params.get("project_id") or "").strip()
        # Resolve project_path from project_id if provided
        if not project_path_str and project_id_str:
            try:
                from seed.core.proj_reg import resolve_project_path
                project_path_str = resolve_project_path(aid, project_id_str)
            except Exception:
                pass
        try:
            from codeagent.core.paths import agent_skills_dir, ensure_agent_scaffold

            ensure_agent_scaffold(aid, base=project_root)
            sdir = agent_skills_dir(aid, base=project_root)
            skills_dir = project_root / "config" / "skills"
            state_path = sdir / "_state.json"
            state = _api_read_skills_state(state_path)
            files: list[dict] = []
            seen: set[str] = set()

            # 1. Project-level skills (if project_path is given)
            if project_path_str:
                pdir = Path(project_path_str).resolve() / ".codeagent" / aid / "skills"
                if pdir.is_dir():
                    pstate_path = pdir / "_state.json"
                    pstate = _api_read_skills_state(pstate_path)
                    files.extend(_api_scan_skills_dir(pdir, pstate, "project", seen))

            # 2. Agent-level skills
            if sdir.is_dir():
                files.extend(_api_scan_skills_dir(sdir, state, "agent", seen))

            # 3. Global config/skills/*.md
            if skills_dir.is_dir():
                gseen = {f["name"] for f in files}
                for fp in sorted(skills_dir.iterdir()):
                    if fp.name.startswith("."):
                        continue
                    if fp.suffix.lower() in (".md", ".txt") and fp.name not in gseen:
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
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        project_path_str = (request.query_params.get("project_path") or "").strip()
        project_id_str = (request.query_params.get("project_id") or "").strip()
        # Resolve project_path from project_id if provided
        if not project_path_str and project_id_str:
            try:
                from seed.core.proj_reg import resolve_project_path
                project_path_str = resolve_project_path(aid, project_id_str)
            except Exception:
                pass
        action = body.get("action", "save")
        name = (body.get("name") or "").strip()
        if not name or "/" in name or "\\" in name:
            return JSONResponse({"detail": "invalid name"}, status_code=400)
        try:
            from codeagent.core.paths import agent_skills_dir, ensure_agent_scaffold

            # Determine target directory
            if project_path_str:
                sdir = Path(project_path_str).resolve() / ".codeagent" / aid / "skills"
            else:
                ensure_agent_scaffold(aid, base=project_root)
                sdir = agent_skills_dir(aid, base=project_root)
            sdir.mkdir(parents=True, exist_ok=True)
            state_path = sdir / "_state.json"

            # New directory format: skills/<name>/SKILL.md
            dir_format = sdir / name  # <name> dir
            flat_file = sdir / f"{name}.md"

            # Load current state
            state = _api_read_skills_state(state_path)
            state_key = f"{name}.md"

            if action == "delete":
                # Try directory format first, then flat
                if dir_format.is_dir():
                    import shutil
                    shutil.rmtree(dir_format)
                elif flat_file.is_file():
                    flat_file.unlink()
                state.pop(state_key, None)
                _api_write_skills_state(state_path, state)
                return JSONResponse({"ok": True, "hint": f"已删除 {name}"})

            content = body.get("content", "")
            # Prefer directory format for new saves
            fp = dir_format / "SKILL.md"
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(str(content), encoding="utf-8")

            # Remove stale flat file if it exists
            if flat_file.is_file():
                flat_file.unlink()

            # Update enabled state if provided
            if "enabled" in body:
                state[state_key] = bool(body["enabled"])
                _api_write_skills_state(state_path, state)

            return JSONResponse({"ok": True, "path": str(fp), "hint": f"已保存 {name}，新会话生效。"})
        except Exception as e:
            logger.exception("api_skills_post")
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def api_config_paths(_: Request) -> JSONResponse:
        root = str(project_root.resolve())
        try:
            from codeagent.core.paths import agent_persona_dir, agent_skills_dir

            aid = _default_agent_id()
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



    return [
        Route("/skills", api_skills_get, methods=["GET"]),
        Route("/skills", api_skills_post, methods=["POST"]),
        Route("/config/paths", api_config_paths, methods=["GET"]),
    ]
