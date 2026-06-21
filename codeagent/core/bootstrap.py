"""Code Agent process bootstrap (product home → config → Seed bridge)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from codeagent.core.env import apply_default_product_home
from codeagent.core.seed_bridge import bridge_codeagent_env_to_seed
from seed.integrations.env_config import apply_seed_env_from_config

logger = logging.getLogger(__name__)

_CODEAGENT_BOOTSTRAP_MD = """\
# CodeAgent 首次启动引导

首次使用请按以下顺序完成初始化。

---

## 1. 环境变量

复制模板并填写 LLM 信息：

```bash
cp config/env.example config/env
```

最低必填项（编辑 `config/env`）：

| 变量 | 说明 |
|------|------|
| `SEED_LLM_BASEURL` | LLM API 地址（OpenAI 格式） |
| `SEED_LLM_MODEL` | 模型名称 |
| `SEED_LLM_API_KEY` | API 密钥 |

系统环境变量优先级 > env 文件。

---

## 2. Agent 人格配置

Agent 行为由 `agents/default/persona/` 下的 Markdown 文件定义：

| 文件 | 作用 |
|------|------|
| `identity.md` | 角色定位 |
| `soul.md` | 核心价值观与行为准则 |
| `agent.md` | 工作流程与项目管理规范 |
| `skills.md` | 核心工作流 |
| `tools.md` | 工具选用规则 |
| `user.md` | 用户偏好 |

按需修改即可调整 Agent 风格。

---

## 3. 首次验证

```bash
# Web UI（推荐）
codeagent web

# 或 CLI 模式
codeagent chat
```

确认 LLM 能正常响应、会话日志写入正常。

---

## 4. （可选）Git 版本管理

对配置进行版本控制，方便回溯：

```bash
cd ~/.codeagent
git init
```

创建 `.gitignore` 忽略运行数据：

```
agents/default/sessions/
agents/default/projects-data/
agents/default/memory/
mcp-minimax-out/
config/env
config/seed.env
config/webui.token
config/codeagent.webui.token
```

首次提交：

```bash
git add .gitignore agents/default/persona/ agents/default/skills/ config/
git commit -m "chore: init codeagent config"
```

---

## 目录结构

```
~/.codeagent/
├── config/                  # 全局配置（env、cron、MCP、LSP、hooks）
├── agents/default/
│   ├── persona/             # Agent 人格定义（修改这里）
│   ├── skills/              # 自定义技能
│   ├── sessions/            # 对话历史（自动生成）
│   ├── memory/              # 长期记忆（自动生成）
│   └── projects-data/       # 项目记忆（自动生成）
├── mcp-minimax-out/         # MCP 工具缓存
└── bootstrap.md             # ← 本文件
```
"""


def _ensure_codeagent_bootstrap_md(home: Path) -> None:
    """Overwrite Seed's generic bootstrap.md with CodeAgent's own version."""
    dest = home / "config" / "bootstrap.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Always overwrite: CodeAgent's bootstrap is the authoritative one.
    dest.write_text(_CODEAGENT_BOOTSTRAP_MD, encoding="utf-8")


def bootstrap_codeagent_runtime(base: Optional[Path] = None) -> Path:
    """
    1. Default data root ``~/.codeagent`` (or ``CODEAGENT_HOME``)
    2. Set ``SEED_PROJECT_ROOT`` so Seed / seed-tools use the same tree
    3. Load ``config/env`` (or legacy ``config/seed.env``) + ``config/codeagent.env``
    4. Bridge ``CODEAGENT_*`` → ``SEED_*`` for kernel env keys
    5. Write CodeAgent's bootstrap.md (overrides Seed's generic version)
    """
    if base is not None:
        home = base.resolve()
        os.environ["CODEAGENT_HOME"] = str(home)
        os.environ["SEED_PROJECT_ROOT"] = str(home)
        home.mkdir(parents=True, exist_ok=True)
        (home / "config").mkdir(parents=True, exist_ok=True)
    else:
        home = apply_default_product_home()

    apply_seed_env_from_config(None)
    bridge_codeagent_env_to_seed()

    from codeagent.runtime.compact_prompt import default_summarizer_prompt_path

    if default_summarizer_prompt_path().is_file():
        os.environ.setdefault(
            "CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_PROMPT_FILE",
            str(default_summarizer_prompt_path()),
        )
    os.environ.setdefault("CODEAGENT_CONTEXT_COMPACT_MID_LOOP", "1")
    os.environ.setdefault("CODEAGENT_CONTEXT_COMPACT_KEEP_USER_ROUNDS", "2")
    bridge_codeagent_env_to_seed()

    _ensure_codeagent_bootstrap_md(home)

    # ── Team config: load if exists ──
    try:
        team_cfg_path = home / "config" / "team.json"
        if team_cfg_path.is_file():
            from codeagent.core.team_manager import TeamManager
            tm = TeamManager()
            if tm.init_from_config(team_cfg_path):
                logger.info(f"Team mode enabled: {len(tm.config.members)} member agents configured")
            else:
                logger.info("Single-agent mode (team config invalid or empty)")
        else:
            logger.info("Single-agent mode (no team.json found)")
    except Exception:
        logger.exception("Team config init failed — continuing in single-agent mode")

    return home
