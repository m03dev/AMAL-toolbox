#!/usr/bin/env python3
"""A logo picture -> clean SVG (vtracer, MIT: github.com/visioncortex/vtracer). LOKI's addition (AGPL-3.0).

A picture model draws good logo ideas but only as pixels; this traces one into vector shapes so it can be tested at
16 px, recoloured and exported like any SVG mark.

  python vectorize.py renders/logo.png -o brand/syn/traced.svg            # flat colours
  python vectorize.py renders/logo.png -o brand/syn/traced.svg --mono     # one colour (black shapes), smallest file
Needs vtracer (pip install vtracer).
"""
import argparse
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--mono", action="store_true", help="one colour: good for marks, smallest paths")
    ap.add_argument("--speckle", type=int, default=12, help="drop specks smaller than this many pixels")
    a = ap.parse_args()
    try:
        import vtracer
    except ImportError:
        sys.exit("needs vtracer: pip install vtracer")
    vtracer.convert_image_to_svg_py(a.picture, a.out, colormode="binary" if a.mono else "color", hierarchical="cutout",
                                    mode="spline", filter_speckle=a.speckle, color_precision=5, layer_difference=24,
                                    corner_threshold=60, length_threshold=5.0, splice_threshold=45, path_precision=3)
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
