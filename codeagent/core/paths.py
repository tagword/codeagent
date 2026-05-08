"""Agent filesystem layout under ``CODEAGENT_PROJECT_ROOT`` (multi-agent aware)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _project_root() -> Path:
    from seed.config_plane import project_root

    return project_root()


def agent_id_default() -> str:
    return (os.environ.get("CODEAGENT_AGENT_ID", "") or "default").strip() or "default"


def agent_home(agent_id: str) -> Path:
    aid = (agent_id or "").strip() or agent_id_default()
    return _project_root() / "agents" / aid


# Default persona Markdown filenames (same as CONFIG_FILENAMES in config_plane).
_DEFAULT_PERSONA_FILENAMES = [
    "agent.md",
    "identity.md",
    "soul.md",
    "tools.md",
    "skills.md",
    "user.md",
]


def _ensure_default_persona_files(persona_dir: Path) -> None:
    """Create default persona *.md files if they do not exist (does not overwrite)."""
    defaults = {
        "agent.md": (
            "# Agent Profile\n\n"
            "你是 CodeAgent，一个能自主执行编程、搜索、文件操作等任务的通用 AI Agent。\n"
            "你的底层模型由 `CODEAGENT_LLM_*` 环境变量配置。\n"
        ),
        "identity.md": (
            "# Identity\n\n"
            "- **名称**: CodeAgent\n"
            "- **角色**: 编程与自动化助手\n"
            "- **核心能力**:\n"
            "  - 代码阅读、编写、调试与重构\n"
            "  - Shell 命令执行与系统操作\n"
            "  - 文件读写与管理\n"
            "  - Web 搜索与信息获取\n"
            "  - 数据库查询与操作\n"
            "  - 多步骤工作流编排\n"
        ),
        "soul.md": (
            "# Soul / 行为准则\n\n"
            "1. **准确可靠**：核对信息源，不编造不存在的事实。\n"
            "2. **安全意识**：执行命令前思考潜在风险，不执行破坏性操作。\n"
            "3. **主动沟通**：当任务目标不明确时，主动向用户澄清。\n"
            "4. **简洁高效**：直接交付结果，避免冗长的客套话。\n"
            "5. **持续学习**：从每次对话中吸取经验。\n"
        ),
        "tools.md": (
            "# Tools / 能力边界\n\n"
            "你可以使用以下类别的工具：\n"
            "- **文件操作**: `file_read`, `file_write`, `file_edit_tool`, `file_search`, `glob_tool`, `grep_tool`\n"
            "- **命令执行**: `bash_exec`, `bash_tool`\n"
            "- **Web 交互**: `web_search_tool`, `web_fetch`, `browser_*`\n"
            "- **代码分析**: `code_check`, `code_analyze`, `project`, `refactor`, `test_gen`\n"
            "- **项目管理**: `todo_tool`, `diagram`, `deploy`, `deps_check`\n"
            "- **数据库**: `db`\n"
            "- **记忆/配置**: `memory_search`, `codeagent_cron_*`, `artifact_read`\n"
            "\n"
            "对于不在上述列表中的工具，按需使用即可。\n"
        ),
        "skills.md": (
            "# Skills / 技能列表\n\n"
            "暂无启用的自定义技能。\n"
            "你可以在 Web UI 的「技能」页面或通过 `config/skills/` 目录添加技能 Markdown 文件。\n"
        ),
        "user.md": (
            "# User / 用户上下文\n\n"
            "此文件用于记录与当前用户相关的上下文信息。\n"
            "你可以根据实际情况在此记录用户的偏好、常用配置等。\n"
        ),
    }
    for fname in _DEFAULT_PERSONA_FILENAMES:
        p = persona_dir / fname
        if not p.is_file():
            body = defaults.get(fname, "")
            if body:
                try:
                    p.write_text(body, encoding="utf-8")
                except OSError:
                    pass


def ensure_agent_scaffold(agent_id: str, base: Optional[Path] = None) -> Path:
    root = Path(base).resolve() if base is not None else _project_root()
    aid = (agent_id or "").strip() or agent_id_default()
    home = root / "agents" / aid
    for sub in ("persona", "skills", "sessions"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    # Ensure default persona *.md files if missing
    _ensure_default_persona_files(home / "persona")
    return home


def agent_persona_dir(agent_id: str, base: Optional[Path] = None) -> Path:
    return ensure_agent_scaffold(agent_id, base) / "persona"


def agent_skills_dir(agent_id: str, base: Optional[Path] = None) -> Path:
    return ensure_agent_scaffold(agent_id, base) / "skills"


def agent_memory_dir(agent_id: str) -> Path:
    p = agent_home(agent_id) / "memory"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_persona_memory_path(agent_id: str) -> Path:
    return agent_memory_dir(agent_id)


def agent_projects_registry_dir(agent_id: str) -> Path:
    p = agent_home(agent_id) / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_projects_data_dir(agent_id: str) -> Path:
    p = agent_home(agent_id) / "projects-data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_project_data_dir(agent_id: str, project_id: str) -> Path:
    pid = (project_id or "").strip()
    d = agent_projects_data_dir(agent_id) / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def agent_project_data_subdir(agent_id: str, project_id: str, sub: str) -> Path:
    d = agent_project_data_dir(agent_id, project_id) / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def agent_daily_dir(agent_id: str) -> Path:
    p = agent_memory_dir(agent_id) / "daily"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_archive_dir(agent_id: str) -> Path:
    p = agent_memory_dir(agent_id) / "archive"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_project_daily_dir(agent_id: str, project_id: str) -> Path:
    p = agent_project_data_subdir(agent_id, project_id, "memory") / "daily"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_project_archive_dir(agent_id: str, project_id: str) -> Path:
    p = agent_project_data_subdir(agent_id, project_id, "memory") / "archive"
    p.mkdir(parents=True, exist_ok=True)
    return p
