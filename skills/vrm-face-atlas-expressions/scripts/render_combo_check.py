"""Render every expression combination of a VRM 1.0 (emotion x vowel, blinks) for visual checking.

    blender -b -P render_combo_check.py -- avatar.vrm out_dir [--angles 0,45,315] [--res 480]

Texture transform binds are emulated by shifting the UVs of the bound materials (glTF offset (u, v_down) ->
Blender (u, -v)), and morph target binds by setting shape-key values, so the result matches what a VRM runtime
shows (offsets ADD, like VRM). Then build a contact sheet with make_grid.py.
"""
import bpy, addon_utils, sys, os, math
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, OUTD = argv[0], argv[1]
ANG = [int(x) for x in (argv[argv.index("--angles") + 1] if "--angles" in argv else "0,45,315").split(",")]
RES = int(argv[argv.index("--res") + 1]) if "--res" in argv else 480
os.makedirs(OUTD, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
for mod in addon_utils.modules():
    if mod.__name__.endswith(".vrm") or mod.__name__ == "io_scene_vrm":
        addon_utils.enable(mod.__name__, default_set=True)
bpy.ops.import_scene.vrm(filepath=VRM)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
pre = arm.data.vrm_addon_extension.vrm1.expressions.preset
# find the mesh that carries the morph binds
headname = next((b.node.mesh_object_name for e in ("aa", "blink", "happy") for b in getattr(pre, e).morph_target_binds), None)
head = bpy.data.objects[headname]; me = head.data
kb = me.shape_keys.key_blocks if me.shape_keys else {}
uv = me.uv_layers.active.data
orig = np.zeros(len(uv) * 2, np.float32); uv.foreach_get("uv", orig)
pm = np.zeros(len(me.polygons), np.int64); me.polygons.foreach_get("material_index", pm)
lt = np.zeros(len(me.polygons), np.int64); me.polygons.foreach_get("loop_total", lt)
loopmat = np.repeat(pm, lt); midx = {m.name: i for i, m in enumerate(me.materials)}

def apply(names):
    for k in kb: k.value = 0.0
    u = orig.reshape(-1, 2).copy()
    for nm in names:
        e = getattr(pre, nm)
        for b in e.morph_target_binds:
            if b.index in kb: kb[b.index].value = b.weight
        for t in e.texture_transform_binds:
            sel = loopmat == midx[t.material.name]
            u[sel, 0] += t.offset[0]; u[sel, 1] -= t.offset[1]
    uv.foreach_set("uv", u.ravel()); me.update()

sc = bpy.context.scene
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try: sc.render.engine = eng; break
    except TypeError: pass
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND"); bg.inputs[0].default_value = (0.8, 0.8, 0.82, 1); bg.inputs[1].default_value = 1.5
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
sun.data.energy = 2.5; sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; sc.render.resolution_x = sc.render.resolution_y = RES
# frame the face from the head mesh bounds
ws = [head.matrix_world @ Vector(c) for c in head.bound_box]
zc = (min(v.z for v in ws) + max(v.z for v in ws)) / 2; cam.data.ortho_scale = (max(v.z for v in ws) - min(v.z for v in ws)) * 1.05
target = Vector((0, 0, zc))

EMO = ["neutral", "happy", "angry", "sad", "surprised", "relaxed"]
VOW = ["rest", "aa", "ih", "ou", "ee", "oh"]
combos = [([e] if e != "neutral" else []) + ([v] if v != "rest" else []) for e in EMO for v in VOW]
combos += [["blink"], ["blink_left"], ["blink_right"]]
for names in combos:
    apply(names); tag = "+".join(names) or "neutral"
    for az in ANG:
        a = math.radians(az); cam.location = target + Vector((math.sin(a) * 2, -math.cos(a) * 2, 0))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(OUTD, f"{tag}_{az:03d}.png"); bpy.ops.render.render(write_still=True)
apply([])
print("done ->", OUTD)
