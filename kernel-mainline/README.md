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

**On the printer** (2026-11-09): 49 patches, checkpatch `--strict` clean,
every commit builds with `W=1`, `dt_binding_check` and `dtbs_check` clean.

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
  silent.
- **DMA:** the PDMA runs on the X1830 driver (`dma-jz4780`); dmatest passed
  50 transfers on each of 4 channels at once, no failures. The UART nodes
  list their DMA channels (`8250_ingenic` does not use DMA yet).
- **eMMC** (`tools/emmc-test.c`, every eMMC block device set read-only
  first): HS200, 8 bits, 1.8 V signalling at 25 MHz, the settings the stock
  kernel uses. The GPT and all 7 partitions are found; a full read of the
  stock root partition (100 MiB, 23.6 MB/s) has the same CRC-32 as a copy
  taken on stock, it mounts as squashfs, and the device counts no writes.
  The controller is a DesignWare MSHC 1.40a, so it is a variant of
  `sdhci-of-dwcmshc`; its card clock comes from the CGU, which now switches
  the MSC clock to the crystal for card identification (400 kHz is out of
  MPLL's reach).
- **USB** (`tools/netusb-test.c`): the host port's DWC2 controller and
  PHY bring up the internal hub, the camera and the RTL8821CU Wi-Fi
  module, all at 480 Mb/s. `rtw88_8821cu` loads its firmware (24.11.0)
  and a scan finds the access points around. The OTG controller runs as
  Kiln's 6.6 kernel has it (OTG mode, VBUS detected outside its PHY),
  though none of the display's USB ports reach it. The PHY registers end
  up as under 6.6: USBPCR 0x80000000, USBPCR1 0x30000000, the highest HS
  eye (0x30 = 0x6D) on both, the OTG PHY's VBUS comparator off.
- **Ethernet:** the MAC is a DWMAC GMAC 3.7 (stmmac with the X1000 glue),
  RMII to an IC Plus IP101G at MDIO address 1; link 100 Mb/s full duplex
  in 2 s, TCP at 11.8 MB/s each way (line rate).
- **Floating point:** Kiln's userspace is built for the o32 FP64 ABI;
  without `MIPS_O32_FP64_SUPPORT` the kernel runs it with FR=0 and doubles
  come out wrong (found with the TCP rates). The defconfig enables it.
- **Wi-Fi:** with the secondary cache fix below, rtw88 brings `wlan0` up in
  every boot, survives repeated down/up, and scans, with no rtw88 errors
  (6 boots). Without it about one register read in 500 came back stale.
- Klipper itself has not run on this kernel yet: next is Kiln's userspace
  on it (rtw88 is a module and needs its firmware in the root file system).

Generic fixes this SoC needed, in the series:

- **UserLocal on XBurst II.** The Ingenic CPU feature overrides, written
  for XBurst1 (which has no UserLocal register), forced it off, so every
  thread pointer read from userspace (glibc's `rdhwr $29`, on each access
  to thread-local data) trapped and was emulated. The X2600 has it; the
  kernel now probes Config3 for it. A thread pointer read: 559 ns before,
  2.8 ns after.
- **Physically tagged icache on XBurst II.** The same overrides, and the
  probe, treated every XBurst icache as virtually tagged, which only
  XBurst1's is; the kernel then flushed it on context switches without
  need. 3% off a pipe round trip; 2400 fork + exec runs of two programs
  at the same addresses all ran the right one.
- **-O2.** The defconfig builds the kernel for performance instead of
  size: fork 690 -> 510 us, fork + exec 1946 -> 1534 us, loopback TCP
  306 -> 365 MB/s, for a 12% larger image.

- **Ingenic L2 cache maintenance.** On XBurst a secondary cache operation
  is still writing back when its instruction retires; mainline's DMA cache
  maintenance did not wait, so DMA reads could come back with the buffer's
  old contents, silently. rtw88 showed it: stale register reads, only for
  buffers at the start of a 64-byte L2 line, then wrong values written back
  into the chip. Ingenic's kernels (both XBurst generations, and Kiln's 6.6)
  end their L2 operations with an uncached load (`__fast_iob()`); the fix
  does the same in `sc-mips.c`. 0 stale reads in 30000 with it, about 1 in
  500 without.

- **Ingenic USB PHY supply.** `exit()` disabled the regulator that
  `power_off()` had already disabled; DWC2 calls both on removal and on a
  failed probe (seen as a regulator warning when the PHY clock was off).
- **Ingenic MAC binding.** The DTs use `"snps,dwmac"` as fallback (that
  makes stmmac treat the core as a GMAC) and the common DWMAC properties,
  which the binding rejected; and the CGU binding checked the MAC's PHY
  control register (a syscon) against the MAC binding.

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
- **eMMC above 25 MHz.** HS200 at its full rate needs the sample clock
  tuning; the stock kernel runs at 25 MHz too, so it stays there for now.
- **Wi-Fi under load.** The USB disconnects (-71) seen in some early
  boots with the camera plugged in have not come back since the L2 fix,
  and stale reads turning into wrong register writes would explain them;
  not proven. rtw88 still never checks for short register reads
  (`ret < len`).
- **Ingenic's SoC code not yet compared:** the SDK's X2600 setup
  (`arch/mips/xburst2/soc-x2600/`) and its idle routine (a SYNC before
  WAIT, which mainline's `r4k_wait` lacks).
- **USB PHY from cold.** The tests chainload from the stock kernel, which
  has set the PHY registers already; that our driver sets them from their
  reset values is still to be seen (a direct boot).
- **MAC address.** stmmac takes the address the stock kernel left in the
  MAC; booted directly by the boot loader the MAC gets a random one
  unless the DT or the boot loader provides it.
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
A test kernel must carry its initramfs (`CONFIG_BLK_DEV_INITRD`) and get
`root=/dev/null` on its command line: the chainload passes on stock's
command line, so a kernel without one boots Kiln OS from the eMMC, which
mounts `/data` read-write (the boot flag is safe: `ad5x.noslot`).

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
  Images before that (v0.0.47) want the release alone, one line, and drop
  a two-line record.
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
