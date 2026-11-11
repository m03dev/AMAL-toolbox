#!/usr/bin/env python3
"""Pixel Match for any textured .glb: the reference picture's own pixels back on the model.

The painting is AssetFurnace's (github.com/Bingeljell/image-to-3dlab, Apache-2.0, pinned below): it needs the camera
each picture was taken from, which its own generator saves. A model from anywhere else has none, so this finds it:
the picture is cut out, and the camera's turn, field of view, distance and place are searched for where the model's
outline lies on the cut-out. An outline looks the same from the front and, mirrored, from the back, so among the
turns that fit, the one whose view of the model's own paint looks most like the picture is taken.

    pixel_match.py model.glb picture.png [--back back.png] [--out out.glb] [--min-fit 0.8]

Writes out.glb (only its base-colour image differs from the model), <out>_report.json and <out>_compare.png.
Exit 1 with FAIL in the report when no picture fits; nothing is painted then.
"""
import argparse, io, json, subprocess, sys, urllib.request
from pathlib import Path

UPSTREAM = "Bingeljell/image-to-3dlab"
COMMIT = "f6d7559cae6d8468e7fc10188c08708baa70408a"
FILES = ["image_to_3dlab/photo_paint.py", "image_to_3dlab/view_align.py", "LICENSE", "NOTICE"]


def need(*packages):
    """Import what the painting uses; install it once into this Python when it is missing."""
    missing = []
    for module, package in packages:
        try: __import__(module)
        except ImportError: missing.append(package)
    if missing:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", *missing], check=False)
        if subprocess.run([sys.executable, "-c", "import " + ",".join(m for m, _ in packages)]).returncode != 0:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--break-system-packages", *missing], check=True)


def upstream():
    """AssetFurnace's two files at the pinned commit, fetched once and kept beside this script."""
    home = Path(__file__).resolve().parent / "upstream" / COMMIT[:12]
    for name in FILES:
        to = home / name
        if not to.is_file():
            to.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(f"https://raw.githubusercontent.com/{UPSTREAM}/{COMMIT}/{name}", timeout=60) as r:
                to.write_bytes(r.read())
    (home / "image_to_3dlab" / "__init__.py").touch()
    sys.path.insert(0, str(home))


need(("numpy", "numpy"), ("scipy", "scipy"), ("cv2", "opencv-python-headless"), ("PIL", "pillow"))
upstream()
import cv2
import numpy as np
from PIL import Image
from image_to_3dlab import photo_paint as pp
from image_to_3dlab import view_align

GLB_FRAME = ((0, 1, 2), (1, 1, 1))   # the cameras found here live in the model's own coordinates
SEARCH_PX = 160                       # the outline search runs on small pictures


def node_matrix(node):
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    if "scale" in node:
        m[:3, :3] = m[:3, :3] * np.asarray(node["scale"], dtype=np.float64)
    if "translation" in node:
        m[:3, 3] = node["translation"]
    return m


