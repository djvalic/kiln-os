# AD5X on Ingenic's Linux 6.6 SDK kernel (the shortcut)

Status: **the kernel Kiln OS runs** by default (since 2026-10-20; the
mainline 7.3 kernel in `../kernel-mainline/` is opt-in), started
from RAM at every boot by the stock kernel (`chainload/`,
`S00ad5x-kernel`): Klipper, IFS, screen, touch and the speaker work.
Nothing is written to the boot slots; a start that doesn't reach userspace,
or two start-ups in a row that don't finish, fall back to the stock kernel
until `ad5x-kernel retry` (an update doesn't clear it: `build.sh` pins the
release string).

## Why this kernel

Ingenic's vendor kernel 6.6.18 for XBurst2 (X2000/X2600 SDK v1.0,
2025-02-21) has a driver for every compatible in the stock AD5X device tree,
including the display controller (`ingenic,dpu`), which mainline lacks. The
vendor drivers in `module_drivers/` are GPL. Compared with mainline
(`../kernel-mainline/`) this trades upstream quality for weeks instead of
months of work.

Source: Ingenic's Gitee (`ingenic-dev`) isn't reachable from here; a full
re-upload of the SDK is at
<https://github.com/Llixuma/ingenic-linux-kernel6.6-x2000-v1.0-20250221>
(`kernel/kernel-6.6`). Sparse clone:

```
git clone --filter=blob:none --sparse \
  https://github.com/Llixuma/ingenic-linux-kernel6.6-x2000-v1.0-20250221.git \
  ~/workspace/ingenic-sdk-6.6
git -C ~/workspace/ingenic-sdk-6.6 sparse-checkout set kernel/kernel-6.6
git -C ~/workspace/ingenic-sdk-6.6 checkout "$(sed -n 's/^INGENIC_SDK_COMMIT=//p' buildroot/PINS)"
```

## Build

```
kernel-ingenic66/build.sh        # SDK=, TOOLBIN=, JOBS=, NO_CONFIG=1, SDK_NO_RESET=1
```

`build.sh` stops unless the SDK is at `INGENIC_SDK_COMMIT` (`buildroot/PINS`),
and restores the SDK's tracked files under `kernel/kernel-6.6` to that commit
before it copies our files and applies the patches, so edits made by hand
there are lost (`SDK_NO_RESET=1` skips the check and the restore).

Uses the Buildroot toolchain (`buildroot/output/host/bin`, GCC 14). Output:
`$SDK/out-ad5x/xImage-ad5x-6.6`, a legacy uImage in stock's format
(load = entry = 0x80f00000, uncompressed self-extracting zboot), 5.9 MiB of
the 8 MiB slot. Kernel release `6.6.18-rt23-ad5x` (the SDK tree's
`localversion-rt` plus `CONFIG_LOCALVERSION`); `build.sh` fails a build
whose release string differs (`EXPECT_RELEASE`), because `S00ad5x-kernel`
records and compares it.

## Files

| File | What |
|---|---|
| `ad5x.dts` | AD5X board on the SDK's `x2600.dtsi`; same pins, aliases (ttyS0/2/3/4/5/7, mmc0) as stock; every difference marked `DEVIATION` |
| `ad5x-display.dtsi` | DPU + KX070 panel (LVDS, 800x480) |
| `panel-kx070.c` | Panel driver in the SDK's fbdev panel style; `patches/0001-*` hooks it into Kconfig/Makefile |
| `patches/0002-*` | RS-485 transmit enable for the IFS UART |
| `patches/0003-0007` | Ingenic's fbdev display driver on the X2600: no rotator line padding, the rotator clocked before its registers are written, no plain LPCDR write, no rotator setup without rotation, no RDMA start from a pan before probe started it (so the kernel starts the display from a cold boot) |
| `patches/0008-*` | DMA: the PDMA's pdmam interrupt is optional on the X2600 |
| `patches/0009-*` | Ethernet: setting the MAC address keeps the driver's shadow copy |
| `patches/0010-*` | rtw88 USB: receive starts only once mac80211 is registered (Wi-Fi oops at start) |
| `patches/0011-0016` | rtw88 RTL8821CU fixes from linux-6.6.y stable (6.6.23, 6.6.24, 6.6.44, 6.6.95; the SDK is 6.6.18): firmware upload, connection failure, beacon loss and disconnects, 500 ms USB control timeout, false alarm count (issue #37). Each keeps its upstream header and commit id |
| `patches/0017-*` | rtw88 USB: a failed or short register read returns 0, not an earlier read's value, and short reads are logged (from PR #46 by Hunter Laux; not upstream) |
| `patches/0018-*` | Watchdog: a watchdog the boot loader left running is kept and fed by the kernel until userspace opens `/dev/watchdog`; stopped on halt and poweroff; `set_timeout` works more than once, `start` sets the timeout, the real maximum (about 1431 s) |
| `diag/l2stale/` | Test only, never in an image: counts stale DMA reads through the Wi-Fi adapter's USB register reads (the count behind PR #46's L2 fix), built out of tree against `out-ad5x`; usage in `l2stale.c`. On the printer (2026-11-11): no stale read in 220,000 (11 runs, both modes, two boots), so 6.6 doesn't need PR #46's L2 fix |
| `ad5x.config` | Fragment on `x2600_halley7_linux_defconfig`: own DT, uinput, zram, UVC, rtw88 8821CU, tsc2007, gpio keys/backlight, watchdog |
| `build.sh` | Copies the files into the SDK tree, merges the config, builds, wraps the uImage |

Panel timings come from the numbers in stock's panel data (800x480@60,
HBP 88 HFP 40 HSYNC 48, VBP 35 VFP 13 VSYNC 3, LVDS mode, 108x64 mm); no
Flashforge code is used.

## Open points before the first boot (2026-10, kept for reference)

Written before the kernel first ran; most are settled now (the IFS runs
over RS-485, Wi-Fi, Ethernet, the display and touch work on the printer).

1. **IFS RS-485 (UART4, driver enable on PC3):** `patches/0002-*` adds the
   stock property `ingenic,rs485-tx-enable-gpio` to `ingenic_uart.c` (enable
   while sending, released on LSR.TEMT via a 20 us hrtimer poll). Compiles;
   untested. Check turnaround timing against the IFS on first boot.
2. Wi-Fi power on PB07 assumed active-high.
3. Ethernet: PHY found by scanning; assumes the PHY supplies the 50 MHz RMII
   reference (stock drives PC15 low as a GPIO).
4. Display: LVDS sets EPLL to 434 MHz (check other EPLL users); 31.0 MHz
   pixel clock (59.8 Hz); bpp 32; no reserved framebuffer memory.
5. Touch: mainline tsc2007 gives raw 0-4095 without axis flip (stock flips
   Y); HelixScreen's calibration handles it.
6. Memory: this kernel ignores `rmem=`/`rtos_size=`; the RTOS area
   4M@0xfc00000 is reserved in the DT. Read the real `mem=` from the printer.
   It is started with `mem=252M@0x0` and no `rmem=` (S00ad5x-kernel's
   `kiln_mem`, Kiln's U-Boot and SPL: `docs/memory.md`, "Memory map"); the
   crash log (ramoops) is the last 256 KiB of that, at 0x0fbc0000.
7. Userspace: stock's out-of-tree modules and `cmd_gpio` don't apply; the
   heartbeat (PC11) and backlight move to gpiod / the DT backlight. Wi-Fi
   needs `rtw88/rtw8821c_fw.bin`: built into the kernel, v24.11.0 from
   linux-firmware commit 07338f9d3308 (pinned with its sha256 in `build.sh`).
