"""Web app entrypoint (compat wrapper)."""

from __future__ import annotations

from typing import Any


def create_app() -> Any:
    from codeagent.server import create_app as _create_app

    return _create_app()


def main(host: str = "0.0.0.0", port: int = 8765) -> None:
    from codeagent.server import main as _main

    _main(host=host, port=port)

