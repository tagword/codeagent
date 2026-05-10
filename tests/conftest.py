"""
pytest shared fixtures and configuration for codeagent tests.

Auto-discovers the ``seed`` and ``codeagent`` packages via ``pythonpath`` set in pyproject.toml.
"""

from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    """Return the absolute project root directory."""
    return Path(__file__).resolve().parent.parent
