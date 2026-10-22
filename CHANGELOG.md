# Changelog

## 1.2.8 (2026-10-22)

### 修复

- **A2A 服务端认证缺失（安全缺陷）**：Agent Card 声明了 `security: [{bearer: []}]`，
  客户端也会发送 `Authorization: Bearer`，但**服务端从未校验** —— 任何人（含伪造 token）
  都能调用 `/a2a` 让 agent 执行任意任务。实测：无 token / 伪造 token 均返回 HTTP 200
  - 新增 `a2a/auth.py`：复用 WebUI token，`hmac.compare_digest` 常量时间比较
  - 认证在 JSON-RPC 入口统一校验，覆盖 `message/send`、`tasks/get`、`message/stream`
  - 未配置 token 时放行（本机开发模式），此时 Agent Card **不再声明** security
    —— 声明与实现保持一致，避免客户端带 token 而服务端不校验

### 文档

- `ARCHITECTURE.md` 新增「A2A 协议层」章节（模块职责 + 认证设计）

### 测试

- 新增 `tests/test_a2a_auth.py`（11 项）：未配置放行 / 无 token 拒绝 / 错误 token 拒绝 /
  非 Bearer 方案拒绝 / 正确 token 通过 / 大小写不敏感 / Card 声明与实现一致
- 反向验证：禁用认证拦截后精确挂 3 项
- 修正 `test_a2a.py` 的认证隔离（原先会读真实 `config/webui.token` 导致用例全挂）

## 1.2.7 (2026-10-22)

### 修复

- **`self_reflect` 单槽覆盖导致反思静默丢失**（依赖 `seed-toolbox` 1.0.9）
  - `task_id="self_reflect"` 硬编码 → 所有 agent/session 写同一文件互相覆盖。
    实测：default 的全局反思被 agent0 的 newshub 日报任务覆盖，且无备份可恢复
  - 现在写前归档上一份到 `memory/reflections/`（保留 30 份），
    `self_reflect.md` 仍是最新一份（审计契约不变）

### 变更

- 依赖下限提升至 `seed-toolbox[code]>=1.0.9`

## 1.2.6 (2026-10-22)

### 变更

- **`seed-toolbox` 依赖加版本下限 `>=1.0.8`**（1.2.5 遗漏）
  - 1.2.5 虽已修复 `apply_patch`，但依赖未加下限，升级时 pip 可能保留旧版
    seed-toolbox，导致修复不生效——实测复现：装 1.2.5 却拿到 seed-toolbox 1.0.6
  - 现在强制 `>=1.0.8`，安装即获得 `apply_patch` 修复

## 1.2.5 (2026-10-22)

### 修复

- **`apply_patch` 会静默损坏文件**（依赖 `seed-toolbox` 1.0.8）
  - 上下文不匹配时不做校验，直接把内容写到声明行号处并报 `APPLIED` 成功。
    实测：声称第 1 行是 `XXX`（实际 `AAA`），仍把第 3 行 `CCC` 改成 `DDD`
  - 现在逐行严格校验上下文与删除行，不匹配即失败并报出行号 + 期望/实际内容，
    文件保持原样
  - 同时修复：无法创建新文件（`--- /dev/null`）、hunk 头行数不校验
    （`@@ -1,99` 实际 3 行也照打）

## 1.2.4 (2026-10-22)

### 新增

- **A2A 客户端** `codeagent/server/a2a/client.py` + `client_card.py`
  - 此前与服务端对等的「主动调用外部 Agent」能力缺失，只能手撸脚本直接 POST，
    跳过发现、硬编码 URL、假设对方支持 JSONRPC 与流式——对方一换地址/传输即失效
  - 现按规范走完整流程：Well-Known 发现 → 读 `supportedInterfaces` 协商传输 →
    按名片声明的 URL/认证/流式能力调用，**不允许跳过发现**
  - `AgentCard.select_interface()` 找不到本端支持的传输时直接报错，不猜测
- **`a2a` 工具** `seed_tools/a2a.py`（toolbox，分类 `agent`）
  - 分层：协议实现留宿主，工具层只做参数校验与格式化输出，延迟导入避免
    `seed-tools` 反向依赖宿主
  - `action`: `send` / `stream` / `get` / `cancel` / `discover`
  - token 走 `CODEAGENT_A2A_TOKEN` 环境变量，不硬编码
- **Agent Card 声明 `supportedInterfaces`**（规范 8.3.1），标准客户端可据此协商

