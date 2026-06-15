# 默认 Persona 模板

提炼自坤坤日常使用的全功能 persona，适配 CodeAgent 系统 prompt 注入机制。

## 文件清单

| 文件 | 来源 | 改动 |
|------|------|------|
| `agent.md` | 原版 | 去掉路径变量值定义，避免与系统注入的路径表重复 |
| `identity.md` | 原版 | 未改动 |
| `soul.md` | 原版 | 未改动 |
| `skills.md` | 原版 | 未改动 |
| `tools.md` | 原版 | "并行调用"精简为一句话，避免与 seed 自动注入的 safety 规则重复 |
| `user.md` | 重写 | 通用模板，去掉个人化信息 |
| `memory.md` | 清空 | 新用户无预置经验，使用中自然积累 |

## 适配说明

### 已解决的重复问题

1. **路径表**：agent.md 里不再定义 `$DOCS/`、`$PLANS/` 等路径具体值（但保留用法说明）；由 `prompt_enrichment._codeagent_path_registry` 动态注入当前值
2. **并行规则**：tools.md 精简为指引性说明；safety 规则由 `build_system_prompt` 末尾统一注入
3. **多模态说明**：由 `prompt_enrichment.vision_multimodal_appendix` 动态注入，user.md/memory.md 中不再包含

### 变量展开兼容性

所有 `$VAR` 引用会被 `render_persona` 展开，变量 key 与 `_build_seed_vars_dict` + `_codeagent_vars_dict` 对齐：

| agent.md 中使用的变量 | 来源 |
|----------------------|------|
| `$DOCS` / `$PLANS` / `$SCRIPTS` / `$TMP` / `$AGENT_STATE` / `$SESSION_LOG` / `$SESSIONS_ARTIFACTS` | `_codeagent_vars_dict` |
| `$AGENT_HOME` / `$AGENT_MEMORY` / `$AGENT_SKILLS` / `$WORKSPACE` | `_build_seed_vars_dict` |

### 生效方式

将 `codeagent/core/paths.py` 中 `_ensure_default_persona_files` 函数的 `defaults` 字典内容替换为本模板各文件内容，即可让新用户 `init` 时自动获取全套 persona。
