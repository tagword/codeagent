# CodeAgent

一个**自主全栈开发 Agent** — 用 Markdown 配置文件驱动人格与行为，支持 Web UI，开箱即用。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](pyproject.toml)

---

## 概览

CodeAgent 是一个**自主全栈开发 Agent** —— 它能独立承接从需求分析到交付维护的完整项目周期。由 Markdown 配置文件（`agent.md`、`soul.md`、`skills.md` 等）定义人格与行为规则，配合强大的工具系统，实现最小人工干预下的自动化开发。

### 架构分层

```
┌─────────────────────────────────────────────────┐
│  CodeAgent（本仓库）                              │
│  CLI · HTTP/WebSocket · Web UI · 认证 · Agent 层 │
├─────────────────────────────────────────────────┤
│  seed                    核心引擎（LLM/路由/会话） │
│  seed-tools[code]        内置工具注册与执行        │
│  seed-model-providers    模型提供商目录（tokenizer）│
└─────────────────────────────────────────────────┘
```

### 核心特性

- 🧠 **LLM 驱动** — 支持 OpenAI、Anthropic、DeepSeek、本地模型等多种后端
- 📜 **人格即配置** — 用 Markdown 定义 Agent 的身份、行为准则、技能，无需改代码
- 🛠️ **工具系统** — 45+ 内置工具：文件操作、Shell 执行、代码分析、Git 管理、数据库、部署
- 🌐 **Web UI v2** — 现代化 React + Vite 前端，可视化聊天、工具调用链、会话历史
- 📋 **项目管控** — 内置待办管理、项目规划（docs/plans 面板）、版本追踪
- 🔌 **可扩展** — 自定义工具、Webhook、多 Agent 协作（Multi-Agent Hub）
- 🧩 **多步工作流** — 内置 fix-and-commit、new-feature、audit-project 等自动化流水线
- 🌍 **国内友好** — 自动检测国内网络，使用 PyPI 镜像（清华源）加速安装

## 快速开始

### ⭐ 一键运行（强烈推荐）

```bash
# 克隆仓库
git clone https://github.com/tagword/codeagent.git
cd codeagent

# 一键运行（自动检测环境、安装依赖、启动服务）
bash run.sh
```

脚本会自动：
1. 检测 Python（≥ 3.9）和 Git
2. **自动识别国内网络** → 使用清华 PyPI 镜像加速
3. 创建虚拟环境 `.venv`
4. 安装 CodeAgent 及全部依赖（含私有 seed 框架）
5. 构建 Web UI v2 前端（如有 Node.js）
6. 启动 Web 服务 → 浏览器打开 `http://localhost:8765`

> 💡 支持自定义参数：`bash run.sh --port 8766 --host 0.0.0.0`
> 💡 `run.sh` 内置了网络重试和 tarball 降级机制，网络不稳定时比 `pip install -e .` 更可靠

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/tagword/codeagent/main/install.sh | bash
```

安装完成后：

```bash
cd ~/codeagent
bash run.sh
```

### 手动安装

> ⚠️ CodeAgent 依赖的 `seed` / `seed-model-providers` / `seed-tools` 是**私有包**（不在 PyPI 上），
> pyproject.toml 使用 `git+https` 自动从 GitHub 拉取。确保已安装 **Git** 且有**网络连接**。

```bash
# 克隆仓库
git clone https://github.com/tagword/codeagent.git
cd codeagent

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装（自动从 GitHub 拉取 seed 私有依赖）
pip install -e .

# 启动
codeagent serve
```

浏览器打开 `http://localhost:8765` 即可使用。

### 国内用户加速

脚本会自动检测网络环境，如直连 PyPI 超时则自动切换至清华镜像源。也可手动指定：

```bash
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple

# npm 前端构建（可选）
cd webui-v2
npm install --registry=https://registry.npmmirror.com
npm run build
```

### 命令行使用

