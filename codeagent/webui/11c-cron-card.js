  editWrap.innerHTML = buildCronEditFormHTML(j);
  editWrap.appendChild(editStatus);
  var toggleEdit = function(show) { editWrap.style.display = show ? 'block' : 'none'; editStatus.textContent = ''; editStatus.classList.remove('is-err'); };
  // Click the card header to toggle edit
  header.style.cursor = 'pointer';
  header.addEventListener('click', function(e) {
    if (e.target.closest('.btn') || e.target.closest('.cron-card__actions')) return;
    toggleEdit(editWrap.style.display !== 'block');
  });

  // Store original job id so we can detect rename and delete old entry
  var origJobId = j.id;

  // Wire up mode switch + day pills
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
      var displayName = name.trim();
      if (!origJobId) { editStatus.textContent = '内部错误：缺少任务 id'; editStatus.classList.add('is-err'); return; }
      var kv = {
        id: origJobId,
        title: displayName,
        enabled: enabled,
        cron: freqToCron(freq),
        agent_id: agent || 'default',
        session_id: session || ('cron-' + origJobId),
        prompt: prompt,
        max_tool_rounds: maxRounds,
      };
      if (tz) kv.timezone = tz;
      if (projectId) kv.project_id = projectId;
      var r = await fetch('/api/ui/cron/job', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(kv) });
      var jr = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(jr.detail || r.statusText);
      editStatus.textContent = '已保存。';
      toggleEdit(false);
      await loadCronPanel();
    } catch (e) { editStatus.classList.add('is-err'); editStatus.textContent = String(e); }
  });
  if (editWrap.querySelector('.cron-cancel-btn')) {
    editWrap.querySelector('.cron-cancel-btn').addEventListener('click', function() { toggleEdit(false); });
  }
  wrap.appendChild(header); wrap.appendChild(editWrap);
  return wrap;
}

