#!/bin/bash
# 构建 CodeAgent macOS DMG 安装包
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="${ROOT}/dist/CodeAgent.app"
DMG_PATH="${ROOT}/dist/CodeAgent-mac.dmg"
STAGING_DIR="${ROOT}/build/dmg-staging"
DMG_TMP="${ROOT}/build/CodeAgent-tmp.dmg"

echo "==> 清理旧文件"
rm -rf "${STAGING_DIR}" "${DMG_TMP}" "${DMG_PATH}"

echo "==> 创建临时目录"
mkdir -p "${STAGING_DIR}"

echo "==> 复制 .app"
cp -Rp "${APP}" "${STAGING_DIR}/CodeAgent.app"

echo "==> 创建 Applications 快捷入口"
ln -s /Applications "${STAGING_DIR}/Applications"

echo "==> 计算 DMG 大小（保守估计）"
APP_SIZE_MB="$(du -sm "${APP}" | cut -f1)"
DMG_SIZE_MB=$((APP_SIZE_MB + 50))
echo "    .app 大小: ${APP_SIZE_MB} MB → DMG 大小: ${DMG_SIZE_MB} MB"

echo "==> 创建 DMG"
hdiutil create \
    -fs HFS+ \
    -volname "CodeAgent" \
    -srcfolder "${STAGING_DIR}" \
    -size "${DMG_SIZE_MB}m" \
    -format UDZO \
    -imagekey zlib-level=9 \
    "${DMG_TMP}" 2>&1

echo "==> 最终 DMG 路径: ${DMG_PATH}"
mv "${DMG_TMP}" "${DMG_PATH}"

echo "==> 清理临时目录"
rm -rf "${STAGING_DIR}"

echo ""
echo "✅  Done: $(ls -lh "${DMG_PATH}" | awk '{print $5}")  ${DMG_PATH}"
