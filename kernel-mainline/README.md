# AD5X on mainline Linux (Ingenic X2600 port)

A port of the Flashforge AD5X (Ingenic X2600, XBurst2) to mainline Linux,
on the latest stable release (now 7.3.3), written as a patch series to
mainline's standards. It is not submitted upstream; the standards are there
so the code is sound, not to get it merged. Kiln OS ships it as an opt-in
second kernel beside the 6.6 SDK kernel (`../kernel-ingenic66/`), which
stays the default: `ad5x-kernel mainline on` on the printer, and a failed
7.3 start falls back to 6.6 in the same boot (`S00ad5x-kernel`). The
buildroot package `ad5x-kernel-mainline` runs `build.sh`. Kiln adds two
patches on top of the series: 0075 (a ramoops region for pstore, as 6.6
has) and 0076 (the eMMC at 50 MHz, as 6.6, until a longer soak at 150).

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
3. I2C (touch), USB OTG and PHY (Wi-Fi), Ethernet, DMA, watchdog/restart:
   done.
4. RS-485 for the IFS (`8250_ingenic` + `serial8250_em485`): done.
5. PWM (speaker): done.
6. Display: a DRM driver for the DPU, the LVDS PHY, the KX070 panel on
   `panel-lvds`: done.
7. SMP (second XBurst2 core): done.

## Status

