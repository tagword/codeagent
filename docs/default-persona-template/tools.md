# Tools policy

## 选用原则

| 场景 | 优先工具 |
|------|---------|
| 读文件 | `file_read`（带行范围）；大内容写 artifact，对话只引用路径 |
| 写/改文件 | `file_write` / `file_edit_tool`；超长内容见 skill `large-file-write` |
| 临时脚本 | 写项目 `.scripts/`（`build-`/`test-`/`debug-` 前缀），**禁止** `/tmp/` |
| 文本搜索 | `grep_tool` / `glob_tool` / `file_search` |
| 结构搜索/重构 | `ast-grep` (sg) via `bash_exec`，见 skill `ast-grep-refactor` |
| 代码质量 | **`code_check`**（ruff/eslint + bandit），不用已弃用的 `code_analyze` |
| 项目结构 | `project(summary)` 快速了解；`refactor` 做符号级重构 |
| 重复多步流程 | `pipeline`（fix-and-commit / new-feature / audit-project） |
| 数据库 | `db`（connect / query / execute / schema / models） |
| 待办管理 | `todo_tool`（create / list / update） |
| 记忆检索 | `memory_search`；写入教训用 `self_reflect` |
| 不确定有什么工具 | `tool_search_tool` |
| 前端/UI 验证 | `browser_screenshot` |
| 长驻进程/服务器 | `bash_exec(detach=true)`，禁止前台阻塞 |

## 开发类命令安全规则

- **npm/pip install**：确认在项目虚拟环境或容器内执行
- **git 操作**：commit 前用 `git status` / `git diff` 确认变更范围
- **删除/覆盖文件**：确认备份或可回退后再执行
- **服务器/后台进程**：必须用 `bash_exec(detach=true)`
- **端口占用**：启动前先检查端口是否已被占用
- **敏感文件写操作**（`.env`、密钥、生产配置）：先确认不包含硬编码凭据

## 并行调用

遵循 system prompt 末尾注入的 parallel tool-call safety 规则，此处不重复。
