"""Grow a MarkovJunior model (github.com/mxgmn/MarkovJunior, MIT) and bring its pictures or voxels to the job.

usage: markovjunior_run.py SRC MODEL OUT_DIR SIZE DIMS AMOUNT SEED      (or: SRC --list)
MarkovJunior reads models.xml and resources/ from the folder it runs in and writes output/: a working copy of that
folder gets a models.xml with just this model, so the program's own copy is never changed.
"""
import glob, os, shutil, subprocess, sys, tempfile

src = sys.argv[1]
if sys.argv[2] == "--list":
    print("\n".join(sorted(os.path.splitext(os.path.basename(m))[0] for m in glob.glob(os.path.join(src, "models", "*.xml")))))
    sys.exit(0)
model, out, size, dims, amount, seed = sys.argv[2:8]
if not os.path.isfile(os.path.join(src, "models", model + ".xml")):
    sys.exit(f"no model {model} - the list action shows the names")
exe = next((p for p in [os.path.join(src, "bin", n) for n in ("MarkovJunior.exe", "MarkovJunior")] if os.path.isfile(p)), None)
dll = os.path.join(src, "bin", "MarkovJunior.dll")
if not exe and not os.path.isfile(dll):
    sys.exit("MarkovJunior is not built - its install runs `dotnet build`")
work = tempfile.mkdtemp(prefix="markovjunior-")
try:
    for d in ("models", "resources"):
        shutil.copytree(os.path.join(src, d), os.path.join(work, d))
    seed_attr = f' seeds="{seed}"' if seed not in ("", "0") else ""
    dim_attr = ' d="3"' if dims == "3" else ""
    with open(os.path.join(work, "models.xml"), "w", encoding="utf-8") as f:
        f.write(f'<models>\n  <model name="{model}" size="{size}"{dim_attr} amount="{amount}"{seed_attr}/>\n</models>\n')
    cmd = [exe] if exe else ["dotnet", dll]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=1700)
    print(r.stdout[-2000:]); sys.stderr.write(r.stderr[-2000:])
    made = glob.glob(os.path.join(work, "output", "*"))
    if not made:
        sys.exit(f"MarkovJunior made nothing (exit {r.returncode})")
    os.makedirs(out, exist_ok=True)
    for m in made:
        shutil.copy(m, out)
    print(f"{len(made)} file(s) in {out}: " + ", ".join(os.path.basename(m) for m in made[:12]))
finally:
    shutil.rmtree(work, ignore_errors=True)
