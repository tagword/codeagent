function renderMarkdown(raw) {
  const t = String(raw || '');
  const plain = '<div class="md-content md-content--plain">' + escapeHtml(t) + '</div>';
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') return plain;
  try {
    marked.setOptions({ breaks: true, gfm: true });
    const html = marked.parse(t);
    const clean = DOMPurify.sanitize(html);
    return '<div class="md-content">' + clean + '</div>';
  } catch (_) { return plain; }
}

function stripOaToolOrphans(s) {
  let t = String(s || '');
  t = t.replace(/<\/\s*parameter\s*>/gi, '');
  t = t.replace(/<\/\s*function\s*>/gi, '');
  t = t.replace(/<\/\s*tool_call\s*>/gi, '');
  t = t.replace(/<\s*tool_call\s*>/gi, '');
  t = t.replace(/<\s*function\s*=\s*\w+\s*>/gi, '');
  t = t.replace(/<\s*parameter\s*=\s*\w+\s*>/gi, '');
  return t.replace(/\n{3,}/g, '\n\n').trim();
}

function extractOaToolCallBlocks(s) {
  const blocks = [];
  const re = /<tool_call>\s*[\s\S]*?<\/tool_call>/gi;
  const text = String(s || '').replace(re, (m) => {
    blocks.push(m);
    return '\n\n';
  });
  return { text: text.replace(/\n{3,}/g, '\n\n').trim(), blocks: blocks };
}

function oaToolDetailsHtml(rawXml, summaryLabel) {
  const lab = escapeHtml(summaryLabel || '内联工具调用 (XML)');
  return '<details class="oa-tool-trace"><summary>' + lab + '</summary><pre class="oa-tool-trace-pre">' + escapeHtml(rawXml) + '</pre></details>';
}

function oaToolTraceRowHtml(row, index) {
  const name = (row && (row.tool || row.name)) || 'tool';
  const args = row && row.arguments != null ? String(row.arguments) : '';
  const res = row && row.result != null ? String(row.result) : '';
  const body = '参数：\n' + args + '\n\n输出：\n' + res;
  const summary = '工具：' + name + (index > 0 ? ' (' + (index + 1) + ')' : '');
  return '<details class="oa-tool-trace"><summary>' + escapeHtml(summary) + '</summary><pre class="oa-tool-trace-pre">' + escapeHtml(body) + '</pre></details>';
}
