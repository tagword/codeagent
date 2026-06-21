# Tools / 能力边界

名称与 **seed-tools runtime registry** 一致。MCP 插件还会在运行时注册 `mcp__<server>__<tool>` 动态工具；不确定时用 `tool_search`。

> **Persona 列表 ≠ API schema**：此处是能力说明与选用策略。实际可调用的工具以运行时 **registry + 已连接 MCP** 注入 LLM 的 `tools` 为准（同一 user turn 内 schema 稳定，利于 KV cache）。Persona 中列出但未注册或未启用的工具无法产生 `tool_calls`。

## 分类清单

- **文件**: `file_read`, `file_write`, `file_edit`, `file_search`, `glob`, `grep`, `artifact_read`, `notebook_edit`
- **Shell / Git**: `bash`, `git`
- **Web / 浏览器**: `web_search`, `web_fetch`, `browser_status`, `browser_connect`, `browser_ensure_running`, `browser_targets`, `browser_new_page`, `browser_navigate`, `browser_screenshot`
- **代码**: `code_check`, `code_analyze`, `project`, `refactor`, `scaffold`, `apply_patch`, `symbol_search`, `symbol_index_refresh`, `lsp_definition`, `lsp_diagnostics`, `test_gen`, `test_run`, `workspace_verify`
- **流程 / 基础设施**: `todo`, `pipeline`, `diagram`, `deploy`, `deps_check`, `api_docs`, `db`, `wbs_draft`
- **记忆 / Cron**: `memory_search`, `self_reflect`, `seed_cron_path`, `seed_cron_reload`, `seed_cron_apply`, `codeagent_cron_path`, `codeagent_cron_reload`, `codeagent_cron_apply`
- **MCP**: `mcp_servers`, `mcp_list_tools`, `mcp_call`, `mcp_list_skills`, `mcp_skill`（动态 `mcp__*`）
- **多模态**: `attachment_resolve_path`, `vision_analyze`, `vision_analyze_directory`, `image_generate`, `music_generate`, `video_generate`, `audio_transcribe`, `video_analyze`
- **协作**: `hub_send`, `call_agent`, `dispatch`, `parallel`
- **其他**: `tool_search`, `instruction_read`；demo：`echo`, `calculate`, `counter`, `whoami`

选用策略见 `docs/default-persona-template/tools.md`。
