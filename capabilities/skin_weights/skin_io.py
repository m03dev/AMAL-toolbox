"""skin_io - a rigged model to and from what SkinTokens needs. Run by skin_weights.py in Blender:

    blender -b --factory-startup --python skin_io.py -- prep  <rigged .fbx/.glb> <input.npz> [max_joints]
    blender -b --factory-startup --python skin_io.py -- apply <rigged .fbx/.glb> <weights.npz> <out .fbx/.glb>

prep: the skin (the visible meshes the skeleton deforms - the same ones AMAL's creature_anim.py checks) in world space at
rest, as triangles, and the skeleton's deforming joints (heads, parents, names) in depth-first order with the root first
(SkinTokens' tokenizer reads a skeleton that way: a joint whose parent is not the joint before it starts a branch).
Twist / roll helpers sit out when there are more joints than `max_joints` (the limb bone they ride on takes their share,
as in creature_anim's bone heat); several roots get one joint above them, marked `synthetic` (its weight goes back to
the real joints). Each mesh's name and vertex count are kept, so weights come back by mesh name + vertex index.

apply: the weights (per vertex: up to 4 joints by name and their weights) onto the same model - every vertex group of a
bone is replaced, a joint this skeleton does not have gives its share to the others, each vertex is normalised - and
the model is written again with the SAME skeleton (names, rest pose), so its controls and clips still drive it.
"""
import os, sys

HELPER_WORDS = ("twist", "roll")


def is_helper(name):
    """A twist / roll helper bone (AdvancedSkeleton's ElbowPart1_R, ShoulderPart2_L; other rigs' Twist / Roll bones)."""
    n = name.lower()
    return ("part" in n and any(c.isdigit() for c in n)) or any(w in n for w in HELPER_WORDS)


def pick_joints(names, parents, deform, weighted, max_joints):
    """Which joints SkinTokens gets, and their parents among them. names/parents (index, -1 = root)/deform/weighted
    (has any skin weight now) are per bone. Returns (order, new_parents, synthetic): order = bone indices depth-first
    from the root (a synthetic root above several roots is -1 in order)."""
    n = len(names)
    keep = [deform[i] for i in range(n)]
    if sum(keep) > max_joints:
        keep = [keep[i] and not is_helper(names[i]) for i in range(n)]
    if sum(keep) > max_joints and any(keep[i] and weighted[i] for i in range(n)):
        keep = [keep[i] and weighted[i] for i in range(n)]
    if sum(keep) > max_joints:
        raise ValueError(f"{sum(keep)} deforming joints besides twist helpers - more than SkinTokens takes ({max_joints})")
    if not any(keep):
        raise ValueError("the skeleton has no deforming joints")

    def kept_parent(i):
        p = parents[i]
        while p != -1 and not keep[p]:
            p = parents[p]
        return p
    kp = {i: kept_parent(i) for i in range(n) if keep[i]}
    kids = {i: [] for i in kp}
    roots = []
    for i in range(n):          # bone order: children stay in the skeleton's own order
        if i in kp:
            (roots if kp[i] == -1 else kids[kp[i]]).append(i)
    order, stack = [], list(reversed(roots))
    while stack:
        u = stack.pop()
        order.append(u)
        stack.extend(reversed(kids[u]))
    pos = {b: k for k, b in enumerate(order)}
    new_parents = [-1 if kp[b] == -1 else pos[kp[b]] for b in order]
    synthetic = [False] * len(order)
    if len(roots) > 1:
        order = [-1] + order
        new_parents = [-1] + [0 if p == -1 else p + 1 for p in new_parents]
        synthetic = [True] + synthetic
    return order, new_parents, synthetic


def merge_weights(idx, w, names, here):
    """One vertex's (joint index, weight) pairs -> {bone name: weight} over the bones this skeleton has, summing to 1."""
    out = {}
    for j, x in zip(idx, w):
        n = names[int(j)]
        if x > 1e-4 and n in here:
            out[n] = out.get(n, 0.0) + float(x)
    t = sum(out.values())
    return {k: v / t for k, v in out.items()} if t > 0 else {}


