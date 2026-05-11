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
# macOS 标准 iconset 文件清单：(stem, 1x_px, 2x_px)
# 生成 10 个文件，覆盖全部 Retina 密度
_ICON_FILES: list[tuple[str, int, int]] = [
    ("icon_16x16",     16,    32),
    ("icon_32x32",     32,    64),
    ("icon_128x128",  128,   256),
    ("icon_256x256",  256,   512),
    ("icon_512x512",  512,  1024),
]
ICONSET = ROOT / "build" / "CodeAgent.iconset"
ICNS = ROOT / "codeagent.icns"


def _write_img(size: int, filename: str, src_img: Image.Image) -> None:
    """缩放并写入 iconset 文件。有 upscale 时提示。"""
    src_max = max(src_img.size)
    if size > src_max:
        print(f"  ⚠️  {filename}: 源图 {src_max}px → upscale {size}px")
    img = src_img.resize((size, size), Image.LANCZOS)
    img.save(ICONSET / filename)


def _make_icns():
    """从 icon.png 生成 codeagent.icns"""
    src = ROOT / "icon.png"
    if not src.exists():
        print("⚠️  icon.png 不存在")
        return

    big = Image.open(src).convert("RGBA")
    ICONSET.mkdir(parents=True, exist_ok=True)

    for stem, px1, px2 in _ICON_FILES:
        _write_img(px1, f"{stem}.png", big)
        _write_img(px2, f"{stem}@2x.png", big)

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
