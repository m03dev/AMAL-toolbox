"""auto_rig - a skeleton and skin for a bare model, made by SkinTokens (TokenRig, UniRig's successor; MIT) on Kaggle's
free GPU. No Maya, no AdvancedSkeleton (owner 2026-11-04: it "is clearly a big problem" - use the newer rigger).

    python auto_rig.py <model .glb/.fbx/.obj> --out <rigged .glb/.fbx> --blender <blender> [--minutes 90]

1. skin_io.py mesh (Blender): the model's meshes in world space -> <work>/<name>_skin_in.npz (no skeleton in it)
2. kaggle_gpu: kaggle_skintokens.py sees no skeleton and auto-rigs -> <name>_auto_rig.npz (joints, parents, 4 weights a vertex)
3. skin_io.py build (Blender): the skeleton and its skin on the model -> --out, ready for creature_anim.py's clips

The work folder is named after the model's content, so a run that was stopped picks up the Kaggle run it started.
"""
import argparse, glob, hashlib, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SKIN = os.path.join(os.path.dirname(HERE), "skin_weights")
KAGGLE = os.path.join(os.path.dirname(HERE), "kaggle_gpu", "run.py")


def blender(exe, *args):
    cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "1", "--python", os.path.join(SKIN, "skin_io.py"), "--", *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l for l in (p.stdout + p.stderr).splitlines() if l.startswith(("LOKI_", "skin:", "Error", "Traceback")) or "Error:" in l]
    print("\n".join(lines), flush=True)
    if p.returncode != 0:
        raise SystemExit(f"Blender ({args[0]}) failed:\n" + (p.stdout + p.stderr)[-2500:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--out", required=True)
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--minutes", type=int, default=90)
    a = ap.parse_args()
    if not os.path.isfile(a.model):
        raise SystemExit(f"no model at {a.model}")
    h = hashlib.sha1(open(a.model, "rb").read() + b"auto").hexdigest()[:12]
    work = os.path.join(".loki", "auto_rig", h)
    out = os.path.join(work, "out")
    os.makedirs(out, exist_ok=True)
    stem = "".join(c if c.isalnum() or c in "_-" else "_" for c in os.path.splitext(os.path.basename(a.model))[0])
    inp = os.path.join(work, f"{stem}_skin_in.npz")
    if not os.path.isfile(inp):
        blender(a.blender, "mesh", a.model, inp)
    got = glob.glob(os.path.join(out, "*_auto_rig*.npz"))
    if not got:
        kernel = os.path.join(out, "kernel.txt")
        recent = os.path.isfile(kernel) and time.time() - os.path.getmtime(kernel) < 3 * 3600
        # a run that already ended without a result is not waited on again: a fixed script would never get its turn
        if recent and glob.glob(os.path.join(out, "*.log")):
            for f in glob.glob(os.path.join(out, "*.log")) + [kernel]:
                os.remove(f)
            recent = False
        cmd = [sys.executable, KAGGLE, os.path.join(SKIN, "kaggle_skintokens.py"), "--out", out, "--gpu", "T4", "--minutes", str(a.minutes)]
        cmd += ["--attach", open(kernel).read().strip()] if recent else ["--title", f"auto rig {stem}", "--inputs", inp]
        print("$", " ".join(cmd), flush=True)
        r = subprocess.run(cmd)
        got = glob.glob(os.path.join(out, "*_auto_rig*.npz"))
        if not got:
            logs = "".join(open(f, encoding="utf-8", errors="replace").read() for f in glob.glob(os.path.join(out, "*.log")))
            why = [l.strip() for l in logs.splitlines() if "LOKI_ERROR" in l or "Error" in l][-6:]
            raise SystemExit(f"Kaggle brought no rig back (exit {r.returncode}; its log is in {out})" + ("\n" + "\n".join(why) if why else ""))
    # every rig Kaggle made (several seeds): the first is --out, the others beside it as <out>_2, <out>_3 ...
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    base, ext = os.path.splitext(a.out)
    built = []
    for k, npz in enumerate(sorted(got), 1):
        dst = a.out if k == 1 else f"{base}_{k}{ext}"
        keep = os.path.splitext(dst)[0] + "_auto_rig.npz"
        shutil.copy(npz, keep)
        try:
            blender(a.blender, "build", a.model, keep, dst)
            built.append(dst)
        except SystemExit as e:
            print(f"rig {k} not built: {str(e)[:300]}", flush=True)
    if not built:
        raise SystemExit("none of the rigs could be built in Blender")
    print("LOKI_AUTO_RIG_DONE " + " ".join(built))


if __name__ == "__main__":
    main()
