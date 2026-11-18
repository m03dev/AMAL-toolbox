"""AMAL's live link inside Maya: a small server on 127.0.0.1:7732 that AMAL drives while you work (a job's
`live` tool). AMAL adds `amal_link.start()` to Maya's userSetup.py, so it runs at every start. Requests are read on a
background thread and run on Maya's main thread (maya.utils.executeInMainThreadWithResult), where cmds is safe.

One JSON object per line in, one JSON line out:
  {"op": "ping"}                 the version and the open scene
  {"op": "scene"}                every transform: name, type of its shape, parent, translate / rotate / scale, vertex count
  {"op": "exec", "code": "..."}  runs Python here (maya.cmds as cmds); printed output, the value of `result`, the error
  {"op": "exec", "mel": "..."}   runs MEL
  {"op": "shot", "path": "..."}  a picture of the viewport now (a one-frame playblast)

It also opens Maya's own command port on 127.0.0.1:7001 (Python), the port a Maya MCP server drives Maya through
(AMAL's Settings › Connections › Maya through MCP) - on this computer only, never on the network.
"""
import io
import json
import socket
import threading
import traceback
import contextlib

import maya.cmds as cmds
import maya.mel as mel
import maya.utils

PORT = 7732
MCP_PORT = 7001
_thread = None


def open_command_port(port=MCP_PORT):
    """Maya's commandPort for an MCP server, bound to this computer only; already open is fine."""
    name = "127.0.0.1:%d" % port
    try:
        if cmds.commandPort(name, q=True):
            return True
        cmds.commandPort(name=name, sourceType="python", echoOutput=True, noreturn=False, bufferSize=16384)
        print("AMAL: Maya's command port is open on %s for MCP" % name)
        return True
    except Exception as e:  # another program holds the port, or Maya refused it
        print("AMAL: could not open Maya's command port %s (%s)" % (name, e))
        return False


def _ping(_req):
    return {"ok": True, "app": "maya", "version": cmds.about(version=True), "file": cmds.file(q=True, sceneName=True),
            "objects": len(cmds.ls(transforms=True) or [])}


def _scene(_req):
    out = []
    for t in cmds.ls(transforms=True, long=False) or []:
        shapes = cmds.listRelatives(t, shapes=True, fullPath=True) or []
        kind = cmds.nodeType(shapes[0]) if shapes else "transform"
        parent = (cmds.listRelatives(t, parent=True) or [""])[0]
        item = {"name": t, "type": kind, "parent": parent,
                "translate": [round(v, 4) for v in cmds.getAttr(t + ".translate")[0]],
                "rotate": [round(v, 4) for v in cmds.getAttr(t + ".rotate")[0]],
                "scale": [round(v, 4) for v in cmds.getAttr(t + ".scale")[0]]}
        if kind == "mesh":
            item["vertices"] = cmds.polyEvaluate(t, vertex=True)
            item["faces"] = cmds.polyEvaluate(t, face=True)
        out.append(item)
    return {"ok": True, "objects": out, "frame": cmds.currentTime(q=True)}


def _exec(req):
    buf = io.StringIO()
    try:
        if req.get("mel"):
            res = mel.eval(req["mel"])
            return {"ok": True, "result": res if isinstance(res, (str, int, float, list)) else repr(res)}
        env = {"cmds": cmds, "mel": mel, "__name__": "__amal__"}
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
    base = path[:-4] if path.lower().endswith(".png") else path
    f = cmds.currentTime(q=True)
    made = cmds.playblast(frame=[f], format="image", compression="png", completeFilename=base + ".png",
                          viewer=False, showOrnaments=False, percent=100, widthHeight=(1280, 720), forceOverwrite=True)
    return {"ok": True, "path": made or base + ".png"}


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
        return maya.utils.executeInMainThreadWithResult(fn, req)
    except Exception:
        return {"ok": False, "error": traceback.format_exc(limit=4)[-4000:]}


def _serve(sock):
    while True:
        try:
            c, _ = sock.accept()
        except OSError:
            return
        try:
            c.settimeout(600)
            buf = b""
            while b"\n" not in buf:
                data = c.recv(1 << 20)
                if not data:
                    break
                buf += data
            ans = _answer(buf.split(b"\n", 1)[0].decode("utf-8", "replace"))
            c.sendall((json.dumps(ans) + "\n").encode())
        except Exception:
            pass
        finally:
            c.close()


def start():
    global _thread
    if _thread is not None or cmds.about(batch=True):
        return
    open_command_port()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", PORT))
        s.listen(8)
    except OSError as e:
        print("AMAL live link: could not listen on %d (%s)" % (PORT, e))
        return
    _thread = threading.Thread(target=_serve, args=(s,), daemon=True)
    _thread.start()
    print("AMAL live link: listening on 127.0.0.1:%d" % PORT)
