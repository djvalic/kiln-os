# AD5X on mainline Linux (Ingenic X2600 port)

A port of the Flashforge AD5X (Ingenic X2600, XBurst2) to mainline Linux,
on the latest stable release (now 7.3.3), written as a patch series to
mainline's standards. It is not submitted upstream; the standards are there
so the code is sound, not to get it merged. Kiln OS keeps running the 6.6
SDK kernel (`../kernel-ingenic66/`) until this one covers the hardware.

## Rules

Each patch must be acceptable to a mainline reviewer:

- One logical change per patch; the tree builds after every patch
  (`check.sh` builds each commit). Bindings come before the code that uses
  them, in their own patch.
- `scripts/checkpatch.pl --strict` clean; `W=1` builds without warnings;
  sparse (`C=1`) clean.
- Device tree bindings in YAML, `dt_binding_check` and `dtbs_check` clean.
  Bindings describe the hardware, never Linux; standard properties over
  vendor ones (for example `rts-gpios` and the serial core's RS-485
  properties, not `ingenic,rs485-tx-enable-gpio`).
- Use the kernel's frameworks: clocks through the clock framework, pins
  through pinctrl, the display through DRM (fbdev takes no new drivers),
  RS-485 through the serial core. No register writes at fixed addresses,
  no `#if 0`, no board-specific hacks in SoC drivers.
- Extend existing Ingenic drivers when the hardware matches (pinctrl,
  8250_ingenic, dwmac-ingenic, cgu.c); a new driver only for new hardware.
- The Ingenic SDK (`~/workspace/ingenic-sdk-6.6`) is documentation for the
  hardware, not code to copy. Credit it where a driver is derived from it.
- Commit messages say why, in the imperative; author Hunter Laux
  <hunterlaux@gmail.com>.

## Order

1. Boot to a serial console on one core: SoC and board bindings, interrupt
   controller, timer, clocks, pinctrl, UART, `x2600.dtsi`, `ad5x.dts`,
   `ad5x_defconfig`.
2. eMMC (SDHCI), read-only first.
3. I2C (touch), USB OTG and PHY (Wi-Fi), Ethernet, DMA, watchdog/restart.
4. RS-485 for the IFS (`8250_ingenic` + `serial8250_em485`).
5. PWM (speaker).
6. Display: a DRM driver for the DPU, the LVDS encoder, the KX070 panel
   in `panel-simple`.
7. SMP (second XBurst2 core).

## Status

**On the printer** (2026-11-08): 24 patches, checkpatch `--strict` clean,
every commit builds with `W=1`, `dt_binding_check` clean on every binding
the series touches, `dtbs_check` clean but for the UART `dmas` below.

- **Boot to a serial console:** the kernel reaches `Waiting for root
  device`: XBurst II CPU (PRId 0x00132000), early console, 490 MB RAM with
  highmem, the OST as clocksource, the five GPIO ports, `ttyS0`.
- **Clocks:** the CGU driver's rates match the boot loader's PLL settings:
  APLL 1152 MHz (CPU 1152, L2 576), MPLL 1800 MHz (AHB0 360, AHB2 300,
  PCLK 150, DDR 900), EPLL 434 MHz (LCD 31 MHz, through OD0 = 4).
- **The three Klipper MCUs:** the test initramfs (`tools/ifs-rs485-test.c`)
  fetched each one's whole data dictionary, every frame CRC-checked, with
  the ports as the kernel sets them up at boot (as Klipper finds them):
  the motion controller (`ttyS2`) and the toolhead board (`ttyS5`) at
  230400 through the fractional divider (DLL 8, UMR 13: 230769 baud),
  v0.13.0-803-g4cd711119; the IFS (`ttyS4`) over RS-485 with the driver
  enable on PC3, v0.13.0-806-g131fffdc4. With RS-485 off the IFS stays
  silent. Klipper itself has not run on this kernel yet: that needs the
  root file system, so eMMC (step 2).

Generic fixes this SoC needed, in the series:

- **zboot cache maintenance.** The decompressor jumped to the kernel without
  writing back the L1 data cache (an old FIXME), so the kernel ran stale
  code: the vendor kernel's, which had been at the same addresses.
- **Config4.IE = 3** (one TLBINVF invalidates the whole MMU) was treated as
  no TLB invalidate support; the XBurst2 reports it and has an FTLB, and the
  fallback path hung in `r4k_tlb_uniquify()`.
- **RS-485 end of transmission.** The 8250 core releases RTS one frame
  after LSR.THRE; on Ingenic UARTs THRE means "FIFO half empty", so the
  driver enable dropped after the first byte (seen with a pin trace). Drivers
  can now report their TX FIFO level (`tx_fifo_count()`); the X2600 counts it
  in its TCR register.

Open points:

- **sparse** has not run on the series (it could not be installed here).
- **UART DMA.** The UART nodes have no `dmas`, the one `dtbs_check`
  warning left (mainline's X1830 has the same), until the X2600 PDMA is
  supported.
- **From Ingenic's SDK, not documentation:** the PLL VCO range (672-2400
  MHz, the range of Ingenic's PLL table; the boot loader's settings are
  inside it), which pins have pull resistors (all allowed), and the X2600
  cores using the X2000 CPU compatible (the same PRId).
- **Sign-off.** The patches carry no `Signed-off-by`; only you can certify
  them (`git rebase --signoff v7.3.3` in the development tree).

## Build

```
kernel-mainline/build.sh                     # tarball + patches/ -> uImage
KSRC=~/workspace/linux-7.3.3 kernel-mainline/build.sh   # development tree
```

Development happens in a git tree on tag `v7.3.3` (`~/workspace/linux-7.3.3`,
branch `ad5x`); the series is exported with
`git format-patch v7.3.3..ad5x -o kernel-mainline/patches/` (empty the
directory first).

## Test on the printer

Nothing below writes the flash; a hung test kernel costs a power cycle.

- **Serial console:** the debug header (3.3 V, 115200 8N1) is wired to PE9
  and PE10. The stock kernel routes UART0 to PE11/PE12 only, so before a
  test switch PE9/PE10 to UART0 (function 1) on stock:
  `b=0x13605000; for o in 0x18 0x28 0x38 0x44; do devmem $((b+o)) 32 0x600; done`
  (clear INT, MSK and PAT1, set PAT0). Our device tree muxes all four pins.
- **From the stock kernel:** record our 6.6 release as failed and reboot
  cleanly; the printer stays on stock. Since issue #42 the record needs a
  second line, the reason (a one-line record is taken as an old one and
  retried once):
  `printf '%s\nkernel test: stay on stock\n' "$(cat /usr/lib/ad5x/kernel66/release)" > /data/ad5x/kernel/failed`
  Then, from `/data/ad5x/chainload/` (`chainload.ko`, `chainload.sh`):
  `chainload.sh stage IMAGE` (loads it, prints what it staged) and
  `chainload.sh go` (stops services and jumps). Undo with `ad5x-kernel retry`
  and a reboot.
- **Wait for the end of start-up before jumping or rebooting:** the boot
  flag (`head -c 11 /dev/mmcblk0p5`) reads `ota:kernel2` again once
  `S99ad5x-booted` ran. Before that it points at recovery, and the next
  power cycle boots recovery (leave it with `ad5x-boot-main`).
- Once the image has the one-shot test boot, `ad5x-kernel test IMAGE` plus a
  reboot replaces the first step.

## Tools

`check.sh` needs `sparse`, and `dt-validate`/`yamllint` (pip: `dtschema`,
`yamllint`) on `PATH`.
