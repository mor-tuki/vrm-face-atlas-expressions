"""Contact sheet for render_combo_check.py output: emotion rows x vowel columns (+ blink row).

    python make_grid.py out_dir --angle 0 --cell 300 --out grid_000.jpg
"""
import argparse, os
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("dir"); ap.add_argument("--angle", type=int, default=0)
ap.add_argument("--cell", type=int, default=300); ap.add_argument("--out", default="grid.jpg")
a = ap.parse_args()
EMO = ["neutral", "happy", "angry", "sad", "surprised", "relaxed"]
VOW = ["rest", "aa", "ih", "ou", "ee", "oh"]
rows = [[("+".join(([e] if e != "neutral" else []) + ([v] if v != "rest" else [])) or "neutral") for v in VOW] for e in EMO]
rows.append(["blink", "blink_left", "blink_right"])
C, L, H = a.cell, 110, 30
sheet = Image.new("RGB", (L + C * len(VOW), H + C * len(rows)), "white"); d = ImageDraw.Draw(sheet)
for j, v in enumerate(VOW): d.text((L + j * C + 6, 8), v, fill="black")
for i, row in enumerate(rows):
    d.text((6, H + i * C + C // 2), EMO[i] if i < len(EMO) else "blinks", fill="black")
    for j, tag in enumerate(row):
        p = os.path.join(a.dir, f"{tag}_{a.angle:03d}.png")
        if os.path.exists(p):
            sheet.paste(Image.open(p).convert("RGB").resize((C, C)), (L + j * C, H + i * C))
sheet.save(a.out, quality=90); print("wrote", a.out)
