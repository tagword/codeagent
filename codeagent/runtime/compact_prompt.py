"""Default paths for CodeAgent context-compact summarizer prompts."""

from __future__ import annotations

from pathlib import Path


def default_summarizer_prompt_path() -> Path:
    return Path(__file__).resolve().parent / "compact_summarizer_prompt.md"
