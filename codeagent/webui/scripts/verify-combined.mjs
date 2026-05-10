// verify-combined.mjs
// 对拼接式前端代码做合并语法验证：
// 1. 按文件名顺序拼接所有 .js 文件
// 2. 包裹在 async IIFE 中以支持顶层 await
// 3. 用 node --check 做语法检查

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webuiDir = path.resolve(__dirname, '..');

// 收集所有 .js 文件（排除 node_modules 和自身）
const files = fs.readdirSync(webuiDir)
  .filter(f => f.endsWith('.js'))
  .sort();

// 拼接
let combined = '';
for (const f of files) {
  combined += `// --- ${f} ---\n`;
  combined += fs.readFileSync(path.join(webuiDir, f), 'utf8');
  combined += '\n';
}

// 包裹成 async IIFE
const wrapped = `(async function(){\n${combined}\n})();\n`;

// 写临时文件
const tmpDir = fs.mkdtempSync('/tmp/webui-verify-');
const tmpFile = path.join(tmpDir, 'combined.mjs');
fs.writeFileSync(tmpFile, wrapped, 'utf8');

// 检查语法
try {
  // 用 child_process 执行 node --check
  const { execSync } = await import('node:child_process');
  execSync(`node --check "${tmpFile}"`, { stdio: 'pipe' });
  console.log('✅ Combined JS syntax: OK');
  process.exit(0);
} catch (e) {
  // 解析错误输出，定位到具体行
  const stderr = e.stderr?.toString() || e.message || '';
  // 把临时文件路径替换回源文件引用
  const friendlyMsg = stderr.replaceAll(tmpFile, 'combined');
  console.error('❌ Combined JS syntax: FAIL');
  console.error(friendlyMsg);

  // 尝试定位到具体文件位置
  const lineMatch = stderr.match(/combined\.mjs:(\d+):/);
  if (lineMatch) {
    const errLine = parseInt(lineMatch[1], 10);
    // 减去 IIFE 包裹的前缀行数 (1行: "(async function(){")
    const concatLine = errLine - 1; // 1-indexed in combined
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
  // 清理临时文件
  try { fs.rmSync(tmpDir, { recursive: true }); } catch {}
}