```bash
# 查看帮助
codeagent --help

# 启动交互式聊天（LLM + 工具循环）
codeagent chat --llm

# 运行单次任务
codeagent run "帮我整理当前目录的文件结构"

# 管理 Web UI 令牌
codeagent webui-token init
codeagent webui-token show
codeagent webui-token reset

# 重启服务
codeagent restart serve --port 8765
```

## 配置

### 首次初始化

```bash
codeagent config init
```

会生成默认配置文件到 `config/` 目录。

### 环境变量

编辑 `config/env`（参考 `config/env.example`），核心配置项：

| 配置项 | 说明 |
|--------|------|
| `CODEAGENT_PROVIDER` | LLM 提供商（openai / deepseek / anthropic 等） |
| `CODEAGENT_API_KEY` | API 密钥 |
| `CODEAGENT_MODEL` | 模型名称 |
| `CODEAGENT_BASE_URL` | API 端点地址 |
| `CODEAGENT_AGENT_ID` | 当前 Agent 标识（默认 `default`） |

详细环境变量清单见 [docs/ENV_REFERENCE.md](docs/ENV_REFERENCE.md)。

### Web UI 认证

```bash
codeagent webui-token init     # 生成访问令牌
codeagent webui-token show     # 查看当前令牌
```

启动服务后访问 `http://localhost:8765`，输入令牌即可登录。

## 项目结构

```
codeagent/
├── codeagent/              # 核心源码
│   ├── cli/main.py         # 命令行入口
│   ├── core/               # 核心模块（bootstrap / env / attachments 等）
│   ├── server/             # HTTP / WebSocket 服务
│   │   ├── webui_api_app.py  # WebUI REST API
│   │   ├── app_factory.py    # Starlette 应用工厂
│   │   └── ...
│   ├── web/                # Web 认证与路由
│   └── webui/              # 内置 Web UI（Vue 版，v1 兼容）
├── webui-v2/               # Web UI v2（React + Vite + TypeScript）
│   ├── src/                # 前端源码
│   ├── dist/               # 构建产物
│   └── package.json
├── agents/                 # Agent 人格配置
│   ├── default/            # 默认 Agent（agent.md / soul.md / skills.md）
│   └── test_agent/
├── config/                 # 运行时配置
│   ├── env                 # 环境变量（本地，不提交）
│   ├── env.example         # 环境变量模板
│   └── codeagent.setup.json
├── docs/                   # 开发文档与参考
│   ├── ENV_REFERENCE.md    # 完整环境变量手册
│   ├── AGNES_API.md        # API 文档
│   ├── CONTEXT_COMPACT.md  # 上下文压缩机制
│   └── ...
├── skills/                 # 可复用的技能定义
├── tests/                  # 测试
├── deploy/                 # 部署配置（supervisord）
├── run.sh                  # ★ 一键运行脚本（推荐）
├── install.sh              # 一键安装脚本
├── pyproject.toml          # 项目元数据与依赖
└── README.md
```

## Web UI v2

基于 **React 19 + Vite + TypeScript + Tailwind v4** 的现代化前端。

```bash
cd webui-v2
npm install
npm run dev      # 开发模式
npm run build    # 生产构建
```

也可通过 `run.sh` 或 `codeagent serve` 自动 serve 构建产物。

## 技术栈

| 层 | 技术 |
|----|------|
| **核心引擎** | seed (LLM 调用 / 路由 / 会话 / 工具运行时) |
| **后端服务** | Python 3.9+ / Starlette / WebSocket / Uvicorn |
| **前端 v2** | React 19 / TypeScript / Vite / Tailwind v4 |
| **前端 v1** | Vanilla JS + CSS（无框架，内置兜底） |
| **LLM 集成** | OpenAI / Anthropic / DeepSeek / Ollama / 兼容 API |
| **工具系统** | 异步工具调度 + 安全检查 + 沙箱 |
| **数据存储** | SQLite（会话 / 记忆 / 项目状态） |

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
