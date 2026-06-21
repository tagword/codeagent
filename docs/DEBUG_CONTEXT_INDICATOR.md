# 上下文指示器问题排查流程

> 文档日期: 2026-06-16  
> 适用场景: WebUI 输入框右下角上下文占用指示器显示异常（长期 0%、频繁大幅涨跌、刷新后百分比不对等）  
> 相关文档: [CONTEXT_COMPACT.md](./CONTEXT_COMPACT.md)、[audit-context-compact-2026-06-16.md](./audit-context-compact-2026-06-16.md)  
> 本文档分三部分：**§0.0 底层逻辑**（最核心、可背）+ **§0 元认知与元知识**（展开版）+ **§1～§6 具体操作**（本功能的排查手册）

---

## 0.0 底层逻辑：调试在干什么

若只记一层，记这个。**调试不是找 bug 在哪一行，而是找「预期」和「实际」第一次分叉的地方。**

可以用一个式子概括大多数 UI / 状态类问题：

```
屏幕上看到的值 = 某条链路上「最后一次写入」的结果
                 （写入者可能口径不同）
```

所以排查永远在做四件事——顺序不要颠倒：

| 步骤 | 问句 | 产出 |
|------|------|------|
| **1. 定义** | 这个数**应该**是什么、**应该怎样变**？ | 不变量（invariant） |
| **2. 追踪** | **谁**在**何时**写入了显示？ | writer 列表 + 时间线 |
| **3. 对比** | 每一次写入的值，是否符合不变量？ | 第一次违规的 writer |
| **4. 归因** | 该 writer 的上游数据从哪来、为何错了？ | 根因 + 修复 |

下面三条是上面四步的「公理」——几乎所有具体技巧都是它们的推论。

---

### 公理 A：先有不变量，再找 bug

**没有「应该怎样」，就无法判断「错了」。**

- 「百分比在跳」不是 bug 描述；「同一轮未 compact 时分子应单调不减，却从 45k 跌到 8k」才是。  
- 不变量来自：**业务语义**（分子/分母各是什么）+ **正常生命周期**（执行中 / 刷新后 / compact 后）。

> 推论：读代码、grep、看 WS 之前，先用一句话写出 invariant。写不出来说明还没理解功能。

---

### 公理 B：显示问题是写入问题

**UI 很少自己算错；错在「太多人改同一块状态，且口径不一致」。**

心智模型：

```
多个 writer ──► 一个 sink（updateXxx / setState / 写 DOM）
                     │
                     └── 用户只看到「最后一次」
```

排查时**默认假设**：不是 sink 函数公式写错，而是  
① 不该写的 writer 写了、② 写入了低精度数据覆盖了高精度、③ 写入顺序和预期相反。

> 推论：`rg "updateXxx"` 列 writer，比精读 sink 函数优先。  
> 推论：DevTools 看事件**时间线**，比按 frontend/backend 模块切分优先。

---

### 公理 C：信源有等级，低等级不能覆盖高等级

系统里同一个「事实」往往有多条获取路径，**精度不同**：

```
运行时观测（WS/API 字段）  >  代码静态阅读  >  文档  >  直觉 / 用户猜测
```

同一条显示链上：

```
LLM API usage  >  服务端估算  >  DOM 估算  >  硬编码默认
```

bug 的常见形态不是「没有数据」，而是 **fallback 倒挂**：  
DOM 估算在 API 已经到达之后，又跑了一次 `recalc`，把精确值盖掉了。

> 推论：看到 fallback 链（if/else if），要问「低优先级分支会不会在错误时机触发？」  
> 推论：用户说「应该不是 X」——可以暂时移出假设，但**不能代替**运行时证据。

---

### 三个公理合成一个决策

```
1. 写出 invariant
2. 若「一直是 0 / 默认值」→ 查生产者断链（谁该写却没写、或被 git 删了）
3. 若「剧烈来回跳」       → 查多 writer + 信源倒挂（时间线对齐）
4. 若「稳定但整体偏差」   → 查分母/单位/配置层不一致
5. 若「仅某时机错」       → 缩小到该时机的唯一 writer 路径
```

**术语对照**（不必纠结用哪个词，指的是同一件事）：

| 你可能的叫法 | 本文档用的词 | 指什么 |
|--------------|--------------|--------|
| 底层逻辑 / 第一性原理 | 公理 A/B/C | 调试时始终成立的规则 |
| 元认知 | §0.1 | 公理之下，**怎么想**的习惯 |
| 元知识 | §0.2 | 公理在具体技术栈里的**落地**（WS、fallback、git） |
| 心智模型 | Single sink、信源栈 | 把公理可视化的一幅图 |

