"""Web UI optional token gate: secret in env or local file; reset only via CLI."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote

logger = logging.getLogger(__name__)

from seed.core.config_plane import project_root  # noqa: E402

COOKIE_NAME = "ca_webui"
TOKEN_FILENAME = "codeagent.webui.token"


def _project_root() -> Path:
    return project_root()


def _token_file_path(base: Path | None = None) -> Path:
    root = base if base is not None else _project_root()
    return root / "config" / TOKEN_FILENAME


def get_webui_token(project_root: Path | None = None) -> str:
    raw = os.environ.get("CODEAGENT_WEBUI_TOKEN", "").strip()
    if raw:
        return raw
    path = _token_file_path(project_root)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def webui_auth_active(project_root: Path | None = None) -> bool:
    return bool(get_webui_token(project_root))


def _cookie_signing_key(token: str) -> bytes:
    return hmac.new(b"codeagent-webui-cookie-v1", token.encode("utf-8"), hashlib.sha256).digest()


def make_webui_cookie_value(token: str, ttl_sec: int = 604800) -> str:
    exp = int(time.time()) + max(60, int(ttl_sec))
    exp_s = str(exp).encode("utf-8")
    sig = hmac.new(_cookie_signing_key(token), exp_s, hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def verify_webui_cookie(token: str, cookie_val: str | None) -> bool:
    if not token or not cookie_val or "." not in cookie_val:
        return False
    try:
        exp_s, sig = cookie_val.rsplit(".", 1)
        exp = int(exp_s)
        if time.time() > exp:
            return False
        expected = hmac.new(
            _cookie_signing_key(token), exp_s.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected.lower(), sig.lower())
    except (ValueError, TypeError, OSError):
        return False


def _setup_incomplete(project_root: Path | None = None) -> bool:
    """True until ``config/codeagent.setup.json`` exists with ``\"done\": true``."""
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    marker = root / "config" / "codeagent.setup.json"
    if not marker.is_file():
        return True
    try:
        import json

        j = json.loads(marker.read_text(encoding="utf-8") or "{}")
        return not bool(j.get("done"))
    except Exception:
        return True


def is_setup_bootstrap_route(path: str, method: str) -> bool:
    """Allow setup wizard APIs without cookie (even when ``CODEAGENT_WEBUI_TOKEN`` is preset in env)."""
    if path.startswith("/api/ui/setup/"):
        return True
    m = (method or "").upper()
    if path == "/api/ui/llm/presets" and m in ("GET", "HEAD", "POST", "OPTIONS"):
        return True
    return bool(path == "/api/ui/llm/presets/default" and m in ("POST", "OPTIONS"))


def is_public_webui_route(path: str, method: str) -> bool:
    if path.startswith("/webhook/"):
        return True
    if path == "/setup" and method == "GET":
        return True
    if path.startswith("/api/ui/setup/"):
        return True
    # Web UI bootstrap (lets the frontend decide whether WS is enabled)
    if path == "/api/ui/flags" and method == "GET":
        return True
    if path == "/api/ui/auth/status":
        return True
    if path == "/api/ui/auth" and method == "POST":
        return True
    if path == "/api/ui/auth/logout" and method == "POST":
        return True
    return bool(method == "GET" and path in ("/icon.png", "/favicon.ico", "/health"))


def get_login_html() -> str:
    p = Path(__file__).resolve().parent.parent / "webui" / "web_login.html"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return (
        "<!DOCTYPE html><html><body><p>Missing web_login.html</p></body></html>"
    )


def _http_method_from_scope(scope: dict) -> str:
    """Starlette 0.x used bytes for scope['method']; 1.x may use str."""
    raw = scope.get("method") or "GET"
    if isinstance(raw, bytes):
        return raw.decode("ascii", errors="replace").upper()
    return str(raw).upper()


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def ws_query_token_bridge_enabled() -> bool:
    """When True, /ws may authenticate via ?webui_token= (same value as CODEAGENT_WEBUI_TOKEN).

    Use only when embedded browsers / previews do not send cookies on WebSocket handshake.
    Token appears in URLs and logs — keep off in production unless you accept that risk.
    """
    return _env_truthy("CODEAGENT_WEBUI_WS_QUERY_TOKEN", "0")


