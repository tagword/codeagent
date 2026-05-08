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
    if (!_fileTreeLoaded) {
      _renderFileTree('', container);
    }
    _loadMonaco();
  }
  window.webuiRefreshFileTreeIfVisible = refreshFileTreeIfVisible;

  function _init() {
    // 监听模式切换 - 当切换到 files 模式时渲染文件树
    var origSwitch = window.switchMode;
    var _origSwitch = window.switchSidebarMode;
    // 尝试 hook 活动栏切换
    document.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-mode="files"]');
      if (btn) {
        setTimeout(function() {
          refreshFileTreeIfVisible();
        }, 50);
      }
    });
    // 如果 stats 按钮存在，在 DOM 加载完后初始化
    if (document.querySelector('[data-mode="files"]')) {
      // 先尝试加载 Monaco（预加载）
      _loadMonaco();
    }
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
