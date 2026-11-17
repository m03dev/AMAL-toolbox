"""AMAL's live session: one interpreter that stays open for a job (plain Python, Python inside Blender, or Maya).

The driver starts it once per job and kind, then sends small pieces of code; variables, imports and the open scene stay
between calls - like an artist working step by step instead of re-running one big script. Protocol (stdin/stdout):
  in:  one JSON line per request  {"code": "..."}
  out: anything, then one line    \\x1eAMAL_DONE {"ok": true|false, "out": "<printed output and/or the error>"}
Inside Blender the helpers from scripts/amal_bpy.py are preloaded (look(), save(), frame(), lights() ...).
Inside Maya (mayapy) every answer also carries MAYA'S OWN MESSAGES - the "// Error: file: ... line N: ..." lines the
Script Editor would show. mayapy does not print them (a failed MEL call only raises "Error occurred during execution of
MEL script"), so without them a job is blind; Maya's cmdFileOutput writes them to a file and they are read back.
Helpers: mel('cmd') runs MEL; whatIs('proc') says where a MEL proc is defined; gui_run('file.mel') runs a MEL file in
a full Maya session (for tools that need Maya's interface, e.g. headsUpDisplay) and returns its messages.
"""
import io
import json
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.getcwd()
MAYA_HELPERS = r'''
def mel(cmd):
    """Run MEL; on failure Maya's own error lines come back with the session's answer."""
    return mel_module.eval(cmd)

def whatIs(name):
    """Where a MEL procedure is defined (file), or what kind of command it is."""
    return mel_module.eval('whatIs "%s"' % name)

def gui_run(mel_file, timeout=900):
    """Run a MEL file in a full Maya session (its interface exists there) and return Maya's messages. The file
    must end with `quit -force;`. Only for tools that fail headless with "not available in batch mode"."""
    import subprocess, tempfile, time
    exe = os.path.join(os.path.dirname(sys.executable), 'maya.exe' if os.name == 'nt' else 'maya')
    log = os.path.join(tempfile.gettempdir(), 'amal_maya_gui_%d.log' % int(time.time()))
    env = dict(os.environ, MAYA_CMD_FILE_OUTPUT=log)
    p = subprocess.run([exe, '-script', os.path.abspath(mel_file)], env=env, timeout=timeout)
    text = open(log, encoding='utf-8', errors='replace').read() if os.path.isfile(log) else '(Maya wrote no log)'
    return 'exit %s\n%s' % (p.returncode, text[-6000:])
'''
ns = {"__name__": "__amal_session__", "ROOT": ROOT, "__file__": os.path.join(ROOT, "scripts", "session.py")}  # script-style code works too
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    import bpy  # noqa: F401  (only inside Blender)
    ns["os"] = os
    exec("from amal_bpy import *\nimport bpy, bmesh, math\nfrom mathutils import Vector, Matrix", ns)
    exec("""
def look(name='look', size=384):
    '''Render this scene from four sides into renders/<name>_views.png (adds camera and light if missing).'''
    import amal_bpy
    amal_bpy.ROOT = ROOT
    os.makedirs(os.path.join(ROOT, 'renders'), exist_ok=True)
    sc = bpy.context.scene
    if not sc.camera: frame()
    if not any(o.type == 'LIGHT' for o in sc.objects): lights()
    return views(name, size=size)

def save(path='scenes/scene.blend'):
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=p)
    return p

def api():
    \'\'\'Every amal_bpy helper with its arguments and what it does - read this instead of the source.\'\'\'
    import inspect, amal_bpy
    for n in amal_bpy.__all__:
        f = getattr(amal_bpy, n, None)
        if callable(f):
            doc = (inspect.getdoc(f) or '').split('\\n')[0]
            print(f'{n}{inspect.signature(f)}  - {doc}')

def scene():
    '''One line per object: name, type, size (m), location, material.'''
    out = []
    for o in bpy.context.scene.objects:
        d = tuple(round(v, 3) for v in o.dimensions); l = tuple(round(v, 3) for v in o.location)
        m = o.active_material.name if getattr(o, 'active_material', None) else '-'
        out.append(f'{o.name}: {o.type} size {d} at {l} mat {m}')
    print('\\n'.join(out) or '(empty scene)')
""", ns)
    import amal_bpy
    amal_bpy.ROOT = ROOT
except Exception:  # noqa: BLE001  plain Python, or Blender without the helpers
    pass

MAYA_LOG = None
try:
    import maya.standalone  # noqa: F401  (only in mayapy)
    import tempfile
    maya.standalone.initialize(name="python")
    import maya.cmds as _c
    # relative paths mean the job's folder: Maya otherwise resolves 'scenes/x.ma' against its own default project
    # (Documents/maya/projects/default), so a job saved its fixes where its build never looked
    try:
        if not os.path.isfile(os.path.join(ROOT, "workspace.mel")):
            open(os.path.join(ROOT, "workspace.mel"), "w").write('workspace -fr "scene" "scenes";\n')
        _c.workspace(ROOT.replace("\\", "/"), openWorkspace=True)
    except Exception as e:  # never stop the session over this; say it
        sys.stderr.write("could not make the job folder Maya's project: %s\n" % e)
    _c.workspace(directory=ROOT.replace("\\", "/"))
    import maya.cmds as cmds
    MAYA_LOG = os.path.join(tempfile.gettempdir(), "amal_maya_%d.log" % os.getpid())
    cmds.cmdFileOutput(o=MAYA_LOG)
    exec("import maya.cmds as cmds\nimport maya.mel as mel_module\nimport maya.api.OpenMaya as om", ns)
    ns.update(os=os, sys=sys, MAYA_LOG=MAYA_LOG)
    exec(MAYA_HELPERS, ns)
except ImportError:
    pass


def maya_messages(start):
    """Maya's own output since `start` (bytes into the log): errors, warnings, results."""
    if not MAYA_LOG or not os.path.isfile(MAYA_LOG):
        return ""
    with open(MAYA_LOG, encoding="utf-8", errors="replace") as fh:
        fh.seek(start)
        return fh.read()


sys.stdout.write("\x1eAMAL_DONE " + json.dumps({"ok": True, "out": "session ready" + (" (Maya)" if MAYA_LOG else "")}) + "\n")
sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        code = json.loads(line).get("code", "")
    except ValueError:
        code = line
    buf = io.StringIO()
    ok = True
    mark = os.path.getsize(MAYA_LOG) if MAYA_LOG and os.path.isfile(MAYA_LOG) else 0
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            try:
                expr = compile(code, "<session>", "eval")   # a bare expression shows its value
            except SyntaxError:
                expr = None
            if expr is not None:
                result = eval(expr, ns)
                if result is not None:
                    print(repr(result))
            else:   # statements; run outside the except block so an error's traceback is only the real one
                exec(compile(code, "<session>", "exec"), ns)
    except SystemExit:
        break
    except BaseException:  # noqa: BLE001
        ok = False
        buf.write(traceback.format_exc(limit=4))
    out = buf.getvalue()
    said = maya_messages(mark).strip()
    if said:
        lines = said.splitlines()
        keep = [l for l in lines if "Error" in l or "Warning" in l] if len(lines) > 60 else lines
        out += "\n--- Maya says ---\n" + "\n".join(keep[-60:])
    if len(out) > 6000:
        out = out[:2500] + "\n...\n" + out[-3000:]
    sys.stdout.write("\x1eAMAL_DONE " + json.dumps({"ok": ok, "out": out}) + "\n")
    sys.stdout.flush()
