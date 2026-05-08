"""CLI package. Lazy-export ``main`` so ``python -m codeagent.cli.main`` does not pre-load the module."""

from __future__ import annotations

__all__ = ("main",)


def __getattr__(name: str):
    if name == "main":
        from .main import main as _main

        return _main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
