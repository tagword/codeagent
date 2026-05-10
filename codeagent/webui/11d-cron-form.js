  var interval = parseInt(el.querySelector('.cron-fld-interval').value) || 30;
  var hour = el.querySelector('.cron-fld-hour') ? el.querySelector('.cron-fld-hour').value : '*';
  var minute = el.querySelector('.cron-fld-minute') ? el.querySelector('.cron-fld-minute').value : '0';
  var dow = el.querySelector('.cron-fld-dow') ? el.querySelector('.cron-fld-dow').value : '*';
  var dom = el.querySelector('.cron-fld-dom') ? el.querySelector('.cron-fld-dom').value : '*';
  return { mode: mode, interval: interval, hour: hour, minute: minute, dayOfWeek: dow, dayOfMonth: dom };
}

/** Wire up mode-switching and day-picker interactions */
function wireCronFormEvents(el) {
  var modeSelect = el.querySelector('.cron-fld-mode');
  if (!modeSelect) return;
  modeSelect.addEventListener('change', function() {
    var mode = this.value;
    el.querySelectorAll('.cron-freq-block').forEach(function(b) { b.classList.add('cron-freq-hidden'); });
    el.querySelectorAll('.cron-freq-' + mode).forEach(function(b) { b.classList.remove('cron-freq-hidden'); });
  });
  el.querySelectorAll('.cron-day-pill').forEach(function(pill) {
    pill.addEventListener('click', function() {
      el.querySelectorAll('.cron-day-pill').forEach(function(p) { p.classList.remove('cron-day-pill--on'); });
      this.classList.add('cron-day-pill--on');
      var dowInput = el.querySelector('.cron-fld-dow');
      if (dowInput) dowInput.value = this.getAttribute('data-day') || '1';
    });
  });
}

function hoursOptions(current) {
  var opts = '';
  for (var i = 0; i < 24; i++) {
    var sel = (parseInt(current) === i || (current === '*' && i === 8)) ? ' selected' : '';
    opts += '<option value="' + i + '"' + sel + '>' + (i < 10 ? '0' : '') + i + ':00</option>';
  }
  return opts;
}

function minutesOptions(current) {
  var opts = '';
  var vals = [0,5,10,15,20,25,30,35,40,45,50,55];
  for (var i = 0; i < vals.length; i++) {
    var v = vals[i];
    var sel = (parseInt(current) === v || (current === '*' && v === 0)) ? ' selected' : '';
    opts += '<option value="' + v + '"' + sel + '>' + (v < 10 ? '0' : '') + v + '</option>';
  }
  return opts;
}

// ---- Show new cron job form ----
function showNewCronJobForm() {
  var list = document.getElementById('cronJobList');
  if (!list) return;
  var existing = list.querySelector('.cron-card-wrap.is-new');
  if (existing) { existing.remove(); }
  var wrap = document.createElement('div'); wrap.className = 'cron-card-wrap is-new';
  var editWrap = document.createElement('div'); editWrap.className = 'cron-edit-wrap'; editWrap.style.display = 'block';
  var editStatus = document.createElement('div'); editStatus.className = 'status-line';
  var emptyJob = { id: '', enabled: true, cron: '0 8 * * *', agent_id: 'default', session_id: '', prompt: '', timezone: '', max_tool_rounds: 12 };
  editWrap.innerHTML = buildCronEditFormHTML(emptyJob);
  editWrap.appendChild(editStatus);
  editWrap.querySelector('.cron-cancel-btn').addEventListener('click', function() { wrap.remove(); });
  wireCronFormEvents(editWrap);
  editWrap.querySelector('.cron-save-btn').addEventListener('click', async function() {
    var freq = readFreqFromForm(editWrap);
    var name = editWrap.querySelector('.cron-fld-name').value.trim();
    var agent = editWrap.querySelector('.cron-fld-agent').value.trim();
    var session = editWrap.querySelector('.cron-fld-session').value.trim();
    var prompt = editWrap.querySelector('.cron-fld-prompt').value.trim();
    var tz = editWrap.querySelector('.cron-fld-tz').value.trim();
    var maxRounds = parseInt(editWrap.querySelector('.cron-fld-rounds').value) || 12;
    var enabled = editWrap.querySelector('.cron-fld-enabled').checked;
    var projectId = editWrap.querySelector('.cron-fld-project').value.trim();
    if (!name) { editStatus.textContent = '任务名称不能为空'; editStatus.classList.add('is-err'); return; }
    if (!prompt) { editStatus.textContent = 'Prompt 不能为空'; editStatus.classList.add('is-err'); return; }
    editStatus.textContent = '保存中…'; editStatus.classList.remove('is-err');
    try {
      var title = name.trim();
      var jobId = cronSafeJobId(title);
      var kv = { id: jobId, title: title, enabled: enabled, cron: freqToCron(freq), agent_id: agent || 'default', session_id: session || ('cron-' + jobId), prompt: prompt, max_tool_rounds: maxRounds };
      if (tz) kv.timezone = tz;
      if (projectId) kv.project_id = projectId;
      var r = await fetch('/api/ui/cron/job', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(kv) });
      var jr = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(jr.detail || jr.statusText);
      wrap.remove();
      await loadCronPanel();
    } catch (e) { editStatus.classList.add('is-err'); editStatus.textContent = String(e); }
  });
  wrap.appendChild(editWrap);
  if (list.firstChild) { list.insertBefore(wrap, list.firstChild); } else { list.appendChild(wrap); }
}

function showCronError(msg) {
  const st = document.getElementById('cronUiStatus');
  if (st) { st.classList.add('is-err'); st.textContent = msg; }
}

// ---- Event bindings ----
document.getElementById('btnCronRefresh') && document.getElementById('btnCronRefresh').addEventListener('click', function() { loadCronPanel(); });
document.getElementById('btnCronJobAdd') && document.getElementById('btnCronJobAdd').addEventListener('click', showNewCronJobForm);

// ---------------- Chat session env config (structured UI) ----------------

/** Cache of LLM presets for the summarizer select dropdown */
let _summarizerPresetsCache = null;
