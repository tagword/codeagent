"""Web UI file + setup endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. Handlers need ``project_root`` (via factory). Pure
helpers defined in ``webui_api_app`` (``_safe_under``, ``_project_fs_dir``,
``_default_agent_id``, ``_llm_probe_response``) are imported lazily inside each
handler to avoid a circular import.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

logger = logging.getLogger(__name__)


def build_files_routes(project_root: Path) -> list[Route]:
    """Return the file + setup routes for ``webui_api_app``."""

    async def api_pick_directory(_: Request) -> JSONResponse:
        from codeagent.core import env as ca_env
        from codeagent.core.folder_picker import pick_directory_sync

        skip = ca_env.pick_default("", ca_env.SKIP_FOLDER_PICKER).strip().lower()
        if skip in ("1", "true", "yes", "on"):
            return JSONResponse({"path": "", "skipped": True})
        try:
            path, skipped, hint = await asyncio.to_thread(pick_directory_sync)
        except Exception as e:
            logger.exception("pick_directory")
            return JSONResponse({"detail": str(e)}, status_code=500)
        payload: dict[str, Any] = {"path": path}
        if skipped:
            payload["skipped"] = True
        if hint:
            payload["hint"] = hint
        return JSONResponse(payload)

    async def api_files_list(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _default_agent_id, _project_fs_dir, _safe_under
        pid = (request.query_params.get("project_id") or "").strip()
        dir_q = (request.query_params.get("dir") or "").strip()
        aid = _default_agent_id()
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
        return JSONResponse({"files": items, "base_path": str(base)})

    async def api_files_read(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _default_agent_id, _project_fs_dir, _safe_under
        pid = (request.query_params.get("project_id") or "").strip()
        rel = (request.query_params.get("path") or "").strip()
        aid = _default_agent_id()
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

    async def api_files_download(request: Request) -> Response:
        from codeagent.server.webui_api_app import _default_agent_id, _project_fs_dir, _safe_under
        """GET /api/ui/files/download — download a file as attachment."""
        pid = (request.query_params.get("project_id") or "").strip()
        rel = (request.query_params.get("path") or "").strip()
        aid = _default_agent_id()
        base = _project_fs_dir(aid, pid) if pid else None
        if base is None:
            return Response("no project path", status_code=400)
        base = base.resolve()
        p = Path(rel)
        if p.is_absolute():
            p = p.resolve()
            if p == base or base in p.parents:
                fp = p
            else:
                return Response("path not under project", status_code=400)
        else:
            fp = _safe_under(base, rel.lstrip("/"))
        if fp is None or not fp.is_file():
            return Response("not found", status_code=404)
        try:
            content = fp.read_bytes()
        except OSError as e:
            return Response(str(e), status_code=500)
        filename = fp.name
        import mimetypes
        media_type, _ = mimetypes.guess_type(filename)
        if media_type is None:
            media_type = "application/octet-stream"
        # RFC 5987/6266：非 ASCII 文件名必须走 filename*=UTF-8''percent-encoded，
        # 裸 filename="中文" 会触发 latin-1 header 编码异常（UnicodeEncodeError → 500）。
        from urllib.parse import quote

        ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "'") or "download"
        disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": disposition},
        )

    async def api_project_file_serve(request: Request) -> Response:
        from codeagent.server.webui_api_app import _default_agent_id, _project_fs_dir
        """Serve a file from a known project directory by absolute path.

        Query param ``path`` — absolute filesystem path to serve (must be under a project dir).
        Returns the raw file content with proper MIME type for images, etc.
        """
        path_str = (request.query_params.get("path") or "").strip()
        if not path_str:
            return Response("path required", status_code=400)
        try:
            fp = Path(path_str).resolve()
        except OSError:
            return Response("invalid path", status_code=400)
        aid = _default_agent_id()
        # Check path is under a known project directory
        from seed.core.proj_reg import list_project_ids
        allowed = False
        for pid in list_project_ids(aid):
            base = _project_fs_dir(aid, pid)
            if base is None:
                continue
            base_r = base.resolve()
            if fp == base_r or base_r in fp.parents:
                allowed = True
                break
        if not allowed or not fp.is_file():
            return Response("not found", status_code=404)
        ext = fp.suffix.lower()
        mime_map = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
            ".ico": "image/x-icon", ".pdf": "application/pdf",
        }
        media_type = mime_map.get(ext, "application/octet-stream")
        try:
            content = fp.read_bytes()
            return Response(content=content, media_type=media_type)
        except OSError as e:
            return Response(str(e), status_code=500)

    async def api_setup_finish(_: Request) -> JSONResponse:
        """Generate Web UI token only; wizard completion is deferred to api_setup_complete."""
        tok = secrets.token_urlsafe(32)
        cfg = project_root / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        from codeagent.web.auth_impl import TOKEN_FILENAME

        (cfg / TOKEN_FILENAME).write_text(tok + "\n", encoding="utf-8")
        return JSONResponse({"webui_token": tok})

    async def api_setup_complete(_: Request) -> JSONResponse:
        from codeagent.core import env as ca_env
        from codeagent.core.seed_bridge import bridge_codeagent_env_to_seed
        from codeagent.server.webui_api_app import _write_env_file_merge
        from seed.integrations.env_config import ENV_FILENAME

        cfg = project_root / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        marker = cfg / "setup.json"
        marker.write_text(json.dumps({"done": True}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # Sensible defaults for new installs (context compact uses tokens, not bytes).
        from codeagent.runtime.compact_prompt import default_summarizer_prompt_path

        _setup_env: dict[str, str] = {
            ca_env.CONTEXT_COMPACT: "1",
            ca_env.CONTEXT_COMPACT_MIN_TOKENS: "30000",
            ca_env.CONTEXT_COMPACT_KEEP_USER_ROUNDS: "2",
            ca_env.CONTEXT_COMPACT_MID_LOOP: "1",
            ca_env.CHAT_MAX_TOOL_ROUNDS_DEFAULT: "16",
        }
        if default_summarizer_prompt_path().is_file():
            _setup_env[ca_env.CONTEXT_COMPACT_SUMMARIZER_PROMPT_FILE] = str(
                default_summarizer_prompt_path()
            )
        _write_env_file_merge(cfg / ENV_FILENAME, _setup_env)
        for k, v in _setup_env.items():
            os.environ[k] = v
        bridge_codeagent_env_to_seed()
        return JSONResponse({"ok": True})

    async def api_setup_test_llm(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _llm_probe_response

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

    # ── Agent CRUD ──────────────────────────────────────────────



    return [
        Route("/pick-directory", api_pick_directory, methods=["POST"]),
        Route("/files/list", api_files_list, methods=["GET"]),
        Route("/files/read", api_files_read, methods=["GET"]),
        Route("/files/download", api_files_download, methods=["GET"]),
        Route("/project-file", api_project_file_serve, methods=["GET"]),
        Route("/setup/finish", api_setup_finish, methods=["POST"]),
        Route("/setup/complete", api_setup_complete, methods=["POST"]),
        Route("/setup/test-llm", api_setup_test_llm, methods=["POST"]),
    ]
