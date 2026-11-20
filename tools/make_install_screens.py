#!/usr/bin/env python3
"""Install-stick screens: 800x480 baseline JPEGs shown during the install.

usage: make_install_screens.py OUTDIR
       make_install_screens.py --boards OUTDIR
Writes step1.jpg .. step6.jpg, done.jpg, powercycle.jpg, failed.jpg,
refused.jpg and installed.jpg in the brand's look (tools/make_logo.py: the mark, the Nord
colours, Noto Sans; no Fira, so the builder can make them).
tools/install/ad5x-install.sh shows them with the stock system's own
cmd_jpeg_display while it runs from the install stick: done.jpg when the
install is finished and the printer restarts, powercycle.jpg if it is
still running about 20 s later (the restart didn't happen). English only:
stock's start-up hook has no language setting to go by. With --boards:
mcu-updating.jpg, mcu-powercycle.jpg and mcu-failed.jpg, which ad5x-mcu
shows while it updates the boards' firmware (in the image,
/usr/share/ad5x/screens).

Something moves on every long screen: a ring turns around the badge.
stepN.jpg is the ring's first position, stepN-1.jpg ..
stepN-7.jpg the next seven; the installer shows them in turn about once a
second (cmd_jpeg_display can only show whole JPEGs). The same for
mcu-updating(-1..7).jpg, which ad5x-mcu cycles on the stock kernel. On
Kiln's kernels ad5x-fb-progress draws over mcu-updating.jpg instead, from
progress/ (--boards): layout.json, ring.png (16 ring positions, cut from
the decoded JPEGs, so they match the screen under them to the bit), a
label-NAME.png per step ("Writing the toolhead board") and two glyph
sheets for the percentage and the elapsed time (the image's Pillow has no
FreeType: the helper only pastes pre-made pieces).

Each screen: the mark at the top, a badge that says the state by its shape
as well as its colour (the step number; a tick for done; a cross for
failed; ! for refused; i for already installed; an arrow for updating; the
power symbol for switch off and on), the title, one or two lines, a
segmented step bar on the step screens, and a footer.
"""
import io
import json
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_logo import (DANGER, GROUND, H, MARK, SS, SUCCESS, TAGLINE,  # noqa: E402
                       TEXT, TRACK, W, WARNING, font, mark_polygons)

STEPS = [
    "Checking the printer",
    "Saving the stock firmware",
    "Copying the printer's own drivers",
    "Writing Kiln OS",
    "Preparing the first start",
    "Switching to Kiln OS",
]
# How long each step usually takes (the printer's install log, 2026-11-18/19:
# step 2 is about 5 minutes with the eMMC copy to the stick, seconds without)
HINTS = [
    "Usually under a minute.",
    "Up to 6 minutes with the eMMC copy to the stick.",
    "Usually a few seconds.",
    "Usually 1 to 2 minutes.",
    "Usually under a minute.",
    "A few seconds, then the printer restarts.",
]
MARK_PX = 64                      # the mark's 120-unit box, px
BADGE_Y, BADGE_R = 150, 46        # badge centre and radius, px
# The turning ring around the badge: radius, width (px), the arc's length
# (degrees). Its box, 8-pixel aligned (whole JPEG blocks: the pixels
# around it decode the same in every frame), holds the badge and the ring
# (rows 89.5 to 210.5, and the 3 px the scaling down smears around it),
# so from row 80 (the mark's last rows, the same in every frame) to 216,
# above the title (222).
RING_R, RING_W, RING_ARC = 58, 5, 100
RING_BOX = (336, 80, 128, 136)    # x, y, w, h
JPEG_FRAMES = 8                   # the cmd_jpeg_display loops: one a second
FB_FRAMES = 16                    # ad5x-fb-progress: 5 a second
# badge kind: (disc colour, symbol colour, title colour). Titles are 40 px
# bold (large text, 3:1): DANGER on the ground is 3.05:1, the cross on it
# 3.5:1; lines below them are TEXT or TAGLINE.
KINDS = {
    "step": (MARK, GROUND, TEXT),
    "busy": (MARK, GROUND, TEXT),
    "info": (MARK, GROUND, TEXT),
    "done": (SUCCESS, GROUND, SUCCESS),
    "warn": (WARNING, GROUND, WARNING),
    "power": (WARNING, GROUND, WARNING),
    "fail": (DANGER, TEXT, DANGER),
}


