# Architecture

## 项目定位

CodeAgent 是 **seed 引擎的人格层**（Personality Layer），运行在 `seed-kernel` 之上。

```
┌─────────────────────────────────────────┐
│              CodeAgent                   │  ← 人格层（你在这里）
│  CLI · Web UI · Skills · Per-Agent cfg  │
├─────────────────────────────────────────┤
│             seed-kernel                  │  ← 引擎层
│  LLM 执行 · 工具系统 · 会话管理 · 记忆  │
├─────────────────────────────────────────┤
│           seed-toolbox                   │  ← 工具层
│  内置工具（搜索、文件、代码检查等）      │
└─────────────────────────────────────────┘
```

## 目录结构

```
codeagent/
│
├── codeagent/                  # 主代码包
│   ├── __init__.py             # 版本号
│   ├── cli/
│   │   └── main.py             # CLI 入口 (codeagent / codeagent-core)
│   │
│   ├── core/
│   │   ├── paths.py            # 路径管理（AGENT_HOME、项目路径等）
│   │   ├── team_config.py      # Team 配置解析
│   │   └── ...                 # 其他核心模块
│   │
│   ├── runtime/
│   │   ├── prompt_enrichment.py # 运行时 prompt 增强（注入技能、记忆等）
│   │   └── compact_summarizer_prompt.md
│   │
│   ├── server/
│   │   ├── app_factory.py      # Starlette/FastAPI 应用工厂
│   │   ├── webui_api_app.py    # WebUI API 路由
│   │   └── ...                 # 其他 API 模块
│   │
│   ├── web/static/             # Web UI 前端（单页应用）
│   │   ├── body.html           # HTML 骨架
│   │   ├── *.css               # 样式文件
│   │   └── *.js                # JS 模块（按功能拆分）
│   │
│   ├── persona_defaults/       # 默认人格模板（每个新 Agent 的初始配置）
│   │   ├── agent.md
│   │   ├── identity.md
│   │   ├── soul.md
│   │   ├── memory.md
│   │   ├── skills.md
│   │   ├── tools.md
│   │   └── user.md
│   │
│   └── skills/
│       └── select.py           # 技能选择引擎（按触发条件匹配）
│
├── packaging/                  # 构建/打包脚本（macOS DMG 等）
├── assets/                     # 图标等资源
│
├── .codeagent/                 # 本地开发配置（不提交 Git）
│   ├── default/                # 默认 Agent 工作区
│   └── skills/                 # 项目级开发 skill
│
├── pyproject.toml              # 项目元数据、依赖、工具配置
├── CHANGELOG.md
├── CONTRIBUTING.md
├── README.md
└── ...                         # 其他配置文件
```

## 模块职责

### CLI (`codeagent/cli/main.py`)
- `codeagent` 命令入口
- 支持 `--serve` 启动 Web UI 模式
- 支持 `--version` 查看版本

### Server (`codeagent/server/`)
- Starlette/FastAPI 应用工厂 (`app_factory.py`)
- REST API 路由 (`webui_api_app.py`)
  - 会话管理 (CRUD、历史)
  - Agent 管理 (CRUD、presets、sessions)
  - Team/Hub (CRUD、run、SSE)
  - 环境配置 (LLM、MCP、Git)
  - 健康检查
- WebSocket 连接管理
- Web UI 静态文件服务

### Web UI (`codeagent/web/static/`)
- 单页应用 (SPA)，纯 HTML/CSS/JS
- 无前端构建工具链，直接 serve 静态文件
- 模块按功能拆分（聊天、会话、配置、项目、文件浏览等）
- 通过 WebSocket + REST API 与服务端通信

### Skills 引擎 (`codeagent/skills/select.py`)
- 技能发现：扫描 agent 级和项目级 skills
- 触发匹配：按用户输入匹配合适 skill
- 渐进式加载：skill 内容按需注入 system prompt

### Paths (`codeagent/core/paths.py`)
- 管理 AGENT_HOME、工作区路径、项目路径
- `.codeagent/{agent_id}/` 路径体系

## 关键设计决策

### 1. 人格层与引擎层分离
- 引擎逻辑 (`seed-kernel`) 与界面/配置层 (`codeagent`) 解耦
- 引擎可独立升级，不依赖 CodeAgent 的 Web UI 和 CLI

### 2. Markdown 即配置
- Agent 人格完全由 Markdown 文件定义（identity/soul/memory 等）
- 无数据库，无 YAML/JSON 配置文件
- 改文件即改行为，无需重启

### 3. 渐进式技能加载
- Skill 不全量注入 system prompt
- 按用户输入动态匹配 top-k 个
- 节省 token，控制上下文窗口

### 4. 单页无构建
- Web UI 纯静态文件，不依赖 npm/webpack
- 开发时改 JS/CSS/HTML 即刷新，无需构建步骤
- 部署时单目录复制即可

### 5. 项目级 `.codeagent/`
- 每个项目可独立配置 rules.md 和 skills
- 项目级技能自动发现，与 agent 级技能共存

## 数据流

```
用户输入
    │
    ▼
CLI / Web UI
    │
    ▼
codeagent.runtime.prompt_enrichment
    │  ├─ 注入人格（identity/soul/memory）
    │  ├─ 注入匹配的技能
    │  └─ 注入项目上下文
    │
    ▼
seed-kernel (LLM 调用)
    │
    ├─ 工具调用 → seed-toolbox tools
    │              └─ 文件/搜索/代码检查等
    │
    └─ 回复 → Web UI / CLI 输出
```
