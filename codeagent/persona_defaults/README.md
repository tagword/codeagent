# Default Persona（唯一来源）

此目录是 CodeAgent **默认 Persona 的唯一权威来源**。

- 首次 `ensure_agent_scaffold` 会将这里的 `*.md`（不含本 README）复制到
  `{SEED_PROJECT_ROOT}/agents/{agent_id}/persona/`（通常即 `~/.codeagent/agents/default/persona/`）。
- 已存在的 persona 文件**不会被覆盖**。
- 修改默认人格：只改此目录，然后发新版 codeagent 包；老用户需手动更新或删除旧 persona 后重新 init。

文件清单：`agent.md`、`identity.md`、`soul.md`、`tools.md`、`skills.md`、`user.md`、`memory.md`

变量 `$DOCS` / `$SCRIPTS` 等由运行时路径表注入，见 `prompt_enrichment._codeagent_vars_dict`。
