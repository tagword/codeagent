"""
CodeAgent — Personality layer

Architecture:
  - seed/   : Core engine (LLM execution, tool system, session management)
  - codeagent/ : Personality layer (CLI, server, web UI, skills, per-agent config)
"""

# 版本号从包元数据动态读取，避免 pyproject.toml 与 __init__ 写死值不同步
try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("tagword-codeagent")
except Exception:  # 未安装（源码目录直接运行）时兜底
    __version__ = "0.0.0"

