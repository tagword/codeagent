// verify-combined.cjs
// 对拼接式前端代码做合并语法验证：
// 1. 按文件名顺序拼接所有 .js 文件
// 2. 包裹在 async IIFE 中以支持顶层 await
// 3. 用 node --check 做语法检查
// 4. 错误时定位到具体源文件 + 行号
//
// 历史：本文件原为 verify-combined.mjs（ESM import），最低要求 node ≥ 14。
//       仓库内执行环境可能为 node 10（如 legacy 系统），改写为 CJS 以兼容 ≥ node 10。
//       临时产物落 .scripts/.tmp/ 而非 /tmp，遵循 project-docs-layout 规则。

'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

// 最低 node 版本：webui 源码用了 optional chaining (?.) / nullish coalescing (??) 等 ES2020 语法，
// node 14+ 的 V8 才原生支持。脚本自身只依赖同步 fs，10 也能跑，但 --check 源文件需要 14+。
// 注：项目还依赖 @biomejs/biome（devDeps）跑 lint，biome 自身要求 node ≥ 18。
const REQUIRED_NODE = 14;
const major = parseInt((process.version || 'v0').slice(1).split('.')[0], 10);
if (!Number.isFinite(major) || major < REQUIRED_NODE) {
  console.error('❌ Node ≥ ' + REQUIRED_NODE + ' required (current: ' + process.version + ')');
  process.exit(2);
}

const webuiDir = path.resolve(__dirname, '..');
// 临时产物落 .scripts/.tmp/，避免污染 /tmp；CI 环境也用同源路径，便于审计。
const tmpRoot = path.join(webuiDir, '.scripts', '.tmp');
const tmpDir = fs.mkdtempSync(path.join(tmpRoot, 'webui-verify-'));
const tmpFile = path.join(tmpDir, 'combined.js');

// 收集所有 .js 文件（按字母序；与 server/__init__.py:454 拼装顺序一致）
const files = fs.readdirSync(webuiDir)
  .filter(f => f.endsWith('.js'))
  .sort();

// 拼接：每文件加 // --- 头注释便于错误定位
let combined = '';
for (const f of files) {
  combined += `// --- ${f} ---\n`;
  combined += fs.readFileSync(path.join(webuiDir, f), 'utf8');
  combined += '\n';
}

// 包裹成 async IIFE（顶层 await 友好；不会实际改变语法，但能让 parse 阶段过）
const wrapped = `(async function(){\n${combined}\n})();\n`;
fs.writeFileSync(tmpFile, wrapped, 'utf8');

try {
  execFileSync(process.execPath, ['--check', tmpFile], { stdio: 'pipe' });
  console.log('✅ Combined JS syntax: OK (' + files.length + ' files, ' + combined.length + ' bytes)');
  process.exit(0);
} catch (e) {
  const stderr = (e.stderr ? e.stderr.toString() : '') || e.message || '';
  // 错误信息中的临时路径替换为可读名
  const friendlyMsg = stderr.split(tmpFile).join('combined.js');
  console.error('❌ Combined JS syntax: FAIL');
  console.error(friendlyMsg);

  // 定位到源文件：IIFE 包裹前缀 1 行 + 每文件 1 行 // --- 头注释 + N 行内容
  const lineMatch = stderr.match(/combined\.js:(\d+):/);
  if (lineMatch) {
    const errLine = parseInt(lineMatch[1], 10);
    const concatLine = errLine - 1; // 减去 IIFE 前缀
    let cumLines = 0;
    for (const f of files) {
      const content = fs.readFileSync(path.join(webuiDir, f), 'utf8');
      const fileLines = content.split('\n').length + 1; // +1 for // --- header
      cumLines += fileLines;
      if (concatLine <= cumLines) {
        const offsetInFile = concatLine - (cumLines - fileLines) - 1; // 0-indexed, skip header
        console.error(`  → File: ${f} (approx line ${offsetInFile + 1})`);
        break;
      }
    }
  }

  process.exit(1);
} finally {
  // 清理临时目录（同步，避免 mjs 版原先的异步竞态）
  try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
}