/** HTML for the edit form — natural language only, no raw CRON fields */
function buildCronEditFormHTML(j) {
  var f = parseCronToFreq(j.cron);
  return '<div class="cron-form-grid">'
    + '<div class="cron-form-full" style="display:flex;gap:var(--sp-4);align-items:start;">'
    + '  <div style="flex:1;"><label class="form-label">任务名称</label><input class="cron-fld-name" type="text" value="' + escAttr(j.title || j.id || '') + '" placeholder="例如：检查消息"/></div>'
    + '  <div style="width:80px;"><label class="form-label">启用</label><div style="margin-top:6px"><input class="cron-fld-enabled" type="checkbox" ' + (j.enabled !== false ? 'checked' : '') + '/></div></div>'
    + '</div>'
    + '<div class="cron-form-full"><label class="form-label">执行频率</label>'
    + '  <select class="cron-fld-mode md-select" style="max-width:100%;">'
    + CRON_FREQ_MODES.map(function(m) { return '<option value="' + m.id + '"' + (m.id === f.mode ? ' selected' : '') + '>' + m.label + '</option>'; }).join('')
    + '  </select>'
    + '</div>'
    /* interval minutes */
    + '<div class="cron-freq-block cron-freq-minutes' + (f.mode === 'minutes' ? '' : ' cron-freq-hidden') + '">'
    + '  <label class="form-label">间隔分钟数</label>'
    + '  <select class="cron-fld-interval md-select" style="max-width:100%;">'
    + [5,10,15,20,30,45].map(function(v) { return '<option value="' + v + '"' + ((parseInt(f.interval) || 30) === v ? ' selected' : '') + '>每 ' + v + ' 分钟</option>'; }).join('')
    + '  </select>'
    + '</div>'
    /* interval hours */
    + '<div class="cron-freq-block cron-freq-hours' + (f.mode === 'hours' ? '' : ' cron-freq-hidden') + '">'
    + '  <label class="form-label">间隔小时数</label>'
    + '  <select class="cron-fld-interval md-select" style="max-width:100%;">'
    + [1,2,3,4,6,8,12].map(function(v) { return '<option value="' + v + '"' + ((parseInt(f.interval) || 1) === v ? ' selected' : '') + '>每 ' + v + ' 小时</option>'; }).join('')
    + '  </select>'
    + '  <div style="margin-top:var(--sp-2);"><label class="form-label">在每小时的第几分钟</label>'
    + '  <select class="cron-fld-minute md-select" style="max-width:100%;">'
    + [0,5,10,15,20,25,30,35,40,45,50,55].map(function(v) { return '<option value="' + v + '"' + (parseInt(f.minute || '0') === v ? ' selected' : '') + '>' + v + ' 分</option>'; }).join('')
    + '  </select></div>'
    + '</div>'
    /** daily/weekly/monthly: time picker */
    + '<div class="cron-freq-block cron-freq-daily cron-freq-weekly cron-freq-monthly' + (f.mode === 'daily' || f.mode === 'weekly' || f.mode === 'monthly' ? '' : ' cron-freq-hidden') + '">'
    + '  <label class="form-label">执行时间</label>'
    + '  <div style="display:flex;gap:var(--sp-2);align-items:center;">'
    + '    <select class="cron-fld-hour md-select" style="width:80px;">' + hoursOptions(f.hour) + '</select><span>:</span>'
    + '    <select class="cron-fld-minute md-select" style="width:80px;">' + minutesOptions(f.minute) + '</select>'
    + '  </div>'
    + '</div>'
    /* weekly day picker */
    + '<div class="cron-freq-block cron-freq-weekly' + (f.mode === 'weekly' ? '' : ' cron-freq-hidden') + '">'
    + '  <label class="form-label">选择星期</label>'
    + '  <div style="display:flex;flex-wrap:wrap;gap:var(--sp-1);">'
    + DAY_NAMES.map(function(dn, i) { return '<label class="cron-day-pill' + (f.dayOfWeek === String(i) ? ' cron-day-pill--on' : '') + '" data-day="' + i + '">' + dn + '</label>'; }).join('')
    + '  </div>'
    + '  <input class="cron-fld-dow" type="hidden" value="' + escAttr(f.dayOfWeek) + '"/>'
    + '</div>'
    /* monthly day picker */
    + '<div class="cron-freq-block cron-freq-monthly' + (f.mode === 'monthly' ? '' : ' cron-freq-hidden') + '">'
    + '  <label class="form-label">每月几号</label>'
    + '  <select class="cron-fld-dom md-select" style="max-width:100%;">'
    + [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28].map(function(v) { return '<option value="' + v + '"' + (parseInt(f.dayOfMonth || '1') === v ? ' selected' : '') + '>' + v + ' 日</option>'; }).join('')
    + '  </select>'
    + '</div>'
    + '<div><label class="form-label">Agent</label><input class="cron-fld-agent" type="text" value="' + escAttr(j.agent_id || 'default') + '" placeholder="default"/></div>'
    + '<div><label class="form-label">项目 ID（可选）</label><input class="cron-fld-project" type="text" value="' + escAttr(j.project_id || '') + '" placeholder="留空则无项目归属"/></div>'
    + '<div><label class="form-label">Session ID（可选）</label><input class="cron-fld-session" type="text" value="' + escAttr(j.session_id || '') + '" placeholder="自动生成"/></div>'
    + '<div class="cron-form-full"><label class="form-label">Prompt（发送给 Agent 的消息）</label>'
    + '<textarea class="cron-fld-prompt" placeholder="【定时任务】输入 prompt…">' + escAttr(j.prompt || '') + '</textarea></div>'
    + '<div><label class="form-label">时区（可选，默认 UTC）</label><input class="cron-fld-tz" type="text" value="' + escAttr(j.timezone || '') + '" placeholder="Asia/Shanghai"/></div>'
    + '<div><label class="form-label">最大工具调用轮数</label><input class="cron-fld-rounds" type="number" min="1" max="32" value="' + (j.max_tool_rounds || 12) + '"/></div>'
    + '<div class="cron-form-full row-actions" style="margin-top:0;">'
    + '  <button type="button" class="btn btn--primary btn--sm cron-save-btn">保存</button>'
    + '  <button type="button" class="btn btn--subtle btn--sm cron-cancel-btn">取消</button>'
    + '</div>'
    + '</div>';
}

/** Read frequency settings from an edit form into a descriptor */
function readFreqFromForm(el) {
  var mode = el.querySelector('.cron-fld-mode').value;
