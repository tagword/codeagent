/**
 * KaTeX 数学公式支持 —— 与 marked / DOMPurify 协作的三段式流程。
 *
 * 为什么需要占位符：
 *   marked 会把 `\(...\)` 的反斜杠当转义符吃掉，`$...$` 里的下划线/星号
 *   也会被当作强调语法。因此必须在 marked 之前把公式抽成占位符，
 *   marked 渲染完、DOMPurify 之后再替换成 KaTeX 生成的 HTML。
 *
 * 支持的定界符：
 *   $$...$$   块级（独占一行）
 *   \[...\]   块级
 *   \(...\)   行内
 *   $...$     行内（严格模式，见 INLINE_DOLLAR_RE）
 *
 * 安全：KaTeX 输出经 DOMPurify 白名单放行（见 MATH_PURIFY_CONFIG），
 *       公式源码一律走 KaTeX 渲染，不拼裸 HTML。
 */

// 行内 $...$ 的严格判定：避免误伤价格（$5）、shell 变量（$HOME）、
// 以及 "a $ b $ c" 这类普通文本。
//   开头 $ 后不能是空白/数字；结尾 $ 前不能是空白；结尾 $ 后不能紧跟数字。
const INLINE_DOLLAR_RE = /\$(?![\s\d])((?:[^$\\\n]|\\.)+?)(?<![\s\\])\$(?!\d)/g;

// 块级 $$...$$（允许跨行，非贪婪）
const BLOCK_DOLLAR_RE = /\$\$([\s\S]+?)\$\$/g;

// LaTeX 风格定界符
const BLOCK_BRACKET_RE = /\\\[([\s\S]+?)\\\]/g;
const INLINE_PAREN_RE = /\\\(([\s\S]+?)\\\)/g;

/**
 * 把文本中的公式抽成占位符，返回 { text, items }。
 * items[i] = { tex, display }
 *
 * 占位符用 `<span data-math-idx="N"></span>` 形式 —— 与 mermaid 的
 * `<p data-mermaid-idx="N">` 保持一致的思路，且 span 不会被 marked
 * 当作块级元素重新分段。
 */
function extractMath(text) {
  const items = [];
  let out = String(text || '');

  function stash(tex, display) {
    const idx = items.length;
    items.push({ tex: String(tex).trim(), display: display });
    // 块级用 <div>：若用 <span>，marked 会把它包进 <p>，导致块级公式
    // 无法独占一行（display:block 塞在 <p> 里布局会塌）。
    return display
      ? '<div data-math-idx="' + idx + '"></div>'
      : '<span data-math-idx="' + idx + '"></span>';
  }

  // 顺序很重要：先块级（$$ / \[），再行内（$ / \(），
  // 否则 $$ 会被行内规则先吃掉一半。
  out = out.replace(BLOCK_DOLLAR_RE, function (_, tex) {
    return stash(tex, true);
  });
  out = out.replace(BLOCK_BRACKET_RE, function (_, tex) {
    return stash(tex, true);
  });
  out = out.replace(INLINE_PAREN_RE, function (_, tex) {
    return stash(tex, false);
  });
  out = out.replace(INLINE_DOLLAR_RE, function (_, tex) {
    return stash(tex, false);
  });

  return { text: out, items: items };
}

/**
 * 把占位符替换成 KaTeX 渲染结果。
 * 失败时降级为原始 TeX 文本（带 error 标记），不抛异常。
 */
function substituteMath(html, items) {
  if (!items || !items.length) return html;
  const hasKatex = typeof katex !== 'undefined' && katex && typeof katex.renderToString === 'function';

  return html.replace(/<(?:span|div) data-math-idx="(\d+)"><\/(?:span|div)>/g, function (_, n) {
    const item = items[Number(n)];
    if (!item) return '';
    if (!hasKatex) {
      return '<code class="math-fallback">' + escapeHtml(item.tex) + '</code>';
    }
    try {
      let rendered = katex.renderToString(item.tex, {
        displayMode: item.display,
        throwOnError: false,
        strict: 'ignore',
        trust: false,
        output: 'html',
      });
      // 安全：这段 HTML 在 DOMPurify 之后注入，必须单独净化一次，
      // 否则 KaTeX 输出（含用户可控的 TeX 源码）可绕过外层净化。
      if (typeof DOMPurify !== 'undefined' && DOMPurify.sanitize) {
        rendered = DOMPurify.sanitize(rendered, MATH_PURIFY_CONFIG);
      }
      return item.display
        ? '<div class="math-block">' + rendered + '</div>'
        : rendered;
    } catch (e) {
      return '<code class="math-fallback" title="公式渲染失败">' + escapeHtml(item.tex) + '</code>';
    }
  });
}

/**
 * DOMPurify 配置：放行 KaTeX 输出的标签与属性。
 * 不放行的话 <math>/<semantics>/<annotation> 会被剥离，公式变空白。
 */
const MATH_PURIFY_CONFIG = {
  ADD_TAGS: ['math', 'semantics', 'annotation', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub',
             'mfrac', 'msqrt', 'mroot', 'mtext', 'mspace', 'mtable', 'mtr', 'mtd', 'munder',
             'mover', 'munderover', 'mstyle', 'mpadded', 'mphantom', 'menclose', 'mglyph'],
  ADD_ATTR: ['encoding', 'mathvariant', 'displaystyle', 'scriptlevel', 'stretchy',
             'fence', 'separator', 'largeop', 'movablelimits', 'symmetric', 'width',
             'height', 'depth', 'voffset', 'lspace', 'rspace', 'columnalign', 'rowalign'],
};
