# Audit: CodeAgent WebUI — 2026-06-16

## 审计范围

`codeagent/codeagent/web/static/` — 67 JS + 25 CSS + body.html ≈ 14,705 行
拼接式 SPA（文件名排序 → 内联到 webui.html）

---

## 🐛 发现的问题

### Bug #1（低风险）: `bubbleAgentWithSplitToolTrace` 死参数

**文件**: `03f-timeline.js:5`

```js
function bubbleAgentWithSplitToolTrace(text, toolTrace, reasoningContent, opts) {
```

第三个参数 `reasoningContent` **在函数体内从未使用**。全部 7 处调用者均传 `null`：

| 调用位置 | 参数值 |
|----------|--------|
| `04-ws-connect.js:246` | `null` |
| `04-ws-connect.js:265` | `null` |
| `05a-session-history.js:71` | `null` |
| `05a-session-history.js:131` | `null` |
| `06-chat.js:33` | `null` |
| `06-chat.js:175` | `null` |
| `06-chat.js:191` | `null` |

且注释写了 `// 1. 文本内容气泡（reasoning_content 不展现给用户）` — 说明设计上就不展示。

**修复**: 删除该参数（或加 `_reasoningContent` 标记为无用）。

---

### ⚠️ 问题 #2（架构）: 5 个 JS 文件超过 400 行上限

| 文件 | 行数 |
|------|------|
| `11h-env-mcp-c-board.js` | **493** |
| `06c-camera.js` | **488** |
| `11g-env-paths-git.js` | **435** |
| `11f-env-llm-b-form.js` | **409** |
| `01c-session-tree.js` | **409** |
| `06-chat.js` | **308** (接近 300 上限) |

后端的 400 行上限在 JS 语境下同样适用，建议拆分。

---

### ⚠️ 问题 #3（CSS）: `05-chat-p1.css` 1000 行

单个 CSS 文件 1000 行，建议按功能域拆分（chat 气泡 / tool trace / compose 区等）。

---

### ⚠️ 问题 #4（架构风险）: 拼接式 SPA 的级联失败

67 个 JS 文件按文件名顺序拼接进单个 `<script>` 块。这意味着：

- **任意一个文件中的 syntax error** → 该文件及之后所有文件不执行
- 无模块打包工具支撑，无编译时错误检测
- 文件排序依赖 `glob("*.js")` 的字母序，新增文件必须小心命名

这是当前架构的固有限制，非 bug，但需 awareness。

---

### ⚠️ 问题 #5（代码风格）: `var` 大量使用（685 处）

`var` 的 hoisting 行为在大型 SPA 中用 `{ }` 块时容易导致细微 bug：

- `var` 声明：685 行
- `let` 声明：70 行
- `const` 声明：918 行

建议新代码统一用 `const`/`let`，旧代码在修改时顺带迁移。

---

### ✅ 正常项

| 项目 | 状态 |
|------|------|
| **上下文压缩指示器**（上次 Bug 修复） | ✅ 全部正确：`handleWsContextUsage` 的 `Object.assign` 模式、历史恢复、`recalcTokenUsageFromDom` 的 `compact_min_tokens` |
| **Mobile / iOS 键盘处理** | ✅ `visualViewport` + `touchstart` + z-index 临时降低 |
| **CSS 主题变量** | ✅ 基本统一使用 `var(--accent)`, `var(--text)`, `var(--border)` 等，少数字体色 fallback 为硬编码 |
| **WS 事件派发** | ✅ 数据驱动的 `WS_HANDLERS` 模式，清晰可控 |
| **Session 去重** | ✅ 15s 内重复 reply 去重 |

---

## 综合评价

| 维度 | 评分 | 说明 |
|------|------|------|
| **[dev] 代码质量** | ✅ 总体良好 | 1 个死参数 + 文件超限是主要问题 |
| **[arch] 架构** | ⚠️ | 拼接式 SPA 架构灵活但脆弱；5 个文件超限 |
| **[des] 交互体验** | ✅ | Mobile 端 iOS 键盘处理到位；状态覆盖较好 |
| **[ops] 可维护性** | ✅ | CSS 主题变量统一；WS 事件派发清晰 |
