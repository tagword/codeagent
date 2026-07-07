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
        // 兼容旧格式
        if (!def.presets && def.provider) {
          def.presets = [{
            name: '默认',
            provider: def.provider,
            owner: def.owner || '',
            host: def.host || '',
            protocol: def.protocol || 'ssh',
            autoPush: !!def.autoPush,
          }];
          def.defaultPreset = '默认';
        }
        if (def.enabled) {
          document.getElementById('chkProjectRemoteEnable').checked = true;
          document.getElementById('projectRemoteForm').style.display = 'block';
          // 填充方案选择器
          var presets = def.presets || [];
          var defaultName = def.defaultPreset || '';
          var selPreset = document.getElementById('selProjectPreset');
          if (selPreset) {
            if (presets.length > 1) {
              document.getElementById('presetSelectorRow').style.display = '';
              selPreset.innerHTML = '<option value="">— 选择方案 —</option>';
              for (var i = 0; i < presets.length; i++) {
                var opt = document.createElement('option');
                opt.value = presets[i].name;
                opt.textContent = presets[i].name;
                selPreset.appendChild(opt);
              }
            } else {
              document.getElementById('presetSelectorRow').style.display = 'none';
            }
            // 默认选中 defaultPreset
            if (defaultName) {
              selPreset.value = defaultName;
              _applyPreset(defaultName, presets);
            } else if (presets.length === 1) {
              _applyPreset(presets[0].name, presets);
            }
          } else {
            // fallback: 无选择器时直接填第一套
            if (presets.length) _applyPreset(presets[0].name, presets);
          }
        }
      } catch(_) {}
    }

    function _applyPreset(name, presets) {
      var p = null;
      for (var i = 0; i < (presets || []).length; i++) {
        if (presets[i].name === name) { p = presets[i]; break; }
      }
      if (!p && presets && presets.length) p = presets[0];
      if (!p) return;
      document.getElementById('selProjectRemoteProvider').value = p.provider || 'github';
      if (p.host) document.getElementById('inpProjectRemoteHost').value = p.host;
      if (p.owner) document.getElementById('inpProjectRemoteOwner').value = p.owner;
      if (p.protocol === 'https') {
        var el = document.querySelector('input[name="projectRemoteProtocol"][value="https"]');
        if (el) el.checked = true;
      } else {
        var el2 = document.querySelector('input[name="projectRemoteProtocol"][value="ssh"]');
        if (el2) el2.checked = true;
      }
      document.getElementById('chkProjectAutoPush').checked = !!p.autoPush;
      _updateProjectRemotePreview();
    }

    function _updateProjectRemotePreview() {
      var preview = document.getElementById('projectRemoteUrlPreview');
      if (!preview) return;
      var provider = document.getElementById('selProjectRemoteProvider').value;
      var hostEl = document.getElementById('inpProjectRemoteHost');
      var ownerEl = document.getElementById('inpProjectRemoteOwner');
      var repoEl = document.getElementById('inpProjectRemoteRepo');

      // 显示/隐藏 主机地址输入
      hostEl.style.display = provider === 'custom' ? '' : 'none';

      var owner = ownerEl.value.trim() || '{owner}';
      var repo = repoEl.value.trim() || '{repo}';
      var protocol = document.querySelector('input[name="projectRemoteProtocol"]:checked')?.value || 'ssh';
      var templates = {
        'github': { ssh: 'git@github.com:{owner}/{repo}.git', https: 'https://github.com/{owner}/{repo}.git' },
        'gitlab': { ssh: 'git@gitlab.com:{owner}/{repo}.git', https: 'https://gitlab.com/{owner}/{repo}.git' },
        'gitee': { ssh: 'git@gitee.com:{owner}/{repo}.git', https: 'https://gitee.com/{owner}/{repo}.git' },
        'bitbucket': { ssh: 'git@bitbucket.org:{owner}/{repo}.git', https: 'https://bitbucket.org/{owner}/{repo}.git' },
      };
      var t = templates[provider];
      if (t) {
        preview.textContent = 'URL: ' + t[protocol].replace('{owner}', owner).replace('{repo}', repo);
      } else if (provider === 'custom') {
        var host = hostEl.value.trim() || '{host}';
        var url;
        if (protocol === 'ssh') {
          url = 'git@' + host + ':' + owner + '/' + repo + '.git';
        } else {
          url = 'https://' + host + '/' + owner + '/' + repo + '.git';
        }
        preview.textContent = 'URL: ' + url;
      }
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
            else if (j.hint) console.warn('pick-directory:', j.hint);
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
