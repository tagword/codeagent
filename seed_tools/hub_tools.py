"""Hub tools"""
import json
import logging
import os
from typing import Any

from seed_tools.models import Tool

logger = logging.getLogger(__name__)

# Multi-agent hub: let an agent proactively message other agents (via Hub UI bus).
async def hub_send(to: str, message: str, hub_url: str = "", frm: str = "") -> str:
    """
    Send a message to another agent via the Hub (default http://127.0.0.1:8899).

    Parameters:
      - to: agent id like agent1..agent5, or "all" to broadcast.
      - message: plain text to forward.
      - hub_url: optional override, e.g. http://127.0.0.1:8899
      - frm: optional override sender id; default from CODEAGENT_AGENT_ID.
    """
    import httpx

    to_s = (to or "").strip()
    msg_s = (message or "").strip()
    if not to_s or not msg_s:
        return json.dumps({"ok": False, "detail": "to/message required"}, ensure_ascii=False)
    hub = (hub_url or "").strip() or os.environ.get("CODEAGENT_HUB_URL", "").strip() or "http://127.0.0.1:8899"
    sender = (frm or "").strip() or os.environ.get("CODEAGENT_AGENT_ID", "").strip() or "agent?"
    payload = {"from": sender, "to": to_s, "message": msg_s}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(hub.rstrip("/") + "/api/send", json=payload)
    ct = (r.headers.get("content-type") or "").lower()
    data: Any
    if "application/json" in ct:
        data = r.json()
    else:
        data = {"raw": r.text}
    if r.status_code != 200:
        return json.dumps({"ok": False, "status": r.status_code, "response": data}, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)

hub_send_def = Tool(
    name="hub_send",
    description="Send a message to another agent via the local Multi-Agent Hub (supports to='all' broadcast).",
    parameters={
        "to": {"type": "string", "required": True, "description": "Target agent id (agent0..agent5) or 'all'"},
        "message": {"type": "string", "required": True, "description": "Message to send"},
        "hub_url": {"type": "string", "required": False, "description": "Hub base URL, default from CODEAGENT_HUB_URL or http://127.0.0.1:8899", "default": ""},
        "frm": {"type": "string", "required": False, "description": "Override sender id (default CODEAGENT_AGENT_ID)", "default": ""},
    },
    returns="string: JSON response from hub",
    category="multiagent",
)

