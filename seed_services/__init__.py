"""seed-services — standalone utilities for browser automation, safety checks, and webhook dedup."""

from seed_services.browser import BROWSER, ensure_browser_running, BrowserError
from seed_services.safety import (
    check_bash_command,
    enforce_bash_timeout,
    sanitize_assistant_output,
    sanitize_tool_output,
)
from seed_services.webhook_dedup import (
    compute_webhook_dedup_key,
    dedup_enabled,
    reset_webhook_dedup_cache,
    try_acquire,
    try_acquire_report,
)

__all__ = (
    "BROWSER",
    "ensure_browser_running",
    "BrowserError",
    "check_bash_command",
    "enforce_bash_timeout",
    "sanitize_assistant_output",
    "sanitize_tool_output",
    "compute_webhook_dedup_key",
    "dedup_enabled",
    "reset_webhook_dedup_cache",
    "try_acquire",
    "try_acquire_report",
)
