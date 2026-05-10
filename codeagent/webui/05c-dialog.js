  try {
    const r = await fetch('/api/ui/flags');
    const f = await r.json();
    if (!f.sessions_ui) return;
    webuiSessionsEnabled = true;
    if (fs) fs.style.display = 'block';
    if (sidebar) {
      var actMode = '';
      try { actMode = localStorage.getItem('oa_activity_mode') || ''; } catch (_) {}
      if (actMode === 'stats') {
        sidebar.style.display = 'none';
        var st = document.getElementById('sidebarStats');
        if (st) st.style.display = 'flex';
        if (typeof loadStats === 'function') loadStats();
      } else {
        sidebar.style.display = 'flex';
      }
    }
        bindSessListOnce();
    const btnProj = document.getElementById('btnNewProject');
    if (btnProj && btnProj.dataset.bound !== '1') {
      btnProj.dataset.bound = '1';
      btnProj.addEventListener('click', () => {
        showNewProjectDialog();
      });
    }

    // ---- 新建项目对话框逻辑（含来源选择 + 远程配置） ---- //
    function showNewProjectDialog() {
      var dialog = document.getElementById('newProjectDialog');
      var inpName = document.getElementById('inpNewProjectName');
      var inpPath = document.getElementById('inpNewProjectPath');
      var btnConfirm = document.getElementById('btnNewProjectConfirm');
      var btnCancel = document.getElementById('btnNewProjectCancel');
      var btnClose = document.getElementById('btnNewProjectDialogClose');
      if (!dialog || !inpName) return;

      // 重置
      inpName.value = '';
      inpPath.value = '';
      document.querySelector('input[name="projectSource"][value="scratch"]').checked = true;
      document.getElementById('inpCloneUrl').value = '';
      document.getElementById('chkProjectRemoteEnable').checked = false;
      document.getElementById('projectRemoteForm').style.display = 'none';
      _updateProjectSourceFields('scratch');

      // 加载默认远程配置
      _loadProjectDefaults();

      dialog.style.display = 'flex';
      setTimeout(function() { inpName.focus(); }, 100);

      function closeDialog() { dialog.style.display = 'none'; }

      function onSubmit() {
        var name = inpName.value.trim();
        if (!name) { inpName.focus(); return; }
        var path = inpPath.value.trim();

        // 收集来源信息
        var source = document.querySelector('input[name="projectSource"]:checked')?.value || 'scratch';
        var cloneUrl = source === 'clone' ? document.getElementById('inpCloneUrl').value.trim() : '';
        var template = source === 'template' ? document.getElementById('selProjectTemplate').value : '';

        // 收集远程信息
        var remoteInfo = null;
        if (source !== 'clone' && document.getElementById('chkProjectRemoteEnable').checked) {
          remoteInfo = {
            provider: document.getElementById('selProjectRemoteProvider').value,
            owner: document.getElementById('inpProjectRemoteOwner').value.trim(),
            repo: document.getElementById('inpProjectRemoteRepo').value.trim(),
            protocol: document.querySelector('input[name="projectRemoteProtocol"]:checked')?.value || 'ssh',
            autoPush: document.getElementById('chkProjectAutoPush').checked,
          };
          if (!remoteInfo.owner || !remoteInfo.repo) remoteInfo = null;
        }

        // 不关闭对话框，而是显示进度覆盖层
        _showProjectProgress(true, source, cloneUrl);
        doCreateProject(name, path, source, cloneUrl, template, remoteInfo);
      }

      // 来源切换
      document.querySelectorAll('input[name="projectSource"]').forEach(function(el) {
        el.addEventListener('change', function() {
          _updateProjectSourceFields(this.value);
        });
      });

      // 远程启用/禁用
      document.getElementById('chkProjectRemoteEnable').addEventListener('change', function() {
        document.getElementById('projectRemoteForm').style.display = this.checked ? 'block' : 'none';
      });

      // 远程输入实时预览
      ['selProjectRemoteProvider', 'inpProjectRemoteOwner', 'inpProjectRemoteRepo'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.addEventListener('change', _updateProjectRemotePreview);
      });
      document.querySelectorAll('input[name="projectRemoteProtocol"]').forEach(function(el) {
