        el.addEventListener('change', _updateProjectRemotePreview);
      });

      // 绑定按钮事件：用 onclick 直接赋值，自动覆盖旧监听器
      btnConfirm.onclick = onSubmit;
      btnCancel.onclick = closeDialog;
      btnClose.onclick = closeDialog;
      inpName.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') onSubmit();
        if (e.key === 'Escape') closeDialog();
      });
      inpPath.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') onSubmit();
        if (e.key === 'Escape') closeDialog();
      });
      dialog.addEventListener('click', function(e) {
        if (e.target === dialog) closeDialog();
      });
    }

    function _updateProjectSourceFields(source) {
      document.getElementById('fieldCloneUrl').style.display = source === 'clone' ? 'block' : 'none';
      document.getElementById('fieldTemplate').style.display = source === 'template' ? 'block' : 'none';
      // 克隆模式隐藏远程配置（克隆自带 origin）
      var remoteField = document.getElementById('fieldProjectRemote');
      if (source === 'clone') {
        remoteField.style.display = 'none';
      } else {
        remoteField.style.display = 'block';
      }
    }

    async function _loadProjectDefaults() {
      try {
        var r = await fetch('/api/ui/git/defaults');
        if (!r.ok) return;
        var j = await r.json();
        var def = j.defaults || {};
        if (def.enabled) {
          document.getElementById('chkProjectRemoteEnable').checked = true;
          document.getElementById('projectRemoteForm').style.display = 'block';
          if (def.provider) document.getElementById('selProjectRemoteProvider').value = def.provider;
          if (def.owner) document.getElementById('inpProjectRemoteOwner').value = def.owner;
          if (def.protocol === 'https') {
            var el = document.querySelector('input[name="projectRemoteProtocol"][value="https"]');
            if (el) el.checked = true;
          }
          document.getElementById('chkProjectAutoPush').checked = !!def.autoPush;
          _updateProjectRemotePreview();
        }
      } catch(_) {}
    }

    function _updateProjectRemotePreview() {
      var preview = document.getElementById('projectRemoteUrlPreview');
      if (!preview) return;
      var provider = document.getElementById('selProjectRemoteProvider').value;
      var owner = document.getElementById('inpProjectRemoteOwner').value.trim() || '{owner}';
      var repo = document.getElementById('inpProjectRemoteRepo').value.trim() || '{repo}';
      var protocol = document.querySelector('input[name="projectRemoteProtocol"]:checked')?.value || 'ssh';
      var templates = {
        'github': { ssh: 'git@github.com:{owner}/{repo}.git', https: 'https://github.com/{owner}/{repo}.git' },
        'gitlab': { ssh: 'git@gitlab.com:{owner}/{repo}.git', https: 'https://gitlab.com/{owner}/{repo}.git' },
        'gitee': { ssh: 'git@gitee.com:{owner}/{repo}.git', https: 'https://gitee.com/{owner}/{repo}.git' },
        'bitbucket': { ssh: 'git@bitbucket.org:{owner}/{repo}.git', https: 'https://bitbucket.org/{owner}/{repo}.git' },
      };
      var t = templates[provider];
      if (t) preview.textContent = 'URL: ' + t[protocol].replace('{owner}', owner).replace('{repo}', repo);
    }

    // ---- 目录选择器：服务端调系统对话框（macOS choose folder / Win 文件夹选择器），返回完整路径 ---- //
    function initNativeDirPicker() {
      var btnBrowse = document.getElementById('btnBrowseDir');
      var inpPath = document.getElementById('inpNewProjectPath');
      if (!btnBrowse || btnBrowse.dataset.bound) return;
      btnBrowse.dataset.bound = '1';

      btnBrowse.addEventListener('click', function() {
        btnBrowse.textContent = '⏳ 选择中…';
        btnBrowse.disabled = true;

        fetch('/api/ui/pick-directory', { method: 'POST', credentials: 'same-origin' })
          .then(function(r) { return r.json(); })
          .then(function(j) {
            if (j.path) inpPath.value = j.path;
            else if (j.detail) console.warn('pick-directory:', j.detail);
          })
          .catch(function(e) { console.error('pick-directory error:', e); })
          .finally(function() {
            btnBrowse.textContent = '📁 浏览';
            btnBrowse.disabled = false;
          });
      });
    }
    initNativeDirPicker();

    async function doCreateProject(name, path, source, cloneUrl, template, remoteInfo) {
      // 显示进度提示
      _showProjectProgress(true, source, cloneUrl);
      try {
