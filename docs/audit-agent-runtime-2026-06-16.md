# Audit: `seed/core/agent_runtime.py` — 核心引擎

- **日期**: 2026-06-16
- **文件**: `/home/u2/agent/seed/seed/core/agent_runtime.py`
- **行数**: 1945 行
- **检查方法**: 全文通读 + 关联代码 grep + 测试覆盖分析

---

## 架构问题

### 🔴 A1 — 单文件 1945 行，4.8x 超限

软上限 400 行，实际 1945 行。文件内包含 **5 个逻辑模块**：

| 范围 | 模块 | 约行数 |
|------|------|--------|
| 1–400 | 消息清洗/格式化辅助函数 (`_strip_think_markup`, `_detect_failure_streak`, `registry_to_openai_tools` 等) | 400 |
| 400–1155 | 上下文/压缩/消息管理 (`_clean_invalid_tool_call_arguments`, `build_api_projection_messages`, 压缩相关等) | 755 |
| 1155–1400 | `maybe_compact_context_messages` + `default_system_prompt` (含自身 import 块) | 245 |
| 1400–1800 | 核心工具循环 (`run_llm_tool_loop`, `_stream_llm_round`, `_execute_tool_with_cancel`) | 400 |
| 1800–1945 | 内联工具调用解析 (`parse_inline_qwen_tool_calls`, `parse_inline_json_tool_calls` 等) | 145 |

**影响**: 任一模块改动都可能影响整个文件的 import 顺序 / 函数可见性，难以独立测试。

### 🟡 A2 — 散落的多处 import 块

import 分布在 **至少 5 个位置**，部分重复：

| 行 | import |
|----|--------|
| 5–10 | `datetime`, `logging`, `re`, `typing`, `chat_events` |
| 109–111 | `typing(Sequence)`, `ToolRegistry` |
| 214 | `re` (第 3 次) |
| 426–432 | `json`, `os`, `re`, `typing`, `env_access`, `llm_exec` |
| 1099 | `os` (第 2 次) |
| 1145–1150 | `logging`, `os`, `typing`, `chat_events`, `llm_exec` |
| 1405–1414 | `asyncio`, `contextlib`, `json`, `logging`, `uuid`, `typing`, `chat_events`, `llm_exec`, `tool_runtime` |
| 1810–1815 | `json`, `os`, `re`, `uuid`, `typing`, `env_access`, `tool_runtime` |

**影响**: 同一模块 (`logging`, `os`, `json`, `re`, `typing` 等) 被 import 2-4 次，lint 不报错但说明文件需要拆分。

### 🟡 A3 — 核心工具循环零测试覆盖

| 函数 | 行 | 单元测试 | 集成测试 |
|------|---|---------|---------|
| `run_llm_tool_loop` | 1531 | ❌ | ❌ (在 `test_task_runner.py` 中被 mock) |
| `_stream_llm_round` | 1419 | ❌ | ❌ |
| `_execute_tool_with_cancel` | 1500 | ❌ | ❌ |
| `registry_to_openai_tools` | 172 | ❌ | ❌ |

仅有 `maybe_compact_context_messages` (126 行测试覆盖)、`_clean_invalid_tool_call_arguments` (270 行测试覆盖) 有针对性测试。

**影响**: 核心工具循环的 bug 可能在运行时才暴露，无法通过 CI 提前拦截。

---

## Bug / 缺陷

### 🔴 B1 (Medium) — `_stream_llm_round` 中 ContextVar 不传播到线程

**位置**: `_stream_llm_round` 第 ~1449 行

**场景**: `run_llm_tool_loop` 通过 `asyncio.to_thread()` 调用 `_stream_llm_round` → 运行在线程池中。

**问题**: `is_chat_cancelled()` 使用 `ContextVar` (第 14 行 `chat_events.py`)。Python 的 `ContextVar` **不会自动传播到线程池**。因此 `_stream_llm_round` 内部的 `is_chat_cancelled()` 永远返回 `False`。

```python
# 第 1449 行 — _stream_llm_round 内部
for event in llm.generate_stream(...):
    if is_chat_cancelled():   # ← 在线程中永远为 False
        break
```

**影响**: 用户点击"取消"按钮后，正在进行的 LLM 流式生成无法提前中断，必须等当前 round 完成。

**严重性**: Medium — 影响用户体验（取消有明显延迟），非数据损坏。

### 🟡 B2 (Low) — `record_round_usage` 在线程中静默失效

