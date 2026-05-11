#!/bin/bash
# Build CodeAgent macOS DMG installer
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="${ROOT}/dist/CodeAgent.app"
DMG="${ROOT}/dist/CodeAgent-mac.dmg"
TMP_IMG="${ROOT}/build/CodeAgent-template.sparseimage"

echo "==> Clean"
rm -rf "${TMP_IMG}" "${DMG}"

echo "==> Size"
APP_SIZE="$(du -sm "${APP}" | cut -f1)"
DMG_SIZE=$((APP_SIZE + 50))
echo "    .app: ${APP_SIZE} MB → DMG buf: ${DMG_SIZE} MB"

echo "==> Create sparse image"
hdiutil create -size "${DMG_SIZE}m" -type SPARSE \
  -fs HFS+ -volname "CodeAgent" \
  "${TMP_IMG}" 2>/dev/null

echo "==> Mount & stage"
MOUNT="/tmp/codeagent-dmg-$$"
hdiutil attach -nobrowse -mountpoint "${MOUNT}" "${TMP_IMG}" 2>/dev/null
echo "    Mount: ${MOUNT}"
cp -Rp "${APP}" "${MOUNT}/CodeAgent.app"
ln -sf /Applications "${MOUNT}/Applications"
hdiutil detach "${MOUNT}" 2>/dev/null

echo "==> Convert to compressed DMG"
hdiutil convert "${TMP_IMG}" -format UDZO -imagekey zlib-level=9 -o "${DMG}" 2>/dev/null

echo "==> Clean up"
rm -f "${TMP_IMG}"

echo ""
echo "✅  $(ls -lh "${DMG}" | awk '{print $5}')  ${DMG}"