class Canvas:
    """800x480 drawn at SS times the size, for smooth edges, then scaled."""

    def __init__(self):
        self.img = Image.new("RGB", (W * SS, H * SS), GROUND)
        self.d = ImageDraw.Draw(self.img)

    def centered(self, y, text, name, size, fill):
        """Text centred, its top at y (px); returns its bottom."""
        f = font(name, size * SS)
        b = self.d.textbbox((0, 0), text, font=f)
        self.d.text(((W * SS - (b[2] - b[0])) / 2 - b[0], y * SS - b[1]), text,
                    font=f, fill=fill)
        return y + (b[3] - b[1]) / SS

    def mark(self):
        k = MARK_PX / 120 * SS
        for p in mark_polygons((W * SS - 120 * k) / 2, 22 * SS, k):
            self.d.polygon(p, fill=MARK)

    def stroke(self, pts, width, fill):
        """A line through pts (px, relative to the badge centre), round ends."""
        cx, cy, w = W / 2, BADGE_Y, width * SS
        q = [((cx + x) * SS, (cy + y) * SS) for x, y in pts]
        self.d.line(q, fill=fill, width=round(w), joint="curve")
        for x, y in (q[0], q[-1]):
            self.d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=fill)

    def dot(self, x, y, r, fill):
        cx, cy = (W / 2 + x) * SS, (BADGE_Y + y) * SS
        self.d.ellipse([cx - r * SS, cy - r * SS, cx + r * SS, cy + r * SS], fill=fill)

    def badge(self, kind, number=None):
        disc, sym, _ = KINDS[kind]
        self.dot(0, 0, BADGE_R, disc)
        if kind == "step":
            f = font("Black", 54 * SS)
            self.d.text((W / 2 * SS, BADGE_Y * SS), str(number), font=f, fill=sym,
                        anchor="mm")
        elif kind == "done":
            self.stroke([(-19, 1), (-6, 14), (19, -12)], 9, sym)
        elif kind == "fail":
            self.stroke([(-15, -15), (15, 15)], 9, sym)
            self.stroke([(15, -15), (-15, 15)], 9, sym)
        elif kind == "warn":
            self.stroke([(0, -20), (0, 5)], 9, sym)
            self.dot(0, 19, 5.5, sym)
        elif kind == "info":
            self.dot(0, -19, 5.5, sym)
            self.stroke([(0, -4), (0, 20)], 9, sym)
        elif kind == "busy":       # an arrow down onto a line: writing
            self.stroke([(0, -22), (0, 8)], 8, sym)
            self.stroke([(-13, -4), (0, 9), (13, -4)], 8, sym)
            self.stroke([(-17, 21), (17, 21)], 8, sym)
        elif kind == "power":
            w = 8 * SS
            r = 20 * SS
            cx, cy = W / 2 * SS, (BADGE_Y + 3) * SS
            self.d.arc([cx - r, cy - r, cx + r, cy + r], -55, 235, fill=sym,
                       width=round(w))
            self.stroke([(0, -26), (0, -2)], 8, sym)

    def ring(self, pos, frames):
        """The ring at position pos of frames: a track and a turning arc
        with round ends, starting at 12 o'clock."""
        cx, cy = W / 2 * SS, BADGE_Y * SS
        r, w = RING_R * SS, RING_W * SS
        # PIL draws outlines and arcs inwards from the box: centred on r
        box = [cx - r - w / 2, cy - r - w / 2, cx + r + w / 2, cy + r + w / 2]
        self.d.ellipse(box, outline=TRACK, width=round(w))
        a0 = -90 + 360 * pos / frames
        a1 = a0 + RING_ARC
        self.d.arc(box, a0, a1, fill=MARK, width=round(w))
        for a in (a0, a1):
            x = cx + r * math.cos(math.radians(a))
            y = cy + r * math.sin(math.radians(a))
            self.d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=MARK)

    def steps(self, n, total):
        """Segmented step bar: steps up to n filled."""
        gap, h = 10, 12
        x0, x1, y = 170, W - 170, 386
        seg = (x1 - x0 - gap * (total - 1)) / total
        for i in range(total):
            a = x0 + i * (seg + gap)
            self.d.rounded_rectangle([a * SS, y * SS, (a + seg) * SS, (y + h) * SS],
                                     radius=h / 2 * SS, fill=MARK if i < n else TRACK)

    def final(self):
        return self.img.resize((W, H), Image.LANCZOS)

    def save(self, path):
        save_jpeg(self.final(), path)


def save_jpeg(img, path):
    """Baseline, full-resolution colour: what stock's cmd_jpeg_display reads."""
    img.save(path, "JPEG", quality=90, optimize=True, progressive=False, subsampling=0)


