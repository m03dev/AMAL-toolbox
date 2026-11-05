#!/usr/bin/env python3
"""Logo marks from real letters, laid out the proven ways - no hand-drawn paths.

MODO's addition to the logo-design skill (AGPL-3.0, like MODO). Free models cannot edit long SVG path data (a job read
the same letter files ten times and never made a mark). This builds the marks itself: every font x every layout, in
each palette, plus one contact sheet to look at and show the owner.

Layouts (what brand marks are made of):
  word     the name set tight, letters nearly touching - a wordmark (like SONY, LG)
  tile     the name in a rounded square, reversed out - an app icon (like BMW's roundel idea, Figma's tile)
  badge    the name in a circle - a seal / roundel (like VW, BMW)
  stack    first letter big, the rest small beneath it - a monogram with its name
  cut      the letters overlapping, each knocked out of the one behind - one interlocked shape (like VW's V over W)

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


def place(items, box, cx, cy, height):
    """The letters as <path>s scaled so the set is `height` tall, centred on (cx, cy)."""
    s = height / max(box[3] - box[1], 1)
    ox = cx - (box[0] + box[2]) / 2 * s
    oy = cy - (box[1] + box[3]) / 2 * s
    return [f'<path transform="translate({ox + x * s:.2f} {oy:.2f}) scale({s:.5f} {-s:.5f})" d="{d}"/>' for d, x, _ in items], s


def svg(body, w=512, h=512, title=""):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><title>{title}</title>{body}</svg>\n'


def make(text, font, layout, colour, ink, weight):
    track = {"word": -0.03, "cut": -0.22}.get(layout, 0.0)
    items, box, _ = glyphs(text, font, weight, track)
    wide = (box[2] - box[0]) / max(box[3] - box[1], 1)
    if layout == "word":
        paths, _ = place(items, box, 256, 256, min(160, 440 / wide))
        return svg(f'<g fill="{colour}">{"".join(paths)}</g>', title=text)
    if layout == "tile":
        paths, _ = place(items, box, 256, 256, min(200, 360 / wide))
        return svg(f'<rect x="16" y="16" width="480" height="480" rx="112" fill="{colour}"/><g fill="{ink}">{"".join(paths)}</g>', title=text)
    if layout == "badge":
        paths, _ = place(items, box, 256, 256, min(170, 330 / wide))
        return svg(f'<circle cx="256" cy="256" r="236" fill="{colour}"/><circle cx="256" cy="256" r="206" fill="none" stroke="{ink}" '
                   f'stroke-width="10"/><g fill="{ink}">{"".join(paths)}</g>', title=text)
    if layout == "stack":
        first, fbox, _ = glyphs(text[0], font, weight, 0)
        rest, rbox, _ = glyphs(text[1:] or text, font, weight, 0.08)
        big, _ = place(first, fbox, 256, 220, 280)
        small, _ = place(rest, rbox, 256, 430, 54)
        return svg(f'<g fill="{colour}">{"".join(big)}{"".join(small)}</g>', title=text)
    if layout == "cut":
        # each letter drawn over the one before with a background-coloured outline: overlaps read as one interlocked mark
        paths, s = place(items, box, 256, 256, min(260, 470 / wide))
        gap = 18 / max(s, 1e-6)
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
    ap.add_argument("--ink", default="#ffffff")
    ap.add_argument("--weight", type=float, default=800)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
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
