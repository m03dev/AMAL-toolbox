"""Run one AMAL ComfyUI graph on Kaggle's free GPU (16 GB) and leave its output files in /kaggle/working.

AMAL sends this as the Kaggle script with spec.json beside it (in $AMAL_INPUTS): the filled API prompt, the node packs
the graph uses (git URL + commit, read from the GPU machine's own ComfyUI), the model files (download URL + folder), and
any input pictures. Used when a graph's model is bigger than the GPU machine's card (Wan 14B: 11.6 GB on an 8 GB 3070 Ti
took minutes a step, fully offloaded).
"""
import json, os, shutil, subprocess, sys, time, urllib.request

if not shutil.which("nvidia-smi"):
    # Kaggle ran this on its CPU (the account may not use GPUs yet): stop at once, the GPU machine renders it instead
    print("AMAL_GPU: none - stopping", flush=True)
    sys.exit(0)

INP = os.environ.get("AMAL_INPUTS", ".")
if not os.path.isfile(os.path.join(INP, "spec.json")):
    # where Kaggle mounted the upload (its folder layout has changed over time)
    INP = next((d for d, _, fs in os.walk("/kaggle/input") if "spec.json" in fs), INP)
spec = json.load(open(os.path.join(INP, "spec.json")))
ROOT = "/kaggle/temp/ComfyUI" if os.path.isdir("/kaggle/temp") else "/tmp/ComfyUI"
OUT = "/kaggle/working"
t0 = time.time()


def sh(*cmd, cwd=None):
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def pip(*args):
    sh(sys.executable, "-m", "pip", "install", "-q", *args)


# ComfyUI at the GPU machine's commit when known, its requirements without touching Kaggle's own torch
sh("git", "clone", "-q", "https://github.com/comfyanonymous/ComfyUI", ROOT)
if spec.get("comfy_commit"):
    subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", spec["comfy_commit"]], cwd=ROOT)
    subprocess.run(["git", "checkout", "-q", spec["comfy_commit"]], cwd=ROOT)


def reqs(path):
    import re
    # Kaggle's own torch, torchvision and torchaudio stay (built for its CUDA); torchsde and the rest are installed
    keep = [l for l in open(path).read().splitlines() if l.strip() and not l.strip().startswith("#")
            and re.split(r"[<>=!~\[ ;]", l.strip())[0].lower() not in ("torch", "torchvision", "torchaudio")]
    if keep:
        tmp = path + ".amal"
        open(tmp, "w").write("\n".join(keep))
        pip("-r", tmp)


reqs(os.path.join(ROOT, "requirements.txt"))
for p in spec.get("packs", []):
    dest = os.path.join(ROOT, "custom_nodes", p["dir"])
    sh("git", "clone", "-q", p["url"], dest)
    if p.get("commit"):
        subprocess.run(["git", "checkout", "-q", p["commit"]], cwd=dest)
    if os.path.isfile(os.path.join(dest, "requirements.txt")):
        reqs(os.path.join(dest, "requirements.txt"))
print(f"set up in {time.time() - t0:.0f} s", flush=True)

for m in spec.get("models", []):
    dest = os.path.join(ROOT, "models", m["folder"].removeprefix("models/"), m["file"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    t = time.time()
    with urllib.request.urlopen(m["url"]) as r, open(dest + ".part", "wb") as f:
        shutil.copyfileobj(r, f, 16 << 20)
    os.rename(dest + ".part", dest)
    print(f"model {m['file']}: {os.path.getsize(dest) / 1e9:.1f} GB in {time.time() - t:.0f} s", flush=True)

for name in spec.get("inputs", []):
    sub = os.path.join(ROOT, "input", os.path.dirname(name))
    os.makedirs(sub, exist_ok=True)
    shutil.copy(os.path.join(INP, os.path.basename(name)), os.path.join(ROOT, "input", name))

server = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"], cwd=ROOT)
base = "http://127.0.0.1:8188"
for _ in range(300):
    if server.poll() is not None:
        print(f"AMAL_ERROR ComfyUI stopped while starting (exit {server.returncode}) - its log is above", flush=True)
        sys.exit(1)
    try:
        urllib.request.urlopen(base + "/system_stats", timeout=5)
        break
    except Exception:
        time.sleep(2)

req = urllib.request.Request(base + "/prompt", data=json.dumps({"prompt": spec["prompt"], "client_id": "amal"}).encode(),
                             headers={"Content-Type": "application/json"})
pid = json.load(urllib.request.urlopen(req))["prompt_id"]
t = time.time()
while True:
    time.sleep(5)
    h = json.load(urllib.request.urlopen(f"{base}/history/{pid}"))
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error" or (st.get("completed") is False and st.get("messages")):
            print("AMAL_ERROR", json.dumps(st)[:3000], flush=True)
        break
    if server.poll() is not None:
        print("AMAL_ERROR ComfyUI stopped", flush=True)
        break
print(f"rendered in {time.time() - t:.0f} s", flush=True)

n = 0
for node in h.get(pid, {}).get("outputs", {}).values():
    for items in node.values():
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and it.get("filename"):
                src = os.path.join(ROOT, it.get("type", "output"), it.get("subfolder", ""), it["filename"])
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(OUT, it["filename"]))
                    n += 1
print(f"AMAL_DONE {n} file(s) in {time.time() - t0:.0f} s", flush=True)
server.terminate()
