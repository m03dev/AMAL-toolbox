"""skin_weights - learned skin weights for a rigged model, its skeleton kept: SkinTokens on Kaggle's free GPU.

    python skin_weights.py <rigged .fbx/.glb> --out <weights.npz> --model-out <re-skinned .fbx/.glb> --blender <blender>
                           [--minutes 90] [--max-joints 150]

1. skin_io.py prep (Blender): the skin and the skeleton's deforming joints -> <work>/<name>_skin_in.npz
2. kaggle_gpu: kaggle_skintokens.py runs SkinTokens on that (Kaggle's T4) -> <name>_skin_weights.npz
3. skin_io.py apply (Blender): the weights onto the same model by mesh name, vertex index and joint name -> --model-out

The work folder is named after the model's content (.loki/skin_weights/<hash>): a caller that was stopped and runs this
again waits for the Kaggle run already started (or takes its finished weights) instead of starting a second one.
"""
import argparse, glob, hashlib, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
KAGGLE = os.path.join(os.path.dirname(HERE), "kaggle_gpu", "run.py")


def blender(exe, *args):
    cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "1", "--python", os.path.join(HERE, "skin_io.py"), "--", *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l for l in (p.stdout + p.stderr).splitlines() if l.startswith(("LOKI_", "skin:", "Error", "Traceback")) or "Error:" in l]
    print("\n".join(lines), flush=True)
    if p.returncode != 0:
        raise SystemExit(f"Blender ({args[0]}) failed:\n" + (p.stdout + p.stderr)[-2500:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-out", required=True)
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--minutes", type=int, default=90)
    ap.add_argument("--max-joints", type=int, default=150)
    a = ap.parse_args()
    if not os.path.isfile(a.model):
        raise SystemExit(f"no model at {a.model}")
    h = hashlib.sha1(open(a.model, "rb").read() + str(a.max_joints).encode()).hexdigest()[:12]
    work = os.path.join(".loki", "skin_weights", h)
    out = os.path.join(work, "out")
    os.makedirs(out, exist_ok=True)
    stem = "".join(c if c.isalnum() or c in "_-" else "_" for c in os.path.splitext(os.path.basename(a.model))[0])
    inp = os.path.join(work, f"{stem}_skin_in.npz")
    if not os.path.isfile(inp):
        blender(a.blender, "prep", a.model, inp, str(a.max_joints))
    got = glob.glob(os.path.join(out, "*_skin_weights.npz"))
    if not got:
        kernel = os.path.join(out, "kernel.txt")
        recent = os.path.isfile(kernel) and time.time() - os.path.getmtime(kernel) < 3 * 3600
        # a run that already ended without a result is not waited on again: a fixed script would never get its turn
        if recent and glob.glob(os.path.join(out, "*.log")):
            for f in glob.glob(os.path.join(out, "*.log")) + [kernel]:
                os.remove(f)
            recent = False
        cmd = [sys.executable, KAGGLE, os.path.join(HERE, "kaggle_skintokens.py"), "--out", out, "--gpu", "T4", "--minutes", str(a.minutes)]
        cmd += ["--attach", open(kernel).read().strip()] if recent else ["--title", f"skin weights {stem}", "--inputs", inp]
        print("$", " ".join(cmd), flush=True)
        r = subprocess.run(cmd)
        got = glob.glob(os.path.join(out, "*_skin_weights.npz"))
        if not got:
            logs = "".join(open(f, encoding="utf-8", errors="replace").read() for f in glob.glob(os.path.join(out, "*.log")))
            why = [l.strip() for l in logs.splitlines() if "LOKI_ERROR" in l or "Error" in l][-6:]
            raise SystemExit(f"Kaggle brought no weights back (exit {r.returncode}; its log is in {out})" + ("\n" + "\n".join(why) if why else ""))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    shutil.copy(got[0], a.out)
    blender(a.blender, "apply", a.model, a.out, a.model_out)
    print(f"LOKI_SKIN_WEIGHTS {a.out} {a.model_out}")


if __name__ == "__main__":
    main()