### 修复

- **流式输出重复**（`流流式流式成功流式成功`）
  - 服务端按规范发 `append: true` 增量片段 + 结束时发 `append: false` 全量快照，
    客户端一律拼接导致内容重复
  - `StreamEvent` 新增 `append` 字段，按语义处理（增量拼接 / 全量覆盖）
- **A2A 上下文解析统一入口** `codeagent/server/a2a/context.py`
  - 原 `contextId` 解析逻辑在 `handlers.py` / `streaming.py` 各写一份，且只做
    `msg.context_id or new_id("ctx")`。两处漂移风险 + 无法扩展，抽成单一模块
    （`resolve()` / `record_task()` / `context_id_for_task()`），不碰 LLM、不碰存储层
- **只传 `taskId` 续聊时上下文断裂**（A2A 规范 3.4 MUST）
  - 此前服务端只认 `contextId`，客户端按规范只传上一次的 `taskId` 时，
    会被当成全新对话（新 `ctx` → 新 session），历史全丢
  - 现在：无 `contextId` 且有 `taskId` → 从 Task 反查 `contextId`；
    反查不到则记 warn 并新建（不静默复用同名上下文，避免串话）
  - `Task.metadata.inferredFromTask` 暴露是否走了反查，便于调用方排查
- **`contextId` / `taskId` 不匹配未拒绝**（规范 3.4 MUST）
  - 两者同时给出但归属不同时必须报 `-32602 Invalid params`，此前直接采信
    `contextId`，等于接受了一个属于别人的 `taskId`
- **`tasks/get` 只传 `id` 时报 `contextId is required`**
  - 规范允许仅凭 `taskId` 查询，现在同样走反查路径
- **`projectId` 丢失导致 A2A 会话落入「未分类」**
  - 支持 A2A 原生 `Message.metadata.projectId`（优先于
    `configuration.projectId`，后者保留向后兼容）
  - `Task.metadata` / `tasks/get` 回传 `projectId`，调用方可对账
- **不存在的 `projectId` 导致会话静默丢失**（严重）
  - `persist_chat_session` 注册会话依赖 registry 外键，项目不存在会抛
    `IntegrityError`，而 `chat_turn` 内持久化异常被吞掉 → 会话凭空消失
  - A2A 是外部入口、`projectId` 不可信，现在入口处校验：不存在则降级为
    未分类并记 warn，宁可归错类也不丢会话

### 测试

- `tests/test_a2a_tool.py` +16：append 语义（增量拼接 / 全量覆盖）、参数校验、
  token 解析、工具注册。含**反向验证**——注入错误逻辑后测试精确复现
  `流流式流式成功流式成功`，还原后全绿
- `tests/test_a2a.py` +14（共 23 项）：projectId 三层优先级、taskId 反查、
  mismatch 拒绝、`tasks/get` 反查、未知 projectId 降级
- 新增真实存储 E2E 脚本 `.codeagent/default/scripts/test-a2a-context-e2e.py`
  （隔离 `SEED_PROJECT_ROOT`）：覆盖登记幂等、反查、mismatch、自动生成、
  projectId 降级 6 组断言。首轮跑挂暴露了「registry 用 `session.name` 做索引」
  的真实行为——手工 `Session(id=..., name=...)` 不一致时反查必失，
  脚本已改为走 `load_or_create_chat_session` 与线上同路径
- 全量 800 passed


- **A2A 上下文解析统一入口** `codeagent/server/a2a/context.py`
  - 原 `contextId` 解析逻辑在 `handlers.py` / `streaming.py` 各写一份，且只做
    `msg.context_id or new_id("ctx")`。两处漂移风险 + 无法扩展，抽成单一模块
    （`resolve()` / `record_task()` / `context_id_for_task()`），不碰 LLM、不碰存储层

### 修复

- **只传 `taskId` 续聊时上下文断裂**（A2A 规范 3.4 MUST）
  - 此前服务端只认 `contextId`，客户端按规范只传上一次的 `taskId` 时，
    会被当成全新对话（新 `ctx` → 新 session），历史全丢
  - 现在：无 `contextId` 且有 `taskId` → 从 Task 反查 `contextId`；
    反查不到则记 warn 并新建（不静默复用同名上下文，避免串话）
  - `Task.metadata.inferredFromTask` 暴露是否走了反查，便于调用方排查
