"""rig_plan - in Blender: build a skeleton from a plan (`amald skeleton`) and bind the mesh to it, or convert a model.

    blender --background --python rig_plan.py -- rig     <model.glb|.fbx|.obj> <plan.json> <out.fbx>
    blender --background --python rig_plan.py -- convert <model.glb|...> <out.fbx|.obj|.glb>
    blender --background --python rig_plan.py -- proxy   <model.glb|...> <out.glb> <faces>

`proxy`: a light copy of the model for making skin weights on: rebuilt watertight first (decimating the glTF as read, split
at every UV seam, cracked it into 931 pieces and the bind made weights on a soup - 2026-11-07), then reduced. Same place
and size as the model, no materials.

`rig`: the plan was made from the same model file read as glTF (Y up); Blender is Z up, so a plan point (x, y, z)
is (x, -z, y) here. One bone per joint, from it to its first child (an end joint continues its parent's direction).
The mesh is bound with bone heat (automatic weights); creature_anim then compares weights and checks the result.
The rig route for machines without Maya, and the fallback when the AdvancedSkeleton build fails.
"""
import json
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
mode = args[0]


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit(f"AMAL_SPEC_ERROR cannot read {ext}")
    for o in [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]:
        bpy.data.objects.remove(o)               # a new skeleton replaces any old one
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("AMAL_SPEC_ERROR no mesh in " + path)
    for o in meshes:
        o.parent = None
        for m in list(o.modifiers):
            if m.type == "ARMATURE":
                o.modifiers.remove(m)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    ext = os.path.splitext(path)[1].lower()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if ext == ".fbx":
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, add_leaf_bones=False, bake_anim=False,
                                 path_mode="COPY", embed_textures=True)  # keep the pictures (the rig was untextured, 2026-11-14)
    elif ext == ".obj":
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, export_materials=False)
    else:
        bpy.ops.export_scene.gltf(filepath=path, use_selection=True)


mesh = load(args[1])
if mode == "proxy":
    want = int(args[3]) if len(args) > 3 else 20000
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import amal_bpy
    health = amal_bpy.make_watertight(mesh, detail=int(os.environ.get("AMAL_PROXY_DETAIL", 192)))
    print("AMAL_STEP light copy watertight: %(pieces)s piece(s), %(open_edges)s open edges" % health)
    faces = sum(len(p.vertices) - 2 for p in mesh.data.polygons)   # triangles: the remesh makes quads
    if faces > want:
        dec = mesh.modifiers.new("proxy", "DECIMATE")
        dec.decimate_type = "COLLAPSE"
        dec.ratio = max(0.01, want / faces)
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.modifier_apply(modifier=dec.name)
    mesh.data.materials.clear()
    # a hidden mesh is not exported (an FBX from Maya carries its body in a hidden group): shown, at the top level
    for c in list(mesh.users_collection):
        c.objects.unlink(mesh)
    bpy.context.scene.collection.objects.link(mesh)
    mesh.hide_set(False)
    mesh.hide_viewport = False
    mesh.hide_render = False
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    os.makedirs(os.path.dirname(os.path.abspath(args[2])), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=args[2], use_selection=True, export_materials="NONE")
    print("AMAL_INFO " + json.dumps({"out": args[2], "faces": len(mesh.data.polygons), "from": faces}))
    raise SystemExit(0)
if mode == "convert":
    export(args[2], [mesh])
    print("AMAL_INFO " + json.dumps({"out": args[2]}))
    raise SystemExit(0)

plan = json.load(open(args[2]))
J = plan["joints"]
P = {j["name"]: Vector((j["pos"][0], -j["pos"][2], j["pos"][1])) for j in J}
kids = {}
for j in J:
    kids.setdefault(j["parent"], []).append(j["name"])
arm_data = bpy.data.armatures.new("Skeleton")
arm = bpy.data.objects.new("Skeleton", arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
eb = {}
h = plan["height"]
for j in J:
    b = arm_data.edit_bones.new(j["name"])
    head = P[j["name"]]
    ch = kids.get(j["name"])
    if ch:
        tail = sum((P[c] for c in ch), Vector()) / len(ch) if j["role"] in ("root", "chest", "wrist", "ankle") else P[ch[0]]
    elif j["parent"]:
        d = head - P[j["parent"]]
        tail = head + (d.normalized() if d.length > 1e-6 else Vector((0, 0, 1))) * max(d.length * 0.5, h * 0.02)
    else:
        tail = head + Vector((0, 0, h * 0.05))
    if (tail - head).length < h * 0.005:
        tail = head + Vector((0, 0, h * 0.02))
    b.head, b.tail = head, tail
    eb[j["name"]] = b
for j in J:
    if j["parent"]:
        eb[j["name"]].parent = eb[j["parent"]]
        eb[j["name"]].use_connect = False
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
mesh.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
export(args[3], [arm, mesh])
print("AMAL_INFO " + json.dumps({"fbx": args[3], "bones": len(J)}))
