#!/usr/bin/env node
/**
 * cron 卡片「执行时间」选项回归测试
 * 从真实源文件拼接运行（与浏览器加载顺序一致），验证：
 *  P1: 非档位值回显不失真（分钟/间隔分钟/间隔小时/每月日期）
 *  P2: 每小时整点/每分钟解析、dow 范围/列表描述
 *  P3: 小时下拉显示文本
 * 常规值行为不变（回归保护）
 */
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const STATIC = '/home/u2/agent/codeagent/codeagent/web/static';
const FILES = ['00-utils.js', '11a-cron-parse.js', '11b-cron-panel.js', '11c-cron-card.js', '11d-cron-form.js'];
const src = FILES.map(f => fs.readFileSync(path.join(STATIC, f), 'utf8')).join('\n;\n');

// mock 浏览器环境（顶层仅 getElementById 短路；fetch/confirm 在函数体内不会执行）
const sandbox = {
  console,
  document: { getElementById: () => null },
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  confirm: () => true,
  alert: () => {},
  setTimeout, clearTimeout, Date, Math, parseInt, JSON, encodeURIComponent,
};
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'cron-bundle.js' });

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (extra !== undefined ? '  → ' + extra : '')); }
}
const { parseCronToFreq, freqToCron, describeCron, describeDow, dowExprMatches,
        hoursOptions, minutesOptions, intervalMinutesOptions, intervalHoursOptions, domOptions } = sandbox;

function roundtrip(expr) { // 模拟：解析 → 表单回显 → 用户不改直接保存
  const f = parseCronToFreq(expr);
  return freqToCron(f);
}

console.log('== P1: 非档位值回显不失真 ==');
check('每天 9:07 (7 9 * * *) 回存不变', roundtrip('7 9 * * *') === '7 9 * * *', roundtrip('7 9 * * *'));
check('minutesOptions("7") 含选中 7', minutesOptions('7').includes('value="7" selected'), minutesOptions('7').match(/selected/g));
check('每 2 分钟 (*/2 * * * *) 回存不变', roundtrip('*/2 * * * *') === '*/2 * * * *', roundtrip('*/2 * * * *'));
check('intervalMinutesOptions("2") 含选中 2', intervalMinutesOptions('2').includes('value="2" selected'));
check('每 5 小时 (0 */5 * * *) 回存不变', roundtrip('0 */5 * * *') === '0 */5 * * *', roundtrip('0 */5 * * *'));
check('intervalHoursOptions("5") 含选中 5', intervalHoursOptions('5').includes('value="5" selected'));
check('每月 31 日 (0 8 31 * *) 回存不变', roundtrip('0 8 31 * *') === '0 8 31 * *', roundtrip('0 8 31 * *'));
check('每月 29 日 (0 8 29 * *) 回存不变', roundtrip('0 8 29 * *') === '0 8 29 * *');
check('domOptions("31") 含选中 31', domOptions('31').includes('value="31" selected'));

console.log('== P2: 解析与描述 ==');
check('0 * * * * = 每小时整点 → hours/1', (f => f.mode === 'hours' && f.interval === 1 && f.minute === '0')(parseCronToFreq('0 * * * *')), JSON.stringify(parseCronToFreq('0 * * * *')));
check('0 * * * * 描述正确', describeCron('0 * * * *') === '每 1 小时（0 分）执行一次', describeCron('0 * * * *'));
check('0 * * * * 回存不变', roundtrip('0 * * * *') === '0 * * * *', roundtrip('0 * * * *'));
check('* * * * * = 每分钟 → minutes/1', (f => f.mode === 'minutes' && f.interval === 1)(parseCronToFreq('* * * * *')), JSON.stringify(parseCronToFreq('* * * * *')));
check('* * * * * 描述正确', describeCron('* * * * *') === '每 1 分钟执行一次', describeCron('* * * * *'));
check('1-5 范围描述', describeDow('1-5') === '周一至周五', describeDow('1-5'));
check('1,3,5 列表描述', describeDow('1,3,5') === '周一、周三、周五', describeDow('1,3,5'));
check('7 = 周日', describeDow('7') === '周日', describeDow('7'));
check('dowExprMatches 范围 1-5', dowExprMatches('1-5', 1) && dowExprMatches('1-5', 5) && !dowExprMatches('1-5', 0) && !dowExprMatches('1-5', 6));
check('dowExprMatches 列表 1,3,5', dowExprMatches('1,3,5', 3) && !dowExprMatches('1,3,5', 2));
check('dowExprMatches 单值 0(周日)', dowExprMatches('0', 0) && !dowExprMatches('0', 1));
check('周一至周五 回存不变', roundtrip('0 8 * * 1-5') === '0 8 * * 1-5', roundtrip('0 8 * * 1-5'));
check('周一三五 回存不变', roundtrip('0 8 * * 1,3,5') === '0 8 * * 1,3,5');
check('每周日 描述', describeCron('0 8 * * 7') === '每周日 8:00 执行', describeCron('0 8 * * 7'));

