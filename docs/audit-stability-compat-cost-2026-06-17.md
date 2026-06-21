# 稳定性 / 兼容性 / 效率 / Token 费用优化记录（2026-06-17）

本文记录本次针对 `seed`、`seed-tools`、`seed-model-providers`、`codeagent` 的两轮修复与验证结果，便于后续回溯、发布说明与继续优化。

## 目标

- 修复会导致请求失败、返回异常或会话中断的高优先级 bug
- 提升跨仓联调与不同版本组合下的兼容性
- 降低超时、卡死、异常配置导致的稳定性风险
- 控制上下文膨胀与无效调用，降低 token 与网络成本

## 变更总览

### 1) `seed-model-providers` 兼容性修复

文件：
- `seed-model-providers/seed_model_providers/model_providers.py`

问题：
- 对 `seed.core.env_access` 新字段做硬依赖，在旧版本 `seed` 环境会触发 `AttributeError`（例如 `LLM_HTTP_REFERER` 缺失）。

修复：
- 增加安全 env 读取辅助函数：
  - `_env_names(...)`
  - `_pick_nonempty_env(...)`
  - `_pick_default_env(...)`
- 对关键配置项改为“优先读取 `env_access`，缺失时回退标准环境变量名”。

收益：
- `seed-model-providers` 与新旧 `seed` 版本组合的兼容性显著提升。

---

### 2) `seed` 跨仓导入兼容性修复

文件：
- `seed/seed/core/model_providers.py`

问题：
- 本地未安装 `seed-model-providers` 包时，`seed` 直接 `import` 失败（`ModuleNotFoundError`），影响 monorepo/sibling checkout 联调。

修复：
- 增加导入回退逻辑：当包不可导入时，自动尝试从同级源码目录 `seed-model-providers` 加入 `sys.path` 后再导入。

收益：
- 降低开发/调试环境对 pip 安装状态的强依赖，提升联调稳定性。

---

### 3) `seed` LLM 执行链路稳定性与成本优化

文件：
- `seed/seed/core/llm_exec.py`
- `seed/tests/test_llm_exec_regressions.py`（新增）

问题与修复：

1. `temperature=0` 被错误覆盖  
- 原逻辑使用 `temperature or self.temperature`，导致 `0` 被当作 falsy 覆盖。  
- 修复为 `self.temperature if temperature is None else temperature`（普通与流式接口一致修复）。

2. MiniMax 输入预估返回值类型不稳定  
- `_to_minimax_responses_input(...)` 有时返回 list，有时返回 tuple。  
- 修复为始终返回 `(input_items, out_tools)`，去除隐性异常路径。

3. `<think>` 清洗结果解包顺序错误  
- 返回值解包顺序写反，可能把正常内容误判为空。  
- 修复解包顺序，避免回复正文被错误清空。

收益：
- 提升响应可预测性与可复现性（尤其 `temperature=0` 场景）。
- 降低异常分支导致的中断与重试成本。
- 减少不必要发散输出，间接降低 token 消耗。

---

### 4) `seed-tools` Web/MCP 工具防失控优化

文件：
- `seed-tools/seed_tools/web.py`
- `seed-tools/seed_tools/mcp.py`
- `seed-tools/tests/test_web_tools.py`（新增）
- `seed-tools/tests/test_mcp_tools.py`（补充）

问题与修复：

1. `web_fetch` 可能拉取过大页面导致上下文膨胀  
- 新增 `SEED_WEB_FETCH_MAX_BYTES`，并做范围钳制（最小 32768，最大 20_000_000）。  
- 读取时按上限截断并标注 `...[body truncated ...]`。  
- 大页面摘要模式返回元数据新增 `body_truncated` 字段。

2. `web_search` 结果规模与重复结果浪费 token  
- `num_results` 安全解析并钳制至 `1~20`。  
- 按 URL 去重，减少重复条目进入上下文。

3. `mcp_call` 超时配置可能异常或过大  
- 对 env 读取结果做安全解析并钳制 `1~900s`，避免非法值导致异常或过长阻塞。

收益：
- 减少工具层“超大输入 + 重复输入 + 长阻塞”的 token/网络开销。
- 提升 MCP 调用与网页抓取在异常配置下的可用性。

---

### 5) `codeagent` 自愈模块稳定性修复

文件：
- `codeagent/codeagent/server/self_healing.py`
- `codeagent/tests/test_self_healing.py`（新增）

问题：
- 导入时一次性读取并固定 env，后续环境变化不生效。  
- `int(os.environ[...])` 直接解析，非法值可能异常。

修复：
- 引入运行时安全解析：
  - `_env_bool(...)`
  - `_env_int(...)`
  - `_heartbeat_timeout(...)`
  - `watchdog_interval()`
- `is_enabled()` 改为实时读取 env。
- 超时与周期参数增加上下限钳制：
  - heartbeat timeout: `10~3600`
  - watchdog interval: `1~600`

收益：
- 提升运行时配置变更可用性。
- 降低非法配置导致的崩溃或异常行为风险。

## 测试与验证

已通过测试（节选）：

- `seed-model-providers`
  - `pytest -q` → `72 passed`

- `seed`
  - `pytest -q tests/test_model_providers.py tests/test_mcp_client.py tests/test_context_compact.py tests/test_usage_accumulator.py` → 通过
  - `pytest -q tests/test_llm_exec_regressions.py tests/test_model_providers.py` → 通过

- `seed-tools`
  - `pytest -q tests/test_mcp_tools.py tests/test_web_tools.py tests/test_search_tools.py tests/test_shell_tool.py` → 通过

- `codeagent`
  - `pytest -q tests/test_self_healing.py tests/test_usage_billing.py tests/test_bootstrap.py` → 通过

## 影响面说明

- 本次改动以“低风险高收益”策略为主，主要是：
  - 兼容性回退
  - 边界钳制
  - 参数解析与默认值修正
  - 回归测试补齐
- 未修改核心业务协议语义，未引入破坏性配置项。

## 后续建议（可选）

- 基于线上日志继续观察 1~2 天：
  - 大页面抓取截断比例
  - MCP 调用超时分布
  - LLM 请求平均 tokens 与失败率
- 若数据稳定，可进一步收紧部分默认阈值，以继续降低 token 成本。
