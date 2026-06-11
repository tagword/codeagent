# Agent 管理功能重设计

> 2026-06-11 实施，包含后端 API 增强 + 前端详情页重构 + bug 修复

## 变更概述

### 1. 卡片展示三要素

每个 Agent 卡片显示：
- **名称**（首字母头像）
- **一句话描述**（后端从 `agents/<id>/description.txt` 读取）
- **工具状态标签**：`未限制` / `仅基础` / `N 工具` / `当前`

### 2. 详情页替代弹窗

**去掉所有弹窗**，编辑功能全部嵌入详情页：
- 新建 Agent → 直接在详情页表单中填写
- 系统提示词 → 详情页内 textarea 编辑 + 保存
- 工具（plugins）→ 详情页内「✎ 编辑」展开复选框网格，勾选后保存
- 描述 → 详情页内 inline edit

### 3. 工具管理

- 后端新增 `GET /api/ui/tools/available`：返回运行时全部可用工具列表（69 个）
- 后端 Agent CRUD API 支持 `tools` 字段的读写
- 前端详情页工具卡片：
  - 未配置 → 显示「未限制（全部工具开放）」
  - 已配置且 0 工具 → 「仅基础工具」
  - 已配置且有工具 → 显示已选工具标签
  - 「✎ 编辑」展开所有可用工具复选框

### 4. 技能（Skills）隔离加载

**背景**：Skills 面板原来使用全局 `agentId`，切换 Agent 详情后仍加载 active agent 的技能。

**修复**：
- 进入详情时传 `loadSkills(agent.id)`
- 新增/编辑/启用/停用/删除后传 `_currentSkillAgentId()`
- 刷新按钮传 `_currentSkillAgentId()`
- 空技能时更新 status 文本（原为：return 前未更新，残留旧计数）

### 5. 身份配置文件（MdFiles）隔离加载

- 进入详情时传 `loadMdFiles(agent.id)`

### 6. 页面跳转保护

- `loadAgentPage()` 开头调用 `_backToList()`，防止侧栏切换页面时覆盖详情面板的技能数据

## 后端 API

| 路径 | 方法 | 用途 |
|------|------|------|
| `/api/ui/agents` | GET | 列出所有 Agent（含 description） |
| `/api/ui/agents` | POST | 创建 Agent |
| `/api/ui/agents/:id` | GET | 获取单个 Agent 详情 |
| `/api/ui/agents/:id` | PUT | 更新 Agent（system_prompt / description / tools） |
| `/api/ui/agents/:id` | DELETE | 删除 Agent |
| `/api/ui/tools/available` | GET | 返回运行时所有可用工具列表 |

## 关键文件

| 文件 | 角色 |
|------|------|
| `codeagent/server/webui_api_app.py` | 后端 API（新增 tools/available、description 字段、PUT 保存） |
| `codeagent/webui/18-agent-mgr.js` | 前端 Agent 管理（卡片列表 + 详情面板） |
| `codeagent/webui/18-agent-mgr.css` | 前端 Agent 管理样式 |
| `codeagent/webui/13a-skills.js` | 前端技能面板（隔离加载） |
| `codeagent/webui/13b-tools.js` | 前端插件面板 + Agent 页面编排 |
| `codeagent/webui/12-plugins.js` | 前端身份配置文件面板（隔离加载） |
| `codeagent/webui/body.html` | 页面结构（Skills/MD 移入详情扩展区） |

## 后续

- [ ] 技能文件在详情页内的拖拽排序
- [ ] 工具编辑支持搜索/分类筛选
