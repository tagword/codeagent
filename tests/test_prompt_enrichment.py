"""codeagent.runtime.prompt_enrichment 纯逻辑单元测试。

覆盖 _codeagent_path_registry（纯 markdown 路径表生成）。
（_compute_persona_hash 依赖函数内 import + 真实文件系统，测试价值低且难隔离，不测）
"""
from codeagent.runtime import prompt_enrichment as pe


# ---------- _codeagent_path_registry ----------
def test_path_registry_basic():
    out = pe._codeagent_path_registry({"PLANS": "/proj/.codeagent/a/plans", "DOCS": "/proj/.codeagent/a/docs"})
    assert "## 路径基准（CodeAgent 扩展）" in out
    assert "| 变量 | 当前值 |" in out
    assert "| `$PLANS` | `/proj/.codeagent/a/plans` |" in out
    assert "| `$DOCS` | `/proj/.codeagent/a/docs` |" in out


def test_path_registry_sorted_keys():
    out = pe._codeagent_path_registry({"b": "2", "a": "1", "c": "3"})
    # 按 key 排序 a,b,c
    ia = out.index("`$a`")
    ib = out.index("`$b`")
    ic = out.index("`$c`")
    assert ia < ib < ic


def test_path_registry_empty():
    out = pe._codeagent_path_registry({})
    assert "| 变量 | 当前值 |" in out
    # 只有表头，无数据行
    assert "$" not in out.split("|------|")[1]


def test_path_registry_escapes_contains_dollar():
    out = pe._codeagent_path_registry({"X": "value"})
    assert "`$X`" in out


def test_path_registry_value_with_underscore():
    out = pe._codeagent_path_registry({"SESSIONS_ARTIFACTS": "/sys/agent/sessions/_artifacts"})
    assert "`$SESSIONS_ARTIFACTS`" in out
    assert "/sys/agent/sessions/_artifacts" in out
