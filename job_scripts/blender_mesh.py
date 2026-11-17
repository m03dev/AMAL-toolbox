"""blender_mesh - one of Blender's mesh tools on a model, in the background (no window). The flow editor's Blender nodes
run this, as maya_mesh.py runs the Maya ones.

    blender -b --python-exit-code 1 --python blender_mesh.py -- <op> <model.glb|.fbx|.obj> <out.fbx> [key=value ...]

The tools and their settings are listed in blender_mesh.json (the flow editor builds its nodes from that list). Each
prints `AMAL_INFO {...}` (triangles, open and non-manifold edges and pieces before and after, what ran) and writes the
FBX; a tool that cannot run ends with `AMAL_SPEC_ERROR <why>` and exit code 1, so a failed step never hands on a model
it did not make.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import bmesh  # noqa: E402
import amal_bpy as L  # noqa: E402


def fail(why):
    print("AMAL_SPEC_ERROR " + why)
    sys.exit(1)


def load(path):
    """The model as one mesh object (joined), transforms applied."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        fail(f"cannot read {ext} models (glb, gltf, fbx, obj)")
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        fail(f"no mesh came in from {path}")
    for o in bpy.context.scene.objects:
        o.hide_set(False)
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for x in [x for x in bpy.context.scene.objects if x is not o]:
        bpy.data.objects.remove(x)
    return o


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def state(o):
    return {"triangles": tris(o), **L.mesh_health(o)}


def weld(o, dist):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bm.to_mesh(o.data)
    bm.free()


def apply(o, kind, **props):
    m = o.modifiers.new(kind.title(), kind)
    for k, v in props.items():
        setattr(m, k, v)
    bpy.ops.object.modifier_apply(modifier=m.name)


def run(op, o, a):
    num = lambda k, d: float(a.get(k, d))
    size = max(o.dimensions) or 1.0
    did = {}
    if op == "watertight":
        did = {"after_remesh": L.make_watertight(o, int(num("detail", L.REMESH_DETAIL)))}
    elif op == "quad_remesh":
        # QuadriFlow (Huang et al. 2018), Blender's built-in quad remesher: needs a closed manifold mesh, so it is made one
        h = L.mesh_health(o)
        if h["open_edges"] or h["non_manifold_edges"]:
            L.make_watertight(o, int(num("detail", L.REMESH_DETAIL)))
            did["made_watertight_first"] = True
        want = int(num("faces", 8000))
        # QuadriFlow only needs the shape, and its solve grows fast with the input: 60k triangles ran past ten minutes,
        # 15k took 4 s (2026-11-07) - the input is reduced to a few triangles per quad wanted first
        if tris(o) > want * 4:
            apply(o, "DECIMATE", decimate_type="COLLAPSE", ratio=max(0.001, want * 4 / tris(o)), use_collapse_triangulate=True)
        r = bpy.ops.object.quadriflow_remesh(target_faces=want, use_mesh_symmetry=False, use_preserve_sharp=True,
                                             use_preserve_boundary=True, smooth_normals=True, seed=0)
        if "FINISHED" not in r:
            fail("QuadriFlow did not finish on this mesh")
    elif op == "decimate":
        want = int(num("triangles", 20000))
        if tris(o) > want:
            apply(o, "DECIMATE", decimate_type="COLLAPSE", ratio=max(0.001, want / tris(o)), use_collapse_triangulate=True)
    elif op == "weld":
        weld(o, num("distance", 0.0001))
    elif op == "symmetrize":
        # cut at the middle, keep one half, mirror it back with the seam merged (Blender's Symmetrize left the two halves
        # apart on a remeshed surface: 1 piece became 4, 2026-11-07)
        keep_plus = str(a.get("keep", "+x")).strip() != "-x"
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.bisect(plane_co=(0, 0, 0), plane_no=(1, 0, 0), clear_inner=keep_plus, clear_outer=not keep_plus,
                            use_fill=False, threshold=size * 1e-5)
        bpy.ops.object.mode_set(mode="OBJECT")
        apply(o, "MIRROR", use_axis=(True, False, False), use_clip=True, use_mirror_merge=True,
              merge_threshold=size * float(a.get("seam", 0.002)))
        h = L.mesh_health(o)
        if h["open_edges"] or h["non_manifold_edges"] or h["pieces"] > 1:
            # where the model crossed the middle more than once (an arm holding a prop over it) the halves overlap: one
            # closed surface again
            did = {"made_watertight_after": L.make_watertight(o, int(num("detail", L.REMESH_DETAIL)))}
    elif op == "fill_holes":
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.fill_holes(sides=int(num("sides", 0)))
        bpy.ops.object.mode_set(mode="OBJECT")
    elif op == "smooth":
        apply(o, "LAPLACIANSMOOTH", iterations=int(num("rounds", 3)), lambda_factor=num("strength", 0.5),
              use_volume_preserve=True, use_normalized=True)
    elif op == "triangulate":
        apply(o, "TRIANGULATE", quad_method="BEAUTY", ngon_method="BEAUTY")
    elif op == "recalc_normals":
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif op == "remove_small":
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        seen, parts = set(), []
        for f in bm.faces:
            if f.index in seen:
                continue
            stack, part = [f], []
            seen.add(f.index)
            while stack:
                x = stack.pop()
                part.append(x)
                for e in x.edges:
                    for y in e.link_faces:
                        if y.index not in seen:
                            seen.add(y.index)
                            stack.append(y)
            parts.append(part)
        big = max((len(p) for p in parts), default=0)
        gone = [p for p in parts if len(p) < num("keep", 0.02) * big]
        bmesh.ops.delete(bm, geom=[f for p in gone for f in p], context="FACES")
        bm.to_mesh(o.data)
        bm.free()
        did = {"pieces": len(parts), "removed": len(gone)}
    elif op == "unwrap":
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(num("angle", 66)), island_margin=0.002)
        bpy.ops.uv.pack_islands(rotate=True, margin=0.002)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif op == "shade_smooth":
        for p in o.data.polygons:
            p.use_smooth = True
        try:
            bpy.ops.object.shade_auto_smooth(angle=math.radians(num("angle", 40)))
        except Exception:  # noqa: BLE001 - the operator's name changed between Blender versions
            pass
    else:
        fail(f"no mesh tool called {op} (see blender_mesh.json)")
    return did


def export(o, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    if out.lower().endswith((".glb", ".gltf")):
        bpy.ops.export_scene.gltf(filepath=out, use_selection=True, export_format="GLB")
    else:
        bpy.ops.export_scene.fbx(filepath=out, use_selection=True, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z",
                                 axis_up="Y", mesh_smooth_type="FACE", add_leaf_bones=False, path_mode="COPY",
                                 embed_textures=True)
    if not os.path.isfile(out):
        fail(f"Blender wrote no {out}")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) < 3:
        fail("usage: blender_mesh.py <op> <model> <out.fbx> [key=value ...]")
    op, src, out = args[0], args[1], args[2]
    a = dict(x.split("=", 1) for x in args[3:] if "=" in x)
    if not os.path.isfile(src):
        fail(f"no model at {src}")
    try:
        o = load(src)
        before = state(o)
        did = run(op, o, a)
        after = state(o)
        export(o, out)
        print("AMAL_INFO " + json.dumps({"op": op, "out": out, "before": before, "after": after, **did}))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        fail(f"{op}: {type(e).__name__}: {str(e).strip()[:400]}")
