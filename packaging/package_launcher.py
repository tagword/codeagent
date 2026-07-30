"""
CodeAgent 启动器

macOS → .app 菜单栏图标 (rumps)
Windows / Linux → 系统托盘图标 (pystray) / 无托盘后台保活（保底）
"""
import os
import sys
import tempfile
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

# 端口与项目默认一致 (codeagent serve → 8765)
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
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


def _report_server_not_ready() -> None:
    """弹出错误消息框（Windows）或打印到 stderr（其它平台）。"""
    msg = (
        f"CodeAgent Web 服务器未能在预期时间内启动。\n"
        f"请检查防火墙或端口 {SERVER_PORT} 是否被占用，\n"
        f"然后手动打开浏览器访问 {SERVER_URL}\n\n"
        f"启动日志（如有）：{_SERVER_LOG}"
    )
    if _PLATFORM == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "CodeAgent", 0x10 | 0x1000)
            return
        except Exception:
            pass
    print(msg, file=sys.stderr)


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
#  Windows / Linux 系统托盘图标 (pystray)
# ═══════════════════════════════════════════════════════

def _run_tray() -> None:
    """pystray 系统托盘图标（阻塞）。"""
    import pystray
    from PIL import Image

    icon_img = Image.open(_ICON)

    def on_open(_icon, _item):
        webbrowser.open(SERVER_URL)

    def on_quit(_icon, _item):
        _icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open Browser", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon("CodeAgent", icon_img, "CodeAgent", menu)
    icon.run()


def _run_background() -> None:
    """纯后台保活（pystray 不可用时的保底方案）。"""
    _keep_alive = threading.Event()
    try:
        _keep_alive.wait()
    except KeyboardInterrupt:
        pass


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

# 服务器启动日志（用于排查启动失败原因；写入用户临时目录确保可写）
_SERVER_LOG = os.path.join(tempfile.gettempdir(), "codeagent_server_startup.log")


def _run_server() -> None:
    """在后台线程中启动服务器，异常时写入日志。"""
    import traceback

    try:
        from codeagent.server import main as server_main

        server_main(SERVER_HOST, SERVER_PORT)
    except Exception:
        try:
            with open(_SERVER_LOG, "w", encoding="utf-8") as f:
                f.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"服务器启动失败:\n{traceback.format_exc()}"
                )
        except Exception:
            pass


def main() -> None:
    # -m 模式: 用 CodeAgent.exe -m 模块名 参数... 替代 python -m
    if len(sys.argv) >= 3 and sys.argv[1] == "-m":
        import runpy

        module = sys.argv[2]
        sys.argv = [module, *sys.argv[3:]]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return

    # 清除上次的启动日志
    try:
        if os.path.exists(_SERVER_LOG):
            os.remove(_SERVER_LOG)
    except Exception:
        pass

    # 后台启动服务器（带异常捕获）
    t = threading.Thread(
        target=_run_server,
        daemon=True,
    )
    t.start()

    # 等待就绪后自动打开浏览器
    ok = _wait_for_server()
    if ok:
        webbrowser.open(SERVER_URL)
    else:
        _report_server_not_ready()

    # 前台保持运行 + 托盘图标
    if _PLATFORM == 'darwin':
        _run_macos_tray()
    elif _PLATFORM == 'win32':
        try:
            import pystray  # noqa: F401 — 检查是否可用
            _run_tray()
        except ImportError:
            print(
                "pystray 不可用，将以无托盘后台模式运行。\n"
                f"请手动打开浏览器访问 {SERVER_URL}",
                file=sys.stderr,
            )
            _run_background()
    else:
        # Linux — 同样尝试 pystray
        try:
            import pystray  # noqa: F401
            _run_tray()
        except ImportError:
            _run_background()


if __name__ == "__main__":
    main()
