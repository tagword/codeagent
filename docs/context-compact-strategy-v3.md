# Context Compact Strategy v3 — 长程开发与多产品

Status: **implementation spec** (Phase 0 / Phase 1)  
Related: `context-compact-summary-prompt-v2.md`, `seed/seed/core/agent_runtime.py`, `codeagent/server/app_factory.py`

## 背景

会话 `ebbb5a78` 暴露的问题：

- `compact_min_tokens=20000`，最终 `peak_prompt_tokens=53288`，**全程未 compact**
- compact 仅在「用户新消息入口」跑一次，触发依据是**上一轮** `prompt_tokens`（4.3k），不是本轮 peak
- 24 轮 tool loop + auto_continue 段之间**不再 compact**
- `state.md` 空，外存未与压缩联动

## 设计原则

1. **三层记忆**
   - **L0 热上下文**：recent tail（完整或投影）
   - **L1 温摘要**：`<<<SEED_COMPACT>>>` 链式摘要
   - **L2 冷存储**：`state.md` / `task.md` / artifacts（Agent 主动读写）

2. **职责分离**
   - **Seed**：何时压、怎么切、链式摘要、recent tail 投影、触发 token 算法
   - **Product（CodeAgent 等）**：orchestration（入口 / mid-loop / auto_continue）、摘要模板、state 注入
   - **Persona**：压前/压后更新 `$AGENT_STATE` 的行为约束

3. **保留轮数不由 LLM 决定**
   - `KEEP_USER_ROUNDS` = 结构偏好（env / 产品 preset）
   - 超预算 → `RECENT_MAX_CHARS` + 按 role 投影（已有 v2 方向）
   - LLM **只摘要 old 段**，输出结构化 continuation 字段，不决定 K

---

## 触发点（Triggers）

| ID | 时机 | 条件 | 层 |
|----|------|------|-----|
| **T1** | 用户新消息入口 | `resolve_trigger_tokens() >= min_tokens` | Product 调用 Seed |
| **T2** | tool loop 每轮 LLM 后 | 同上 + `SEED_CONTEXT_COMPACT_MID_LOOP=1` | Seed loop + Product 传 peak |
| **T3** | auto_continue 切段前 | segment 结束且 peak >= min | Product (`app_factory`) |
| **T4** | 软预警（已有） | peak >= min × `WARN_RATIO` (0.85) | Seed emit `context_usage` |
| **T5** | recent tail 投影（已有） | recent chars > `RECENT_MAX_CHARS` | Seed |

### 触发 token 算法（Seed 新增）

```python
def resolve_compact_trigger_tokens(
    *,
    persisted: dict | None,      # session metadata context_usage
    loop_meta: dict | None,      # 当前 run 进行中
    api_prompt_tokens: int | None = None,  # 显式传入（兼容旧 call site）
) -> int:
    candidates = [
        int((persisted or {}).get("peak_prompt_tokens") or 0),
        int((persisted or {}).get("prompt_tokens") or 0),
        int((loop_meta or {}).get("peak_prompt_tokens") or 0),
        int(api_prompt_tokens or 0),
    ]
    return max(candidates)
```

`maybe_compact_context_messages(..., api_prompt_tokens=X)` 内部改为使用 `resolve_compact_trigger_tokens`；call site 可继续传 `api_prompt_tokens`，但应优先传 peak。

Compact 成功后：call site 将 `loop_meta["peak_prompt_tokens"]` 重置为 compact 后首轮 API 值（或 0 直到下一轮 LLM），避免同 run 重复压。

---

## 保留轮数策略（非 LLM）

### 默认值（产品 preset）

| 产品 | `KEEP_USER_ROUNDS` | `COMPACT_MIN_TOKENS` | 说明 |
|------|-------------------|----------------------|------|
| **CodeAgent（代码）** | **2** | 20000 | 单 user 轮可含 24 tool 步 |
| DesignAgent（规划） | 3–4 | 25000 | 对话连贯性优先 |
| 电销 / 短任务 | 2–3 | 15000 | tool 链较短 |

CodeAgent 安装/默认 env 将 `CONTEXT_COMPACT_KEEP_USER_ROUNDS` 从 3 改为 **2**（与 `webui_api_app` setup 默认值对齐）。

### 可选启发式（Phase 1，默认关闭）

`SEED_CONTEXT_COMPACT_ADAPTIVE_KEEP=0`

当 `=1` 时，在固定 `KEEP_USER_ROUNDS` 基础上微调（**仍不用 LLM**）：

