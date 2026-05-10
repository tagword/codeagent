  }

  function _showWelcome() {
    var welcome = document.querySelector('.file-editor__welcome');
    if (welcome) welcome.style.display = 'flex';
    _setEditorStatus('');
  }

  function _setEditorStatus(msg) {
    var el = document.getElementById('editorStatus');
    if (el) el.textContent = msg || '';
  }

  function _setEditorContent(content, language) {
    var container = document.getElementById('editorContainer');
    if (!container) return;

    if (typeof monaco !== 'undefined' && monaco.editor) {
      if (_monacoEditor) {
        _monacoEditor.setValue(content);
        monaco.editor.setModelLanguage(_monacoEditor.getModel(), language || 'plaintext');
      } else {
        _monacoEditor = monaco.editor.create(container, {
          value: content,
          language: language || 'plaintext',
          theme: 'vs-dark',
          automaticLayout: true,
          minimap: { enabled: true },
          fontSize: 13,
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          tabSize: 4,
        });
      }
    } else {
      // Fallback: textarea
      container.innerHTML = '<textarea style="width:100%;height:100%;background:#1e1e1e;color:#d4d4d4;border:none;padding:8px;font-family:monospace;font-size:13px;resize:none;" spellcheck="false">' + escapeHtml(content) + '</textarea>';
    }
  }

  // =============================================
  // 初始化：监听 files 模式切换
  // =============================================
  function refreshFileTreeIfVisible() {
    var filesSection = document.getElementById('sidebarFiles');
    var container = document.getElementById('fileTreeContainer');
    if (!filesSection || !container || filesSection.style.display === 'none') return;
    // 每次切到文件模式都重新加载，确保切换项目后能刷新（不依赖 _fileTreeLoaded 缓存）
    _renderFileTree('', container);
    _loadMonaco();
  }
  window.webuiRefreshFileTreeIfVisible = refreshFileTreeIfVisible;

  function _init() {
    // 监听模式切换 - 当切换到 files 模式时渲染文件树（由 switchActivityMode 触发）
    // 文件树由 switchActivityMode('files') 内部自动触发刷新
    // 预加载 Monaco 编辑器（首次进入文件模式时会按需加载）
    // 这里不再依赖 activity bar 的 [data-mode="files"] 按钮
    // 因为该按钮已移至 topbar
  }

  // =============================================
  // 工具函数
  // =============================================
  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function _getFileIcon(name) {
    var ext = name.split('.').pop().toLowerCase();
    var icons = {
      py: '🐍', js: '🟨', jsx: '⚛️', ts: '🔵', tsx: '⚛️',
      html: '🌐', css: '🎨', json: '📋', md: '📝',
      yaml: '⚙️', yml: '⚙️', toml: '⚙️', ini: '⚙️',
      sql: '🗃️', sh: '💻', bash: '💻',
      txt: '📄', cfg: '⚙️', conf: '⚙️',
      png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🖼️',
    };
    return icons[ext] || '📄';
  }

  // 页面加载后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

})();
