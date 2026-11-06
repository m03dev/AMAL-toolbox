"""Make a 3D model symmetrical left to right: find its own mirror plane, keep one half, mirror it, weld the seam.

Run in Blender:  blender -b --factory-startup --python symmetrize.py -- <in.glb|fbx|obj> <out.glb> [keep]
  keep = auto (default: the half with more surface - the more complete side) | left | right

Mirroring a WHOLE model onto itself doubles it (two heads, four wings: 2026-11-03). The model is cut at its mirror
plane first and only the kept half is mirrored. The plane is found, not assumed: the model is turned about its up axis
until its two halves match best (a model generated from a three-quarter picture is a few degrees off), and the turn
and the match are reported. Materials and UVs stay (the mirrored half reuses the kept half's texture).
Writes <out.glb> and <out>_symmetry.json.
"""
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
if len(argv) < 2:
    print("usage: symmetrize.py <in> <out.glb> [auto|left|right]")
    sys.exit(2)
src, out = os.path.abspath(argv[0]), os.path.abspath(argv[1])
keep = (argv[2] if len(argv) > 2 else "auto").lower()
if len(argv) > 3 and argv[3] not in ("", "search"):
    os.environ["MODO_SYM_PLANE_X"] = argv[3]

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(src)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=src)
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=src)
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=src)
else:
    print(f"MODO_ERROR cannot read {ext} files (glb, gltf, fbx, obj)")
    sys.exit(2)

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    print("MODO_ERROR no mesh in " + src)
    sys.exit(2)
# rigs and their modifiers would undo the cut: the mesh alone, as it stands
for o in meshes:
    for m in list(o.modifiers):
        o.modifiers.remove(m)
    o.parent = None
for o in [o for o in bpy.context.scene.objects if o.type != "MESH"]:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = obj.data

