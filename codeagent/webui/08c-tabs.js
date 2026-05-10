      return;
    }

    fetch('/api/ui/files/read?path=' + encodeURIComponent(path) + '&project_id=' + encodeURIComponent(_fileTreeProjectId))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) {
          _setEditorStatus('❌ ' + data.error);
          return;
        }
        var tab = {
          path: path,
          name: name,
          language: data.language || 'plaintext',
          content: data.content,
        };
        _openTabs.push(tab);
        _renderTabs();
        _activateTab(_openTabs.length - 1);
        _showEditor();
        _setEditorStatus('📄 ' + path + '  (' + data.lines + ' 行, ' + data.size + ' B)');
      })
      .catch(function(err) {
        _setEditorStatus('❌ 加载失败: ' + err.message);
      });
  }

  function _activateTab(index) {
    _activeTab = index;
    _renderTabs();
    var tab = _openTabs[index];
    if (!tab) return;
    _setEditorContent(tab.content, tab.language);
  }

  function _closeTab(index) {
    _openTabs.splice(index, 1);
    if (_openTabs.length === 0) {
      _activeTab = null;
      _renderTabs();
      _showWelcome();
      return;
    }
    if (index >= _openTabs.length) index = _openTabs.length - 1;
    _activateTab(index);
  }

  function _renderTabs() {
    var container = document.getElementById('editorTabs');
    if (!container) return;
    if (_openTabs.length === 0) {
      container.innerHTML = '<div class="file-editor__tabs-empty">选择一个文件查看</div>';
      return;
    }
    var html = '';
    _openTabs.forEach(function(tab, i) {
      var active = i === _activeTab ? ' active' : '';
      html += '<div class="file-editor__tab' + active + '" data-index="' + i + '">' +
        '<span class="file-editor__tab-name">' + escapeHtml(tab.name) + '</span>' +
        '<span class="file-editor__tab-close" data-index="' + i + '">×</span></div>';
    });
    container.innerHTML = html;
    // 添加事件
    container.querySelectorAll('.file-editor__tab').forEach(function(el) {
      el.addEventListener('click', function(e) {
        if (e.target.classList.contains('file-editor__tab-close')) {
          _closeTab(parseInt(e.target.dataset.index));
        } else {
          _activateTab(parseInt(el.dataset.index));
        }
      });
    });
  }

  // =============================================
  // Monaco / 编辑器
  // =============================================
  function _showEditor() {
    var welcome = document.querySelector('.file-editor__welcome');
    if (welcome) welcome.style.display = 'none';
