/* ================================================================
 * 11-config.js
 *   - Config page: codeagent.env raw editor
 *   - Chat session env config (structured UI controls)
 *   - Cron (codeagent.cron.json) card-based UI (like LLM Presets)
 *   - LLM Presets management (multi-model)
 *
 * Depends on (provided by earlier files):
 *   agentId, refreshChatModelSelect
 * ================================================================ */

// ---------------- Cron card-based UI (natural language, no raw CRON) ----------------

/** Frequency modes: how the user picks schedule in natural language */
const CRON_FREQ_MODES = [
  { id: 'minutes',  label: '每 N 分钟' },
  { id: 'hours',    label: '每 N 小时' },
  { id: 'daily',    label: '每天固定时间' },
  { id: 'weekly',   label: '每周固定时间' },
  { id: 'monthly',  label: '每月固定日期' },
];

const DAY_NAMES = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

/** Parse a cron expression into a friendly frequency descriptor */
function parseCronToFreq(expr) {
  if (!expr) return { mode: 'daily', minute: '0', hour: '8', interval: 30, dayOfWeek: '1', dayOfMonth: '1' };
  var parts = (expr || '').trim().split(/\s+/);
  while (parts.length < 5) parts.push('*');
  var min = parts[0], hour = parts[1], dom = parts[2], mon = parts[3], dow = parts[4];
  var result = { minute: min, hour: hour, interval: 30, dayOfWeek: dow, dayOfMonth: dom };

  if (hour === '*' && dom === '*' && mon === '*' && dow === '*' && min.indexOf('/') !== -1) {
    result.mode = 'minutes';
    result.interval = parseInt(min.split('/')[1]) || 30;
  } else if (min !== '*' && dom === '*' && mon === '*' && dow === '*' && hour.indexOf('/') !== -1) {
    result.mode = 'hours';
    result.interval = parseInt(hour.split('/')[1]) || 1;
    result.minute = min;
  } else if (hour !== '*' && dom === '*' && mon === '*' && dow === '*') {
    result.mode = 'daily';
    result.minute = min === '*' ? '0' : min;
    result.hour = hour === '*' ? '8' : hour;
  } else if (hour !== '*' && mon === '*' && dow !== '*' && dom === '*') {
    result.mode = 'weekly';
    result.minute = min === '*' ? '0' : min;
    result.hour = hour === '*' ? '8' : hour;
    result.dayOfWeek = dow;
  } else if (hour !== '*' && dom !== '*' && mon === '*' && dow === '*') {
    result.mode = 'monthly';
    result.minute = min === '*' ? '0' : min;
    result.hour = hour === '*' ? '8' : hour;
    result.dayOfMonth = dom;
  } else {
    result.mode = 'daily';
    result.minute = min === '*' ? '0' : min;
    result.hour = hour === '*' ? '8' : hour;
  }
  return result;
}

/** Convert frequency descriptor back to a standard 5-field cron */
function freqToCron(f) {
  switch (f.mode) {
    case 'minutes':
      var iv = parseInt(f.interval) || 30;
      return '*/' + iv + ' * * * *';
    case 'hours':
      var ih = parseInt(f.interval) || 1;
      return (f.minute || '0') + ' */' + ih + ' * * *';
    case 'daily':
      return (f.minute || '0') + ' ' + (f.hour || '8') + ' * * *';
    case 'weekly':
      return (f.minute || '0') + ' ' + (f.hour || '8') + ' * * ' + (f.dayOfWeek || '1');
    case 'monthly':
      return (f.minute || '0') + ' ' + (f.hour || '8') + ' ' + (f.dayOfMonth || '1') + ' * *';
    default:
      return '0 8 * * *';
  }
}

/** Describe a cron expression in full Chinese */
function describeCron(expr) {
  if (!expr) return '未设置';
  var f = parseCronToFreq(expr);
  var timeStr = (f.hour || '8') + ':' + ((f.minute || '0').length < 2 ? '0' : '') + (f.minute || '0');
  switch (f.mode) {
    case 'minutes': return '每 ' + (parseInt(f.interval) || 30) + ' 分钟执行一次';
    case 'hours':   return '每 ' + (parseInt(f.interval) || 1) + ' 小时（' + f.minute + ' 分）执行一次';
    case 'daily':   return '每天 ' + timeStr + ' 执行';
    case 'weekly':  return '每' + (DAY_NAMES[parseInt(f.dayOfWeek)] || '周' + f.dayOfWeek) + ' ' + timeStr + ' 执行';
    case 'monthly': return '每月 ' + f.dayOfMonth + ' 日 ' + timeStr + ' 执行';
    default:        return '每天 ' + timeStr + ' 执行';
  }
}

/**
 * Stable ASCII id for codeagent.cron.json / APScheduler.
 * Pure CJK names become cron-<timestamp>-<rand>; mixed names keep Latin slug.
 * Display text should use ``title`` (see save payload).
 */
function cronSafeJobId(displayName) {
  var s = String(displayName || '').trim();
  var slug = s.replace(/[^a-zA-Z0-9_-]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '').toLowerCase();
  if (!slug || /^_+$/.test(slug)) {
    return 'cron-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
  }
  if (slug.charAt(0) === '_') {
    return 'job-' + slug.replace(/^_+/, '');
  }
  return slug;
}

// ---- Global state ----
let cronGlobalEnabled = false;

async function loadCronPanel() {