- **`contextId` / `taskId` 不匹配未拒绝**（规范 3.4 MUST）
  - 两者同时给出但归属不同时必须报 `-32602 Invalid params`，此前直接采信
    `contextId`，等于接受了一个属于别人的 `taskId`
- **`tasks/get` 只传 `id` 时报 `contextId is required`**
  - 规范允许仅凭 `taskId` 查询，现在同样走反查路径
- **`projectId` 丢失导致 A2A 会话落入「未分类」**
  - 支持 A2A 原生 `Message.metadata.projectId`（优先于
    `configuration.projectId`，后者保留向后兼容）
  - `Task.metadata` / `tasks/get` 回传 `projectId`，调用方可对账
- **不存在的 `projectId` 导致会话静默丢失**（严重）
  - `persist_chat_session` 注册会话依赖 registry 外键，项目不存在会抛
    `IntegrityError`，而 `chat_turn` 内持久化异常被吞掉 → 会话凭空消失
  - A2A 是外部入口、`projectId` 不可信，现在入口处校验：不存在则降级为
    未分类并记 warn，宁可归错类也不丢会话

### 测试

- 单测 +14 项（`tests/test_a2a.py` 共 23 项）：projectId 三层优先级、
  taskId 反查、mismatch 拒绝、`tasks/get` 反查、未知 projectId 降级
- 新增真实存储 E2E 脚本 `.codeagent/default/scripts/test-a2a-context-e2e.py`
  （隔离 `SEED_PROJECT_ROOT`）：覆盖登记幂等、反查、mismatch、自动生成、
  projectId 降级 6 组断言。首轮跑挂暴露了「registry 用 `session.name` 做索引」
  的真实行为——手工 `Session(id=..., name=...)` 不一致时反查必失，
  脚本已改为走 `load_or_create_chat_session` 与线上同路径

## 1.2.3 (2026-10-21)

### 修复

- **明确待办优先级：项目 todo 优先于 task.md 计划**
  - 此前 `get_pending_all` 依赖 `list(a.items) + list(b.items)` 的**书写顺序**
    隐式保证 todo 在前，从未作为规则表达；去重时若 plan 项与 todo 项文本相同，
    保留的恰是 todo（因先入 seen），但这属于巧合而非设计
  - 新增 `_sort_by_priority()`：显式定义优先级并加文档表格说明理由
    （todo 是当前任务亲手记的待办，粒度细、时效强；task.md 是项目级计划，
    粒度粗、可能过时）
  - `build_continue_nudge()` 改为按优先级**分组输出**：
    「优先处理（当前任务待办）」在前，「项目计划（task.md）」在后，
    让模型明确先后顺序，而非两类混在一起无从取舍

### 测试

- 新增 6 项测试锁定优先级：顺序、同级稳定、去重保留 todo、
  nudge 分组顺序、仅 todo 时不出现计划分组、仅计划时正常渲染
- 验证：临时倒序 `_sort_by_priority` 后 3 项测试失败，恢复后全绿

## 1.2.2 (2026-10-21)

### 修复

- **撞满工具轮次后静默停止**（v1.2.0 回归，严重）
  - v1.2.0 新增「pending todo 驱动续跑」时，把 pending 检查塞进了
    `if _stop_reason != "max_tool_rounds":` 分支，导致撞满 24 轮时整块跳过、
    `_pending_continue` 恒为 `False` → 直接 `break`，`_segment += 1` 不可达
  - 等于用新能力换掉了 v1.1.36 的原有能力（撞满轮次续跑），而非叠加
  - 修复：两条续跑路径拆开，pending 检查提到 `max_tool_rounds` 判断之外；
    撞满轮次时**无条件续跑**（不依赖 pending 查询，避免查询失败再次静默停止）

### 测试

- 修正 `test_pending_check_runs_even_when_agent_thinks_done`：原断言
  `assert 'if _stop_reason != "max_tool_rounds"' in src` 断言的正是缺陷结构
  本身，把 bug 锁成了预期；改为反向断言
- 新增 5 项**行为测试**：按真实控制流模拟分段循环，让「轮数用尽是否续跑」
  可证伪。源码文本断言只能证明「代码长这样」，不能证明「跑起来是这样」
- 验证：还原 v1.2.0 代码后新测试失败，恢复后全绿（750 passed，ruff 通过）

## 1.2.1 (2026-10-21)

