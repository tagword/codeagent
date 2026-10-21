"""Web UI env + LLM preset endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. Handlers need ``project_root`` (via factory). Pure env
helpers defined in ``webui_api_app`` (``_env_chat_specs``, ``_env_chat_view``,
``_env_view_from_specs``, ``_llm_probe_response``, ``_write_env_file_merge``)
are imported lazily inside each handler to avoid a circular import.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from codeagent.core.default_presets import (
    SLOTS as DEFAULT_PRESET_SLOTS,
)
from codeagent.core.default_presets import (
    get_default_preset_ids,
    set_default_preset_id_for_slot,
)
from seed.core.llm_presets import (
    _validate_preset,
    get_default_preset_id,
    load_presets,
    save_presets,
    set_default_preset_id,
)
from seed.integrations.env_config import ENV_FILENAME

logger = logging.getLogger(__name__)


def build_envllm_routes(project_root: Path) -> list[Route]:
    """Return the env + LLM-preset routes for ``webui_api_app``."""

    async def api_env_chat_get(_: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _env_chat_view
        return JSONResponse(_env_chat_view(project_root))

    def _env_mcp_specs() -> list[tuple[tuple[str, ...], str]]:
        from seed.core.env_access import MCP_CALL_TIMEOUT, MCP_ENABLED, MCP_REGISTER_TOOLS

        return [
            (MCP_ENABLED, "1"),
            (MCP_REGISTER_TOOLS, "1"),
            (MCP_CALL_TIMEOUT, "120"),
        ]

    def _env_mcp_view(root: Path) -> dict[str, str]:
        from codeagent.server.webui_api_app import _env_view_from_specs

        return _env_view_from_specs(root, _env_mcp_specs())

    async def api_env_mcp_get(_: Request) -> JSONResponse:
        return JSONResponse(_env_mcp_view(project_root))

    async def api_env_mcp_post(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _write_env_file_merge
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        updates: dict[str, str] = {}
        for keys, _default in _env_mcp_specs():
            canonical = keys[0]
            for k in keys:
                if k in body:
                    updates[canonical] = str(body[k])
                    break
        if not updates:
            return JSONResponse({"detail": "no known keys"}, status_code=400)
        from seed.integrations.env_config import ENV_FILENAME

        _write_env_file_merge(project_root / "config" / ENV_FILENAME, updates)
        for k, v in updates.items():
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        from codeagent.core.seed_bridge import bridge_codeagent_env_to_seed

        bridge_codeagent_env_to_seed()
        from codeagent.tools.agent_tools import reset_agent_tools_cache
        from seed.integrations.mcp_client import reset_mcp_manager

        reset_mcp_manager()
        reset_agent_tools_cache()
        return JSONResponse({"ok": True, "hint": "已写入 config/env；重启服务后 MCP 开关完全生效。"})

    async def api_env_chat_post(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _env_chat_specs, _write_env_file_merge
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        updates: dict[str, str] = {}
        for keys, _default in _env_chat_specs():
            canonical = keys[0]
            for k in keys:
                if k in body:
                    updates[canonical] = str(body[k])
                    break
        if not updates:
            return JSONResponse({"detail": "no known keys"}, status_code=400)
        p = project_root / "config" / ENV_FILENAME
        _write_env_file_merge(p, updates)
        for k, v in updates.items():
            if v:
                os.environ[k] = v
            else:
                # 空值表示"取消设置"，避免下游 pick_default("262144", ...) 读到空串 -> int('') 崩溃
                os.environ.pop(k, None)
        from codeagent.core.seed_bridge import bridge_codeagent_env_to_seed

        bridge_codeagent_env_to_seed()
        # bridge 只设 SEED_* 未定义的情况；显式保存时强制覆盖
        for k, v in updates.items():
            sk = "SEED_" + k[len("CODEAGENT_") :] if k.startswith("CODEAGENT_") else None
            if sk:
                if v:
                    os.environ[sk] = v
                else:
                    os.environ.pop(sk, None)
        return JSONResponse({"ok": True, "hint": "已写入 config/env；内核项已同步 SEED_*。"})

    async def api_tts_options(_: Request) -> JSONResponse:
        from codeagent.core.speech_synth import minimax_tts_configured
        from codeagent.core.tts_voices import tts_options_payload

        return JSONResponse(tts_options_payload(configured=minimax_tts_configured(project_root)))

    async def api_llm_presets_get(_: Request) -> JSONResponse:
        from seed_model_providers import enrich_presets_for_ui, list_provider_catalog

        default_ids = get_default_preset_ids()
        return JSONResponse(
            {
                "presets": enrich_presets_for_ui(load_presets()),
                # New: per-slot default map (slot → preset_id)
                "default_preset_ids": default_ids,
                "default_slots": list(DEFAULT_PRESET_SLOTS),
                # Legacy: kept so older UI code still gets the chat default
                "default_id": default_ids.get("chat", get_default_preset_id()),
                "providers": list_provider_catalog(),
            }
        )

    async def api_llm_providers_get(_: Request) -> JSONResponse:
        from seed_model_providers import list_provider_catalog

        return JSONResponse({"providers": list_provider_catalog()})

    async def api_llm_presets_post(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        from seed_model_providers import materialize_preset_from_form, provider_requires_api_key

        body = materialize_preset_from_form(body)
        err = _validate_preset(body)
        if err:
            return JSONResponse({"detail": err}, status_code=400)
        prov = str(body.get("provider") or "").strip()
        if provider_requires_api_key(prov) and not str(body.get("api_key") or "").strip():
            return JSONResponse({"detail": "该服务商需要填写 API Key"}, status_code=400)
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
        return JSONResponse({"ok": True, "preset_id": pid})

    async def api_llm_presets_default(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        pid = str(body.get("preset_id") or "").strip()
        use_type = str(body.get("use_type") or "chat").strip() or "chat"
        if use_type not in DEFAULT_PRESET_SLOTS:
            return JSONResponse(
                {"detail": f"use_type must be one of {list(DEFAULT_PRESET_SLOTS)}"},
                status_code=400,
            )
        set_default_preset_id_for_slot(use_type, pid)
        # Keep seed's legacy single-id in sync for the chat slot so other
        # in-process callers (speech_synth etc.) keep working.
        if use_type == "chat":
            set_default_preset_id(pid)
        return JSONResponse(
            {"ok": True, "use_type": use_type, "preset_id": pid,
             "default_preset_ids": get_default_preset_ids()}
        )

    async def api_llm_presets_delete(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        pid = str(body.get("preset_id") or "").strip()
        presets = [p for p in load_presets() if str(p.get("id") or "").strip() != pid]
        save_presets(presets)
        # Clear this preset from default_preset_ids for any slot
        cur_defaults = get_default_preset_ids()
        changed = False
        for slot, def_pid in list(cur_defaults.items()):
            if def_pid == pid:
                set_default_preset_id_for_slot(slot, "")
                changed = True
        # Legacy single-id sync (chat only)
        if get_default_preset_id() == pid:
            set_default_preset_id("")
        return JSONResponse({"ok": True, "defaults_changed": changed})

    async def api_llm_presets_test(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _llm_probe_response
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        from seed_model_providers import materialize_preset_from_form

        body = materialize_preset_from_form(body)
        return await _llm_probe_response(body)



    return [
        Route("/env/chat", api_env_chat_get, methods=["GET"]),
        Route("/env/chat", api_env_chat_post, methods=["POST"]),
        Route("/env/mcp", api_env_mcp_get, methods=["GET"]),
        Route("/env/mcp", api_env_mcp_post, methods=["POST"]),
        Route("/tts/options", api_tts_options, methods=["GET"]),
        Route("/llm/presets", api_llm_presets_get, methods=["GET"]),
        Route("/llm/presets", api_llm_presets_post, methods=["POST"]),
        Route("/llm/providers", api_llm_providers_get, methods=["GET"]),
        Route("/llm/presets/default", api_llm_presets_default, methods=["POST"]),
        Route("/llm/presets/delete", api_llm_presets_delete, methods=["POST"]),
        Route("/llm/presets/test", api_llm_presets_test, methods=["POST"]),
    ]
