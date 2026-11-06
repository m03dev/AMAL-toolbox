"""SkinTokens (github.com/VAST-AI-Research/SkinTokens, MIT) on Kaggle's free T4: skin weights for a skeleton that exists.

kaggle_gpu sends this as the Kaggle script with <name>_skin_in.npz beside it ($AMAL_INPUTS; skin_io.py prep wrote it:
the skin's vertices and triangles, the joints' names, heads and parents). It writes <name>_skin_weights.npz to
/kaggle/working: per vertex the 4 strongest joints (indices into joint_names) and their weights, summing to 1.

What it does the way SkinTokens' own `demo.py --use_skeleton` does (same checkpoint, transform, tokenizer, sampling
settings), and where it differs:
- no bpy: the model is given as SkinTokens' own Asset (its npz loader's fields) instead of read by its Blender server,
  so Kaggle's Python 3.13 needs no bpy wheel;
- no flash-attn (a T4 is sm_75; flash-attn 2 needs sm_80): `flash_attn_interface` is a small module here that runs
  PyTorch's scaled_dot_product_attention on the same (batch, length, heads, dim) tensors - SkinTokens' own fallback in
  src/model/skin_vae/attention_processor.py does the same - and the Qwen3 backbone is built with "sdpa" instead of
  "flash_attention_2" (src/model/tokenrig.py:109 asks for it by name);
- the weights are decoded at every vertex of the mesh (with its own normal), not at sampled surface points spread back
  to the vertices by distance: SkinTokens' decoder answers each query point on its own (cross-attention to the skin's
  latent tokens), and spreading by distance mixes the weights of parts that touch (a hand on the chest) - the very
  thing this is for.
bf16 stays (as trained); on a T4 PyTorch runs bf16 without its tensor cores - slower, same numbers.
"""
import glob, json, os, shutil, subprocess, sys, time

REPO_URL = "https://github.com/VAST-AI-Research/SkinTokens"
COMMIT = "273b691d35989d71cd17ff2895fdc735097b92d1"      # checked 2026-11-03
HF_REPO = "VAST-AI/SkinTokens"
CKPTS = ["experiments/skin_vae_2_10_32768/last.ckpt", "experiments/articulation_xl_quantization_256_token_4/grpo_1400.ckpt"]
# SkinTokens asks for transformers>=4.57 and diffusers>=0.35 (its requirements.txt); the 4.x line it was written for
DEPS = ["transformers>=4.57.0,<5", "diffusers>=0.35.0,<0.37", "python-box", "einops", "omegaconf", "lightning", "addict",
        "trimesh", "huggingface_hub", "scipy", "requests"]
TOP_K = 4                 # influences a vertex keeps (game engines take 4; SkinTokens' export also keeps 4)
SAMPLING = dict(top_k=5, top_p=0.95, temperature=1.0, repetition_penalty=2.0, num_beams=10)   # demo.py's defaults
TRIES = 3
OUT = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.getcwd()
WORK = "/kaggle/temp" if os.path.isdir("/kaggle/temp") else "/tmp"

SHIM = '''"""flash_attn_interface for a GPU flash-attn does not run on: the same call, PyTorch's attention."""
import torch.nn.functional as F


def flash_attn_func(q, k, v, dropout_p=0.0, softmax_scale=None, causal=False, *args, **kwargs):
    # flash-attn takes (batch, length, heads, dim); scaled_dot_product_attention (batch, heads, length, dim)
    q, k, v = (t.transpose(1, 2) for t in (q, k, v))
    k, v = k.to(q.dtype), v.to(q.dtype)
    if k.shape[1] != q.shape[1]:
        r = q.shape[1] // k.shape[1]
        k, v = k.repeat_interleave(r, dim=1), v.repeat_interleave(r, dim=1)
    o = F.scaled_dot_product_attention(q, k, v, dropout_p=dropout_p, is_causal=causal, scale=softmax_scale)
    return o.transpose(1, 2), None
'''


def sh(*cmd, cwd=None):
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def top_k(skin, k=TOP_K):
    """(N, J) weights -> the k strongest joints per vertex and their weights, summing to 1 (numpy)."""
    import numpy as np
    k = min(k, skin.shape[1])
    idx = np.argsort(-skin, axis=1)[:, :k]
    w = np.take_along_axis(skin, idx, axis=1).clip(min=0)
    s = w.sum(1, keepdims=True)
    w = np.where(s > 1e-8, w / np.maximum(s, 1e-8), np.eye(k, dtype=w.dtype)[0])
    return idx.astype(np.int32), w.astype(np.float32)