- **fix(auto-continue)**：`get_pending_all` 补异常兜底。它是 chat_turn 续跑判定的入口，一旦抛异常会被 `except Exception: logger.debug(...)` 静默吞掉 → Agent 误判「无未完成事项」而停止。这是「24 轮后静默停止」的隐形来源
- **test(auto-continue)**：新增 `tests/test_auto_continue_wiring.py`（8 项接线层契约测试）。原有 41 项只覆盖 `auto_continue.py` 纯函数（该不该续），完全没测 `chat_turn.py` 接线 —— 而静默停止类 bug 只出在接线处。新增锁定：① 与 seed-kernel 的 `stopped_reason` 字段契约（上游改名会静默失效）② nudge 必须注入 `api_msgs`（续跑空转的唯一判据）③ pending 检查在 Agent 自认为完成时也执行 ④ 分段上限两处生效 ⑤ 记录开关默认关闭的事实
- **端到端实测**：mock LLM 循环验证「轮数用尽 → 续跑 → 第二段 LLM 收到 nudge」链路完好

### 已知行为（非 bug，供部署参考）
`CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT` **默认关闭**。未显式配置时，`max_tool_rounds`（默认 24）用尽即停止等用户。需要自主续跑必须设 `=1`。

## 1.2.0 (2026-10-18)

本轮把 RSI 实验线的 31 个 commit 合入正式线，并修复合入过程中暴露的计费缺陷。

### 新增能力
- **团队协作**：team run 真实 LLM 执行（替换 `[模拟]`）、成员可配角色提示词（A 形态角色扮演）、运行历史面板 + 失败 run 恢复重跑、卡死 run watchdog 惰性清理 + 手动停止、并发上限与成本统计
- **多 Agent 管理**：page-agent 多 Agent 管理、`list_agents` 工具让 Agent 可发现彼此、团队结果导出、Agent 页改主从两栏布局（页面高度 2400px → 1100px）
- **A2A 协议**：Agent Card + JSON-RPC 端点、`message/stream`（SSE 流式）、`tasks/get` 改从磁盘加载 session（重启后不再丢）
- **交付证据链**：Agent 声明完成时附可验证证据（测试计数去累加、lint/收集错误不再漏报）
- **自动续跑**：未完成事项驱动续跑，覆盖「做完一个 Wave 就问要不要继续」、`task.md` 计划检测、陈旧 pending 过滤
- **CLI**：`chat --project-id` 让派发任务归入 Web UI 项目视图

### 修复
- **计费时刻不可控**（真实缺陷）：`merge_accumulated_usage` 内部调用 `calculate_cost` 不传 `now`，费用随运行时刻在 peak/off_peak 间浮动，同一用量白天算 2 倍价。新增 `now` 参数透传
- **测试随运行时刻飘移**：`test_pricing` / `test_usage_billing` 未固定时段，白天跑 peak(2.0)、深夜跑 off_peak(1.0)，同一断言时对时错。全部显式传 `now`，并新增 peak vs off_peak 2 倍差验证
- **定价表口径同步**：测试跟随 `seed_model_providers` 1.0.2 真实定价表（`deepseek-flash` / `deepseek-v4-pro`）
- **CLI `--version` 写死**：硬编码 `v1.1.0`，改为动态读取包版本
- **版本号静默回落**：`__version__` 只查 `tagword-codeagent`，历史 editable 安装的 dist-info 名是 `codeagent` → 异常 → 回落 `0.0.0`。改为依次尝试两个名字
- **Agent 数据根不一致**：统一 agent 数据根解析，根治「新建后 WebUI 不可见」；空壳 agent 不再注册，persona 初始化不再静默降级
- **Agent 删除误删**：图标语义 + 弱化 + 强确认

### 依赖
- `seed-model-providers>=1.0.3`（新增非数值 usage 字段容错，避免 `ValueError` 中断计费）

### 质量
- 测试 737 passed（新增约 20 组测试，+6400 行）
- ruff 全仓归零

## 1.1.36 (2026-08-27)

- fix(build): Docker 镜像升级到 tagword-codeagent 1.1.36 + seed-kernel 1.0.19 — 让 Docker 部署也拿到 mcp_call 参数名冲突修复（此前钉死 seed-kernel==1.0.16 缺修复）。seed-kernel 1.0.19 含 ToolExecutor 调度参数 tool_name→tool 修复

## 1.1.35 (2026-08-27)