**位置**: `_stream_llm_round` 第 ~1472 行

**根因**: 与 B1 相同 — `ContextVar` 不传播到线程。`record_round_usage` 内部用 `_USAGE_CTX.get()` 获取累加器，在线程中拿不到。

```python
# usage_accumulator.py 第 9 行
_USAGE_CTX: contextvars.ContextVar[...] = ...
# 在线程中 _USAGE_CTX.get() 返回 None → record_round_usage 静默不做事
```

**影响**: 流式轮次的 token 用量数据不累加到全局统计。metadata 仍正确返回（只是 `record_round_usage` 作为副作用失效），用户侧影响极小。

### 🟢 B3 (Low) — 多处 `except Exception: pass` 吞错误

覆盖的调用点:

| 位置 | 行 | 具体代码 |
|------|----|---------|
| `_stream_llm_round` — on_text_delta | ~1453 | `except Exception: pass` |
| `_stream_llm_round` — on_reasoning_delta | ~1458 | `except Exception: pass` |
| `run_llm_tool_loop` — on_round_persist | ×3 | `except Exception: pass` |
| `run_llm_tool_loop` — projection_audit | ×2 | `except Exception: ...` |
| `_emit_context_usage_snapshot` | ~1494 | `except Exception: ...` |

**影响**: 前端回调或持久化失败时，无日志、无告警。调试困难。**建议**: 至少 `logger.exception(...)` 或 `logger.warning(...)`。

---

## 设计 / 关注点

### 🟢 C1 — `is_chat_cancelled()` 和 `emit_chat_event()` 都是 ContextVar

这本身是合理的设计（每个 chat session 有独立的 cancel/emitter 上下文）。问题在于 **`asyncio.to_thread` 不传播 ContextVar**。

**修复方向 (建议)**：
- 方案 A: 用 `contextvars.copy_context()` + `loop.run_in_executor()` 手动传上下文
- 方案 B: 将 `_stream_llm_round` 改成 async generator (如果 `llm.generate_stream` 支持异步)
- 方案 C: 最小修复 — 在 `run_llm_tool_loop` 的每次 round 之间检查 cancel，`_stream_llm_round` 内不做 cancel 检查

### 🟢 C2 — `_execute_tool_with_cancel` 用轮询 200ms 检查取消

每 0.2 秒轮询 `is_chat_cancelled()`。对于耗时很短的工具（<100ms），取消有明显滞后。对于长时间运行的工具（如代码执行），200ms 间隔可接受。

---

## 测试覆盖总结

| 函数 | 有测试? | 覆盖率 |
|------|---------|--------|
| `_clean_invalid_tool_call_arguments` | ✅ test_invalid_tool_call_args.py | 好 |
| `_sweep_empty_invalid_tc_turns` | ✅ test_invalid_tool_call_args.py | 好 |
| `_clean_orphaned_tool_calls` | ✅ test_invalid_tool_call_args.py | 好 |
| `_clean_orphaned_tool_results` | ✅ test_invalid_tool_call_args.py | 好 |
| `maybe_compact_context_messages` | ✅ test_context_compact.py | 中等 |
| `build_api_projection_messages` | ✅ (通过 compact 测试) | 间接 |
| `run_llm_tool_loop` | ❌ (在 task_runner 测试中被 mock) | 0% |
| `_stream_llm_round` | ❌ | 0% |
| `_execute_tool_with_cancel` | ❌ | 0% |
| `registry_to_openai_tools` | ❌ | 0% |

---

## 总结优先级

| # | 类型 | 严重度 | 描述 | 建议操作 |
|---|------|--------|------|---------|
| A1 | 架构 | 🔴 | 单文件 1945 行严重超限 | 拆分为 4-5 个模块文件 |
| A2 | 架构 | 🟡 | 散落重复 import | 随 A1 自动解决 |
| A3 | 架构 | 🟡 | 核心工具循环零测试 | 补 `run_llm_tool_loop` + `_stream_llm_round` 集成测试 |
| B1 | Bug | 🔴 Medium | ContextVar 不传播到线程，取消无效 | 修复 ContextVar 传播或改用 async |
| B2 | Bug | 🟡 Low | `record_round_usage` 在线程中静默失效 | 随 B1 修复自动解决 |
| B3 | Bug | 🟢 Low | 多处 `except Exception: pass` 吞错误 | 改为 `logger.exception()` |
| C1 | 设计 | 🟢 | ContextVar 传播方案选择 | 决策后再实施 |