# ---------------------------------------------------------------- Blender side
def load(path):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    # the same importer and options as creature_anim.py, so the objects, names and vertex order are the same there
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=True)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        raise SystemExit(f"AMAL_SPEC_ERROR skin_weights takes a rigged .fbx or .glb, not {ext}")
    sc = bpy.context.scene
    arm = next((o for o in sc.objects if o.type == "ARMATURE"), None)
    if arm is None:
        raise SystemExit("AMAL_SPEC_ERROR the file has no skeleton (rig it first)")
    meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_get() and not o.hide_viewport]
    skinned = [o for o in meshes if any(m.type == "ARMATURE" for m in o.modifiers)]
    meshes = skinned or meshes or [o for o in sc.objects if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    if not meshes:
        raise SystemExit("AMAL_SPEC_ERROR the file has no mesh to skin")
    return arm, meshes


def prep(src, dst, max_joints):
    import numpy as np
    arm, meshes = load(src)
    W = arm.matrix_world
    bones = list(arm.data.bones)
    names = [b.name for b in bones]
    col = {n: i for i, n in enumerate(names)}
    parents = [col[b.parent.name] if b.parent else -1 for b in bones]
    weighted = [False] * len(bones)
    verts, faces, mnames, counts = [], [], [], []
    off = 0
    for o in meshes:
        groups = {g.index: g.name for g in o.vertex_groups}
        M = o.matrix_world
        for v in o.data.vertices:
            verts.append(tuple(M @ v.co))
            for g in v.groups:
                if g.weight > 1e-4 and groups.get(g.group) in col:
                    weighted[col[groups[g.group]]] = True
        o.data.calc_loop_triangles()
        faces.extend(tuple(off + i for i in t.vertices) for t in o.data.loop_triangles)
        mnames.append(o.name)
        counts.append(len(o.data.vertices))
        off += len(o.data.vertices)
    order, new_parents, synthetic = pick_joints(names, parents, [b.use_deform for b in bones], weighted, max_joints)
    heads = [W @ bones[i].head_local if i >= 0 else None for i in order]
    real = [h for h in heads if h is not None]
    if heads[0] is None:     # the joint above several roots: where they are, on average
        heads[0] = sum(real[1:], real[0]) / len(real)
    tails = [W @ bones[i].tail_local if i >= 0 else heads[k] for k, i in enumerate(order)]
    jn = ["amal_skin_root" if i < 0 else names[i] for i in order]
    np.savez_compressed(dst, vertices=np.array(verts, np.float32), faces=np.array(faces, np.int32),
                        mesh_names=np.array(mnames), mesh_counts=np.array(counts, np.int32),
                        joint_names=np.array(jn), parents=np.array(new_parents, np.int32),
                        joints=np.array([tuple(h) for h in heads], np.float32),
                        lengths=np.array([(t - h).length for t, h in zip(tails, heads)], np.float32),
                        synthetic=np.array(synthetic))
    dropped = len([b for b in bones if b.use_deform]) - (len(order) - sum(synthetic))
    print(f"AMAL_SKIN_PREP {len(verts)} vertices, {len(faces)} triangles in {len(meshes)} mesh(es); {len(order)} joints"
          + (f" ({dropped} helper / unweighted joints sit out)" if dropped else "") + (" + one root above several" if any(synthetic) else ""))


def apply(src, weights, dst):
    import bpy
    import numpy as np
    arm, meshes = load(src)
    d = np.load(weights)
    names = [str(x) for x in d["joint_names"]]
    here = {b.name for b in arm.data.bones}
    idx, w = d["idx"], d["w"]
    start, done = 0, 0
    for mname, n in zip(d["mesh_names"], d["mesh_counts"]):
        mname, n = str(mname), int(n)
        rows = slice(start, start + n)
        start += n
        o = next((m for m in meshes if m.name == mname), None)
        if o is None or len(o.data.vertices) != n:
            print(f"skin: {mname} skipped ({'not in this model' if o is None else 'its vertex count differs'})")
            continue
        for g in [g for g in o.vertex_groups if g.name in here]:
            o.vertex_groups.remove(g)
        vg = {}
        for vi, (ii, ww) in enumerate(zip(idx[rows], w[rows])):
            for bn, x in merge_weights(ii, ww, names, here).items():
                if bn not in vg:
                    vg[bn] = o.vertex_groups.new(name=bn)
                vg[bn].add([vi], x, "REPLACE")
        if not any(m.type == "ARMATURE" for m in o.modifiers):
            o.modifiers.new("Armature", "ARMATURE").object = arm
        done += 1
    if not done:
        raise SystemExit("AMAL_SPEC_ERROR none of the weights' meshes is in this model (a different file?)")
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm] + meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    if dst.lower().endswith(".fbx"):
        # creature_anim.py's export settings: the skeleton comes back as it went in
        bpy.ops.export_scene.fbx(filepath=dst, use_selection=True, object_types={"ARMATURE", "MESH"}, bake_anim=False,
                                 add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", axis_forward="-Z",
                                 axis_up="Y", apply_scale_options="FBX_SCALE_ALL", mesh_smooth_type="FACE")
    else:
        bpy.ops.export_scene.gltf(filepath=dst, use_selection=True, export_format="GLB", export_animations=False)
    print(f"AMAL_SKIN_APPLIED {done} mesh(es) -> {dst}")


