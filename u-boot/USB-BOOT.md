# Starting Kiln's SPL over USB (bench, phase 4)

The X2600's boot ROM has a USB mode: it waits on the OTG port (J28) and
runs whatever stage 1 a host sends into its SRAM window. Kiln's SPL can be
started that way with **nothing written to the eMMC**: it sets up clocks
and DDR3, reads the boot flag and boots the slot's kernel from the eMMC
(read-only), and the printer comes up as usual. That is the phase-4 test
of the v1.0 boot plan: ~20 starts from the boot ROM, to see the clock,
DDR and eMMC code work from a reset chip before anything goes onto the
eMMC.

Bench only. Nothing here is in an image, the update or install path, or
the touch screen and Fluidd.

## What it needs

- **J28**, the white 5-pin JST PH 2.0 mm connector labelled `USB` on the
  mainboard (`docs/boot-slots.md`, "J28"): `GND GND P N 5V`, P = D+, N =
  D-. It is the X2600's OTG controller (`13500000`); the outside USB-C
  port is a host port on another controller and can't be used. Newer
  boards ship without the connector fitted. Wire D+, D- and GND to the
  laptop. Measure `5V` first: if the printer powers it, leave the
  laptop's 5 V unconnected (never two supplies on one line).
- **The console** on the DEBUG header: UART0, PE9 TX / PE10 RX, 115200
  8N1, 1.8 V levels per `kernel-ingenic66/usb-boot.md` (measure TX idle
  before connecting a 3.3 V adapter). Log it to a file (`tio -L`,
  `picocom --logfile`).
- **The laptop**: Python 3 with pyusb and libusb-1.0 (a venv:
  `python3 -m venv ~/.venv/usb && ~/.venv/usb/bin/pip install pyusb`), and
  access to the device (udev: `SUBSYSTEM=="usb", ATTR{idVendor}=="a108",
  ATTR{idProduct}=="eaef", MODE="0660", TAG+="uaccess"`).
- **The image**: `spl-usb.bin` from `u-boot/build.sh` (`$WORK/out/dist`).
  It is `spl-mmc.img` with an 8-byte tag (`KILNUSB1`) in the header's
  zero room at offset 0x7F0; the SPL's code is the same bytes. It never
  goes onto the eMMC (there every start would count as a fresh one, the
  tries gone): `ad5x_spl_image.py first-mib`/`write-plan` and
  `check_first_mib.py` refuse it.

## Into the boot ROM's USB mode

**Soft entry** (found by alexshev86, djvalic/kiln-os#68; no opening of
the printer besides J28). On the running printer, as root:

```
devmem 0x100000cc 32 0x42575302   # CPM_SLPC = "SWB" << 8 | 2
reboot
```

or the bench helper, which checks first (root, Kiln's main OS, an X2600,
Moonraker says not printing or paused), says what it will do, and does it
only with `--yes`:

```
P=192.168.x.y    # the printer's address
scp -O tools/bench/ad5x-usbboot-mode root@$P:/tmp/
ssh root@$P /tmp/ad5x-usbboot-mode          # checks, explains
ssh root@$P /tmp/ad5x-usbboot-mode --yes    # writes, reboots
```

