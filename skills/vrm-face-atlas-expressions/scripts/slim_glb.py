"""Post-export fix-up + slimming for a VRM 1.0 / glTF binary (.vrm / .glb). Pure Python (numpy), no Blender needed.

    python slim_glb.py in.vrm out.vrm [--no-sparse] [--no-weights] [--keep-emissive]

  * emissiveFactor -> 0 on materials without an emissive texture (Blender MToon export can write (1,1,1),
    which makes faces glow white in three-vrm)
  * VRMC_materials_mtoon.matcapFactor -> [0,0,0] when no matcap texture (spec default is white)
  * every texture gets a mipmapped sampler (min LINEAR_MIPMAP_LINEAR, mag LINEAR, repeat)
  * drops accessors nothing references (e.g. exported-but-unused shape-key normals)
  * morph-target float deltas -> sparse accessors (only moving vertices are stored)
  * WEIGHTS_n float -> normalized UNSIGNED_BYTE (rows re-summed to 255)
VRM extensions (VRMC_vrm, VRMC_springBone, ...) only reference nodes/materials/images, so they are kept as-is.
Always reload the result (Blender VRM add-on / three-vrm) and check expressions + springs afterwards.
"""
import json, struct, sys
import numpy as np

args = sys.argv[1:]
src, dst = args[0], args[1]
SPARSE = "--no-sparse" not in args; QW = "--no-weights" not in args; ZERO_EMI = "--keep-emissive" not in args
b = open(src, "rb").read()
assert b[:4] == b"glTF", "not a glb/vrm"
n = struct.unpack("<I", b[12:16])[0]
j = json.loads(b[20:20 + n]); binb = b[20 + n + 8:]
acc, bvs = j["accessors"], j["bufferViews"]
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
report = {}

# ---- material / sampler fixes ----
for m in j.get("materials", []):
    if ZERO_EMI and "emissiveTexture" not in m and m.get("emissiveFactor", [0, 0, 0]) != [0, 0, 0]:
        m["emissiveFactor"] = [0.0, 0.0, 0.0]; report.setdefault("emissive_zeroed", []).append(m.get("name"))
    e = m.get("extensions", {}).get("VRMC_materials_mtoon")
    if e is not None and "matcapTexture" not in e:
        e["matcapFactor"] = [0.0, 0.0, 0.0]
j.setdefault("samplers", []).append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
si = len(j["samplers"]) - 1
for t in j.get("textures", []): t["sampler"] = si

# ---- accessor slimming ----
def read_acc(a):
    bv = bvs[a["bufferView"]]; o = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    dt = CT[a["componentType"]]; k = NC[a["type"]]
    stride = bv.get("byteStride")
    if stride in (None, np.dtype(dt).itemsize * k):
        return np.frombuffer(binb, dt, a["count"] * k, o).reshape(a["count"], k)
    rows = [np.frombuffer(binb, dt, k, o + i * stride) for i in range(a["count"])]   # interleaved (rare)
    return np.stack(rows)
targets, weights, ref = set(), set(), []
def use(i):
    if i not in ref: ref.append(i)
for m in j["meshes"]:
    for p in m["primitives"]:
        for k, v in p["attributes"].items():
            use(v)
            if k.startswith("WEIGHTS_"): weights.add(v)
        if "indices" in p: use(p["indices"])
        for t in p.get("targets", []):
            for v in t.values(): use(v); targets.add(v)
for s in j.get("skins", []):
    if "inverseBindMatrices" in s: use(s["inverseBindMatrices"])
for an in j.get("animations", []):
    for s in an["samplers"]: use(s["input"]); use(s["output"])
amap = {old: new for new, old in enumerate(ref)}
out = bytearray(); new_bvs = []
def add_bv(data, target=None):
    while len(out) % 4: out.append(0)
    bv = {"buffer": 0, "byteOffset": len(out), "byteLength": len(data)}
    if target: bv["target"] = target
    out.extend(data); new_bvs.append(bv); return len(new_bvs) - 1
