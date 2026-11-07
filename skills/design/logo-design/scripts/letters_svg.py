#!/usr/bin/env python3
"""Letters as real outlines: text -> SVG paths from a proper typeface, one <path> per letter.

AMAL's addition to the logo-design skill (AGPL-3.0, like AMAL). A model drawing letter shapes by hand in SVG code makes
letters nobody can read (owner 2026-11-01: SYN marks that "didn't look anything like the letters"). Every lettermark,
monogram and wordmark starts here instead: the letters come from a well-drawn open font, then you design with them -
overlap them, share a stroke, cut one, put them in a badge - keeping each letter readable.

Usage:
  python letters_svg.py SYN -o brand/syn/letters.svg --font archivo-black
  python letters_svg.py SYN -o out.svg --font syne --weight 800 --tracking -0.04
  python letters_svg.py --list                       # the fonts it knows (all SIL Open Font License, free for logos)
  python letters_svg.py SYN -o out.svg --font path/to/any.ttf

Output: viewBox tight around the letters, each letter <path id="L0-S" ...> with its own transform, so you can move or
merge them. Needs fontTools (pip install fonttools); fonts download once from github.com/google/fonts.
"""
import argparse
import os
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
# name -> (path under ofl/, what it looks like). Picked for marks: strong, geometric, distinct.
FONTS = {
    "archivo-black": ("archivoblack/ArchivoBlack-Regular.ttf", "heavy grotesque, bold and solid"),
    "bebas-neue": ("bebasneue/BebasNeue-Regular.ttf", "tall condensed caps"),
    "russo-one": ("russoone/RussoOne-Regular.ttf", "squared, technical, heavy"),
    "michroma": ("michroma/Michroma-Regular.ttf", "wide, squared, engineered"),
    "audiowide": ("audiowide/Audiowide-Regular.ttf", "rounded, wide, tech"),
    "righteous": ("righteous/Righteous-Regular.ttf", "rounded retro display"),
    "syne": ("syne/Syne%5Bwght%5D.ttf", "art-school grotesque, wide at heavy weights"),
    "space-grotesk": ("spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf", "quirky geometric grotesque"),
    "sora": ("sora/Sora%5Bwght%5D.ttf", "clean geometric sans"),
    "outfit": ("outfit/Outfit%5Bwght%5D.ttf", "round geometric sans"),
    "orbitron": ("orbitron/Orbitron%5Bwght%5D.ttf", "sci-fi geometric"),
    "unbounded": ("unbounded/Unbounded%5Bwght%5D.ttf", "very wide rounded display"),
}


def font_dir():
    home = os.environ.get("AMAL_HOME")
    base = os.path.join(os.path.dirname(home), "fonts") if home else os.path.join(os.path.expanduser("~"), ".cache", "amal-fonts")
    os.makedirs(base, exist_ok=True)
    return base


def font_file(name):
    if os.path.isfile(name):
        return name
    if name not in FONTS:
        sys.exit(f"unknown font '{name}' - use --list, or give a .ttf/.otf path")
    rel, _ = FONTS[name]
    dest = os.path.join(font_dir(), rel.replace("/", "_").replace("%5B", "[").replace("%5D", "]"))
    if not os.path.isfile(dest):
        urllib.request.urlretrieve(RAW + rel, dest + ".part")
        os.replace(dest + ".part", dest)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--font", default="archivo-black")
    ap.add_argument("--weight", type=float, default=700, help="for variable fonts (100-900)")
    ap.add_argument("--tracking", type=float, default=0.0, help="extra space between letters, in em (negative = tighter)")
    ap.add_argument("--fill", default="#111111")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, (_, what) in FONTS.items():
            print(f"{k:15} {what}")
        return 0
    if not a.text or not a.out:
        ap.error("text and -o are needed")
    try:
        from fontTools.ttLib import TTFont
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.boundsPen import BoundsPen
    except ImportError:
        sys.exit("needs fontTools: pip install fonttools")
    f = TTFont(font_file(a.font))
    if "fvar" in f:
        from fontTools.varLib import instancer
        axes = {ax.axisTag: ax for ax in f["fvar"].axes}
        loc = {"wght": max(axes["wght"].minValue, min(axes["wght"].maxValue, a.weight))} if "wght" in axes else {}
        f = instancer.instantiateVariableFont(f, loc)
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    upm = f["head"].unitsPerEm
    x, paths, boxes = 0.0, [], []
    for i, ch in enumerate(a.text):
        g = cmap.get(ord(ch))
        if g is None:
            sys.exit(f"the font has no '{ch}'")
        pen, bp = SVGPathPen(gs), BoundsPen(gs)
        gs[g].draw(pen)
        gs[g].draw(bp)
        if bp.bounds:
            x0, y0, x1, y1 = bp.bounds
            boxes.append((x + x0, -y1, x + x1, -y0))
        safe = ch if ch.isalnum() else "c"
        paths.append(f'  <path id="L{i}-{safe}" transform="translate({x:.1f} 0) scale(1 -1)" d="{pen.getCommands()}"/>')
        x += gs[g].width + a.tracking * upm
    if not boxes:
        sys.exit("nothing to draw")
    minx, miny = min(b[0] for b in boxes), min(b[1] for b in boxes)
    maxx, maxy = max(b[2] for b in boxes), max(b[3] for b in boxes)
    pad = 0.04 * upm
    vb = f"{minx - pad:.0f} {miny - pad:.0f} {maxx - minx + 2 * pad:.0f} {maxy - miny + 2 * pad:.0f}"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">\n  <title>{a.text}</title>\n'
           f'  <g fill="{a.fill}">\n' + "\n".join("  " + p for p in paths) + "\n  </g>\n</svg>\n")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {a.out} ({len(a.text)} letters, font {a.font})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
