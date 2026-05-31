"""Image understanding: vision LLM presets or MiniMax Token Plan MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from seed.integrations.mcp_config import MINIMAX_MCP_SERVER_ID, get_server_config

MCP_VISION_SENTINEL = "__mcp_minimax__"
MINIMAX_UNDERSTAND_IMAGE_TOOL = "understand_image"
MCP_QUALIFIED_UNDERSTAND_IMAGE = f"mcp__{MINIMAX_MCP_SERVER_ID}__{MINIMAX_UNDERSTAND_IMAGE_TOOL}"


def minimax_mcp_configured(base: Optional[Path] = None) -> bool:
    """MiniMax MCP server enabled in config with a non-empty API key."""
    from seed.integrations.mcp_client import mcp_globally_enabled

    if not mcp_globally_enabled():
        return False
    cfg = get_server_config(MINIMAX_MCP_SERVER_ID, base)
    if not cfg or not cfg.enabled or not cfg.command.strip():
        return False
    key = (cfg.env or {}).get("MINIMAX_API_KEY") or ""
    return bool(str(key).strip())


def minimax_mcp_understand_image_ready(
    base: Optional[Path] = None,
    *,
    probe: bool = False,
    servers_status: Optional[list[dict[str, Any]]] = None,
) -> bool:
    """True when MiniMax MCP can run ``understand_image`` (configured; optionally probed)."""
    if not minimax_mcp_configured(base):
        return False
    if not probe:
        return True
    rows = servers_status
    if rows is None:
        from seed.integrations.mcp_client import get_mcp_manager

        rows = get_mcp_manager().list_servers_status(probe=True)
    for row in rows or []:
        if str(row.get("id") or "") != MINIMAX_MCP_SERVER_ID:
            continue
        if not row.get("connected"):
            return False
        tools = row.get("tools") or []
        return MINIMAX_UNDERSTAND_IMAGE_TOOL in tools
    return False


def image_attachment_allowed(vision_llm_id: str, base: Optional[Path] = None) -> bool:
    """User may send image attachments when a vision preset or MiniMax MCP is available."""
    vid = (vision_llm_id or "").strip()
    if vid == MCP_VISION_SENTINEL:
        return minimax_mcp_configured(base)
    if vid:
        from codeagent.core.vision_models import preset_supports_vision_id

        return preset_supports_vision_id(vid)
    return minimax_mcp_configured(base)


def video_attachment_allowed(vision_llm_id: str) -> bool:
    """Video analysis still requires a vision-capable LLM preset."""
    from codeagent.core.vision_models import preset_supports_vision_id

    vid = (vision_llm_id or "").strip()
    return bool(vid) and preset_supports_vision_id(vid)


def image_understanding_status(
    base: Optional[Path] = None,
    *,
    probe: bool = False,
    servers_status: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    configured = minimax_mcp_configured(base)
    ready = minimax_mcp_understand_image_ready(
        base, probe=probe, servers_status=servers_status
    )
    return {
        "configured": configured,
        "ready": ready,
        "sentinel": MCP_VISION_SENTINEL,
        "mcp_tool": MCP_QUALIFIED_UNDERSTAND_IMAGE,
        "minimax_server_id": MINIMAX_MCP_SERVER_ID,
    }
