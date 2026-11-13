#!/usr/bin/env python3
"""Install-stick screens: 800x480 baseline JPEGs shown during the install.

usage: make_install_screens.py OUTDIR
       make_install_screens.py --boards OUTDIR
Writes step1.jpg .. step6.jpg, done.jpg, failed.jpg, refused.jpg and
installed.jpg in the brand's look (tools/make_logo.py: the mark, the Nord
colours, Noto Sans; no Fira, so the builder can make them).
tools/install/ad5x-install.sh shows them with the stock system's own
cmd_jpeg_display while it runs from the install stick. With --boards:
mcu-updating.jpg, mcu-powercycle.jpg and mcu-failed.jpg, which ad5x-mcu
shows while it updates the boards' firmware (in the image,
/usr/share/ad5x/screens).

Each screen: the mark at the top, a badge that says the state by its shape
as well as its colour (the step number; a tick for done; a cross for
failed; ! for refused; i for already installed; an arrow for updating; the
power symbol for switch off and on), the title, one or two lines, a
segmented step bar on the step screens, and a footer.
"""
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
MARK_PX = 64                      # the mark's 120-unit box, px
BADGE_Y, BADGE_R = 150, 46        # badge centre and radius, px
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

    def steps(self, n, total):
        """Segmented step bar: steps up to n filled."""
        gap, h = 10, 12
        x0, x1, y = 170, W - 170, 386
        seg = (x1 - x0 - gap * (total - 1)) / total
        for i in range(total):
            a = x0 + i * (seg + gap)
            self.d.rounded_rectangle([a * SS, y * SS, (a + seg) * SS, (y + h) * SS],
                                     radius=h / 2 * SS, fill=MARK if i < n else TRACK)

    def save(self, path):
        self.img.resize((W, H), Image.LANCZOS).save(
            path, "JPEG", quality=90, optimize=True, progressive=False, subsampling=0)


def screen(path, kind, title, line1, line2="", number=None, progress=None,
           foot="Do not switch the printer off"):
    c = Canvas()
    c.mark()
    c.badge(kind, number)
    y = c.centered(222, title, "Bold", 40, KINDS[kind][2])
    y = c.centered(y + 26, line1, "Regular", 28, TEXT)
    if line2:
        c.centered(y + 14, line2, "Regular", 24, TAGLINE)
    if progress is not None:
        c.steps(*progress)
    if foot:
        c.centered(H - 50, foot, "Regular", 20, TAGLINE)
    c.save(path)


def boards(out):
    os.makedirs(out, exist_ok=True)
    screen(os.path.join(out, "mcu-updating.jpg"), "busy", "Updating the boards",
           "Writing Klipper firmware to the boards.",
           "This takes about a minute, once.")
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
               "Step %d of %d: %s" % (i, len(STEPS), text),
               "This takes a few minutes" if i in (2, 4) else "",
               number=i, progress=(i, len(STEPS)))
    screen(os.path.join(out, "done.jpg"), "done", "Done, restarting",
           "Remove the USB stick now.",
           "Kiln OS starts next. The first start takes a few minutes.",
           foot="Nothing after 3 minutes? Power-cycle the printer.")
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
