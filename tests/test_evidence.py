"""交付证据链测试。"""

from codeagent.server import evidence as ev


def _trace(*items):
    return [{"tool": t, "arguments": a, "result": r} for t, a, r in items]


# ---------- 分类 ----------
def test_classify_test_pass():
    b = ev.collect_evidence(_trace(
        ("test_run", "pytest tests/", "657 passed, 1 warning in 2.49s"),
    ))
    assert b.tests_passed == 657
    assert b.tests_failed == 0
    assert not b.has_failure()


def test_classify_test_fail():
    b = ev.collect_evidence(_trace(
        ("test_run", "pytest", "2 failed, 655 passed"),
    ))
    assert b.tests_failed == 2
    assert b.tests_passed == 655
    assert b.has_failure()


def test_classify_git_commit():
    b = ev.collect_evidence(_trace(
        ("git", "commit -m 'x'", "[rsi/x abc1234] feat: something"),
    ))
    assert b.commits == ["abc1234"]


def test_classify_file_edit():
    b = ev.collect_evidence(_trace(
        ("file_edit", "filepath=/a/b/chat_turn.py", "ok"),
    ))
    assert any(f.endswith("chat_turn.py") for f in b.files_touched)


def test_classify_http_verify():
    b = ev.collect_evidence(_trace(
        ("bash", "curl -s -o /dev/null -w '%{http_code}' http://x", "HTTP 200"),
    ))
    assert len(b.items) == 1
    assert b.items[0].kind == "verify"
    assert b.items[0].ok is True


def test_plain_bash_ignored():
    """普通 bash 命令不记录（防噪音）。"""
    b = ev.collect_evidence(_trace(("bash", "ls -la", "total 8\n...")))
    assert b.is_empty()


def test_failure_recorded():
    b = ev.collect_evidence(_trace(
        ("bash", "pytest", "Traceback (most recent call last): AssertionError"),
    ))
    assert b.has_failure()
    assert b.failures


def test_file_dedup():
    """同一文件多次改动只留一条。"""
    b = ev.collect_evidence(_trace(
        ("file_edit", "filepath=/a/x.py", "ok"),
        ("file_edit", "filepath=/a/x.py", "ok"),
        ("file_write", "filepath=/a/x.py", "ok"),
    ))
    files = [i for i in b.items if i.kind == "file"]
    assert len(files) == 1


def test_empty_trace():
    assert ev.collect_evidence(None).is_empty()
    assert ev.collect_evidence([]).is_empty()


def test_malformed_trace():
    """非法结构不崩。"""
    b = ev.collect_evidence([None, "x", {"tool": "bash", "arguments": "ls", "result": ""}])
    assert isinstance(b, ev.EvidenceBundle)


# ---------- 格式化 ----------
def test_format_empty_returns_blank():
    assert ev.format_evidence_block(ev.EvidenceBundle()) == ""


def test_format_full_block():
    b = ev.collect_evidence(_trace(
        ("test_run", "pytest", "657 passed"),
        ("git", "commit", "[main deadbee] x"),
        ("file_edit", "filepath=/a/b.py", "ok"),
        ("bash", "curl http://x", "HTTP 200"),
    ))
    txt = ev.format_evidence_block(b)
    assert "本轮执行证据" in txt
    assert "657 通过" in txt
    assert "deadbee" in txt
    assert "b.py" in txt
    assert "HTTP 200" in txt


def test_format_shows_failures():
    b = ev.collect_evidence(_trace(
        ("test_run", "pytest", "3 failed, 100 passed"),
    ))
    txt = ev.format_evidence_block(b)
    assert "❌" in txt
    assert "未通过项" in txt


def test_build_appendix_convenience():
    txt = ev.build_evidence_appendix(_trace(("test_run", "pytest", "10 passed")))
    assert "10 通过" in txt
    assert ev.build_evidence_appendix(None) == ""


def test_to_dict_roundtrip():
    b = ev.collect_evidence(_trace(("test_run", "pytest", "5 passed")))
    d = b.to_dict()
    assert d["tests_passed"] == 5
    assert d["has_failure"] is False
    assert isinstance(d["items"], list)


# ---------- 集成：chat_turn 注入 ----------
def test_chat_turn_signature_has_with_evidence():
    """run_chat_turn 支持 with_evidence 参数（默认关闭，不改变既有行为）。"""
    import inspect

    from codeagent.server.chat_turn import run_chat_turn

    sig = inspect.signature(run_chat_turn)
    assert "with_evidence" in sig.parameters
    assert sig.parameters["with_evidence"].default is False


def test_evidence_default_off_keeps_reply_clean():
    """默认关闭时，证据块为空（不污染回复）。"""
    from codeagent.server.evidence import build_evidence_appendix

    # 模拟：无证据时返回空串
    assert build_evidence_appendix([]) == ""


