#!/usr/bin/env python3
"""Logo marks from real letters, laid out the proven ways - no hand-drawn paths.

AMAL's addition to the logo-design skill (AGPL-3.0, like AMAL). Free models cannot edit long SVG path data (a job read
the same letter files ten times and never made a mark). This builds the marks itself: every font x every layout, in
each palette, plus one contact sheet to look at and show the owner.

Layouts (what brand marks are made of):
  word     the name set tight, letters nearly touching - a wordmark (like SONY, LG)
  tile     the name in a rounded square, reversed out - an app icon (like BMW's roundel idea, Figma's tile)
  badge    the name in a circle - a seal / roundel (like VW, BMW)
  stack    the monogram big, the whole name small beneath it
  cut      the monogram's letters overlapping, each knocked out of the one behind - one interlocked shape (like VW's V over W)

The monogram is the name itself when it is short (SYN, NOVA) and its words' first letters when it is not
(EMBER & OAK -> E&O, Blue Bottle Coffee -> BBC): a long name set small in a tile, or split after its first letter,
does not read. `--picture` takes the marks' colours from a picture they have to belong with (the mascot, a product
shot): its main colours, most telling first.

Usage:
  python marks_svg.py SYN --out brand/syn/marks --fonts russo-one syne michroma --palettes "#E4572E" "#111111"
  -> brand/syn/marks/<font>-<layout>-<n>.svg and brand/syn/marks/sheet.png (render_png.py's renderers)
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import letters_svg  # noqa: E402

LAYOUTS = ("word", "tile", "badge", "stack", "cut")


def glyphs(text, font, weight, tracking):
    """[(path d, x offset, width)], box (x0, y0, x1, y1) in font units (y down), units per em."""
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.boundsPen import BoundsPen
    f = TTFont(letters_svg.font_file(font))
    if "fvar" in f:
        from fontTools.varLib import instancer
        axes = {a.axisTag: a for a in f["fvar"].axes}
        if "wght" in axes:
            f = instancer.instantiateVariableFont(f, {"wght": max(axes["wght"].minValue, min(axes["wght"].maxValue, weight))})
    gs, cmap, upm = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm
    out, x, box = [], 0.0, [1e9, 1e9, -1e9, -1e9]
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            raise SystemExit(f"{font} has no '{ch}'")
        pen, bp = SVGPathPen(gs), BoundsPen(gs)
        gs[g].draw(pen)
        gs[g].draw(bp)
        if bp.bounds:
            x0, y0, x1, y1 = bp.bounds
            box = [min(box[0], x + x0), min(box[1], -y1), max(box[2], x + x1), max(box[3], -y0)]
            out.append((pen.getCommands(), x, (x0, -y1, x1, -y0)))
        x += gs[g].width + tracking * upm
    return out, box, upm


def monogram(text):
    """The few letters that stand for the name: the name itself up to four letters, else its words' first letters
    (a joining & or + between two words stays: E&O)."""
    solid = "".join(ch for ch in text if not ch.isspace())
    if len(solid) <= 4:
        return solid
    words = text.split()
    letters = [w[0] for w in words if w[0].isalnum()]
    if len(words) == 3 and words[1] in ("&", "+") and len(letters) == 2:
        return letters[0] + words[1] + letters[1]
    return "".join(letters)[:4] or solid[:1]


def colours_of(picture, most=3):
    """The main colours of a picture's subject, as hex, most telling first: the background (the colour its border
    is made of) is set aside before the colours are counted - else a figure on a plain ground gives back shades of
    the ground - then strong colours that fill much of the subject come before dull or small ones, and a colour close
    to one already taken is passed over."""
    from PIL import Image
    im = Image.open(picture).convert("RGBA")
    im.thumbnail((200, 200))
    raw = im.tobytes()
    px = [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]
    w, h = im.size
    edge = [px[x + y * w][:3] for x in range(w) for y in (0, h - 1)] + [px[x + y * w][:3] for y in range(h) for x in (0, w - 1)]
    ground = tuple(sorted(c[i] for c in edge)[len(edge) // 2] for i in range(3))
    far = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
    subject = [c[:3] for c in px if c[3] > 127 and far(c[:3], ground) > 48]
    if len(subject) < 50:
        subject = [c[:3] for c in px if c[3] > 127]
    strip = Image.new("RGB", (len(subject), 1))
    strip.putdata(subject)
    q = strip.quantize(colors=10, method=Image.Quantize.MAXCOVERAGE)
    pal = q.getpalette()
    scored = []
    for n, i in q.getcolors():
        r, g, b = pal[i * 3:i * 3 + 3]
        hi, lo = max(r, g, b), min(r, g, b)
        if n < 0.02 * len(subject) or (hi > 235 and lo > 215) or hi < 40:
            continue
        scored.append(((0.25 + (hi - lo) / max(hi, 1)) * (n / len(subject)) ** 0.5, (r, g, b)))
    picked = []
    for _, c in sorted(scored, reverse=True):
        if all(far(c, p) > 70 for p in picked):
            picked.append(c)
    return [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in picked[:most]]


def place(items, box, cx, cy, height):
    """The letters as <path>s scaled so the set is `height` tall, centred on (cx, cy)."""
    s = height / max(box[3] - box[1], 1)
    ox = cx - (box[0] + box[2]) / 2 * s
    oy = cy - (box[1] + box[3]) / 2 * s
    return [f'<path transform="translate({ox + x * s:.2f} {oy:.2f}) scale({s:.5f} {-s:.5f})" d="{d}"/>' for d, x, _ in items], s


def svg(body, w=512, h=512, title=""):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><title>{title}</title>{body}</svg>\n'


def make(text, font, layout, colour, ink, weight):
    mono = monogram(text)
    long_name = mono != "".join(ch for ch in text if not ch.isspace())
    if layout == "word":
        items, box, _ = glyphs(text, font, weight, -0.03)
        wide = (box[2] - box[0]) / max(box[3] - box[1], 1)
        paths, _ = place(items, box, 256, 256, min(160, 440 / wide))
        return svg(f'<g fill="{colour}">{"".join(paths)}</g>', title=text)
    if layout == "tile":
        # an app icon holds a few letters: a long name's monogram
        items, box, _ = glyphs(mono, font, weight, 0.0)
        wide = (box[2] - box[0]) / max(box[3] - box[1], 1)
        paths, _ = place(items, box, 256, 256, min(200, 360 / wide))
        return svg(f'<rect x="16" y="16" width="480" height="480" rx="112" fill="{colour}"/><g fill="{ink}">{"".join(paths)}</g>', title=text)
    if layout == "badge":
        ring = (f'<circle cx="256" cy="256" r="236" fill="{colour}"/><circle cx="256" cy="256" r="206" fill="none" stroke="{ink}" '
                f'stroke-width="10"/>')
        if long_name:
            # a seal: the monogram in the middle, the whole name beneath it inside the ring
            big, bbox, _ = glyphs(mono, font, weight, 0.0)
            name, nbox, _ = glyphs(text, font, weight, 0.06)
            bw, nw = (bbox[2] - bbox[0]) / max(bbox[3] - bbox[1], 1), (nbox[2] - nbox[0]) / max(nbox[3] - nbox[1], 1)
            top, _ = place(big, bbox, 256, 226, min(150, 270 / bw))
            under, _ = place(name, nbox, 256, 356, min(34, 290 / nw))
            return svg(f'{ring}<g fill="{ink}">{"".join(top)}{"".join(under)}</g>', title=text)
        items, box, _ = glyphs(text, font, weight, 0.0)
        wide = (box[2] - box[0]) / max(box[3] - box[1], 1)
        paths, _ = place(items, box, 256, 256, min(170, 330 / wide))
        return svg(f'{ring}<g fill="{ink}">{"".join(paths)}</g>', title=text)
    if layout == "stack":
        first, fbox, _ = glyphs(mono if long_name else text[0], font, weight, 0)
        # beneath: the whole name (a name split after its first letter - E / MBER - does not read)
        rest, rbox, _ = glyphs(text, font, weight, 0.08)
        fw, rw = (fbox[2] - fbox[0]) / max(fbox[3] - fbox[1], 1), (rbox[2] - rbox[0]) / max(rbox[3] - rbox[1], 1)
        big, _ = place(first, fbox, 256, 215, min(270, 440 / fw))
        small, _ = place(rest, rbox, 256, 430, min(54, 460 / rw))
        return svg(f'<g fill="{colour}">{"".join(big)}{"".join(small)}</g>', title=text)
    if layout == "cut":
        # each letter drawn over the one before with a background-coloured outline: overlaps read as one interlocked
        # mark. Letters only (an & between them would be cut to pieces), and the outline is a share of the letter's
        # own size - on a long name it was wider than the letters and the mark came out blank
        letters = "".join(ch for ch in mono if ch.isalnum()) or mono
        items, box, upm = glyphs(letters, font, weight, -0.22)
        wide = (box[2] - box[0]) / max(box[3] - box[1], 1)
        paths, s = place(items, box, 256, 256, min(260, 470 / wide))
        gap = min(18 / max(s, 1e-6), 0.05 * upm)
        body = "".join(f'<g fill="{colour}" stroke="#ffffff" stroke-width="{gap:.1f}" paint-order="stroke">{p}</g>' for p in paths)
        return svg(f'<rect width="512" height="512" fill="#ffffff"/>{body}', title=text)
    raise SystemExit(f"unknown layout {layout}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fonts", nargs="+", default=["russo-one", "syne", "michroma", "archivo-black"])
    ap.add_argument("--layouts", nargs="+", default=list(LAYOUTS), choices=LAYOUTS)
    ap.add_argument("--palettes", nargs="+", default=["#111111"], help="main colours; text on tiles/badges is --ink")
    ap.add_argument("--picture", default="", help="a picture the marks belong with: its main colours are the palette")
    ap.add_argument("--ink", default="#ffffff")
    ap.add_argument("--weight", type=float, default=800)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.picture and a.picture != "none":
        found = colours_of(a.picture)
        if found:
            a.palettes = found
            print(f"colours from {os.path.basename(a.picture)}: {' '.join(found)}")
    made = []
    for font in a.fonts:
        for layout in a.layouts:
            for i, colour in enumerate(a.palettes, 1):
                name = f"{font}-{layout}" + (f"-{i}" if len(a.palettes) > 1 else "")
                p = os.path.join(a.out, name + ".svg")
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(make(a.text, font, layout, colour, a.ink, a.weight))
                made.append(p)
    print(f"wrote {len(made)} marks to {a.out}")
    # one sheet of all of them on white, to look at and to show
    sheet = os.path.join(a.out, "sheet.svg")
    cols, cell = len(a.layouts) * len(a.palettes), 220
    rows = (len(made) + cols - 1) // cols
    parts = [f'<rect width="{cols * cell}" height="{rows * (cell + 26)}" fill="#ffffff"/>']
    for k, p in enumerate(made):
        inner = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", open(p, encoding="utf-8").read().strip())
        inner = re.sub(r"<title>.*?</title>", "", inner)
        x, y = (k % cols) * cell, (k // cols) * (cell + 26)
        parts.append(f'<g transform="translate({x + 10} {y + 10}) scale({(cell - 20) / 512:.4f})">{inner}</g>'
                     f'<text x="{x + cell / 2}" y="{y + cell + 14}" font-family="sans-serif" font-size="12" text-anchor="middle" fill="#555">'
                     f'{os.path.basename(p)[:-4]}</text>')
    with open(sheet, "w", encoding="utf-8") as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cols * cell} {rows * (cell + 26)}">{"".join(parts)}</svg>\n')
    subprocess.run([sys.executable, os.path.join(HERE, "render_png.py"), sheet, "-o", sheet[:-4] + ".png",
                    "--width", str(cols * cell), "--height", str(rows * (cell + 26))], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