---

## 0. 元认知与元知识

本节回答：**做这类项目排查，需要具备什么思维习惯与背景知识**。  
「这类项目」指：前后端分离 + WebSocket 实时推送 + HTTP 兜底 + session 持久化 + 多数据源 fallback 的 Agent/WebUI 系统。

### 0.1 元认知：怎么想

元认知是「关于思考的思考」——不是记住某个 bug 的 fix，而是知道**遇到问题时应该先问什么、避免什么陷阱**。

#### （1）先对齐语义，再读代码

任何 UI 指标都有隐含的**业务定义**。排查的第一步不是 grep，而是回答：

- 这个数**代表什么**？（事实 vs 配置 vs 估算）
- 用户**期望它怎么变**？（单调递增？可回落？何时归零？）
- 文档里的定义和代码是否一致？

本例：指示器 = `prompt_tokens / compact_min_tokens`，不是 `占用 / 模型窗口`。  
若跳过语义对齐，很容易在用户说「和 context_limit 无关」时仍纠结分母，而忽略**分子被多路覆盖**。

#### （2）假设与证据分离

| 类型 | 示例 | 处理方式 |
|------|------|----------|
| **现象** | 「百分比从 70% 跳到 15%」 | 记录时机、tooltip 数值、是否可复现 |
| **假设** | 「是 context_limit 的锅」 | 待验证；不可直接当结论 |
| **证据** | WS 两条 `context_usage` 分子差 3 倍 | 可驱动修改 |

养成习惯：**用户判断、文档、代码、运行时日志是四种独立信源**，互相矛盾时以运行时证据为准，并回头更新文档。

#### （3）找「写入者」，不只看「读取者」

UI 异常几乎都是 **multiple writers → single display** 问题。  
思维模板：

```
显示值 = f(最后一次写入, 写入者的数据口径)
```

不要只读 `updateTokenUsage` 怎么算，而要问：**谁在什么时机调用了它？**  
用 `rg "updateTokenUsage"` 列出完整调用图，比单点读函数有效一个数量级。

#### （4）按时间线想，不只按模块想

静态模块划分（前端 / 后端 / seed）适合开发，不适合查「涨跌」。  
应建立**事件时间线**：

```
用户发送 → LLM 轮次 1 → WS context_usage → tool 执行 → WS reply → DOM recalc → HTTP finally
```

跳变发生在时间线上的哪一格，就在那一格找 writer。  
DevTools WS 面板是时间线的直接证据。

#### （5）区分「该变」与「不该变」

先写下**正常单调性约束**，再查异常：

- 同一轮对话、未 compact：分子应**大致单调不减**（每轮 tool 追加内容）  
- compact 后：分子应**台阶式下跌**  
- 分母：应**稳定**，除非用户改了阈值  

违反单调性约束的跳变 = bug；符合约束的跳变 = 正常或设计如此。

#### （6）警惕「清理死代码」类提交

全栈项目里，名为 cleanup / dead code 的提交常删掉**唯一生产者**而留下**所有消费者**。  
看到「长期 0% / 从不更新」，除了逻辑 bug，应立刻：

```bash
git log --oneline -20 -- <相关文件>
git show <commit> -- <file>
```

本例：`build_context_usage_snapshot` 被删，`_ctx = {}` 仍存在 → 生产者断链。

#### （7）文档是地图，不是 террит

`CONTEXT_COMPACT.md` 写「restore 只传分子」——若代码仍传 `context_limit`，以代码+运行时为准，并**回填文档或修代码**。  
元认知原则：**文档用于建立初始模型；代码与 WS 用于验证模型。**

#### （8）控制排查半径

| 信号 | 扩大半径 | 缩小半径 |
|------|----------|----------|
| 仅刷新后不对 | → restore / metadata 路径 | |
| 仅执行中跳 | → WS + 多 writer + 估算混用 | |
| 始终 0% | → 服务端是否生产 `_ctx` | 不必先查 CSS |
| 用户已排除某字段 | → 暂时移出假设集，查其他 writer | 不必反复证明该字段 |

---

### 0.2 元知识：需要掌握什么

元知识是**可迁移的领域背景**——换成功能（费用指示器、会话列表未读数）也适用。

#### （1）系统分层与信源优先级

本类项目通常存在**多条信源链**，且优先级写在代码 fallback 里：

