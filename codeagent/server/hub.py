"""Hub — multi-agent message bus with SSE streaming.

Messages flow: Agent A → POST /api/hub/send → persist → SSE stream → Agent B

Architecture:
- Incoming messages are persisted to ~/.codeagent/hub/ as JSON files
- SSE subscribers get real-time delivery via an in-memory event queue
- `last-event-id` support for reconnection (replays missed events)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, AsyncGenerator

from codeagent.core.paths import codeagent_home

logger = logging.getLogger(__name__)

# ── In-memory SSE event queue ─────────────────────────────────
# {subscriber_id: asyncio.Queue}
_sse_subscribers: dict[str, asyncio.Queue] = {}


def _hub_dir() -> Path:
    p = codeagent_home() / "hub"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hub_msgs_path() -> Path:
    """Single JSON lines file for all hub messages (append-only)."""
    return _hub_dir() / "messages.jl"


def _persist_message(msg: dict) -> None:
    """Append a message to the messages.jl file."""
    path = _hub_msgs_path()
    try:
        with open(str(path), "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("hub persist failed: %s", e)


def load_messages(
    since_id: str | None = None,
    limit: int = 100,
    filter_agent: str | None = None,
) -> list[dict]:
    """Load messages from the persisted file, newest first."""
    path = _hub_msgs_path()
    if not path.is_file():
        return []
    msgs: list[dict] = []
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msgs.append(msg)
    except OSError:
        return []

    # Filter by since_id
    if since_id:
        idx = -1
        for i, m in enumerate(msgs):
            if m.get("id") == since_id:
                idx = i
                break
        if idx >= 0:
            msgs = msgs[idx + 1:]

    # Filter by agent
    if filter_agent:
        msgs = [m for m in msgs if m.get("frm") == filter_agent or m.get("to") == filter_agent]

    # Return newest first, limited
    msgs.reverse()
    return msgs[:limit]


def send_message(frm: str, to: str, content: str, msg_type: str = "text") -> dict:
    """Create, persist, and broadcast a hub message."""
    msg = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "frm": frm,
        "to": to,
        "type": msg_type,
        "content": content,
    }
    _persist_message(msg)
    _broadcast(msg)
    return msg


def _broadcast(msg: dict) -> None:
    """Push a message to all active SSE subscribers."""
    dead: list[str] = []
    for sid, q in _sse_subscribers.items():
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(sid)
        except Exception:
            dead.append(sid)
    for sid in dead:
        _sse_subscribers.pop(sid, None)


def subscribe() -> tuple[str, asyncio.Queue]:
    """Register a new SSE subscriber. Returns (subscriber_id, queue)."""
    sid = uuid.uuid4().hex[:8]
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    _sse_subscribers[sid] = q
    return sid, q


def unsubscribe(sid: str) -> None:
    """Remove an SSE subscriber."""
    _sse_subscribers.pop(sid, None)


async def sse_generator(
    subscriber_id: str,
    queue: asyncio.Queue,
    last_event_id: str | None = None,
) -> AsyncGenerator[bytes, None]:
    """Async generator for SSE streaming.

    Yields SSE-format bytes. Supports last-event-id for reconnection.
    """
    # Replay missed messages if last_event_id provided
    if last_event_id:
        missed = load_messages(since_id=last_event_id)
        for msg in reversed(missed):
            yield _format_sse(msg)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
                yield _format_sse(msg)
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield b": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        unsubscribe(subscriber_id)


def _format_sse(msg: dict) -> bytes:
    """Format a message dict as SSE bytes."""
    data = json.dumps(msg, ensure_ascii=False)
    lines = [
        f"id: {msg.get('id', '')}",
        f"event: message",
        f"data: {data}",
        "",
    ]
    return "\n".join(lines).encode("utf-8") + b"\n"
