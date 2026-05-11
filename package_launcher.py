"""
CodeAgent macOS .app 启动器

双击 CodeAgent.app 后：
1. 启动 CodeAgent Web 服务器（127.0.0.1:8899）
2. 自动在默认浏览器打开 UI
3. 保持运行直到用户退出（Cmd+Q）
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# PyInstaller 打包后, `sys._MEIPASS` 指向 .app/Contents/Resources
_BUNDLED = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
if _BUNDLED:
    sys.path.insert(0, sys._MEIPASS)

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8899
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"


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


def _open_browser():
    """等待服务器就绪后打开浏览器。"""
    ok = _wait_for_server()
    if ok:
        webbrowser.open(SERVER_URL)


def main():
    from codeagent.server import main as server_main

    # 后台等待服务器就绪后开浏览器
    threading.Thread(target=_open_browser, daemon=True).start()

    # 前台阻塞运行服务器（窗口关闭 / Cmd+Q 后进程终止）
    server_main(host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    main()
