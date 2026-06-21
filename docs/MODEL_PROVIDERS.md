# 模型提供商（Chat 协议与 Catalog）

CodeAgent 的 Web UI 预设、多模态 preset、上下文 usage 与 LLM 调用，均通过 **`seed-model-providers`** 包解析 provider / 协议。

Canonical 文档（请优先阅读）：

| 文档 | 内容 |
|------|------|
| [`seed-model-providers/docs/PROVIDER_PROTOCOLS.md`](../../seed-model-providers/docs/PROVIDER_PROTOCOLS.md) | Chat 协议、usage 归一化、OpenRouter 头、思考模式、调用链 |
| [`seed-model-providers/docs/MODEL_CATALOG.md`](../../seed-model-providers/docs/MODEL_CATALOG.md) | 内置 model 下拉列表 |
| [`IMAGE_GEN_PROVIDERS.md`](IMAGE_GEN_PROVIDERS.md) | 生图 / 音乐 / 视频协议 |
| [`DEBUG_CONTEXT_INDICATOR.md`](DEBUG_CONTEXT_INDICATOR.md) | 上下文条与 `prompt_tokens` |
| [`ENV_REFERENCE.md`](ENV_REFERENCE.md) | `CODEAGENT_*` / bridge 到 `SEED_*` |

---

## 2026-06-16 变更摘要

针对「网关 usage 为空、OpenRouter 无 header、思考模式多轮 400、各厂商 model 列表过旧」等问题，已在 providers 层对齐：

1. **`normalize_chat_usage()`** — 统一 `prompt_tokens`（Anthropic `input_tokens`、Gemini 字段名等）
2. **`apply_provider_chat_headers()`** — OpenRouter 默认 `HTTP-Referer` / `X-OpenRouter-Title`
3. **`apply_chat_stream_options()`** — 流式 `include_usage`
4. **思考协议** — DashScope `preserve_thinking`；Kimi `thinking.keep`；智谱新协议 `zhipu` + `clear_thinking: false`；Kimi/智谱 禁止与 `reasoning_effort` 同传
5. **`PROVIDER_CATALOG`** — 各厂商 model 列表与默认 model 更新

生效步骤：**重装包 + 重启 `codeagent serve`**。

---

## Web UI 与 API

| 入口 | 说明 |
|------|------|
| 环境配置 → 模型预设 | `materialize_preset_from_form()` 写 `config/seed.models.json` |
| `GET /api/ui/llm/providers` | `list_provider_catalog()` |
| `GET /api/ui/llm/presets` | 含 `providers` + 已保存 preset |
| Preset 字段 `_chat_protocol` | `enrich_preset_defaults()` 附加，便于调试 |

---

## Preset 字段 `provider`（Chat，更新后）

| provider | chat_protocol | 备注 |
|----------|---------------|------|
| `deepseek` | `deepseek` | thinking + reasoning_effort |
| `dashscope` | `dashscope` | enable_thinking + preserve_thinking |
| `moonshot` | `moonshot` | thinking.type；K2.6+ keep=all |
| `zhipu` | **`zhipu`** | thinking + clear_thinking=false |
| `minimax` | `minimax` | reasoning_split |
| `openrouter` | `openai` | + 自动 Referer/Title |
| `openai`, `anthropic`, `google`, `groq`, `volcengine`, … | `openai` | 通用兼容 |

生图 / 音乐 / 视频协议见 [`ENV_REFERENCE.md`](ENV_REFERENCE.md) 预设表与 [`IMAGE_GEN_PROVIDERS.md`](IMAGE_GEN_PROVIDERS.md)。

---

## 环境变量（OpenRouter / 思考）

通过 `CODEAGENT_*` 设置时，由 `seed_bridge` 同步为 `SEED_*`：

| 变量 | 用途 |
|------|------|
| `CODEAGENT_LLM_HTTP_REFERER` | OpenRouter Referer |
| `CODEAGENT_LLM_APP_TITLE` | OpenRouter 应用名 |
| `CODEAGENT_LLM_ENABLE_THINKING` | 全局思考开关 |
| `CODEAGENT_LLM_EXTRA_BODY` | 额外 JSON 请求体 |

详见 `seed/docs/ENV_REFERENCE.md`。
