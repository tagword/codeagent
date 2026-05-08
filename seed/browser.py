from __future__ import annotations

"""
Shared errors and small helpers for Chromium remote-debugging clients.

Security:
- URL / host checks live in ``browser_http``; this module holds shared primitives.
"""


import ipaddress
import os
import socket
from typing import Any, Dict, List


class BrowserError(RuntimeError):
    pass


def _runtime_evaluate_value(res: Dict[str, Any]) -> Any:
    """Extract the JSON-serializable value from a Runtime.evaluate response.

    With ``returnByValue=True`` the response shape is::

        {"result": {"type": "string|number|boolean|object|undefined", "value": ...}}

    We return the inner ``value`` verbatim so that primitives (strings, numbers,
    booleans, ``None``, arrays) survive intact.  Previously this helper forced
    the result into a dict, which meant expressions like
    ``window.app ? 'app exists' : 'app not found'`` (a string) or
    ``document.querySelectorAll('script[src]').length`` (a number) were turned
    into ``{}`` at the tool boundary, confusing the agent into thinking the
    tool was broken and spamming retries.
    """
    if not isinstance(res, dict):
        return None
    outer = res.get("result")
    if not isinstance(outer, dict):
        return None
    # ``undefined`` comes with no ``value`` key; ``null`` usually has value=None.
    if outer.get("type") == "undefined":
        return None
    if outer.get("subtype") == "null":
        return None
    if "value" in outer:
        return outer["value"]
    return outer


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _is_localhost_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("localhost", "127.0.0.1", "::1")


def _resolve_ips(host: str) -> List[str]:
    out: List[str] = []
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return out
    for fam, _t, _p, _n, addr in infos:
        try:
            if fam == socket.AF_INET:
                out.append(addr[0])
            elif fam == socket.AF_INET6:
                out.append(addr[0])
        except Exception:
            pass
    # dedupe preserving order
    seen: set[str] = set()
    ordered: List[str] = []
    for ip in out:
        if ip in seen:
            continue
        seen.add(ip)
        ordered.append(ip)
    return ordered


def _is_private_or_local_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    if addr.is_loopback:
        return True
    if addr.is_private:
        return True
    if addr.is_link_local:
        return True
    if addr.is_reserved:
        return True
    if addr.is_multicast:
        return True
    return False




"""Core browser remote-debugging manager: connection, targets, new tab."""


import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx



