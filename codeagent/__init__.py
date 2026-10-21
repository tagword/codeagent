"""
CodeAgent — Personality layer

Architecture:
  - seed/   : Core engine (LLM execution, tool system, session management)
  - codeagent/ : Personality layer (CLI, server, web UI, skills, per-agent config)
"""

# 版本号从包元数据动态读取，避免 pyproject.toml 与 __init__ 写死值不同步
# 注意：发行名（tagword-codeagent）与历史 editable 安装的 dist-info 名（codeagent）
# 可能不一致，两者都尝试，避免静默回落到 0.0.0。
def _resolve_version() -> str:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    for dist_name in ("tagword-codeagent", "codeagent"):
        try:
            return _pkg_version(dist_name)
        except PackageNotFoundError:
            continue
    return "0.0.0"


__version__ = _resolve_version()