def nearest_joint_skin(vertices, joints):
    """A placeholder skin (each vertex on its nearest joint) for transforms that carry a skin along; never the answer."""
    import numpy as np
    from scipy.spatial import cKDTree
    _, j = cKDTree(joints).query(vertices)
    s = np.zeros((len(vertices), len(joints)), np.float32)
    s[np.arange(len(vertices)), j] = 1.0
    return s


def torch_ok():
    """This GPU runs bf16 matrices and attention in this PyTorch (False: it was not built for the card)."""
    try:
        import torch
        import torch.nn.functional as F
        if not torch.cuda.is_available():
            return False
        x = torch.randn(64, 64, device="cuda", dtype=torch.bfloat16)
        q = torch.randn(1, 4, 16, 32, device="cuda", dtype=torch.bfloat16)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            (x @ x).sum().item()
            F.scaled_dot_product_attention(q, q, q).sum().item()
            torch.nn.Linear(8, 8).cuda()(torch.randn(2, 8, device="cuda")).sum().item()
        print(f"torch {torch.__version__}, {torch.cuda.get_device_name(0)} sm_{''.join(map(str, torch.cuda.get_device_capability(0)))}, "
              f"built for {torch.cuda.get_arch_list()}", flush=True)
        return True
    except Exception as e:  # noqa: BLE001
        print("torch check failed:", e, flush=True)
        return False


def setup():
    if not torch_ok():
        if os.environ.get("AMAL_TORCH_REPLACED"):
            raise SystemExit("AMAL_ERROR PyTorch cannot run on this GPU even after reinstalling it")
        # a PyTorch built without this card (sm_75): the one SkinTokens names, built for CUDA 12.8 (runs on newer drivers)
        sh(sys.executable, "-m", "pip", "install", "-q", "torch==2.7.0", "--index-url", "https://download.pytorch.org/whl/cu128")
        os.environ["AMAL_TORCH_REPLACED"] = "1"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    import torch
    cons = os.path.join(WORK, "amal_constraints.txt")
    open(cons, "w").write(f"torch=={torch.__version__.split('+')[0]}\n")    # the dependencies never swap Kaggle's torch
    sh(sys.executable, "-m", "pip", "install", "-q", "-c", cons, *DEPS)
    repo = os.path.join(WORK, "SkinTokens")
    if not os.path.isdir(os.path.join(repo, "src")):
        sh("git", "clone", "-q", REPO_URL, repo)
        sh("git", "checkout", "-q", COMMIT, cwd=repo)
    shims = os.path.join(WORK, "amal_shims")
    os.makedirs(shims, exist_ok=True)
    open(os.path.join(shims, "flash_attn_interface.py"), "w").write(SHIM)
    os.environ.setdefault("HF_HOME", os.path.join(WORK, "hf"))
    from huggingface_hub import hf_hub_download, snapshot_download
    for c in CKPTS:     # what SkinTokens' download.py --model fetches, to the same places
        t = time.time()
        p = hf_hub_download(repo_id=HF_REPO, filename=c, local_dir=repo)
        print(f"{c}: {os.path.getsize(p) / 1e9:.2f} GB in {time.time() - t:.0f} s", flush=True)
    snapshot_download(repo_id="Qwen/Qwen3-0.6B", local_dir=os.path.join(repo, "models/Qwen3-0.6B"), ignore_patterns=["*.bin", "*.safetensors"])
    return repo, shims


def find_input():
    inp = os.environ.get("AMAL_INPUTS", ".")
    got = glob.glob(os.path.join(inp, "*_skin_in.npz"))
    if not got:   # where Kaggle mounted the upload (its folder layout has changed over time)
        got = [os.path.join(d, f) for d, _, fs in os.walk("/kaggle/input") for f in fs if f.endswith("_skin_in.npz")]
    if not got:
        raise SystemExit("AMAL_ERROR no *_skin_in.npz among the inputs")
    return got[0]


