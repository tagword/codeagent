"""
Generate CodeAgent.app icon file (codeagent.icns).

Run with:  python make_icon.py
Requires:  Pillow (pip install pillow)
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent.resolve()
SIZES = [16, 32, 64, 128, 256, 512]
ICONSET = ROOT / "build" / "CodeAgent.iconset"
ICNS = ROOT / "codeagent.icns"


def _draw(size: int) -> Image.Image:
    """Draw CodeAgent icon: a deep-blue circle with < / > code brackets."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg = (30, 60, 140, 255)
    accent = (80, 200, 245, 255)
    fg = (200, 230, 255, 255)

    cx = cy = size // 2
    r = int(size * 0.44)

    # Glow rings
    for i in range(3):
        draw.ellipse(
            [cx - r - i, cy - r - i, cx + r + i, cy + r + i],
            outline=(*accent[:3], max(40, 140 - i * 35)),
            width=2,
        )

    # Gradient circle
    for i in range(int(r * 0.85), 0, -1):
        ratio = i / (r * 0.85)
        clr = (
            int(bg[0] + (accent[0] - bg[0]) * (1 - ratio)),
            int(bg[1] + (accent[1] - bg[1]) * (1 - ratio)),
            int(bg[2] + (accent[2] - bg[2]) * (1 - ratio)),
            255,
        )
        draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=clr)

    # Code brackets < />
    cs = max(8, int(size * 0.25))
    lw = max(2, int(size * 0.06))

    lx, ly = cx - int(size * 0.12), cy
    draw.line([(lx, ly - cs), (lx - cs, ly), (lx, ly + cs)], fill=fg, width=lw)

    rx, ry = cx + int(size * 0.12), cy
    draw.line([(rx, ly - cs), (rx + cs, ly), (rx, ly + cs)], fill=fg, width=lw)

    s = int(size * 0.04)
    draw.line([(cx - s, cy + int(size * 0.22)),
               (cx + s, cy - int(size * 0.22))], fill=fg, width=lw - 1)

    return img


def main():
    ICONSET.mkdir(parents=True, exist_ok=True)

    for s in SIZES:
        _draw(s).save(ICONSET / f"icon_{s}x{s}.png")
        if s * 2 <= 512:
            _draw(s * 2).save(ICONSET / f"icon_{s}x{s}@2x.png")

    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
                   check=True)
    print(f"✅  {ICNS.name}  ({ICNS.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
