"""Build one sand3d program into a GLB with the arguments given (AMAL's premade assets, premade.rs `build`).

    python run.py <program.py> <out.glb> '<{"name": value}>'

The program's own function makes the object; its arguments, with their defaults, are what the asset browser shows as
sliders. A program written as a script (no function - sand3d's CAD set) has its settings as capitals-named numbers at
its top; those are the sliders, changed in the text before it runs, and what it built is exported as it stands. Prints one JSON line: the function, its arguments (defaults and what was used).
"""
import importlib.util
import inspect
import json
import re
import sys
import tempfile
import os

import sand3d as s3d

# a program written as a script (sand3d's CAD set): its settings are the numbers named in capitals at its top
CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?)\s*(#.*)?$")


def script_params(src):
    """The capitals-named numbers before the program starts building (`HANDLE_LENGTH = 70`), in order."""
    out = {}
    for line in src.splitlines():
        if "s3d." in line:
            break
        m = CONST.match(line.strip())
        if m:
            v = m.group(2)
            out[m.group(1)] = float(v) if "." in v else int(v)
    return out


def unwrap_all():
    """UVs for every mesh that has none (sand3d colours by material, and a model without UVs is not game-ready):
    Blender's Smart UV Project, the usual unwrap for hard-surface parts. A part it cannot unwrap is left as it is."""
    import bpy
    import math
    for o in list(bpy.context.scene.objects):
        if o.type != "MESH" or o.data.uv_layers:
            continue
        try:
            for x in bpy.context.selected_objects:
                x.select_set(False)
            bpy.context.view_layer.objects.active = o
            o.select_set(True)
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception as e:  # noqa: BLE001 - the build stands without it; the check will say "no UVs"
            print("unwrap %s: %s" % (o.name, e), file=sys.stderr)
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:  # noqa: BLE001
                pass


def build_script(src, out, given):
    """Run a script program with its settings changed, then export what it built (the visible objects)."""
    params = script_params(src)
    use = {k: type(params[k])(v) for k, v in given.items() if k in params}
    lines = []
    for line in src.splitlines():
        m = CONST.match(line.strip())
        if m and m.group(1) in use and line == line.lstrip():
            line = "%s = %r" % (m.group(1), use[m.group(1)])
        lines.append(line)
    s3d.empty_scene()
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("\n".join(lines))
        tmp = f.name
    try:
        spec = importlib.util.spec_from_file_location("program", tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.unlink(tmp)
    import bpy
    # sand3d draws in millimetres; a glTF is in metres (s3d.export converts the same way)
    for o in bpy.context.scene.objects:
        if o.parent is None:
            o.location = o.location * 0.001
            o.scale = o.scale * 0.001
    unwrap_all()
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_visible=True, export_apply=True)
    return {"function": "", "params": params, "used": use}


def main():
    src, out, given = sys.argv[1], sys.argv[2], json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")
    text = open(src, encoding="utf-8").read()
    if not re.search(r"^def ", text, re.M):
        print(json.dumps(build_script(text, out, given)))
        return
    spec = importlib.util.spec_from_file_location("program", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    funcs = [f for _, f in inspect.getmembers(mod, inspect.isfunction) if f.__module__ == mod.__name__ and not f.__name__.startswith("_")]
    funcs.sort(key=lambda f: f.__code__.co_firstlineno)
    # the maker: every argument has a default (it can be built as it stands); a posed variant ("..._open") comes after
    makers = [f for f in funcs if all(p.default is not inspect.Parameter.empty for p in inspect.signature(f).parameters.values())]
    if not makers:
        raise SystemExit("no function in the program that builds the object (its functions: %s)" % ", ".join(f.__name__ for f in funcs))
    f = makers[0]
    params = {k: p.default for k, p in inspect.signature(f).parameters.items()}
    use = {}
    for k, v in given.items():
        if k in params:
            d = params[k]
            use[k] = type(d)(v) if isinstance(d, (int, float, bool)) and not isinstance(v, type(d)) else v
    s3d.empty_scene()
    root = f(**use)
    unwrap_all()
    s3d.export(root, out)
    print(json.dumps({"function": f.__name__, "params": {k: v for k, v in params.items() if isinstance(v, (int, float, bool, str))}, "used": use}))


if __name__ == "__main__":
    main()
