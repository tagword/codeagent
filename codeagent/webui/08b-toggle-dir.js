
    if (children.classList.contains('open')) {
      children.classList.remove('open');
      if (toggle) toggle.classList.remove('expanded');
      return;
    }

    // 加载子目录
    if (toggle) toggle.classList.add('expanded');
    children.innerHTML = '<div class="file-tree__loading">加载中...</div>';
    children.classList.add('open');

    fetch('/api/ui/files/list?dir=' + encodeURIComponent(path) + '&project_id=' + encodeURIComponent(_fileTreeProjectId))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        children.innerHTML = '';
        var items = data.files || data.items || [];
        if (data.detail && items.length === 0) {
          children.innerHTML = '<div class="file-tree__loading" style="padding-left:20px;color:#e88;">' + data.detail + '</div>';
          return;
        }
        if (items.length === 0) {
          children.innerHTML = '<div class="file-tree__loading" style="padding-left:20px;">(空)</div>';
          return;
        }
        items.forEach(function(item) {
          var subEl = document.createElement('div');
          subEl.className = 'file-tree__item' + (item.is_dir ? ' file-tree__item--dir' : ' file-tree__item--file');
          subEl.dataset.path = item.path;
          subEl.dataset.isDir = item.is_dir;
          subEl.style.paddingLeft = ((parseInt(el.style.paddingLeft) || 4) + 16) + 'px';

          if (item.is_dir) {
            subEl.innerHTML = '<span class="file-tree__toggle">▸</span>' +
              '<span class="file-tree__icon">📁</span>' +
              '<span class="file-tree__name">' + escapeHtml(item.name) + '</span>';
            subEl.onclick = function(e) {
              e.stopPropagation();
              _toggleDir(item.path, subEl);
            };
            var subChildren = document.createElement('div');
            subChildren.className = 'file-tree__children';
            subChildren.id = 'children-' + item.path.replace(/[\/.]/g,'_');
            subEl.appendChild(subChildren);
          } else {
            var icon = _getFileIcon(item.name);
            subEl.innerHTML = '<span class="file-tree__icon">' + icon + '</span>' +
              '<span class="file-tree__name">' + escapeHtml(item.name) + '</span>';
            subEl.onclick = function(e) {
              e.stopPropagation();
              _openFile(item.path, item.name);
              document.querySelectorAll('.file-tree__item.active').forEach(function(a) { a.classList.remove('active'); });
              subEl.classList.add('active');
            };
          }
          children.appendChild(subEl);
        });
      })
      .catch(function(err) {
        children.innerHTML = '<div class="file-tree__loading" style="color:#e33;">' + err.message + '</div>';
      });
  }

  // =============================================
  // 打开文件
  // =============================================
  function _openFile(path, name) {
    // 检查是否已打开
    var existing = _openTabs.findIndex(function(t) { return t.path === path; });
    if (existing >= 0) {
      _activateTab(existing);