**On the printer** (2026-11-09): 74 patches, checkpatch `--strict` clean,
every commit builds with `W=1`, `dt_binding_check` and `dtbs_check` clean,
sparse (v0.6.5-rc1, `C=2` on every C file the series touches) clean apart
from code it doesn't change (`asm/mips-cm.h`, three 32-bit constants in
`phy-rockchip-inno-dsidphy.c` as in v7.3.3).
Kiln OS runs on it (`build.sh` adds `kiln.config`: Wi-Fi with its firmware
built in, webcams, zram) and it has printed: a 2 h 10 min PETG print
through Klipper, Happy Hare and the IFS, every layer, no kernel warnings.

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
  first): HS200, 8 bits, 1.8 V signalling, now at 150 MHz (stock: 25,
  Kiln's 6.6: 50), the fastest the MSC clock reaches within HS200's 200
  MHz (the CGU divides by multiples of 4; MPLL / 12), with the standard
  tuning. Reads of the 100 MiB partition below: 23.6 MB/s at 25 MHz, 46.3
  at 50, 60.6 at 96, 68.9 at 150, every time with the stock copy's CRC-32;
  under Kiln, five more passes matched and a 256 MiB file written to
  `/data` read back intact. The GPT and all 7 partitions are found; a full read of the
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
- **SMP:** both cores run. The core control unit (CCU) starts the second
  one and carries the IPIs (a mailbox per core, CPU interrupt line 3);
  each core takes its own OST timer, peripheral interrupts stay on CPU 0.
  The test init's SMP checks (`smp_check()`): a CPU-bound loop does 2.00x
  the work on both cores; 4M atomic and 1M mutex increments across the
  cores all counted; 200000 release/acquire message round trips, none
  stale; 15000 map/fill/unmap cycles (TLB shootdowns) while the other core
  checks its buffer, no bad words; code rewritten on CPU 0 then run on
  CPU 1 20000 times, never stale. XBurst2 is weakly ordered, also around
  LL/SC (as Ingenic's kernels declare), so the platform selects
  `WEAK_ORDERING` and `WEAK_REORDERING_BEYOND_LLSC`. Single-process
  latency costs what SMP costs (fork 510 -> about 600 us, Kiln's 6.6:
  616 us; loopback TCP 365 -> 400-460 MB/s). Of that, the cache
  maintenance IPIs mainline sends to the other core are about 50 us of
  fork; Ingenic's kernels skip them. The cross-CPU code test also
  passed without them, but that proves little (cache evictions can hide
  a missed invalidation) and nothing documents that the hardware makes
  it safe, so they stay. Without CPU hotplug, suspend is off.
- **Klipper:** all four MCUs (motion controller, toolhead board, IFS, bed
  weighing board on `ttyS7`) connect from Kiln's userspace, and a full
  print ran. The IFS needed `rs485-rx-during-tx`: without it the 8250 core
  empties the RX FIFO when the driver enable drops, and the IFS, which
  answers within one frame, has started its reply by then (its transceiver
  does not echo our bytes, so nothing else changes).
- **Display:** a DRM driver for the DPU (`ingenic-dpu`) scans out one
  plane through the simple read channel; the SoC's Innosilicon LVDS PHY
  (the IP of `phy-rockchip-inno-dsidphy`, its PLL locked to the crystal)
  drives the KX070 panel on `panel-lvds`, with the backlight on PC14.
  HelixScreen runs on it through DRM (atomic page flips, vblank events)
  and through `/dev/fb0` (fbdev emulation); starting and stopping it
  repeatedly leaves no warnings. The kernel sets up the pixel clock and
  the PHY itself, so the screen also comes up from a cold boot, with
  nothing from stock's display drivers before it.
- **Touch:** the TSC2007 on I2C0 (`i2c-jz4780`, the X1000 register map),
  pen-down on PC7; HelixScreen's stored calibration lands taps right.
- **Restart:** the watchdog (`jz4740_wdt`, an X2600 variant: the TCU
  watchdog registers in a block of their own, cleared with TCSR.CLRZ
  since its counter ignores writes) restarts the board; `reboot` used to
  hang. A 10 s timeout fires when its pinger is killed, and not while it
  pings. With it, the chainload's `panic=10` reboots instead of hanging.
- **Speaker:** a new driver for the X2600's PWM controller
  (`pwm-ingenic-x2600`, 16 channels apart from the TCU, the waveform
  callbacks), the piezo on PC12 = channel 13. Measured on the printer
  first, with the channel driven by hand: a period starts with the phase
  INL picks, the high and low counts and INL are shadowed until UPT and
  the period's end, the prescaler is not, and a stop finishes the phase in
  progress. Checked with `PWM_DEBUG` and a pin trace (normal and inverted
  polarity, 0%, 100%, stop); `ad5x-sound`'s tones and MIDI files play.
- **Not needed:** cpufreq, thermal and an RTC driver; Kiln's 6.6 has none
  of them either (the board has no battery-backed clock: `ad5x-clock`).

Generic fixes this SoC needed, in the series:

- **UserLocal on XBurst II.** The Ingenic CPU feature overrides, written
  for XBurst1 (which has no UserLocal register), forced it off, so every
  thread pointer read from userspace (glibc's `rdhwr $29`, on each access
  to thread-local data) trapped and was emulated. The X2600 has it; the
  kernel now probes Config3 for it. A thread pointer read: 559 ns before,
  2.8 ns after.
- **Icache tagging from Config.VI.** The same overrides, and the probe,
  treated every XBurst icache as virtually tagged, so the kernel flushed it
  without need. Both XBurst programming manuals describe a physically
  tagged icache and hardwire Config.VI to 0, which the cache probe already
  reads, so the series drops both. On the X2600, code at a virtual address
  remapped to another page through the TLB alone runs the new page
  (`ictag.ko`, 20000 rounds per CPU). XBurst1 has not been tested.
- **-O2.** The defconfig builds the kernel for performance instead of
  size: fork 690 -> 510 us, fork + exec 1946 -> 1534 us, loopback TCP
  306 -> 365 MB/s, for a 12% larger image.

- **Stale L2 data after DMA (`WAR_INGENIC_L2_HIT_CACHEOP`).** With the
  L2-to-DDR prefetcher on, invalidating the L2 with Hit CACHE operations can
  leave stale data there, so DMA reads come back with the buffer's old
  contents, silently. rtw88 showed it: stale register reads, only for
  buffers at the start of a 64-byte L2 line (about 1 in 500), then wrong
  values written back into the chip; 1 in 12 when every buffer starts a
  line, as when each gets its own cache line. Turning off the L2-to-DDR
  prefetcher (CCU MSCR.DisPFB2) removes them, the L1-to-L2 one (DisPFB1)
  does not. The fix leaves the prefetcher on and, as mainline's R4600 V2.0
  workaround does, issues an uncached load (`__fast_iob()`) before
  `mips_sc_inv()`'s cache operations; Ingenic's kernels issue the same
  load. 0 stale reads in 20000 with it. Selected by `MACH_X2600` only.

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

- **IFS link errors (not the kernel).** Over the 2 h print Klipper counted
  604 invalid bytes from the IFS (about 30 messages) and resent 791;
  Klipper recovers, the print is unaffected. The stock kernel does the
  same with the same configuration (idle, 5 min: 21 invalid on stock,
  about 20 on mainline); an earlier clean stock print ran without Happy
  Hare, whose buffer sensors add traffic from the IFS on the half-duplex
  bus. The UART counts no framing, parity or overrun errors, and does not
  receive our own bytes back.

- **Wi-Fi under load.** The USB disconnects (-71) seen in some early
  boots with the camera plugged in have not come back since the L2 fix,
  and stale reads turning into wrong register writes would explain them;
  not proven. rtw88 returned an earlier read's value when a register read
  failed or came back short; the series fixes that.
- **Idle (compared, left as mainline).** Ingenic's kernels idle XBurst
  with interrupts off, a SYNC, then WAIT; mainline uses `r4k_wait`
  (interrupts on, no SYNC). Nothing documents why the SYNC is there, so
  the series doesn't change it. The rest of the SDK's X2600 setup
  (`arch/mips/xburst2/soc-x2600/`) has nothing mainline lacks: the DRAM
  size, the I/O base, a bus priority write left in `#if 0`, and suspend.
- **One unexplained hang.** Once, about a minute into a boot (the first
  boot with the PWM driver), the printer stopped answering on the network
  and the serial console, with nothing in the log. It hasn't come back:
  a 10 minute soak with tones and MIDI, and five boot rounds (boot, 3 min
  watched, reboot) were clean.
- **Direct boot (not Kiln's path).** Kiln never puts its kernel in a boot
  slot: `S00ad5x-kernel` chainloads it from stock at every boot, as the
  tests do. Booted straight by the boot loader, the USB PHY would start
  from its reset values (untested), and the MAC would get a random
  address; on Kiln `S41ad5x-eth` sets the one stock assigns (usershare
  `/MAC`) on any kernel.
- **From Ingenic's SDK, not documentation:** the PLL VCO range (672-2400
  MHz, the range of Ingenic's PLL table; the boot loader's settings are
  inside it), which pins have pull resistors (all allowed), and the X2600
  cores using the X2000 CPU compatible (the same PRId).
- **Sign-off.** Three patches are signed off and ready for submission:
  TLBINV on the whole MMU, icache tagging from Config.VI and the L2
  workaround. The rest carry no `Signed-off-by` yet; only you can certify
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

`check.sh` needs `sparse` (0.6.4 is too old for 7.3: `__typeof_unqual__`; v0.6.5-rc1 built from git.kernel.org works), and `dt-validate`/`yamllint` (pip: `dtschema`,
`yamllint`) on `PATH`.