```
精确度:  LLM API usage  >  服务端估算  >  DOM 估算  >  硬编码默认值
实时性:  WebSocket      >  HTTP 响应    >  页面 restore  >  本地变量初始值
持久性:  session metadata  >  前端内存变量  >  无（刷新丢失）
```

排查时要能画出当前功能的「信源栈」，并检查：**低优先级信源是否在不该出现时覆盖了高优先级**（本例：DOM 覆盖 API）。

#### （2）Single Sink / Multiple Writers 反模式

```
                    ┌─ WS handler ────────┐
                    ├─ HTTP finally ──────┤
  各种事件 ────────►│ updateTokenUsage()  │──► 一个 UI 元素
                    ├─ session restore ───┤
                    └─ DOM recalc ────────┘
```

**元规则**：sink 函数有 fallback 链时，每个 writer 必须遵守同一套字段语义；否则百分比/计数会跳。  
设计评审时应问：「有几个 writer？能否合并或加 monotonic guard？」

#### （3）事实数据 vs 配置数据

| 类型 | 特点 | 存储建议 | 本例 |
|------|------|----------|------|
| **事实** | 测量值，随对话变化 | 可持久化到 session | `prompt_tokens` |
| **配置** | 用户/env 设定，变的少 | 运行时变量 + API，慎存快照 | `compact_min_tokens` |
| **元信息** | 辅助判断，不参与 UI 主公式 | 可选 | `context_limit` |

混存或混传会导致：刷新后用旧配置当分母、或用模型窗口代替 compact 阈值。

#### （4）Fallback 链 = 隐式契约

`updateTokenUsage` 这类函数里的 `if / else if` 顺序是**契约**，不是实现细节：

```javascript
prompt_tokens → estimated_tokens → total_tokens   // 分子
compact_min_tokens → _tokenContextMax             // 分母（不应再 fallback 到 context_limit）
```

改一个分支或增删字段，要追问：**谁在什么 payload 里传了这个字段？会不会误触发下一级 fallback？**

#### （5）投影层 vs 展示层

Agent 系统中常见两层消息：

- **API 投影**（`build_api_projection_messages`）：真正送进 LLM 的内容，含 system、tool schema、隐藏字段  
- **DOM 展示**（聊天气泡）：用户可见文本，通常**更短**

用 DOM 估算 token **必然系统性低估**。任何「气泡算一遍、API 算一遍」的双路径都需要明确：**主路径只能有一个**。

#### （6）双通道推送：WebSocket + HTTP

| 通道 | 特点 | 典型用途 |
|------|------|----------|
| WebSocket | 流式、多事件、可能乱序 | 执行中实时更新 |
| HTTP | 一次响应、finally 块 | 整轮结束兜底 |

两者可能**重复更新同一 sink**。要检查：重复是否 idempotent？是否会用更差的数据覆盖更好的？

#### （7）配置的三层叠加

```
环境变量 (文件)  →  运行时覆写 (内存/API)  →  前端变量 (_tokenContextMax)
```

三层可不一致。页面加载时要确认**哪一层初始化前端变量**；保存时要确认**写了几层**（本例 env 页保存曾只改 env 却用 context_limit 更新前端）。

#### （8）Git 考古是回归排查的标准动作

不仅 `git blame` 一行，更要：

- `git log --oneline -- <file>` 看近期主题（fix / clean / refactor）  
- `git show` 看删除是否断链（删 function 但留 call site，或反过来）  
- 关联**同一作者、同一时段**的跨仓库提交（本例 codeagent + seed 同时 clean）

#### （9）必备工具与用法

| 工具 | 元用途 |
|------|--------|
| `rg` / grep | 找所有 writer、reader、字段名 |
| 语义搜索 / 设计 doc | 建立数据流初始模型 |
| DevTools → WS | 时间线证据，对照 UI 跳变 |
| `console.debug` + `Error().stack` | 定位 JS 调用栈 |
| hover tooltip / aria | 不改代码快速读分子分母 |
| `git log` / `git show` | 找生产者断链、回归引入点 |

#### （10）本类项目的排查决策树（抽象版）

```
UI 指标异常
├─ 是否恒为 0 / 默认值？
│   └─ 是 → 查生产者是否存在、是否被删、payload 是否空
├─ 是否仅特定时机错（刷新/切会话/执行中）？
│   └─ 是 → 查对应路径的 writer 与 restore 语义
├─ 是否剧烈来回跳？
│   └─ 是 → 列所有 writer → 对照时间线 → 查信源优先级 inversion
└─ 是否整体偏差但稳定？
    └─ 是 → 查分母配置层 / fallback 链 / 单位口径
```

