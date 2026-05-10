"""
CodeAgent — Personality layer

Architecture:
  - seed/   : Core engine (LLM execution, tool system, session management)
  - codeagent/ : Personality layer (CLI, server, web UI, skills, per-agent config)
"""

__version__ = "1.0.0"

# Compat: bind ``generate`` / ``generate_stream`` onto ``seed``'s LLMAPIExecutor when missing.
import codeagent.llm.executor  # noqa: F401

