"""
CodeAgent macOS .app 启动器（带菜单栏图标）

双击 CodeAgent.app 后：
1. 启动 CodeAgent Web 服务器（127.0.0.1:8899）
2. 自动在默认浏览器打开 UI
3. 菜单栏显示图标 → 可打开浏览器或退出
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import rumps

# PyInstaller 打包后, `sys._MEIPASS` 指向 .app/Contents/Resources
_BUNDLED = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
if _BUNDLED:
    sys.path.insert(0, sys._MEIPASS)

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8899
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# 托盘图标路径（打包后 sys._MEIPASS = Contents/Resources/）
if _BUNDLED:
    _ICON = str(Path(sys._MEIPASS) / "tray_icon.png")
else:
    _ICON = str(Path(__file__).parent / "tray_icon.png")


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


class CodeAgentTray(rumps.App):
    """菜单栏托盘应用。"""

    def __init__(self):
        super().__init__(
            "CodeAgent",
            icon=_ICON,
            quit_button=None,  # 我们用自定义退出
        )
        self.menu = [
            rumps.MenuItem("Open Browser", callback=self._open_browser),
            None,  # 分隔线
            rumps.MenuItem("Quit", callback=self._quit_app),
        ]

    @staticmethod
    def _open_browser(_):
        webbrowser.open(SERVER_URL)

    @staticmethod
    def _quit_app(_):
        rumps.quit_application()
        os._exit(0)


def main():
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

    # 前台运行菜单栏图标（阻塞）
    CodeAgentTray().run()


if __name__ == "__main__":
    main()
