/* ================================================================
 * 12-plugins.js
 *   - System-prompt MD file list: click to edit inline (no toggles).
 *
 * Depends on (from earlier files): agentId
 * ================================================================ */

const mdFileList = document.getElementById('mdFileList');
const mdFileStatus = document.getElementById('mdFileStatus');

async function loadMdFiles() {
  if (!mdFileList || !mdFileStatus) return;
  mdFileStatus.textContent = '加载中…';
  mdFileStatus.classList.remove('is-err');
  try {
    // Get the list of config filenames from the plugins endpoint
    const r = await fetch('/api/ui/plugins');
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    const names = j.config_filenames || [];
    mdFileList.innerHTML = '';
    if (names.length === 0) {
      mdFileList.innerHTML = '<div class="cron-empty">暂无配置文件。</div>';
      mdFileStatus.textContent = '';
      return;
    }
    names.forEach(function(name) {
      mdFileList.appendChild(buildMdFileCard(name));
    });
    mdFileStatus.textContent = '';
  } catch (e) {
    mdFileStatus.classList.add('is-err');
    mdFileStatus.textContent = String(e);
  }
}

function buildMdFileCard(name) {
  var wrap = document.createElement('div'); wrap.className = 'cron-card-wrap';

  var header = document.createElement('div'); header.className = 'cron-card';
  var info = document.createElement('div'); info.className = 'cron-card__info';
  var nameRow = document.createElement('div'); nameRow.className = 'cron-card__name';
  nameRow.textContent = name;
  info.appendChild(nameRow);
  header.appendChild(info);
  header.style.cursor = 'pointer';

  var editWrap = document.createElement('div'); editWrap.className = 'cron-edit-wrap'; editWrap.style.display = 'none';
  var editStatus = document.createElement('div'); editStatus.className = 'status-line';
  var textarea = document.createElement('textarea');
  textarea.className = 'skill-fld-body';
  textarea.spellcheck = false;
  textarea.style.cssText = 'height:300px;font-family:var(--font-mono);font-size:13px;width:100%;padding:var(--sp-2);border:1px solid var(--border);border-radius:var(--r-sm);background:var(--bg);color:var(--text);resize:vertical;';
  textarea.placeholder = '加载中…';
  editWrap.appendChild(textarea);

  var actionsRow = document.createElement('div');
  actionsRow.className = 'row-actions';
  actionsRow.style.marginTop = 'var(--sp-2)';

  var btnSave = document.createElement('button');
  btnSave.type = 'button'; btnSave.className = 'btn btn--primary btn--sm';
  btnSave.textContent = '保存';
  actionsRow.appendChild(btnSave);

  var btnCancel = document.createElement('button');
  btnCancel.type = 'button'; btnCancel.className = 'btn btn--subtle btn--sm';
  btnCancel.textContent = '取消';
  actionsRow.appendChild(btnCancel);

  editWrap.appendChild(actionsRow);
  editWrap.appendChild(editStatus);

  var toggleEdit = function(show) {
    editWrap.style.display = show ? 'block' : 'none';
    editStatus.textContent = '';
    editStatus.classList.remove('is-err');
  };

  // Click header to toggle edit
  header.addEventListener('click', function(e) {
    if (e.target.closest('.btn')) return;
    var opening = editWrap.style.display !== 'block';
    toggleEdit(opening);
    if (opening) {
      loadMdFileContent(name, textarea, editStatus);
    }
  });

  btnCancel.addEventListener('click', function() { toggleEdit(false); });
  btnSave.addEventListener('click', async function() {
    var content = textarea.value;
    editStatus.textContent = '保存中…';
    editStatus.classList.remove('is-err');
    try {
      var sr = await fetch('/api/ui/md/' + encodeURIComponent(name) + '?agent_id=' + encodeURIComponent(agentId), {
        method: 'POST', headers: { 'Content-Type': 'text/plain; charset=utf-8' }, body: content
      });
      var sj = await sr.json().catch(function() { return {}; });
      if (!sr.ok) throw new Error(sj.detail || sr.statusText);
      editStatus.textContent = sj.hint || '已保存。';
    } catch (e) { editStatus.classList.add('is-err'); editStatus.textContent = String(e); }
  });

  wrap.appendChild(header); wrap.appendChild(editWrap);
  return wrap;
}

async function loadMdFileContent(name, textarea, statusEl) {
  try {
    var r = await fetch('/api/ui/md/' + encodeURIComponent(name) + '?agent_id=' + encodeURIComponent(agentId));
    var j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    textarea.value = j.content || '';
    if (statusEl) statusEl.textContent = j.exists ? '' : '（文件尚不存在，保存后将自动创建）';
  } catch (e) {
    textarea.value = '';
    if (statusEl) { statusEl.classList.add('is-err'); statusEl.textContent = String(e); }
  }
}
