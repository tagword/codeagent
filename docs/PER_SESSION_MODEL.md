# Per-session Model Stack

> 每个会话可独立覆盖 6 个模型选择（chat / vision / image_gen / audio / music / video_gen），
> 同时保留一个"全局默认"作为新会话的初始值。

## 用户视角

```
┌─ 顶部「模型栈」下拉（每个 session 独立）──────────┐
│  Chat  ▾ [Qwen2.5-72B-Local]  📌                │
│  识图  ▾ [默认]                                    │
│  生图  ▾ [Doubao-Seedream]  📌                   │
│  [⨯ 清除所有覆盖，回到全局默认]                     │
└───────────────────────────────────────────────────┘
```

- 📌 = 当前会话有自定义模型
- 没有角标 = 跟随全局默认
- 「清除本会话覆盖」= 一键回到全局默认

## 「环境配置 → 全局默认模型栈」面板

新会话的默认模型栈。低频设置入口，不易误改。

## 数据模型

**Session.metadata**（磁盘）新增 6 个可选字段：

| 字段 | slot |
|------|------|
| `llm_id` | `llm` |
| `vision_llm_id` | `vision` |
| `image_gen_llm_id` | `image_gen` |
| `audio_llm_id` | `audio` |
| `music_llm_id` | `music` |
| `video_gen_llm_id` | `video_gen` |

空 / 缺失 → 使用全局默认。

## 优先级链（前端 `getEffectiveModel`）

```
session override  →  global default  →  系统默认
```

## API

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/ui/session/model-stack?session_id=X&agent_id=Y` | 读 session 覆盖 |
| POST | `/api/ui/session/model-stack` | 写 session 覆盖（合并） |
| POST | `/api/ui/session/model-stack/clear` | 清除全部 6 个 |
| GET | `/api/ui/sessions?project_id=X` | 现在每行带 `model_stack_overrides: {count, has_any, keys}` 字段 |

## 关键文件

**后端**
- `codeagent/server/app_factory.py` — 3 个新 handler + 路由（注意：必须注册在 `Mount("/api/ui")` 之前）
- `codeagent/server/webui_api_app.py` — `api_sessions` 给每行加 `model_stack_overrides` 字段

**前端**
- `codeagent/webui/01k-model-stack-state.js` — 共享状态：session override / global default / 三级 resolver / 后端持久化
- `codeagent/webui/01k-model-stack-bootstrap.js` — 监听 `session-changed` 事件、刷新 selector、迁移老 key
- `codeagent/webui/11k-global-default-models.js` — 全局默认面板
- `codeagent/webui/01b-think.js` + 5 个 `01[cdhj]-*.js` — 6 个 selector 改为走 `ModelStackState`
- `codeagent/webui/01i-model-stack.js` — 📌 角标 + 清除按钮
- `codeagent/webui/body.html` — 新增 📌 角标节点 / 清除按钮 / 全局默认面板

## 老版本迁移

启动时一次性：把旧的全局 localStorage key（`oa_llm_preset_id` 等）当作"当前 session 的 override" 写一次，并清除老 key。完成后用 `oa_ms_legacy_migrated_v1` 标记，不再执行。

## 验证

- ✅ 单元测试：`_read_model_stack_from_metadata` 处理 None / {} / 含未知字段 / 含空白字符串
- ✅ HTTP 端到端：用真实 token 通过 TestClient 验证 GET / POST / clear / 错误输入 / sessions 列表带新字段
- ✅ 节点语法：所有新 JS 文件 `node --check` 通过
- ✅ Python 语法：所有改动文件 `ast.parse` 通过
