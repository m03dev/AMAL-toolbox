"""Cut the subjects out of a picture, each into its own picture, unchanged.

    python cut_out.py picture.png --out-dir renders/cut_out --subjects 2 --name character

The background is taken away one of three ways, the first that fits: the picture's own transparency; a plain
background (the border is one colour); a background remover (rembg) for a photo, a screenshot or a busy background.
What is left is told apart into subjects: parts that stand apart are subjects by themselves; when --subjects asks for
more than stand apart, the widest part is cut along the cheapest line from top to bottom between its figures - the line
that crosses the least of the figures and keeps to the borders between their colours.
Writes <name>_<n>.png (transparent) and <name>_<n>_white.png for each, left to right, and cut_out_report.json.
Exit 1 when nothing stands out from the background or the picture holds fewer subjects than asked.
"""
import argparse, json, subprocess, sys
from pathlib import Path


def need(*packages):
    """Import what this uses; install it once into this Python when it is missing."""
    missing = []
    for module, package in packages:
        try: __import__(module)
        except ImportError: missing.append(package)
    if missing:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", *missing], check=False)
        if subprocess.run([sys.executable, "-c", "import " + ",".join(m for m, _ in packages)]).returncode != 0:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--break-system-packages", *missing], check=True)


need(("numpy", "numpy"), ("cv2", "opencv-python-headless"), ("PIL", "pillow"))
import cv2
import numpy as np
from PIL import Image


def foreground(path):
    """The picture as RGB and the mask of what is not background, and which way the background was taken away."""
    rgba = np.asarray(Image.open(path).convert("RGBA")).copy()
    rgb = rgba[..., :3]
    if (rgba[..., 3] < 128).mean() > 0.02:
        return rgb, (rgba[..., 3] >= 128).astype(np.uint8), "its own transparency"
    flat = rgb.astype(np.float64)
    border = np.concatenate([flat[0], flat[-1], flat[:, 0], flat[:, -1]])
    if border.std(axis=0).max() <= 12:
        away = (np.linalg.norm(flat - np.median(border, axis=0), axis=2) > 28).astype(np.uint8)
        return rgb, away, "a plain background"
    need(("rembg", "rembg"), ("onnxruntime", "onnxruntime"))
    import rembg
    cut = None
    for model in ("birefnet-general", "isnet-general-use", "u2net"):
        try:
            cut = np.asarray(rembg.remove(Image.fromarray(rgb), session=rembg.new_session(model)).convert("RGBA"))
            break
        except Exception as e:  # a model that will not download or load: the next one
            print(f"[cut-out] {model}: {e}", flush=True)
    if cut is None:
        raise SystemExit(f"{path}: the background is not plain and no background remover could be loaded")
    return rgb, (cut[..., 3] >= 128).astype(np.uint8), "a background remover"


def tidy(mask):
    """Specks gone, pinholes closed; parts under 2% of the biggest are not subjects."""
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count < 2:
        return []
    big = stats[1:, cv2.CC_STAT_AREA].max()
    parts = [(labels == i).astype(np.uint8) for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 0.02 * big]
    return sorted(parts, key=lambda m: np.where(m.any(axis=0))[0].mean())


