r"""bpy_exit_guard - let ComfyUI load custom nodes whose isolated environment contains Blender's bpy (ComfyUI-UniRig).

Why: on Windows `import bpy` works, but the Python process crashes with an access violation (0xC0000005) when it
EXITS. comfy-env learns a node pack's nodes by running a short scan process in the pack's own environment; the scan
finishes, writes its result, then crashes on exit, so comfy-env throws the result away ("Metadata scan failed ...
exit 1") and ComfyUI shows 0 UniRig nodes. Found 2026-10-31 by re-running the scan by hand.

Fix: a .pth file in each comfy-env environment that, for the scan process only, ends it outright as soon as the
scan script is done (0 if it finished, 1 if it raised) - before shutdown reaches bpy. On Windows that is
TerminateProcess: even os._exit still unloads bpy's DLLs, and the unload is what crashes. Long-running
worker processes are not touched. AMAL's comfy tool runs this before it starts ComfyUI; it is safe to run again.

    python bpy_exit_guard.py        (prints what it did)
"""
import glob
import os
import sys

GUARD = r'''# written by AMAL tools/comfy/bpy_exit_guard.py - see there
import os, sys, threading
_main = os.path.basename(sys.argv[0] if sys.argv else "")
if _main.startswith(("comfy_meta_", "amal_meta_scan")) and hasattr(threading, "_register_atexit"):
    _failed = [False]
    _hook = sys.excepthook
    def _record(t, v, tb):
        _failed[0] = True
        _hook(t, v, tb)
    sys.excepthook = _record
    def _leave():
        if "bpy" in sys.modules:
            for s in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
                try:
                    s.flush()
                except Exception:
                    pass
            code = 1 if _failed[0] else 0
            if os.name == "nt":   # os._exit still unloads bpy's DLLs, and that is what crashes: end the process outright
                import ctypes
                from ctypes import wintypes
                k = ctypes.WinDLL("kernel32")
                k.GetCurrentProcess.restype = wintypes.HANDLE
                k.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
                k.TerminateProcess(k.GetCurrentProcess(), code)
            os._exit(code)
    threading._register_atexit(_leave)
'''


def site_dirs():
    roots = []
    if os.environ.get("LOCALAPPDATA"):
        roots.append(os.path.join(os.environ["LOCALAPPDATA"], "Programs", "comfy-env", "envs"))
    roots.append(os.path.expanduser("~/.local/share/comfy-env/envs"))
    roots.append(os.path.expanduser("~/Library/Application Support/comfy-env/envs"))
    out = []
    for r in roots:
        out += glob.glob(os.path.join(r, "*", ".pixi", "envs", "*", "Lib", "site-packages"))
        out += glob.glob(os.path.join(r, "*", ".pixi", "envs", "*", "lib", "python*", "site-packages"))
    return out


def main():
    done = []
    for sp in site_dirs():
        if not glob.glob(os.path.join(sp, "bpy*")):
            continue
        mod = os.path.join(sp, "amal_bpy_exit_guard.py")
        pth = os.path.join(sp, "amal_bpy_exit_guard.pth")
        if not (os.path.isfile(mod) and open(mod, encoding="utf-8").read() == GUARD):
            with open(mod, "w", encoding="utf-8") as f:
                f.write(GUARD)
        if not os.path.isfile(pth):
            with open(pth, "w", encoding="utf-8") as f:
                f.write("import amal_bpy_exit_guard\n")
        done.append(sp)
    print("bpy exit guard in: " + (", ".join(done) if done else "(no comfy-env environment with bpy)"))


if __name__ == "__main__":
    sys.exit(main())
