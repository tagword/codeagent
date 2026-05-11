"""
CodeAgent macOS 启动器 — 菜单栏托盘版

功能：
  1. 启动 CodeAgent 服务器
  2. 系统菜单栏显示图标
  3. 菜单：打开浏览器 / 重启服务 / 退出
  4. 点击图标快速打开浏览器
"""
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import rumps

# ── 路径 ──────────────────────────────────────────────────
# PyInstaller .app 打包后，资源在 sys._MEIPASS / Resources
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _ROOT = Path(sys._MEIPASS).parent.parent  # CodeAgent.app/Contents
    _DIST = _ROOT.parent  # dist/
else:
    _ROOT = Path(__file__).parent.resolve()
    _DIST = _ROOT / "dist"

APP_NAME = "CodeAgent"
SERVER_PORT = 8899
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"


# ============================================================
#  托盘图标素材
# ============================================================
def _menu_icon() -> str:
    """
    返回菜单栏图标路径。
    优先用打包内的 tray_icon.png（22x22），没有则用 icon.png 缩小版本。
    """
    # 在 .app 内搜索 tray 图标
    candidates = [
        _ROOT / "Resources" / "tray_icon.png",
        _ROOT / "tray_icon.png",
        _ROOT.parent / "tray_icon.png",
        Path(__file__).parent / "tray_icon.png",
        Path(__file__).parent / "icon.png",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # 用 icon.png 实时生成小尺寸 tray 图标
    src = candidates[-1]
    if src.exists():
        try:
            from PIL import Image
            tray = _ROOT / "tray_icon.png"
            img = Image.open(src).resize((22, 22), Image.LANCZOS)
            img.save(tray, "PNG")
            return str(tray)
        except Exception:
            pass
    return ""


# ============================================================
#  服务器管理
# ============================================================
class ServerManager:
    """管理 CodeAgent 服务器生命周期。"""

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._ready = threading.Event()

    # ── 启动 ──────────────────────────────────────────────
    def start(self) -> bool:
        """启动服务器，等待就绪后返回。"""
        self._ready.clear()
        self._do_start()

        # 等待端口就绪（最多 30 秒）
        for _ in range(90):
            if self._is_listening():
                self._ready.set()
                return True
            time.sleep(0.33)
        return False

    def _do_start(self):
        """派生子进程启动服务器。"""
        cmd = [sys.executable, "-m", "codeagent.server"]
        env = {**os.environ, "CODEAGENT_PORT": str(SERVER_PORT)}
        self._process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _is_listening(self) -> bool:
        """检查端口是否可访问。"""
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", SERVER_PORT))
            return True
        except (ConnectionRefusedError, OSError):
            return False
        finally:
            s.close()

    # ── 重启 ──────────────────────────────────────────────
    def restart(self) -> bool:
        """优雅重启。"""
        self.stop(graceful=True)
        return self.start()

    # ── 停止 ──────────────────────────────────────────────
    def stop(self, graceful: bool = False):
        if self._process is None:
            return

        if graceful:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
        else:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass

        try:
            self._process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process = None


# ============================================================
#  菜单栏应用
# ============================================================
class CodeAgentTrayApp(rumps.App):
    """CodeAgent 菜单栏应用。"""

    def __init__(self, server: ServerManager):
        icon_path = _menu_icon()
        super().__init__(
            APP_NAME,
            icon=icon_path or None,
            quit_button=None,  # 自定义退出
        )
        self.server = server
        self._update_menu()

    def _update_menu(self, status: str = "Idle"):
        """更新菜单项状态。"""
        self.menu.clear()
        self.menu.add(rumps.MenuItem(f"CodeAgent — {status}", callback=None))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("🌐 打开浏览器", callback=self._open_browser))
        self.menu.add(rumps.MenuItem("🔄 重启服务", callback=self._restart_server))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("❌ 退出", callback=self._quit_app))

    # ── 菜单动作 ──────────────────────────────────────────
    @rumps.clicked("CodeAgent 图标")
    def _on_click(self, _):
        """点击图标 → 打开浏览器。"""
        self._open_browser(None)

    def _open_browser(self, _):
        webbrowser.open(SERVER_URL)

    def _restart_server(self, _):
        self._update_menu("重启中…")
        ok = self.server.restart()
        self._update_menu("运行中" if ok else "启动失败")
        if not ok:
            rumps.notification(
                APP_NAME, "服务启动失败",
                "请检查日志后重试", sound=False,
            )

    def _quit_app(self, _):
        self.server.stop(graceful=True)
        rumps.quit_application()


# ============================================================
#  入口
# ============================================================
def main():
    server = ServerManager()

    print(f"🚀 正在启动 {APP_NAME} 服务器…")
    ok = server.start()

    app = CodeAgentTrayApp(server)
    app._update_menu("运行中" if ok else "启动失败")

    if ok:
        print(f"✅ 服务器已就绪 → {SERVER_URL}")
        rumps.notification(
            APP_NAME, "服务已就绪",
            f"浏览器中打开 {SERVER_URL}", sound=False,
        )
        # 首次启动自动打开浏览器
        webbrowser.open(SERVER_URL)
    else:
        print("❌ 服务器启动失败")
        rumps.notification(
            APP_NAME, "启动失败",
            "CodeAgent 服务未能正常启动，请检查日志",
            sound=True,
        )

    app.run()


if __name__ == "__main__":
    main()