- fix(packaging): Windows Stage 卡死根治 — 所有下载（node/ast-grep/mac node tarball）改用 `_download_with_timeout`：分块读取 + 每块 socket 读超时。`urllib.urlopen(timeout=120)` 只限制 TCP 连接建立，响应体开始流式后停滞的对端会让 `copyfileobj` 无限挂起（v1.1.29/1.1.34 Windows 构建反复在 Stage bundled tools 卡到 15min 超时被 kill 的根因）。现在任何停滞都会在超时内抛错 → fallback 或失败可见
- feat(webui): git 凭据检查改用 `credential fill` 按 host 精确判定（`/api/ui/git` 新增 `action: fill`），前端 PAT 状态卡片不再用 `show` 结果做模糊字符串匹配，避免误判
- fix(webui): 文件下载 Content-Disposition 支持非 ASCII 文件名 — 按 RFC 5987/6266 输出 `filename*=UTF-8''percent-encoded`（裸 `filename="中文"` 触发 latin-1 header 编码异常 → UnicodeEncodeError 500）
- chore: `.gitignore` 忽略误建的 `home/` 测试数据库目录

## 1.1.34 (2026-08-27)

- fix(mcp): `mcp_call` 调用必崩修复 — `ToolExecutor` 调度参数 `tool_name` 与 `mcp_call` 工具入参 `tool_name`（远程工具名）同名冲突，`execute_async("mcp_call", tool_name=..., ...)` 抛 `TypeError: got multiple values for argument 'tool_name'`，请求到不了 MCP server。修复：executor 调度参数改名为 `tool`（bundled seed-kernel，见 tagword/seed@57fceef）。新增 4 个回归用例（sync/async × execute/execute_with_validation）

## 1.1.33 (2026-08-27)

- feat(chat): `api_chat` 抽薄壳 + `run_chat_turn` 核心抽取 — 聊天核心逻辑独立为 `chat_turn.py`，cron 任务复用 WebUI 消息口（同一套会话/上下文处理，不再各写各的）；`app_factory.py` 相应精简 ~800 行
- fix(server): WebUI `on_round_persist` 增量合并兼容 mid-loop compact — `n_before_ref` 索引失效（compact 后消息位移）时退化为最后一条 user 消息之后，防止工具循环输出丢失
- feat(packaging): PyPI 元数据营销优化 — classifiers + project_urls（Homepage/Repository/Changelog）+ description
- docs(readme): 营销导向重写 + 真实界面截图（替换侧边栏暴露本地项目名的旧截图）+ 官网徽章（codeagent.tagword.cn）

## 1.1.32 (2026-08-18)

- fix(webui): cron 定时任务时间配置保存 bug — ①daily/weekly/monthly 修改「分钟」保存不生效（`readFreqFromForm` 用 `querySelector('.cron-fld-minute')` 误取 hidden 的 hours-block 分钟下拉）；②「每 N 小时」模式非档位分钟（如 7 分）无选中项静默变 0 分（硬编码档位表缺动态插入）；③后端 `save_cron_job` 丢弃 `max_continuations`、`cron_status_for_ui` 不回显 `max_tool_rounds`/`max_continuations`（UI 编辑已有任务时轮数静默回退默认 30→12）。修复：minute select 类名按模式区分（`cron-fld-minute-hours`/`cron-fld-minute-time`）+ 改用 `minutesOptions()` 动态插入非档位值；依赖 seed-kernel ≥1.0.17 保留字段
- fix(webui): cron 调度器启动失败可见化 — `app_factory._lifespan` 用 `getattr` 兼容旧版 seed 缺失 `register_main_loop`，ImportError 不再吞掉整个调度器启动；cron 面板展示 `startup_error` / scheduler 未运行告警（此前静默白屏）
- test: tests/test_cron_time_options.js 新增 6 个时间保存回归用例（44 通过）

## 1.1.31 (2026-08-06)

- fix(core): `codeagent.__version__` 改为从包元数据动态读取（此前写死 1.1.8，与 pyproject 版本脱节，显示误导）
- build(docker): Dockerfile 重构为纯 PyPI 安装 — 本体与依赖（seed-kernel / seed-model-providers / seed-toolbox[code]）均从 PyPI 拉取（版本与 main 对齐），apt 切清华源、pip 用清华 PyPI 镜像；修复原 editable 安装导致的 `ModuleNotFoundError: No module named 'codeagent'` 镜像无法启动问题

## 1.1.30 (2026-08-06)

