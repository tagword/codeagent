"""Browser automation tools (Chrome/Edge remote debugging)."""
import os
import json
from seed_tools.models import Tool

# -----------------------------
# Browser tools (MVP)
# -----------------------------
async def browser_status() -> str:
    """Return current browser debugger connection status."""
    try:
        from seed.browser import BROWSER

        return json.dumps(BROWSER.status(), ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"

browser_status_def = Tool(
    name="browser_status",
    description="Get browser remote-debugging connection status (base URL, cached targets, last ok time).",
    parameters={},
    returns="string: JSON status",
    category="browser",
)

async def browser_connect(baseurl: str) -> str:
    """Connect to an existing Chromium remote-debugging endpoint (requires --remote-debugging-port)."""
    from seed.browser import BROWSER

    st = await BROWSER.connect(baseurl)
    return json.dumps(st, ensure_ascii=False)

browser_connect_def = Tool(
    name="browser_connect",
    description=(
        "Connect to a local Chromium remote-debugging endpoint, "
        "e.g. http://127.0.0.1:9222 (browser must be started with --remote-debugging-port)."
    ),
    parameters={
        "baseurl": {
            "type": "string",
            "required": True,
            "description": "Base URL like http://127.0.0.1:9222",
        },
    },
    returns="string: JSON status",
    category="browser",
)

async def browser_ensure_running(
    baseurl: str = "http://127.0.0.1:9222",
    browser: str = "chrome",
    browser_path: str = "",
    user_data_dir: str = "",
    use_system_profile: bool = False,
    profile_directory: str = "",
    new_window: bool = True,
) -> str:
    """
    Reuse an existing local debugging endpoint if present; otherwise launch a dedicated browser instance.
    """
    from seed.browser import BROWSER, ensure_browser_running

    if not use_system_profile:
        use_system_profile = os.environ.get("CODEAGENT_BROWSER_USE_SYSTEM_PROFILE", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    if not profile_directory:
        profile_directory = os.environ.get("CODEAGENT_BROWSER_PROFILE_DIRECTORY", "").strip()
    if not user_data_dir:
        user_data_dir = os.environ.get("CODEAGENT_BROWSER_USER_DATA_DIR", "").strip()
    if not browser_path:
        browser_path = os.environ.get("CODEAGENT_BROWSER_PATH", "").strip()
    if not browser or browser == "chrome":
        browser = os.environ.get("CODEAGENT_BROWSER_KIND", browser).strip() or "chrome"

    res = await ensure_browser_running(
        baseurl=baseurl,
        browser=browser,
        browser_path=browser_path,
        user_data_dir=user_data_dir,
        use_system_profile=bool(use_system_profile),
        profile_directory=profile_directory,
        new_window=bool(new_window),
    )
    # Connect manager after ensure so later browser_* calls can reuse the session.
    st = await BROWSER.connect(baseurl)
    return json.dumps({"ensure": res, "status": st}, ensure_ascii=False)

browser_ensure_running_def = Tool(
    name="browser_ensure_running",
    description=(
        "Ensure a local Chromium remote-debugging endpoint is available. "
        "If http://127.0.0.1:9222 already responds, reuse it; otherwise launch a dedicated Chrome/Edge instance and connect."
    ),
    parameters={
        "baseurl": {
            "type": "string",
            "required": False,
            "description": "Remote debugging base URL like http://127.0.0.1:9222",
            "default": "http://127.0.0.1:9222",
        },
        "browser": {
            "type": "string",
            "required": False,
            "description": "chrome or edge",
            "default": "chrome",
        },
        "browser_path": {
            "type": "string",
            "required": False,
            "description": "Optional explicit browser executable path",
        },
        "user_data_dir": {
            "type": "string",
            "required": False,
            "description": "Optional dedicated user data dir; default uses a temp profile",
        },
        "use_system_profile": {
            "type": "boolean",
            "required": False,
            "description": "Use the system browser user-data directory so login state/cookies can be reused; close existing browser windows first",
            "default": False,
        },
        "profile_directory": {
            "type": "string",
            "required": False,
            "description": "Optional Chromium profile directory name like Default or Profile 1 when use_system_profile=true",
        },
        "new_window": {
            "type": "boolean",
            "required": False,
            "description": "Launch browser with --new-window when starting a new instance",
            "default": True,
        },
    },
    returns="string: JSON ensure+connect result",
    category="browser",
)

async def browser_targets() -> str:
    """List debuggable targets."""
    from seed.browser import BROWSER

    rows = await BROWSER.list_targets()
    return json.dumps({"targets": rows}, ensure_ascii=False)

browser_targets_def = Tool(
    name="browser_targets",
    description="List current debug targets (pages/tabs) with webSocketDebuggerUrl.",
    parameters={},
    returns="string: JSON {targets:[...]}",
    category="browser",
)

async def browser_new_page() -> str:
    """Create a new about:blank tab."""
    from seed.browser import BROWSER

    t = await BROWSER.new_page()
    return json.dumps(t, ensure_ascii=False)

browser_new_page_def = Tool(
    name="browser_new_page",
    description="Create a new blank page target; returns target descriptor (includes webSocketDebuggerUrl).",
    parameters={},
    returns="string: JSON target descriptor",
    category="browser",
)

async def browser_navigate(target_ws_url: str, url: str) -> str:
    """Navigate a target page to URL (with SSRF guard by default)."""
    from seed.browser import BROWSER

    res = await BROWSER.navigate(target_ws_url=target_ws_url, url=url)
    return json.dumps(res, ensure_ascii=False)

browser_navigate_def = Tool(
    name="browser_navigate",
    description=(
        "Navigate a page target to the given URL. "
        "Default blocks private/local IPs unless CODEAGENT_BROWSER_ALLOW_PRIVATE_URLS=1."
    ),
    parameters={
        "target_ws_url": {
            "type": "string",
            "required": True,
            "description": "Target webSocketDebuggerUrl (ws://.../devtools/page/...) or one of: active, current, latest, last",
        },
        "url": {"type": "string", "required": True, "description": "Destination URL (http/https)"},
    },
    returns="string: JSON result",
    category="browser",
)

async def browser_screenshot(target_ws_url: str, full_page: bool = False) -> str:
    """Capture a screenshot as base64 PNG."""
    from seed.browser import BROWSER

    res = await BROWSER.screenshot(target_ws_url=target_ws_url, full_page=bool(full_page))
    # Do not return the full base64 to the model by default (it is huge).
    # Return metadata + a short prefix so the user can choose to fetch full data via UI endpoint.
    b64 = str(res.get("png_base64") or "")
    meta = {k: v for k, v in res.items() if k != "png_base64"}
    meta["png_base64_prefix"] = b64[:120] + ("..." if len(b64) > 120 else "")
    meta["png_base64_len"] = len(b64)
    return json.dumps(meta, ensure_ascii=False)

browser_screenshot_def = Tool(
    name="browser_screenshot",
    description=(
        "Capture a PNG screenshot of a page target. Returns metadata and a short base64 prefix only "
        "(full image omitted by default due to size)."
    ),
    parameters={
        "target_ws_url": {
            "type": "string",
            "required": True,
            "description": "Target webSocketDebuggerUrl or active/current/latest/last",
        },
        "full_page": {
            "type": "boolean",
            "required": False,
            "description": "Capture full scrollable page",
            "default": False,
        },
    },
    returns="string: JSON screenshot metadata",
    category="browser",
)
