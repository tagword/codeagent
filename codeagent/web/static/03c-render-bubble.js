function attachmentApiUrl(attachmentId) {
  const id = String(attachmentId || '').trim();
  if (!id) return '';
  const sid = typeof sessionId !== 'undefined' ? sessionId : 'web-chat';
  const aid = typeof agentId !== 'undefined' ? agentId : 'default';
  return '/api/attachments/' + encodeURIComponent(id)
    + '?session_id=' + encodeURIComponent(sid)
    + '&agent_id=' + encodeURIComponent(aid);
}

/** 将 Markdown / 正文中的 attachment: 引用改为可加载的附件 URL */
function rewriteAttachmentRefsInMarkdown(raw) {
  let t = String(raw || '');
  const toUrl = function(id) { return attachmentApiUrl(id); };

  // ![alt](attachment:id) 或 ![alt](attachment:id filename)
  t = t.replace(
    /!\[([^\]]*)\]\(attachment:([^)\s]+)(?:\s+[^)]*)?\)/gi,
    function(_, alt, id) { return '![' + alt + '](' + toUrl(id) + ')'; }
  );
  // [text](attachment:id)
  t = t.replace(
    /\[([^\]]+)\]\(attachment:([^)\s]+)(?:\s+[^)]*)?\)/gi,
    function(_, text, id) { return '[' + text + '](' + toUrl(id) + ')'; }
  );
  // 裸 [attachment:id filename] → 内联图片（与 vision 提示格式一致）
  t = t.replace(
    /\[attachment:([^\s\]]+)(?:\s+([^\]]+))?\]/gi,
    function(_, id, fn) {
      const alt = (fn || id || 'image').trim();
      return '\n\n![' + alt + '](' + toUrl(id) + ')\n\n';
    }
  );
  // 模型误写的绝对 URL（如 https://i0.hitpt.com/api/attachments/...）→ 同源附件路径
  t = t.replace(
    /https?:\/\/[^/]+\/api\/attachments\/([^?\s)"']+)(\?[^)\s"']*)?/gi,
    function(_, id, _q) { return toUrl(id); }
  );
  // 本地文件系统绝对路径（如 /home/u2/xxx/tmp/file.png）→ 通过 /api/file-serve 代理加载
  // 匹配 ![alt](/absolute/path/file.ext) 形式的图片引用
  t = t.replace(
    /!\[([^\]]*)\]\(\/([^)]+\.\w+)\)/gi,
    function(_, alt, rawPath) {
      var path = rawPath.split('?')[0];
      if (!path.startsWith('home/u2/')) return _;
      return '![' + alt + '](/api/file-serve?path=' + encodeURIComponent('/' + path) + ')';
    }
  );
  return t;
}

function markChatInlineImage(img) {
  if (!img || !img.classList) return;
  if (!img.classList.contains('chat-inline-img')) img.classList.add('chat-inline-img');
}

