// ---------------- Config paths & allowlist ----------------
// escapeHtml/escAttr 已统一在 00-utils.js（顶层声明）。

var GIT_PROVIDER_HTTPS_HOST = {
  github: 'https://github.com',
  gitlab: 'https://gitlab.com',
  gitee: 'https://gitee.com',
  bitbucket: 'https://bitbucket.org',
};

var GIT_PROVIDER_SSH_HOST = {
  github: 'git@github.com',
  gitlab: 'git@gitlab.com',
  gitee: 'git@gitee.com',
  bitbucket: 'git@bitbucket.org',
};

function _gitProviderFromSelect(id) {
  var el = document.getElementById(id);
  return el ? String(el.value || 'github').trim() : 'github';
}

function _syncCredUrlFromProvider() {
  var prov = _gitProviderFromSelect('selConfigCredProvider');
  var inp = document.getElementById('inpConfigCredUrl');
  if (inp) inp.value = GIT_PROVIDER_HTTPS_HOST[prov] || GIT_PROVIDER_HTTPS_HOST.github;
}

async function loadConfigPaths() {
  const display = document.getElementById('configPathsDisplay');
  if (!display) return;
  try {
    const r = await fetch('/api/ui/config/paths');
    if (!r.ok) return;
    const j = await r.json();
    display.innerHTML =
      '<div class="form-row" style="margin-bottom:var(--sp-1);max-width:100%;">'
      + '<label class="form-label" style="width:auto;min-width:100px;">根目录</label>'
      + '<code style="font-size:12px;word-break:break-all;line-height:28px;">' + escHtml(j.codeagent_root_path || '') + '</code>'
      + '</div>'
      + '<div class="form-row" style="margin-bottom:var(--sp-1);max-width:100%;">'
      + '<label class="form-label" style="width:auto;min-width:100px;">技能目录</label>'
      + '<code style="font-size:12px;word-break:break-all;line-height:28px;">' + escHtml(j.skills_path || '') + '</code>'
      + '</div>'
      + '<div class="form-row" style="max-width:100%;">'
      + '<label class="form-label" style="width:auto;min-width:100px;">人设目录</label>'
      + '<code style="font-size:12px;word-break:break-all;line-height:28px;">' + escHtml(j.persona_path || '') + '</code>'
      + '</div>';
  } catch (_) {}
  await loadAllowlistConfig();
}

async function loadAllowlistConfig() {
  const el = document.getElementById('allowlistConfig');
  if (!el) return;
  try {
    const r = await fetch('/api/ui/allowlist');
    if (!r.ok) return;
    const j = await r.json();
    const mode = j.mode || 'all';
    const paths = j.paths || [];
    el.innerHTML =
      '<div class="form-row"><label class="form-label" style="width:auto;min-width:100px;">权限模式</label>'
      + '<select id="selAllowMode" class="md-select" style="max-width:200px;">'
      + '<option value="all"' + (mode === 'all' ? ' selected' : '') + '>允许所有目录</option>'
      + '<option value="whitelist"' + (mode === 'whitelist' ? ' selected' : '') + '>仅允许白名单</option>'
      + '</select>'
      + '<span class="form-hint">限制 Agent 文件读写操作的范围</span>'
      + '</div>'
      + '<div id="allowPathsEditor"' + (mode === 'whitelist' ? '' : ' style="display:none;"') + '>'
      + '  <label class="form-label">白名单路径（每行一个）</label>'
      + '  <textarea id="allowPathsText" class="env-edit" style="height:100px;" spellcheck="false">' + escHtml(paths.join('\n')) + '</textarea>'
      + '</div>'
      + '<div class="row-actions" style="margin-top:var(--sp-2);">'
      + '<button type="button" class="btn btn--primary btn--sm" id="btnAllowSave">保存</button>'
      + '</div>'
      + '<div id="allowStatus" class="status-line"></div>';

    document.getElementById('selAllowMode').addEventListener('change', function() {
      const editor = document.getElementById('allowPathsEditor');
      if (editor) editor.style.display = this.value === 'whitelist' ? '' : 'none';
    });
    document.getElementById('btnAllowSave').addEventListener('click', async function() {
      const s = document.getElementById('allowStatus');
      if (!s) return;
      s.textContent = '保存中…';
      s.classList.remove('is-err');
      try {
        const newMode = document.getElementById('selAllowMode').value;
        const newPaths = document.getElementById('allowPathsText') ? document.getElementById('allowPathsText').value.split('\n').map(function(x) { return x.trim(); }).filter(Boolean) : [];
        const dr = await fetch('/api/ui/allowlist', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: newMode, paths: newPaths }) });
        if (!dr.ok) throw new Error((await dr.json()).detail || dr.statusText);
        s.textContent = '已保存。';
      } catch (e) { s.classList.add('is-err'); s.textContent = String(e); }
    });
  } catch (_) {}
}


