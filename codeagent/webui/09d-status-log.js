    _gitApi('status').then(function(r) {
      if (r.error) {
        container.innerHTML = '<div style="color:var(--danger,#e06c75);padding:8px 12px;">❌ ' + escapeHtml(r.error) + '</div>';
        return;
      }
      var output = r.result || '';
      _renderStatus(container, output);
    }).catch(function(err) {
      container.innerHTML = '<div style="color:var(--danger,#e06c75);padding:8px 12px;">❌ ' + escapeHtml(err.message) + '</div>';
    });
  }

  function _renderStatus(container, output) {
    if (!output || output.trim() === '' || output.trim() === '(无输出)') {
      container.innerHTML = '<div style="color:var(--success,#98c379);padding:12px;text-align:center;">✅ 工作区干净，无改动</div>';
      return;
    }

    var lines = output.split('\n');
    var sections = [];
    var currentSection = null;

    lines.forEach(function(line) {
      var trimmed = line.trim();
      if (/^(📌|已暂存|Changes to be committed)/i.test(trimmed)) {
        currentSection = { label: '已暂存', icon: '📌', files: [] };
        sections.push(currentSection); return;
      }
      if (/^(📝|未暂存|Changes not staged)/i.test(trimmed)) {
        currentSection = { label: '未暂存', icon: '📝', files: [] };
        sections.push(currentSection); return;
      }
      if (/^(🆕|未跟踪|Untracked)/i.test(trimmed)) {
        currentSection = { label: '未跟踪', icon: '🆕', files: [] };
        sections.push(currentSection); return;
      }
      if (/^(✅|工作区干净)/i.test(trimmed)) {
        container.innerHTML = '<div style="color:var(--success,#98c379);padding:12px;text-align:center;">✅ 工作区干净，无改动</div>';
        return;
      }
      if (trimmed && trimmed.length >= 3 && currentSection) {
        var statusChar = trimmed[0];
        var filePath = trimmed.substring(1).trim();
        if (filePath) currentSection.files.push({ status: statusChar, path: filePath });
      }
    });

    if (sections.length === 0) {
      container.innerHTML = '<div style="color:var(--success,#98c379);padding:12px;text-align:center;">✅ 工作区干净，无改动</div>';
      return;
    }

    var html = '';
    sections.forEach(function(sec) {
      if (sec.files.length === 0) return;
      html += '<div style="font-weight:500;font-size:11px;padding:6px 12px 2px;color:var(--text-muted,#888);">'
        + sec.icon + ' ' + sec.label + ' <span style="font-weight:400;">(' + sec.files.length + ')</span></div>';
      sec.files.forEach(function(f) {
        var icon = _statusIcon(f.status);
        var cls = _statusClass(f.status);
        html += '<div class="git-panel__file" data-file="' + escapeHtmlAttr(f.path) + '">'
          + '<span class="git-panel__file-icon ' + cls + '">' + icon + '</span>'
          + '<span class="git-panel__file-name">' + escapeHtml(f.path) + '</span></div>';
      });
    });
    container.innerHTML = html;

    container.querySelectorAll('.git-panel__file').forEach(function(el) {
      el.addEventListener('click', function() {
        var path = this.getAttribute('data-file');
        if (path) _showFileDiff(path);
      });
    });
  }

  /* =============================================
   * 历史 / 差异 视图
   * ============================================= */
  function _loadLog(container) {
    container.innerHTML = '<div class="git-panel__loading">加载提交历史中...</div>';
