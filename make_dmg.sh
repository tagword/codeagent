#!/bin/bash
# Build CodeAgent macOS DMG installer
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="${ROOT}/dist/CodeAgent.app"
DMG="${ROOT}/dist/CodeAgent-mac.dmg"
STAGING="${ROOT}/build/dmg-staging"

echo "==> Clean"
rm -rf "${STAGING}" "${DMG}"

echo "==> Stage"
mkdir -p "${STAGING}"
ditto "${APP}" "${STAGING}/CodeAgent.app"
ln -s /Applications "${STAGING}/Applications"

APP_SIZE="$(du -sm "${APP}" | cut -f1)"
DMG_SIZE=$((APP_SIZE + 50))
echo "    .app: ${APP_SIZE} MB → DMG buf: ${DMG_SIZE} MB"

echo "==> Create DMG"
hdiutil create \
    -fs HFS+ \
    -volname "CodeAgent" \
    -srcfolder "${STAGING}" \
    -size "${DMG_SIZE}m" \
    -format UDZO \
    -imagekey zlib-level=9 \
    "${DMG}"

echo "==> Clean up"
rm -rf "${STAGING}"

echo ""
echo "✅  $(ls -lh "${DMG}" | awk '{print $5}')  ${DMG}"