# Blender is Z-up: the mirror plane is vertical; left-right is X
pts = [v.co.copy() for v in me.vertices]
n = len(pts)
step = max(1, n // 4000)
sample = pts[::step]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
size = (hi - lo).length or 1.0
near = size * 0.015
tree = KDTree(n)
for i, p in enumerate(pts):
    tree.insert(p, i)
tree.balance()


def match(deg):
    """Share of the sample whose mirror image (after turning by deg about Z, mirror at the median X) lands on the mesh."""
    r = Matrix.Rotation(math.radians(deg), 3, "Z")
    ri = r.inverted()
    xs = sorted((r @ p).x for p in sample)
    mid = xs[len(xs) // 2]
    hit = 0
    for p in sample:
        q = r @ p
        m = ri @ Vector((2 * mid - q.x, q.y, q.z))
        if tree.find(m)[2] <= near:
            hit += 1
    return hit / len(sample), mid


# a known mirror plane (a model MODO re-posed: its middle already runs down x = MODO_SYM_PLANE_X): used as it is
known_x = os.environ.get("MODO_SYM_PLANE_X")
best = (-1.0, 0.0, 0.0)
# any heading: a model generated from a side or three-quarter picture can face any way (a dragon facing sideways was
# mirrored across its length and came out as two dragons side by side, 2026-11-03)
for deg in (range(-90, 91, 3) if known_x is None else []):
    s, mid = match(deg)
    if s > best[0]:
        best = (s, deg, mid)
for deg in ([best[1] + d * 0.5 for d in range(-5, 6)] if known_x is None else []):
    s, mid = match(deg)
    if s > best[0]:
        best = (s, deg, mid)
if known_x is not None:
    s0, _ = match(0.0)
    best = (s0, 0.0, float(known_x))
before, turn, mid = best
print(f"mirror plane: turned {turn:.1f} deg about the up axis, {before * 100:.0f}% of the model already mirrors onto itself")
# a model whose two sides match less than 60% is posed (the owner's dragon, head turned and tail curled: 41%) (a wing up, the head turned, a tail curled across): mirroring
# half of it makes a different creature or two of it. Nothing is written; the fix is a straight, symmetric pose first.
MIN_MATCH = float(os.environ.get("MODO_SYM_MIN", "0.6"))
if before < MIN_MATCH and known_x is None:
    report = {"source": src, "mirrored_before": round(before, 3), "turned_deg": round(turn, 2), "out": None,
              "error": f"only {before * 100:.0f}% of the model mirrors onto itself at its best plane - it is posed, not "
                       "symmetric, so mirroring would make a different model. Make it in a straight, symmetric pose first "
                       "(a front-facing T-pose reference picture), then symmetrize"}
    with open(os.path.splitext(out)[0] + "_symmetry.json", "w") as fh:
        json.dump(report, fh, indent=1)
    print("MODO_ERROR " + report["error"])
    sys.exit(3)

# turn the model so its mirror plane is X = 0
obj.matrix_world = Matrix.Translation((-mid, 0, 0)) @ Matrix.Rotation(math.radians(turn), 4, "Z")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

base = bmesh.new()
base.from_mesh(me)
# a glTF arrives split at every UV seam (31 loose pieces for one fox): one surface again before the cut, or the weld and
# the faces' facing are worked out per piece - the fox came out with 191 open edges and patches turned inside out
# (2026-11-06). The UVs live on the faces' corners, so welding vertices keeps them.
bmesh.ops.remove_doubles(base, verts=base.verts[:], dist=size * 1e-5)
base.faces.ensure_lookup_table()


def islands(b, min_share=0.01):
    """Pieces of the mesh with at least min_share of its vertices (a part cut off at the plane floats on its own)."""
    seen, sizes = set(), []
    b.verts.ensure_lookup_table()
    for v in b.verts:
        if v.index in seen:
            continue
        stack, size = [v], 0
        seen.add(v.index)
        while stack:
            x = stack.pop()
            size += 1
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        sizes.append(size)
    total = sum(sizes) or 1
    return sum(1 for z in sizes if z / total >= min_share)


def side_area(sign):
    return sum(f.calc_area() for f in base.faces if sign * f.calc_center_median().x > 0)


def mirrored(side):
    """The model cut at the plane, the `side` half kept and mirrored onto the other: a new bmesh. Blender's own
    Symmetrize does the cut, the mirror and the weld of the seam in one step and keeps every face facing out - the
    hand-made version (snap the vertices near the plane onto it, mirror, weld, recalculate the facing) tore cracks along
    the middle and turned patches inside out (2026-11-06)."""
    b = base.copy()
    # Blender's +X is the model's left when it faces -Y (glTF front)
    bmesh.ops.symmetrize(b, input=b.verts[:] + b.edges[:] + b.faces[:],
                         direction="X" if side == "left" else "-X", dist=near * 0.2)
    # a face lying flat in the mirror plane (where the generator left a sliver inside the snout) is inside the model and
    # only ever had one neighbour: it showed as 34 open edges down the fox's middle (2026-11-06). Gone, the faces on
    # either side close the seam.
    flat = [f for f in b.faces if all(abs(v.co.x) < near * 0.05 for v in f.verts)]
    if flat:
        bmesh.ops.delete(b, geom=flat, context="FACES_ONLY")
        bmesh.ops.remove_doubles(b, verts=[v for v in b.verts if abs(v.co.x) < near * 0.05], dist=near * 0.2)
    return b


def open_edges(b):
    """Edges with a face on one side only: holes (and the seams of a model that was not one surface)."""
    return sum(1 for e in b.edges if len(e.link_faces) == 1)


pieces_before = islands(base)
holes_before = open_edges(base)
if keep in ("left", "right"):
    order = [keep]
else:
    # the more complete side first (more surface: a wing folded behind the body has less of it showing)
    order = ["left", "right"] if side_area(1) >= side_area(-1) else ["right", "left"]
tried = []
for side in order + [x for x in ("left", "right") if x not in order]:
    b = mirrored(side)
    tried.append((islands(b), side, b))
    if tried[-1][0] <= pieces_before:
        break
# a cut that leaves a part floating on its own (a tail that curls across the middle, cut off at the plane) is not the
# model any more: the other half is tried, and the fewest floating parts win
pieces_after, keep, bm = min(tried, key=lambda t: t[0])
for t in tried:
    if t[2] is not bm:
        t[2].free()
warning = None
if pieces_after > pieces_before:
    warning = (f"{pieces_after - pieces_before} part(s) float free after mirroring (both halves tried): a part crossing "
               "the middle in this pose was cut off - pose it straight, or join it by hand")
    print("MODO_WARNING " + warning)
holes_after = open_edges(bm)
# the mirrored model must not have more holes than the model had: a seam that did not weld is a crack an engine shows
if holes_after > holes_before * 2 + 8:
    msg = (f"mirroring left {holes_after} open edges (the model had {holes_before}): the seam did not weld")
    warning = f"{warning}; {msg}" if warning else msg
    print("MODO_WARNING " + msg)
bm.to_mesh(me)
bm.free()
base.free()
me.update()

# stand it back on the floor at the origin
bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
obj.location.z -= min(p.z for p in bb)
bpy.ops.object.transform_apply(location=True)

after_pts = [v.co.copy() for v in obj.data.vertices]
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False)
report = {"source": src, "kept": keep, "turned_deg": round(turn, 2), "mirrored_before": round(before, 3),
          "vertices_before": n, "vertices_after": len(after_pts), "pieces_before": pieces_before, "pieces_after": pieces_after,
          "open_edges_before": holes_before, "open_edges_after": holes_after,
          "halves_tried": [t[1] for t in tried], "warning": warning, "out": out}
with open(os.path.splitext(out)[0] + "_symmetry.json", "w") as fh:
    json.dump(report, fh, indent=1)
print("MODO_INFO " + json.dumps(report))
