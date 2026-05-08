"""CLI entrypoint (compat wrapper)."""

from __future__ import annotations


def main() -> None:
    # Delegate to the existing implementation for now.
    from src.cli_pkg import main as _main

    _main()


if __name__ == "__main__":
    main()

