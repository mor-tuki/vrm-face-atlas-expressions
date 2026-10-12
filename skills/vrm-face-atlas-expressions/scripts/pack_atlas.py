"""Pack expression tiles into an atlas grid with padding + colour bleed (safe for mipmaps).

    python pack_atlas.py --grid 3 --tile 1024 --pad 0.06 --bleed 64 --out atlas_eyeL.png \
        neutral.png closed.png happy.png angry.png sad.png surprised.png relaxed.png

Tiles are placed row by row (glTF UV: top-left = (0,0)). Missing cells (fewer files than grid*grid) repeat the
first tile so an accidental offset never shows garbage. Each tile is scaled into the inner (1-2*pad) area of its
cell; the remaining border is filled by extending the tile's edge colours ("bleed"), so lower mip levels do not
pick up the neighbouring tile. Output is RGB (no alpha): keep face atlases opaque.

The base UV of the eye/mouth material must cover the INNER area of the top-left cell, i.e. map your original
eye/mouth region to [pad, 1-pad] * (1/grid) when you build the neutral tile. Use --report to print that UV box.
"""
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("tiles", nargs="+"); ap.add_argument("--grid", type=int, required=True)
ap.add_argument("--tile", type=int, default=1024); ap.add_argument("--pad", type=float, default=0.06)
ap.add_argument("--bleed", type=int, default=64); ap.add_argument("--out", required=True)
ap.add_argument("--report", action="store_true")
a = ap.parse_args()
G, T = a.grid, a.tile; P = int(round(T * a.pad)); inner = T - 2 * P
atlas = np.zeros((G * T, G * T, 3), np.float32)
files = a.tiles + [a.tiles[0]] * (G * G - len(a.tiles))
for i, f in enumerate(files[:G * G]):
    r, c = divmod(i, G)
    im = Image.open(f).convert("RGBA").resize((inner, inner), Image.LANCZOS)
    rgba = np.array(im).astype(np.float32)
    valid = rgba[..., 3] > 8
    cell = np.zeros((T, T, 3), np.float32); mask = np.zeros((T, T), bool)
    cell[P:P + inner, P:P + inner] = rgba[..., :3]; mask[P:P + inner, P:P + inner] = valid
    # bleed: nearest valid colour outward (covers padding and any transparent holes)
    _, (iy, ix) = ndimage.distance_transform_edt(~mask, return_indices=True)
    cell = cell[iy, ix]
    atlas[r * T:(r + 1) * T, c * T:(c + 1) * T] = cell
Image.fromarray(np.clip(atlas, 0, 255).astype(np.uint8)).save(a.out)
print("wrote", a.out, atlas.shape[:2], "tile", T, "pad px", P)
if a.report:
    t = 1.0 / G
    print(f"base UV box for the top-left tile (glTF, v down): u,v in [{P / T * t:.5f}, {(T - P) / T * t:.5f}]")