```python
def effective_keep_user_rounds(
    default_keep: int,
    *,
    trigger_tokens: int,
    min_tokens: int,
    recent_tool_char_ratio: float,  # recent tail 中 tool 内容占比
) -> int:
    keep = default_keep
    if trigger_tokens >= int(min_tokens * 1.5):
        keep = max(1, keep - 1)
    if recent_tool_char_ratio >= 0.75:
        keep = max(1, keep - 1)
    return keep
```

Audit 写入 `meta.compact.effective_keep_user_rounds` 与 `meta.compact.adaptive_reason`。

---

## 环境变量（新增 / 变更）

### Seed（`SEED_*`，CodeAgent 通过 bridge 映射 `CODEAGENT_*`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `SEED_CONTEXT_COMPACT` | `""`（产品层设 `1`） | 总开关 |
| `SEED_CONTEXT_COMPACT_MIN_TOKENS` | 30000（CodeAgent env: 20000） | 触发阈值 |
| `SEED_CONTEXT_COMPACT_KEEP_USER_ROUNDS` | 3（CodeAgent preset: **2**） | 保留 user 轮偏好 |
| `SEED_CONTEXT_COMPACT_MID_LOOP` | **0** → Phase 1 后 CodeAgent 设 **1** | T2：loop 内 compact |
| `SEED_CONTEXT_COMPACT_ADAPTIVE_KEEP` | **0** | 启发式微调 keep |
| `SEED_CONTEXT_COMPACT_RECENT_MAX_CHARS` | 120000 | recent tail 字符预算 |
| `SEED_CONTEXT_COMPACT_WARN_RATIO` | 0.85 | T4 预警 |
| `SEED_CONTEXT_COMPACT_SUMMARIZER_*` | （已有） | 摘要模型 |
| `SEED_CONTEXT_COMPACT_SUMMARIZER_PROMPT_FILE` | **新增，可选** | 覆盖 summarizer system prompt 路径 |

### CodeAgent 仅 orchestration（不改 Seed 语义）

| 行为 | 位置 |
|------|------|
| T1 入口 compact，trigger 用 peak | `app_factory.py` chat handler |
| T3 auto_continue 切段前 compact | `app_factory.py` auto_continue loop |
| compact 后 `state.md` 注入 | 已有 `llm_worker._inject_state_into_system`；Phase 1 扩展到 app_factory compact 路径 |
| 代码域 summarizer 模板 | `codeagent/runtime/compact_summarizer_prompt.md`（新文件） |

---

## Phase 0 — 修洞（优先）

**目标**：复现 ebbb5a78 路径时能产生 `compact_summarizer` audit。

### Seed 改动

1. **`resolve_compact_trigger_tokens()`** — `agent_runtime.py`
2. **`maybe_compact_context_messages`** — 用 resolve 替代纯 `api_prompt_tokens`；日志/audit extra 写入 `trigger_tokens`
3. **测试** — `tests/test_context_compact.py`
   - `peak > min` 但 `last_prompt < min` → 必须 compact
   - compact 后 messages 变短、`<<<SEED_COMPACT>>>` 出现

### CodeAgent 改动

1. **`app_factory.py` T1** — 入口 `_compact_pt` 改为：
   ```python
   peak = int(_prev_cu.get("peak_prompt_tokens") or 0)
   last = int(_prev_cu.get("prompt_tokens") or 0)
   _compact_pt = max(peak, last) or None
   ```
2. **`app_factory.py` T3** — auto_continue 切段前（inject nudge 之前）：
   ```python
   compact_result = maybe_compact_context_messages(
       api_msgs, llm,
       api_prompt_tokens=int(_seg_meta.get("peak_prompt_tokens") or 0) or None,
   )
   persist_compact_summary(chat_sess.messages, compact_result)
   if compact_result:
       _inject_state_into_system(api_msgs, agent_id)  # 抽取 shared helper
   ```
3. **默认 env** — `~/.dev_codeagent/config/env` 文档化；setup 默认 `KEEP_USER_ROUNDS=2`

### 验收

- [ ] audit 出现 `*-compact_summarizer-r000.json`
- [ ] audit chat 条目 system 含 `<<<SEED_COMPACT>>>`
- [ ] session 边界消息含 `_compact_summary`
- [ ] 模拟 24 轮 loop + auto_continue：peak 超过 min 后 msg 数下降或 body_bytes 回落
- [ ] trace / WS 有 `context_compact` 事件

---

## Phase 1 — 长程代码开发