async function loadGitRemoteConfig() {
  const section = document.getElementById('fieldsetGitRemote');
  if (!section) return;

  // ---- 默认远程配置 ----
  await _loadGitDefaults();

  // ---- SSH ----
  _bindGitSshEvents();

  // ---- HTTPS 凭据 ----
  _bindGitCredEvents();

  // ---- Git 代理 ----
  _loadGitProxy();
  _bindGitProxyEvents();
}

// =============================================
// Git 代理（带启用开关）
// =============================================
async function _loadGitProxy() {
  var chk = document.getElementById('chkGitProxyEnabled');
  var httpInp = document.getElementById('inpGitHttpProxy');
  var httpsInp = document.getElementById('inpGitHttpsProxy');
  if (!chk || !httpInp || !httpsInp) return;
  try {
    var r = await fetch('/api/ui/git/proxy-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method: 'get' })
    });
    var j = await r.json();
    if (j.ok) {
      chk.checked = !!j.enabled;
      httpInp.value = j.http || '';
      httpsInp.value = j.https || '';
      _toggleGitProxyForm(j.enabled);
    }
  } catch(_) {}
}

function _bindGitProxyEvents() {
  var saveBtn = document.getElementById('btnGitProxySave');
  if (!saveBtn || saveBtn.dataset.bound) return;
  saveBtn.dataset.bound = '1';
  saveBtn.addEventListener('click', _saveGitProxy);

  var clHttp = document.getElementById('btnGitHttpProxyClear');
  var clHttps = document.getElementById('btnGitHttpsProxyClear');
  if (clHttp) clHttp.addEventListener('click', function() {
    _clearGitProxy('http');
  });
  if (clHttps) clHttps.addEventListener('click', function() {
    _clearGitProxy('https');
  });

  var chk = document.getElementById('chkGitProxyEnabled');
  if (chk) {
    chk.addEventListener('change', function() {
      _toggleGitProxyForm(this.checked);
    });
  }
}

function _toggleGitProxyForm(show) {
  var form = document.getElementById('gitProxyForm');
  var inputs = form ? form.querySelectorAll('input[type="text"], button.btn--ghost') : [];
  if (form) form.style.opacity = show ? '1' : '0.5';
  inputs.forEach(function(el) {
    el.disabled = !show;
  });
}

async function _saveGitProxy() {
  var chk = document.getElementById('chkGitProxyEnabled');
  var httpInp = document.getElementById('inpGitHttpProxy');
  var httpsInp = document.getElementById('inpGitHttpsProxy');
  var status = document.getElementById('gitProxyStatus');
  if (!chk || !httpInp || !httpsInp || !status) return;
  status.textContent = '保存中...';

  var enabled = chk.checked;
  var httpVal = httpInp.value.trim();
  var httpsVal = httpsInp.value.trim();

  try {
    var r = await fetch('/api/ui/git/proxy-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        method: 'set',
        enabled: enabled,
        http: httpVal,
        https: httpsVal
      })
    });
    var j = await r.json();
    if (j.ok) {
      _toggleGitProxyForm(enabled);
      status.textContent = '✅ 代理配置已保存';
    } else {
      status.textContent = '❌ ' + (j.detail || '保存失败');
    }
    setTimeout(function() { status.textContent = ''; }, 3000);
  } catch(e) {
    status.textContent = '❌ ' + String(e);
  }
}

