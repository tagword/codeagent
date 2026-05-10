/**
 * 文件浏览器 + Monaco 编辑器
 * 依赖: 08-file-tree.css
 */

(function() {
  'use strict';

  var _fileTreeLoaded = false;
  var _fileTreeProjectId = '';  // 当前项目 ID，切换项目时更新
  var _openTabs = [];       // [{path, name, language}]
  var _activeTab = null;
  var _monacoEditor = null;
  var _monacoLoaded = false;

  // =============================================
  // 加载 Monaco Editor (从 CDN)
  // =============================================
  function _loadMonaco(callback) {
    if (_monacoLoaded) {
      if (callback) callback();
      return;
    }
    // 不要重复加载
    if (document.querySelector('script[src*="monaco-editor"]')) {
      _monacoLoaded = true;
      if (callback) callback();
      return;
    }
    var loader = document.createElement('script');
    loader.src = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/loader.js';
    loader.onload = function() {
      require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' }});
      require(['vs/editor/editor.main'], function() {
        _monacoLoaded = true;
        if (callback) callback();
      });
    };
    loader.onerror = function() {
      console.warn('Monaco Editor 加载失败，使用文本编辑器');
      _monacoLoaded = true; // 标记为已尝试
    };
    document.head.appendChild(loader);
  }

  // =============================================
  // 渲染文件树
  // =============================================
  function _renderFileTree(dir, container, level) {
    _fileTreeProjectId = (typeof projectId !== 'undefined') ? projectId : '';
    level = level || 0;
    container = container || document.getElementById('fileTreeContainer');
    container.innerHTML = '<div class="file-tree__loading">加载中...</div>';

    fetch('/api/ui/files/list?dir=' + encodeURIComponent(dir || '') + '&project_id=' + encodeURIComponent(_fileTreeProjectId))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) {
          container.innerHTML = '<div class="file-tree__loading" style="color:#e33;">' + data.error + '</div>';
          return;
        }
        container.innerHTML = '';
        var items = data.files || data.items || [];
        if (data.detail && items.length === 0) {
          container.innerHTML = '<div class="file-tree__loading" style="color:#e88;">' + data.detail + '</div>';
          return;
        }
        if (items.length === 0) {
          container.innerHTML = '<div class="file-tree__loading">(空目录)</div>';
          return;
        }
        items.forEach(function(item) {
          var el = document.createElement('div');
          el.className = 'file-tree__item' + (item.is_dir ? ' file-tree__item--dir' : ' file-tree__item--file');
          el.dataset.path = item.path;
          el.dataset.isDir = item.is_dir;

          if (item.is_dir) {
            el.innerHTML = '<span class="file-tree__toggle" id="toggle-' + item.path.replace(/[\/.]/g,'_') + '">▸</span>' +
              '<span class="file-tree__icon">📁</span>' +
              '<span class="file-tree__name">' + escapeHtml(item.name) + '</span>';
            el.onclick = function(e) {
              if (e.target.className === 'file-tree__toggle') return;
              _toggleDir(item.path, el);
            };
            // 点击三角箭头
            var toggle = el.querySelector('.file-tree__toggle');
            if (toggle) {
              toggle.onclick = function(e) {
                e.stopPropagation();
                _toggleDir(item.path, el);
              };
            }
            // 子容器
            var children = document.createElement('div');
            children.className = 'file-tree__children';
            children.id = 'children-' + item.path.replace(/[\/.]/g,'_');
            el.appendChild(children);
          } else {
            var icon = _getFileIcon(item.name);
            el.innerHTML = '<span class="file-tree__icon">' + icon + '</span>' +
              '<span class="file-tree__name">' + escapeHtml(item.name) + '</span>';
            el.onclick = function() {
              _openFile(item.path, item.name);
              // 高亮
              container.querySelectorAll('.file-tree__item.active').forEach(function(a) { a.classList.remove('active'); });
              el.classList.add('active');
            };
          }
          container.appendChild(el);
        });

        _fileTreeLoaded = true;
      })
      .catch(function(err) {
        container.innerHTML = '<div class="file-tree__loading" style="color:#e33;">加载失败: ' + err.message + '</div>';
      });
  }

  function _toggleDir(path, el) {
    var toggle = el.querySelector('.file-tree__toggle');
    var children = el.querySelector('.file-tree__children');
    if (!children) return;
