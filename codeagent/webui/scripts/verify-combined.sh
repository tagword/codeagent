#!/bin/bash
# verify-combined.sh
# 对拼接式前端代码做合并验证：
# 1. 按文件名顺序拼接所有 JS 文件
# 2. 包裹在 async IIFE 中以支持顶层 await
# 3. 用 node --check 做语法检查
# 4. (可选) 用 biome 对合并结果做 lint

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEBUI_DIR="$(dirname "$SCRIPT_DIR")"
COMBINED="/tmp/webui-combined.mjs"

# Step 1: 按字母序拼接所有 .js 文件（排除自身）
cd "$WEBUI_DIR"
for f in $(ls *.js | sort); do
  echo "// --- $f ---"
  cat "$f"
  echo ""
done > "$COMBINED"

# Step 2: 包裹成 async function + 立即执行
WRAPPED="/tmp/webui-wrapped.mjs"
{
  echo "(async function() {"
  cat "$COMBINED"
  echo "})();"
} > "$WRAPPED"

# Step 3: 语法检查
echo "--- Syntax check ---"
node --check "$WRAPPED" 2>&1
if [ $? -eq 0 ]; then
  echo "✅ Combined JS syntax: OK"
else
  echo "❌ Combined JS syntax: FAILED"
  exit 1
fi