def main():
    if not shutil.which("nvidia-smi"):
        print("AMAL_GPU: none - stopping", flush=True)
        sys.exit(0)
    t0 = time.time()
    inp = find_input()
    repo, shims = setup()
    os.chdir(repo)                        # SkinTokens reads its checkpoints by relative path
    sys.path[:0] = [shims, repo]
    import numpy as np
    import torch
    import transformers
    _from_config = transformers.AutoModelForCausalLM.from_config

    def from_config(*a, **kw):
        if kw.get("attn_implementation") == "flash_attention_2":
            kw["attn_implementation"] = "sdpa"
        return _from_config(*a, **kw)
    transformers.AutoModelForCausalLM.from_config = staticmethod(from_config)

    from src.data.datapath import LazyAsset
    from src.data.dataset import RigDataset
    from src.data.transform import Transform
    from src.rig_package.info.asset import Asset
    from src.server.spec import get_model
    from src.tokenizer.parse import get_tokenizer

    d = np.load(inp)
    if "joint_names" not in d.files:
        return auto_rig(d, inp, t0, np, torch, Asset, LazyAsset, RigDataset, Transform, get_model, get_tokenizer)
    names = [str(x) for x in d["joint_names"]]
    J = len(names)
    joints = d["joints"].astype(np.float32)
    ml = np.tile(np.eye(4, dtype=np.float32), (J, 1, 1))
    ml[:, :3, 3] = joints
    V = d["vertices"].astype(np.float32)
    asset = Asset(vertices=V, faces=d["faces"].astype(np.int64), joint_names=list(names), parents=d["parents"].astype(np.int64),
                  lengths=d["lengths"].astype(np.float32), matrix_world=np.eye(4, dtype=np.float32), matrix_local=ml,
                  skin=nearest_joint_skin(V, joints))
    asset.build_normals()
    print(f"input: {len(V)} vertices, {len(d['faces'])} triangles, {J} joints; set up in {time.time() - t0:.0f} s", flush=True)

    model = get_model(CKPTS[1])
    model.eval()
    print("Qwen3 attention:", getattr(model.transformer.config, "_attn_implementation", "?"), flush=True)
    tokenizer = get_tokenizer(**model.tokenizer_config)
    transform = Transform.parse(**model.transform_config["predict_transform"])

    class Given(LazyAsset):
        def load(self):
            a = asset.copy()
            a.cls, a.path = self.cls, self.path
            return a
    ds = RigDataset(data=[Given(path=inp, cls="articulation")], transform=transform, tokenizer=tokenizer, process_fn=model._process_fn)
    item = ds[0]
    after = [str(x) for x in item.asset.joint_names]
    # SkinTokens' transform drops joints it does not skin (end joints, helpers - AdvancedSkeleton adds many: 130 in, 98
    # kept for his dragon, 2026-11-04). Those carry no weight in a game rig anyway: the kept ones are weighted and the
    # dropped ones get none. Refused only when it renames joints or keeps too few to deform the body.
    if not set(after) <= set(names):
        raise SystemExit(f"AMAL_ERROR SkinTokens' transform renamed joints: {sorted(set(after) - set(names))[:8]}")
    dropped = [n for n in names if n not in after]
    if len(after) < 0.6 * J:
        raise SystemExit(f"AMAL_ERROR SkinTokens kept only {len(after)} of {J} joints - too few to deform the model")
    if dropped:
        print(f"SkinTokens skins {len(after)} of {J} joints; no weight on: {', '.join(dropped[:40])}", flush=True)
    Jk = len(after)
    batch = {k: v.to("cuda") if isinstance(v, torch.Tensor) else v for k, v in ds.collate_fn([item]).items()}
    mask = batch["skeleton_mask"][0] == 1
    skel = batch["skeleton_tokens"][0][mask].cpu().numpy()
    tps = model.tokens_per_skin
    print(f"skeleton: {len(skel)} tokens; skin: {Jk * tps} tokens to make", flush=True)

    # every vertex of the mesh, as SkinTokens sees it after its transform (normalised position + normal)
    if item.asset.vertices.shape[0] != len(V):
        raise SystemExit(f"AMAL_ERROR SkinTokens' transform changed the mesh ({len(V)} vertices in, {item.asset.vertices.shape[0]} after)")
    Q = torch.from_numpy(np.concatenate([item.asset.vertices, item.asset.vertex_normals], 1).astype(np.float32)).cuda()
    skin = None
    for attempt in range(TRIES):
        torch.manual_seed(attempt)
        t = time.time()
        with torch.no_grad():
            res = model.generate(vertices=batch["vertices"][0], normals=batch["normals"][0], cls=batch["cls"][0],
                                 skeleton_tokens=skel, return_decode_dict=True, max_new_tokens=Jk * tps + 4,
                                 num_return_sequences=1, do_sample=True, **SAMPLING)
        ids = res.output_ids
        eos = torch.where(ids == tokenizer.eos)[0]
        if len(eos) == 0:
            print(f"try {attempt + 1}: no skeleton end in the output", flush=True)
            continue
        e = int(eos[0])
        made = tokenizer.detokenize(ids=ids[:e + 1].cpu().numpy()).joints.shape[0]
        sk = ids[e + 1:e + 1 + Jk * tps]
        print(f"try {attempt + 1}: {time.time() - t:.0f} s, {made} joints read back, {len(sk)} of {Jk * tps} skin tokens", flush=True)
        if made != Jk or len(sk) != Jk * tps:
            continue
        out = torch.empty((Q.shape[0], Jk), dtype=torch.float32, device="cuda")
        cond = res.cond_latents.unsqueeze(0)
        jb, chunk = 4, 16384
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
            for s in range(0, Jk, jb):
                b = min(Jk, s + jb) - s
                ind = (sk[s * tps:(s + b) * tps] - tokenizer.vocab_size).unsqueeze(0)
                z = model.vae.model.FSQ.indices_to_codes(ind).reshape(b, tps, -1)
                for c in range(0, Q.shape[0], chunk):
                    q = Q[c:c + chunk].unsqueeze(0).repeat(b, 1, 1)
                    logits = model.vae.decode(z=z, sampled_cond=q, cond_tokens=cond.repeat(b, 1, 1))
                    out[c:c + chunk, s:s + b] = logits.reshape(b, -1).permute(1, 0).float()
        skin = out.cpu().numpy()
        break
    if skin is None:
        raise SystemExit(f"AMAL_ERROR SkinTokens did not make a whole skin in {TRIES} tries")
    # back in the input's joint order (SkinTokens' transform may order them its own way); a dropped joint gets no weight
    full = np.full((skin.shape[0], J), -1e9, dtype=np.float32)
    for i, n in enumerate(after):
        full[:, names.index(n)] = skin[:, i]
    skin = full
    idx, w = top_k(skin)
    stem = os.path.basename(inp)[:-len("_skin_in.npz")]
    dst = os.path.join(OUT, f"{stem}_skin_weights.npz")
    np.savez_compressed(dst, joint_names=np.array(names), idx=idx, w=w, mesh_names=d["mesh_names"], mesh_counts=d["mesh_counts"])
    used = np.bincount(idx[:, 0], minlength=J)
    print("AMAL_INFO " + json.dumps({"vertices": int(len(V)), "joints": J, "joints_leading_somewhere": int((used > 0).sum()),
                                     "seconds": round(time.time() - t0), "file": os.path.basename(dst)}), flush=True)


