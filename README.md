# CodeAgent

一个面向开发者的自主任务执行 Agent。用 Markdown 配置文件驱动行为，支持 Web UI，开箱即用。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](pyproject.toml)

---

## 概览

CodeAgent 是一个**自主全栈开发 Agent** —— 它能独立承接从需求分析到交付维护的完整项目周期。由 Markdown 配置文件（`agent.md`、`soul.md`、`skills.md` 等）定义人格与行为规则，配合强大的工具系统，实现最小人工干预下的自动化开发。

### 核心特性

- 🧠 **LLM 驱动** — 支持 OpenAI、Anthropic、本地模型等多种后端，通过配置即可切换
- 📜 **人格即配置** — 用 Markdown 定义 Agent 的身份、行为准则、技能，无需改代码
- 🛠️ **工具系统** — 45+ 内置工具：文件操作、Shell 执行、代码分析、Git 管理、数据库、部署等
- 🌐 **Web UI** — 可视化聊天界面，实时查看执行过程、工具调用链、会话历史
- 📋 **项目管控** — 内置待办管理（todo_tool）、项目规划、版本追踪
- 🔌 **可扩展** — 支持自定义工具、Webhook、多 Agent 协作（Multi-Agent Hub）
- 🧩 **多步工作流** — 内置 fix-and-commit、new-feature、audit-project 等自动化流水线

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/tagword/codeagent.git
cd codeagent

# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装（默认含 Starlette + Uvicorn Web UI 支持）
pip install -e .
```

### 启动 Web UI

```bash
codeagent serve
```

浏览器打开 `http://localhost:8765` 即可开始使用。

### 命令行使用

```bash
# 查看帮助
codeagent --help

# 运行单次任务
codeagent run "帮我整理当前目录的文件结构"
```

## 配置

首次运行会自动生成配置文件 `~/.codeagent/config.toml`，你可以在其中设置：

| 配置项 | 说明 |
|--------|------|
| `llm.provider` | LLM 后端（openai / anthropic / local 等） |
| `llm.api_key` | API 密钥 |
| `llm.model` | 模型名称 |
| `web.port` | Web UI 端口（默认 8765） |
| `web.host` | 监听地址（默认 127.0.0.1） |

## 项目结构

```
codeagent/
├── codeagent/            # 核心源码
│   ├── cli/              # 命令行入口
│   ├── core/             # 核心模型与配置
│   ├── llm/              # LLM 调用执行器
│   ├── runtime/          # Agent 运行时（orchestrator, turn_loop, worker）
│   ├── server/           # HTTP / WebSocket 服务
│   ├── web/              # Web 认证与路由
│   └── webui/            # 前端 UI 文件（CSS + JS）
├── skills/               # 可复用的技能定义
├── docs/                 # 开发文档
├── pyproject.toml        # 项目元数据与依赖
└── README.md
```

## 技术栈

- **后端**：Python 3.9+ / Starlette / WebSocket
- **前端**：Vanilla JS + CSS（无框架依赖）
- **LLM 集成**：OpenAI / Anthropic / 兼容 API
- **工具运行**：异步工具调度 + 安全检查
- **数据存储**：SQLite（会话/记忆）

## 开发

```bash
# 安装开发依赖
pip install -e '.[dev]'

# 运行测试
pytest

# 代码检查
ruff check codeagent/

# 安全审计
bandit -r codeagent/
```

## 许可证

[MIT](LICENSE) © 2025 tagword
