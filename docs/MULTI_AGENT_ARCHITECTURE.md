# 多 Agent 架构说明

> 本文档说明 CodeAgent 中两套多 Agent 机制的定位、边界与统一路径。
> 最后更新：2026-09-12

## 一、为什么有两套？

历史上 CodeAgent 存在**两套独立的多 Agent 实现**，职责重叠但互不相通：

| | **team_engine**（团队引擎） | **AgentRegistry**（agent 注册表） |
|---|---|---|
| 位置 | `codeagent/server/team_engine.py` | `seed/core/agent_registry.py` |
| 入口 | WebUI Agent 页「团队」面板 | chat 工具 `call_agent`/`dispatch`/`parallel` |
| 执行 | 成员 = 角色化 LLM 会话 | 成员 = 可调用 agent |
| 持久化 | run/step 落盘（`~/.codeagent/runs/`） | 无 |
| 状态（修复前） | 已真实执行 | **恒空 → 工具永远失败** |

**根因**：`AgentRegistry` 靠宿主显式 `register()` 注入，但**没有任何宿主代码调用它**——类都齐了，没人"造 agent 并注册"。

## 二、统一后的架构

修复后的核心原则：**一个执行载体，两个入口**。

```
                    ┌─────────────────────────────┐
                    │   LLMWorkerHandle           │
                    │  (runtime/agent_handle.py)  │
                    │  包 LLMWorker → run_task()  │
                    └──────────┬──────────────────┘
                               │ 同一执行路径
              ┌────────────────┴────────────────┐
              │                                 │
   ┌──────────▼──────────┐         ┌────────────▼────────────┐
   │  chat 工具委派       │         │  team_engine 团队运行    │
   │  call_agent         │         │  use_agent_loop=True     │
   │  dispatch           │         │  （B 形态成员）           │
   │  parallel           │         │                          │
   └─────────────────────┘         └──────────────────────────┘
```

### 关键组件

| 组件 | 文件 | 职责 |
|---|---|---|
| `LLMWorkerHandle` | `runtime/agent_handle.py` | 把 `LLMWorker` 适配成 `AgentHandle`（`run_task → {content, success}`）；处理嵌套事件循环 |
| `register_disk_agents` | `runtime/agent_bootstrap.py` | 扫描磁盘 agents 注册进 registry（幂等、跳过 testagent） |
| bootstrap 接入 | `server/app_factory.py` lifespan | 服务启动时自动注册 |
| 新建即注册 | `server/webui_handlers_agents.py` | 新建 agent 后立即注册 |
| `use_agent_loop` | `server/team_worker.py` | 团队成员可选走完整 agent 循环（B 形态） |
| `_run_member` | `server/team_engine.py` | 三种模式统一分发 plain / agent-loop |

## 三、两种成员形态

### A 形态（默认）：角色扮演
成员是**轻量文本角色**，走单次 LLM completion（`llm.generate`），无工具循环。

```json
{"id": "default", "role_prompt": "你是幽默的段子手"}
```

适用：快速产出、成本敏感、不需要工具的场景。

### B 形态：完整 agent 循环
成员走**完整 agent 工具循环**（工具 / 记忆 / MCP），与 chat 委派共用 `LLMWorkerHandle`。

```json
{"id": "default", "role_prompt": "你是资深工程师", "use_agent_loop": true}
```

适用：需要读写文件、调用工具、访问记忆的复杂任务。

## 四、并发安全

run 文件是「读-改-写」共享状态，多线程并发触碰。两道防线：

1. **`_RUN_LOCK`（RLock）**：串行化同一进程内的读-改-写。
2. **原子写（`_atomic_write_json`）**：临时文件 + `os.replace`，保证 reader 永远读到完整 JSON。
   - 修复前用 `write_text`，并发下 reader 会读到半截文件 → `JSONDecodeError` → run 看似消失。

线程同步：`wait_for_run(run_id)` join 后台线程，替代 sleep 轮询。

## 五、新增 agent 的完整生命周期

```
POST /api/ui/agents  →  ensure_agent_scaffold()
                     →  register_disk_agents([id], overwrite=True)
                     →  立即可被 chat 的 call_agent 调用
```

## 六、验证方式

```bash
# 1. 单元测试
pytest tests/test_agent_registry_bridge.py tests/test_team_engine.py

# 2. 真实 chat 工具调用（LLM 自主决定调用）
curl -X POST /api/chat -d '{"message":"调用 call_agent 工具...","agent_id":"default"}'
# 期望：tools_used 含 "call_agent"，reply 含子 agent 产出

# 3. 团队 B 形态
# 建团队时成员设 use_agent_loop: true，运行后 step output 应为完整 agent 产出
```