- fix(packaging): Windows stage 卡死根因修复 — node 下载改用带 120s 超时的 `urlopen`（此前 `urlretrieve` 无超时，网络挂起会无限等待卡死构建）；Windows 优先复用系统 node（runner 预装，本地复制零网络风险）；stage 步骤加 `timeout-minutes: 15` 保险

## 1.1.29 (2026-08-06)

- fix(packaging): Windows stage 崩溃根因修复 — 脚本输出含 `✓/←/→/⚠` 等 Unicode，Windows 控制台默认 cp1252 无法编码抛 `UnicodeEncodeError`；启动时强制 stdout/stderr UTF-8 容错（mac 默认 UTF-8 无此问题）

## 1.1.28 (2026-08-06)

- fix(packaging): Windows stage 失败诊断 — prepare_bundle_tools 异常输出 `::error::` annotation（check-runs 匿名可读），workflow 步骤失败时输出日志尾部，便于定位 Windows 构建问题

## 1.1.27 (2026-08-06)

- fix(packaging): Windows 构建修复 #2 — node 解压改用 `shutil.move`（`TemporaryDirectory` 在 `%TEMP%`（C 盘）而 workspace 在 D 盘，跨盘 `rename` 抛 WinError 17）；Windows stage 步骤输出日志并上传诊断 artifact（失败可查）

## 1.1.26 (2026-08-06)

- fix(packaging): Windows 构建修复 — ast-grep stage 支持 `.exe` 二进制查找（win zip 解压出 `sg.exe`，此前 `rglob("sg")` 匹配不到导致 SystemExit 构建失败）；eslint 经 `cmd /c` 执行 npm.cmd；Windows 上用副本替代 symlink（无特权时 symlink 失败）

## 1.1.25 (2026-08-06)

- fix(cron): 启动时 register_main_loop() 记录 uvicorn 主循环 — seed_cron_apply/reload 在 worker 线程通过 run_coroutine_threadsafe 安全触发 cron reload（app_factory.py）
- fix(packaging): 跨平台化 `prepare_bundle_tools.py`（支持 macOS + Windows）— Windows 打包内置 node/npm/eslint/ast-grep/ruff 到 bundle `tools/bin`（git 因体积/结构走系统 PATH）；Windows workflow 增加工具 stage 步骤
- fix(packaging): 所有 monorepo 兄弟包 `git clone` 显式 `-b main`（修复 seed-model-providers GitHub 默认分支为 master 导致 Docker 镜像/桌面应用拿到旧版 1.0.0 的问题，Dockerfile / build.yml / build_mac_dmg.sh / install.sh / install.ps1 共 5 处）
- fix(packaging): Windows spec ruff 收集与 prepare_bundle_tools 输出去重（bundle-tools 已有 ruff 时跳过 spec 直取）

## 1.1.24 (2026-08-06)

- fix(packaging): Windows exe 内置 ruff 二进制 — spec 将构建机 `Scripts/ruff.exe` stage 到 bundle `tools/bin` + `collect_all("ruff")`（此前 prepare_bundle_tools.py 为 macOS-only，Windows 构建无工具目录，code_check 运行时提示 ruff 缺失）；配套 seed-toolbox 1.0.5 的 frozen 探测逻辑

## 1.1.23 (2026-08-06)

- fix(webui): mermaid 放大预览空白 — 根因是含 foreignObject 的 SVG 绘制 canvas 必然污染（SecurityError），PNG 转换 fallback 的原始 SVG `width="100%"` 在 lightbox flex/fit-content 布局里塌陷成 0×0；改为 SVG DOM 直插放大预览（保留文字、矢量无损），显式设置 viewBox 像素尺寸，操作按钮移到弹窗右上角不再遮挡节点，关闭时完整重置状态

## 1.1.22 (2026-08-03)

- fix(webui): cookie 固定名 `ca_webui` + 统一读写端口来源（消除反向代理下登录后 401 循环）
- fix(webui): 登出彻底清理 cookie（无多端口残留）+ 滑动过期（剩余 TTL 过半自动续期）
- feat(webui): `CODEAGENT_WEBUI_COOKIE_SECURE` 环境变量，HTTPS 反代生产可开启 Secure
- fix: `_wd` 未初始化导致 project_id 为空时 UnboundLocalError（app_factory.py）

## 1.1.21 (2026-07-30)

- fix: PyInstaller GUI 模式 (console=False) 下 `sys.stdout=None` 导致 uvicorn 启动崩溃（启动前修补 stdout/stderr）

## 1.1.20 (2026-07-30)

