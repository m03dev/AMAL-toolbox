"""repose - bring a posed model into a symmetric pose, so it can be made exactly symmetric without changing its design.

    blender --background --python repose.py -- <model.glb> <plan.json> <out.glb>

A model generated from a picture keeps the picture's pose: the head turned, the tail curled to one side, one wing up and
one down. Mirroring half of it then cuts through the head and the tail and makes a different creature (a dragon came
out as two side by side, 2026-11-03). Re-posing first is how riggers do it: the model gets a skeleton (the plan from
crates/amal-core/src/skeleton.rs, `amald skeleton`), and

  - the middle chains (spine, neck, head, and the longest tail) are turned into the mirror plane, so they run straight
    down the middle instead of to one side;
  - the side whose limbs reach out further (an open wing, not a folded one) is named as the one to keep: mirroring
    that half then makes the pairs match.

The skin follows its two nearest bones (a smooth falloff, no bone heat: re-posing needs it robust, not perfect). The
re-posed model is written as glTF with its materials; AMAL then mirrors it (mesh_symmetrize), which now finds most of it
already matching. Writes <out>.glb and <out>_repose.json (what was turned, how far).
"""
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
src, plan_path, out = argv[0], argv[1], argv[2]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for o in [o for o in bpy.context.scene.objects if o.type not in ("MESH",)]:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.parent = None
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
mesh = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

plan = json.load(open(plan_path))
J = plan["joints"]
# the plan is in glTF axes (Y up); Blender is Z up: (x, y, z) -> (x, -z, y)
P = {j["name"]: Vector((j["pos"][0], -j["pos"][2], j["pos"][1])) for j in J}
cx = float(plan.get("centre_x", 0.0))
kids = {}
for j in J:
    kids.setdefault(j["parent"], []).append(j["name"])
h = float(plan["height"])

