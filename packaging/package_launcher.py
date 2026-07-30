"""
CodeAgent 启动器

macOS → .app 菜单栏图标 (rumps)
Windows → exe 系统托盘图标 (pystray，可选) / 无托盘后台运行
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from bundled_tools import is_frozen, setup_bundled_tools_env

# ── 平台相关导入 ──────────────────────────────────────
_PLATFORM = sys.platform
if _PLATFORM == 'darwin':
    import rumps

# PyInstaller 打包后, `sys._MEIPASS` 指向解压目录（.app/Contents/Resources 或 _MEIxxxx）
_BUNDLED = is_frozen()
if _BUNDLED:
    sys.path.insert(0, sys._MEIPASS)
    setup_bundled_tools_env()

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8899
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# 托盘图标路径
_ICON = str(
    Path(sys._MEIPASS if _BUNDLED else Path(__file__).parent.parent / "assets")
    / "tray_icon.png"
)


def _wait_for_server(url: str = SERVER_URL, timeout: float = 10.0) -> bool:
    """轮询直到服务器可访问。"""
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(f"{url}/health", timeout=2)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ═══════════════════════════════════════════════════════
#  macOS 菜单栏托盘 (rumps)
# ═══════════════════════════════════════════════════════

def _run_macos_tray() -> None:
    """运行 macOS 菜单栏托盘（阻塞）。"""

    class CodeAgentTray(rumps.App):
        def __init__(self):
            super().__init__("CodeAgent", icon=_ICON, quit_button=None)
            self.menu = [
                rumps.MenuItem("Open Browser", callback=self._open_browser),
                None,
                rumps.MenuItem("Quit", callback=self._quit_app),
            ]

        @staticmethod
        def _open_browser(_):
            webbrowser.open(SERVER_URL)

        @staticmethod
        def _quit_app(_):
            rumps.quit_application()
            os._exit(0)

    CodeAgentTray().run()


# ═══════════════════════════════════════════════════════
#  Windows / Linux 后台保活
# ═══════════════════════════════════════════════════════

def _run_background() -> None:
    """非 macOS: 保持进程存活。守护线程中的服务器会持续运行。"""
    _keep_alive = threading.Event()
    try:
        _keep_alive.wait()
    except KeyboardInterrupt:
        pass


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

def main() -> None:
    # -m 模式: 用 CodeAgent.exe -m 模块名 参数... 替代 python -m
    if len(sys.argv) >= 3 and sys.argv[1] == "-m":
        import runpy

        module = sys.argv[2]
        sys.argv = [module, *sys.argv[3:]]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return

    # 后台启动服务器
    from codeagent.server import main as server_main

    t = threading.Thread(
        target=server_main,
        args=(SERVER_HOST, SERVER_PORT),
        daemon=True,
    )
    t.start()

    # 等待就绪后自动打开浏览器
    ok = _wait_for_server()
    if ok:
        webbrowser.open(SERVER_URL)

    # 前台保持运行
    if _PLATFORM == 'darwin':
        _run_macos_tray()
    else:
        _run_background()


if __name__ == "__main__":
    main()