- fix: 服务器启动失败诊断 — 添加异常捕获日志 + .spec 补充 h11/anyio/websockets/sniffio 隐性依赖

## 1.1.19 (2026-07-30)

- fix(windows): launcher 防护 macOS-only `import rumps`，修复 EXE 崩溃

## 1.1.12 ~ 1.1.18 (2026-07-25)

- fix(release): 连续修复 CI 发布资产路径问题（DMG/EXE 定位、upload-artifact 通配符、release 文件复制）

## 1.1.11 (2026-07-25)

- feat: Docker 镜像支持 — 多阶段构建，自动推送到 GHCR（`ghcr.io/tagword/codeagent`）
- feat: CI 增加 Docker 构建任务，tag push 时自动构建并推送
- fix: 手机端 files 模式下汉堡菜单改为抽屉侧边栏（与 chat 模式一致）
- docs: ARCHITECTURE.md 补充交付物说明和 Docker 使用方式
- docs: CONTRIBUTING.md 补充 Docker 本地构建与生产运行说明

## 1.1.8 (2026-07-24)

- feat: 项目级 skills 支持 — 自动扫描 `.codeagent/skills/`，Web UI 技能面板
- fix: 纯文本回复路径的流式占位符删除，覆盖无 tool rounds 场景
- fix: `_on_text_delta` 移除上一个流式占位符防止会话落盘重复
- docs: PyPI 安装说明 (tagword-codeagent)
- chore: 仓库清理 — 移除误入目录、整理 .gitignore、迁移构建脚本

## 1.1.7 (2026-07-20)

- feat(webui): mermaid 图表渲染 + PNG 放大/下载
- fix: 新用户无孩子时显示"添加宝贝"空状态而非白屏

## 1.1.6 (2026-07-08)

- fix: seed 私有依赖改为 git+https URL，`pip install -e .` 可直接安装
- chore: 添加 rules.md 和 upload-weapp.sh 自动上传脚本

## 1.1.5 (2026-07-07)

- fix: 根治 tool messages 在 compact 中丢失的问题 + WebUI 渲染修复
- clean: 移除 `_on_tool_round_persist` 中冗余的 `_streaming` 清理逻辑
- fix: 历史消息 API 不再过滤 `_streaming` 标记

## 1.1.4-p2 (2026-07-06)

- feat: 发布流程 pipeline — collector → raw → review → publish (WebUI + API + MCP)
- feat: 多宝贝家庭支持 — 快速入口可切换孩子
- feat: weapp 首页简化 — 选宝贝自动推荐主题/长度/语种
- feat: 工具链折叠到组容器，默认收起减少视觉干扰
- feat: 收藏按钮移至播放器左上角 + 分享按钮移至进度条右上角
- feat: 神经网络页重写 — 数据流动动画 + 实际应用案例
- feat: pcbagent 核心 + Web PCB Viewer
- feat: 播放器新增播放模式切换——连播/循环/随机
- fix: CDN marked/purify 替换为本地文件
- fix: Git 代理保存时同步写入 git config --global
- fix: MCP 连接失败不再阻塞 WebUI 加载
- refactor: 聊天对话区三刀手术切割

## 1.1.4 (2026-06-26)

- fix: 会话运行状态管理 — 三个根因修复
- fix: 项目目录对话框浏览按钮+路径展开+刷新联动

## 1.1.3 (2026-06-26)

- fix(webui): 修复 WS 断连后 running 状态丢失 + WS 事件不刷新会话列表 + DOM 重建后闪烁

## 1.1.2 (2026-06-26)

- 与 1.1.1 同日发布，包含以下补充修复

## 1.1.1 (2026-06-26)

### 多 Agent 体系 (M1)
- feat: Agent CRUD API + presets API + sessions API
- feat: Agent 管理前端页面 — 列表、创建、编辑、切换
- feat: Agent 详情页增强 — 描述、工具编辑、技能/MD 按 Agent 隔离
- feat: Agent 气泡着色 + 名称显示
- feat: WS 连接改造 — 切换 agent 时重连
- feat: Agent 切换器移至侧栏 brand，等宽不换行

### Team / Hub
- feat: Team CRUD API + Run engine + 管理前端
- feat: Hub SSE 服务端 + 前端面板
- feat: 自愈引擎 + 恢复 API + supervisord 配置
- feat: 健康看板 + CSS
- feat: M1 team foundation — config parsing, auto-registration, dispatch flow

