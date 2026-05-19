# 多产品数据目录（Seed 内核 + 独立产品仓）

`seed`、`seed-tools` 可单独发 GitHub / PyPI；每个**产品**在启动时把自己的数据根写入 `SEED_PROJECT_ROOT`，内核与工具只认这一条树。

## 约定

| 产品 | 默认数据根 | 产品环境变量 | 启动入口 |
|------|------------|--------------|----------|
| **Seed**（仅用内核） | `~/.seed` | `SEED_PROJECT_ROOT` | 自行设置或默认 |
| **Code Agent** | `~/.codeagent` | `CODEAGENT_HOME` / `CODEAGENT_PROJECT_ROOT` | `codeagent.core.bootstrap.bootstrap_codeagent_runtime()` |
| **Design Agent**（规划） | `~/.designagent` | `DESIGNAGENT_HOME` | 同上模式，独立包内 bootstrap |

## Code Agent 启动顺序

```text
~/.codeagent/                    ← CODEAGENT_HOME（默认）
  config/
    seed.env                     ← SEED_*（内核）
    codeagent.env                ← CODEAGENT_*（产品）
  agents/ …

bootstrap:
  1. apply_default_product_home()  → 设置 CODEAGENT_HOME、SEED_PROJECT_ROOT
  2. apply_seed_env_from_config()
  3. bridge_codeagent_env_to_seed()  → CODEAGENT_LLM_* 等 → SEED_LLM_*
```

## 新产品的模板（如 designagent）

```python
# designagent/core/bootstrap.py
import os
from pathlib import Path

def bootstrap_designagent_runtime(base: Path | None = None) -> Path:
    home = (base or Path.home() / ".designagent").resolve()
    os.environ.setdefault("DESIGNAGENT_HOME", str(home))
    if "SEED_PROJECT_ROOT" not in os.environ:
        os.environ["SEED_PROJECT_ROOT"] = str(home)
    home.mkdir(parents=True, exist_ok=True)
    # load designagent.env + seed.env, then bridge DESIGNAGENT_* → SEED_*
    ...
    return home
```

依赖方向不变：`designagent` → `seed-tools` → `seed`（禁止 seed 依赖产品包）。
