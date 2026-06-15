# Skills

本文件只保留**每轮对话都需要**的核心工作流。其余 skill 按需从 `$AGENT_SKILLS/` 动态加载。

---

## Skill: 项目全流程（requirement → design → task → 执行）

这是所有项目的**起点技能**。每次接到多步骤任务时执行。

### 一、模式判断

需求理解阶段，先判断走哪种模式：

```
维度清单（涉及 ≥1 个就算）：
□ 前端页面
□ 后端 API
□ 数据库
□ 第三方服务
□ 部署上线
□ 用户认证/权限

结果：
≤2 个维度 → 🪶 轻量模式
≥3 个维度 → 🏗️ 完整模式

特殊强制完整模式（不论维度）：
- 用户说"需要看方案再动手"
- 交付给客户/团队其他成员
- 涉及数据迁移/兼容
```

### 二、完整模式

#### Phase 1: 需求沟通 → `$DOCS/requirement.md`

1. **理解范围**：用 `project(summary)`、`file_search`、`git(log)` 快速了解项目现状
2. **写 requirement.md**：

```markdown
# requirement.md

## 模式
- 模式: full
- 状态: draft → confirmed

## 需求概述
三两句话说明核心目标

## 功能列表 & 验收标准
| # | 功能 | 验收条件（具体、可验证） | 优先级 |
|---|------|------------------------|--------|
| 1 | ... | ... | P0 |

## 边界（不做什么）
- ❌ 本版本不做...

## 五维扫描
- [dev] 技术风险与关键依赖
- [arch] 模块边界与限制
- [des] 用户流程与四种状态
- [ops] 部署与配置要求
- [pm] 范围与预估工期
```

3. **关键规则**：
   - **每条功能必须有验收条件**（可验证、可测试）
   - 写清边界（不做什么）
   - 五维扫描写入
   - **用户确认后才进 Phase 2**

#### Phase 2: Design + Diagnostic → `$DOCS/design.md`

1. **技术可行性验证（PoC）**：
   - 核心依赖能安装（`pip install` / `npm install`）
   - 关键 API 调用能返回数据
   - 有版本兼容风险的库做集成测试
   - PoC 不通过 → 回退选型，不硬着头皮往下走

2. **写 design.md**：

```markdown
# design.md

## 技术选型
框架、数据库、第三方依赖及选择理由

## 数据模型 & API 设计
表结构、API 路径、请求/响应格式、状态流转

## 目录结构
```
project/
├── app/
│   ├── api/       # 路由层
│   ├── services/  # 业务逻辑
│   └── models/    # 数据模型
├── frontend/
│   ├── pages/     # 页面
│   └── components/# 组件
└── tests/
```

## 关键决策及理由
为什么选 A 不选 B？有什么 trade-off？

## Diagnostic 检查清单
- [ ] 选型 PoC 验证
- [ ] 依赖检查（deps_check → 安全漏洞、许可证）
- [ ] 安全风险（注入/XSS/鉴权）
- [ ] 性能预估（数据量级、查询频率）
- [ ] YAGNI 检查（有没有过度设计）
- [ ] 配置外部化（所有配置环境变量化）
- [ ] 五维再检：[dev][arch][des][ops][pm]
```

3. **diagnostic 全部通过后才能进 Phase 3**

#### Phase 3: Wave 拆解 → `$DOCS/task.md`

1. **使用 `wbs_draft` 辅助**（复杂任务先 WBS 再拆）
2. **写 task.md**：

```markdown
# task.md

## Wave 1: 基础架构
  依赖: 无
  验收条件: ...
  任务:
    - [W1.1] 任务描述（5–30 分钟）
    - [W1.2]

## Wave 2: 核心功能（→ 验收后才能做 Wave 3）
  依赖: Wave 1
  验收条件: ...
  任务:
    - [W2.1]
```

3. **每个 TODO 必须写清楚验收条件**：

```
❌ 模糊：实现登录功能
✅ 清晰：输入正确账号密码→跳转首页；错误密码→提示"账号或密码错误"
```

4. **排序**：Wave 间按依赖排列，Wave 内任务无依赖可任意排序，高风险项优先做

5. **初始化 git（新项目）**：`git(init)` → `.gitignore`（含 `$SCRIPTS/`、`$TMP/`）→ `git(commit, message="chore: init")`

6. **用 `todo_tool` 同步创建 TODO**，使用 `[W1.1]` 前缀格式

#### Phase 4: 执行

每个 TODO 的完整执行流程（硬规则，不可跳过）：

```
① 写代码前
   ├── memory_search 查同类教训
   ├── 读现有代码结构，确认模块边界
   └── 已有模块 → git(log) 看历史

② 写代码中
   ├── 遵守文件上限（前300/后400/组件200行）
   ├── 必覆盖四种状态（loading/empty/error/success）
   ├── 新增配置必须环境变量化 + 默认值
   └── 同类问题第二次 → 先重构再继续

③ 写代码后 — 三步强制审查（不通过不 commit）
   ├── 步骤1: code_check（代码质量检查）
   │   └── 有报错必须修复，不跳过
   ├── 步骤2: 五维内嵌自审
   │   ├── [dev] 命名一致？Scout Rule？
   │   ├── [arch] 补丁链深度≥2？YAGNI？
   │   ├── [des] 四种状态覆盖？
   │   ├── [ops] 配置外部化？有日志？
   │   └── [pm] todo 状态更新了？
   └── 步骤3: 经验记录
       ├── self_reflect("这次学到了什么")
       └── 有价值模式 → 写入 memory.md 的 Know-How 区

④ 通过后
   ├── git(add) + git(commit) — commit message 写清楚（feat/fix/refactor/plan）
   └── todo_tool(update, status="completed")

⑤ 卡住
   ├── 尝试不同方案（最多2次）
   ├── 仍卡住 → status="blocked" 写明原因
   └── 换另一个 todo
```

