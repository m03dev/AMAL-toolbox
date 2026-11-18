"""AMAL's live link inside Cascadeur: a small server on 127.0.0.1:7735 that AMAL drives while you animate (
a job's `live` tool). AMAL puts it in Cascadeur's commands as "AMAL > Live link"; run it once after Cascadeur starts
(Commands > AMAL > Live link), or paste `exec(open(r"<this file>").read())` into Window > Python console. Requests are
read by a Qt timer on Cascadeur's own thread, where its scene API is safe to use.

One JSON object per line in, one JSON line out:
  {"op": "ping"}                 the version and the open scene
  {"op": "scene"}                the objects of the open scene (name, id) and the current frame
  {"op": "exec", "code": "..."}  runs Python here with csc, app (the application), scene (the open scene) in scope;
                                 printed output, the value of `result`, the error with its line
  {"op": "shot", "path": "..."}  a picture of Cascadeur's window now
"""
import io
import json
import socket
import traceback
import contextlib

import csc

try:
    from PySide6 import QtCore, QtWidgets
except Exception:  # older builds
    from PySide2 import QtCore, QtWidgets

PORT = 7735
_state = {"server": None, "timer": None, "clients": []}


def _app():
    return csc.app.get_application()


def _scene():
    try:
        return _app().get_scene_manager().current_scene()
    except Exception:
        return None


def _ping(_req):
    sc = _scene()
    name = ""
    try:
        name = sc.name() if sc else ""
    except Exception:
        pass
    ver = ""
    try:
        ver = csc.app.get_application().version()
    except Exception:
        pass
    return {"ok": True, "app": "cascadeur", "version": str(ver), "file": str(name)}


def _scene_info(_req):
    sc = _scene()
    if sc is None:
        return {"ok": True, "objects": [], "note": "no scene is open"}
    out = {"ok": True, "objects": []}

    def read(model, *_):
        try:
            for oid in model.get_objects():
                try:
                    out["objects"].append({"id": str(oid), "name": model.get_object_name(oid)})
                except Exception:
                    out["objects"].append({"id": str(oid)})
        except Exception as e:
            out["note"] = "objects could not be listed here: %s" % e
    try:
        sc.domain_scene().model_viewer() and read(sc.domain_scene().model_viewer())
    except Exception:
        try:
            sc.modify("AMAL read scene", read)
        except Exception as e:
            out["note"] = str(e)
    return out


def _exec(req):
    buf = io.StringIO()
    env = {"csc": csc, "app": _app(), "scene": _scene(), "__name__": "__amal__"}
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(compile(req.get("code", ""), "<amal>", "exec"), env)
        res = env.get("result")
        try:
            json.dumps(res)
        except TypeError:
            res = repr(res)
        return {"ok": True, "output": buf.getvalue()[-8000:], "result": res}
    except Exception:
        return {"ok": False, "output": buf.getvalue()[-4000:], "error": traceback.format_exc(limit=4)[-4000:]}


def _shot(req):
    path = req.get("path")
    if not path:
        return {"ok": False, "error": "a path to save the picture is needed"}
    w = QtWidgets.QApplication.activeWindow() or next((t for t in QtWidgets.QApplication.topLevelWidgets() if t.isVisible()), None)
    if w is None:
        return {"ok": False, "error": "no Cascadeur window is visible (is it minimised?)"}
    ok = w.grab().save(path, "PNG")
    return {"ok": bool(ok), "path": path}


OPS = {"ping": _ping, "scene": _scene_info, "exec": _exec, "shot": _shot}


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
    s = _state["server"]
    try:
        while True:
            c, _ = s.accept()
            c.setblocking(False)
            _state["clients"].append([c, b""])
    except (BlockingIOError, OSError):
        pass
    for entry in list(_state["clients"]):
        c, buf = entry
        try:
            data = c.recv(1 << 20)
            if not data:
                raise ConnectionError
            buf += data
        except BlockingIOError:
            pass
        except Exception:
            _state["clients"].remove(entry)
            c.close()
            continue
        entry[1] = buf
        if b"\n" in buf:
            ans = _answer(buf.split(b"\n", 1)[0].decode("utf-8", "replace"))
            try:
                c.setblocking(True)
                c.sendall((json.dumps(ans) + "\n").encode())
            except Exception:
                pass
            _state["clients"].remove(entry)
            c.close()


def start():
    if _state["server"] is not None:
        print("AMAL live link: already listening on %d" % PORT)
        return
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", PORT))
    except OSError as e:
        print("AMAL live link: could not listen on %d (%s)" % (PORT, e))
        return
    s.listen(8)
    s.setblocking(False)
    t = QtCore.QTimer()
    t.timeout.connect(_tick)
    t.start(50)
    _state.update(server=s, timer=t)
    print("AMAL live link: listening on 127.0.0.1:%d" % PORT)


# as a Cascadeur command (Commands > AMAL > Live link)
def command_name():
    return "AMAL.Live link"


def run(_scene=None):
    start()


if __name__ in ("__main__", "__amal_exec__") or __name__ == "builtins":
    start()