---

### 0.3 从元能力到本手册

| 元认知 / 元知识 | 在本案中的落地（§1～§6） |
|-----------------|-------------------------|
| 先对齐语义 | §1 分子/分母表 |
| 找所有 writer | §2 Step 2 `rg updateTokenUsage` |
| 时间线证据 | §2 Step 5 DevTools WS |
| 信源优先级 | §2 Step 4 API vs 估算 emit |
| 事实 vs 配置 | §5 restore 只传分子 |
| Git 考古 | §2 Step 4 `6045969` / `8a73394` |
| 单调性约束 | §4 验证清单 |
| Single sink 反模式 | §3 根因 R1/R2/R3 |

---

## 1. 先明确「分子 / 分母」分别是什么

排查前必须先对齐设计意图，否则容易在错误字段上浪费时间。

| 角色 | 字段 | 含义 | 数据来源 |
|------|------|------|----------|
| **分子** | `prompt_tokens`（优先） | 当前送入 LLM 的上下文 token 数 | LLM API `usage.prompt_tokens` |
| 分子 | `prompt_tokens` | LLM API `usage.prompt_tokens`（含 system/tools/reasoning） | 无 API 值时为 0，不再本地估算 |
| 分子兜底 | `total_tokens` | DOM 气泡文字估算 | `recalcTokenUsageFromDom()` |
| **分母** | `compact_min_tokens` | compact 触发阈值 | env / `POST /api/ui/compact-config` / 前端 `_tokenContextMax` |

**注意**: `context_limit` 是模型上下文窗口硬上限，**不应**参与指示器百分比计算。若代码里仍用它做分母，会导致百分比偏小或随模型窗口变化而跳变。

指示器核心函数: `codeagent/web/static/04-ws-connect.js` → `updateTokenUsage()`。

---

## 2. 排查操作流程（可复现）

以下流程按实际排查「频繁大幅涨跌」问题时使用的顺序整理。

### Step 0 — 记录现象

在浏览器里 hover 指示器，记录 title _tooltip_ 内容，例如：

```
上下文 45.2k / 30k tokens（100%）
```

关注三件事：

1. **分子**（第一个数字）是否在同一轮对话中大幅来回跳  
2. **分母**（第二个数字）是否稳定为 compact 阈值（如 30k），还是变成了 128k / 200k  
3. 跳变发生在什么时机：LLM 回复中 / tool 执行后 / 整轮结束 / 刷新页面后

### Step 1 — 读设计文档，建立数据流心智模型

```bash
# 阅读 compact 机制与指示器约定
codeagent/docs/CONTEXT_COMPACT.md
```

重点看：

- 「指示器 UI」章节：分子 / 分母定义  
- 「数据流」章节：WS 推送 vs 页面 restore 两条路径  
- 「开发注意事项 → denominator 覆盖路径」：restore 时只传分子的规则

### Step 2 — 定位所有会调用 `updateTokenUsage` 的入口

```bash
cd codeagent
rg "updateTokenUsage|recalcTokenUsageFromDom|setTokenContextMax" codeagent/web/static/
```

2026-06-16 排查时找到的**全部更新入口**：

| 文件 | 触发时机 | 风险 |
|------|----------|------|
| `04-ws-connect.js` → `handleWsContextUsage` | WS `context_usage` 事件 | 正常主路径（API 精确值） |
| `04-ws-connect.js` → `handleWsContextCompact` | compact 完成后 | 正常（应下跌） |
| `04-ws-connect.js` → `handleWsReply` | WS `reply` 事件 | ⚠️ 曾调用 `recalcTokenUsageFromDom` 覆盖 API 值 |
| `06-chat.js` → `submitChatMessage` finally | HTTP `/api/chat` 返回 | 正常（`j.context`） |
| `05a-session-history.js` | 切会话 / 加载历史 | ⚠️ 曾传 `context_limit` 污染分母 |
| `04-ws-connect.js` → `recalcTokenUsageFromDom` | DOM 气泡估算 | ⚠️ 分子远低于 API 值 |

**排查原则**: 指示器异常几乎都是「多个入口先后写入，且分子/分母口径不一致」。

### Step 3 — 读 `updateTokenUsage` 的分母优先级

打开 `04-ws-connect.js`，检查分母计算逻辑：

