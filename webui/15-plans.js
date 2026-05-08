/* ================================================================
 * 15-plans.js — Plan 面板 UI
 *   - 与 todo-panel 互斥（打开一个自动关闭另一个）
 *   - 显示当前项目的 *-plan.md 文件列表
 *   - 点击展开/收起内容预览
 *   - 监听 project-changed 事件自动刷新
 * ================================================================ */

(function() {

const btnToggle = document.getElementById('btnTogglePlans');
const planPanel = document.getElementById('planPanel');
const planList = document.getElementById('planList');
const planStatus = document.getElementById('planStatus');
const btnRefresh = document.getElementById('btnPlanRefresh');

if (!btnToggle || !planPanel || !planList) {
  return;
}

// ---- 生命周期控制 ---- //

// 用实际 DOM display 状态判断，不依赖内部布尔变量。
// 这样即使被对方面板互斥关闭，下次点击也能正确打开。
function planIsVisible() {
  return planPanel.style.display === 'flex';
}

try {
  if (localStorage.getItem('oa_plan_panel_open') === '1') {
    // 初始化互斥：如果待办已打开，不覆盖
    var todoPanel = document.getElementById('todoPanel');
    if (todoPanel && todoPanel.style.display === 'flex') {
      // 待办已开 → 忽略 localStorage，自己不打开
    } else {
      planPanel.style.display = 'flex';
      btnToggle.classList.add('is-active');
      setTimeout(refreshPlans, 150);
    }
  }
} catch (_) {}

// ---- Toggle: 打开 Plan 面板时关闭 Todo 面板（互斥） ---- //

btnToggle.addEventListener('click', function() {
  var opening = !planIsVisible();
  planPanel.style.display = opening ? 'flex' : 'none';
  btnToggle.classList.toggle('is-active', opening);
  try { localStorage.setItem('oa_plan_panel_open', opening ? '1' : '0'); } catch (_) {}

  // 互斥：打开 Plan 时自动关闭 Todo
  if (opening) {
    var todoP = document.getElementById('todoPanel');
    var todoB = document.getElementById('btnToggleTodos');
    if (todoP && todoP.style.display !== 'none') {
      todoP.style.display = 'none';
      if (todoB) todoB.classList.remove('is-active');
      try { localStorage.setItem('oa_todo_panel_open', '0'); } catch (_) {}
    }
    refreshPlans();
  }
});

if (btnRefresh) {
  btnRefresh.addEventListener('click', refreshPlans);
}

// ---- 监听项目切换 ---- //

document.addEventListener('project-changed', function() {
  if (planIsVisible()) refreshPlans();
});

// ---- API ---- //

async function fetchPlans() {
  var pid = typeof projectId !== 'undefined' ? (projectId || '') : '';
  if (!pid) return [];
  try {
    var r = await fetch('/api/ui/projects/plans?project_id=' + encodeURIComponent(pid));
    if (!r.ok) return [];
    var j = await r.json();
    return j.plans || [];
  } catch (_) { return []; }
}

// ---- 渲染 ---- //

async function refreshPlans() {
  var plans = await fetchPlans();
  if (!planList) return;
  planList.innerHTML = '';

  if (!plans || plans.length === 0) {
    planList.innerHTML = '<div class="plan-empty">当前项目暂无规划文档。<br/>Agent 在规划项目时会自动生成 <code>*-plan.md</code> 文件。</div>';
    if (planStatus) planStatus.textContent = '';
    return;
  }

  if (planStatus) planStatus.textContent = plans.length + ' 个文件';

  plans.forEach(function(p) {
    planList.appendChild(buildPlanCard(p));
  });
}

function buildPlanCard(plan) {
  var wrap = document.createElement('div');
  wrap.className = 'plan-card';

  // ---- Header (clickable) ---- //
  var header = document.createElement('div');
  header.className = 'plan-card__header';

  var icon = document.createElement('span');
  icon.className = 'plan-card__icon';
  icon.textContent = '📄';
  icon.style.fontSize = '16px';

  var info = document.createElement('div');
  info.className = 'plan-card__info';

  var nameEl = document.createElement('div');
  nameEl.className = 'plan-card__name';
  nameEl.textContent = plan.name;

  var meta = document.createElement('div');
  meta.className = 'plan-card__meta';
  meta.textContent = formatRelativeTime(plan.modified_at) + (plan.size ? ' · ' + formatSize(plan.size) : '');

  info.appendChild(nameEl);
  info.appendChild(meta);

  var arrow = document.createElement('span');
  arrow.className = 'plan-card__arrow';
  arrow.textContent = '\u25B6'; // ▶

  header.appendChild(icon);
  header.appendChild(info);
  header.appendChild(arrow);
  wrap.appendChild(header);

  // ---- Body (collapsible) ---- //
  var bodyWrap = document.createElement('div');
  bodyWrap.className = 'plan-card__body-wrap';

  var body = document.createElement('div');
  body.className = 'plan-card__body';
  body.textContent = plan.content || '';
  bodyWrap.appendChild(body);
  wrap.appendChild(bodyWrap);

  // ---- Toggle ---- //
  var isOpen = false;
  header.addEventListener('click', function() {
    isOpen = !isOpen;
    bodyWrap.classList.toggle('is-open', isOpen);
    arrow.classList.toggle('is-open', isOpen);
  });

  return wrap;
}

// ---- 工具函数 ---- //

function formatRelativeTime(epochSec) {
  if (!epochSec) return '';
  var diffMs = Date.now() - (epochSec * 1000);
  var diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 10) return '刚刚';
  if (diffSec < 60) return diffSec + '秒前';
  var diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return diffMin + '分钟前';
  var diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return diffHr + '小时前';
  var diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return diffDay + '天前';
  var d = new Date(epochSec * 1000);
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB';
  return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
}

})();
