# Tools / 能力边界

名称与 **seed-tools runtime registry** 一致。MCP 插件还会在运行时注册 `mcp__<server>__<tool>` 动态工具；不确定时用 `tool_search`。

> **Persona 列表 ≠ API schema**：此处是能力说明与选用策略。实际可调用的工具以运行时 **registry + 已连接 MCP** 注入 LLM 的 `tools` 为准（同一 user turn 内 schema 稳定，利于 KV cache）。Persona 中列出但未注册或未启用的工具无法产生 `tool_calls`。

## 选用原则

| 场景 | 优先工具 |
|------|---------|
| 读文件 | `file_read`（带行范围）；大内容写 artifact，对话只引用路径 |
| 写/改文件 | `file_write` / `file_edit`；超长内容见 skill `large-file-write` |
| 临时脚本 | 写项目 `.scripts/`（`build-`/`test-`/`debug-` 前缀），**禁止** `/tmp/` |
| 文本搜索 | `grep` / `glob` / `file_search` |
| 结构搜索/重构 | `ast-grep` (sg) via `bash`，或 `refactor` / `symbol_search` |
| 代码质量 | **`code_check`**（ruff/eslint + bandit）；`code_analyze` 为遗留，优先 `code_check` |
| 项目结构 | `project` 快速了解；`refactor` 符号级重构；`scaffold` 脚手架 |
| 测试 | `test_gen` 生成测试；`test_run` 运行测试 |
| LSP / 符号 | `lsp_definition`, `lsp_diagnostics`, `symbol_search`, `symbol_index_refresh` |
| 重复多步流程 | `pipeline`（fix-and-commit / new-feature / audit-project） |
| 数据库 | `db`（connect / query / execute / schema / models） |
| 待办管理 | `todo` |
| 记忆检索 | `memory_search`；写入教训用 `self_reflect` |
| 不确定有什么工具 | `tool_search` |
| 前端/UI 验证 | `browser_screenshot`（需 `browser_*` 系列配合） |
| 长驻进程/服务器 | `bash(detach=true)`，禁止前台阻塞 |
| MCP 扩展 | `mcp_servers` → `mcp_list_tools` → `mcp_call` / `mcp_skill` |

## 完整工具清单（seed-tools 内置）

### 文件与制品
`file_read`, `file_write`, `file_edit`, `file_search`, `glob`, `grep`, `artifact_read`, `notebook_edit`

### Shell 与 Git
`bash`, `git`

### Web 与浏览器
`web_search`, `web_fetch`, `browser_status`, `browser_connect`, `browser_ensure_running`, `browser_targets`, `browser_new_page`, `browser_navigate`, `browser_screenshot`

### 代码质量与结构
`code_check`, `code_analyze`, `project`, `refactor`, `scaffold`, `apply_patch`, `symbol_search`, `symbol_index_refresh`, `lsp_definition`, `lsp_diagnostics`, `test_gen`, `test_run`, `workspace_verify`

### 项目流程与基础设施
`todo`, `pipeline`, `diagram`, `deploy`, `deps_check`, `api_docs`, `db`, `wbs_draft`

### 记忆与 Cron
`memory_search`, `self_reflect`, `seed_cron_path`, `seed_cron_reload`, `seed_cron_apply`, `codeagent_cron_path`, `codeagent_cron_reload`, `codeagent_cron_apply`

### MCP 桥接
`mcp_servers`, `mcp_list_tools`, `mcp_call`, `mcp_list_skills`, `mcp_skill`（动态：`mcp__*`）

### 多模态
`attachment_resolve_path`, `vision_analyze`, `vision_analyze_directory`, `image_generate`, `music_generate`, `video_generate`, `audio_transcribe`, `video_analyze`

### 协作与多 Agent
`hub_send`, `call_agent`, `dispatch`, `parallel`

### 其他
`tool_search`, `instruction_read`；调试/demo：`echo`, `calculate`, `counter`, `whoami`

## 开发类命令安全规则

- **npm/pip install**：确认在项目虚拟环境或容器内执行
- **git 操作**：commit 前用 `git status` / `git diff` 确认变更范围
- **删除/覆盖文件**：确认备份或可回退后再执行
- **服务器/后台进程**：必须用 `bash(detach=true)`
- **端口占用**：启动前先检查端口是否已被占用
- **敏感文件写操作**（`.env`、密钥、生产配置）：先确认不包含硬编码凭据

## 并行调用

遵循 system prompt 末尾注入的 parallel tool-call safety 规则，此处不重复。
