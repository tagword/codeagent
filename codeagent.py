#!/usr/bin/env python3
"""
CodeAgent CLI - Main entry point

Usage:
    python -m codeagent --help
    python -m codeagent run "What commands are available?"
    python -m codeagent commands
    python -m codeagent tools
"""
import sys
import os

# Repo root must be on path so package `src` resolves (do not use src/main.py flat imports).
repo_root = os.path.dirname(os.path.abspath(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.cli_pkg import main

if __name__ == "__main__":
    main()