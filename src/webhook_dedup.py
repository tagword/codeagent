"""In-memory TTL deduplication for inbound webhooks (platform retries)."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_seen: Dict[str, float] = {}

_ID_FIELDS = (
    "delivery_id",
    "webhook_delivery_id",
    "idempotency_key",
    "event_id",
    "dedup_key",
    "webhook_id",
    "request_id",
)


def _scalar_id(v: Any) -> Optional[str]:
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return None


def _pick_id_from_dict(obj: Dict[str, Any], depth: int = 0) -> Optional[str]:
    if depth > 4 or not isinstance(obj, dict):
        return None
    for k in _ID_FIELDS:
        if k in obj:
            sid = _scalar_id(obj.get(k))
            if sid:
                return sid
    for nested_key in ("data", "payload", "body", "event", "object"):
        nested = obj.get(nested_key)
        if isinstance(nested, dict):
            sid = _pick_id_from_dict(nested, depth + 1)
            if sid:
                return sid
    return None


def compute_webhook_dedup_key(data: Dict[str, Any], raw_body: bytes) -> str:
    """
    Prefer platform-provided delivery / event id; otherwise hash identical raw body
    (retries usually reuse the same payload).
    """
    picked = _pick_id_from_dict(data)
    if picked:
        return f"id:{picked}"
    h = hashlib.sha256(raw_body).hexdigest()
    return f"body:{h}"


def _dedup_ttl_sec() -> float:
    raw = os.environ.get("CODEAGENT_WEBHOOK_DEDUP_TTL_SEC", "86400").strip()
    try:
        v = float(raw)
    except ValueError:
        v = 86400.0
    return max(60.0, v)


def _dedup_max_keys() -> int:
    raw = os.environ.get("CODEAGENT_WEBHOOK_DEDUP_MAX_KEYS", "20000").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 20000
    return max(100, min(n, 500_000))


def dedup_enabled() -> bool:
    return os.environ.get("CODEAGENT_WEBHOOK_DEDUP", "1").lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def try_acquire(dedup_key: str) -> bool:
    """
    If *dedup_key* was seen within TTL, return False (duplicate). Otherwise record and return True.
    """
    if not dedup_key:
        return True
    ttl = _dedup_ttl_sec()
    max_keys = _dedup_max_keys()
    now = time.time()
    with _lock:
        dead = [k for k, seen_at in _seen.items() if now - seen_at > ttl]
        for k in dead:
            del _seen[k]
        if dedup_key in _seen:
            logger.info("webhook dedup skip key=%s", dedup_key[:80])
            return False
        _seen[dedup_key] = now
        if len(_seen) > max_keys:
            for k, _ in sorted(_seen.items(), key=lambda kv: kv[1])[
                : len(_seen) - max_keys + 1000
            ]:
                del _seen[k]
    return True


def try_acquire_report(dedup_key: str) -> Tuple[bool, str]:
    """Returns (is_new, dedup_key)."""
    if not dedup_enabled():
        return True, dedup_key
    ok = try_acquire(dedup_key)
    return ok, dedup_key


def reset_webhook_dedup_cache() -> None:
    """Clear dedup memory (for tests)."""
    with _lock:
        _seen.clear()