```javascript
var maxTokens = _tokenContextMax;  // 兜底
if (curOrUsage.compact_min_tokens > 0) maxTokens = ...;
// ⚠️ 若仍存在下一行，就是 bug：
else if (curOrUsage.context_limit) maxTokens = curOrUsage.context_limit;
```

若 `context_limit` 仍在 fallback 链上，且 WS / restore  payload 里带有模型窗口值（128k），分母会被拉大，百分比突然变小。

### Step 4 — 追踪服务端 WS 事件构造

```bash
rg "context_usage|build_context_usage_snapshot|_emit_context" \
  codeagent/server/app_factory.py seed/seed/core/agent_runtime.py
```

确认两件事：

1. **`build_context_usage_snapshot` 是否仍被调用**  
   - 输入: `build_api_projection_messages(...)` 投影后的 messages + LLM `meta.usage`  
   - 输出: `{ prompt_tokens, context_limit, message_count, compact_min_tokens, ... }`  
   - 若 `_ctx = {}` 空 dict 仍被使用 → 分子恒为 0，指示器长期 0%

2. **工具循环中 `_emit_context_usage_snapshot` 调用几次、是否混用 API 与估算**  
   - LLM 轮次结束 + 有 `last_meta` → API `prompt_tokens`（偏高、准确）  
   - 工具执行后再 emit、无 `meta` → 纯本地估算（常偏低）  
   - 两者交替推送 → 同一轮对话内百分比大幅回落

用 git 查近期是否误删了关键调用：

```bash
cd codeagent && git log --oneline -10 -- codeagent/server/app_factory.py
cd ../seed    && git log --oneline -5  -- seed/core/agent_runtime.py
git show <commit> -- <file>   # 查看具体删了什么
```

2026-06-16 实际发现：`6045969` 删掉了 `app_factory.py` 里对 `build_context_usage_snapshot` 的调用；`8a73394` 删掉了 `agent_runtime.py` 里相关函数（后已恢复）。

### Step 5 — 在浏览器 DevTools 验证「谁在改指示器」

1. 打开 WebUI → DevTools → **Network** → 筛选 **WS**  
2. 发送一条会触发 tool call 的消息  
3. 观察 `context_usage` 事件序列中 `prompt_tokens` / `compact_min_tokens` 字段  
4. 对照指示器跳变时刻，看是否出现：
   - `prompt_tokens` 从 45000 变为 0 或很小值  
   - 分母从 30000 变为 128000  
   - 同一轮内连续两条 `context_usage`，数值差距很大

可选：在 `updateTokenUsage` 开头临时加日志（本地调试）：

```javascript
console.debug('[tokenUsage]', curOrUsage, 'max=', _tokenContextMax, new Error().stack);
```

看 call stack 即可知道是哪个入口覆盖了读数。

### Step 6 — 区分「分母问题」vs「分子问题」

| 现象 | 更可能原因 | 验证方法 |
|------|------------|----------|
| 百分比长期极低（如 1%～5%）但对话很长 | 分母过大（200k 默认值 / context_limit） | hover title 看 `/` 后面是否是 30k |
| 长期 0% | 分子未推送（`_ctx` 空 / WS 未连） | 查 WS `context_usage.prompt_tokens` 是否为 0 |
| 同一轮内 70% ↔ 15% 来回跳 | 多入口覆盖 + API vs DOM 估算混用 | Step 5 + Step 2 对照 |
| 仅 compact 后下跌 | 正常 | `handleWsContextCompact` + `prompt_tokens_after` |
| 刷新后百分比变 | restore 传了错误字段 | 查 `05a-session-history.js` 是否只传分子 |

用户反馈「频繁大幅涨跌」且确认与 `context_limit` 无关时，**优先查 Step 2 的多入口覆盖**，而不是分母。

---

## 3. 2026-06-16 实际根因汇总

| # | 根因 | 表现 | 修复 |
|---|------|------|------|
| R1 | `handleWsReply` 调用 `recalcTokenUsageFromDom()` | API 45k → DOM 估算 8k，百分比暴跌 | 删除该调用 |
| R2 | 工具循环结束后二次 `_emit`（无 API meta） | API 值后接估算值，分子回落 | 删除工具轮次末尾 emit |
| R3 | `curTokens=0` 时强制显示 0% | 执行中 45% → 0% → 45% 闪烁 | 运行中 session 跳过 0 值覆盖 |
| R4 | `updateTokenUsage` 仍用 `context_limit` 作分母 fallback | 分母偶发变为 128k | 移除该 fallback |
| R5 | session restore 传入 `context_limit` | 刷新后百分比偏小 | restore 只传 `prompt_tokens` |
| R6 | env 保存误用 `inpContextLimit` 更新 `_tokenContextMax` | 改 compact 阈值后分母不对 | 改为 `inpCompactMinBytes` + `POST /compact-config` |
| R7 | （历史）`build_context_usage_snapshot` 被删 | 指示器长期 0% | 恢复服务端快照构造 |