async function _clearGitProxy(scheme) {
  var inp = document.getElementById(scheme === 'http' ? 'inpGitHttpProxy' : 'inpGitHttpsProxy');
  var status = document.getElementById('gitProxyStatus');
  if (inp) inp.value = '';
  try {
    await fetch('/api/ui/git/proxy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method: 'unset', scheme: scheme })
    });
    if (status) { status.textContent = '✅ 已清除 git ' + scheme + ' 代理'; setTimeout(function() { status.textContent = ''; }, 2000); }
  } catch(e) {
    if (status) status.textContent = '❌ ' + String(e);
  }
}

/* ---------- 默认远程配置 ---------- */
async function _loadGitDefaults() {
  const chk = document.getElementById('chkGitDefaultEnabled');
  if (!chk) return;

  try {
    const r = await fetch('/api/ui/git/defaults');
    if (!r.ok) return;
    const j = await r.json();
    const def = j.defaults || {};
    chk.checked = !!def.enabled;
    _toggleGitDefaultsForm(def.enabled);

    if (def.provider) {
      document.getElementById('selGitDefaultProvider').value = def.provider;
      var credProv = document.getElementById('selConfigCredProvider');
      if (credProv) credProv.value = def.provider;
      _syncCredUrlFromProvider();
    }
    if (def.owner) document.getElementById('inpGitDefaultOwner').value = def.owner;
    if (def.protocol === 'https') {
      const el = document.querySelector('input[name="gitDefaultProtocol"][value="https"]');
      if (el) el.checked = true;
    }
    document.getElementById('chkGitDefaultAutoPush').checked = !!def.autoPush;

  } catch (_) {}

  if (!window._gitDefaultsBound) {
    window._gitDefaultsBound = true;
    chk.addEventListener('change', function() {
      _toggleGitDefaultsForm(this.checked);
    });
    var selProv = document.getElementById('selGitDefaultProvider');
    if (selProv) {
      selProv.addEventListener('change', function() {
        var credProv = document.getElementById('selConfigCredProvider');
        if (credProv) credProv.value = selProv.value;
        _syncCredUrlFromProvider();
        var sshBody = document.getElementById('gitConfigSshBody');
        if (sshBody && sshBody.style.display === 'block') _refreshGitSshStatus();
      });
    }
    var gds = document.getElementById('btnGitDefaultsSave');
    if (gds) gds.addEventListener('click', _saveGitDefaults);
  }
}

function _toggleGitDefaultsForm(show) {
  const form = document.getElementById('gitDefaultsForm');
  if (form) form.style.display = show ? 'block' : 'none';
}

async function _saveGitDefaults() {
  const status = document.getElementById('gitDefaultsStatus');
  if (!status) return;
  status.textContent = '保存中…';
  try {
    const body = {
      enabled: document.getElementById('chkGitDefaultEnabled').checked,
      provider: document.getElementById('selGitDefaultProvider').value,
      owner: document.getElementById('inpGitDefaultOwner').value.trim(),
      protocol: document.querySelector('input[name="gitDefaultProtocol"]:checked')?.value || 'ssh',
      autoPush: document.getElementById('chkGitDefaultAutoPush').checked,
    };
    const r = await fetch('/api/ui/git/defaults', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || '保存失败');
    status.textContent = '✅ 已保存';
    setTimeout(function() { status.textContent = ''; }, 3000);
  } catch (e) {
    status.textContent = '❌ ' + String(e);
  }
}

