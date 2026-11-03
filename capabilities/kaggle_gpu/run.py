"""kaggle_gpu - run a Python script on Kaggle's free GPU (about 30 hours a week, 16 GB T4/P100) and bring its files back.

    python run.py <script.py> --out <folder> [--title NAME] [--inputs FILES...] [--gpu T4|P100] [--minutes 120]

The script runs as a private Kaggle notebook (kernel) with the GPU and the internet on; whatever it writes to its working
folder (/kaggle/working) comes back into --out. Files given with --inputs are uploaded beside it as a private dataset and
are at /kaggle/input/<dataset>/ (the script also gets their folder as the environment variable LOKI_INPUTS).
Needs the owner's Kaggle API token: KAGGLE_API_TOKEN (Settings > Account > API > Create New Token), or KAGGLE_USERNAME +
KAGGLE_KEY, or ~/.kaggle/kaggle.json. The `kaggle` package is installed on first use.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time


def load_keys():
    """Keys saved in LOKI's Connections after this program started: ~/.loki/keys.env (one KEY=value a line)."""
    f = os.path.join(os.path.expanduser("~"), ".loki", "keys.env")
    for line in open(f, encoding="utf-8").read().splitlines() if os.path.isfile(f) else []:
        k, _, v = line.partition("=")
        k, v = k.strip().removeprefix("export ").strip(), v.strip().strip('"')
        if k.startswith("KAGGLE_") and v and not os.environ.get(k):
            os.environ[k] = v


def need_kaggle():
    try:
        import kaggle  # noqa: F401
    except Exception:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--user", "kaggle>=1.7"], check=True)


def cli(*args, check=True):
    p = subprocess.run([sys.executable, "-m", "kaggle"] + list(args), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"kaggle {' '.join(args[:3])} failed: {(p.stderr or p.stdout).strip()[-800:]}")
    return p.stdout


def username():
    if os.environ.get("KAGGLE_USERNAME"):
        return os.environ["KAGGLE_USERNAME"]
    cfg = os.path.expanduser("~/.kaggle/kaggle.json")
    if os.path.isfile(cfg):
        return json.load(open(cfg)).get("username", "")
    out = cli("config", "view", check=False)
    m = re.search(r"username:\s*(\S+)", out)
    return m.group(1) if m else ""


def slug(s):
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")[:40] or "loki-job"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--inputs", nargs="*", default=[])
    ap.add_argument("--gpu", default="T4", choices=["T4", "P100"])
    ap.add_argument("--minutes", type=int, default=120)
    a = ap.parse_args()
    load_keys()
    if not (os.environ.get("KAGGLE_API_TOKEN") or os.environ.get("KAGGLE_KEY") or os.path.isfile(os.path.expanduser("~/.kaggle/kaggle.json"))):
        raise SystemExit("no Kaggle API token: the owner creates one at kaggle.com > Settings > Account > API > Create New Token "
                         "and saves it in LOKI's Settings > Models > Connections (Kaggle)")
    need_kaggle()
    user = username()
    if not user:
        raise SystemExit("could not tell the Kaggle user name (set KAGGLE_USERNAME)")
    name = slug(a.title or os.path.splitext(os.path.basename(a.script))[0]) + "-" + time.strftime("%m%d%H%M")
    work = tempfile.mkdtemp(prefix="loki-kaggle-")
    sources = []
    if a.inputs:
        ds = os.path.join(work, "data")
        os.makedirs(ds)
        for f in a.inputs:
            shutil.copy(f, ds)
        json.dump({"title": name + "-in", "id": f"{user}/{name}-in", "licenses": [{"name": "CC0-1.0"}]}, open(os.path.join(ds, "dataset-metadata.json"), "w"))
        cli("datasets", "create", "-p", ds, "-q")
        sources = [f"{user}/{name}-in"]
        time.sleep(20)  # the dataset is processed before a kernel can mount it
    k = os.path.join(work, "kernel")
    os.makedirs(k)
    body = open(a.script, encoding="utf-8").read()
    pre = f"import os\nos.environ.setdefault('LOKI_INPUTS', '/kaggle/input/{name}-in')\n" if sources else ""
    open(os.path.join(k, "main.py"), "w", encoding="utf-8").write(pre + body)
    json.dump({"id": f"{user}/{name}", "title": name, "code_file": "main.py", "language": "python", "kernel_type": "script",
               "is_private": True, "enable_gpu": True, "enable_internet": True, "machine_shape": "NvidiaTeslaT4" if a.gpu == "T4" else "NvidiaTeslaP100",
               "dataset_sources": sources, "competition_sources": [], "kernel_sources": []}, open(os.path.join(k, "kernel-metadata.json"), "w"))
    print(cli("kernels", "push", "-p", k))
    t0 = time.time()
    status = ""
    while time.time() - t0 < a.minutes * 60:
        time.sleep(30)
        status = cli("kernels", "status", f"{user}/{name}", check=False).lower()
        if any(s in status for s in ("complete", "error", "cancel")):
            break
    os.makedirs(a.out, exist_ok=True)
    print(cli("kernels", "output", f"{user}/{name}", "-p", a.out, check=False))
    print(f"LOKI_KAGGLE {user}/{name}: {status.strip()}")
    if "complete" not in status:
        raise SystemExit(f"the Kaggle run ended as: {status.strip() or 'still running after ' + str(a.minutes) + ' min'} (its log is in {a.out})")


if __name__ == "__main__":
    main()
