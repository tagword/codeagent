// ---------------- Config paths & allowlist ----------------

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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

    if (def.provider) document.getElementById('selGitDefaultProvider').value = def.provider;
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
      body: JSON.stringify({ command: 'ssh', args: 'status' }),
    });
    var j = await r.json();
    el.innerHTML = (j.result || '未知').replace(/\n/g, '<br>');
  } catch (e) { el.textContent = '❌ ' + String(e); }
}

async function _gitSshAction(action) {
  var output = document.getElementById('gitConfigSshOutput');
  if (!output) return;
  if (action === 'generate' && !confirm('生成新的 SSH 密钥（ed25519）？已有密钥不会被覆盖。')) return;
  output.textContent = '⏳ 执行中...';
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'ssh', args: action }),
    });
    var j = await r.json();
    output.textContent = j.result || j.error || '完成';
    if (action === 'generate' || action === 'test') _refreshGitSshStatus();
    if (action === 'cat' && j.result) {
      // 尝试复制公钥
      var pubMatch = j.result.match(/(ssh-\S+)/);

      if (pubMatch) {
        try { await navigator.clipboard.writeText(pubMatch[1]); output.textContent += '\n📋 公钥已复制！'; } catch(_) {}
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
    if (f) f.style.display = 'block';
  });
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
      body: JSON.stringify({ command: 'credential', args: 'show' }),
    });
    var j = await r.json();
    el.innerHTML = (j.result || '未知').replace(/\n/g, '<br>');
  } catch (e) { el.textContent = '❌ ' + String(e); }
}

async function _saveGitCred() {
  var url = document.getElementById('inpConfigCredUrl').value.trim();
  var user = document.getElementById('inpConfigCredUser').value.trim();
  var token = document.getElementById('inpConfigCredToken').value.trim();
  if (!url || !user || !token) { alert('请填写 URL、用户名和 Token'); return; }
  var status = document.getElementById('gitConfigCredStatus');
  if (!status) return;
  status.textContent = '保存中...';
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'credential', args: 'store ' + url + ' ' + user + ' ' + token }),
    });
    var j = await r.json();
    status.textContent = j.result || '✅ 已保存';
    document.getElementById('gitConfigCredForm').style.display = 'none';
    document.getElementById('inpConfigCredUrl').value = '';
    document.getElementById('inpConfigCredUser').value = '';
    document.getElementById('inpConfigCredToken').value = '';
    setTimeout(function() { status.textContent = ''; }, 3000);
  } catch (e) { status.textContent = '❌ ' + String(e); }
}

async function _showGitCred() {
  var status = document.getElementById('gitConfigCredStatus');
  if (!status) return;
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'credential', args: 'show' }),
    });
    var j = await r.json();
    status.innerHTML = (j.result || '无').replace(/\n/g, '<br>');
  } catch (e) { status.textContent = '❌ ' + String(e); }
}

async function _clearGitCred() {
  if (!confirm('确定清除所有 Git 凭据吗？')) return;
  var status = document.getElementById('gitConfigCredStatus');
  if (!status) return;
  status.textContent = '清除中...';
  try {
    var r = await fetch('/api/ui/git', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'credential', args: 'clear' }),
    });
    var j = await r.json();
    status.textContent = j.result || '✅ 已清除';
    setTimeout(function() { status.textContent = ''; }, 3000);
  } catch (e) { status.textContent = '❌ ' + String(e); }
}