def part_in_two(mask, rgb):
    """One part that holds two figures side by side, cut where they meet: the top-to-bottom line that crosses the
    least of the part and, where it must cross, keeps to a border between two colours."""
    h, w = mask.shape
    xs = np.where(mask.any(axis=0))[0]
    x0, x1 = xs.min(), xs.max()
    # the line may run anywhere but the outer sixth on either side: a figure is never sliced off at its edge
    left, right = x0 + (x1 - x0) // 6, x1 - (x1 - x0) // 6
    if right - left < 8:
        return None
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gx, gy = cv2.Sobel(grey, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(grey, cv2.CV_32F, 0, 1, ksize=3)
    edge = cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), 1.5)
    edge = np.clip(edge / (np.percentile(edge[mask > 0], 98) or 1.0), 0.0, 1.0)
    # free outside the part; inside it, cheap along a border between two colours and dear across a flat colour - so
    # the line goes round the figures where it can and between them where they touch, not through one of them
    cost = np.where(mask > 0, 1.0 - 0.9 * edge, 0.0)[:, left:right + 1]
    total = cost.copy()
    for y in range(1, h):
        above = total[y - 1]
        best = np.minimum(above, np.minimum(np.roll(above, 1), np.roll(above, -1)))
        best[0], best[-1] = min(above[0], above[1]), min(above[-1], above[-2])
        total[y] += best
    seam = np.zeros(h, np.int64)
    seam[-1] = int(np.argmin(total[-1]))
    for y in range(h - 2, -1, -1):
        x = seam[y + 1]
        lo, hi = max(0, x - 1), min(total.shape[1] - 1, x + 1)
        seam[y] = lo + int(np.argmin(total[y, lo:hi + 1]))
    seam += left
    columns_at = np.arange(w)[None, :]
    a = (mask > 0) & (columns_at <= seam[:, None])
    b = (mask > 0) & (columns_at > seam[:, None])
    out = []
    for half in (a, b):
        # each side keeps its biggest piece; crumbs the line left on the wrong side go back to the other
        count, labels, stats, _ = cv2.connectedComponentsWithStats(half.astype(np.uint8), connectivity=8)
        if count < 2:
            return None
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        out.append(labels == keep)
    crumbs = (mask > 0) & ~out[0] & ~out[1]
    if crumbs.any():
        near_a = cv2.distanceTransform((~out[0]).astype(np.uint8), cv2.DIST_L2, 3)
        near_b = cv2.distanceTransform((~out[1]).astype(np.uint8), cv2.DIST_L2, 3)
        out[0] |= crumbs & (near_a <= near_b)
        out[1] |= crumbs & (near_a > near_b)
    return [m.astype(np.uint8) for m in out]


def write(rgb, mask, stem):
    ys, xs = np.where(mask > 0)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    alpha = cv2.GaussianBlur((mask * 255).astype(np.uint8), (5, 5), 0)
    cut = Image.fromarray(np.dstack([rgb, alpha])[y0:y1 + 1, x0:x1 + 1], "RGBA")
    side = int(max(cut.size) * 1.14)
    at = ((side - cut.width) // 2, (side - cut.height) // 2)
    clear = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    clear.paste(cut, at, cut)
    white = Image.new("RGB", (side, side), (255, 255, 255))
    white.paste(cut, at, cut)
    if side > 2048:
        clear, white = clear.resize((2048, 2048), Image.LANCZOS), white.resize((2048, 2048), Image.LANCZOS)
    clear.save(f"{stem}.png")
    white.save(f"{stem}_white.png")
    return {"transparent": f"{stem}.png", "on_white": f"{stem}_white.png", "box_in_picture": [int(x0), int(y0), int(x1), int(y1)],
            "share_of_picture": round(float(mask.mean()), 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("picture", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("renders/cut_out"))
    ap.add_argument("--subjects", type=int, default=0)
    ap.add_argument("--name", default="subject")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / "cut_out_report.json"
    rgb, mask, how = foreground(args.picture)
    parts = tidy(mask)
    report = {"picture": str(args.picture), "background_taken_away_by": how, "asked_for": args.subjects}
    if not parts:
        report.update(result="FAIL", why="nothing stands out from the background")
        report_path.write_text(json.dumps(report, indent=2))
        print("[cut-out] FAIL: " + report["why"])
        return 1
    parted = 0
    while 0 < len(parts) < args.subjects:
        widest = max(range(len(parts)), key=lambda i: np.ptp(np.where(parts[i].any(axis=0))[0]))
        two = part_in_two(parts[widest], rgb)
        if not two:
            break
        parts[widest:widest + 1] = two
        parted += 1
    if args.subjects and len(parts) > args.subjects:      # more parts than subjects: the biggest ones are the subjects
        parts = sorted(sorted(parts, key=lambda m: -int(m.sum()))[:args.subjects], key=lambda m: np.where(m.any(axis=0))[0].mean())
    report["subjects"] = [write(rgb, m, str(args.out_dir / f"{args.name}_{i + 1}")) for i, m in enumerate(parts)]
    report["parted_where_they_touch"] = parted
    ok = not args.subjects or len(parts) == args.subjects
    report["result"] = "PASS" if ok else "FAIL"
    if not ok:
        report["why"] = f"{len(parts)} subject(s) found where {args.subjects} were asked for"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"[cut-out] {report['result']}: {len(parts)} subject(s), background taken away by {how}"
          + (f", {parted} parted where they touch" if parted else "") + (f"; {report.get('why')}" if not ok else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
