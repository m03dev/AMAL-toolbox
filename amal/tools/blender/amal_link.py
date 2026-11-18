"""AMAL's live link inside Blender: a small server on 127.0.0.1:7731 that AMAL drives while you work (a
job's `live` tool). Installed into Blender's startup scripts by AMAL, so it runs at every start; it never blocks the
interface - requests are read by a timer on Blender's own thread, where bpy is safe to use.

One JSON object per line in, one JSON line out:
  {"op": "ping"}                 the version and the open file
  {"op": "scene"}                every object: name, type, parent, location, rotation, scale, vertex count, modifiers, materials
  {"op": "exec", "code": "..."}  runs Python here (bpy, the scene as it is); printed output, the value of `result`, the error with its line
  {"op": "shot", "path": "..."}  a picture of the 3D view as it is now
"""
import io
import json
import socket
import traceback
import contextlib

import bpy

PORT = 7731
_server = None
_clients = []


def _ping(_req):
    return {"ok": True, "app": "blender", "version": bpy.app.version_string, "file": bpy.data.filepath,
            "scene": bpy.context.scene.name if bpy.context.scene else "", "objects": len(bpy.data.objects)}


def _scene(_req):
    out = []
    for o in bpy.data.objects:
        item = {"name": o.name, "type": o.type, "parent": o.parent.name if o.parent else "",
                "location": [round(v, 4) for v in o.location], "rotation": [round(v, 4) for v in o.rotation_euler],
                "scale": [round(v, 4) for v in o.scale], "hidden": o.hide_get() if hasattr(o, "hide_get") else False,
                "modifiers": [m.type for m in getattr(o, "modifiers", [])],
                "materials": [s.material.name for s in getattr(o, "material_slots", []) if s.material]}
        if o.type == "MESH" and o.data:
            item["vertices"] = len(o.data.vertices)
            item["faces"] = len(o.data.polygons)
        out.append(item)
    return {"ok": True, "objects": out, "collections": [c.name for c in bpy.data.collections],
            "frame": bpy.context.scene.frame_current if bpy.context.scene else 0}


def _exec(req):
    code = req.get("code", "")
    buf = io.StringIO()
    env = {"bpy": bpy, "__name__": "__amal__"}
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(compile(code, "<amal>", "exec"), env)
        res = env.get("result")
        try:
            json.dumps(res)
        except TypeError:
            res = repr(res)
        return {"ok": True, "output": buf.getvalue()[-8000:], "result": res}
    except Exception:
        return {"ok": False, "output": buf.getvalue()[-4000:], "error": traceback.format_exc(limit=4)[-4000:]}


def _view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                return win, area
    return None, None


def _shot(req):
    path = req.get("path") or bpy.path.abspath("//amal_live.png")
    win, area = _view3d()
    if area is None:
        return {"ok": False, "error": "no 3D view is open"}
    with bpy.context.temp_override(window=win, area=area):
        bpy.ops.screen.screenshot_area(filepath=path)
    return {"ok": True, "path": path}


OPS = {"ping": _ping, "scene": _scene, "exec": _exec, "shot": _shot}


def _answer(line):
    try:
        req = json.loads(line)
    except ValueError:
        return {"ok": False, "error": "not JSON"}
    fn = OPS.get(req.get("op", ""))
    if fn is None:
        return {"ok": False, "error": "unknown op; one of " + ", ".join(OPS)}
    try:
        return fn(req)
    except Exception:
        return {"ok": False, "error": traceback.format_exc(limit=4)[-4000:]}


def _tick():
    global _server
    if _server is None:
        return None
    try:
        while True:
            c, _ = _server.accept()
            c.setblocking(False)
            _clients.append([c, b""])
    except (BlockingIOError, OSError):
        pass
    for entry in list(_clients):
        c, buf = entry
        try:
            data = c.recv(1 << 20)
            if not data:
                raise ConnectionError
            buf += data
        except BlockingIOError:
            pass
        except Exception:
            _clients.remove(entry)
            c.close()
            continue
        entry[1] = buf
        if b"\n" in buf:
            line, _rest = buf.split(b"\n", 1)
            ans = _answer(line.decode("utf-8", "replace"))
            try:
                c.setblocking(True)
                c.sendall((json.dumps(ans) + "\n").encode())
            except Exception:
                pass
            _clients.remove(entry)
            c.close()
    return 0.05


def register():
    global _server
    if _server is not None or bpy.app.background:
        return
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", PORT))
        s.listen(8)
        s.setblocking(False)
        _server = s
        bpy.app.timers.register(_tick, persistent=True)
        print("AMAL live link: listening on 127.0.0.1:%d" % PORT)
    except OSError as e:
        print("AMAL live link: could not listen on %d (%s) - another Blender has it" % (PORT, e))


def unregister():
    global _server
    if _server is not None:
        _server.close()
        _server = None


if __name__ == "__main__":
    register()
