# Code Agent 环境变量（`CODEAGENT_*`）

**Code Agent** 是构建在 [Seed](../seed/) 之上的产品层。本产品**长期保留** `CODEAGENT_*` 前缀，用于 Web UI、skills、日记、计费展示等产品行为。

**默认数据目录**：`~/.codeagent`（`CODEAGENT_HOME`）。启动时同步为内核的 `SEED_PROJECT_ROOT`，与仅用 Seed 时的 `~/.seed` 分离。见 [`MULTI_PRODUCT.md`](MULTI_PRODUCT.md)。

通用内核与集成（LLM、沙箱、MCP、hooks、会话存储等）使用 **`SEED_*`**，见 [`seed/docs/ENV_REFERENCE.md`](../seed/docs/ENV_REFERENCE.md)。

---

## 产品与 Web UI

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_HOME` | `~/.codeagent` | 产品数据根（agents、config、会话等） |
| `CODEAGENT_PROJECT_ROOT` | 同 `CODEAGENT_HOME` | 可选显式覆盖数据根 |
| `CODEAGENT_AGENT_ID` | `default` | 默认 logical agent id |
| `CODEAGENT_LOG_LEVEL` | `INFO` | 服务日志级别 |
| `CODEAGENT_PORT` | `8765` | HTTP 端口 |
| `CODEAGENT_WEBUI_TOKEN` | （空） | Web UI 访问令牌 |
| `CODEAGENT_SKIP_FOLDER_PICKER` | （空） | 跳过首次目录选择 |
| `CODEAGENT_WEBUI_TRANSCRIPT_MAX_CHARS` | `12000` | transcript 单条字符上限 |
| `CODEAGENT_WEBUI_TRANSCRIPT_USER_BLOCKS` | `10` | transcript 用户块窗口 |
| `CODEAGENT_WEBUI_TRANSCRIPT_MAX_MESSAGES` | `300` | transcript 消息条数上限 |
| `CODEAGENT_WEBUI_TRANSCRIPT_REASONING_MAX_CHARS` | `50000` | reasoning 展示上限 |

## Skills 与日记（Phase 1）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_SKILLS_AUTO` | `1` | `0` 关闭按 query 动态选 skill |
| `CODEAGENT_SKILLS_TOP_K` | `3` | 每轮最多注入 skill 数 |
| `CODEAGENT_DIARY` | `1` | `0` 关闭日记 |
| `CODEAGENT_DIARY_KEEP_DAYS` | `7` | 日记保留天数 |

## 聊天与工具策略

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_CHAT_USER_ROUNDS` | `12` | API 投影保留用户轮数 |
| `CODEAGENT_MAX_TOOL_ROUNDS` | `24` | 单轮 chat 最大工具轮次 |
| `CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT` | `0` | 触顶后自动续跑 |
| `CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS` | `4` | 自动续跑最大段数 |
| `CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT` | `16` | Web 设置页默认工具轮次 |
| `CODEAGENT_AGENT_TOOLS_NO_CACHE` | `0` | `1` 禁用 per-agent 工具缓存 |
| `CODEAGENT_AGENT_TOOLS_MODE` | （空） | `all` 时不按 tools.json 过滤 |

## 与 Seed 的关系

- 内核项：写在 **`config/seed.env`**（`SEED_*`）。
- 产品项：写在 **`config/codeagent.env`**（`CODEAGENT_*`）；两个文件会一并加载（见 `seed.integrations.env_config`）。
- 也可写在同一文件或进程环境中；启动时调用 `codeagent.core.bootstrap.bootstrap_codeagent_runtime()`。
- 启动或保存配置后，`codeagent.core.seed_bridge.bridge_codeagent_env_to_seed()` 会把与内核同后缀的 `CODEAGENT_*` 复制为 `SEED_*`（仅当 `SEED_*` 未设置时），供 Seed / seed-tools 使用。

---

## 相关文档

- [`ROADMAP.md`](../../ROADMAP.md) — `SEED_*` / `CODEAGENT_*` 分层与 Phase 6.7–6.8
- [`PUBLIC_API.md`](../../PUBLIC_API.md) — 包依赖与公开面