class BrowserManagerBase:
    """
    Process-wide manager.
    - Keeps a single browser-level WS connection and a per-target WS cache.
    """

    def __init__(self):
        self._endpoint: Optional[DebugEndpoint] = None
        self._browser_ws: Optional[_WsClient] = None
        self._target_ws: Dict[str, _WsClient] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_ok_ts: float = 0.0
        self._target_fail_counts: Dict[str, int] = {}
        self._target_blacklist: set = set()

    def _rebind_if_needed(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is loop and self._lock is not None:
            return
        self._loop = loop
        self._lock = asyncio.Lock()
        self._browser_ws = None
        self._target_ws = {}
        self._target_fail_counts = {}
        self._target_blacklist = set()

    def status(self) -> Dict[str, Any]:
        return {
            "connected": bool(self._endpoint and self._browser_ws),
            "baseurl": getattr(self._endpoint, "baseurl", ""),
            "browser_ws": getattr(self._endpoint, "browser_ws", ""),
            "targets_cached": len(self._target_ws),
            "last_ok_ts": self._last_ok_ts,
        }

    async def connect(self, baseurl: str) -> Dict[str, Any]:
        self._rebind_if_needed()
        if self._lock is None:
            raise BrowserError("browser manager lock not initialized")
        async with self._lock:
            ep = await discover_debug_endpoint(baseurl)
            if self._browser_ws:
                await self._browser_ws.close()
            for _tid, c in list(self._target_ws.items()):
                await c.close()
            self._target_ws.clear()
            self._endpoint = ep
            self._browser_ws = _WsClient(ep.browser_ws)
            await self._browser_ws.connect()
            self._last_ok_ts = time.time()
            return self.status()

    async def _ensure_connected(self) -> Tuple[DebugEndpoint, _WsClient]:
        self._rebind_if_needed()
        if self._endpoint and self._browser_ws is None:
            self._browser_ws = _WsClient(self._endpoint.browser_ws)
            await self._browser_ws.connect()
        if not self._endpoint or not self._browser_ws:
            raise BrowserError("not connected; call browser_connect or browser_ensure_running first")
        return self._endpoint, self._browser_ws

    async def list_targets(self) -> List[Dict[str, Any]]:
        ep, _ws = await self._ensure_connected()
        rows = await _http_get_json_list(ep.baseurl + "/json/list")
        self._last_ok_ts = time.time()
        return rows

    async def new_page(self) -> Dict[str, Any]:
        ep, ws = await self._ensure_connected()
        last_http_err: str = ""
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            for verb in ("put", "get"):
                try:
                    call = getattr(client, verb)
                    r = await call(ep.baseurl + "/json/new?about:blank")
                    if r.status_code == 200:
                        j = r.json()
                        if isinstance(j, dict):
                            self._last_ok_ts = time.time()
                            return j
                    last_http_err = f"{verb.upper()} /json/new -> HTTP {r.status_code}"
                except Exception as e:
                    last_http_err = f"{verb.upper()} /json/new -> {e}"
        try:
            created = await ws.call(
                "Target.createTarget",
                {"url": "about:blank"},
                timeout=10.0,
            )
        except Exception as e:
            raise BrowserError(
                f"new_page failed: http path: {last_http_err}; "
                f"Target.createTarget fallback: {e}"
            ) from e
        target_id = str(created.get("targetId") or "").strip()
        if not target_id:
            raise BrowserError(
                f"new_page: Target.createTarget returned no targetId (http path: {last_http_err})"
            )
        try:
            rows = await _http_get_json_list(ep.baseurl + "/json/list")
        except Exception:
            rows = []
        for row in rows:
            if isinstance(row, dict) and str(row.get("id") or "").strip() == target_id:
                self._last_ok_ts = time.time()
                return row
        ws_url = ""
        try:
            parsed_base = urlparse(ep.baseurl)
            netloc = parsed_base.netloc
            if netloc:
                ws_url = f"ws://{netloc}/devtools/page/{target_id}"
        except Exception:
            ws_url = ""
        self._last_ok_ts = time.time()
        return {
            "id": target_id,
            "type": "page",
            "url": "about:blank",
            "webSocketDebuggerUrl": ws_url,
            "fallback": "Target.createTarget",
        }


"""Target resolution and per-page WebSocket clients."""


import os
from typing import Any, Dict, List



class BrowserMixinTargets:
    async def _page_targets(self) -> List[Dict[str, Any]]:
        ep, _ws = await self._ensure_connected()
        rows = await _http_get_json_list(ep.baseurl + "/json/list")
        out: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("type") or "").strip() != "page":
                continue
            ws = str(row.get("webSocketDebuggerUrl") or "").strip()
            if not ws:
                continue
            out.append(row)
        return out

    async def _resolve_target_ws_url(self, target_ws_url: str) -> str:
        raw = (target_ws_url or "").strip()
        if not raw:
            raise BrowserError("target_ws_url required")
        special = raw.lower()
        page_targets = await self._page_targets()
        if special in ("active", "current", "latest", "last"):
            if not page_targets:
                raise BrowserError("no page targets available")
            return str(page_targets[-1].get("webSocketDebuggerUrl") or "").strip()
        if not raw.startswith(("ws://", "wss://")):
            raise BrowserError(
                "target_ws_url must be a ws:// devtools URL or one of: active, current, latest, last"
            )
        for row in page_targets:
            ws = str(row.get("webSocketDebuggerUrl") or "").strip()
            if ws == raw:
                return ws
        target_id = _extract_target_id_from_ws_url(raw)
        if target_id:
            for row in page_targets:
                if str(row.get("id") or "").strip() == target_id:
                    return str(row.get("webSocketDebuggerUrl") or "").strip()
        if len(page_targets) == 1:
            return str(page_targets[0].get("webSocketDebuggerUrl") or "").strip()
        if not page_targets:
            raise BrowserError("no page targets available")
        raise BrowserError(
            "target page no longer exists; call browser_targets to refresh target_ws_url"
        )

    async def _target_client(self, target_ws_url: str) -> _WsClient:
        resolved = await self._resolve_target_ws_url(target_ws_url)
        if resolved in self._target_blacklist:
            raise BrowserError(
                f"browser target is marked unhealthy (ws={resolved}) after repeated timeouts. "
                "Do NOT retry this target_ws_url. Switch strategy: "
                "(1) call browser_targets and pick a different type=page entry, "
                "(2) pass target_ws_url='active' to auto-route to the latest live page, "
                "(3) browser_new_page to open a fresh tab."
            )
        c = self._target_ws.get(resolved)
        if c:
            return c
        c = _WsClient(resolved)
        self._target_ws[resolved] = c
        try:
            await c.connect()
        except Exception:
            self._target_ws.pop(resolved, None)
            refreshed = await self._resolve_target_ws_url(target_ws_url)
            if refreshed == resolved:
                raise
            c = _WsClient(refreshed)
            self._target_ws[refreshed] = c
            await c.connect()
        return c

    async def _target_enable(self, c: _WsClient, method: str, *, timeout: float = 10.0) -> None:
        raw_thr = (
            os.environ.get("CODEAGENT_BROWSER_UNHEALTHY_THRESHOLD")
            or os.environ.get("CODEAGENT_BROWSER_CDP_UNHEALTHY_THRESHOLD")
            or "2"
        )
        threshold = int(raw_thr or "2")
        threshold = max(1, min(threshold, 20))

        ws = c.ws_url
        try:
            await c.call(method, {}, timeout=timeout)
        except Exception as e:
            self._target_fail_counts[ws] = self._target_fail_counts.get(ws, 0) + 1
            if self._target_fail_counts[ws] >= threshold:
                self._target_blacklist.add(ws)
                self._target_ws.pop(ws, None)
                try:
                    await c.close()
                except Exception:
                    pass
                raise BrowserError(
                    f"browser target became unhealthy after {self._target_fail_counts[ws]} "
                    f"consecutive {method} timeouts (ws={ws}). This target has been dropped. "
                    "Do NOT retry the same target_ws_url. Switch strategy: "
                    "(1) call browser_targets and pick another type=page target, "
                    "(2) pass target_ws_url='active', "
                    "(3) browser_new_page to open a fresh tab, or "
                    "(4) fall back to bash_exec+curl / web_fetch for HTTP-level verification."
                ) from e
            raise
        else:
            if ws in self._target_fail_counts:
                self._target_fail_counts[ws] = 0