console.log('== P3: 小时下拉显示文本 ==');
check('hoursOptions 不含 ":00"', !hoursOptions('8').includes(':00') && hoursOptions('8').includes('value="8" selected'));
check('hoursOptions 全部 24 项', (hoursOptions('8').match(/<option/g) || []).length === 24);

console.log('== 回归: 常规值行为不变 ==');
check('每天 8:00 回存不变', roundtrip('0 8 * * *') === '0 8 * * *');
check('每天 8:00 描述', describeCron('0 8 * * *') === '每天 8:00 执行', describeCron('0 8 * * *'));
check('每 30 分钟回存不变', roundtrip('*/30 * * * *') === '*/30 * * * *');
check('每 30 分钟描述', describeCron('*/30 * * * *') === '每 30 分钟执行一次');
check('每 2 小时（15 分）回存不变', roundtrip('15 */2 * * *') === '15 */2 * * *');
check('每月 15 日 8:00 回存不变', roundtrip('0 8 15 * *') === '0 8 15 * *');
check('每月 15 日 描述', describeCron('0 8 15 * *') === '每月 15 日 8:00 执行');
check('每周三 8:00 回存不变', roundtrip('0 8 * * 3') === '0 8 * * 3');
check('每周三 描述', describeCron('0 8 * * 3') === '每周三 8:00 执行', describeCron('0 8 * * 3'));
check('weekly pill 高亮单值(周三仅1个)', (html => (html.match(/cron-day-pill--on/g) || []).length === 1)(sandbox.buildCronEditFormHTML({ id: 't', title: 't', cron: '0 8 * * 3', agent_id: 'default', enabled: true, prompt: 'x' })));
// pill 高亮集成：生成表单 HTML 检查
const escAttr = sandbox.escAttr;
const html = sandbox.buildCronEditFormHTML({ id: 't', title: 't', cron: '0 8 * * 1-5', agent_id: 'default', enabled: true, prompt: 'x' });
check('表单对 1-5 高亮 5 个 pill', (html.match(/cron-day-pill--on/g) || []).length === 5, (html.match(/cron-day-pill--on/g) || []).length);
const html31 = sandbox.buildCronEditFormHTML({ id: 't', title: 't', cron: '0 8 31 * *', agent_id: 'default', enabled: true, prompt: 'x' });
check('表单对 31 日回显选中', html31.includes('value="31" selected'));
const html9 = sandbox.buildCronEditFormHTML({ id: 't', title: 't', cron: '7 9 * * *', agent_id: 'default', enabled: true, prompt: 'x' });
check('表单对 9:07 回显选中', html9.includes('value="7" selected') && html9.includes('value="9" selected'));

console.log('== P4: 分钟 select 语义修复（daily 改分钟 / hours 非档位分钟） ==');
// 修复 1：hours block 与 time-picker 的 minute select 类名区分（避免 readFreqFromForm 误读 hidden 项）
check('hours 模式分钟用 .cron-fld-minute-hours', html9.includes('cron-fld-minute-hours'), '');
check('time-picker 分钟用 .cron-fld-minute-time', sandbox.buildCronEditFormHTML({ id: 't', title: 't', cron: '0 8 * * *', agent_id: 'default', enabled: true, prompt: 'x' }).includes('cron-fld-minute-time'));
// 修复 2：hours 模式非档位分钟（7 分）在 hours block 中被动态插入并选中（此前硬编码档位无 7 → 静默变 0 分）
check('hours block 对 7 分动态插入选中', html9.includes('value="7" selected'), (html9.match(/value="7" selected/g) || []).length + ' 处');
check('7 * * * * 回存不变（每小时第 7 分）', roundtrip('7 * * * *') === '7 * * * *', roundtrip('7 * * * *'));
// 修复 3：daily 改分钟 roundtrip
check('30 8 * * * 回存不变', roundtrip('30 8 * * *') === '30 8 * * *', roundtrip('30 8 * * *'));
check('30 8 * * * 描述', describeCron('30 8 * * *') === '每天 8:30 执行', describeCron('30 8 * * *'));

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail ? 1 : 0);
