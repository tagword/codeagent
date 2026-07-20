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
  renderMermaidInBubble(root); // 异步渲染气泡中的 mermaid 图（fire-and-forget）
}

function renderMarkdown(raw) {
  const t = rewriteAttachmentRefsInMarkdown(String(raw || ''));

  // 先把 ```mermaid 块抽出来，替换成 <pre class="mermaid"> 占位符，
  // 避免 marked/DOMPurify/code-block-wrap 增强链路误处理它
  const mermaidBlocks = [];
  const tWithPlaceholders = t.replace(/```mermaid\s*([\s\S]*?)```/g, function(_, code) {
    const idx = mermaidBlocks.length;
    mermaidBlocks.push(String(code || '').trim());
    return '<p data-mermaid-idx="' + idx + '"></p>';
  });

  const plain = '<div class="md-content md-content--plain">' + escapeHtml(t) + '</div>';
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') return plain;
  try {
    marked.setOptions({ breaks: true, gfm: true });
    const html = marked.parse(tWithPlaceholders);
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
    // 把占位 <p data-mermaid-idx="N"></p> 替换成真正的 <pre class="mermaid"> 节点
    // （放在 code-block-wrap 增强之后，避开其正则）
    enhanced = enhanced.replace(/<p data-mermaid-idx="(\d+)"><\/p>/g, function(_, idx) {
      const i = Number(idx);
      const code = mermaidBlocks[i] != null ? mermaidBlocks[i] : '';
      return '<pre class="mermaid" data-mermaid-idx="' + i + '">' + escapeHtml(code) + '</pre>';
    });
    return '<div class="md-content">' + enhanced + '</div>';
  } catch (_) { return plain; }
}

/**
 * 把 mermaid 输出的 SVG 字符串转成 PNG data URL。
 * - 用 canvas 绘制，便于在手机端/聊天软件/邮件里正常显示。
 * - scale=2 输出 2 倍像素，高 DPI 屏更清晰。
 * - 失败时返回 null（调用方应 fallback 到 SVG）。
 */
async function svgToPngDataUrl(svgStr, scale) {
  try {
    const pixelRatio = (scale && scale > 0) ? scale : 2;
    // 解析 viewBox 取宽高（mermaid 输出通常不带 width/height 属性）
    const tmp = document.createElement('div');
    tmp.innerHTML = svgStr;
    const svgEl = tmp.querySelector('svg');
    if (!svgEl) return null;
    // 确保有 viewBox；无则用 getBBox 取（此时 svg 必须已挂载到 DOM，但我们后面会处理）
    let vb = svgEl.getAttribute('viewBox');
    let w = parseFloat(svgEl.getAttribute('width'));
    let h = parseFloat(svgEl.getAttribute('height'));
    if (!vb && svgEl.getBBox) {
      try {
        // getBBox 需要在 DOM 中，先挂到隐藏容器
        tmp.style.position = 'absolute';
        tmp.style.visibility = 'hidden';
        document.body.appendChild(tmp);
        const bb = svgEl.getBBox();
        document.body.removeChild(tmp);
        if (bb && bb.width > 0 && bb.height > 0) {
          w = bb.width;
          h = bb.height;
          vb = '0 0 ' + w + ' ' + h;
          svgEl.setAttribute('viewBox', vb);
        } else {
          document.body.removeChild(tmp);
          return null;
        }
      } catch (_) {
        if (tmp.parentNode) tmp.parentNode.removeChild(tmp);
        return null;
      }
    }
    if (!vb) {
      // 都没有就放弃 PNG 转换
      return null;
    }
    // 从 viewBox 解析尺寸
    const vbParts = vb.split(/[\s,]+/).map(Number);
    let vbW = vbParts[2], vbH = vbParts[3];
    if (!vbW || !vbH) {
      // 退回到 width/height 属性
      if (!w || !h) return null;
      vbW = w; vbH = h;
    }
    // 给 svg 加上显式 width/height（必须有，canvas 才能绘制）
    svgEl.setAttribute('width', String(vbW));
    svgEl.setAttribute('height', String(vbH));
    // 套一层白色背景，避免 PNG 透明
    const bgId = 'mermaid-bg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
    const bgRect = '<rect x="0" y="0" width="100%" height="100%" fill="white"/>';
    if (svgEl.querySelector('defs')) {
      // 把背景 rect 注入到第一个非 defs 子元素之前
      const firstNonDefs = Array.from(svgEl.children).find(function(c) {
        return c.tagName && c.tagName.toLowerCase() !== 'defs' && c.tagName.toLowerCase() !== 'style';
      });
      if (firstNonDefs) {
        firstNonDefs.insertAdjacentHTML('beforebegin', bgRect);
      } else {
        svgEl.insertAdjacentHTML('beforeend', bgRect);
      }
    } else {
      svgEl.insertAdjacentHTML('afterbegin', '<defs></defs>' + bgRect);
    }
    // 序列化
    const finalSvg = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([finalSvg], { type: 'image/svg+xml;charset=utf-8' });
    const blobUrl = URL.createObjectURL(blob);

    // 用 Image 加载 SVG（必须是 Blob URL 或 data URL，不能用 inline svg 串）
    const img = new Image();
    img.crossOrigin = 'anonymous';
    const loaded = new Promise(function(resolve, reject) {
      img.onload = function() { resolve(); };
      img.onerror = function(ev) { reject(new Error('SVG image load failed')); };
    });
    img.src = blobUrl;
    await loaded;

    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(vbW * pixelRatio);
    canvas.height = Math.ceil(vbH * pixelRatio);
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      URL.revokeObjectURL(blobUrl);
      return null;
    }
    // 先铺白底（部分浏览器 SVG 透明区域会留空）
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(blobUrl);
    return canvas.toDataURL('image/png');
  } catch (_) {
    return null;
  }
}