"""Navigate, screenshot, DOM snapshot."""


import asyncio
import base64
import time
from typing import Any, Dict



class BrowserMixinPages:
    async def _wait_for_page_ready(
        self,
        c: _WsClient,
        *,
        timeout_sec: float = 15.0,
        poll_interval_sec: float = 0.3,
    ) -> Dict[str, Any]:
        deadline = time.time() + max(1.0, float(timeout_sec))
        last_state = ""
        last_href = ""
        while time.time() < deadline:
            try:
                res = await c.call(
                    "Runtime.evaluate",
                    {
                        "expression": """
        (() => ({
          readyState: String(document.readyState || ""),
          href: String(location.href || ""),
          title: String(document.title || "")
        }))()
    """,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                    timeout=5.0,
                )
                payload = _runtime_evaluate_value(res)
                if isinstance(payload, dict):
                    last_state = str(payload.get("readyState") or "")
                    last_href = str(payload.get("href") or "")
                    if last_state == "complete":
                        return {
                            "ok": True,
                            "ready_state": last_state,
                            "url": last_href,
                            "title": str(payload.get("title") or ""),
                        }
            except Exception:
                pass
            await asyncio.sleep(max(0.05, float(poll_interval_sec)))
        return {"ok": False, "ready_state": last_state, "url": last_href}

    async def navigate(self, *, url: str, target_ws_url: str) -> Dict[str, Any]:
        safe = assert_safe_navigate_url(url)
        c = await self._target_client(target_ws_url)
        await self._target_enable(c, "Page.enable")
        await c.call("Page.navigate", {"url": safe}, timeout=15.0)
        ready = await self._wait_for_page_ready(c, timeout_sec=15.0, poll_interval_sec=0.3)
        self._last_ok_ts = time.time()
        return {
            "ok": True,
            "url": safe,
            "target_ws_url": c.ws_url,
            "ready_state": str(ready.get("ready_state") or ""),
            "final_url": str(ready.get("url") or safe),
        }

    async def screenshot(self, *, target_ws_url: str, full_page: bool = False) -> Dict[str, Any]:
        c = await self._target_client(target_ws_url)
        await self._target_enable(c, "Page.enable")
        if full_page:
            try:
                m = await c.call("Page.getLayoutMetrics", {})
                css = (m.get("cssContentSize") or {}) if isinstance(m, dict) else {}
                w = int(css.get("width") or 0)
                h = int(css.get("height") or 0)
                if w > 0 and h > 0 and w <= 10000 and h <= 40000:
                    await c.call(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "mobile": False,
                            "width": w,
                            "height": h,
                            "deviceScaleFactor": 1,
                        },
                    )
            except Exception:
                pass
        res = await c.call("Page.captureScreenshot", {"format": "png"})
        data = (res.get("data") or "").strip()
        if not data:
            raise BrowserError("captureScreenshot returned empty data")
        self._last_ok_ts = time.time()
        return {
            "ok": True,
            "png_base64": data,
            "bytes": len(base64.b64decode(data)),
            "target_ws_url": c.ws_url,
        }

    async def snapshot(self, *, target_ws_url: str) -> Dict[str, Any]:
        c = await self._target_client(target_ws_url)
        res = await c.call(
            "DOMSnapshot.captureSnapshot",
            {
                "computedStyles": [],
                "includeDOMRects": True,
                "includePaintOrder": False,
            },
            timeout=20.0,
        )
        self._last_ok_ts = time.time()
        return {"ok": True, "snapshot": res, "target_ws_url": c.ws_url}