arm_data = bpy.data.armatures.new("Skeleton")
arm = bpy.data.objects.new("Skeleton", arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
eb = {}
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
segs = {n: (np.array(b.head[:]), np.array(b.tail[:])) for n, b in eb.items()}
bpy.ops.object.mode_set(mode="OBJECT")

# the skin: each vertex on its two nearest bones, weighted by inverse distance
names = list(segs)
A = np.array([segs[n][0] for n in names])
B = np.array([segs[n][1] for n in names])
V = np.array([v.co[:] for v in mesh.data.vertices])
AB = B - A
L2 = np.maximum((AB * AB).sum(1), 1e-12)
dist = np.empty((len(V), len(names)), np.float32)
for i0 in range(0, len(V), 20000):
    v = V[i0:i0 + 20000, None, :]
    t = np.clip(((v - A[None]) * AB[None]).sum(2) / L2[None], 0, 1)
    dist[i0:i0 + 20000] = np.linalg.norm(v - (A[None] + t[..., None] * AB[None]), axis=2)
near = np.argsort(dist, axis=1)[:, :2]
d2 = np.take_along_axis(dist, near, axis=1) + h * 1e-3
w = 1.0 / d2 ** 4
w /= w.sum(1, keepdims=True)
groups = {n: mesh.vertex_groups.new(name=n) for n in names}
for k in range(2):
    for bi, n in enumerate(names):
        idx = np.nonzero(near[:, k] == bi)[0]
        g = groups[n]
        for vi, wt in zip(idx.tolist(), w[idx, k].tolist()):
            g.add([vi], wt, "ADD")
mod = mesh.modifiers.new("Skeleton", "ARMATURE")
mod.object = arm
mesh.parent = arm

# what is turned
role = {j["name"]: j["role"] for j in J}
side = {j["name"]: j["side"] for j in J}
parent = {j["name"]: j["parent"] for j in J}


def chain_of(root_child):
    out, n = [], root_child
    while n:
        out.append(n)
        nxt = [c for c in kids.get(n, []) if role.get(c) == role.get(n) or role.get(n) in ("root", "spine", "chest", "neck")]
        n = nxt[0] if nxt else None
    return out


def tip_spread(chain):
    """How far the chain reaches from the mirror plane - the more spread-out side of a pair shows its true shape."""
    return max(abs(P[n].x - cx) for n in chain) if chain else 0.0


# the mirror plane: halfway between the paired limbs where they join the body (the bounding box's middle is off when
# a tail curls or a wing lifts to one side - a cut there gave two tails, 2026-11-03)
mids = sorted((P[n].x + P[n[:-2] + "_R"].x) / 2 for n in names if n.endswith("_L") and n[:-2] + "_R" in P
              and role[n] in ("scapula", "shoulder", "hip"))
if mids:
    cx = mids[len(mids) // 2]
middle = [n for n in names if role[n] in ("root", "spine", "chest", "neck", "head", "head_end")]
tails = [c for c in kids.get("Root", []) if role.get(c) == "tail"]
if tails:
    longest = max(tails, key=lambda t: sum((P[a] - P[b]).length for a, b in zip(chain_of(t)[1:], chain_of(t)))
                  + 0 * len(chain_of(t)))
    middle += chain_of(longest)
# limb pairs by name: <Name>_L <-> <Name>_R, the limb joints only (fingers follow their hand)
limb_roles = ("scapula", "shoulder", "elbow", "wrist", "hip", "knee", "ankle")
pairs = sorted({n[:-2] for n in names if n.endswith(("_L", "_R")) and role[n] in limb_roles
                and n[:-2] + "_L" in segs and n[:-2] + "_R" in segs})


def limb_chain(n):
    """The joints of the limb n belongs to (from its scapula/hip down to its wrist/ankle)."""
    top = n
    while parent.get(top) and side.get(parent[top]) == side[n]:
        top = parent[top]
    out, stack = [], [top]
    while stack:
        x = stack.pop()
        out.append(x)
        stack += kids.get(x, [])
    return out


pose = arm.pose
MAX_TURN = 60.0   # degrees: a bone that would turn more than this is read wrongly, not posed
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="POSE")
report = {"middle": []}


def turn(name, target):
    pb = pose.bones[name]
    bpy.context.view_layer.update()
    hd, tl = pb.head.copy(), pb.tail.copy()
    d = tl - hd
    if d.length < 1e-6 or target.length < 1e-6:
        return 0.0
    q = d.rotation_difference(target)
    ang = math.degrees(q.angle)
    if ang < 0.5:
        return 0.0
    pb.matrix = Matrix.Translation(hd) @ q.to_matrix().to_4x4() @ Matrix.Translation(-hd) @ pb.matrix
    bpy.context.view_layer.update()
    return ang


def depth(n):
    k = 0
    while parent.get(n):
        n = parent[n]
        k += 1
    return k


def shift(name, dx):
    """Move a bone (and everything below it) sideways."""
    pb = pose.bones[name]
    bpy.context.view_layer.update()
    pb.matrix = Matrix.Translation(Vector((dx, 0.0, 0.0))) @ pb.matrix
    bpy.context.view_layer.update()


# 0. the middle starts on the mirror plane: the body's root and each middle chain's first joint are moved onto it
report["shifted"] = []
for n in [x for x in middle if role[x] == "root" or (parent.get(x) and role.get(parent[x]) == "root")]:
    bpy.context.view_layer.update()
    dx = cx - pose.bones[n].head.x
    if abs(dx) > 0.005 * h:
        shift(n, dx)
        report["shifted"].append([n, round(dx / h, 3)])

# 1. the middle runs straight down the mirror plane (parents first, so children start from where they now are)
for n in sorted(middle, key=depth):
    if role[n] == "root":
        continue
    pb = pose.bones[n]
    d = pb.tail - pb.head
    # a very short bone's direction is noise (a medial skeleton bunches joints where parts meet): turning it would swing
    # everything beyond it - it is left as it is
    if d.length < 0.04 * h:
        continue
    t = Vector((0.0, d.y, d.z))
    if t.length > 0.2 * d.length and math.degrees(d.angle(t)) <= MAX_TURN:
        t = t.normalized() * d.length
        a = turn(n, t)
        if a:
            report["middle"].append([n, round(a, 1)])

# 2. the side to keep when the model is mirrored: the one whose limbs reach out further (an open wing shows its whole
#    shape; a folded one hides it). Mirroring the kept half makes the pairs match - they are not re-posed here.
spread = {"L": 0.0, "R": 0.0}
for base in pairs:
    for sd in ("L", "R"):
        spread[sd] += tip_spread(limb_chain(base + "_" + sd))
report["keep"] = "left" if spread["L"] >= spread["R"] else "right"
report["plane_x"] = cx
bpy.ops.object.mode_set(mode="OBJECT")
# the pose becomes the model
bpy.context.view_layer.objects.active = mesh
bpy.ops.object.modifier_apply(modifier=mod.name)
mesh.parent = None
for g in list(mesh.vertex_groups):
    mesh.vertex_groups.remove(g)
bpy.data.objects.remove(arm, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
mesh.select_set(True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True)
report.update({"source": src, "out": out, "middle_bones": len(report["middle"])})
with open(out.rsplit(".", 1)[0] + "_repose.json", "w") as fh:
    json.dump(report, fh, indent=1)
print("AMAL_INFO " + json.dumps({k: report[k] for k in ("out", "middle_bones", "keep", "plane_x")}))