The value is Ingenic's `softburn` request (SDK `common/cmd_softburn.c`).
After the reboot the laptop sees `a108:eaef` and the printer is off the
network. BusyBox `devmem` is in Kiln OS's image (Buildroot's default
`CONFIG_DEVMEM=y`); alexshev86's test ran on Kiln OS with 6.6. This start
follows a watchdog reset (Linux's reboot), not a power-on: the CPM, the
PLLs and the DDR controller are reset, but the DDR chips keep power and
CPSPR, SLPC and the RTC domain keep their values.

**K4** (alexshev86, #68): closing the pad pair K4 changes the boot-select
straps `boot_sel[2:0]` (R370-R374 next to K4) from `101` (eMMC) to `111`
(USB), so the ROM starts in USB mode at every power-on, even with a good
SPL on the eMMC. With K4 closed, each power cycle is a true cold start.
(The older note that K4 made no difference came from a unit whose SPL was
gone, where the ROM went to USB anyway.)

## What the tool sends

```
u-boot/tools/ad5x_usbboot.py info
u-boot/tools/ad5x_usbboot.py run-spl spl-usb.bin [--no-flush]
u-boot/tools/ad5x_usbboot.py --dry-run run-spl spl-usb.bin   # prints only
```

Vendor requests on EP0 (recipient device), data on bulk OUT 0x01:

| Request | Type | wValue / wIndex |
|---|---|---|
| 0x00 GET_CPU_INFO | IN 0xC0, wLength 8 | 0 / 0 |
| 0x01 SET_DATA_ADDR | OUT 0x40 | address bits 31:16 / 15:0 (4-aligned) |
| 0x02 SET_DATA_LEN | OUT 0x40 | length, split the same way |
| 0x03 FLUSH_CACHE | OUT 0x40 | 0 / 0 |
| 0x04 PROG_START1 | OUT 0x40 | entry point, split |
| 0x05 PROG_START2 | OUT 0x40 | (stage 2 in DDR; unused) |

`run-spl`: GET_CPU_INFO; SET_DATA_ADDR 0x80001000; SET_DATA_LEN (13,824
bytes for the current build); the image on bulk OUT; FLUSH_CACHE;
PROG_START1 0x80001800. Timeouts 1 s (control) and 10 s (bulk). Exit 0
started, 1 error (nothing started), 3 PROG_START1 got no status stage
(everything went out; the ROM may have jumped before answering: watch the
console).

Sources: Ingenic's GPL boot ROM protocol code in the SDK's U-Boot
(device side `common/spl/usb_boot.c` with `include/usb_boot/usb_boot.h`
and `include/cloner/cloner.h`; host side `common/usb_load.c`); Rockbox's
`utils/jztool` (directions, GET_CPU_INFO as IN verified on an X1600;
endpoints) and ballaswag/ingenic-usbboot (X2000: stage 1 with a 2 KiB
parameter area at 0xb2401000, started at 0xb2401800); the X2600 addresses
from Ingenic Cloner's `firmwares/x2600/config.cfg` (`ginfo=0x80001000`,
`spl=0x80001800`, `d2i_len=0x7000`) and the SDK's `burner_x2600.h`. The
tool's docstring cites them line by line.

Why the whole image, header included: Cloner sends its parameter records
(BDIF/DDR/BOOT, for its own stage 1) and its code behind them as one block
to 0x80001000; Kiln sends its 2 KiB eMMC header there instead, so SRAM
holds what an eMMC start loads, plus the tag. Kiln's SPL has its DDR
values built in and reads only the tag from the header. 13,824 bytes is
within the SPL window (24 KiB, 48 blocks, to 0x80007000) and Cloner's
0x7000. FLUSH_CACHE before PROG_START1 follows Ingenic's `usb_load.c`
(the window is cached KSEG0); `--no-flush` is there if the ROM disagrees.

## What the SPL does when started over USB

The same as from the eMMC (patches 0013-0025), checked in the code for
anything it would have left to the ROM's eMMC path:

- start.S stops the ROM's watchdog, sets CP0 Status/Config, its own stack
  at 0x80007000; it never returns to the ROM;
- patch 0025: sees the tag (or CPM_SLPC = 0x42575302) and clears both, so
  the next reset boots from the eMMC; treats the start as fresh (CPSPR is
  printed, not counted); runs a DDR test after the DDR setup;
- it arms its own watchdog (10 s per phase) and opens every clock gate it
  uses itself: OST, UART0, TCU/RTC (watchdog), EFUSE, DDR, and MSC0
  (patch 0024: before the controller's reset; the ROM opens that one only
  on an eMMC start);
- pins: MSC0 on PD0-PD5 and UART0 on PE9-PE12, set by the SPL;
- clocks from EXCLK up: CPU to EXCLK first, then APLL/MPLL/EPLL, CPCCR, the
  CGU parents, the DDR divider and the MSC0 divider; none of the ROM's
  `cpm_desc` values (applied only on an eMMC start) is relied on;
- eMMC: CMD0/1/2/3/7, CMD6 for 4-bit (EXT_CSD BUS_WIDTH, volatile), CMD13,
  CMD17/18/12. No write command is sent; the boot flag and the slot are
  only read.

## The cold-start test (~20 starts)

Each start:

1. Into USB mode: K4 closed and a power cycle (a smart plug, on our
   bench one in Home Assistant), or the soft entry above.
2. `lsusb -d a108:eaef`; `ad5x_usbboot.py info` (log the CPU info).
3. `ad5x_usbboot.py run-spl spl-usb.bin`.
4. On the console, in this order:

```
U-Boot SPL 2026.10 (...)
SPL: boot ROM
SPL: started over USB (soft entry, SLPC cleared); scratch pad 0x... not counted: a fresh start
SPL: CPCCR ..., APLL ..., MPLL ..., EPLL ...
SPL: DDR3 W634GU6QG-11, 900 MHz
SPL: DDR 512 MiB up
SPL: DDR test: data lines, address lines 2-27, 16 MiB at 0x1000000: good (... ms)
SPL: no U-Boot at 0xA400: the slot, as the stock SPL
SPL: slot b
SPL: <uImage name>, <size> bytes at 0x80f00000
SPL: starting the kernel
```

   then the kernel and the main OS as usual (Klipper ready in Fluidd).
   With K4 the first line after the banner has no "(soft entry ...)".

Log per start: date and time, how it entered USB mode (K4 + power cycle,
or soft), the CPU info, the whole console log, the DDR test time, and
whether the main OS came up. Once: `cat /proc/cmdline` over SSH.

Pass: 20 of 20 reach "SPL: starting the kernel" and the main OS, the DDR
test good every time, and no "busy", "doesn't lock", "attempt" or
"failed" line. Do most of them as true cold starts (K4 + power cycle);
soft entries alone test only the start after a reset.

A failure resets through the watchdog within about 10 s. After a soft
entry the SPL had cleared CPM_SLPC, so the stock SPL on the eMMC boots
the printer normally (its banner: `U-Boot SPL 2013.07-00190`); with K4
the ROM waits on USB again. Write down the SPL's last line and the
scratch pad value the next USB start prints. Nothing goes onto the eMMC
because of a failure.

## Getting back

- **Power cycle** (off for a few seconds; the smart plug): CPM_SLPC
  doesn't survive power-off, the stock SPL boots from the eMMC.
- After a start of Kiln's SPL over USB the kernel's reboot also goes back
  to the eMMC (the SPL cleared CPM_SLPC).
- **K4**: open it again, then power-cycle.
- None of this writes the eMMC: it still holds the stock SPL and both
  slots as before.

## Only hardware can tell

- GET_CPU_INFO's answer on the X2600 (Cloner reads 5 bytes) and the
  endpoints (`info` prints the descriptors).
- That the ROM takes 13,824 bytes at 0x80001000 (Cloner's own stage 1 is
  9,432 bytes; `d2i_len` is written commented out in its config) and
  starts 0x80001800 with PROG_START1.
- Whether FLUSH_CACHE before PROG_START1 is right, and whether the ROM
  answers PROG_START1 before it jumps (exit 3 if not).
- That the SRAM window and caches are as on an eMMC start once the ROM
  jumps, so the SPL's clock and DDR code runs as it would there.
- Whether the ROM clears CPM_SLPC itself, and whether CPSPR keeps its
  value over the reset (the SPL prints it).
- The MSC0 gate (0024) is the one dependency on the ROM's eMMC path the
  review found; the rest is set by the SPL in the code, not yet seen
  running.
- The DDR test covers the low 256 MiB (KSEG1); the upper 256 MiB at
  0x30000000 is tested only by Linux using it.
