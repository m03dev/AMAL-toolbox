"""glb_finish - turn a generated 3D model (TRELLIS.2 / any .glb) into an editable game asset. Every job gets it in scripts/.

    blender --background --python-exit-code 1 --python scripts/glb_finish.py -- renders/<in>.glb <name> [tris] [height_m] [tex]

The generator's own texture maps are not usable (owner 2026-10-31: the fox's normal, AO and base colour were
"complete garbage"): its UVs are thousands of tiny islands and its normal/AO bakes are noisy. So the generated mesh is
only the SOURCE here:
  1. import it, join it, stand it on the floor, scale it to `height_m` (0 = keep);
  2. a clean low copy: rebuilt watertight (one closed surface - the generated mesh is a triangle soup of thousands of
     open pieces that no retopology, reduce or rig can use), reduced to `tris` triangles (0 = keep), shaded smooth;
  3. fresh UVs on the low copy (xatlas: large charts packed for the texture size; Smart UV Project if it can't load);
  4. bake from the source onto the low copy with Cycles (GPU when there is one): base colour (the source's Base Color
     itself, through emission - no light, metal or roughness in it),
     a tangent-space normal map (the source's detail on the low mesh) and ambient occlusion - `tex` px square;
  5. a clean material that uses the three maps; the source is removed.
Writes renders/<name>_basecolor.png, _normal.png, _ao.png, renders/<name>.fbx (for the engines) and renders/<name>.glb
(the window's preview), scenes/<name>.blend, renders/<name>.png,
renders/<name>_views.png and prints AMAL_INFO {...} (triangles before / after, size, maps).
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import amal_bpy as L  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(args) < 2:
    raise SystemExit("usage: blender -b --python glb_finish.py -- renders/in.glb name [tris] [height_m] [tex]")
ROOT = os.path.dirname(HERE)
src = args[0] if os.path.isabs(args[0]) else os.path.join(ROOT, args[0])
name = args[1]
tris = int(float(args[2])) if len(args) > 2 else 0
height = float(args[3]) if len(args) > 3 else 0.0
tex = int(float(args[4])) if len(args) > 4 else 2048
# "quads": the low copy is rebuilt as an all-quad mesh with even edge flow (Blender's QuadriFlow) - what a rig and an
# animator need; anything else: reduced as triangles
quads = len(args) > 5 and args[5].strip().lower().startswith("quad")
REN = os.path.join(ROOT, "renders")
os.makedirs(REN, exist_ok=True)

L.start(os.path.join(HERE, "glb_finish.py"))
# a model from any step: glTF, or FBX / OBJ (what Maya's mesh tools hand on)
_ext = os.path.splitext(src)[1].lower()
if _ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=src)
elif _ext == ".obj":
    bpy.ops.wm.obj_import(filepath=src)
else:
    bpy.ops.import_scene.gltf(filepath=src)


meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    print("AMAL_SPEC_ERROR the file has no mesh")
    raise SystemExit(2)


def only(o):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    return sum(sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).data.polygons) for o in objs)


before = count(meshes)
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
high = bpy.context.view_layer.objects.active
high.name = name + "_source"
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in [o for o in bpy.context.scene.objects if o.type == "EMPTY"]:
    bpy.data.objects.remove(o)

# floor + size on the source, so the low copy and the bake share one space
if height > 0:
    lo, hi = L.bounds(high)
    if hi.z - lo.z > 0:
        high.scale = (height / (hi.z - lo.z),) * 3
        bpy.ops.object.transform_apply(scale=True)
lo, hi = L.bounds(high)
high.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
bpy.ops.object.transform_apply(location=True)
size = L.bounds(high)[1] - L.bounds(high)[0]

# 2. the clean low copy
only(high)
bpy.ops.object.duplicate()
low = bpy.context.view_layer.objects.active
low.name = name
low.data = low.data.copy()
health_in = L.mesh_health(low)
detail = int(os.environ.get("AMAL_REMESH_DETAIL", L.REMESH_DETAIL))
health = L.make_watertight(low, detail)
print("AMAL_STEP watertight: %(pieces)s piece(s), %(open_edges)s open and %(non_manifold_edges)s non-manifold edges" % health
      + " (the generated mesh had %(pieces)s pieces, %(open_edges)s open edges)" % health_in)
if health["open_edges"] or health["non_manifold_edges"]:
    raise SystemExit(f"the low copy is not watertight after the remesh: {health}")
n = count([low])


def reduce_to(obj, want, triangulate):
    have = count([obj])
    if want and have > want:
        m = obj.modifiers.new("Reduce", "DECIMATE")
        m.ratio = max(0.01, want / have)
        m.use_collapse_triangulate = triangulate
        bpy.ops.object.modifier_apply(modifier=m.name)


made_quads = False
if quads and tris:
    # QuadriFlow works from a mesh a few times the target (on the whole voxel mesh it runs for many minutes); the
    # target is in quads: half the triangle budget. The model's left-right symmetry is kept. If it cannot do this
    # mesh, the triangle reduction below still gives a game-ready copy and the step says so.
    only(low)
    # its base is the watertight surface at coarser voxels - still one closed manifold, which QuadriFlow needs (a base
    # reduced by collapsing edges was not: QuadriFlow left it untouched, "450000 faces, 0% quads", 2026-11-12)
    L.make_watertight(low, 160)
    try:
        # asked the way it most often takes a mesh first; a way it cancels gives way to the plainer one
        r = set()
        for sym, keep in ((True, True), (False, True), (False, False)):
            r = bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=max(200, tris // 2), use_mesh_symmetry=sym,
                                                 use_preserve_sharp=keep, use_preserve_boundary=keep, seed=0)
            if "FINISHED" in r:
                break
            print("AMAL_STEP topology: QuadriFlow cancelled (symmetry %s, sharp edges kept %s) - trying it plainer" % (sym, keep))
        polys = low.data.polygons
        four = sum(1 for p in polys if len(p.vertices) == 4)
        made_quads = "FINISHED" in r and len(polys) > 0 and four >= len(polys) * 0.9
        print("AMAL_STEP topology: QuadriFlow (%s) made %d faces, %d%% quads" % (",".join(sorted(r)), len(polys), round(100 * four / max(1, len(polys)))))
        # QuadriFlow's target is a wish, not a limit: it overshot a 20,000 budget sevenfold on a drone (137,552
        # triangles, 2026-11-13). Over the budget by more than a third, it is asked once more for fewer by the same
        # ratio; still over, the triangle reduction below holds the budget
        if made_quads and count([low]) > tris * 1.33:
            ratio = tris / count([low])
            L.make_watertight(low, 160)
            r = bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=max(200, int(tris // 2 * ratio)), use_mesh_symmetry=False,
                                                 use_preserve_sharp=True, use_preserve_boundary=True, seed=0)
            got = count([low])
            made_quads = "FINISHED" in r and got <= tris * 1.33
            print("AMAL_STEP topology: over the %d budget - QuadriFlow again: %d triangles%s" % (tris, got, "" if made_quads else ", reduced as triangles instead"))
    except Exception as e:  # noqa: BLE001 - QuadriFlow refuses some meshes; the triangle copy is the way left
        print("AMAL_STEP topology: QuadriFlow could not rebuild this mesh as quads (%s) - reduced as triangles instead" % e)
if not made_quads:
    reduce_to(low, tris, True)
print("AMAL_STEP budget: %d triangles for a budget of %d" % (count([low]), tris))
for p in low.data.polygons:
    p.use_smooth = True
try:
    bpy.ops.object.shade_auto_smooth(angle=0.7)
except Exception:  # noqa: BLE001 - older/newer API names
    pass

# 3. fresh UVs: few large charts, packed tight. Smart UV Project cut a reduced scan into thousands of crumbs (2026-11-01:
#    a dragon's 2048 map was mostly black gaps and dots, so its colour came out blotchy and its seams dark); xatlas -
#    the unwrapper TRELLIS, Hunyuan3D and most game tools use - makes large charts and packs them for the texture size.
def xatlas_uvs(obj):
    # Blender's own folder is read-only (C:\\Program Files): xatlas goes into a folder of AMAL's in the user's home
    lib = os.path.join(os.path.expanduser("~"), ".amal", "blender-pylib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    try:
        import xatlas  # noqa: F401
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "ensurepip", "--user"], capture_output=True)
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", lib, "xatlas"], capture_output=True, text=True)
        if r.returncode:
            print("AMAL_NOTE xatlas did not install: " + (r.stderr or r.stdout)[-400:])
    try:
        import numpy as np
        import xatlas
    except ImportError:
        return False
    me = obj.data
    me.calc_loop_triangles()
    v = np.array([vt.co[:] for vt in me.vertices], dtype=np.float32)
    f = np.array([t.vertices[:] for t in me.loop_triangles], dtype=np.uint32)
    atlas = xatlas.Atlas()
    atlas.add_mesh(v, f)
    po = xatlas.PackOptions()
    po.resolution = tex
    po.padding = 4
    po.bilinear = True
    atlas.generate(xatlas.ChartOptions(), po)
    _, idx, uvs = atlas[0]
    uv = me.uv_layers.active.data
    for t, tri in zip(me.loop_triangles, idx):
        for loop, k in zip(t.loops, tri):
            uv[loop].uv = uvs[k]
    return True


while low.data.uv_layers:
    low.data.uv_layers.remove(low.data.uv_layers[0])
low.data.uv_layers.new(name="UVMap")
only(low)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()   # one loop per triangle corner: xatlas works on triangles
bpy.ops.object.mode_set(mode="OBJECT")
UNWRAP = "xatlas" if xatlas_uvs(low) else "smart project"
if UNWRAP != "xatlas":
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.003, area_weight=0.0)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.002)
    bpy.ops.object.mode_set(mode="OBJECT")

# 4. bake from the source
sc = bpy.context.scene
sc.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
                sc.cycles.device = "GPU"
                break
        except Exception:  # noqa: BLE001
            continue
except Exception:  # noqa: BLE001
    pass
sc.cycles.samples = 16
low.data.materials.clear()
mat = bpy.data.materials.new(name + "_mat")
mat.use_nodes = True
nt = mat.node_tree
bsdf = next(nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED")
low.data.materials.append(mat)
cage = max(0.002, size.length * 0.01)
maps = {}


def bake(kind, label, colorspace, **kw):
    img = bpy.data.images.new(f"{name}_{label}", tex, tex, alpha=False)
    img.colorspace_settings.name = colorspace
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    for nd in nt.nodes:
        nd.select = False
    node.select = True
    nt.nodes.active = node
    to_active = kw.pop("to_active", True)
    bpy.ops.object.select_all(action="DESELECT")
    if to_active:
        high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.bake(type=kind, use_selected_to_active=to_active, cage_extrusion=cage, margin=8, **kw)
    path = os.path.join(REN, f"{name}_{label}.png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    maps[label] = os.path.relpath(path, ROOT).replace("\\", "/")
    return node


def show_base_colour(obj):
    """Each of the source's materials shows only what feeds its Base Color, as light: the colour bake then copies the
    colour itself, whatever the material's metal, roughness or lighting (a diffuse-colour bake of a model the generator
    called fully metallic came out black, 2026-11-02)."""
    for slot in obj.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        t = m.node_tree
        out = next((nd for nd in t.nodes if nd.type == "OUTPUT_MATERIAL"), None)
        p = next((nd for nd in t.nodes if nd.type == "BSDF_PRINCIPLED"), None)
        if not out or not p:
            continue
        em = t.nodes.new("ShaderNodeEmission")
        src = p.inputs["Base Color"]
        if src.is_linked:
            t.links.new(src.links[0].from_socket, em.inputs["Color"])
        else:
            em.inputs["Color"].default_value = src.default_value
        t.links.new(em.outputs["Emission"], out.inputs["Surface"])


show_base_colour(high)
b_col = bake("EMIT", "basecolor", "sRGB")
b_nrm = bake("NORMAL", "normal", "Non-Color", normal_space="TANGENT")
sc.cycles.samples = 64
high.hide_render = True   # the source sits in the same space: it would shade the low copy black
b_ao = bake("AO", "ao", "Non-Color", to_active=False)

# 5. the clean material: base colour (lightly multiplied by AO), normal map
mix = nt.nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
mix.blend_type = "MULTIPLY"
mix.inputs[0].default_value = 0.35
nt.links.new(b_col.outputs["Color"], mix.inputs[6])
nt.links.new(b_ao.outputs["Color"], mix.inputs[7])
nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
nmap = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(b_nrm.outputs["Color"], nmap.inputs["Color"])
nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
bsdf.inputs["Roughness"].default_value = 0.6
bpy.data.objects.remove(high)

after = count([low])
L.ground(max(3.0, size.length * 5), L.mat("Floor", "#3b3b3b", rough=0.85))
L.frame(fill=1.2)
# neutral white light and Blender's Standard view: the four views are how the model's colours are judged against his
# picture, so they show the colour map as it is, as a game engine shows it. A warm light and AgX turned a dark blue dragon
# grey-purple (2026-11-04); AgX Punchy turned an orange fox red-pink, and reading the generator's colours as linear to
# undo that made it beige - the colour map itself was right all along (2026-11-05).
L.lights(warm="#ffffff", cool="#ffffff")
try:
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
except Exception:
    pass
only(low)
bpy.ops.export_scene.gltf(filepath=os.path.join(REN, f"{name}.glb"), use_selection=True, export_format="GLB")
# FBX is what game studios hand to Unreal, Unity and Maya (the owner, 2026-11-05: "why are they GLB? they should be
# FBX"): the same mesh with its textures inside the file (one file opens with its colours anywhere - Maya unpacks them
# beside it; with the textures only referenced, the preview showed the chest grey), the PNGs beside it as well,
# metres as engine units, Y up / -Z forward, no leaf bones, smoothing by face. The GLB stays for the web.
fbx = os.path.join(REN, f"{name}.fbx")
# an FBX names a texture only when its image feeds the material input straight: the colour ran through the AO multiply,
# and the chest's FBX carried its normal map alone (it opened grey). Engines take the AO as its own map anyway.
nt.links.new(b_col.outputs["Color"], bsdf.inputs["Base Color"])
bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                         mesh_smooth_type="FACE", add_leaf_bones=False, path_mode="COPY", embed_textures=True,
                         use_tspace=True, bake_anim=False)
if not os.path.isfile(fbx) or os.path.getsize(fbx) < 1000:
    raise SystemExit(f"FBX export failed: {fbx}")
nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])   # the preview renders keep the AO-shaded colour
L.finish(name)
info = {"name": name, "triangles_in": before, "triangles": after, "size_m": [round(size.x, 3), round(size.y, 3), round(size.z, 3)],
        "texture": tex, "maps": maps, "uv_islands": UNWRAP, "watertight": health, "source_mesh": health_in, "glb": f"renders/{name}.glb", "fbx": f"renders/{name}.fbx"}
with open(os.path.join(REN, f"{name}_info.json"), "w") as f:
    json.dump(info, f, indent=1)
print("AMAL_INFO " + json.dumps(info))