def auto_rig(d, inp, t0, np, torch, Asset, LazyAsset, RigDataset, Transform, get_model, get_tokenizer):
    """A mesh with no skeleton: SkinTokens (TokenRig, UniRig's successor) makes the skeleton AND the skin, the way its
    demo.py does without --use_skeleton, with its voxel clean-up (--use_postprocess) against weights bleeding between
    parts that touch. Writes <name>_auto_rig.npz: joints (heads, in the mesh's own space), parents, names, and per vertex
    the 4 strongest joints and their weights. (Owner 2026-11-04: AdvancedSkeleton "is clearly a big problem" - use this.)"""
    from src.data.vertex_group import voxel_skin
    try:
        import open3d  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "open3d"], check=False)
    V = d["vertices"].astype(np.float32)
    F = d["faces"].astype(np.int64)
    c = V.mean(0)
    ml = np.eye(4, dtype=np.float32)[None].copy()
    ml[0, :3, 3] = c
    # a one-joint placeholder: the transform carries a skeleton along; the model is not given it (tokens removed below)
    asset = Asset(vertices=V, faces=F, joint_names=["root"], parents=np.array([-1], np.int64), lengths=np.array([0.1], np.float32),
                  matrix_world=np.eye(4, dtype=np.float32), matrix_local=ml, skin=np.ones((len(V), 1), np.float32))
    asset.build_normals()
    print(f"auto rig input: {len(V)} vertices, {len(F)} triangles; set up in {time.time() - t0:.0f} s", flush=True)
    model = get_model(CKPTS[1])
    model.eval()
    tokenizer = get_tokenizer(**model.tokenizer_config)
    transform = Transform.parse(**model.transform_config["predict_transform"])

    class Given(LazyAsset):
        def load(self):
            a = asset.copy()
            a.cls, a.path = self.cls, self.path
            return a
    ds = RigDataset(data=[Given(path=inp, cls="articulation")], transform=transform, tokenizer=tokenizer, process_fn=model._process_fn)
    item = ds[0]
    batch = {k: v.to("cuda") if isinstance(v, torch.Tensor) else v for k, v in ds.collate_fn([item]).items()}
    batch.pop("skeleton_tokens", None)
    batch.pop("skeleton_mask", None)
    batch["generate_kwargs"] = dict(max_length=2048, num_return_sequences=1, do_sample=True, **SAMPLING)
    # SkinTokens samples: each seed gives a different skeleton, and which one deforms best only shows when it moves
    # (the dragon: 3x worst stretch on one, 6x on the next, 2026-11-04). Several are made here, where the model is
    # loaded once (about 45 s each), and AMAL animates each and keeps the best.
    want = int(os.environ.get("AMAL_RIG_SAMPLES", "3"))
    stem = os.path.basename(inp)[:-len("_skin_in.npz")]
    made, seed = [], 0
    while len(made) < want and seed < want * 2:
        torch.manual_seed(seed)
        seed += 1
        t = time.time()
        try:
            with torch.no_grad():
                res = model.predict_step(batch, make_asset=True)["results"][0]
        except Exception as e:  # noqa: BLE001
            print(f"seed {seed - 1}: {type(e).__name__}: {e}", flush=True)
            continue
        got = res.asset
        n = 0 if got is None or got.joints is None else len(got.joints)
        print(f"seed {seed - 1}: {time.time() - t:.0f} s, {n} joints", flush=True)
        if n < 3:
            continue
        # the voxel clean-up (demo.py --use_postprocess) needs open3d, which has no build for Kaggle's Python 3.13: it
        # is tried, and the rig comes back without it rather than not at all (AMAL's deformation check judges it)
        try:
            vox = got.voxel(resolution=196)
            got.skin *= voxel_skin(grid=0, grid_coords=vox.coords, joints=got.joints, vertices=got.vertices, faces=got.faces,
                                   mode="square", voxel_size=vox.voxel_size)
            got.normalize_skin()
        except Exception as e:  # noqa: BLE001
            print(f"voxel clean-up skipped ({type(e).__name__})", flush=True)
        # back to the mesh's own space: the transform moved and scaled it; the same vertices in both give the map exactly
        Vn = np.asarray(got.vertices, np.float64)
        if len(Vn) != len(V):
            print(f"seed {seed - 1}: the transform changed the mesh ({len(V)} vertices in, {len(Vn)} after)", flush=True)
            continue
        A, *_ = np.linalg.lstsq(np.c_[Vn, np.ones(len(Vn))], V.astype(np.float64), rcond=None)
        err = float(np.abs(np.c_[Vn, np.ones(len(Vn))] @ A - V).max() / max(np.ptp(V, 0).max(), 1e-6))
        if err > 0.01:
            print(f"seed {seed - 1}: the transform is not a move-and-scale (worst miss {err:.3f})", flush=True)
            continue
        joints = (np.c_[np.asarray(got.joints, np.float64), np.ones(len(got.joints))] @ A).astype(np.float32)
        J = len(joints)
        names = [str(x) for x in (got.joint_names if got.joint_names is not None else [])] or [f"bone_{i}" for i in range(J)]
        idx, w = top_k(np.asarray(got.skin, np.float32))
        dst = os.path.join(OUT, f"{stem}_auto_rig_{len(made) + 1}.npz")
        np.savez_compressed(dst, joint_names=np.array(names), joints=joints, parents=np.asarray(got.parents, np.int64), idx=idx, w=w,
                            mesh_names=d["mesh_names"], mesh_counts=d["mesh_counts"])
        made.append(os.path.basename(dst))
    if not made:
        raise SystemExit(f"AMAL_ERROR SkinTokens made no usable skeleton in {seed} tries")
    print("AMAL_INFO " + json.dumps({"vertices": int(len(V)), "rigs": made, "seconds": round(time.time() - t0)}), flush=True)


if __name__ == "__main__":
    main()