"""Compose BrowserManager from base + mixins."""



class BrowserManager(BrowserManagerBase, BrowserMixinTargets, BrowserMixinPages):
    """Combined remote-debugging browser manager."""

    pass


BROWSER = BrowserManager()


"""HTTP helpers and debug endpoint discovery for Chromium remote debugging."""


import ipaddress
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx
from urllib.parse import urlparse



def _allow_remote_debug() -> bool:
    return _env_truthy("CODEAGENT_BROWSER_ALLOW_REMOTE_DEBUG", "0") or _env_truthy(
        "CODEAGENT_BROWSER_ALLOW_REMOTE_CDP", "0"
    )


def assert_safe_debug_baseurl(baseurl: str) -> str:
    """
    Only allow connecting to localhost remote-debugging endpoints by default.
    Override with CODEAGENT_BROWSER_ALLOW_REMOTE_DEBUG=1 (legacy: CODEAGENT_BROWSER_ALLOW_REMOTE_CDP=1).
    """
    u = (baseurl or "").strip()
    if not u:
        raise BrowserError("baseurl required, e.g. http://127.0.0.1:9222")
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        raise BrowserError("baseurl must be http(s)://host:port")
    if not p.hostname:
        raise BrowserError("baseurl missing hostname")
    if _allow_remote_debug():
        return u.rstrip("/")
    if _is_localhost_host(p.hostname):
        return u.rstrip("/")
    ips = _resolve_ips(p.hostname)
    if ips and all(ipaddress.ip_address(x).is_loopback for x in ips if x):
        return u.rstrip("/")
    raise BrowserError(
        "Refuse non-local debug endpoint. Set CODEAGENT_BROWSER_ALLOW_REMOTE_DEBUG=1 to override "
        "(legacy: CODEAGENT_BROWSER_ALLOW_REMOTE_CDP=1)."
    )


def assert_safe_navigate_url(url: str) -> str:
    """
    Basic SSRF guard for navigation.
    Default: block private / loopback / link-local hosts; allow only http/https.
    Override with CODEAGENT_BROWSER_ALLOW_PRIVATE_URLS=1.
    """
    u = (url or "").strip()
    if not u:
        raise BrowserError("url required")
    if u.lower() == "about:blank":
        return "about:blank"
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        raise BrowserError("only http/https URLs are allowed (or 'about:blank')")
    host = (p.hostname or "").strip()
    if not host:
        raise BrowserError("url missing hostname")
    if _env_truthy("CODEAGENT_BROWSER_ALLOW_PRIVATE_URLS", "0"):
        return u
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        ips = _resolve_ips(host)
        if not ips:
            raise BrowserError("cannot resolve hostname")
    for ip in ips:
        if _is_private_or_local_ip(ip):
            raise BrowserError(f"blocked private/local address: {host} -> {ip}")
    return u


async def _http_get_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        r = await client.get(url, headers={"Accept": "application/json"})
        r.raise_for_status()
        j = r.json()
        if not isinstance(j, dict):
            raise BrowserError("unexpected json response")
        return j


