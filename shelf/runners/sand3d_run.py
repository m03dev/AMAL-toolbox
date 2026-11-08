"""Run a sand3d program (github.com/Sandflow-ai/sand3d, Apache-2.0) and check what it made.

usage: sand3d_run.py PROGRAM OUT.glb
The program builds its object with `import sand3d as s3d` and ends with `s3d.export(root, OUT)`; OUT is passed as
sys.argv[1] (also as the variable OUT). Afterwards the GLB must exist, hold at least one mesh with faces, and the
size of every part is printed so the job can check it against its brief.
"""
import runpy, sys, os, json

prog, out = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
sys.argv = [prog, out]
runpy.run_path(prog, init_globals={"OUT": out}, run_name="__main__")
if not os.path.isfile(out) or os.path.getsize(out) == 0:
    sys.exit(f"the program did not export {out} - end it with s3d.export(root, sys.argv[1])")
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.abspath(out))
parts = []
for ob in bpy.context.scene.objects:
    if ob.type == "MESH" and len(ob.data.polygons):
        d = ob.dimensions
        parts.append({"part": ob.name, "faces": len(ob.data.polygons), "size_mm": [round(d.x * 1000, 1), round(d.y * 1000, 1), round(d.z * 1000, 1)]})
if not parts:
    sys.exit(f"{out} holds no mesh with faces")
print(json.dumps({"glb": out, "parts": parts}, indent=1))