def _parse_query_params(scope: dict) -> dict[str, list[str]]:
    raw = scope.get("query_string") or b""
    qs = raw.decode("latin-1", errors="replace") if isinstance(raw, bytes) else str(raw)
    return parse_qs(qs, keep_blank_values=False)


def _first_query_value(scope: dict, key: str) -> str:
    vals = _parse_query_params(scope).get(key) or []
    return (vals[0] or "").strip() if vals else ""


def _raw_token_matches(server_token: str, presented: str) -> bool:
    if not server_token or not presented:
        return False
    a = server_token.strip().encode("utf-8")
    b = presented.strip().encode("utf-8")
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def _read_cookie_from_scope(scope: dict, name: str) -> str | None:
    prefix = name + "="
    for k, v in scope.get("headers") or []:
        key = k.decode("latin-1") if isinstance(k, bytes) else str(k)
        if key.lower() != "cookie":
            continue
        try:
            text = v.decode("latin-1") if isinstance(v, bytes) else str(v)
        except Exception:
            continue
        for segment in text.split(";"):
            segment = segment.strip()
            if segment.startswith(prefix):
                try:
                    return unquote(segment[len(prefix) :].strip())
                except Exception:
                    return None
    return None


class WebUIAuthMiddleware:
    """ASGI middleware: require signed cookie when Web UI token is configured."""

    def __init__(self, app, *, project_root: Path):
        self.app = app
        self.project_root = Path(project_root).resolve()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            path = scope.get("path") or ""
            tok = get_webui_token(self.project_root)
            # Some dev proxies / IDE previews rewrite websocket paths like:
            #   /ws//127.0.0.1%3A8765/ws?...  (still our Web UI websocket)
            if tok and (path == "/ws" or path.startswith("/ws/")):
                ck = _read_cookie_from_scope(scope, COOKIE_NAME)
                ok = verify_webui_cookie(tok, ck)
                if not ok and ws_query_token_bridge_enabled():
                    ok = _raw_token_matches(tok, _first_query_value(scope, "webui_token"))
                if not ok:
                    from starlette.responses import PlainTextResponse
                    from starlette.websockets import WebSocket

                    ws = WebSocket(scope, receive, send)
                    logger.info(
                        "WebSocket /ws rejected (403): invalid or missing Web UI auth "
                        "(cookie / optional webui_token query). Path=%r",
                        path,
                    )
                    try:
                        await ws.send_denial_response(
                            PlainTextResponse(
                                "Web UI auth required: open the app in a normal browser and log in, "
                                "or set CODEAGENT_WEBUI_WS_QUERY_TOKEN=1 and reconnect after login "
                                "(webui_token query bridge).\n",
                                status_code=403,
                            )
                        )
                    except RuntimeError:
                        await ws.close(code=4401)
                    return
            await self.app(scope, receive, send)
            return

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        method = _http_method_from_scope(scope)
        tok = get_webui_token(self.project_root)
        # If setup hasn't been completed yet, allow the root page to load the setup UI
        # even when a token exists (otherwise users get stuck at login before setup).
        if tok and method == "GET" and path == "/":
            try:
                marker = self.project_root / "config" / "codeagent.setup.json"
                if marker.is_file():
                    import json

                    j = json.loads(marker.read_text(encoding="utf-8") or "{}")
                    if not bool(j.get("done")):
                        await self.app(scope, receive, send)
                        return
                else:
                    # No marker yet => not set up
                    await self.app(scope, receive, send)
                    return
            except Exception:
                # Fail open for setup bootstrap
                await self.app(scope, receive, send)
                return
        if not tok or is_public_webui_route(path, method):
            await self.app(scope, receive, send)
            return
        ck = _read_cookie_from_scope(scope, COOKIE_NAME)
        if verify_webui_cookie(tok, ck):
            await self.app(scope, receive, send)
            return

        # Wizard step 1 saves LLM presets before user gets a signed cookie; env token alone must not block.
        if tok and _setup_incomplete(self.project_root) and is_setup_bootstrap_route(path, method):
            await self.app(scope, receive, send)
            return

        from starlette.responses import HTMLResponse, JSONResponse

        if method == "GET" and path == "/":
            resp = HTMLResponse(get_login_html(), status_code=200)
            await resp(scope, receive, send)
            return

        resp = JSONResponse({"detail": "webui auth required"}, status_code=401)
        await resp(scope, receive, send)