/* ---------- SSH 密钥管理 ---------- */
function _bindGitSshEvents() {
  if (window._gitSshBound) return;
  window._gitSshBound = true;

  var header = document.getElementById('gitConfigSshHeader');
  if (!header) return;

  header.addEventListener('click', function() {
    var body = document.getElementById('gitConfigSshBody');
    var icon = document.getElementById('gitConfigSshIcon');
    if (!body || !icon) return;
    var opening = body.style.display !== 'block';
    body.style.display = opening ? 'block' : 'none';
    icon.textContent = opening ? '▼' : '▶';
    if (opening) _refreshGitSshStatus();
  });

  var g = document.getElementById('btnConfigSshGen');
  var c = document.getElementById('btnConfigSshCat');
  var t = document.getElementById('btnConfigSshTest');
  if (g) g.addEventListener('click', function() { _gitSshAction('generate'); });
  if (c) c.addEventListener('click', function() { _gitSshAction('cat'); });
  if (t) t.addEventListener('click', function() { _gitSshAction('test'); });
}

async function _refreshGitSshStatus() {
  var el = document.getElementById('gitConfigSshStatus');
  if (!el) return;
  el.textContent = '检查中...';
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'ssh',
        args: 'status',
        provider: _gitProviderFromSelect('selGitDefaultProvider'),
      }),
    });
    var j = await r.json();
    el.innerHTML = _renderGitSshStatus(j);
    _applyGitSshActionState(j);
  } catch (e) { el.textContent = '❌ ' + String(e); }
}

function _renderGitSshStatus(j) {
  if (!j || typeof j !== 'object') return escHtml(String(j && j.result || '未知'));
  var parts = [];
  var connected = !!j.connected;
  var recommendation = String(j.recommendation || '');
  var title = connected
    ? '✅ SSH 已可用'
    : (recommendation === 'needs_platform_or_config'
      ? '⚠️ 已检测到密钥，但当前平台未连通'
      : (recommendation === 'generate_suggested' ? '❌ 未检测到可用 SSH 密钥' : '❔ 暂时无法判断 SSH 状态'));
  var host = escHtml(j.ssh_host || '');
  var auth = escHtml(j.auth_message || '');
  var bannerBg = connected
    ? 'rgba(34,197,94,0.12)'
    : (recommendation === 'generate_suggested' ? 'rgba(239,68,68,0.12)' : 'rgba(234,179,8,0.12)');
  var bannerIcon = connected ? '✅' : (recommendation === 'generate_suggested' ? '❌' : '⚠️');
  parts.push(
    '<div style="padding:6px 8px;border-radius:4px;background:' + bannerBg + ';margin-bottom:6px;">'
    + '<div><strong>' + title + '</strong></div>'
    + '<div style="margin-top:3px;">' + bannerIcon + ' <strong>' + host + '</strong>'
    + (auth ? ' — ' + auth : '')
    + '</div>'
    + '</div>'
  );
  var ids = j.identities || [];
  if (ids.length) {
    parts.push('<div style="margin:4px 0;"><strong>实际会尝试的密钥</strong> <span style="color:var(--text-muted);">(ssh -G)</span></div>');
    parts.push('<ul style="margin:0;padding-left:16px;">');
    ids.forEach(function(row) {
      var mark = row.private_exists ? '✓' : '✗';
      var line = mark + ' <code style="font-size:10px;">' + escHtml(row.private || '') + '</code>';
      if (row.public_exists) {
        line += '<br><span style="color:var(--text-muted);padding-left:14px;">公钥: '
          + escHtml(row.public || '') + '</span>';
      }
      parts.push('<li style="margin-bottom:4px;">' + line + '</li>');
    });
    parts.push('</ul>');
  } else {
    parts.push('<div style="color:var(--text-muted);">未解析到 identityfile（可能仅依赖 ssh-agent / 系统钥匙串）</div>');
  }
  var agent = j.agent_keys || [];
  if (agent.length) {
    parts.push('<div style="margin-top:6px;"><strong>ssh-agent</strong></div><ul style="margin:0;padding-left:16px;">');
    agent.slice(0, 5).forEach(function(ln) {
      parts.push('<li><code style="font-size:10px;">' + escHtml(ln) + '</code></li>');
    });
    parts.push('</ul>');
  }
  var rec = j.recommendation_text || j.result || '';
  if (rec) {
    var recStyle = connected
      ? 'color:var(--text-muted);'
      : (j.recommendation === 'generate_suggested' ? 'color:var(--text);' : 'color:#b45309;');
    parts.push('<div style="margin-top:8px;font-size:11px;' + recStyle + '">' + escHtml(rec) + '</div>');
  }
  return parts.join('');
}