def load_meshes(path):
    """A bare model (no skeleton needed): its visible meshes, imported the way creature_anim.py imports them."""
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=True)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit(f"AMAL_SPEC_ERROR auto_rig takes a .glb, .fbx or .obj, not {ext}")
    sc = bpy.context.scene
    for o in [o for o in sc.objects if o.type == "ARMATURE"]:   # an old skeleton goes: a new one is made
        bpy.data.objects.remove(o, do_unlink=True)
    meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_get() and not o.hide_viewport]
    if not meshes:
        raise SystemExit("AMAL_SPEC_ERROR the file has no mesh")
    for o in meshes:
        for m in [m for m in o.modifiers if m.type == "ARMATURE"]:
            o.modifiers.remove(m)
        o.vertex_groups.clear()
    return meshes


def mesh_prep(src, dst):
    """auto_rig: only the mesh (world space, triangles, each mesh's name and vertex count) - no skeleton."""
    import numpy as np
    meshes = load_meshes(src)
    verts, faces, mnames, counts, off = [], [], [], [], 0
    for o in meshes:
        M = o.matrix_world
        verts.extend(tuple(M @ v.co) for v in o.data.vertices)
        o.data.calc_loop_triangles()
        faces.extend(tuple(off + i for i in t.vertices) for t in o.data.loop_triangles)
        mnames.append(o.name)
        counts.append(len(o.data.vertices))
        off += len(o.data.vertices)
    np.savez_compressed(dst, vertices=np.array(verts, np.float32), faces=np.array(faces, np.int32),
                        mesh_names=np.array(mnames), mesh_counts=np.array(counts, np.int32))
    print(f"AMAL_SKIN_PREP {len(verts)} vertices, {len(faces)} triangles in {len(meshes)} mesh(es); no skeleton (auto rig)")