new_acc = []; dense = sparse = 0; werr = 0.0
for old in ref:
    a = dict(acc[old])
    if "bufferView" not in a:            # already sparse / zero-filled: keep definition, copy its views
        if "sparse" in a:
            for part in ("indices", "values"):
                bv = bvs[a["sparse"][part]["bufferView"]]; o = bv.get("byteOffset", 0)
                a["sparse"][part]["bufferView"] = add_bv(binb[o:o + bv["byteLength"]])
        new_acc.append(a); continue
    tgt = bvs[a["bufferView"]].get("target"); data = read_acc(acc[old])
    if SPARSE and old in targets and a["componentType"] == 5126:
        nz = np.flatnonzero(np.abs(data).max(1) > 0)
        if len(nz) == 0: nz = np.array([0])
        ict = 5123 if data.shape[0] < 65536 else 5125
        idx = nz.astype(np.uint16 if ict == 5123 else np.uint32).tobytes(); val = np.ascontiguousarray(data[nz], np.float32).tobytes()
        a.pop("bufferView"); a.pop("byteOffset", None)
        a["sparse"] = {"count": int(len(nz)), "indices": {"bufferView": add_bv(idx), "componentType": ict}, "values": {"bufferView": add_bv(val)}}
        dense += data.nbytes; sparse += len(idx) + len(val)
    elif QW and old in weights and a["componentType"] == 5126:
        q = np.round(np.clip(data, 0, 1) * 255).astype(np.int32)
        q[np.arange(len(q)), q.argmax(1)] += 255 - q.sum(1)
        q = np.clip(q, 0, 255).astype(np.uint8); werr = max(werr, float(np.abs(q / 255.0 - data).max()))
        a.update(componentType=5121, normalized=True); a.pop("min", None); a.pop("max", None); a.pop("byteOffset", None)
        a["bufferView"] = add_bv(q.tobytes(), tgt)
    else:
        a.pop("byteOffset", None); a["bufferView"] = add_bv(np.ascontiguousarray(data).tobytes(), tgt)
    new_acc.append(a)
for im in j.get("images", []):
    if "bufferView" in im:
        bv = bvs[im["bufferView"]]; o = bv.get("byteOffset", 0); im["bufferView"] = add_bv(binb[o:o + bv["byteLength"]])
while len(out) % 4: out.append(0)
for m in j["meshes"]:
    for p in m["primitives"]:
        p["attributes"] = {k: amap[v] for k, v in p["attributes"].items()}
        if "indices" in p: p["indices"] = amap[p["indices"]]
        if "targets" in p: p["targets"] = [{k: amap[v] for k, v in t.items()} for t in p["targets"]]
for s in j.get("skins", []):
    if "inverseBindMatrices" in s: s["inverseBindMatrices"] = amap[s["inverseBindMatrices"]]
for an in j.get("animations", []):
    for s in an["samplers"]: s["input"] = amap[s["input"]]; s["output"] = amap[s["output"]]
j["accessors"] = new_acc; j["bufferViews"] = new_bvs; j["buffers"] = [{"byteLength": len(out)}]
js = json.dumps(j, ensure_ascii=False, separators=(",", ":")).encode("utf-8"); js += b" " * ((4 - len(js) % 4) % 4)
res = (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(out)) + struct.pack("<II", len(js), 0x4E4F534A) + js
       + struct.pack("<II", len(out), 0x004E4942) + bytes(out))
open(dst, "wb").write(res)
report.update(accessors=[len(acc), len(new_acc)], morph_MB=[round(dense / 1e6, 2), round(sparse / 1e6, 2)],
              weight_max_err=round(werr, 4), size_MB=[round(len(b) / 1e6, 2), round(len(res) / 1e6, 2)])
print(json.dumps(report, ensure_ascii=False))