def decoded(img):
    """img as the panel gets it: through the same JPEG encoding, decoded."""
    b = io.BytesIO()
    save_jpeg(img, b)
    b.seek(0)
    return Image.open(b).convert("RGB")


def screen(path, kind, title, line1, line2="", number=None, progress=None,
           foot="Do not switch the printer off", big=0, line3="", ring=0):
    """big: the first `big` lines (1 or 2) in 30 px bold, for what the
    user has to do (instructions read from across the room). ring: also
    write path's frames with the ring turning (path-1.jpg ..), this many
    in all; path itself is the first."""
    c = Canvas()
    c.mark()
    c.badge(kind, number)
    y = c.centered(222, title, "Bold", 40, KINDS[kind][2])
    if big >= 1:
        y = c.centered(y + 24, line1, "Bold", 30, TEXT)
    else:
        y = c.centered(y + 26, line1, "Regular", 28, TEXT)
    if line2:
        if big >= 2:
            y = c.centered(y + 14, line2, "Bold", 30, TEXT)
        else:
            y = c.centered(y + 14, line2, "Regular", 24, TAGLINE)
    if line3:
        c.centered(y + 16, line3, "Regular", 24, TAGLINE)
    if progress is not None:
        c.steps(*progress)
    if foot:
        c.centered(H - 50, foot, "Regular", 20, TAGLINE)
    if not ring:
        c.save(path)
        return []
    return ring_frames(c, path, ring)


def ring_frames(c, path, frames):
    """Canvas c with the ring at each of frames positions: path (the first),
    path-1.jpg .. Returns the frames, decoded."""
    base = c.img
    out = []
    for i in range(frames):
        c.img = base.copy()
        c.d = ImageDraw.Draw(c.img)
        c.ring(i, frames)
        img = c.final()
        save_jpeg(img, path if i == 0 else "%s-%d.jpg" % (os.path.splitext(path)[0], i))
        out.append(img)
    c.img, c.d = base, ImageDraw.Draw(base)
    return out


# The board update screen's parts that ad5x-fb-progress redraws, 8-pixel
# aligned rows across the whole width (whole JPEG blocks, plain ground
# around the text): the line under the title (label, 28 px), the bar
# (12 px high), the elapsed time (24 px). Baselines in px.
LABEL_BAND, LABEL_BASE = (272, 48), 306
BAR_BAND, BAR_Y, BAR_X, BAR_H = (336, 16), 338, (170, 630), 12
TIME_BAND, TIME_BASE = (352, 40), 382
LABELS = {
    "check": "Checking the boards",
    "mainboard": "Writing the mainboard",
    "eboard": "Writing the toolhead board",
    "ifs": "Writing the filament unit (IFS)",
    "start": "Starting the toolhead board",
}
UPDATING_LINE = "Writing Klipper firmware to the boards."
UPDATING_FOOT = "Usually 1 to 2 minutes, once. Do not switch the printer off."


def text_strip(text, size, colour, band, base, ground):
    """text at 1x (as the helper puts it together), its advance wide and
    the band high, baseline at base (panel rows), on ground."""
    f = font("Regular", size)
    w = max(1, round(f.getlength(text)))
    im = Image.new("RGB", (w, band[1]), ground)
    ImageDraw.Draw(im).text((0, base - band[0]), text, font=f, fill=colour, anchor="ls")
    return im


def glyph_sheet(chars, size, colour, band, base, ground):
    """One strip of glyphs, each its rounded advance wide; {char: [x, w]}."""
    parts = [(ch, text_strip(ch, size, colour, band, base, ground)) for ch in chars]
    sheet = Image.new("RGB", (sum(p.width for _, p in parts), band[1]), ground)
    index, x = {}, 0
    for ch, p in parts:
        sheet.paste(p, (x, 0))
        index[ch] = [x, p.width]
        x += p.width
    return sheet, index


