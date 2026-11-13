#!/usr/bin/env python3
"""Boot logo for Kiln OS: 800x480 baseline JPEG (the panel size).

usage: make_logo.py [--recovery] [-o logo.jpg] [--rgb565 preview.png]
                    [--wordmark-font TTF]
The brand lockup (docs/brand/logo/kiln-lockup-single-dark.svg) on the
brand ground: the mark (ring with four gaps and the K, drawn from the SVG's
own geometry, no font), "KILN OS" in Fira Sans Compressed ExtraBold (the
lockup's font, SIL OFL; Arch: ttf-fira-sans) and the tagline in Noto Sans
(SIL OFL, as HelixScreen uses). Flat colours, no gradient: the 7.3 kernel's
framebuffer is 16 bpp (RGB565) and gradients band there.
Shown at boot by S07ad5x-board until HelixScreen takes the screen.
--recovery: the recovery OS's logo
(board/ad5x-recovery/rootfs-overlay/usr/share/ad5x/recovery-logo.jpg):
the same mark and scale, "RECOVERY" in the warning colour in place of
"KILN OS" (a word, not only a colour) and its own tagline.
--rgb565: also write a PNG of what a 16 bpp panel shows (ad5x-fb-show's
packing). The fonts are needed only to make the JPEGs, not on the printer.
"""
import os
import math
import argparse
from PIL import Image, ImageDraw, ImageFont

W, H = 800, 480
# Noto Sans: Arch's path, then Debian's (fonts-noto-core, the builder)
FONTS = next((d for d in ("/usr/share/fonts/noto", "/usr/share/fonts/truetype/noto")
              if os.path.isfile(d + "/NotoSans-Regular.ttf")), "/usr/share/fonts/noto")
# Brand colours (docs/brand/README.md; HelixScreen's Nord theme tokens in
# brackets), contrast on GROUND. Also used by make_install_screens.py and,
# as C_* in recovery-ui/src/ui.c, by the recovery touch UI.
GROUND = (0x2E, 0x34, 0x40)       # [screen_bg]
TEXT = (0xEC, 0xEF, 0xF4)         # [text] wordmark, 10.8:1
TAGLINE = (0xD8, 0xDE, 0xE9)      # [text_muted] tagline, as the lockup, 9.2:1
MARK = (0x88, 0xC0, 0xD0)         # [primary] the mark, 6.2:1
WARNING = (0xEB, 0xCB, 0x8B)      # [warning] recovery's wordmark, 8.0:1
SUCCESS = (0xA3, 0xBE, 0x8C)      # [success] 6.1:1
DANGER = (0xBF, 0x61, 0x6A)       # [danger] 3.05:1: fills, large text only
TRACK = (0x4C, 0x56, 0x6A)        # [elevated_bg] empty progress, decoration

FIRA = ("/usr/share/fonts/TTF/FiraSansCompressed-ExtraBold.ttf",
        "/usr/share/fonts/OTF/FiraSansCompressed-ExtraBold.otf",
        "/usr/share/fonts/truetype/fira/FiraSansCompressed-ExtraBold.ttf",
        os.path.expanduser("~/.local/share/fonts/FiraSansCompressed-ExtraBold.ttf"))
SS = 4                            # supersampling for smooth edges

# The lockup, in its own 480x140 units: mark at translate(8 10) scale(0.9)
# of the 120x120 mark; ring centre (60,60) r 46, stroke 8, four gaps whose
# ends sit 2.4 off the axes; the K as two polygons.
MARK_X, MARK_Y, MARK_S = 8, 10, 0.9
RING_C, RING_R, RING_W, GAP = 60, 46, 8, 2.4
K_STEM = [(53.40229885057471, 88.0), (37.47126436781609, 88.0),
          (37.47126436781609, 32.0), (53.40229885057471, 32.0)]
K_ARMS = [(69.41379310344827, 56.94252873563218), (82.5287356321839, 88.0),
          (65.39080459770115, 88.0), (53.80459770114942, 58.14942528735632),
          (65.95402298850574, 32.0), (81.32183908045977, 32.0)]
WORD_X, WORD_Y, WORD_SIZE = 150, 84, 64      # baseline
TAG_X, TAG_Y, TAG_SIZE = 154, 116, 22        # baseline
SCALE = 1.6                       # lockup units -> panel pixels


def font(name, size):
    return ImageFont.truetype("%s/NotoSans-%s.ttf" % (FONTS, name), size)


def wordmark_font(path, size):
    for p in ([path] if path else FIRA):
        if p and os.path.isfile(p):
            return ImageFont.truetype(p, size)
    raise SystemExit("make_logo.py: Fira Sans Compressed ExtraBold (SIL OFL) not "
                     "found; install ttf-fira-sans (Arch) or pass --wordmark-font")