### WebUI 重构
- refactor: 01c-session.js 拆 5 文件 (thinking / identity / tree / tree-menus / utilities)
- refactor: 11f-env-llm-presets.js / 11h-env-mcp.js 各拆 3 文件
- refactor: 00-storage.js 集中 localStorage/sessionStorage key
- refactor: 04-ws-connect.js onmessage handler 改派发表
- refactor: 抽 00-utils.js 统一 6 个散落的 escape 实现
- refactor(webui): switchToPage 回归自然布局，删除 31 行冗余 JS
- perf: 主区 scroll 检测 80ms 节流；17+8 次 getElementById 散落调用 → 集中 IIFE 缓存

### WebUI 新功能
- feat: 停止按钮交互优化 — 点按后显示 "⏳ 正在完成…"，完成时显示 "✅ 已停止。"
- feat: 上下文窗口上限 context_limit 加入环境配置页
- feat: 聊天与会话配置增加「最大输出 tokens」字段
- feat: preset 表单增加「最大输出 tokens」设置
- feat: 代码块复制按钮改为浮动右上角 style（隐藏式，hover 显现）
- feat: 项目规划面板同步展示 Agent 的 docs/ 和 plans/ 文档
- feat: 项目名右侧增加 + 按钮，hover 时显示，快速新建会话
- feat: 输入框草稿本地持久化（跨会话切换保留输入内容）
- feat: bootstrap 引导页替换为 CodeAgent 专属版（含配置指南和目录说明）
- feat: 流式生成时新增一行才触发滚动，避免同一行逐字下拉
- feat: WebUI MCP skill slash command — /skill
- feat(mcp): Streamable HTTP support
- feat: WebUI Git 凭据/SSH 管理
- feat(webui+cli): video_generate end-to-end wiring
- feat: per-session model override (model stack)

### 移动端
- fix: 手机视图顶栏抽屉覆盖全屏无法关闭根因修复
- fix: compose dock 按钮被 activity-bar 遮挡/键盘收起吞事件
- fix: 手机端项目列表按钮始终显示（桌面 hover 才显示）
- fix: token 为 0 时不显示红色；手机端 Enter 换行不发送

### 安装/脚本
- feat: Windows 安装/启动脚本 + run.sh 支持 seed 包自动安装
- feat: 一键运行脚本 run.sh + 国内源检测 + README 更新
- fix: 全面重写安装脚本，修复所有已知问题
- fix: 所有安装/启动脚本统一加超时 + 重试 + 可见输出
- fix: 跨系统自动安装 libxml2/libxslt（编译 lxml 所需）

### 其他
- feat: 添加 /api/health 健康检查端点 + 默认 persona 模板
- feat: .codeagent/{agent_id}/ 路径管理体系落地
- feat: 运行时环境信息块 (time + OS + workdir)
- feat: CodeAgent 扩展变量 + memory.md 渲染
- perf: cache system prompt per session via get_cached_system_prompt()
- refactor: token_counter → seed.core，消除逆向依赖
- refactor: web/ + webui/ + webui.html 合并为一个目录
- refactor: self_healing 配置改为惰性求值 + 安全 env 解析 + 范围约束
- refactor: 移除 codeagent/core/ 死代码 (image_gen/music/video/token_counter/llm)
- clean: 移除死代码目录（apps/tray、storage、integrations）和 webui 开发期文件
- clean: 移除未使用的 Monaco 文件编辑器组件

## 1.1.0 (2026-06-02)

- 多模态工具链：附件、图片理解、图像生成、音乐生成
- 会话存储重构与 Web UI 历史加载
- TTS 语音合成与模型栈设置
- MCP 环境配置 UI
- Tool-first multimodal pipeline with attachments, Web UI, and camera
- 移动端 WebUI + macOS 打包工具链
- auto_continue — 达到 max_tool_rounds 后自动续接
- 停止按钮 — ACTIVE_CHAT_CANCELS + is_chat_cancelled 完整链路
- 同 session 并发消息注入 + PENDING_INJECTIONS 队列
- 上下文 token 用量指示器 + DeepSeek V3 精确计费
- macOS .app bundle + DMG 安装包 + CI 自动构建
- 安装脚本 install.sh
- 代码全面清理和 ruff 修复

## 1.0.0 (2025-05-08)

- 首个公开发布版本
- 基础 Agent 执行引擎
- Web UI 界面
- 会话管理
- 工具调用系统
- 记忆存储