# ---------- 回归：真实场景误判 ----------
def test_passed_not_misjudged_as_failed():
    """回归：测试名含 'error' 子串时，不能把'全通过'误判为失败。

    真实场景：test_add_with_string_raises_type_error PASSED
    """
    b = ev.collect_evidence(_trace(
        ("bash", "pytest test_demo_calc.py",
         "test_add_with_string_raises_type_error PASSED\n"
         "============================== 8 passed in 0.01s =============================="),
    ))
    assert b.tests_passed == 8
    assert b.tests_failed == 0
    assert not b.has_failure(), f"误报失败: {b.failures}"


def test_real_failure_still_detected():
    """真失败仍要检出。"""
    b = ev.collect_evidence(_trace(
        ("bash", "pytest", "FAILED test_x.py::test_a - assert 1 == 2\n1 failed, 7 passed"),
    ))
    assert b.tests_failed == 1
    assert b.has_failure()


def test_traceback_detected():
    b = ev.collect_evidence(_trace(
        ("bash", "python x.py", "Traceback (most recent call last):\n  File \"x.py\""),
    ))
    assert b.has_failure()


def test_filename_not_function_attr():
    """回归：'demo_calc.add' 不能被当成文件名。"""
    assert ev._extract_filename("filepath=/a/b/demo_calc.py") == "/a/b/demo_calc.py"
    assert ev._extract_filename('{"filepath": "/a/b/x.py", "content": "..."}') == "/a/b/x.py"
    # 模块.属性 形态不应被提取为文件
    assert ev._extract_filename("demo_calc.add") == ""
    assert ev._extract_filename("调用 demo_calc.add(a,b)") == ""


def test_filename_fallback_known_ext():
    assert ev._extract_filename("write to notes.md please") == "notes.md"


def test_evidence_block_no_false_failure():
    """端到端：全通过的任务，证据块不得出现'未通过项'。"""
    b = ev.collect_evidence(_trace(
        ("file_write", "filepath=/a/demo_calc.py", "ok"),
        ("bash", "pytest", "8 passed in 0.01s"),
    ))
    txt = ev.format_evidence_block(b)
    assert "8 通过" in txt
    assert "未通过项" not in txt
    assert "demo_calc.py" in txt


# ---------- 回归：真实场景（端到端实测发现） ----------
def test_code_check_not_counted_as_test():
    """回归：code_check 的 'All checks passed!' 不是'测试通过'。"""
    b = ev.collect_evidence(_trace(
        ("code_check", "filepath=/a/x.py", "All checks passed!"),
    ))
    assert b.tests_passed == 0, "lint 通过不该计入测试通过数"
    assert len(b.items) == 1
    assert b.items[0].kind == "verify"
    assert b.items[0].ok is True


def test_code_check_with_errors_is_failure():
    """回归：ruff 报错要判失败。"""
    b = ev.collect_evidence(_trace(
        ("code_check", "filepath=/a/x.py", "Found 1 error.\n[*] 1 fixable with the `--fix` option."),
    ))
    assert b.has_failure()
    assert b.items[0].kind == "verify"


def test_git_not_a_repo_not_failure():
    """回归：'fatal: not a git repository' 不是任务失败。"""
    b = ev.collect_evidence(_trace(
        ("bash", "git rev-parse --is-inside-work-tree",
         "fatal: not a git repository (or any of the parent directories): .git"),
    ))
    assert not b.has_failure()


def test_pytest_collection_error_detected():
    """回归：pytest 收集错误要检出（此前漏报）。"""
    b = ev.collect_evidence(_trace(
        ("bash", "pytest test_x.py", "ERROR: file or directory not found: test_x.py"),
    ))
    assert b.has_failure()


def test_pytest_warning_not_failure():
    """回归：'1 warning' 不是失败。"""
    b = ev.collect_evidence(_trace(
        ("bash", "pytest", "8 passed, 1 warning in 0.01s"),
    ))
    assert b.tests_passed == 8
    assert not b.has_failure()


def test_mixed_session_clean_evidence():
    """端到端场景：一次真实会话（含 lint + git 失败 + pytest 通过）。

    期望：只有 pytest 通过，无失败误报。
    """
    b = ev.collect_evidence(_trace(
        ("bash", "ls -la", "total 40\ndrwxrwxr-x ..."),
        ("file_write", "filepath=/a/strutil.py", "ok"),
        ("file_write", "filepath=/a/test_strutil.py", "ok"),
        ("code_check", "filepath=/a/strutil.py", "All checks passed!"),
        ("bash", "pytest test_strutil.py -v", "test_a PASSED\ntest_b PASSED\n8 passed in 0.01s"),
        ("bash", "git rev-parse", "fatal: not a git repository"),
    ))
    assert b.tests_passed == 8
    assert b.tests_failed == 0
    assert not b.has_failure(), f"误报失败: {b.failures}"
    assert len(b.files_touched) == 2
    txt = ev.format_evidence_block(b)
    assert "8 通过" in txt
    assert "未通过项" not in txt