def mark_polygons(x0=MARK_X, y0=MARK_Y, k=MARK_S):
    """The mark as polygons: four ring segments with butt ends (radial, as
    SVG strokes), then the K. The 120x120 mark at (x0, y0), k units per
    mark unit; by default in lockup units."""
    def to_lockup(x, y):
        return x0 + k * x, y0 + k * y
    polys = []
    half = math.degrees(math.asin(GAP / RING_R))
    r0, r1 = RING_R - RING_W / 2, RING_R + RING_W / 2
    for q in range(4):            # PIL/SVG angles: 0 = 3 o'clock, clockwise
        a0, a1 = -90 + 90 * q + half, -90 + 90 * (q + 1) - half
        steps = [a0 + (a1 - a0) * i / 96 for i in range(97)]
        outer = [(RING_C + r1 * math.cos(math.radians(a)),
                  RING_C + r1 * math.sin(math.radians(a))) for a in steps]
        inner = [(RING_C + r0 * math.cos(math.radians(a)),
                  RING_C + r0 * math.sin(math.radians(a))) for a in reversed(steps)]
        polys.append([to_lockup(*p) for p in outer + inner])
    polys.append([to_lockup(*p) for p in K_STEM])
    polys.append([to_lockup(*p) for p in K_ARMS])
    return polys


def rgb565_view(img):
    """What a 16 bpp panel shows: ad5x-fb-show keeps the top 5/6/5 bits."""
    r, g, b = img.split()
    return Image.merge("RGB", (r.point(lambda v: (v & 0xf8) | (v >> 5)),
                               g.point(lambda v: (v & 0xfc) | (v >> 6)),
                               b.point(lambda v: (v & 0xf8) | (v >> 5))))


def render(recovery, wordmark_path=None):
    s = SCALE * SS
    word_f = wordmark_font(wordmark_path, round(WORD_SIZE * s))
    tag_f = font("Regular", round(TAG_SIZE * s))
    tagline = ("update  ·  backup  ·  rescue" if recovery
               else "for the Flashforge AD5X")
    # "KILN RECOVERY" would not fit the panel at the lockup's scale
    words = [("RECOVERY", WARNING)] if recovery else [("KILN OS", TEXT)]
    polys = mark_polygons()

    # The content's box in lockup units (mark, wordmark, tagline), to centre it
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    wb = word_f.getbbox("".join(t for t, _ in words), anchor="ls")
    tb = tag_f.getbbox(tagline, anchor="ls")
    left, top = min(xs), min(ys + [WORD_Y + wb[1] / s, TAG_Y + tb[1] / s])
    right = max(xs + [WORD_X + wb[2] / s, TAG_X + tb[2] / s])
    bottom = max(ys + [WORD_Y + wb[3] / s, TAG_Y + tb[3] / s])
    ox = (W * SS - (right - left) * s) / 2 - left * s
    oy = (H * SS - (bottom - top) * s) / 2 - top * s

    def at(x, y):
        return ox + x * s, oy + y * s

    img = Image.new("RGB", (W * SS, H * SS), GROUND)
    d = ImageDraw.Draw(img)
    for p in polys:
        d.polygon([at(x, y) for x, y in p], fill=MARK)
    x, y = at(WORD_X, WORD_Y)
    for text, colour in words:
        d.text((x, y), text, font=word_f, fill=colour, anchor="ls")
        x += d.textlength(text, font=word_f)
    d.text(at(TAG_X, TAG_Y), tagline, font=tag_f, fill=TAGLINE, anchor="ls")
    return img.resize((W, H), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", default="logo.jpg")
    ap.add_argument("--recovery", action="store_true",
                    help="recovery OS variant")
    ap.add_argument("--rgb565", metavar="PNG",
                    help="also write what a 16 bpp (RGB565) panel shows")
    ap.add_argument("--wordmark-font", metavar="TTF",
                    help="Fira Sans Compressed ExtraBold, if not in a system path")
    args = ap.parse_args()
    img = render(args.recovery, args.wordmark_font)
    # baseline, full-resolution colour: what stock's cmd_jpeg_display reads
    img.save(args.output, "JPEG", quality=90, optimize=True, progressive=False,
             subsampling=0)
    print("wrote", args.output)
    if args.rgb565:
        rgb565_view(Image.open(args.output).convert("RGB")).save(args.rgb565)
        print("wrote", args.rgb565)


def raw_frames(jpeg):
    """make_logo.py --raw JPEG: JPEG as the framebuffer's first frame, for
    S02ad5x-logo (busybox only, no Python that early): decoded and packed by
    ad5x-fb-show's own code, gzipped next to it as NAME-16.raw.gz (RGB565
    little-endian, stride 1600, the 7.3 kernel) and NAME-32.raw.gz
    (XRGB8888 as BGRX bytes, stride 3200, 6.6). tools/test_fb_show.sh
    fails when they no longer match the JPEG."""
    import sys
    import gzip
    import importlib.machinery
    import importlib.util
    sys.dont_write_bytecode = True    # no __pycache__ next to ad5x-fb-show
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                        "buildroot/package/ad5x-system/bin/ad5x-fb-show")
    loader = importlib.machinery.SourceFileLoader("ad5x_fb_show", path)
    fb_show = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(fb_show)
    im = Image.open(jpeg).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H))
    for bpp in (16, 32):
        out = "%s-%d.raw.gz" % (os.path.splitext(jpeg)[0], bpp)
        # mtime 0, no name: the same JPEG gives the same file
        with open(out, "wb") as f:
            f.write(gzip.compress(fb_show.frame(im, bpp, W * bpp // 8), 9, mtime=0))
        print("wrote", out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--raw":
        raw_frames(sys.argv[2])
    else:
        main()