#### Wave 验收（Phase 4 完成后）

每个 Wave 所有 TODO 完成后：

1. **对照验收条件逐一确认**
2. **code_check** + 测试/编译 + **UI 截图**（前端改动时）
3. **向用户展示结果**（截图/输出），**用户确认后进入下一 Wave**
4. 验收不通过 → 补修，不跳票

### 三、轻量模式

适用于 ≤2 个维度的场景（修 bug、加字段、小脚本）。

1. 跳过 `requirement.md` 和 `design.md`
2. 直接写 `$DOCS/task.md`（目标 + Wave 拆分 + 验收条件）
3. 按 Wave 执行（同上 Phase 4 的 TODO 执行流程）

```markdown
# task.md

## 目标
加一个用户头像字段

## Wave 1: 数据库 + API
  验收: POST /api/users 返回头像字段
  任务:
    - [W1.1] 改表 + 数据模型
    - [W1.2] 改 API schema + handler

## Wave 2: 前端展示
  验收: 用户详情页显示头像
  任务:
    - [W2.1] 改页面组件

## Wave 3: 交付
  验收: todo 清零、清理
  任务:
    - [W3.1] 交付审计
```

### 四、Plan 动态更新

开发过程中发现设计不合理时：
- 更新 `design.md`（技术方案变更）或 `task.md`（任务调整）
- 如果需求变更 → **先改 `requirement.md`**（唯一事实源），再同步 `design.md` 和 `task.md`
- commit message 写 `plan: xxx 调整`

---

## Skill: 五维内嵌检查清单

每个决策从五个维度同时审视，贯彻全流程。

| 阶段 | 检查内容 |
|------|---------|
| **Phase 1: 需求沟通** | 五维扫描写入 `requirement.md`，覆盖[dev][arch][des][ops][pm] |
| **Phase 2: Design** | Diagnostic 中包含五维再检 |
| **Phase 4: 执行** | 每个 TODO 三步审查中的五维自审 |
| **Wave 验收** | 检查有没有维度遗漏（5 个 commit 无设计师/运维维度 → 腐化信号） |
| **交付** | 五维审计跑一遍 |

**内嵌检查规则**（硬约束）：
- 同一模块同类修补 ≥2 次 → 重构前置
- 补丁链深度 ≥2 → 重写根模块
- 新组件必须覆盖 loading / empty / error / success 四种状态
- 新增配置项必须环境变量化 + 默认值
- 连续 5 个 commit 无设计师/运维维度 → 腐化信号

---

## Skill: 交付审计

交付前执行「五维全量扫描」，确保不遗漏任何一个维度。

详见 skill `delivery-audit`，检查维度：
- [pm] 项目完整性：todo清零、清理临时产物、文档归档
- [dev] 代码质量：lint、test、行数限制
- [arch] 架构健康：git log审计、补丁链检测
- [des] 交互体验：UI截图、四种状态、风格一致
- [ops] 运维检查：配置外部化、依赖、启动、日志

**交付前必须跑一遍交付审计**，不通过不交付。

---

## Skill: 错误调试全流程

从复现 → 定位根因 → 写回归测试 → 修复 → 验证 → 防复发。

详见 skill `error-debugging`，关键步骤：
1. **复现**：缩到最小复现步骤，产物是一条可执行的测试用例
2. **定位**：症状 vs 根因，二分法 / git bisect
3. **回归测试**：先写测试暴露 bug，再修复，测试永远留在测试集里
4. **修复**：最小改动 + 检查同类 + 补全边界
5. **验证**：自问"这个问题还会出现吗？"→ 再提交
6. **补丁链警告**：2次同类修补 → 底层设计问题，停手重构

---

## Skill: 结构化重构流程

检测到补丁链/文件严重超限/模块职责模糊时的重构方法论。

详见 skill `refactoring-workflow`，关键原则：
- 重构不加功能，先补测试再动手
- 小步提交：每次重构后都能跑
- 有回滚方案（分支或 tag）
- 重构后验证全量测试 + 行为一致性

---

## Skill: 技术债登记与管理

登记"知道有问题但当前不修"的事项，设到期时间，跟踪还债进度。

详见 skill `technical-debt-registry`，关键机制：
- 债务文件: `$PLANS/debt-registry.md`（自动创建）
- 登记时机: 临时方案/补丁链/设计缺陷/交付遗留
- 还债时机: 涉及同模块的新功能/到期触发重构/P0优先
- 债务状态: 🔴 critical / 🟡 open / ⬜ resolved / ❌ wontfix

---

## 项目文件布局（硬规则摘要）

| 目录 | 用途 | 说明 |
|------|------|------|
| `$DOCS/` | 正式文档 | `requirement.md`、`design.md`、`task.md` — 给人看，相对稳定 |
| `$PLANS/` | 工作计划 | `*-plan.md`、`debt-registry.md` — Agent 私有，可频繁更新 |
| `$SCRIPTS/` | 临时脚本 | 一次性，用完可删，禁止 `/tmp/` |
| `$TMP/` | 中间产物 | 截图、临时 DB、日志 — 交付前清空 |
| `$AGENT_STATE` | 会话接力 | 覆写，保持精简 |
| `$SESSION_LOG/` | 运行日志 | 追加，给人看 |

> 完整规则见 skill `project-docs-layout`。

## 其他 skill

场景化 skill（项目文件布局、代码目录与拆分、自主项目 cron、ast-grep、Web 搭建、pipeline、错误调试、代码审查、数据库、复盘、大文件写入、macOS 打包、记忆整理等）存放在 `$AGENT_SKILLS/`，系统会根据当前任务自动匹配注入。
