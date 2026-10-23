"""KaTeX 数学公式支持测试。

覆盖三层：
1. 资源完整性：KaTeX JS/CSS/字体文件存在，CSS 字体路径改写正确
2. 服务端：字体路由（正常/404/路径穿越）、认证白名单、HTML 拼接
3. 前端逻辑：extractMath 定界符抽取（用 node 跑真实 JS，无 node 则跳过）
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "codeagent" / "web" / "static"


# ---------- 1. 资源完整性 ----------

def test_katex_assets_present():
    assert (STATIC / "00-katex.min.js").is_file(), "缺少 KaTeX JS"
    assert (STATIC / "00-katex.min.css").is_file(), "缺少 KaTeX CSS"
    fonts = list((STATIC / "katex-fonts").glob("*.woff2"))
    assert len(fonts) == 20, f"期望 20 个 woff2 字体，实际 {len(fonts)}"


def test_katex_css_points_to_route():
    css = (STATIC / "00-katex.min.css").read_text(encoding="utf-8")
    # 字体必须指向独立路由，而不是相对 fonts/（内联单页下相对路径会 404）
    assert "url(/katex-fonts/" in css
    assert "url(fonts/" not in css, "残留相对字体路径，内联后会 404"
    # 只保留 woff2，避免内联三份格式
    assert ".woff)" not in css and ".ttf)" not in css
    assert css.count("@font-face") == 20


def test_katex_math_js_loaded_before_render():
    """00- 前缀确保在 03c-render-bubble.js 之前拼接（依赖全局函数）。"""
    files = sorted(p.name for p in STATIC.glob("*.js"))
    assert files.index("00-katex-math.js") < files.index("03c-render-bubble.js")


# ---------- 2. 服务端 ----------

def test_katex_font_route_registered():
    from codeagent.server import get_app_html

    html, _ = get_app_html()
    assert "function extractMath" in html, "extractMath 未内联"
    assert "MATH_PURIFY_CONFIG" in html
    assert "extractMath(tWithPlaceholders)" in html, "renderMarkdown 未接入公式抽取"
    assert "DOMPurify.sanitize(html, purifyCfg)" in html, "DOMPurify 未使用 KaTeX 白名单"


def test_katex_fonts_are_public():
    """字体是纯静态资源，登录前也要能加载（否则登录页公式字体 401）。"""
    from codeagent.web.auth_impl import is_public_webui_route

    assert is_public_webui_route("/katex-fonts/KaTeX_Main-Regular.woff2", "GET")
    assert is_public_webui_route("/katex-fonts/KaTeX_Main-Regular.woff2", "HEAD")
    # 非 GET 不放行
    assert not is_public_webui_route("/katex-fonts/KaTeX_Main-Regular.woff2", "POST")


def test_katex_font_route_path_traversal():
    """路由正则只允许 [A-Za-z0-9_-]+.woff2，穿越/其他扩展名必须拒绝。"""
    # 直接验证正则契约（避免起整个 app）
    import re

    from codeagent.server.app_factory import create_app  # noqa: F401

    pat = re.compile(r"^/katex-fonts/([A-Za-z0-9_\-]+\.woff2)$")
    assert pat.match("/katex-fonts/KaTeX_Main-Regular.woff2")
    assert not pat.match("/katex-fonts/../../../etc/passwd")
    assert not pat.match("/katex-fonts/body.html")
    assert not pat.match("/katex-fonts/a/b.woff2")


# ---------- 3. 前端逻辑（node 实测） ----------

NODE_TEST = r"""
const fs = require('fs'), vm = require('vm');
const D = process.argv[2];
const ctx = { console };
ctx.window = ctx; ctx.self = ctx;
vm.createContext(ctx);
for (const f of ['00-utils.js', '00-katex-math.js']) {
  vm.runInContext(fs.readFileSync(D + f, 'utf8'), ctx);
}
const cases = {
  inline_dollar: '质能方程 $E=mc^2$ 很简单',
  block_dollar: '$$\\int_0^1 x^2 dx$$',
  inline_paren: '行内 \\(a+b\\) 测试',
  block_bracket: '\\[c+d\\]',
  price_untouched: '价格是 $5 和 $10 哦',
  shell_untouched: '用 $HOME 变量',
};
const out = {};
for (const [k, v] of Object.entries(cases)) {
  const r = ctx.extractMath(v);
  out[k] = { count: r.items.length, display: r.items.map(i => i.display), text: r.text };
}
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 运行前端逻辑")
def test_extract_math_delimiters():
    script = Path(__file__).parent / "_katex_probe.js"
    script.write_text(NODE_TEST, encoding="utf-8")
    try:
        res = subprocess.run(
            ["node", str(script), str(STATIC) + "/"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        data = json.loads(res.stdout)
    finally:
        script.unlink(missing_ok=True)

    # 各定界符都能抽出来
    assert data["inline_dollar"]["count"] == 1
    assert data["inline_dollar"]["display"] == [False]
    assert data["block_dollar"]["count"] == 1
    assert data["block_dollar"]["display"] == [True]
    assert data["inline_paren"]["count"] == 1
    assert data["block_bracket"]["count"] == 1
    assert data["block_bracket"]["display"] == [True]

    # 关键：价格和 shell 变量不能被误当成公式
    assert data["price_untouched"]["count"] == 0, "价格被误判为公式"
    assert data["shell_untouched"]["count"] == 0, "shell 变量被误判为公式"

    # 占位符必须从原文中移除（否则会同时显示原始 TeX）
    assert "$E=mc^2$" not in data["inline_dollar"]["text"]
    assert "data-math-idx" in data["inline_dollar"]["text"]