function _setBtnStyle(btn, isPrimary) {
  if (!btn) return;
  btn.classList.remove('btn--primary', 'btn--ghost');
  btn.classList.add(isPrimary ? 'btn--primary' : 'btn--ghost');
}

function _applyGitSshActionState(j) {
  var btnGen = document.getElementById('btnConfigSshGen');
  var btnCat = document.getElementById('btnConfigSshCat');
  var btnTest = document.getElementById('btnConfigSshTest');
  if (!btnGen || !btnCat || !btnTest) return;

  btnGen.style.display = '';
  btnCat.style.display = '';
  btnTest.style.display = '';
  btnGen.textContent = '生成密钥';
  btnCat.textContent = '查看公钥';
  btnTest.textContent = '测试连接';

  var connected = !!(j && j.connected);
  var recommendation = String((j && j.recommendation) || '');
  if (connected) {
    _setBtnStyle(btnCat, true);
    _setBtnStyle(btnTest, false);
    _setBtnStyle(btnGen, false);
    btnCat.textContent = '查看并复制公钥';
    btnTest.textContent = '重新检测';
    btnGen.textContent = '仍要生成新密钥';
    return;
  }
  if (recommendation === 'needs_platform_or_config') {
    _setBtnStyle(btnCat, true);
    _setBtnStyle(btnTest, false);
    _setBtnStyle(btnGen, false);
    btnCat.textContent = '查看并复制公钥';
    btnTest.textContent = '重新检测';
    btnGen.style.display = 'none';
    return;
  }
  if (recommendation === 'generate_suggested') {
    _setBtnStyle(btnGen, true);
    _setBtnStyle(btnTest, false);
    _setBtnStyle(btnCat, false);
    btnGen.textContent = '生成 ed25519 密钥';
    btnTest.textContent = '重新检测';
    btnCat.style.display = 'none';
    return;
  }
  _setBtnStyle(btnTest, true);
  _setBtnStyle(btnCat, false);
  _setBtnStyle(btnGen, false);
  btnTest.textContent = '重新检测';
}

async function _gitSshAction(action, opts) {
  opts = opts || {};
  var output = document.getElementById('gitConfigSshOutput');
  if (!output) return;
  var provider = _gitProviderFromSelect('selGitDefaultProvider');
  if (action === 'generate' && !opts.force) {
    if (!confirm('生成新的 SSH 密钥（ed25519）？已有 ~/.ssh/id_ed25519 不会被覆盖。')) return;
  }
  output.textContent = '⏳ 执行中...';
  try {
    var payload = { command: 'ssh', args: action, provider: provider };
    if (action === 'generate' && opts.force) payload.force = true;
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    var j = await r.json();
    if (action === 'generate' && j.needs_confirm && !opts.force) {
      var msg = j.result || '当前 SSH 已可用，仍要生成新密钥吗？';
      if (confirm(msg)) {
        return _gitSshAction('generate', { force: true });
      }
      output.textContent = '已取消';
      return;
    }
    output.textContent = j.result || j.error || '完成';
    if (action === 'generate' || action === 'test') _refreshGitSshStatus();
    if (action === 'generate' && !j.error) {
      await _gitSshAction('cat', { fromGenerate: true });
    }
    if (action === 'cat' && j.result) {
      var pubMatch = j.result.match(/(ssh-\S+)/);
      if (pubMatch) {
        try {
          await navigator.clipboard.writeText(pubMatch[1]);
          output.textContent += opts.fromGenerate ? '\n📋 已自动复制新公钥。' : '\n📋 公钥已复制！';
        } catch (_) {}
      }
    }
  } catch (e) { output.textContent = '❌ ' + String(e); }
}