def read_model(path):
    """Every part of the model that wears the base-colour image, where its nodes put it: positions, UVs, faces,
    the image. A model in several parts or with moved nodes is painted as it stands in the scene."""
    doc, binary = pp._split_glb(Path(path).read_bytes())
    image_index = pp.base_colour_image_index(doc)
    def wears(prim):
        try:
            tex = doc["materials"][prim["material"]]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
            return doc["textures"][tex].get("source", doc["textures"][tex].get("extensions", {}).get("EXT_texture_webp", {}).get("source")) == image_index
        except (KeyError, IndexError):
            return False
    parts, roots = [], doc.get("scenes", [{}])[doc.get("scene", 0)].get("nodes", list(range(len(doc.get("nodes", [])))))
    def walk(index, parent):
        node = doc["nodes"][index]
        world = parent @ node_matrix(node)
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                a = prim["attributes"]
                if "TEXCOORD_0" not in a or "indices" not in prim or prim.get("mode", 4) != 4 or not wears(prim):
                    continue
                p = pp._accessor(doc, binary, a["POSITION"]).astype(np.float64)
                parts.append((p @ world[:3, :3].T + world[:3, 3], pp._accessor(doc, binary, a["TEXCOORD_0"]).astype(np.float64),
                              pp._accessor(doc, binary, prim["indices"]).reshape(-1, 3).astype(np.int64)))
        for child in node.get("children", []):
            walk(child, world)
    for root in roots:
        walk(root, np.eye(4))
    if not parts:
        raise SystemExit("this model has no part with a base-colour picture and UVs: there is no texture to paint")
    offset, positions, uvs, faces = 0, [], [], []
    for p, uv, f in parts:
        positions.append(p); uvs.append(uv); faces.append(f + offset); offset += len(p)
    image = doc["images"][image_index]
    view = doc["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    picture = Image.open(io.BytesIO(binary[start:start + view["byteLength"]]))
    texture = np.asarray(picture.convert("RGBA" if "A" in picture.getbands() else "RGB"))
    return np.concatenate(positions), np.concatenate(uvs), np.concatenate(faces), texture


def cut_out(path):
    """The picture as RGBA with its subject cut out: its own transparency when it has some, else the plain
    background the border shows (white, grey, any one colour) taken away."""
    rgba = np.asarray(Image.open(path).convert("RGBA")).copy()
    if (rgba[..., 3] < 128).mean() > 0.02:
        return rgba
    rgb = rgba[..., :3].astype(np.float64)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    if border.std(axis=0).max() > 12:
        raise SystemExit(f"{path}: the picture has no transparency and its background is not one plain colour - cut the subject out first")
    away = np.linalg.norm(rgb - np.median(border, axis=0), axis=2) > 28
    away = cv2.morphologyEx(away.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(away, connectivity=8)
    if count < 2:
        raise SystemExit(f"{path}: nothing stands out from the background")
    keep = np.isin(labels, [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 0.02 * stats[1:, cv2.CC_STAT_AREA].max()])
    # holes inside the subject that happen to be the background's colour (a white eye on white) stay part of it
    filled = keep.astype(np.uint8)
    contours, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    rgba[..., 3] = np.where(filled > 0, 255, 0)
    return rgba


def turns():
    """The 24 ways a camera can stand square to a model: which way it looks and which way is up."""
    axes = [np.array(a, dtype=np.float64) for a in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
    for back in axes:           # the camera looks down its own -Z: `back` points from the model to the camera
        for up in axes:
            if abs(back @ up) < 0.5:
                yield np.stack([np.cross(up, back), up, back], axis=1)


def camera(rotation, centre, distance, shift=(0.0, 0.0)):
    m = np.eye(4)
    m[:3, :3] = rotation
    m[:3, 3] = centre + rotation[:, 2] * distance + rotation[:, 0] * shift[0] + rotation[:, 1] * shift[1]
    return m


def outline(positions, faces, view):
    x, y, depth = pp.project(positions, view)
    h, w = view.image.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    if (depth <= 0).any():
        return mask.astype(bool)
    cv2.fillPoly(mask, np.round(np.stack([x, y], axis=1)[faces] * 16).astype(np.int32), 1, shift=4)
    return mask.astype(bool)


def box(mask):
    ys, xs = np.nonzero(mask)
    return xs.min(), xs.max() + 1, ys.min(), ys.max() + 1


def iou(a, b):
    union = (a | b).sum()
    return float((a & b).sum()) / union if union else 0.0


def place(positions, faces, small, rotation, fov, centre, radius):
    """The camera with this turn and field of view whose view of the model fills the cut-out's box: distance from
    the box's size, sideways place from its centre, settled over a few rounds. Returns (fit, matrix)."""
    matte = small[..., 3] > 127
    x0, x1, y0, y1 = box(matte)
    focal = (small.shape[1] / 2.0) / np.tan(fov / 2.0)
    distance, shift = radius / np.tan(fov / 2.0) * 1.2, np.zeros(2)
    best = (0.0, None)
    for _ in range(4):
        matrix = camera(rotation, centre, distance, shift)
        seen = outline(positions, faces, pp.View(small, matrix, fov))
        if not seen.any():
            break
        fit = iou(seen, matte)
        if fit > best[0]:
            best = (fit, matrix)
        a0, a1, b0, b1 = box(seen)
        # the model's box against the cut-out's, along the cut-out's longer side: farther makes it smaller
        size = (a1 - a0) / max(x1 - x0, 1) if (x1 - x0) > (y1 - y0) else (b1 - b0) / max(y1 - y0, 1)
        distance *= size if size > 0 else 1.0
        shift = shift + np.array([((a0 + a1) - (x0 + x1)) / 2.0, -((b0 + b1) - (y0 + y1)) / 2.0]) * distance / focal
    return best


def alike(own, seen, picture):
    """How alike the model's own paint, seen by a camera, and the picture are where both show (0 to 1)."""
    both = seen & (picture[..., 3] > 127)
    if both.sum() < 50:
        return 0.0
    a = cv2.GaussianBlur(own, (0, 0), 2)[both].astype(np.float64)
    b = cv2.GaussianBlur(picture[..., :3], (0, 0), 2)[both].astype(np.float64)
    a, b = a - a.mean(axis=0), b - b.mean(axis=0)
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float(max(0.0, (a * b).sum() / den)) if den > 0 else 0.0


def find_camera(positions, uvs, faces, texture, rgba):
    """The camera the picture was taken from: (fit, likeness, View at the picture's full size)."""
    scale = SEARCH_PX / max(rgba.shape[:2])
    small = cv2.resize(rgba, (max(8, round(rgba.shape[1] * scale)), max(8, round(rgba.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    low, high = positions.min(axis=0), positions.max(axis=0)
    centre, radius = (low + high) / 2.0, float(np.linalg.norm(high - low)) / 2.0
    tried = []
    for rotation in turns():
        for fov in (0.15, 0.45, 0.75):   # a far lens (image-to-3D pictures are nearly flat), a normal one, a wide one
            fit, matrix = place(positions, faces, small, rotation, fov, centre, radius)
            if matrix is not None:
                tried.append((fit, fov, matrix))
    if not tried:
        raise SystemExit("the model could not be seen from any side")
    tried.sort(key=lambda t: -t[0])
    top = tried[0][0]
    # the turns that fit as well as the best (a mirror-symmetric outline fits from the front and the back alike):
    # the model's own paint tells them apart
    chosen = None
    for fit, fov, matrix in [t for t in tried if t[0] >= top - 0.03][:8]:
        view = pp.View(small, matrix, fov)
        seen, own = view_align.render_own_paint(positions, uvs, faces, texture, view, GLB_FRAME, 1.0)
        like = alike(own, seen, small)
        if chosen is None or fit + 0.5 * like > chosen[0] + 0.5 * chosen[1]:
            chosen = (fit, like, fov, matrix)
    fit, like, fov, matrix = chosen
    return fit, like, pp.View(rgba, matrix, fov, "picture")


def look(positions, uvs, faces, texture, view, size=512):
    s = size / max(view.image.shape[:2])
    small = cv2.resize(view.image, (round(view.image.shape[1] * s), round(view.image.shape[0] * s)), interpolation=cv2.INTER_AREA)
    seen, own = view_align.render_own_paint(positions, uvs, faces, texture, pp.View(small, view.cam_to_world, view.fov_x), GLB_FRAME, 1.0)
    own[~seen] = 255
    flat = small[..., :3].copy()
    flat[small[..., 3] < 128] = 255
    return seen, own, flat, small


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model", type=Path)
    ap.add_argument("picture", type=Path)
    ap.add_argument("--back", default="none")
    ap.add_argument("--out", type=Path, default=Path("renders/pixel_match.glb"))
    ap.add_argument("--min-fit", type=float, default=0.8)
    args = ap.parse_args()
    report_path = args.out.with_name(args.out.stem + "_report.json")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    positions, uvs, faces, texture = read_model(args.model)
    pictures = [args.picture] + ([Path(args.back)] if args.back not in ("", "none") else [])
    views, found = [], []
    for path in pictures:
        rgba = cut_out(path)
        fit, like, view = find_camera(positions, uvs, faces, texture, rgba)
        used = bool(fit >= args.min_fit)
        found.append({"picture": str(path), "outline_fit": round(fit, 3), "likeness_to_own_paint": round(like, 3), "used": used,
                      "field_of_view_deg": round(float(np.degrees(view.fov_x)), 1), "camera_to_model": np.round(view.cam_to_world, 5).tolist()})
        print(f"[pixel-match] {path.name}: outline fit {fit:.3f}, likeness {like:.3f}, {'used' if used else 'NOT used (under ' + str(args.min_fit) + ')'}", flush=True)
        if used:
            views.append(view)
    report = {"model": str(args.model), "upstream": f"{UPSTREAM}@{COMMIT[:12]}", "pictures": found}
    if not views:
        report.update(result="FAIL", why="the model's outline does not lie on the picture from any side - is this the picture the model was made from?")
        report_path.write_text(json.dumps(report, indent=2))
        print("[pixel-match] FAIL: " + report["why"])
        return 1
    reports = []
    painted, weight = pp.paint_texture(texture, positions, uvs, faces, views, 1.0, frame=GLB_FRAME, align_reports=reports)
    share = float((weight > 0.5).mean())
    for entry, r in zip([f for f in found if f["used"]], reports):
        entry.update(outline_fit_after_nudge=round(float(r.iou_after), 3), feature_matches=int(r.matches))
    # how far the model's look, from the picture's camera, is from the picture - before and after
    seen, before, flat, small = look(positions, uvs, faces, texture, views[0])
    _, after, _, _ = look(positions, uvs, faces, painted, views[0])
    both = seen & (small[..., 3] > 127)
    err = lambda img: float(np.abs(img[both].astype(np.float64) - flat[both]).mean()) if both.any() else 0.0
    report.update(texture_from_picture=round(share, 3), colour_error_before=round(err(before), 2), colour_error_after=round(err(after), 2))
    ok = bool(share >= 0.03 and err(after) < err(before))
    report["result"] = "PASS" if ok else "FAIL"
    if not ok:
        report["why"] = "the painted model does not look more like the picture than before" if share >= 0.03 else "the picture reached almost none of the texture"
    Image.fromarray(np.concatenate([flat, before, after], axis=1)).save(args.out.with_name(args.out.stem + "_compare.png"))
    if ok:
        args.out.write_bytes(pp.replace_base_colour(Path(args.model).read_bytes(), pp.encode_png(painted)))
    report_path.write_text(json.dumps(report, indent=2))
    print(f"[pixel-match] {report['result']}: {share:.0%} of the texture from the picture; colour error {err(before):.1f} -> {err(after):.1f}"
          + (f"; wrote {args.out}" if ok else f"; {report.get('why')}"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