def tails_of(heads, parents):
    """Each joint's tail: towards its children (their average) or, for an end joint, on along its parent's direction."""
    import numpy as np
    heads = np.asarray(heads, np.float64)
    size = float(np.ptp(heads, 0).max()) or 1.0
    kids = {}
    for i, p in enumerate(parents):
        if p >= 0:
            kids.setdefault(int(p), []).append(i)
    out = []
    for i, h in enumerate(heads):
        if i in kids:
            t = heads[kids[i]].mean(0)
        elif parents[i] >= 0:
            d = h - heads[int(parents[i])]
            n = np.linalg.norm(d)
            t = h + (d / n * max(n * 0.5, size * 0.02) if n > 1e-9 else np.array([0, 0, size * 0.03]))
        else:
            t = h + np.array([0, 0, size * 0.05])
        if np.linalg.norm(t - h) < size * 0.005:      # a bone of no length is not a bone in Blender
            t = h + np.array([0, 0, size * 0.02])
        out.append(t)
    return out


def build(src, rig, dst):
    """auto_rig: a skeleton from <rig>.npz (heads, parents, names) and its skin (4 joints a vertex) on the model."""
    import bpy
    import numpy as np
    from mathutils import Vector
    meshes = load_meshes(src)
    d = np.load(rig)
    names = [str(x) for x in d["joint_names"]]
    heads, parents = d["joints"], [int(p) for p in d["parents"]]
    tails = tails_of(heads, parents)
    ad = bpy.data.armatures.new("Armature")
    arm = bpy.data.objects.new("Armature", ad)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = []
    for n, h, t in zip(names, heads, tails):
        b = ad.edit_bones.new(n)
        b.head, b.tail = Vector(tuple(map(float, h))), Vector(tuple(map(float, t)))
        eb.append(b)
    for i, p in enumerate(parents):
        if p >= 0:
            eb[i].parent = eb[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    idx, w = d["idx"], d["w"]
    start, done = 0, 0
    for mname, n in zip(d["mesh_names"], d["mesh_counts"]):
        mname, n = str(mname), int(n)
        rows = slice(start, start + n)
        start += n
        o = next((m for m in meshes if m.name == mname), None)
        if o is None or len(o.data.vertices) != n:
            print(f"skin: {mname} skipped ({'not in this model' if o is None else 'its vertex count differs'})")
            continue
        vg = {}
        for vi, (ii, ww) in enumerate(zip(idx[rows], w[rows])):
            for j, x in zip(ii, ww):
                if x <= 1e-4:
                    continue
                bn = names[int(j)]
                if bn not in vg:
                    vg[bn] = o.vertex_groups.new(name=bn)
                vg[bn].add([vi], float(x), "REPLACE")
        o.modifiers.new("Armature", "ARMATURE").object = arm
        o.parent = arm
        done += 1
    if not done:
        raise SystemExit("AMAL_SPEC_ERROR none of the rig's meshes is in this model (a different file?)")
    bpy.ops.object.select_all(action="DESELECT")
    for o in [arm] + meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    if dst.lower().endswith(".fbx"):
        bpy.ops.export_scene.fbx(filepath=dst, use_selection=True, object_types={"ARMATURE", "MESH"}, bake_anim=False,
                                 add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", axis_forward="-Z",
                                 axis_up="Y", apply_scale_options="FBX_SCALE_ALL", mesh_smooth_type="FACE")
    else:
        bpy.ops.export_scene.gltf(filepath=dst, use_selection=True, export_format="GLB", export_animations=False)
    print(f"AMAL_AUTO_RIG {len(names)} joints on {done} mesh(es) -> {dst}")


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(a) >= 3 and a[0] == "mesh":
        mesh_prep(a[1], a[2])
        raise SystemExit(0)
    if len(a) >= 4 and a[0] == "build":
        build(a[1], a[2], a[3])
        raise SystemExit(0)
    if len(a) >= 3 and a[0] == "prep":
        prep(a[1], a[2], int(a[3]) if len(a) > 3 else 150)
    elif len(a) >= 4 and a[0] == "apply":
        apply(a[1], a[2], a[3])
    else:
        raise SystemExit("usage: skin_io.py -- prep <rigged> <input.npz> [max_joints] | apply <rigged> <weights.npz> <out>")