function chatImageDownloadName(img) {
  const alt = String((img && img.alt) || '').trim();
  if (alt && alt !== 'generated' && alt !== 'image') {
    return alt.replace(/[^\w.\-\u4e00-\u9fff]+/g, '_').slice(0, 120) || 'image.png';
  }
  const src = String((img && img.src) || '');
  const m = src.match(/\/api\/attachments\/([^/?#]+)/);
  const base = m ? m[1] : 'image';
  return /\.[a-z0-9]{2,5}$/i.test(base) ? base : base + '.png';
}

var _chatImageLightbox = null;

function ensureChatImageLightbox() {
  if (_chatImageLightbox) return _chatImageLightbox;
  const root = document.createElement('div');
  root.id = 'chatImageLightbox';
  root.className = 'chat-img-lightbox';
  root.setAttribute('aria-hidden', 'true');
  root.innerHTML =
    '<div class="chat-img-lightbox__backdrop" data-close="1"></div>' +
    '<div class="chat-img-lightbox__panel" role="dialog" aria-modal="true" aria-label="图片预览">' +
    '  <div class="chat-img-lightbox__stage">' +
    '    <img class="chat-img-lightbox__img" alt=""/>' +
    '    <div class="chat-img-lightbox__actions">' +
    '      <button type="button" class="chat-img-btn chat-img-lightbox__close" title="关闭" aria-label="关闭">&times;</button>' +
    '      <a class="chat-img-btn chat-img-lightbox__dl" href="#" download title="下载" aria-label="下载">↓</a>' +
    '    </div>' +
    '  </div>' +
    '</div>';
  document.body.appendChild(root);
  function closeLb() {
    root.classList.remove('is-open');
    root.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('chat-img-lightbox-open');
  }
  root.querySelector('.chat-img-lightbox__backdrop').addEventListener('click', closeLb);
  root.querySelector('.chat-img-lightbox__close').addEventListener('click', closeLb);
  document.addEventListener('keydown', function(ev) {
    if (ev.key === 'Escape' && root.classList.contains('is-open')) closeLb();
  });
  _chatImageLightbox = { root: root, close: closeLb };
  return _chatImageLightbox;
}

function openChatImageLightbox(src, downloadName) {
  const url = String(src || '').trim();
  if (!url) return;
  const lb = ensureChatImageLightbox();
  const img = lb.root.querySelector('.chat-img-lightbox__img');
  const dl = lb.root.querySelector('.chat-img-lightbox__dl');
  img.src = url;
  img.alt = downloadName || 'image';
  if (dl) {
    dl.href = url;
    dl.download = downloadName || 'image.png';
  }
  lb.root.classList.add('is-open');
  lb.root.setAttribute('aria-hidden', 'false');
  document.body.classList.add('chat-img-lightbox-open');
}

function wrapChatImage(img) {
  if (!img || !img.parentNode || img.closest('.chat-img-wrap')) return;
  markChatInlineImage(img);
  const wrap = document.createElement('div');
  wrap.className = 'chat-img-wrap';
  const parent = img.parentNode;
  parent.insertBefore(wrap, img);
  wrap.appendChild(img);

  const actions = document.createElement('div');
  actions.className = 'chat-img-wrap__actions';

  const zoomBtn = document.createElement('button');
  zoomBtn.type = 'button';
  zoomBtn.className = 'chat-img-btn chat-img-btn--zoom';
  zoomBtn.title = '放大';
  zoomBtn.setAttribute('aria-label', '放大');
  zoomBtn.textContent = '⤢';

  const dlName = chatImageDownloadName(img);
  const dlBtn = document.createElement('a');
  dlBtn.className = 'chat-img-btn chat-img-btn--dl';
  dlBtn.href = img.src || '#';
  dlBtn.download = dlName;
  dlBtn.title = '下载';
  dlBtn.setAttribute('aria-label', '下载');
  dlBtn.textContent = '↓';

  function openPreview(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    const src = img.currentSrc || img.src;
    if (!src) return;
    openChatImageLightbox(src, dlName);
  }

  zoomBtn.addEventListener('click', openPreview);
  img.addEventListener('click', openPreview);
  img.setAttribute('role', 'button');
  img.tabIndex = 0;
  img.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter' || ev.key === ' ') openPreview(ev);
  });

  actions.appendChild(zoomBtn);
  actions.appendChild(dlBtn);
  wrap.appendChild(actions);
}

/** 为会话内图片增加放大 / 下载控件 */
function enhanceChatImagesInBubble(root) {
  if (!root || !root.querySelectorAll) return;
  const sel = 'img.chat-inline-img, .bubble .md-content img, .oa-tool-gen-images img, .bubble-user__img';
  root.querySelectorAll(sel).forEach(function(img) {
    if (!img.src || img.closest('.chat-img-wrap')) return;
    wrapChatImage(img);
  });
}

/** 修复已渲染 DOM 中残留的 attachment: / 缺 query 的附件链接 */
function hydrateAttachmentImagesInBubble(root) {
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll('img[src]').forEach(function(img) {
    const src = String(img.getAttribute('src') || '');
    const m = src.match(/^attachment:([^?\s#]+)/i);
    if (m) {
      markChatInlineImage(img);
      img.src = attachmentApiUrl(m[1]);
      return;
    }
    if (src.indexOf('/api/attachments/') >= 0) {
      markChatInlineImage(img);
      if (src.indexOf('session_id=') < 0) {
        const path = src.split('?')[0];
        img.src = attachmentApiUrl(path.replace(/^\/api\/attachments\//, ''));
      }
      return;
    }
    const ext = src.match(/https?:\/\/[^/]+\/api\/attachments\/([^?\s#]+)/i);
    if (ext) {
      markChatInlineImage(img);
      img.src = attachmentApiUrl(ext[1]);
    }
  });
  root.querySelectorAll('a[href^="attachment:"]').forEach(function(a) {
    const m = String(a.getAttribute('href') || '').match(/^attachment:([^?\s#]+)/i);
    if (m) a.setAttribute('href', attachmentApiUrl(m[1]));
  });
  enhanceChatImagesInBubble(root);
}

function renderMarkdown(raw) {
  const t = rewriteAttachmentRefsInMarkdown(String(raw || ''));
  const plain = '<div class="md-content md-content--plain">' + escapeHtml(t) + '</div>';
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') return plain;
  try {
    marked.setOptions({ breaks: true, gfm: true });
    const html = marked.parse(t);
    const clean = DOMPurify.sanitize(html);
    // 给代码块添加复制按钮（浮动右上角）
    var enhanced = clean;
    enhanced = enhanced.replace(
      /<pre><code(?:\s+class="language-(\w+)")?>/g,
      function(match, lang) {
        return '<div class="code-block-wrap"><button class="code-copy-btn" type="button" title="复制代码" aria-label="复制代码"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg></button><pre><code' + (lang ? ' class="language-' + lang + '"' : '') + '>';
      }
    );
    enhanced = enhanced.replace(/<\/code><\/pre>/g, '</code></pre></div>');
    return '<div class="md-content">' + enhanced + '</div>';
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
