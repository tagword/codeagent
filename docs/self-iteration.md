# CodeAgent 自迭代仪表板

> 这是判断"自迭代到底有没有让 CodeAgent 变好"的唯一真理。
> 所有 cron、skill 调整、改动提案都必须看这张表的指标作为约束。

## 目标

让 `~/.codeagent/agents/default`（默认 agent 的运行时数据）在**不让人陷入维护负担**的前提下，越来越能处理同类任务。

## 核心指标（每周一行）

| 周次 | skills 数量 | experiences 数量（有内容）| daily 篇数 | 7d 新增 self_reflect | 重复经验合并 | 提案采纳率 | 备注 |
|---|---|---|---|---|---|---|---|
| W22 (2026-06-02) | 17 (+1) | 26 (7 项目 + 19 全局，全有内容) | 5 | 3 (项目级) | 1 | 100% (1/1) | v2 基线 + 接受首个提案: `async-state-propagation` |

> 每周日 04:00 由 `weekly-skill-audit` cron 写入一行。

## 7 个北极星指标

> ⚠️ 2026-06-02 试运行发现：现有 3 个指标采集路径有缺陷，已标记修复优先级。

### 1. 容量指标（看会不会爆炸）
- `skills 数量`：应保持 **10–25**，超过 30 触发整理
- `experiences 数量`：应保持 **20–80**，超过 100 触发 archive
  - ⚠️ **修复中**：应合并 `agents/default/memory/experiences/` 和 `agents/default/projects-data/*/memory/experiences/`
- `daily 平均长度`：单篇 < 200 行，超过 = 没提炼

### 2. 活力指标（看是不是死水）
- `7d 新增 self_reflect`：≥ 2 条 = 健康，0 条 = 警惕
  - ⚠️ **修复中**：现 `find -mtime -7` 把"被 touch 的旧文件"也算进去
- `7d 新增 skill`：通常 0，月度 1–2 = 健康
- `30d skill 引用次数`：每个 skill 至少 1 次，否则建议退役
  - ⚠️ **暂不靠**：grep `_artifacts` 找 skill 名不可靠（口述引用漏算）

### 3. 效果指标（看改完对不对）
- `提案 → 采纳 转化率`：> 50% = 评估准，< 20% = 评估瞎提
- `回归次数`：改了 skill 后同类错误再次出现 = 0

## 改动日志（每次大动必填）

| 日期 | 改动 | 提案来源 | 评估指标 | 结果 |
|---|---|---|---|---|
| 2026-06-02 | 建立自迭代基础设施三件套 | 本次会话 | — | 待观察 |
| 2026-06-02 | 修复 metrics-snapshot / weekly-skill-audit 路径（合并 projects-data） | manual pilot 试运行 | 修后 self_reflect 总数 0→26 | 成功 |
| 2026-06-02 | 提案 `async-state-propagation` skill | weekly-audit v2 | 等人工审 | 待定 |
| 2026-06-02 | 接受提案，写入 `async-state-propagation` skill | 提案通过 | skills: 16→17 | 待观察（回归计数） |

## 边界与禁区

- ❌ persona 核心 5 件套（`agent.md` / `soul.md` / `identity.md` / `tools.md` / `user.md`）永不自动改
- ❌ `codeagent/` 平台代码永不由本 agent 改（那是 release 流程）
- ✅ `agents/default/skills/` 允许提案 → 人工审核 → 应用
- ✅ `agents/default/memory/` 允许自动写入
- ✅ `agents/default/persona/memory.md` 允许自动追加（仅"近期活动"段）

## 触发动作的阈值（自动化）

| 触发条件 | 自动动作 |
|---|---|
| skills > 30 | 写 `experiences/skill-bloat-YYYY-MM-DD.md` 提醒 |
| 同一 self_reflect 关键词 3+ 次 | 起草新 skill 草稿到 `_proposals/` |
| 任一 skill 30d 0 引用 | 写入 `candidates-retire.md` |
| 改动后同类错误再现 | 自动写一条 regression 经验 |

## 复审节奏

- **日**：memory-organizer（已跑）
- **周**：skill-audit（本次新增）
- **月**：人工看一次本 dashboard，判定是否调整指标本身
