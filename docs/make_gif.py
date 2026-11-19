"""Assemble docs/studio-demo.gif from frames named NN-<hold ms>.png (see studio-ui/scripts/screenshots.mjs)."""

import sys
from pathlib import Path

from PIL import Image

frames_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
files = sorted(frames_dir.glob("*.png"))
frames, durations = [], []
for f in files:
    img = Image.open(f).convert("RGB")
    img = img.resize((960, int(img.height * 960 / img.width)), Image.LANCZOS)
    frames.append(img.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    durations.append(int(f.stem.split("-")[1]))
frames[0].save(out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
print(f"{out}: {len(frames)} frames, {sum(durations) / 1000:.1f} s, {out.stat().st_size // 1024} KB")
