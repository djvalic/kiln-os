#!/usr/bin/env python3
"""Install-stick screens: 800x480 baseline JPEGs shown during the install.

usage: make_install_screens.py OUTDIR
       make_install_screens.py --boards OUTDIR
Writes step1.jpg .. step6.jpg, done.jpg, failed.jpg, refused.jpg and
installed.jpg in the boot logo's style (tools/make_logo.py, Noto Sans).
tools/install/ad5x-install.sh shows them with the stock system's own
cmd_jpeg_display while it runs from the install stick. With --boards:
mcu-updating.jpg, mcu-powercycle.jpg and mcu-failed.jpg, which ad5x-mcu
shows while it updates the boards' firmware (in the image,
/usr/share/ad5x/screens).
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_logo import ACCENT, BG_BOTTOM, BG_TOP, H, MUTED, W, WHITE, font  # noqa: E402

RED = (226, 88, 74)
GREEN = (88, 190, 120)
STEPS = [
    "Checking the printer",
    "Saving the stock firmware",
    "Copying the printer's own drivers",
    "Writing Kiln OS",
    "Preparing the first start",
    "Switching to Kiln OS",
]


def base():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(
            round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return img, d


def centered(d, y, text, fnt, fill):
    b = d.textbbox((0, 0), text, font=fnt)
    d.text(((W - (b[2] - b[0])) // 2 - b[0], y - b[1]), text, font=fnt, fill=fill)
    return y + (b[3] - b[1])


def screen(path, title, line1, line2="", accent=ACCENT, progress=None,
           foot="Do not switch the printer off"):
    img, d = base()
    y = centered(d, 70, "Kiln OS", font("Black", 64), WHITE)
    y += 22
    d.rounded_rectangle([(W - 120) // 2, y, (W + 120) // 2, y + 6], radius=3, fill=accent)
    y += 40
    y = centered(d, y, title, font("Bold", 40), accent)
    y += 28
    y = centered(d, y, line1, font("Regular", 28), WHITE)
    if line2:
        y += 14
        y = centered(d, y, line2, font("Regular", 24), MUTED)
    if progress is not None:
        n, total = progress
        x0, x1, py = 150, W - 150, 380
        d.rounded_rectangle([x0, py, x1, py + 14], radius=7, fill=(48, 58, 74))
        d.rounded_rectangle([x0, py, x0 + (x1 - x0) * n // total, py + 14], radius=7, fill=accent)
    if foot:
        centered(d, H - 50, foot, font("Regular", 20), MUTED)
    img.save(path, "JPEG", quality=90, optimize=True, progressive=False, subsampling=0)


def boards(out):
    os.makedirs(out, exist_ok=True)
    screen(os.path.join(out, "mcu-updating.jpg"), "Updating the boards",
           "Writing Klipper firmware to the boards.",
           "This takes about a minute, once.")
    screen(os.path.join(out, "mcu-powercycle.jpg"), "Switch off and on",
           "To finish updating the toolhead board,",
           "switch the printer off, wait 5 seconds, switch it on.",
           foot="")
    screen(os.path.join(out, "mcu-failed.jpg"), "Board update failed",
           "Klipper can't start. Switch off and on to retry.",
           "Details: ad5x-mcu status, /data/ad5x/mcu/log", accent=RED, foot="")
    print("wrote board screens to", out)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--boards":
        return boards(sys.argv[2])
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for i, text in enumerate(STEPS, 1):
        screen(os.path.join(out, "step%d.jpg" % i), "Installing",
               "Step %d of %d: %s" % (i, len(STEPS), text),
               "This takes a few minutes" if i in (2, 4) else "",
               progress=(i, len(STEPS)))
    screen(os.path.join(out, "done.jpg"), "Done, restarting",
           "Remove the USB stick now.",
           "Kiln OS starts next. The first start takes a few minutes.",
           accent=GREEN,
           foot="Nothing after 3 minutes? Power-cycle the printer.")
    screen(os.path.join(out, "failed.jpg"), "Installation failed",
           "Nothing was switched: the printer keeps its firmware.",
           "See ad5x-install.log on the stick. Remove the stick, power-cycle.",
           accent=RED, foot="")
    screen(os.path.join(out, "refused.jpg"), "Not installed",
           "This printer can't be installed this way.",
           "See ad5x-install.log on the stick. Remove the stick, power-cycle.",
           accent=RED, foot="")
    screen(os.path.join(out, "installed.jpg"), "Already installed",
           "This printer already runs Kiln OS.",
           "Use an update instead. Remove the stick, power-cycle.",
           foot="")
    print("wrote screens to", out)


if __name__ == "__main__":
    main()