/** 触发浏览器下载（兼容 data URL 或 Blob URL），用完自动 revoke */
function triggerDownload(href, fileName) {
  try {
    const a = document.createElement('a');
    a.href = href;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // data URL 不需要 revoke；Blob URL 需 revoke（调用方负责）
  } catch (_) {}
}

/**
 * 扫描 root 内所有 <pre class="mermaid">，调用 mermaid.render() 转成 SVG。
 * 必须等 DOM 渲染完成后调用（通常在 enhanceChatImagesInBubble 之后）。
 * 失败时把节点替换为红框错误提示，不抛出。
 */
async function renderMermaidInBubble(root) {
  if (typeof window === 'undefined' || typeof window.mermaid === 'undefined') return;
  if (!root || !root.querySelectorAll) return;
  const nodes = root.querySelectorAll('pre.mermaid:not([data-mermaid-rendered])');
  if (!nodes.length) return;

  try {
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'default',
      fontFamily: 'inherit',
    });
  } catch (_) { /* already initialized */ }

  for (const node of Array.from(nodes)) {
    const code = node.textContent || '';
    if (!code.trim()) continue;
    node.setAttribute('data-mermaid-rendered', '1');
    const id = 'mermaid-bubble-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    try {
      const result = await window.mermaid.render(id, code);
      const svg = (result && result.svg) ? result.svg : '';
      const wrap = document.createElement('div');
      wrap.className = 'mermaid-host';
      wrap.innerHTML = svg;
      // 提取渲染产物的 svg 字符串（来自 wrap 内的 <svg>），便于下载/放大预览
      const svgEl = wrap.querySelector('svg');
      const svgStr = svgEl ? svgEl.outerHTML : svg;
      // 文件名：使用 mermaid 第一个单词作为前缀，附时间戳
      const firstWord = (code.match(/^\s*([A-Za-z][\w-]*)/) || [, 'diagram'])[1].toLowerCase();
      const baseName = 'mermaid-' + firstWord + '-' + Date.now();
      const svgFileName = baseName + '.svg';
      const pngFileName = baseName + '.png';

      // hover 时显示的右上角操作按钮（复用 .chat-img-btn-* 视觉风格）
      const actions = document.createElement('div');
      actions.className = 'mermaid-host__actions';

      // 防止并发：用户连续点击时复用同一个转换 Promise
      let pngPromise = null;
      const getPng = function() {
        if (!pngPromise) pngPromise = svgToPngDataUrl(svgStr, 2);
        return pngPromise;
      };

      const zoomBtn = document.createElement('button');
      zoomBtn.type = 'button';
      zoomBtn.className = 'chat-img-btn chat-img-btn--zoom';
      zoomBtn.title = '放大预览';
      zoomBtn.setAttribute('aria-label', '放大预览');
      zoomBtn.textContent = '⤢';
      zoomBtn.addEventListener('click', async function(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        try {
          const pngDataUrl = await getPng();
          if (pngDataUrl) {
            openChatImageLightbox(pngDataUrl, pngFileName);
          } else {
            // fallback：转换失败时用 SVG data URL
            const svgDataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgStr);
            openChatImageLightbox(svgDataUrl, svgFileName);
          }
        } catch (_) {}
      });

      const dlBtn = document.createElement('a');
      dlBtn.className = 'chat-img-btn chat-img-btn--dl';
      dlBtn.href = '#';
      dlBtn.download = pngFileName;
      dlBtn.title = '下载 PNG';
      dlBtn.setAttribute('aria-label', '下载 PNG');
      dlBtn.textContent = '↓';
      dlBtn.addEventListener('click', async function(ev) {
        ev.preventDefault();
        try {
          const pngDataUrl = await getPng();
          if (pngDataUrl) {
            triggerDownload(pngDataUrl, pngFileName);
          } else {
            // fallback：PNG 转换失败 → 下载原始 SVG
            const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            triggerDownload(url, svgFileName);
            setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
          }
        } catch (_) {}
      });

      // svg 元素自身点击也触发放大
      if (svgEl) {
        svgEl.style.cursor = 'zoom-in';
        svgEl.setAttribute('role', 'button');
        svgEl.tabIndex = 0;
        svgEl.addEventListener('click', function() { zoomBtn.click(); });
        svgEl.addEventListener('keydown', function(ev) {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); zoomBtn.click(); }
        });
      }

      actions.appendChild(zoomBtn);
      actions.appendChild(dlBtn);
      wrap.appendChild(actions);

      node.parentNode.replaceChild(wrap, node);
    } catch (err) {
      const msg = (err && err.message) ? err.message : String(err);
      const errBox = document.createElement('div');
      errBox.className = 'mermaid-error';
      errBox.textContent = '⚠️ Mermaid 渲染失败：' + msg;
      node.parentNode.replaceChild(errBox, node);
    }
  }
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