---

## 4. 修复验证清单

完成修改后，按以下步骤验收：

- [ ] **单轮纯文本对话**：指示器从低到高缓升，不回落  
- [ ] **多轮 tool call**：每轮 LLM 结束后上升，工具执行期间不闪 0%  
- [ ] **hover title**：分母始终为 compact 阈值（如 30k），不是 128k / 200k  
- [ ] **刷新页面**：百分比与刷新前接近（restore 只读 metadata 分子）  
- [ ] **修改 compact 阈值并保存**：分母立即更新，百分比相应变化  
- [ ] **触发 compact**：百分比明显下跌，系统消息提示 compact  

DevTools 快速检查：

```
WS context_usage: prompt_tokens 单调不减（compact 除外）
不应出现: prompt_tokens 从 >0 突然变 0（运行中）
```

---

## 5. 防止回归的开发约定

1. **分母**：指示器只用 `compact_min_tokens` / `_tokenContextMax`，禁止 `context_limit` 进入 `updateTokenUsage` 分母链  
2. **restore**：`05a-session-history.js` 调用 `updateTokenUsage` 时**只传分子**  
3. **DOM 估算**：`recalcTokenUsageFromDom` 仅作 WS/API 不可用兜底，禁止在 WS `reply` 等主路径上调用  
4. **服务端 emit**：工具循环内不要在没有 API `usage` 时推送 `context_usage`（避免估算覆盖 API 值）  
5. **改 `_ctx` 构造前**：确认 `app_factory.py` 仍调用 `build_context_usage_snapshot`  
6. **PR 自检命令**：

```bash
rg "context_limit" codeagent/web/static/04-ws-connect.js codeagent/web/static/05a-session-history.js
rg "recalcTokenUsageFromDom" codeagent/web/static/
rg "build_context_usage_snapshot" codeagent/server/app_factory.py
```

---

## 6. 关键文件索引

| 文件 | 职责 |
|------|------|
| `codeagent/web/static/04-ws-connect.js` | `updateTokenUsage`、WS handler、`_tokenContextMax` |
| `codeagent/web/static/05a-session-history.js` | 会话切换时 restore 指示器 |
| `codeagent/web/static/06-chat.js` | HTTP chat 完成后 `updateTokenUsage(ctx)` |
| `codeagent/web/static/11e-env-config.js` | compact 阈值 env 保存 + 同步分母 |
| `codeagent/server/app_factory.py` | chat 结束后构造 `_ctx`、推送 WS、持久化 metadata |
| `seed/seed/core/agent_runtime.py` | `build_context_usage_snapshot`、`_emit_context_usage_snapshot` |
| `seed/seed/core/llm_exec.py` | `normalize_chat_usage`、OpenRouter headers、流式 `include_usage` |
| `seed-model-providers/…/model_providers.py` | 各厂商 Chat 协议、catalog；见 [`MODEL_PROVIDERS.md`](MODEL_PROVIDERS.md) |

---

## 7. 与模型提供商（usage 为空）

若某 preset 网关**不返回** `usage.prompt_tokens`，指示器会长期为 0；compact 也不会触发（API-only）。请先确认：

1. 直连官方 OpenAI 兼容端点（非残缺代理）
2. OpenRouter 已带 `HTTP-Referer` / `X-OpenRouter-Title`（2026-06-16 起 `llm_exec` 默认附带，可用 `SEED_LLM_HTTP_REFERER` 覆盖）
3. 流式场景末 chunk 含 usage（`stream_options.include_usage`）

详见 [`MODEL_PROVIDERS.md`](MODEL_PROVIDERS.md) 与 [`seed-model-providers/docs/PROVIDER_PROTOCOLS.md`](../../seed-model-providers/docs/PROVIDER_PROTOCOLS.md)。

---

## 7. 延伸阅读

- 机制设计：[CONTEXT_COMPACT.md](./CONTEXT_COMPACT.md)  
- 全链路审计案例：[audit-context-compact-2026-06-16.md](./audit-context-compact-2026-06-16.md)  
- WebUI 整体审计：[audit-webui-2026-06-16.md](./audit-webui-2026-06-16.md)
