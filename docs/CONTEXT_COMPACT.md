# 上下文压缩（Context Compact）机制

## 概述

上下文压缩（Context Compact）用于控制 LLM 会话的上下文窗口大小，避免超出模型的 token 限制。当会话的上下文 token 量达到设定的阈值时，自动触发压缩操作，将历史消息精简为摘要。

## 核心参数

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| 触发阈值 | `SEED_CONTEXT_COMPACT_MIN_TOKENS` | 分子≥分母时触发 compact（默认 `100000`） |
| 运行时覆写 | - | 通过 WebUI 设置，覆盖环境变量，重启后丢失 |

## 指示器 UI

WebUI 顶栏右侧的环形指示器实时展示当前会话的上下文占用情况：

```
分子 / 分母（环状进度）
```

- **分子（prompt_tokens）**：当前会话上下文的 token 量，由 LLM API 返回，持久化到 session 元数据快照
- **分母（compact_min_tokens）**：触发压缩的阈值，来自 **前端变量 `_tokenContextMax`**，仅通过 WS 事件实时更新
- **超过 100%** → 自动触发 context compact

## 设计原则

**分子和分母是分离的**：分子是事实数据（不可变），分母是运行时配置（可变）——不放在同一个快照里。

- session 元数据的 `context_usage` 快照**只存分子**（`prompt_tokens`、`estimated_tokens`），不存分母
- 分母存储在前端变量 `_tokenContextMax` 中，仅通过 WebSocket 事件实时更新
- WebUI 修改阈值后，同时更新 `_tokenContextMax` 和后台运行时覆写

## 数据流

### 1. WebSocket 实时推送（LLM 调用时）

```
LLM 响应
  → app_factory.py: build_context_usage_snapshot()
  → 计算 prompt_tokens / estimated_tokens
  → _get_compact_min_tokens() 获取实时阈值
  → WS event {type: "context_usage", prompt_tokens, compact_min_tokens, ...}
  → 前端 04-ws-connect.js:  updateTokenUsage(j.token_usage, j.compact_min_tokens)
  → maxTokens = curOrUsage.compact_min_tokens（更新 _tokenContextMax 覆盖变量）
  → 同时持久化到 session metadata（快照，不包含 compact_min_tokens）
```

### 2. 页面加载 / 会话切换（恢复指示器）

```
页面加载
  → 立即（不等 DOM）fetch /api/ui/compact-config
  → setTokenContextMax(d.compact_min_tokens) ← 尽早初始化 _tokenContextMax
  → api_sessions（获取会话列表）
  → 从 session metadata 提取 context_usage（仅含 prompt_tokens 快照）
  → lastSessionsCache 缓存
  → loadSessionHistoryIntoLog 调用 updateTokenUsage({prompt_tokens}) ← 只传分子
  → maxTokens = _tokenContextMax（无 compact_min_tokens / context_limit 覆盖，回退到实时分母）

WS 事件到达后
  → compact_min_tokens 来自 WS 事件实时值
  → 覆盖 _tokenContextMax 更新指示器
```

**关键设计**：restore 时不传 `compact_min_tokens`，分母自然走 `_tokenContextMax` 回退路径。`_tokenContextMax` 在页面加载时通过 API 初始化，WS 事件保持实时更新。

## 相关 API

### `GET /api/ui/compact-config`

返回当前的 `compact_min_tokens` 值及是否有运行时覆写。

```json
{"compact_min_tokens": 50000, "runtime_override": null}
```

### `POST /api/ui/compact-config`

设置运行时覆写的 `compact_min_tokens`。

```json
// Request
{"compact_min_tokens": 50000}

// Response
{"ok": true, "compact_min_tokens": 50000}
```

### WebUI 中的设置入口

位于设置面板"上下文管理"区域，输入框 `#inpCompactMinTokens`：

- 加载时：`GET /api/ui/compact-config` → 填入当前值 + `setTokenContextMax()`
- 变更时：`POST /api/ui/compact-config` → 立即生效 + `setTokenContextMax()`
- 值取自 `_get_compact_min_tokens()`（优先返回运行时覆写，若无则返回环境变量值）

## 文件涉及

| 文件 | 职责 |
|------|------|
| `codeagent/server/app_factory.py` | WS 事件推送 + session 元数据持久化（不含 `compact_min_tokens`） |
| `codeagent/server/webui_api_app.py` | REST API（会话列表/历史 + compact-config） |
| `codeagent/webui/04-ws-connect.js` | WS 消息处理 + 紧凑配置设置入口 + `setTokenContextMax()` |
| `codeagent/webui/05a-session-history.js` | 页面加载后恢复指示器（不含 `compact_min_tokens`） |
| `codeagent/webui/06-chat.js` | 紧凑完成后的视图刷新 |
| `seed/core/agent_runtime.py` | `_get_compact_min_tokens()` / `set_compact_min_tokens()` |
