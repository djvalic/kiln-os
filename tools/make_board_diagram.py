#!/usr/bin/env python3
"""Block diagram of the AD5X main board: what connects to what.

usage: make_board_diagram.py [-o docs/img/ad5x-board-diagram.png]

Drawn from docs/pinout-ad5x.md (alexshev86, PR #92), the X2600 data sheet
(release 2.1), kernel-ingenic66/ad5x.dts, klipper/ad5x.cfg and live reads on
an X2600E printer. Layout is fixed coordinates; edit them when adding a part.
Needs Pillow and Noto Sans (falls back to DejaVu Sans).
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 2720, 1680
SCALE = 1  # raise for a sharper image

FONT_DIR = "/usr/share/fonts/truetype/noto"


def font(size, bold=False):
    name = "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"
    for d in (FONT_DIR, "/usr/share/fonts/truetype/dejavu"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size * SCALE)
        p = os.path.join(d, "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
        if os.path.exists(p):
            return ImageFont.truetype(p, size * SCALE)
    return ImageFont.load_default()


F_TITLE = font(30, True)
F_HEAD = font(19, True)
F_TEXT = font(15)
F_SMALL = font(13)

# Wire colours by signal kind.
C = {
    "usb": "#1f63c6",
    "uart": "#1e8a43",
    "disp": "#7a3db0",
    "gpio": "#c86a12",
    "mem": "#a12a4d",
    "unk": "#8a8a8a",
}
INK = "#1d1d1f"
MUTED = "#5b5b63"
V18 = "#c0262d"

img = Image.new("RGB", (W * SCALE, H * SCALE), "white")
d = ImageDraw.Draw(img)


def s(v):
    return v * SCALE


def dashed_line(p0, p1, fill, width=3, dash=12, gap=8):
    (x0, y0), (x1, y1) = p0, p1
    length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    if length == 0:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    t = 0.0
    while t < length:
        e = min(t + dash, length)
        d.line([(s(x0 + ux * t), s(y0 + uy * t)), (s(x0 + ux * e), s(y0 + uy * e))],
               fill=fill, width=s(width))
        t = e + gap


def box(x0, y0, x1, y1, title=None, lines=(), fill="#f6f6f8", edge=INK,
        dashed=False, title_font=F_HEAD, width=2, line_colors=None):
    if dashed:
        d.rectangle([s(x0), s(y0), s(x1), s(y1)], fill=fill)
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                     ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            dashed_line(a, b, edge, width=width, dash=8, gap=6)
    else:
        d.rounded_rectangle([s(x0), s(y0), s(x1), s(y1)], radius=s(6),
                            fill=fill, outline=edge, width=s(width))
    y = y0 + 8
    if title:
        d.text((s(x0 + 10), s(y)), title, font=title_font, fill=INK)
        y += title_font.size / SCALE + 6
    for i, ln in enumerate(lines):
        col = (line_colors or {}).get(i, MUTED)
        d.text((s(x0 + 10), s(y)), ln, font=F_TEXT, fill=col)
        y += 20


def label(x, y, text, color, anchor="lm", f=F_SMALL):
    bb = d.textbbox((s(x), s(y)), text, font=f, anchor=anchor)
    d.rectangle([bb[0] - s(3), bb[1] - s(2), bb[2] + s(3), bb[3] + s(2)], fill="white")
    d.text((s(x), s(y)), text, font=f, fill=color, anchor=anchor)


def wire(pts, kind, dashed=False, width=3, arrow_end=False):
    col = C[kind]
    for a, b in zip(pts, pts[1:]):
        if dashed:
            dashed_line(a, b, col, width=width)
        else:
            d.line([(s(a[0]), s(a[1])), (s(b[0]), s(b[1]))], fill=col, width=s(width))
    for p in (pts[0], pts[-1]):
        r = 4
        d.ellipse([s(p[0] - r), s(p[1] - r), s(p[0] + r), s(p[1] + r)], fill=col)


# ---------------------------------------------------------------- title
d.text((s(40), s(18)), "AD5X main board: how the parts connect", font=F_TITLE, fill=INK)
d.text((s(40), s(58)),
       "FFP0303_Main_Board_V3.0.1 (second generation).  X2600 pin names (PAx-PEx) and N32G455 pin names are "
       "separate namespaces: PB13 on one chip has nothing to do with PB13 on the other.",
       font=F_TEXT, fill=MUTED)

# ---------------------------------------------------------------- display board
DX0, DX1 = 40, 470
box(DX0, 115, DX1, 1010, "Display board", fill="#fbf8ff", edge=C["disp"])
disp_items = [
    # y, title, sub, kind, dashed
    (200, "USB socket", "hub port 1", "usb", False),
    (280, "Camera socket (back)", "hub port 2", "usb", False),
    (360, "Side USB-C", "unproven: shares the camera pair?", "unk", True),
    (480, "LCD panel 800x480", "driven as LVDS", "disp", False),
    (580, "TSC2007 touch", "I2C address 0x48, 400 kHz", "disp", False),
    (680, "Backlight", "on/off from PC14", "disp", False),
    (760, "K1 power button", "AD5M Pro part, no link on AD5X", "unk", True),
    (840, "Pin 13 load", "PC10: purpose unknown", "unk", True),
    (920, "Pin 19 load", "unknown", "unk", True),
]
for y, t, sub, kind, dsh in disp_items:
    box(70, y - 30, 440, y + 30, None, (), fill="white", edge=C[kind], dashed=dsh, width=2)
    d.text((s(82), s(y - 25)), t, font=F_HEAD, fill=INK)
    d.text((s(82), s(y + 2)), sub, font=F_SMALL, fill=MUTED)

# ---------------------------------------------------------------- J5
J5X0, J5X1 = 545, 615
box(J5X0, 140, J5X1, 1010, None, fill="#eeeeee", edge=INK)
d.text((s(580), s(1016)), "J5 LCD, 40-pin FPC", font=F_HEAD, fill=INK, anchor="mt")

# ---------------------------------------------------------------- X2600
XX0, XY0, XX1, XY1 = 760, 140, 1380, 1290
box(XX0, XY0, XX1, XY1, "X2600 SoC (runs Linux)", (
    "X2600E 256 MB or X2600H 512 MB (eFuse)",
    "MIPS main core + RISC-V core",
), fill="#f3f7ff", edge=INK, width=3)
volt = [
    ("Ports B, C, D: 3.3 V", INK),
    ("  except PD0-PD5 (eMMC): 1.8 V", V18),
    ("Ports A, E: 1.8 V", V18),
    ("PE5-PE20 on the 1.8 V ADC supply", V18),
]
for i, (t, col) in enumerate(volt):
    d.text((s(900), s(980 + i * 22)), t, font=F_TEXT, fill=col)

# Display signals: X2600 left edge -> J5 -> display item.
def disp_wire(y, kind, x2600_text, pins_text, reach_soc=True, dashed=False):
    x_start = XX0 if reach_soc else J5X0 + 35
    wire([(x_start, y), (440, y)], kind, dashed=dashed)
    label(500, y - 14, pins_text, C[kind], anchor="mm")
    if reach_soc:
        d.text((s(XX0 + 10), s(y)), x2600_text, font=F_TEXT, fill=C[kind], anchor="lm")


disp_wire(480, "disp", "DSI/LVDS: 4 lanes + clock", "pins 21-34")
disp_wire(570, "disp", "I2C0: PC0 SCK, PC1 SDA", "pins 15/16")
disp_wire(600, "disp", "PC7: touch interrupt", "pin 18")
disp_wire(680, "gpio", "PC14: backlight (PWM15)", "pin 12")
disp_wire(760, "unk", "", "pin 5", reach_soc=False, dashed=True)
disp_wire(840, "unk", "PC10: PWM11 / CAN1_RX", "pin 13", dashed=True)
disp_wire(920, "unk", "", "pin 19", reach_soc=False, dashed=True)

# ---------------------------------------------------------------- USB hub, Wi-Fi, J6, J28
HX0, HY0, HX1, HY1 = 1500, 140, 1800, 330
box(HX0, HY0, HX1, HY1, "GL852G USB hub", ("4 downstream ports",), fill="#f2f7ff", edge=C["usb"])
wire([(XX1, 200), (HX0, 200)], "usb")
d.text((s(XX1 - 10), s(200)), "USB1 (host)", font=F_TEXT, fill=C["usb"], anchor="rm")
label(1440, 186, "13540000", C["usb"], anchor="mm")

# ports 1 and 2 go up and over to J5 / the display.
wire([(1560, HY0), (1560, 100), (580, 100), (580, 200), (440, 200)], "usb")
wire([(1620, HY0), (1620, 115), (595, 115), (595, 280), (440, 280)], "usb")
label(1555, 120, "p1", C["usb"], anchor="rm")
label(1615, 130, "p2", C["usb"], anchor="rm")
label(492, 186, "pins 6/7", C["usb"], anchor="mm")
label(492, 266, "pins 2/3", C["usb"], anchor="mm")
dashed_line((440, 300), (480, 300), C["unk"], width=2)
dashed_line((480, 300), (480, 340), C["unk"], width=2)
dashed_line((480, 340), (440, 340), C["unk"], width=2)

box(1900, 150, 2200, 210, "J6 USB", ("not fitted",), fill="white", edge=C["usb"], dashed=True)
wire([(HX1, 180), (1900, 180)], "usb")
label(1850, 166, "p3", C["usb"], anchor="mm")
box(1900, 235, 2250, 305, "Wi-Fi RTL8821CU", ("module U4",), fill="white", edge=C["usb"])
wire([(HX1, 265), (1900, 265)], "usb")
label(1850, 251, "p4", C["usb"], anchor="mm")
wire([(XX1, 360), (2300, 360), (2300, 270), (2250, 270)], "gpio")
d.text((s(XX1 - 10), s(360)), "PB7: Wi-Fi power", font=F_TEXT, fill=C["gpio"], anchor="rm")

box(1900, 400, 2380, 470, "J28 USB0 (OTG)", ("fitted on gen 1 boards, not on gen 2",),
    fill="white", edge=C["usb"])
wire([(XX1, 430), (1900, 430)], "usb")
d.text((s(XX1 - 10), s(430)), "USB0 (OTG)", font=F_TEXT, fill=C["usb"], anchor="rm")
label(1640, 416, "13500000: boot-ROM USB recovery, host", C["usb"], anchor="mm")

# ---------------------------------------------------------------- N32G455 and its loads
NX0, NY0, NX1, NY1 = 1760, 560, 2110, 1160
box(NX0, NY0, NX1, NY1, "N32G455 MCU", (
    "Klipper [mcu] (main board)",
    "its own pin names",
), fill="#f3fbf5", edge=C["uart"], width=3)
wire([(XX1, 610), (NX0, 610)], "uart")
d.text((s(XX1 - 10), s(610)), "UART2 PD12/PD13 (ttyS2)", font=F_TEXT, fill=C["uart"], anchor="rm")
wire([(XX1, 650), (NX0, 650)], "gpio")
d.text((s(XX1 - 10), s(650)), "PB17/PB18: N32 NRST/BOOT0", font=F_TEXT, fill=C["gpio"], anchor="rm")

n32_loads = [
    (590, "TMC2209 X", "EN PB1, DIR PB12, STEP PB13, UART PB11", False),
    (650, "TMC2209 Y", "EN PA2, DIR PA7, STEP PC4, UART PB0", False),
    (710, "TMC2209 Z", "EN PB14, DIR PC8, STEP PC7, UART PB15", False),
    (770, "Bed", "heater PB9; thermistor PA0 on J35", False),
    (830, "Probe input", "PB3 on J23 (RES); weighing board trigger?", False),
    (890, "Endstops", "Y PC12 on J12; Z PD2 on J14", False),
    (950, "PCB fan / chamber light", "PA5 on J20; PA11 on J21", False),
    (1015, "Fan/servo headers, off in stock", "J16 PB7 fitted; J17 PC15, J18 PA4, J26 PC11 not", True),
    (1085, "J22 SWD", "PA13 SWDIO, PA14 SWCLK", False),
]
for y, t, sub, dsh in n32_loads:
    box(2200, y - 27, 2680, y + 27, None, (), fill="white",
        edge=C["unk"] if dsh else C["uart"], dashed=dsh)
    d.text((s(2212), s(y - 24)), t, font=F_HEAD, fill=INK)
    d.text((s(2212), s(y + 3)), sub, font=F_SMALL, fill=MUTED)
    wire([(NX1, y), (2200, y)], "unk" if dsh else "gpio", dashed=dsh)

# ---------------------------------------------------------------- UART peripherals column
PX0, PX1 = 1430, 1690
uart_items = [
    (760, "IFS (filament changer)", ["RS-485 transceiver", "DE on PC3"],
     "UART4 PB24/PB25 (ttyS4)", False),
    (870, "Toolhead board (eboard)", ["extruder, heater, fans,", "LIS2DW, X endstop"],
     "UART5 PB26/PB27 (ttyS5)", False),
    (980, "Weighing board", ["strain gauges; tared over ttyS7", "trigger to N32 PB3? (unproven)"],
     "UART7 PC4/PC5 (ttyS7)", False),
    (1080, "J24 TVOC", ["not fitted; opened by nothing"],
     "UART3 PB22/PB23 (ttyS3)", True),
    (1180, "J19 RISC-V JTAG", ["not fitted; R80-R83 0 ohm"],
     "PB0-PB3 (TMS TDI TDO TCK)", True),
]
for y, t, sub, soc_text, dsh in uart_items:
    kind = "unk" if dsh else "uart"
    box(PX0, y - 42, PX1, y + 42, None, (), fill="white", edge=C[kind], dashed=dsh)
    d.text((s(PX0 + 12), s(y - 38)), t, font=F_HEAD, fill=INK)
    for i, ln in enumerate(sub):
        d.text((s(PX0 + 12), s(y - 12 + i * 18)), ln, font=F_SMALL, fill=MUTED)
    wire([(XX1, y), (PX0, y)], kind, dashed=dsh)
    d.text((s(XX1 - 10), s(y)), soc_text, font=F_TEXT, fill=C[kind], anchor="rm")
# Weighing board trigger -> N32 PB3: likely, not proven.
# Weighing board trigger -> probe input (N32 PB3): likely, not proven.
# Runs below the N32 box to reach the probe input on the right.
wire([(PX1, 995), (1730, 995), (1730, 1190), (2160, 1190), (2160, 845), (2200, 845)],
     "unk", dashed=True)
label(1945, 1190, "weighing board trigger? (unproven)", C["unk"], anchor="mm")
# PC3 driver enable
d.text((s(XX1 - 10), s(785)), "PC3: RS-485 driver enable", font=F_SMALL, fill=C["gpio"], anchor="rm")

# ---------------------------------------------------------------- bottom row under the X2600
bottom = [
    (770, 990, "eMMC", ["MSC0, 8-bit, HS200", "PD0-PD5 + PE1-PE4", "1.8 V signalling"], "mem", 1),
    (1010, 1200, "Ethernet PHY + J4", ["RMII PC16-PC24", "PC15 held low"], "mem", None),
    (1210, 1420, "J8 debug", ["UART0 PE9 TX, PE10 RX", "level shifter:", "3.3 V on header"], "uart", 0),
]
for x0, x1, t, lines, kind, red in bottom:
    lc = {red: V18} if red is not None else None
    box(x0, 1380, x1, 1490, t, lines, fill="white", edge=C[kind], line_colors=lc)
    xm = (x0 + x1) // 2
    wire([(xm, XY1), (xm, 1380)], kind)
label(1300, 1335, "1.8 V side", V18, anchor="mm")

# Other X2600 pins
box(40, 1080, 700, 1290, "Other X2600 pins", (
    "PB11: power key",
    "PC11: heartbeat (toggled 1 Hz by sys_start.sh)",
    "PC12: speaker (PWM13)",
    "PC6: console strap read by the SPL",
    "PB12: to U20 on the AD5M Pro; U20 not fitted on AD5X",
    "Test points TP12-TP58: spare SoC pins (see doc)",
), fill="white", edge=C["gpio"])
wire([(XX0, 1180), (700, 1180)], "gpio")

# ---------------------------------------------------------------- legend
LX, LY = 40, 1530
d.text((s(LX), s(LY)), "Key", font=F_HEAD, fill=INK)
keys = [("usb", "USB"), ("uart", "UART / serial"), ("disp", "display and touch"),
        ("gpio", "GPIO / PWM"), ("mem", "storage / network"), ("unk", "unknown or not fitted")]
x = LX + 60
for k, t in keys:
    wire([(x, LY + 14), (x + 50, LY + 14)], k)
    d.text((s(x + 60), s(LY + 4)), t, font=F_TEXT, fill=INK)
    x += 80 + int(d.textlength(t, font=F_TEXT) / SCALE) + 20
dashed_line((x, LY + 14), (x + 50, LY + 14), INK, width=2)
d.text((s(x + 60), s(LY + 4)), "dashed: not fitted, unused or unproven", font=F_TEXT, fill=INK)
d.text((s(LX), s(LY + 40)), "Red text: 1.8 V signals. Don't connect 3.3 V devices to them directly.",
       font=F_TEXT, fill=V18)
d.text((s(LX), s(LY + 66)),
       "Sources: docs/pinout-ad5x.md (alexshev86), X2600 data sheet rel. 2.1, "
       "kernel-ingenic66/ad5x.dts, klipper/ad5x.cfg, live reads on an X2600E printer. "
       "Traced on one board only: hub ports 1-3, U20, PB2/PB3 routing, N32 connector numbers.",
       font=F_SMALL, fill=MUTED)
d.text((s(LX), s(LY + 88)),
       "Generated by tools/make_board_diagram.py. Provided as is; check against your own board "
       "before connecting anything.", font=F_SMALL, fill=MUTED)

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("-o", "--output", default=os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs", "img", "ad5x-board-diagram.png"))
out = os.path.normpath(ap.parse_args().output)
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
img.save(out, optimize=True)
print(out)
