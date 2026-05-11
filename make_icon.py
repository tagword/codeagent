"""
从现成 PNG 图片构建 .app 所需的图标文件：
  - icon.png (896×896) → codeagent.icns（应用图标）
  - tray_icon.png (142×142) → tray_icon.png (22×22) + tray_icon@2x.png (44×44)

仅做缩放，不修改原始图片内容。
Run:  python make_icon.py
Requires:  Pillow (pip install pillow)
"""
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent.resolve()
SIZES = [16, 32, 64, 128, 256, 512]
ICONSET = ROOT / "build" / "CodeAgent.iconset"
ICNS = ROOT / "codeagent.icns"


def _make_icns():
    """从 icon.png 生成 codeagent.icns"""
    src = ROOT / "icon.png"
    if not src.exists():
        print("⚠️  icon.png 不存在")
        return

    big = Image.open(src).convert("RGBA")
    ICONSET.mkdir(parents=True, exist_ok=True)

    for s in SIZES:
        big.resize((s, s), Image.LANCZOS).save(ICONSET / f"icon_{s}x{s}.png")
        if s * 2 <= 512:
            big.resize((s * 2, s * 2), Image.LANCZOS).save(ICONSET / f"icon_{s}x{s}@2x.png")

    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
                   check=True)
    print(f"✅  {ICNS.name}  ({ICNS.stat().st_size / 1024:.0f} KB) — 来自 {src.name}")


def _make_tray():
    """从 tray_icon.png 缩放到 macOS 菜单栏所需尺寸（22×22 / 44×44）"""
    src = ROOT / "tray_icon.png"
    if not src.exists():
        print("⚠️  tray_icon.png 不存在")
        return

    big = Image.open(src).convert("RGBA")
    sizes = [(22, 22, "tray_icon.png"), (44, 44, "tray_icon@2x.png")]
    for w, h, name in sizes:
        resized = big.resize((w, h), Image.LANCZOS)
        resized.save(ROOT / name)
        print(f"✅  {name}  ({w}×{h}) — 来自 {src.name}")


if __name__ == "__main__":
    _make_icns()
    _make_tray()