async def _http_get_json_list(url: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        r = await client.get(url, headers={"Accept": "application/json"})
        r.raise_for_status()
        j = r.json()
        if not isinstance(j, list):
            raise BrowserError("unexpected json response")
        out: List[Dict[str, Any]] = []
        for x in j:
            if isinstance(x, dict):
                out.append(x)
        return out


@dataclass
class DebugEndpoint:
    baseurl: str  # http://127.0.0.1:9222
    browser_ws: str  # ws://127.0.0.1:9222/devtools/browser/<id>


async def discover_debug_endpoint(baseurl: str) -> DebugEndpoint:
    base = assert_safe_debug_baseurl(baseurl)
    v = await _http_get_json(base + "/json/version")
    ws = (v.get("webSocketDebuggerUrl") or "").strip()
    if not ws:
        raise BrowserError("/json/version missing webSocketDebuggerUrl")
    return DebugEndpoint(baseurl=base, browser_ws=ws)


async def probe_debug_endpoint(baseurl: str) -> Dict[str, Any]:
    """
    Best-effort health probe for a remote-debugging HTTP endpoint.
    Returns a JSON-serializable dict instead of raising for connection failures.
    """
    try:
        ep = await discover_debug_endpoint(baseurl)
        return {"ok": True, "baseurl": ep.baseurl, "browser_ws": ep.browser_ws}
    except Exception as e:
        return {"ok": False, "error": str(e), "baseurl": (baseurl or "").strip()}


"""Launch helpers for Chromium with a remote debugging port (Windows-oriented)."""


import os
import subprocess
from typing import Any, Dict, List
from urllib.parse import urlparse



def _windows_browser_candidates(browser: str) -> List[str]:
    b = (browser or "chrome").strip().lower()
    if b == "edge":
        return [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    return [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]


def _resolve_browser_executable(browser: str, explicit_path: str = "") -> str:
    if explicit_path and os.path.isfile(explicit_path):
        return explicit_path
    for p in _windows_browser_candidates(browser):
        if os.path.isfile(p):
            return p
    raise BrowserError(
        f"Cannot find browser executable for {browser!r}. "
        "Pass browser_path explicitly or install Chrome/Edge in the default location."
    )


def _default_user_data_dir_for_debug(browser: str, port: int) -> str:
    tmp = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
    name = "oa-browser-profile-edge" if (browser or "").strip().lower() == "edge" else "oa-browser-profile"
    return os.path.join(tmp, f"{name}-{port}")


def _system_user_data_dir(browser: str) -> str:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    home = os.path.expanduser("~")
    base = local or os.path.join(home, "AppData", "Local")
    if (browser or "").strip().lower() == "edge":
        return os.path.join(base, "Microsoft", "Edge", "User Data")
    return os.path.join(base, "Google", "Chrome", "User Data")


def _browser_image_name(browser: str) -> str:
    return "msedge.exe" if (browser or "").strip().lower() == "edge" else "chrome.exe"


def _extract_target_id_from_ws_url(ws_url: str) -> str:
    raw = (ws_url or "").strip()
    if not raw:
        return ""
    try:
        p = urlparse(raw)
    except Exception:
        return ""
    path = (p.path or "").rstrip("/")
    if not path:
        return ""
    return path.rsplit("/", 1)[-1].strip()


def _is_browser_running(browser: str) -> bool:
    if os.name != "nt":
        return False
    image = _browser_image_name(browser)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    try:
        r = subprocess.run(  # noqa: S603
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
            startupinfo=si,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except OSError:
        return False
    out = (r.stdout or "").strip().lower()
    if not out:
        return False
    return image.lower() in out and "no tasks are running" not in out


def _launch_browser_with_debug_port(
    *,
    browser: str,
    browser_path: str,
    port: int,
    user_data_dir: str,
    profile_directory: str = "",
    new_window: bool = True,
) -> Dict[str, Any]:
    args = [
        browser_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
    ]
    if (profile_directory or "").strip():
        args.append(f"--profile-directory={profile_directory.strip()}")
    if new_window:
        args.append("--new-window")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        proc = subprocess.Popen(  # noqa: S603
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except OSError as e:
        raise BrowserError(f"failed to launch browser: {e}") from e
    return {
        "ok": True,
        "launched": True,
        "pid": int(proc.pid),
        "browser": browser,
        "browser_path": browser_path,
        "user_data_dir": user_data_dir,
        "profile_directory": (profile_directory or "").strip(),
        "port": port,
    }


"""WebSocket client for Chromium DevTools-style JSON-RPC."""


import asyncio
import json
from typing import Any, Dict, Optional



class _WsClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None
        self._id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _rebind_if_needed(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is loop and self._lock is not None:
            return
        self._loop = loop
        self._lock = asyncio.Lock()
        self._pending = {}
        self._reader_task = None
        self._ws = None
        self._id = 0

    async def connect(self) -> None:
        self._rebind_if_needed()
        try:
            import websockets  # type: ignore
        except Exception as e:  # pragma: no cover
            raise BrowserError(
                "Missing dependency 'websockets'. Install: pip install -e \".[browser]\""
            ) from e
        if self._ws:
            return
        self._ws = await websockets.connect(self.ws_url, max_size=32 * 1024 * 1024)  # type: ignore
        self._reader_task = asyncio.create_task(self._reader(), name="browser-ws-reader")

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _reader(self) -> None:
        ws = self._ws
        if not ws:
            return
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mid = msg.get("id")
                if isinstance(mid, int) and mid in self._pending:
                    fut = self._pending.pop(mid)
                    if not fut.done():
                        fut.set_result(msg)
        except Exception as e:
            for _id, fut in list(self._pending.items()):
                if not fut.done():
                    fut.set_exception(e)
            self._pending.clear()

    async def call(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        self._rebind_if_needed()
        if self._lock is None:
            raise BrowserError("ws lock not initialized")
        async with self._lock:
            await self.connect()
            if not self._ws:
                raise BrowserError("ws not connected")
            self._id += 1
            mid = self._id
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending[mid] = fut
            payload: Dict[str, Any] = {"id": mid, "method": method}
            if params:
                payload["params"] = params
            await self._ws.send(json.dumps(payload))  # type: ignore
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as e:
            self._pending.pop(mid, None)
            raise BrowserError(f"debugger timeout calling {method}") from e
        if not isinstance(msg, dict):
            raise BrowserError("invalid debugger response")
        if "error" in msg:
            raise BrowserError(f"debugger error {method}: {msg.get('error')}")
        res = msg.get("result")
        return res if isinstance(res, dict) else {}


"""Ensure a Chromium remote-debugging HTTP endpoint is reachable (launch if needed)."""


import asyncio
import os
import time
from typing import Any, Dict
from urllib.parse import urlparse



async def ensure_browser_running(
    *,
    baseurl: str,
    browser: str = "chrome",
    browser_path: str = "",
    user_data_dir: str = "",
    use_system_profile: bool = False,
    profile_directory: str = "",
    new_window: bool = True,
    wait_timeout_sec: float = 10.0,
    poll_interval_sec: float = 0.4,
) -> Dict[str, Any]:
    """
    Idempotent helper:
    - If the debug endpoint already responds, reuse it.
    - Otherwise launch a dedicated browser instance and wait for the endpoint.
    """
    safe_base = assert_safe_debug_baseurl(baseurl)
    first = await probe_debug_endpoint(safe_base)
    if first.get("ok"):
        return {
            "ok": True,
            "reused": True,
            "launched": False,
            "baseurl": safe_base,
            "browser_ws": first.get("browser_ws", ""),
        }

    parsed = urlparse(safe_base)
    port = int(parsed.port or 9222)
    resolved_browser_path = _resolve_browser_executable(browser, explicit_path=browser_path)
    if use_system_profile:
        udd = _system_user_data_dir(browser)
        if not os.path.isdir(udd):
            raise BrowserError(f"system browser profile not found: {udd}")
        if _is_browser_running(browser):
            raise BrowserError(
                "detected an existing browser process using the main profile. "
                "Please close all Chrome/Edge windows first, then retry launching "
                "with the system profile."
            )
    else:
        udd = (user_data_dir or "").strip() or _default_user_data_dir_for_debug(browser, port)
    launch_meta = _launch_browser_with_debug_port(
        browser=browser,
        browser_path=resolved_browser_path,
        port=port,
        user_data_dir=udd,
        profile_directory=profile_directory,
        new_window=bool(new_window),
    )

    deadline = time.time() + max(1.0, float(wait_timeout_sec))
    last_err = first.get("error") or "unknown error"
    while time.time() < deadline:
        cur = await probe_debug_endpoint(safe_base)
        if cur.get("ok"):
            return {
                "ok": True,
                "reused": False,
                "launched": True,
                "baseurl": safe_base,
                "browser_ws": cur.get("browser_ws", ""),
                "launch": launch_meta,
            }
        last_err = str(cur.get("error") or last_err)
        await asyncio.sleep(max(0.1, float(poll_interval_sec)))

    raise BrowserError(
        "browser launched but remote debugging endpoint did not become ready in time: " + last_err
    )

