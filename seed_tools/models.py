"""Minimal data model for seed-tools — only what tools need."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Tool:
    """Declarative tool metadata for LLM schema and registration."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: str = "string"
    category: str = "builtin"
    version: str = "1.0"