def updating(out):
    """mcu-updating.jpg and its ring frames, and progress/ for
    ad5x-fb-progress."""
    c = Canvas()
    c.mark()
    c.badge("busy")
    c.centered(222, "Updating the boards", "Bold", 40, TEXT)
    f = font("Regular", 28 * SS)
    c.d.text((W / 2 * SS, LABEL_BASE * SS), UPDATING_LINE, font=f, fill=TEXT, anchor="ms")
    c.centered(H - 50, UPDATING_FOOT, "Regular", 20, TAGLINE)
    path = os.path.join(out, "mcu-updating.jpg")
    ring_frames(c, path, JPEG_FRAMES)

    p = os.path.join(out, "progress")
    os.makedirs(p, exist_ok=True)
    # The ground as the JPEG decodes it (plain blocks), so the redrawn
    # bands meet the screen around them without a seam, at 16 bpp too
    first = Image.open(path).convert("RGB")
    ground = first.getpixel((8, LABEL_BAND[0] + 4))
    x, y, w, h = RING_BOX
    base = c.img
    sheet = Image.new("RGB", (w * FB_FRAMES, h), ground)
    for i in range(FB_FRAMES):
        c.img = base.copy()
        c.d = ImageDraw.Draw(c.img)
        c.ring(i, FB_FRAMES)
        sheet.paste(decoded(c.final()).crop((x, y, x + w, y + h)), (w * i, 0))
    sheet.save(os.path.join(p, "ring.png"), optimize=True)
    for name, text in LABELS.items():
        text_strip(text, 28, TEXT, LABEL_BAND, LABEL_BASE, ground).save(
            os.path.join(p, "label-%s.png" % name), optimize=True)
    lsheet, lindex = glyph_sheet("0123456789%: ", 28, TEXT, LABEL_BAND, LABEL_BASE, ground)
    lsheet.save(os.path.join(p, "glyphs-label.png"), optimize=True)
    tsheet, tindex = glyph_sheet("0123456789:", 24, TAGLINE, TIME_BAND, TIME_BASE, ground)
    tsheet.save(os.path.join(p, "glyphs-time.png"), optimize=True)
    layout = {
        "comment": "ad5x-fb-progress's parts of mcu-updating.jpg (make_install_screens.py --boards)",
        "ground": list(ground), "track": list(TRACK), "fill": list(MARK),
        "ring": {"x": x, "y": y, "w": w, "h": h, "frames": FB_FRAMES, "file": "ring.png"},
        "label": {"y": LABEL_BAND[0], "h": LABEL_BAND[1],
                  "files": {n: "label-%s.png" % n for n in LABELS},
                  "glyphs": "glyphs-label.png", "index": lindex},
        "bar": {"y": BAR_BAND[0], "h": BAR_BAND[1], "top": BAR_Y, "x0": BAR_X[0],
                "x1": BAR_X[1], "thick": BAR_H},
        "time": {"y": TIME_BAND[0], "h": TIME_BAND[1], "glyphs": "glyphs-time.png",
                 "index": tindex},
    }
    with open(os.path.join(p, "layout.json"), "w") as fh:
        json.dump(layout, fh, indent=1, sort_keys=True)
        fh.write("\n")


def boards(out):
    os.makedirs(out, exist_ok=True)
    updating(out)
    screen(os.path.join(out, "mcu-powercycle.jpg"), "power", "Switch off and on",
           "To finish updating the toolhead board,",
           "switch the printer off, wait 5 seconds, switch it on.",
           foot="")
    screen(os.path.join(out, "mcu-failed.jpg"), "fail", "Board update failed",
           "Klipper can't start. Switch off and on to retry.",
           "Details: ad5x-mcu status, /data/ad5x/mcu/log", foot="")
    print("wrote board screens to", out)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--boards":
        return boards(sys.argv[2])
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for i, text in enumerate(STEPS, 1):
        screen(os.path.join(out, "step%d.jpg" % i), "step", "Installing",
               "Step %d of %d: %s" % (i, len(STEPS), text), HINTS[i - 1],
               number=i, progress=(i, len(STEPS)), ring=JPEG_FRAMES)
    screen(os.path.join(out, "done.jpg"), "done", "Done, restarting",
           "Take out the USB stick now.",
           "The printer restarts by itself into Kiln OS.",
           line3="The first start takes a few minutes.", big=1,
           foot="Still on this screen after a minute? Switch the printer off and on.")
    screen(os.path.join(out, "powercycle.jpg"), "power", "Switch off and on",
           "1. Take out the USB stick.",
           "2. Switch the printer off, then on.",
           line3="This is safe now: Kiln OS is installed.", big=2, foot="")
    screen(os.path.join(out, "failed.jpg"), "fail", "Installation failed",
           "Nothing was switched: the printer keeps its firmware.",
           "See ad5x-install.log on the stick. Remove the stick, power-cycle.",
           foot="")
    screen(os.path.join(out, "refused.jpg"), "warn", "Not installed",
           "This printer can't be installed this way.",
           "See ad5x-install.log on the stick. Remove the stick, power-cycle.",
           foot="")
    screen(os.path.join(out, "installed.jpg"), "info", "Already installed",
           "This printer already runs Kiln OS.",
           "Use an update instead. Remove the stick, power-cycle.",
           foot="")
    print("wrote screens to", out)


if __name__ == "__main__":
    main()
