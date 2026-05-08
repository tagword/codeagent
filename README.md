# CodeAgent

一个面向开发者的自主任务执行 Agent。用 Markdown 配置文件驱动，支持 Web UI，开箱即用。

## 它能做什么

- 通过自然语言描述任务，自主拆解并执行
- 内置 Web UI，可视化查看执行过程和结果
- 支持多种 LLM 后端（OpenAI、Anthropic、本地模型等）
- 会话管理、记忆存储、工具调用链追踪
- 可扩展的工具系统

## 快速开始

### 安装

```bash
pip install codeagent
```

或者从源码安装：

```bash
git clone <your-repo-url>
cd codeagent
pip install -e .
```

### 启动 Web UI

```bash
codeagent serve
```

然后浏览器打开 `http://localhost:8765` 即可使用。

### 命令行使用

```bash
codeagent "你的任务描述"
```

## 配置

首次运行会自动生成配置文件，位于 `~/.codeagent/config.toml`，可在此设置 API Key、模型选择等。

## 许可证

[MIT](LICENSE)
