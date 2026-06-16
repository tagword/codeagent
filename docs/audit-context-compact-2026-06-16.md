# 上下文压缩（Context Compact）全链路审计报告

> 审计日期: 2026-06-16
> 审计范围: context_usage 前端指示器 + 服务端持久化 + 历史恢复全链路
> 风险等级: 🔴 1 中 + 🟡 3 低

---

## Bug 1 (🔴 中) — `handleWsContextUsage` token_usage 分支丢失 compact_min_tokens

**文件**: `codeagent/web/static/04-ws-connect.js:209`

**代码**:
```js
} else if (j.token_usage) {
    updateTokenUsage(j.token_usage, j.compact_min_tokens);   // ← BUG
```

**根因**:  
`updateTokenUsage(curOrUsage, compactMinTokens)` 的第二个参数 `compactMinTokens` **只在 `curOrUsage` 为原始值（非对象）时生效**。当 `curOrUsage` 是对象时，函数从 `curOrUsage.compact_min_tokens` 提取分母。

而 `j.token_usage` 是裸的 LLM API usage（如 `{total_tokens: 123, prompt_tokens: 100, completion_tokens: 23}`），**不包含 `compact_min_tokens` 字段**。所以分母回退到 `_tokenContextMax`（默认 200k），指示器百分比显示错误。

**预期行为**: 应当用 `j.compact_min_tokens` 作为分母（实际设置的上下文阈值）。

**修复方案**:
```js
// 把 compact_min_tokens 合并到 token_usage 对象中
updateTokenUsage(Object.assign({}, j.token_usage, {
    compact_min_tokens: j.compact_min_tokens,
    context_limit: j.context_limit,
}));
```

---

## Bug 2 (🟡 低) — 服务端持久化 `_snap` 缺失 `compact_min_tokens`

**文件**: `codeagent/server/app_factory.py:744`

**代码**:
```python
_snap = {
    "prompt_tokens": int(_ctx.get("prompt_tokens") or 0),
    "context_limit": int(_ctx.get("context_limit") or 0),
    "message_count": int(_ctx.get("message_count") or 0),
    "estimated_tokens": int(_ctx.get("estimated_tokens") or 0),
    "updated_at": chat_sess.updated_at or "",
}
```

**根因**:  
`_ctx` 来自 `build_context_usage_snapshot()` → `estimate_context_usage()`，返回的 dict **已经包含了 `compact_min_tokens`**（见 `seed/core/agent_runtime.py:983`：`"compact_min_tokens": _get_compact_min_tokens()`）。但 `_snap` 在持久化时**没有把它带进去**。

**影响**: 页面刷新后，从 metadata 恢复的 context_usage 没有 `compact_min_tokens`，前端只能用 `context_limit`（模型最大上下文）或回退到 `_tokenContextMax`（200k），百分比偏小。

**修复方案**:
```python
_snap = {
    "prompt_tokens": int(_ctx.get("prompt_tokens") or 0),
    "context_limit": int(_ctx.get("context_limit") or 0),
    "compact_min_tokens": int(_ctx.get("compact_min_tokens") or 0),  # ← 新增
    "message_count": int(_ctx.get("message_count") or 0),
    "estimated_tokens": int(_ctx.get("estimated_tokens") or 0),
    "updated_at": chat_sess.updated_at or "",
}
```

---

## Bug 3 (🟡 低) — 前端历史恢复代码丢失 `compact_min_tokens` / `context_limit`

**文件**: `codeagent/web/static/05a-session-history.js` (两处)

**代码（位置 1 — 快速恢复，行 ~93-100）**:
```js
if (Number(cu.prompt_tokens) > 0) {
    updateTokenUsage({
        prompt_tokens: cu.prompt_tokens,
    });
} else if (Number(cu.estimated_tokens) > 0) {
    updateTokenUsage({
        estimated_tokens: cu.estimated_tokens,
    });
}
```

**代码（位置 2 — 完整加载后校正，行 ~136-146）**:
```js
if (Number(cu.prompt_tokens) > 0) {
    updateTokenUsage({
        prompt_tokens: cu.prompt_tokens,
    });
} else if (Number(cu.estimated_tokens) > 0) {
    updateTokenUsage({
        estimated_tokens: cu.estimated_tokens,
    });
}
```

**根因**:  
两处恢复代码都只传了 `prompt_tokens` / `estimated_tokens`，**没有传 `compact_min_tokens` 和 `context_limit`**。当 `updateTokenUsage` 收到 `{prompt_tokens: N}` 时，查找 `.compact_min_tokens`（没有）→ `.context_limit`（也没有）→ 回退到 `_tokenContextMax`（200k）。

**影响**: 历史会话加载后/刷新后的百分比始终以 200k 分母计算，而不是实际设置的 compact_min_tokens。

**修复方案**:
```js
updateTokenUsage({
    prompt_tokens: cu.prompt_tokens,
    compact_min_tokens: cu.compact_min_tokens,
    context_limit: cu.context_limit,
});
```

---

## Bug 4 (🟡 低) — `recalcTokenUsageFromDom` 第二个参数被忽略

**文件**: `codeagent/web/static/04-ws-connect.js:131`

**代码**:
```js
function recalcTokenUsageFromDom() {
    // ... 计算 totalTokens ...
    var compactMinTokens = _tokenContextMax;
    updateTokenUsage({ total_tokens: totalTokens }, compactMinTokens);  // ← BUG
}
```

**根因**:  
与 Bug 1 相同模式 — `updateTokenUsage` 的第二个参数 `compactMinTokens` 只在第一个参数为非对象时生效。`{ total_tokens: totalTokens }` 是对象，所以 `compactMinTokens` 被忽略，且对象上没有 `compact_min_tokens` 属性。

**影响**: DOM 回退估算法始终以 `_tokenContextMax`（200k）为分母，不感知用户配置的 compact_min_tokens。

**修复方案**:
```js
updateTokenUsage({
    total_tokens: totalTokens,
    compact_min_tokens: _tokenContextMax,  // 直接传进对象
});
```

---

## 根因总结

所有 4 个 bug 的**共同模式**：`updateTokenUsage` 函数的重载设计不一致 —— 当参数为对象时忽略第二个参数，但调用方经常以对象+第二参数的方式传递。导致 `compact_min_tokens` 在多个路径中丢失。

| Bug | 影响链路 | 丢失位置 |
|-----|---------|---------|
| #1 | WS context_usage → 实时指示器 | token_usage 分支 |
| #2 | 服务端 → metadata 持久化 | _snap 构造 |
| #3 | metadata → 历史加载恢复 | 05a-session-history.js 两处 |
| #4 | DOM 回退估算 | recalcTokenUsageFromDom |

### 修复优先级

1. **Bug #1** — 高影响，每次 LLM 调用后指示器都错
2. **Bug #2 + #3** — 一起修，页面刷新/恢复后百分比错误
3. **Bug #4** — 低影响（仅 DOM 回退兜底路径）

---

## 附：更新日志

| 日期 | 操作 |
|------|------|
| 2026-06-16 | 初始审计，4 bugs 识别 |
