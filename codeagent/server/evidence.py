"""交付证据链 — 让 Agent 的"完成"变成可验证的事实。

为什么需要（数据依据）
----------------------
对 5293 条真实用户消息的分析显示：
- **验证/确认类消息 513 条（9%）**，是最大的一类
- 高频句式：`验证一下`、`你看看`、`对吗？`、`git 回溯了，修改的都还在吗？`
- 根因：Agent 报告"完成"时**不给证据**，用户被迫自己验证

本模块把 `run_chat_turn` 的工具执行轨迹（tool_trace）提炼成**结构化证据块**，
附在回复里——用户一眼看到"做了什么、结果如何、改动落在哪"。

设计原则
--------
- **零侵入**：纯函数，不改 chat_turn 逻辑；调用方决定是否使用
- **只提取关键证据**：不是全量工具输出（防 token 爆炸），而是测试结果/失败/关键命令
- **诚实**：失败必须显式呈现，不粉饰
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── 证据类型识别（按工具名 + 参数/结果特征）─────────────────────
_TEST_TOOLS = {"test_run", "pytest", "test_gen"}
_GIT_TOOLS = {"git", "bash"}
_VERIFY_TOOLS = {"bash", "test_run", "browser_screenshot", "curl"}

# 结果里的关键信号
# 注意：失败正则必须**精确**，否则会误判——
# 例：测试名 `test_add_with_string_raises_type_error PASSED` 里的 "error"
# 会被宽松的 `Error` 匹配到，导致"全通过"被误报为"有失败"。
_RE_PASS = re.compile(r"(\d+)\s+passed|PASSED|✅|tests? passed", re.I)
_RE_FAIL = re.compile(
    r"(\d+)\s+failed"          # N failed（pytest 统计行）
    r"|\bFAILED\b"             # pytest 的 FAILED 标记（词边界，不匹配 PASSED）
    r"|❌"
    r"|^Traceback \(most recent call last\)"   # 行首的 Traceback
    r"|\bAssertionError\b"
    r"|^E\s+\w*Error"          # pytest 错误行「E   ValueError: ...」
    r"|\bERROR: (?:file|directory|collection|import)\b"  # pytest 收集错误
    r"|\b\d+ errors?\b(?=\s*(?:in|during|,|$))",  # "N errors" 但要求后接统计语境
    re.I | re.M,
)

# 带数字计数的专用正则（优先使用，保证能取到数量）
_RE_PASS_N = re.compile(r"(\d+)\s+passed", re.I)
_RE_FAIL_N = re.compile(r"(\d+)\s+(?:failed|error)", re.I)

# 代码检查（lint）专用信号
_RE_CHECK_OK = re.compile(r"all checks passed|no issues found|0 error", re.I)
_RE_CHECK_ERR = re.compile(r"found\s+(\d+)\s+error|(\d+)\s+error\(s\)|✖", re.I)
_RE_COMMIT = re.compile(r"\b([0-9a-f]{7,40})\b")
_RE_HTTP = re.compile(r"HTTP[/ ]?\d?\.?\d?\s*(\d{3})|status[:\s]+(\d{3})", re.I)


@dataclass
class Evidence:
    """单条证据。"""

    kind: str          # test / git / verify / file / other
    tool: str          # 工具名
    summary: str       # 一句话摘要（人可读）
    detail: str = ""   # 关键细节（截断）
    ok: bool | None = None   # 成功/失败/未知

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "tool": self.tool, "summary": self.summary,
                "detail": self.detail, "ok": self.ok}


@dataclass
class EvidenceBundle:
    """一次执行的证据包。"""

    items: list[Evidence] = field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    commits: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.items

    def has_failure(self) -> bool:
        return bool(self.failures) or self.tests_failed > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "commits": self.commits,
            "files_touched": self.files_touched,
            "failures": self.failures,
            "has_failure": self.has_failure(),
        }


def _truncate(s: str, n: int = 300) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + " …"


def _extract_filename(args: str) -> str:
    """从工具参数里提取文件名。

    优先 ``filepath=xxx`` / ``"filepath": "xxx"``；
    兜底用路径正则，但**排除** ``模块.属性`` 形态（如 ``demo_calc.add``）。

    判定标准：扩展名必须是已知的**文件扩展名**（≥2 字符且非纯标识符后缀）。
    """
    args = args or ""
    # 1. 优先显式 filepath 字段
    m = re.search(r'["\']?filepath["\']?\s*[:=]\s*["\']?([^\s"\',}]+)', args)
    if m:
        return m.group(1)
    # 2. 兜底：找路径形态，但排除 模块.属性
    m = re.search(r"(/[\w./\-]+\.\w{1,8})", args)  # 必须含 /，排除 demo_calc.add
    if m:
        return m.group(1)
    m = re.search(r"([\w\-]+\.(?:py|md|json|yaml|yml|toml|txt|js|ts|vue|html|css|sh|sql))", args)
    if m:
        return m.group(1)
    return ""


def _classify(tool: str, args: str, result: str) -> Evidence | None:
    """把一条工具轨迹分类成证据。返回 None 表示不值得记录。

    分类优先级（关键：先判"专用工具"，再判"通用 bash"，避免误判）：
    1. 专用测试工具（test_run/test_gen）→ 测试证据
    2. git 工具 → 提交证据
    3. 文件工具 → 改动证据
    4. 通用工具（bash/curl）→ 看**结果特征**判断是测试/验证
    """
    tool = (tool or "").lower()
    args = args or ""
    result = result or ""

    # ── 1. 专用测试工具 ──
    if tool in ("test_run", "test_gen") or "pytest" in tool:
        return _as_test_evidence(tool, result)

    # ── 1b. 代码检查工具（lint）——归 verify，不归 test ──
    if tool in ("code_check", "code_analyze", "lsp_diagnostics"):
        return _as_check_evidence(tool, result)

    # ── 2. git 工具 ──
    if tool == "git":
        if "commit" in args or "push" in args:
            m = _RE_COMMIT.search(result)
            sha = m.group(1) if m else ""
            summary = f"提交：{sha[:8]}" if sha else "git 操作完成"
            return Evidence("git", tool, summary, _truncate(result, 200), True)
        return None

    # ── 3. 文件工具 ──
    if tool in ("file_edit", "file_write", "apply_patch"):
        fname = _extract_filename(args)
        summary = f"改动：{fname}" if fname else "文件已修改"
        return Evidence("file", tool, summary, "", True)

    # ── 4. 通用工具（bash/curl/截图）：看结果特征 ──
    if tool in _VERIFY_TOOLS or tool in ("bash", "bash_exec", "curl", "browser_screenshot"):
        # 4a. 结果像测试输出 → 测试证据
        if _RE_PASS.search(result) or _RE_FAIL.search(result):
            return _as_test_evidence(tool, result)
        # 4b. HTTP 状态 → 验证证据
        m_http = _RE_HTTP.search(result)
        if m_http:
            code = m_http.group(1) or m_http.group(2)
            return Evidence("verify", tool, f"HTTP {code}", _truncate(result, 200),
                            str(code).startswith("2"))
        # 4c. 其他 bash 输出不记（噪音太大）
        return None

    return None


def _as_check_evidence(tool: str, result: str) -> Evidence | None:
    """代码检查（lint）证据。

    注意：`All checks passed!` 是 lint 通过，**不是**"测试通过"——
    不能计入 tests_passed，否则证据块会误导。
    """
    r = result or ""
    if _RE_CHECK_OK.search(r):
        return Evidence("verify", tool, "代码检查通过", _truncate(r, 200), True)
    m = _RE_CHECK_ERR.search(r)
    if m:
        n = m.group(1) or "?"
        return Evidence("verify", tool, f"代码检查：{n} 个问题", _truncate(r, 300), False)
    return None


def _as_test_evidence(tool: str, result: str) -> Evidence:
    """从结果里提取测试通过/失败数。"""
    # 优先用带数字的计数（"8 passed" / "1 failed"），避免被无分组的
    # PASSED/FAILED 标记抢先匹配导致数字丢失。
    m_pass = _RE_PASS_N.search(result) or _RE_PASS.search(result)
    m_fail = _RE_FAIL_N.search(result) or _RE_FAIL.search(result)
    n_pass = int(m_pass.group(1)) if (m_pass and m_pass.group(1)) else 0
    n_fail = int(m_fail.group(1)) if (m_fail and m_fail.group(1)) else 0
    ok: bool | None
    if n_pass or n_fail:
        ok = n_fail == 0
        summary = f"测试：{n_pass} 通过" + (f"，{n_fail} 失败" if n_fail else "")
    elif m_fail:
        # 有失败信号但无数字（如 Traceback / AssertionError）→ 判失败
        ok = False
        summary = "测试：结果含报错"
    else:
        ok = None
        summary = "测试：已执行"
    return Evidence("test", tool, summary, _truncate(result, 400), ok)


def collect_evidence(tool_trace: list[dict[str, Any]] | None) -> EvidenceBundle:
    """从 tool_trace 提炼证据包。

    Args:
        tool_trace: ``[{"tool": name, "arguments": str, "result": str}, ...]``

    Returns:
        EvidenceBundle（可能为空）
    """
    bundle = EvidenceBundle()
    for t in tool_trace or []:
        if not isinstance(t, dict):
            continue
        name = str(t.get("tool") or t.get("name") or "")
        args = str(t.get("arguments") or "")
        result = str(t.get("result") or "")
        ev = _classify(name, args, result)
        if ev is None:
            continue

        # 去重（同一文件多次改动只留一条）
        if ev.kind == "file" and any(
            i.kind == "file" and i.summary == ev.summary for i in bundle.items
        ):
            continue

        bundle.items.append(ev)

        # 汇总
        if ev.kind == "test":
            m_pass = _RE_PASS_N.search(result)
            m_fail = _RE_FAIL_N.search(result)
            if m_pass and m_pass.group(1):
                bundle.tests_passed += int(m_pass.group(1))
            if m_fail and m_fail.group(1):
                bundle.tests_failed += int(m_fail.group(1))
        elif ev.kind == "git":
            m = _RE_COMMIT.search(result)
            if m:
                bundle.commits.append(m.group(1)[:8])
        elif ev.kind == "file":
            fname = ev.summary.replace("改动：", "")
            if fname and fname not in bundle.files_touched:
                bundle.files_touched.append(fname)

        if ev.ok is False:
            bundle.failures.append(f"{ev.tool}: {ev.summary}")

    return bundle


def format_evidence_block(bundle: EvidenceBundle) -> str:
    """把证据包格式化成 Markdown 块（附在回复末尾）。

    空包返回空串（不污染回复）。
    """
    if bundle.is_empty():
        return ""

    lines: list[str] = ["", "---", "**📋 本轮执行证据**", ""]

    # 测试结果
    if bundle.tests_passed or bundle.tests_failed:
        if bundle.tests_failed:
            lines.append(f"- ❌ 测试：**{bundle.tests_passed} 通过 / {bundle.tests_failed} 失败**")
        else:
            lines.append(f"- ✅ 测试：**{bundle.tests_passed} 通过**")

    # 提交
    if bundle.commits:
        lines.append(f"- 📦 提交：`{'`, `'.join(bundle.commits)}`")

    # 文件改动
    if bundle.files_touched:
        shown = bundle.files_touched[:8]
        more = f" 等 {len(bundle.files_touched)} 个文件" if len(bundle.files_touched) > 8 else ""
        lines.append(f"- 📝 改动：`{'`, `'.join(shown)}`{more}")

    # 验证
    verifies = [i for i in bundle.items if i.kind == "verify"]
    if verifies:
        marks = " ".join(
            f"{'✅' if v.ok else '❌' if v.ok is False else '•'} {v.summary}"
            for v in verifies[:5]
        )
        lines.append(f"- 🔍 验证：{marks}")

    # 失败显式列出（诚实原则）
    if bundle.failures:
        lines.append("")
        lines.append("**⚠️ 未通过项**（需处理）：")
        for f in bundle.failures[:5]:
            lines.append(f"- {f}")

    return "\n".join(lines)


def build_evidence_appendix(tool_trace: list[dict[str, Any]] | None) -> str:
    """便捷入口：tool_trace → Markdown 证据块。"""
    return format_evidence_block(collect_evidence(tool_trace))