**目标**：单请求内长 tool loop 不会无限制涨到 50k+ 而不压。

### Seed 改动

1. **`SEED_CONTEXT_COMPACT_MID_LOOP`**
2. **`run_llm_tool_loop`** — 每轮 LLM 后（`_record_peak_prompt_tokens` 之后）：
   ```python
   if mid_loop_enabled and resolve_trigger_tokens(...) >= min_tokens:
       result = maybe_compact_context_messages(messages, llm, api_prompt_tokens=peak)
       # 需 product 传入 persist 回调或返回 compact_result 由上层 persist
   ```
   - 设计：新增可选参数 `on_compact: Callable[[Optional[dict]], None] | None`
3. **`SEED_CONTEXT_COMPACT_ADAPTIVE_KEEP`** + `effective_keep_user_rounds()`
4. **`SEED_CONTEXT_COMPACT_SUMMARIZER_PROMPT_FILE`** — 产品可覆盖摘要 system prompt

### CodeAgent 改动

1. 启用 `CONTEXT_COMPACT_MID_LOOP=1`
2. **`compact_summarizer_prompt.md`** — 代码域模板，末尾固定：
   ```markdown
   ## Continuation pointers（必填）
   - Re-read: state.md, docs/task.md, …
   - Active task / todo: …
   - Do not redo: …
   - Blockers: …
   ```
3. **compact 后提示 Agent 更新 `$AGENT_STATE`** — 在 `context_compact` WS 事件或 persona 规则中强调
4. **`webui_api_app` setup 默认值** — `KEEP_USER_ROUNDS=2`, `MID_LOOP=1`

### 测试

- [ ] mid-loop：第 N 轮 peak 超阈值后 msg 数减少
- [ ] adaptive keep：高 tool ratio 时 effective_keep=1
- [ ] 多产品：仅改 env prompt file，Seed 测试仍通过

---

## 多产品影响

| 改动 | CodeAgent | DesignAgent | 电销 Agent |
|------|-----------|-------------|-----------|
| T1/T2/T3 机制 | ✅ | ✅ 同 Seed | ✅ 同 Seed |
| `MID_LOOP` 默认 | on | optional | optional |
| `KEEP_USER_ROUNDS` | 2 | 3–4 | 2–3 |
| Summarizer prompt | 代码模板 | 设计模板 | 线索/话术模板 |
| 外存文件 | state.md + task.md | design-brief 等 | lead-state 等 |

**Seed 不依赖产品包**；各产品独立 `SEED_PROJECT_ROOT` + env preset（见 `MULTI_PRODUCT.md`）。

`call_agent` / 团队子 Agent：各自 session 独立 compact；Lead 只收 artifact 摘要，不收全文 trace。

---

## 摘要 prompt 分层

| 层 | 内容 |
|----|------|
| **Seed 默认** | 通用 continuation（v2 现有 + TRANSIENT-FACT） |
| **Product 文件** | `SUMMARIZER_PROMPT_FILE` 覆盖 |
| **CodeAgent 默认文件** | Wave/文件/测试/blocker/pointers |

LLM 不决定保留轮数；LLM 在摘要中输出 **Continuation pointers** 段即可。

---

## 实施顺序（建议 PR 拆分）

1. **PR1 (Phase 0 Seed)** — `resolve_compact_trigger_tokens` + tests  
2. **PR2 (Phase 0 CodeAgent)** — T1 peak + T3 auto_continue + state inject  
3. **PR3 (Phase 1 Seed)** — mid-loop + adaptive keep + prompt file hook  
4. **PR4 (Phase 1 CodeAgent)** — env preset + code summarizer template + persona 一行  

---

## 非目标（本 spec 不做）

- LLM 动态决定 `KEEP_USER_ROUNDS`
- 本地 token 估算替代 API `usage.prompt_tokens`
- 跨 session 自动开新 session（仍由 persona 规则 + 用户决定）
- `call_agent` 子会话合并到 Lead 上下文

---

## 参考代码位置

| 模块 | 路径 |
|------|------|
| compact 核心 | `seed/seed/core/agent_runtime.py` — `maybe_compact_context_messages` |
| peak 记录 | 同上 — `_record_peak_prompt_tokens`, `build_context_usage_from_run` |
| Web 入口 | `codeagent/codeagent/server/app_factory.py` |
| state 注入 | `codeagent/codeagent/runtime/llm_worker.py` — `_inject_state_into_system` |
| 现有测试 | `seed/tests/test_context_compact.py` |
| 产品 env | `~/.dev_codeagent/config/env` |
