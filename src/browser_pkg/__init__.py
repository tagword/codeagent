"""Browser remote-debugging integration (Chromium)."""

from src.browser_pkg._browser_pkg_merged import BROWSER, BrowserManager
from src.browser_pkg._browser_pkg_merged import BrowserError
from src.browser_pkg._browser_pkg_merged import ensure_browser_running

__all__ = ["BrowserManager", "BROWSER", "ensure_browser_running", "BrowserError"]
