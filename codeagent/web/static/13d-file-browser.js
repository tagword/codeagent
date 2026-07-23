/* ================================================================
 * 13d-file-browser.js — File browser (sidebar tree + workspace editor)
 *
 *   Exposes: webuiRefreshFileTreeIfVisible()
 *   Dependencies: projectId (global)
 *
 *   Layout:
 *     Mode 'files' → sidebarFiles (file tree) + page-files (editor)
 * ================================================================ */

// ---- SVG icons ----
var FB_ICON_FOLDER = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3.5h4.5L8 5.5h6v7a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4a.5.5 0 0 1 .5-.5z"/></svg>';
var FB_ICON_FILE = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M10 1.5H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V5l-3-3.5z"/><path d="M10 1.5V5h3.5"/></svg>';

// ---- State ----
var _fb = {
  rootDir: '',
  currentDir: '',
  entries: [],
  breadcrumbs: [],
  openTabs: [],    // [{path, name, lang, content, lines, size}]
  activeTab: null, // path of active tab
};

// ---- Helpers ----
function _fbApi(path, params) {
  var q = '?project_id=' + encodeURIComponent(projectId || '');
  if (params) q += '&' + params;
  return fetch(path + q, { credentials: 'same-origin' });
}

function _fbFormatSize(bytes) {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function _fbFileLang(filename) {
  var ext = filename.includes('.') ? filename.split('.').pop().toLowerCase() : '';
  var map = {
    py: 'Python', js: 'JavaScript', jsx: 'JSX', ts: 'TypeScript', tsx: 'TSX',
    html: 'HTML', css: 'CSS', scss: 'SCSS', json: 'JSON', md: 'Markdown',
    yaml: 'YAML', yml: 'YAML', toml: 'TOML', sql: 'SQL', sh: 'Shell',
    go: 'Go', rs: 'Rust', java: 'Java', xml: 'XML', svg: 'SVG',
    txt: 'Text', ini: 'INI', cfg: 'INI', vue: 'Vue', svelte: 'Svelte',
  };
  return map[ext] || '';
}

function _fbEntrySort(a, b) {
  if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
  return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
}

function _fbEscHtml(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function _fbEscAttr(s) {
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// =====================================================
// Sidebar file tree
// =====================================================

function _fbRender() {
  var container = document.getElementById('fileTreeContainer');
  if (!container) return;

  var html = '<div class="file-browser">';
  // Breadcrumbs
  html += '<div class="file-browser__bread">';
  _fb.breadcrumbs.forEach(function(seg, i) {
    if (i > 0) html += '<span class="file-browser__bread-sep">▸</span>';
    html += '<span class="file-browser__bread-seg" data-fb-bread="' + i + '">' + _fbEscHtml(seg.label) + '</span>';
  });
  html += '</div>';
  // Entries
  html += '<div class="file-browser__list">';
  if (_fb.entries.length === 0) {
    html += '<div class="file-browser__empty">此目录为空</div>';
  } else {
    _fb.entries.forEach(function(entry) {
      var icon = entry.is_dir ? FB_ICON_FOLDER : FB_ICON_FILE;
      var iconCls = entry.is_dir ? 'file-browser__entry-icon--dir' : '';
      var sizeStr = entry.is_dir && entry.size ? _fbFormatSize(entry.size) : (!entry.is_dir ? _fbFormatSize(entry.size) : '');
      html += '<div class="file-browser__entry" data-fb-path="' + _fbEscAttr(entry.path) + '" data-fb-dir="' + (entry.is_dir ? '1' : '0') + '">';
      html += '<span class="file-browser__entry-icon ' + iconCls + '">' + icon + '</span>';
      html += '<span class="file-browser__entry-name">' + _fbEscHtml(entry.name) + '</span>';
      if (sizeStr) html += '<span class="file-browser__entry-size">' + sizeStr + '</span>';
      html += '</div>';
    });
  }
  html += '</div></div>';
  container.innerHTML = html;
  _fbBindTreeEvents();
}

function _fbBindTreeEvents() {
  var container = document.getElementById('fileTreeContainer');
  if (!container) return;

  container.querySelectorAll('[data-fb-bread]').forEach(function(el) {
    el.addEventListener('click', function() {
      _fbNavToBreadcrumb(parseInt(this.getAttribute('data-fb-bread'), 10));
    });
  });

  container.querySelectorAll('.file-browser__entry').forEach(function(el) {
    el.addEventListener('click', function() {
      var path = this.getAttribute('data-fb-path');
      var isDir = this.getAttribute('data-fb-dir') === '1';
      if (!path) return;
      if (isDir) {
        _fbLoadDir(path);
      } else {
        _fbOpenFile(path);
      }
    });
  });
}

function _fbNavToBreadcrumb(idx) {
  if (idx < 0 || idx >= _fb.breadcrumbs.length) return;
  _fbLoadDir(_fb.breadcrumbs[idx].path);
}

function _fbLoadDir(dirPath) {
  var container = document.getElementById('fileTreeContainer');
  if (!container) return;
  container.innerHTML = '<div class="file-browser"><div class="file-browser__loading"><div class="file-browser__spinner"></div>加载中...</div></div>';

  _fbApi('/api/ui/files/list', 'dir=' + encodeURIComponent(dirPath))
    .then(function(r) { if (!r.ok) throw new Error('请求失败'); return r.json(); })
    .then(function(j) {
      var items = j.files || [];
      items.sort(_fbEntrySort);

      var crumbs = [];
      var root = _fb.rootDir;
      crumbs.push({ label: _fb.rootLabel || '项目根目录', path: root });
      if (dirPath !== root) {
        var rel = dirPath.startsWith(root) ? dirPath.slice(root.length).replace(/^\/+/, '') : dirPath;
        var parts = rel.split('/').filter(Boolean);
        var acc = root;
        parts.forEach(function(p) { acc = acc + '/' + p; crumbs.push({ label: p, path: acc }); });
      }

      _fb.currentDir = dirPath;
      _fb.entries = items;
      _fb.breadcrumbs = crumbs;
      _fbRender();
    })
    .catch(function(err) {
      container.innerHTML = '<div class="file-browser"><div class="file-browser__error">' + _fbEscHtml(err.message || String(err))
        + '<br><button class="file-browser__reload-btn" id="fbRetryBtn">重试</button></div></div>';
      var retryBtn = document.getElementById('fbRetryBtn');
      if (retryBtn) retryBtn.addEventListener('click', function() { _fbLoadDir(dirPath); });
    });
}

// =====================================================
// Workspace file editor
// =====================================================

function _fbOpenFile(filePath) {
  var filename = filePath.split('/').pop() || filePath;

  // If already open, just switch tab
  var existing = _fb.openTabs.findIndex(function(t) { return t.path === filePath; });
  if (existing >= 0) {
    _fb.activeTab = filePath;
    _fbRenderTabs();
    _fbRenderEditor();
    return;
  }

  // Add new tab
  _fb.openTabs.push({ path: filePath, name: filename, lang: _fbFileLang(filename), loading: true });
  _fb.activeTab = filePath;
  _fbRenderTabs();
  _fbShowEditorLoading(filename);

  // Fetch content
  _fbApi('/api/ui/files/read', 'path=' + encodeURIComponent(filePath))
    .then(function(r) { if (!r.ok) throw new Error('读取失败'); return r.json(); })
    .then(function(j) {
      var tab = _fb.openTabs.find(function(t) { return t.path === filePath; });
      if (tab) {
        tab.loading = false;
        tab.content = j.content || '';
        tab.lines = j.lines || 0;
        tab.size = j.size || 0;
      }
      if (_fb.activeTab === filePath) {
        _fbRenderEditor();
      }
    })
    .catch(function(err) {
      var tab = _fb.openTabs.find(function(t) { return t.path === filePath; });
      if (tab) { tab.loading = false; tab.error = err.message || String(err); }
      if (_fb.activeTab === filePath) {
        _fbRenderEditor();
      }
    });
}

function _fbRenderTabs() {
  var tabsEl = document.getElementById('editorTabs');
  if (!tabsEl) return;

  if (_fb.openTabs.length === 0) {
    tabsEl.innerHTML = '<div class="file-editor__tabs-empty">选择一个文件查看</div>';
    return;
  }

  var html = '';
  _fb.openTabs.forEach(function(tab) {
    var active = tab.path === _fb.activeTab ? ' active' : '';
    var langBadge = tab.lang ? '<span class="file-editor__tab-lang">' + _fbEscHtml(tab.lang) + '</span>' : '';
    html += '<div class="file-editor__tab' + active + '" data-tab-path="' + _fbEscAttr(tab.path) + '">'
      + langBadge
      + '<span class="file-editor__tab-name">' + _fbEscHtml(tab.name) + '</span>'
      + '<button class="file-editor__tab-close" data-tab-close="' + _fbEscAttr(tab.path) + '">✕</button>'
      + '</div>';
  });
  tabsEl.innerHTML = html;

  // Tab click
  tabsEl.querySelectorAll('.file-editor__tab').forEach(function(el) {
    el.addEventListener('click', function(e) {
      if (e.target.closest('.file-editor__tab-close')) return;
      var path = this.getAttribute('data-tab-path');
      if (path && path !== _fb.activeTab) {
        _fb.activeTab = path;
        _fbRenderTabs();
        _fbRenderEditor();
      }
    });
  });

  // Close button
  tabsEl.querySelectorAll('.file-editor__tab-close').forEach(function(el) {
    el.addEventListener('click', function(e) {
      e.stopPropagation();
      var path = this.getAttribute('data-tab-close');
      _fbCloseTab(path);
    });
  });
}

function _fbCloseTab(path) {
  var idx = _fb.openTabs.findIndex(function(t) { return t.path === path; });
  if (idx < 0) return;
  _fb.openTabs.splice(idx, 1);
  if (_fb.activeTab === path) {
    _fb.activeTab = _fb.openTabs.length > 0 ? _fb.openTabs[Math.min(idx, _fb.openTabs.length - 1)].path : null;
  }
  _fbRenderTabs();
  _fbRenderEditor();
}

function _fbShowEditorLoading(filename) {
  var container = document.getElementById('editorContainer');
  var statusEl = document.getElementById('editorStatus');
  if (container) {
    container.innerHTML = '<div class="file-editor__loading"><div class="file-browser__spinner" style="margin-right:8px"></div>加载 ' + _fbEscHtml(filename) + '...</div>';
  }
  if (statusEl) statusEl.textContent = '';
}

function _fbRenderEditor() {
  var container = document.getElementById('editorContainer');
  var statusEl = document.getElementById('editorStatus');
  if (!container) return;

  if (!_fb.activeTab || _fb.openTabs.length === 0) {
    container.innerHTML = '<div class="file-editor__welcome"><h3>文件编辑器</h3><p>从左侧文件树选择文件进行编辑</p></div>';
    if (statusEl) statusEl.textContent = '';
    return;
  }

  var tab = _fb.openTabs.find(function(t) { return t.path === _fb.activeTab; });
  if (!tab) return;

  if (tab.loading) {
    container.innerHTML = '<div class="file-editor__loading"><div class="file-browser__spinner" style="margin-right:8px"></div>加载中...</div>';
    if (statusEl) statusEl.textContent = '';
    return;
  }

  if (tab.error) {
    container.innerHTML = '<div class="file-editor__error">' + _fbEscHtml(tab.error) + '</div>';
    if (statusEl) statusEl.textContent = '错误';
    return;
  }

  var escaped = (tab.content || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  container.innerHTML = '<pre class="file-editor__code">' + escaped + '</pre>';
  if (statusEl) statusEl.textContent = tab.name + '  ·  ' + (tab.lines || 0) + ' 行  ·  ' + _fbFormatSize(tab.size || 0);
}

// =====================================================
// Init / exported
// =====================================================

window.webuiRefreshFileTreeIfVisible = function() {
  var filesSection = document.getElementById('sidebarFiles');
  if (!filesSection || !filesSection.classList.contains('is-visible')) return;

  var container = document.getElementById('fileTreeContainer');
  if (!container) return;

  if (!projectId) {
    container.innerHTML = '<div class="file-browser"><div class="file-browser__no-project"><span style="font-size:24px;opacity:0.3">📂</span><div>请先选择一个项目</div><div style="font-size:11px;color:var(--text-subtle)">在左侧会话树中点击项目名称</div></div></div>';
    _fb.rootDir = ''; _fb.currentDir = ''; _fb.entries = []; _fb.breadcrumbs = [];
    return;
  }

  _fbApi('/api/ui/files/list', 'dir=')
    .then(function(r) { if (!r.ok) throw new Error('无法获取项目文件列表'); return r.json(); })
    .then(function(j) {
      var root = j.base_path || '';
      var items = j.files || [];
      items.sort(_fbEntrySort);
      _fb.rootDir = root;
      _fb.currentDir = root;
      _fb.entries = items;
      _fb.rootLabel = projectId;
      _fb.breadcrumbs = [{ label: projectId, path: root }];
      _fbRender();
    })
    .catch(function(err) {
      container.innerHTML = '<div class="file-browser"><div class="file-browser__error">' + _fbEscHtml(err.message || String(err))
        + '<br><button class="file-browser__reload-btn" id="fbRetryRootBtn">重试</button></div></div>';
      var retryBtn = document.getElementById('fbRetryRootBtn');
      if (retryBtn) retryBtn.addEventListener('click', function() { window.webuiRefreshFileTreeIfVisible(); });
    });
};

// ---- Init ----
(function _fbInit() {
  // Auto-refresh on project change
  window.addEventListener('project-changed', function() {
    var fs = document.getElementById('sidebarFiles');
    if (fs && fs.classList.contains('is-visible')) {
      window.webuiRefreshFileTreeIfVisible();
    }
  });
})();
