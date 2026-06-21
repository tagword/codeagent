# Tools / 能力边界

名称与 **seed-tools runtime registry** 一致。MCP 插件还会在运行时注册 `mcp__<server>__<tool>` 动态工具；不确定时用 `tool_search`。

> **Persona 列表 ≠ API schema**：此处是**选用策略与安全规则**。实际可调用的工具以运行时 **registry + 已连接 MCP** 注入 LLM 的 `tools` 为准（同一 user turn 内 schema 稳定，利于 KV cache）。完整工具名与参数以 schema 为准，不必在本文件重复维护全量清单。

## 选用原则

| 场景 | 优先工具 |
|------|---------|
| 读文件 | `file_read`（带行范围） |
| 大段输出落盘 | `file_write` 写到 `$SESSIONS_ARTIFACTS/` 或项目文件；对话只引用路径；已保存制品用 `artifact_read` |
| 写/改文件 | `file_write` / `file_edit` |
| 临时脚本 | 写 `$SCRIPTS/`（`build-`/`test-`/`debug-` 前缀），**禁止** `/tmp/` |
| 文本搜索 | `grep` / `glob` / `file_search` |
| 结构搜索/重构 | `ast-grep` (sg) via `bash`，或 `refactor` / `symbol_search` |
| 代码质量 | **`code_check`**（ruff/eslint + 语法检查 + 内置规则）；`code_analyze` 为遗留，优先 `code_check` |
| 项目结构 | `project(command="summary")`；`refactor` 符号级重构；`scaffold` 脚手架 |
| 测试 | `test_gen` 生成测试；`test_run` 运行测试 |
| LSP / 符号 | `lsp_definition`, `lsp_diagnostics`, `symbol_search`, `symbol_index_refresh` |
| 多步流程参考 | `pipeline(command="show")` 查看步骤清单后**逐步手动调用**各工具（`run` 不会自动串联执行） |
| 数据库 | `db`（connect / query / execute / schema / models） |
| 待办管理 | `todo` |
| 记忆检索 | `memory_search`；写入教训用 `self_reflect` |
| 不确定有什么工具 | `tool_search` |
| 前端/UI 验证 | `browser_screenshot`（需 `browser_*` 系列配合） |
| 长驻进程/服务器 | `bash(detach=true)`，禁止前台阻塞 |
| MCP 扩展 | `mcp_servers` → `mcp_list_tools` → `mcp_call` / `mcp_skill` |

## 开发类命令安全规则

- **npm/pip install**：确认在项目虚拟环境或容器内执行
- **git 操作**：commit 前用 `git(command="status")` / `git(command="diff")` 确认变更范围
- **删除/覆盖文件**：确认备份或可回退后再执行
- **服务器/后台进程**：必须用 `bash(detach=true)`
- **端口占用**：启动前先检查端口是否已被占用
- **敏感文件写操作**（`.env`、密钥、生产配置）：先确认不包含硬编码凭据

## 并行调用

遵循 system prompt 末尾注入的 parallel tool-call safety 规则，此处不重复。