/* ---------- HTTPS 凭据管理 ---------- */
function _bindGitCredEvents() {
  if (window._gitCredBound) return;
  window._gitCredBound = true;

  var header = document.getElementById('gitConfigCredHeader');
  if (!header) return;

  header.addEventListener('click', function() {
    var body = document.getElementById('gitConfigCredBody');
    var icon = document.getElementById('gitConfigCredIcon');
    if (!body || !icon) return;
    var opening = body.style.display !== 'block';
    body.style.display = opening ? 'block' : 'none';
    icon.textContent = opening ? '▼' : '▶';
    if (opening) _refreshGitCredStatus();
  });

  var bAdd = document.getElementById('btnConfigCredAdd');
  var bCan = document.getElementById('btnConfigCredCancel');
  var bSav = document.getElementById('btnConfigCredSave');
  var bSho = document.getElementById('btnConfigCredShow');
  var bClr = document.getElementById('btnConfigCredClear');
  if (bAdd) bAdd.addEventListener('click', function() {
    var f = document.getElementById('gitConfigCredForm');
    var defProv = _gitProviderFromSelect('selGitDefaultProvider');
    var credProv = document.getElementById('selConfigCredProvider');
    if (credProv) credProv.value = defProv;
    _syncCredUrlFromProvider();
    if (f) f.style.display = 'block';
  });
  var credProvSel = document.getElementById('selConfigCredProvider');
  if (credProvSel) credProvSel.addEventListener('change', _syncCredUrlFromProvider);
  if (bCan) bCan.addEventListener('click', function() {
    var f = document.getElementById('gitConfigCredForm');
    if (f) f.style.display = 'none';
  });
  if (bSav) bSav.addEventListener('click', _saveGitCred);
  if (bSho) bSho.addEventListener('click', _showGitCred);
  if (bClr) bClr.addEventListener('click', _clearGitCred);
}

async function _refreshGitCredStatus() {
  var el = document.getElementById('gitConfigCredStatus');
  if (!el) return;
  el.textContent = '检查中...';
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'credential', action: 'show' }),
    });
    var j = await r.json();
    if (j.error && !j.result) {
      el.textContent = '❌ ' + j.error;
      return;
    }
    el.innerHTML = (j.result || '未知').replace(/\n/g, '<br>');
  } catch (e) { el.textContent = '❌ ' + String(e); }
}

async function _saveGitCred() {
  var url = document.getElementById('inpConfigCredUrl').value.trim();
  var user = document.getElementById('inpConfigCredUser').value.trim();
  var token = document.getElementById('inpConfigCredToken').value.trim();
  var provider = _gitProviderFromSelect('selConfigCredProvider');
  if (!url || !user || !token) { alert('请填写平台、用户名和 Token'); return; }
  var status = document.getElementById('gitConfigCredStatus');
  if (!status) return;
  status.textContent = '保存中...';
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'credential',
        action: 'store',
        url: url,
        provider: provider,
        username: user,
        token: token,
      }),
    });
    var j = await r.json();
    if (j.error && !j.result) {
      status.textContent = '❌ ' + j.error;
      return;
    }
    status.textContent = j.result || '✅ 已保存';
    document.getElementById('gitConfigCredForm').style.display = 'none';
    document.getElementById('inpConfigCredUser').value = '';
    document.getElementById('inpConfigCredToken').value = '';
    setTimeout(function() { status.textContent = ''; }, 3000);
  } catch (e) { status.textContent = '❌ ' + String(e); }
}

async function _showGitCred() {
  await _refreshGitCredStatus();
}

async function _clearGitCred() {
  if (!confirm('确定清除已配置的 Git HTTPS 凭据吗？')) return;
  var status = document.getElementById('gitConfigCredStatus');
  if (!status) return;
  status.textContent = '清除中...';
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'credential', action: 'clear' }),
    });
    var j = await r.json();
    status.textContent = j.result || j.error || '✅ 已清除';
    setTimeout(function() { status.textContent = ''; }, 3000);
  } catch (e) { status.textContent = '❌ ' + String(e); }
}

