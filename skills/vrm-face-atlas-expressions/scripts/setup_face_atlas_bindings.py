"""Set up VRM 1.0 expressions driven by eye/mouth texture atlases (TextureTransformBind) + helper shape keys.

Run inside Blender with the VRM Add-on for Blender enabled, on a scene that already has the VRM armature
and the head mesh (materials split into skin / eyeL / eyeR / mouth):

    blender your_avatar.blend -b -P setup_face_atlas_bindings.py -- face_atlas_config.json [--export out.vrm]

What it does
  1. Checks that the eye/mouth UVs sit inside the top-left tile (glTF UV, origin top-left) and warns if not.
  2. Converts the 4 face materials to MToon and gives them IDENTICAL shading parameters (no blocks in shade),
     opaque, emissive 0, matcap 0, no outline.
  3. Creates the VRM 1.0 preset expressions from the config: morph target binds + texture transform binds,
     isBinary = true, emotions overrideBlink = block / overrideMouth = none.
"""
import bpy, addon_utils, sys, json, os

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    raise SystemExit("usage: blender file.blend -b -P setup_face_atlas_bindings.py -- config.json [--export out.vrm]")
CFG = json.load(open(argv[0], encoding="utf-8"))
OUT = argv[argv.index("--export") + 1] if "--export" in argv else None

for mod in addon_utils.modules():
    if mod.__name__.endswith(".vrm") or mod.__name__ == "io_scene_vrm":
        addon_utils.enable(mod.__name__, default_set=True)

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
ext = arm.data.vrm_addon_extension
head = bpy.data.objects[CFG["head_object"]]
MAT = {k: bpy.data.materials[v] for k, v in CFG["materials"].items()}
GRID = {"eyeL": CFG["eye_grid"], "eyeR": CFG["eye_grid"], "mouth": CFG["mouth_grid"]}

# ---- 1. UV sanity: atlas materials must sit in the top-left tile ------------------------------------------------
me = head.data; uv = me.uv_layers.active.data
idx = {m.name: i for i, m in enumerate(me.materials)}
for key in ("eyeL", "eyeR", "mouth"):
    mi = idx.get(MAT[key].name)
    us, vs = [], []
    for p in me.polygons:
        if p.material_index == mi:
            for li in p.loop_indices:
                u, v = uv[li].uv; us.append(u); vs.append(1.0 - v)    # Blender v-up -> glTF v-down
    if not us:
        print(f"[warn] material {MAT[key].name} has no faces"); continue
    t = 1.0 / GRID[key]
    ok = min(us) >= -1e-4 and max(us) <= t + 1e-4 and min(vs) >= -1e-4 and max(vs) <= t + 1e-4
    print(f"[uv] {key}: u {min(us):.4f}..{max(us):.4f} v {min(vs):.4f}..{max(vs):.4f} (tile {t:.4f}) {'OK' if ok else 'OUTSIDE TOP-LEFT TILE'}")

# ---- 2. MToon with identical parameters on all face materials ---------------------------------------------------
fm = CFG["face_mtoon"]
for key, m in MAT.items():
    bpy.ops.vrm.convert_material_to_mtoon1(material_name=m.name)
    mt = m.vrm_addon_extension.mtoon1
    mt.enabled = True                        # the convert operator may leave this False in background mode
    mt.alpha_mode = "OPAQUE"
    mt.pbr_metallic_roughness.base_color_factor = fm["base_color"]
    x = mt.extensions.vrmc_materials_mtoon
    x.shade_color_factor = fm["shade_color"]; x.shading_shift_factor = fm["shading_shift"]
    x.shading_toony_factor = fm["shading_toony"]; x.gi_equalization_factor = fm["gi_equalization"]
    x.matcap_factor = (0.0, 0.0, 0.0); x.outline_width_mode = "none"
    x.parametric_rim_color_factor = (0.0, 0.0, 0.0); x.rim_lighting_mix_factor = 0.0
    src = mt.pbr_metallic_roughness.base_color_texture.index.source
    if src is not None:
        x.shade_multiply_texture.index.source = src
    mt.emissive_factor = (0.0, 0.0, 0.0)
    print(f"[mtoon] {m.name} texture={src.name if src else None}")

# ---- 3. expressions ---------------------------------------------------------------------------------------------
keys = set(head.data.shape_keys.key_blocks.keys()) if head.data.shape_keys else set()
preset = ext.vrm1.expressions.preset
for name, e in CFG["expressions"].items():
    ex = getattr(preset, name)
    while len(ex.morph_target_binds): ex.morph_target_binds.remove(0)
    while len(ex.texture_transform_binds): ex.texture_transform_binds.remove(0)
    for k in e.get("morph", []):
        if k not in keys:
            print(f"[warn] {name}: shape key '{k}' not found, skipped"); continue
        b = ex.morph_target_binds.add(); b.node.mesh_object_name = head.name; b.index = k; b.weight = 1.0
    for mk, (col, row) in e.get("tt", {}).items():
        g = GRID[mk]
        t = ex.texture_transform_binds.add(); t.material = MAT[mk]; t.scale = (1.0, 1.0); t.offset = (col / g, row / g)
    ex.is_binary = True
    ex.override_blink = "block" if e.get("emotion") else "none"
    ex.override_mouth = "none"
    ex.override_look_at = "none"
    print(f"[expr] {name}: morph {len(ex.morph_target_binds)} tt {[(t.material.name, tuple(round(v, 4) for v in t.offset)) for t in ex.texture_transform_binds]}")

if OUT:
    bpy.ops.object.select_all(action="DESELECT")
    print(bpy.ops.export_scene.vrm(filepath=OUT, armature_object_name=arm.name), OUT)
    print("[next] run slim_glb.py on the exported file (emissive 0, matcap 0, mipmaps, sparse morphs)")
