# U-Boot and SPL for the AD5X (work in progress)

Mainline U-Boot (v2026.10) and an SPL for the Ingenic X2600 and the
Flashforge Adventurer 5X. The recovery OS carries the built images
(`buildroot/package/ad5x-bootloader`: `spl-mmc.img` and `u-boot-emmc.img`
in `/usr/share/ad5x/bootloader`) for its opt-in installer,
`ad5x-bootloader-install` ("Install Kiln's boot loader (experimental)",
`docs/own-boot-loader.md`); nothing writes them unless the user runs it.
Phases 0a/0b of the v1.0 boot plan began here: a correct, size- and
memory-checked build for the bench and printer tests.

The port is **Hunter Laux's (jolting)**: patches 0001-0012, his commits in
this directory's history, his chainload tests below. Kiln OS took it as he
wrote it (one trailer line trimmed from his patch headers, and his
userspace part left to the branch that owns userspace) and fixed what
review found in patches 0013-0016, 0017 leaves the watchdog running into
Kiln's own kernels, 0018-0023 fix what a second review against the
stock SPL's disassembly found, 0024-0025 let the SPL start from the
boot ROM's USB mode for the bench (`USB-BOOT.md`), and 0026 takes
Flashforge's 5.10 out of the fallback order (7.3 -> 6.6 -> the recovery
OS, which runs on Kiln's 6.6 from p1) and leaves what it started in
CPSPR, and 0027 starts the recovery OS only from Kiln's 6.6: this U-Boot
starts no Flashforge kernel at all.

## Layout

| Path | What |
|---|---|
| `patches/0001-0012` | jolting: X2600 + AD5X U-Boot proper, the X2600 SDHCI driver, SquashFS boot, environment, `ad5x_flag`, the SPL with the stock SPL's clock and DDR3 setup, watchdog and `ad5x_wdt` |
| `patches/0013` | the SPL inside the boot ROM's SRAM window, own eMMC reader, pins, clock parents, DDR and lpj as stock, second try, U-Boot proper from 0xA400, chainload-test build |
| `patches/0014` | U-Boot proper below the kernels' crash log (ramoops) |
| `patches/0015` | the environment in the `ota` partition |
| `patches/0016` | the boot rules (`ad5x_boot`, `bootlogic.c`): state in `ota`, 6.6 / 7.3 / stock kernel, checked recovery fallback, watchdog rules |
| `patches/0017` | the watchdog left running into Kiln's 6.6 and 7.3 (`ad5x_wdt_seconds`, `wdt_os=30`), stopped for the stock kernel and the recovery OS |
| `patches/0018` | start-up tries in CPSPR that always reach the other slot (`mach/ad5x_start.h`), U-Boot proper's entry value |
| `patches/0019` | SPL: watchdog armed first, UART0's clock, bounded console waits, OST set up whatever the ROM left |
| `patches/0020` | U-Boot proper gives up (reset, the SPL boots the slot) instead of parking at the prompt; stop key Ctrl-C or `kiln` (`stopkey.h`) |
| `patches/0021` | eMMC identification clock as the stock SPL (MSC0CDR bit 21, parent 3) in the SPL and `x2600_sdhci`; chainload test from the ROM's MSC0CDR |
| `patches/0022` | SPL: uImage limits without wrap, `ih_name` without `%.32s`, CMD6 SWITCH_ERROR, no SDHCI power write |
| `patches/0023` | SPL: the stock DDR table's name `W634GU6QG-11`, the `KILNCLK` clock record for the first-MiB check |
| `patches/0024` | SPL: MSC0's clock gate opened before the controller's reset (the ROM opens it only on an eMMC start) |
| `patches/0025` | SPL started over USB: the `KILNUSB1` tag or CPM_SLPC's soft request seen and cleared, a fresh start, a DDR test |
| `patches/0027` | slot A startable only with Kiln's 6.6 in p1 (`ad5x_slot_a_kernel_ok`, uImage name `Linux-6.6-ad5x`): a Flashforge 5.10 there is never started |
| `patches/0026` | no stock-kernel rung: 7.3 -> 6.6 -> the recovery OS; slot A broken: the main OS again on its own kernel; a Kiln 6.6 in p1 gets Kiln's command line; `0x55NK` in CPSPR before the jump (`ad5x_start_uboot_kernel`) |
| `patches/0028` | DDR parameters by the SoC ID in the eFuse (Ingenic's `check_socid()`): X2600H as before, X2600E (256 MiB) and X2600N (128 MiB) as the 2025 stock SPL; no `mem=256M@0x30000000` on a 256 MiB unit (SPL and U-Boot proper) |
| `patches/0029` | SPL: eMMC data at RX sample phase 3 (MSC0CDR 19:17, tuning off): phase 0 gives data CRC errors on an X2600E unit's A31M8C eMMC |
| `patches/0030` | U-Boot proper over USB as stage 2: the `KILNUSB2` SPL sets up DDR and goes back to the boot ROM, U-Boot runs `ums 0 mmc 0` (the eMMC as a USB disk); MSC pads at 1.8 V; the DWC2 gadget driver on MIPS |
| `patches/0031` | X2600: L1 and L2 cache range operations in U-Boot proper (the generic ones skip the L2: stale SETUP packets after DMA, ums never enumerated) |
| `patches/0032` | mmc: CMD12 after a failed multi-block read, and the chunk read again (a data CRC error left the card sending and ums dropped the disk) |
| `patches/0033` | dts: the OTG controller, FIFO sizes within its 3576 words |
| `patches/0034` | X2600: DMA alignment to the L2's 64-byte lines (`SYS_CACHE_SHIFT_6`; was the L1's 32) |
| `patches/0035` | net: designware: `virt_to_phys()`/`phys_to_virt()` between CPU and DMA addresses, registers mapped uncached (MIPS KSEG0/KSEG1) |
| `patches/0036` | net: `dwmac_ingenic`: the X2600 GMAC's pins (PC16-PC24), clock gate, 50 MHz MAC clock from the MPLL, RMII in the CPM; enhanced descriptors |
| `patches/0037` | AD5X: the MAC and its IP101G in the device tree, the address from usershare `/MAC`, `dhcp`/`ping`/`mii`/`wget`/`hash` |
| `patches/0038` | network rescue: a record in the first MiB's last sector (`ad5x_emmc_image.py --rescue`) makes U-Boot fetch, check and write the rest of the eMMC over HTTP; U-Boot proper ends one sector earlier |
| `patches/0039` | netconsole: U-Boot's console over UDP 6666 when `/data/ad5x/netconsole` exists (the PC's IP, or empty for the LAN) or `ad5x_nc` is set; always in the network rescue |
| `patches/0040` | prototype: the main OS in both slots (A/B), safe mode as the last fallback, all of the RAM to Linux (`mem=256M@0x0`, no `rmem=`/`rtos_size=`) |
| `USB-BOOT.md` | starting the SPL from the boot ROM over J28 (phase 4): wiring, soft entry and K4, the cold-start test; the eMMC as a USB disk (`run-uboot`) |
| `build.sh` | fetch v2026.10 (sha256-pinned), patch, build, check; `--container` for the laptop |
| `Containerfile` | the builder's pinned Debian base + Debian's `gcc-mipsel-linux-gnu` |
| `tools/ad5x_spl_image.py` | boot ROM header + INGE params generator; the SPL's memory-map check; a first-MiB candidate from a unit's dump; its write plan |
| `tools/check_first_mib.py` | offline check of a candidate first MiB against stock dumps, the build's `spl-mmc.img` and the unit's stock DDR table and clocks |
| `tools/spl_stack.py` | worst-case SPL stack from GCC's call graph (`--nm` for merged functions) |
| `../tools/ad5x_netconsole.py` | PC: U-Boot's netconsole, any OS with Python 3 (UDP 6666; Ctrl-C sends the stop key) |
| `tools/bootlogic_cli.c` | host driver for the boot rules (tests) |
| `tools/test_bootlogic_ab.py` | the A/B and safe-mode boot rules through `bootlogic_cli` |
| `tools/spl_uimage_cli.c` | host driver for the SPL's uImage loader, cut out of `spl.c` (`test_spl_uimage.py`) |
| `tools/ad5x_start_cli.c` | host driver for the start-up tries and the stop key (`test_ad5x_start.py`) |
| `tools/ad5x_usbboot.py` | laptop: the X2600 boot ROM's USB protocol, `info` and `run-spl` (pyusb; `--dry-run` without) |
| `../tools/bench/ad5x-usbboot-mode` | printer (bench only, copied over SSH): the soft entry into USB boot, with checks |
| `../tools/bench/ad5x-uboot-chainload` | recovery OS on 5.10 (bench only): U-Boot proper started from RAM with `chainload_uboot.ko`, nothing written (`tools/bench/README.md`, step 2) |
| `../tools/bench/ad5x-spl-flash` | main OS (bench only): the SPL written from `first-mib.img`, only 0x4-0x7 and 0x4400-0xA3FF, read back; `--restore` (`tools/bench/README.md`, step 3) |
| `../tools/bench/ad5x-uboot-flash` | main OS (bench only): U-Boot proper written at 0xA400 from `first-mib-uboot.img`, only its sectors, header last, read back; `--restore`, `--drill` (`tools/bench/README.md`, step 4) |
| `tools/test_*.py` | tests (run by `tools/autobuild.sh` as `uboot-tools`) |

Patches are `git format-patch` output on top of the v2026.10 tag, upstream
style, applied in order. They don't carry `Signed-off-by` lines of Kiln's
own (0013-0016 would need them for an upstream submission).

## Build

```
u-boot/build.sh --container          # laptop: podman (or docker), u-boot/Containerfile
u-boot/build.sh                      # builder: Buildroot's toolchain ($TOOLBIN), or Debian's
FIRST_MIB_DUMP=unit.img FIRST_MIB_ALSO=other.img u-boot/build.sh --container
```

`FIRST_MIB_DUMP` is a unit's stock first MiB: the main OS saves it as
`/data/ad5x/stock/boot.img` (copy it off with `scp -O`). For the bench
printer it was ours, with alexshev86's `first1m.bin` as `FIRST_MIB_ALSO`.

The Buildroot package `ad5x-bootloader` runs this same script on the
release tarball with the patches applied (`USRC`) and Buildroot's cross
compiler (`TOOLBIN`), for the recovery OS.

Output in `$WORK/out/dist` (`WORK` default `~/workspace/u-boot-ad5x-build`):
`u-boot.bin`, `u-boot-emmc.img` (U-Boot uImage for eMMC 0xA400),
`u-boot-kernel-slot.img` (the same as a Linux uImage, load = entry
0x80100000, for a kernel slot), `spl-mmc.img` (boot ROM image),
`spl-usb.bin` (the same with the USB tag, for `tools/ad5x_usbboot.py`),
`spl-chainload.bin` (chainload tests only), the SPL's map and `nm`,
`report.txt`, `SHA256SUMS`; with a dump also `first-mib.img` (a file:
nothing here writes a device), `first-mib-plan.json` (what an installer
may write for it, below) and `first-mib-uboot.img` (`first-mib.img` with
`u-boot-emmc.img` at 0xA400, checked by `check_first_mib.py --uboot`;
below, "U-Boot proper at 0xA400"). `SOURCE_DATE_EPOCH` is the last commit to
`u-boot/`, so a build is reproducible.

The build fails when: the SPL image exceeds what the boot ROM loads (48
blocks, 24 KiB); code/data/BSS leave the SRAM window or reach the stack
reserve (linker script asserts, `SPL_FOOTPRINT_LIMIT`, and the `nm` check);
the worst-case SPL stack exceeds the 2 KiB reserve, or the call graph has a
dynamic frame, recursion or an unknown call (a split `.part` merged with
another function counts as that function, by address from the `nm`
output; one that can't be resolved is an error); the stack-check build's
SPL differs from the real one; the chainload SPL would be accepted as a
boot ROM image; U-Boot doesn't fit 0xA400-1 MiB or a kernel slot; with a
dump, the first-MiB check fails or the write plan doesn't give the same
first MiB.

Results 2026-11-15 (Debian gcc 14.2.0, laptop container, patches
0001-0025):

| | |
|---|---|
| SPL code+rodata+data | 11,584 bytes (from 0x80001800 to 0x80004540); 27 blocks with the header, of 48 |
| SPL BSS | 940 bytes, 0x80004540-0x800048EC |
| SPL stack | reserve 0x80006800-0x80007000; worst case 512 bytes (board_init_f, spl_load_uimage, printf, _vprintf, x2600_spl_puts, x2600_spl_putc, udelay, __udelay, get_ticks) |
| free in the window | 7,956 bytes between BSS and the stack reserve (and 1,536 of the reserve unused at the worst case) |
| spl-usb.bin | 13,824 bytes to 0x80001000 (of the 0x7000 the ROM takes over USB); differs from spl-mmc.img only in the 8-byte tag |
| chainload-test SPL | 8,512 bytes |
| U-Boot proper | 351,580 bytes (343 KiB); uImage 351,644 of the 1,006,592 bytes from 0xA400 to 1 MiB. With 0026-0027 (2026-11-16): 351,812 bytes, uImage 351,876 (sectors 82-769); the SPL and `first-mib.img` byte for byte the same (built with step 3's `SOURCE_DATE_EPOCH`) |
| first MiB | both stock dumps: candidate passes the check (only the SPL range and the length fields differ; the SPL is `spl-mmc.img`'s; DDR table and clocks as the unit's stock SPL); the write plan gives the same first MiB |

jolting's SPL, for comparison: 22,400 bytes of code with BSS at
0x80007000-0x80009000, heap 0x80009000-0x8000B000 and stack 0x8000D000,
outside the window; with the stock header the boot ROM would have loaded
0x3E00 bytes of it.

## The boot ROM header (finding A)

The X2600 boot ROM reads LBA 0 bytes 0x000-0x0FF (the `INGE` params block,
inside the protective-MBR sector) and the SPL image at eMMC 0x4400 (a
2 KiB header, then the code), which it loads to 0x80001000 and starts at
0x80001800. Ingenic's tools write them: `spl_params_fixer_x2600.c` (the
params, at offset 0 and again at 256 of the image) and `mmc_params.c` (the
block count at offset 4, capped at 48 = 24 KiB).

| Field | Meaning | Stock (both dumps) |
|---|---|---|
| 0x0000 `INGE` | params id | |
| 0x0004 length | SPL image length rounded up to 512 | 0x4600 |
| 0x0008 pll_freq | APLL rate after the descriptors | 624,000,000 |
| 0x000C cpccr | CPCCR after them | 0x95073310 |
| 0x0010 nand_timing[16] | unused on eMMC | 3,14,6,20,6,12,15,0,...,30,0,0 |
| 0x0020 cpm_desc[14] | {u16 set, u16 poll, value, wait-set mask, wait-clear mask}, ended by 0xFFFF/0xFFFF | APLL 624 MHz, CPCCR dividers, CPCCR sources, DDRCDR, MSC0CDR (39 MHz), SFCCDR |
| 0x4400 `LPSM` | "MSPL" | |
| 0x4404 block count | blocks the ROM loads | 0x23 (35: 0x3E00 bytes of code) |
| 0x4500 | params copy, same length | |
| 0x4600-0x4BFF | zero (SDK: secure-boot room) | |
| after the image | 0xFF fill to 0xA400 (the SDK's `SPL_PAD_TO`) | |

`ad5x_spl_image.py` makes the header and the params block from these values;
its params block is byte-identical with both stock dumps' (tests). A
first-MiB candidate keeps the unit's own params and changes only the two
length fields and the block count. `check_first_mib.py CAND --unit DUMP
--spl spl-mmc.img [--also DUMP]` (or `--spl-sha256 HEX` of that image)
passes only when:

- nothing else differs from the unit's dump (the GPT 0x200-0x43FF
  included) and the SPL range is a well-formed image;
- the SPL range is this build's `spl-mmc.img` (its params copy aside,
  which is the unit's);
- the unit's stock SPL is the board build Kiln's SPL was made for: it
  holds the DDR3 table `W634GU6QG-11` with the same 188 bytes (name to
  `remap[]`) as the candidate's, and builds every value of the
  candidate's `KILNCLK` record (CPCCR 0x55700000, 0x557B5410,
  0x9A0B5410; APLL 0x03004901, MPLL 0x04B04901, EPLL 0x01905101) with
  `lui`/`addiu` immediates. A unit with another board build (the Nov 2025
  00437 one) is refused until its own dump has been looked at.

### Writing it: the write plan

`first-mib.img` carries the dump's GPT and everything else of it, which
may be stale by the time anything is written (an old dump, a unit
repartitioned since). Nothing may write it whole.
`ad5x_spl_image.py write-plan DUMP spl-mmc.img PLAN.json` (build.sh:
`first-mib-plan.json`) lists the only bytes that change, with their data
and SHA-256: 0x0004-0x0007 (the INGE length) and 0x4400-0xA3FF (the SPL
range), and the SHA-256 that 0x0000-0x00FF and 0x4400-0xA3FF must have
before (the dump's). An installer, which doesn't exist yet, must:

1. re-read the device's first MiB and refuse when the verify ranges
   differ (the dump is stale, or the SPL is already another one);
2. CRC-check the kernel slots read-only first (below);
3. write exactly the two write ranges, nothing else (never the GPT), and
   read them back.

`ad5x_spl_image.py apply-plan PLAN IN OUT` does steps 1 and 3 on a file
and refuses a plan that writes anywhere else; build.sh checks that it
gives `first-mib.img` from the dump. The bench script
`tools/bench/ad5x-spl-flash` does all three on the printer without
Python: it compares the device's first MiB with the saved `boot.img` and
`first-mib.img` byte for byte, writes the two ranges from `first-mib.img`
(the SPL's header sector zeroed, its body, the length, the header sector
last: a power cut leaves a whole SPL or none) and reads them back
(`tools/bench/README.md`, step 3).

### U-Boot proper at 0xA400

`ad5x_spl_image.py uboot-mib first-mib.img u-boot-emmc.img OUT` (build.sh:
`first-mib-uboot.img`) puts U-Boot proper's uImage at 0xA400 and changes
nothing else: its whole sectors (82 to 769 for 0027's 351,876 bytes,
0xA400-0x603FF), the rest of the last sector `first-mib.img`'s. It refuses
an image Kiln's SPL wouldn't start (`uimage_problems()`: the same checks
as `spl_load_uimage()`, and `test_spl_uimage.py` checks that both say yes
to the same images), one that isn't Kiln's (load = entry 0x80100000, name
`Kiln U-Boot`) and one that reaches 1 MiB. `check_first_mib.py CAND
--unit DUMP --spl spl-mmc.img --uboot u-boot-emmc.img` then passes only
when the candidate differs from the unit's dump in the SPL's ranges and
U-Boot's sectors alone. No JSON plan: the bench tool
`tools/bench/ad5x-uboot-flash` compares the device with `first-mib.img`
and `first-mib-uboot.img` byte for byte. `first-mib.img` must be the one
on the printer: build with step 3's `SOURCE_DATE_EPOCH` (its
`report.txt`), or the SPL's banner (its build date) differs.

**What Kiln's SPL does with a half-written U-Boot there**
(`arch/mips/mach-jz47xx/x2600/spl.c` after patches 0001-0025:
`ad5x_boot()` lines 435-457, `spl_load_uimage()` lines 363-399; from
patches 0013, 0018 and 0022): it boots the flagged slot, as with
Flashforge's raw U-Boot there, never hangs. `spl_load_uimage()` reads
sector 82 and returns 0 (not usable) when the magic isn't there (line
369-371); when the header CRC, MIPS, OS U-Boot, the size against 0xA400 to
1 MiB, the load address and entry point don't check (377-385); when an
eMMC read fails (369, 391); and when the data CRC over `ih_size` bytes
is wrong (393-396), which covers a body cut short or partly old: it reads
the blocks the header names whatever they hold. `ad5x_boot()` (448-456)
then prints "no U-Boot at 0xA400: the slot, as the stock SPL" and goes on
to the flag and the slot with the same tries as without U-Boot. Every
read is bounded (`spl_emmc.c`: 500 ms per block and for the end of the
transfer, then an error), and phase 2 (`AD5X_PH_UBOOT`) is armed with
the 10 s watchdog before the read (line 448), so even a read that hung
would reset into the next attempt without U-Boot proper (the skip bit,
"Tries"). A uImage with good CRCs that hangs after the jump resets
through the 30 s watchdog (line 452) the same way. `test_spl_uimage.py`
builds that C code on the host and runs it over the image cut at every
sector in both write orders, a torn header sector, single flipped bits,
read errors and refused headers: each ends in 0 (the slot) and only the
whole image in U-Boot's entry point.

**Write order** (the bench tool): U-Boot's state sector in `ota` zeroed
first (what step 2's starts left there would count against the first
start); then sectors 83-768 (the body); then sector 82 (the header) last,
each with `fsync` and read back. Until the header sector is written,
0xA400 holds Flashforge's bytes, no uImage magic, and the SPL boots the
slot as after step 3 without even reading the body; once it is, the whole
image is in place. A torn header sector fails its CRC. The restore writes
Flashforge's header sector back first, so the magic goes before anything
else changes. The 4 KiB page that holds sector 82 also holds 0xA000-0xA3FF
(the SPL range's 0xFF fill, which the boot ROM doesn't load: 27 blocks end
at 0x7A00) and sectors 83-87, rewritten with the bytes they already hold.

## SPL memory (finding B)

`x2600/u-boot-spl.lds`: everything in 0x80001000-0x80007000.

```
0x80001000-0x800017FF  header (loaded by the ROM, dead after the jump;
                       0x800017F0: the USB tag in spl-usb.bin)
0x80001800-...         text, rodata, data
...                    BSS (no heap: CONFIG_SPL_SYS_MALLOC_F off)
0x80006800-0x80007000  stack reserve, sp = 0x80007000
```

The generic MMC/SDHCI/block stack alone was about 10 KiB of SPL code and
needed a heap; `spl_emmc.c` reads the eMMC by PIO in about 2 KiB (CMD0,
CMD1, CMD2, CMD3, CMD7, CMD6 4-bit, CMD17/18 with auto CMD12, 25 MHz, no
HS switch), following the eMMC part of Ingenic's SPL driver for this SoC.
Patches 0006-0008 (legacy block lists, SDHCI phase checks, x2600_sdhci
without driver model) are no longer used by the SPL; they stay as
jolting's fixes.

## SPL behaviour (finding C)

- Order: start.S stops the boot ROM's watchdog (as stock); `board_init_f`
  first reads CPSPR and arms the watchdog for this attempt (10 s), then
  the OST, pins and console. Nothing before that can hang.
- Console: UART0's clock opened (CLKGR0 bit 12, as the stock SPL's
  `enable_uart_clk()`); 2 ms per character at most (one takes 87 us),
  and a UART that times out is left alone for the rest of the SPL.
- Timer: the OST set up at /1 (24 MHz) whatever the boot ROM left (the
  stock SPL sets /4); U-Boot proper sets it up too unless it runs at /1.
  `__udelay()` also ends after a loop count that can't be shorter than the
  delay, should the counter not run.
- Pins as the stock SPL's `gpio_set_func` calls: PD0-PD5 (MSC0) and
  PD6-PD11 (the SDK's SFC group) function 0, pulls off; PE9-PE12 (UART0)
  function 1 with the pull-up.
- Clocks: the stock PLLs (APLL 1152, MPLL 1800, EPLL 300 MHz), then every
  CGU parent as Ingenic's `cgu_clks_set()` sets them for `x2600_base`:
  DDR (2 = MPLL), MACPHY, LCD, MSC0, MSC1, SSI, SFC from the MPLL, PWM from
  the APLL.
- DDR3: jolting's port of Ingenic's code with the stock values;
  `DDRC_AUTOSR_EN` now 0, as in the stock SPL's table. The table is the
  stock one, `W634GU6QG-11`, byte for byte from the name to `remap[]`
  (`check_first_mib.py` compares it with each unit's); the clock values
  are one record, `KILNCLK`, that the checker reads.
- eMMC clock as the stock SPL's `clk_set_rate()`: controller clocks on,
  for identification MSC0CDR bit 21 (`MSCCDR_EXCK_E`) and parent 3
  (EXCLK) / 60 = 400 kHz, for data the MPLL / 72 = 25 MHz; change enable,
  wait for busy; no gating around the switch. No SDHCI power control
  write (neither the stock SPL nor the SDK's driver has one). CMD6 to 4
  bits is checked with CMD13 for SWITCH_ERROR (status bit 7): a card that
  refuses stays at 1 bit, and the host with it.
- `lpj=11935744`, as the stock SPL passes it (the SDK board config's
  11476992 is not what Flashforge ships).
- Chainload tests: `CONFIG_AD5X_SPL_CHAINLOAD=y` builds an SPL without the
  clock and DDR setup (`spl-chainload.bin`); it carries a marker the image
  tools and the checker refuse. No runtime guess any more. It writes the
  boot ROM's MSC0CDR value (0x20108003) before the eMMC setup, so the
  reader starts from the cold-start state, not Linux's.
- Tries (instead of `hang()`), with the CPM scratch pad CPSPR, which
  survives a watchdog reset (Ingenic's scheme; Linux writes 0x1a1a, 0x3535
  or 0x4343 there on reboot, bits 18-22 reserved). Kiln's values are
  `0x4b00 | low byte` (`mach/ad5x_start.h`): bits 0-1 the attempt, bit 2
  "skip U-Boot proper", bit 3 slot B, bits 4-6 the phase, bit 7 "slot
  forced" (not the flag's). Phases: 0 DDR, 1 eMMC (and the flag), 2
  loading or started U-Boot at 0xA400, 3 U-Boot proper up, 4 U-Boot
  proper gave up, 5 loading the slot, 6 kernel started, 7 a U-Boot proper
  from a kernel slot runs. Each SPL phase arms the watchdog for 10 s (30 s
  for U-Boot proper to come up); a failure resets through it at once.
  What the next SPL start does with the value it finds:

  | Found | Next attempt |
  |---|---|
  | not Kiln's, or 6 (a kernel was started: its reboot, a power cycle) | fresh: attempt 0, U-Boot proper, the flag's slot |
  | 0, 1 | the same plan again |
  | 2, 3, 4 | without U-Boot proper (the skip bit stays for this start) |
  | 5, 7 | the other slot, forced |
  | attempt 3 and any of these | stop, watchdog off (power-cycle to retry) |

  So within four attempts the board starts a kernel, or the next start
  stops; a failed slot is never loaded again before the other one: U-Boot proper hanging
  and the flagged slot not loading gives U-Boot, slot B, slot A.
  `test_ad5x_start.py` builds the header on the laptop and walks every
  combination (DDR/eMMC ok, failing once or always; U-Boot at 0xA400 none,
  booting, hanging before or after it starts, giving up, its read hanging;
  each slot a kernel, a bad or a hanging uImage, or a U-Boot proper that
  boots, hangs or gives up; either flag) from a fresh start and from every
  value the scratch pad can hold: each ends in a started kernel or the
  stop within five starts, and something bootable always boots as long as
  at most one DDR/eMMC failure is transient.
- Started over USB (patch 0025, `USB-BOOT.md`): the tag `KILNUSB1` at
  0x800017F0 (spl-usb.bin) or CPM_SLPC = 0x42575302 (the soft entry) says
  so; the SPL clears both (so the next reset boots from the eMMC), logs
  "started over USB", plans a fresh start whatever CPSPR holds (it prints
  the value), and after the DDR setup runs a DDR test: data lines,
  address lines 2-27 around 0x04100000, 16 MiB from 0x01000000 with
  address and inverted-address patterns, uncached, inside physical
  0x00100000-0x0C100000. A failure resets like the other SPL failures.
  The rest is the eMMC start's code; MSC0's clock gate is opened before
  the controller's reset (patch 0024), as the ROM opens it only on an
  eMMC start.
- U-Boot proper, as it starts, keeps the fields and sets the phase: 2 ->
  3 (from 0xA400), 6 -> 7 (from a kernel slot, so if it doesn't get a
  kernel going the SPL boots the other slot, not the same one again);
  anything else (the stock SPL, a chainload) -> 7 for slot B. Before it
  jumps to a kernel it writes `0x5500 | N << 4 | K` (patch 0026,
  `ad5x_start_uboot_kernel`): K 1 the main OS on 6.6, 2 on 7.3, 3 the
  recovery OS, 0 a `bootm` typed at the prompt; N the main OS's start
  count from U-Boot's state (1-15, 0 for the others). Not 0x4b00-0x4bff,
  so the SPL's next start is a fresh one, as it was after 0; Linux writes
  its own value only when it reboots, so `devmem 0x10000034 32` shows how
  a boot came up: `0x00005511` 6.6 at its first start through U-Boot,
  `0x00004B68` the SPL alone (slot B), `0x00004B6D` the SPL after U-Boot
  proper failed. It writes 0 in `reset` and at the prompt, and 4 (or
  keeps 7) when it gives up.
- SPL -> U-Boot proper: if eMMC 0xA400 holds a uImage with ih_os U-Boot,
  MIPS, load = entry inside it, and good header and data CRCs, it is loaded
  and started. Otherwise (as on every stock unit: the stock U-Boot there is
  raw) the SPL boots the flagged slot like the stock SPL, now checking the
  uImage's header and data CRCs, with the stock command line and the
  watchdog stopped. So one SPL serves phase 6 (only the SPL written) and
  phase 7 (U-Boot at 0xA400 added later). The uImage may hold a kernel or
  `u-boot-kernel-slot.img`.

## U-Boot proper (finding D)

- RAM: `board_get_usable_ram_top()` = 0x8EB00000: relocation, the 16 MiB
  heap and the stack stay below ramoops (0x0EB00000-0x0EBFFFFF).
- Environment: `ota` (p5) at 512 KiB and 544 KiB (eMMC 0xD980000 and
  0xD988000, 32 KiB each, redundant). Settings only: `bootcmd=ad5x_boot`,
  `ad5x_delay` (2 s for the stop key, Ctrl-C or `kiln`: prompt, watchdog
  off; any other byte is ignored), `wdt_os` (30, see Watchdog),
  `args_spl`. Reset to the build's defaults when it comes from another
  build. From Linux: `/dev/mmcblk0p5 0x80000 0x8000` and `0x88000 0x8000`
  in `fw_env.config`.
- `ad5x_flag a|b` and every fallback write only the flag's first bytes,
  as `echo ota:kernel > /dev/mmcblk0p5` does; the rest of the sector stays.
- Before any write U-Boot checks that the GPT agrees with the stock SPL's
  table (p1-p5 start LBAs and names, p7 `userdata`).
- Recovery kernel: read whole by its uImage header (any size up to 8 MiB),
  header and data CRC checked.
- Ethernet (patches 0034-0037): the X2600's GMAC, RMII to the IP101G at
  MDIO address 1, at the prompt only; nothing starts over the network by
  itself. The address is stock's, the first line of `/MAC` on usershare
  (p6), read only. Commands: `dhcp`, `ping`, `mii`, `wget` (HTTP; another
  port with `httpdstp`) and `hash -v sha256` to check what came in, e.g.

  ```
  setenv autoload no; dhcp
  setenv httpdstp 8000; wget ${loadaddr} 192.168.1.10:/rootfs.squashfs
  hash -v sha256 ${loadaddr} ${filesize} <sha256 from SHA256SUMS>
  ```

### `ota` layout (p5, 1 MiB)

| Offset | Size | What | Written by |
|---|---|---|---|
| 0x00000 | 12 B | boot flag `ota:kernel2\n` / `ota:kernel\n` (scripts read 256 B) | userspace, U-Boot on a fallback |
| 0x10000 | 8 KiB | boot trace (`ad5x-bootlog`) | userspace |
| 0x80000 | 32 KiB | U-Boot environment | U-Boot (once per build), `fw_setenv` |
| 0x88000 | 32 KiB | its redundant copy | |
| 0x90000 | 512 B | U-Boot state (sector 0x480 of p5) | U-Boot before each main-OS start; `S99ad5x-booted` zeroes it when the start finished |
| 0x90200 | 512 B | U-Boot records (sector 0x481) | U-Boot; `ad5x-kernel retry` zeroes it |

State and records are text, `key value` lines ending in `crc32 XXXXXXXX`
(zlib CRC-32 of everything before that line), NUL-padded:

```
kiln-uboot-state 1           kiln-uboot-records 1
tries 2                      failed-own 6.6.66-kiln
kernel 66                    failed-mainline -
release 6.6.66-kiln          fallbacks 1
crc32 1a2b3c4d               reason own kernel 6.6.66-kiln did not finish starting, 2 in a row; ...
                             crc32 ...
```

A sector that doesn't parse, has a bad CRC (an old `ota` backup restored)
or is all zeros counts as empty: a fresh start, never a fallback.

## Boot rules (`ad5x_boot`, `bootlogic.c`)

Inputs, read only: the flag; state and records; /data (ext4 p7):
`ad5x/kernel/mainline` (the 7.3 choice, read each start: the one source),
`ad5x/kernel/failed`, `ad5x/kernel/failed-mainline` (S00's records),
`ad5x/install/recovery.squashfs` (first start after an install),
`ad5x/kernel/cmdline-extra`; rootfs2 (SquashFS p4):
`/usr/lib/ad5x/kernel66/{xImage,release}`,
`/usr/lib/ad5x/kernel-mainline/{xImage,release}`; slot A: p1 a Linux uImage
for MIPS that isn't a U-Boot (load address 0x80100000), header and data CRCs
good, p1's kernel Kiln's 6.6 (uImage name `Linux-6.6-ad5x`, patch 0027,
`ad5x_slot_a_kernel_ok`), and p2 starting with `hsqs` (as S01 checks).
The main OS writes its 6.6 into p1 (and p3) once Kiln's SPL is in the
first MiB (`S99ad5x-update-recovery`); a p1 that still holds Flashforge's
5.10 makes slot A not startable. p1's kernel is never started for the main
OS. This U-Boot starts no Flashforge kernel; a `bootm` typed at the prompt
still starts whatever it is given.

1. Flag on slot A: slot A startable -> the recovery OS; the state is cleared
   (a recovery start gives the main OS fresh tries). Not startable -> the
   main OS, and the flag is pointed at slot B so it tells the truth.
2. Flag on slot B, the main OS. Kernel order as S00ad5x-kernel's: 7.3 if
   `mainline` exists, it's not the first start after an install and its
   release hasn't failed; else 6.6 unless its release failed. Never
   Flashforge's 5.10 (patch 0026: the stock-kernel rung is gone). The
   state counts unconfirmed starts:
   - one unconfirmed 7.3 start: its release goes into `failed-mainline`,
     this start uses 6.6;
   - two unconfirmed 6.6 starts in a row (one, on the first start after an
     install): its release goes into `failed-own`; 7.3 next if it is
     chosen and hasn't failed, else the recovery OS;
   - no kernel left (both failed, or none in rootfs2), or two unconfirmed
     starts of a kernel this build doesn't know (`kernel stock` in a state
     an older build wrote): the recovery OS, `ota:kernel` written to the
     flag, the state cleared, the reason recorded ("own kernel R did not
     finish starting, 2 in a row: recovery OS"). Slot A not startable: the
     main OS again on its own kernel whatever the records say (6.6, else
     7.3; never a loop on a broken slot A); no kernel at all (also when
     the eMMC doesn't come up in U-Boot): U-Boot proper gives up, it
     records that in CPSPR and resets, and the SPL boots the flagged slot
     itself (or the other slot when this U-Boot came from one; on the
     slot, the SPL starts what the slot holds: Kiln's 6.6, which the main
     OS writes into kernel2 too). The prompt with the watchdog off only
     after the stop key.
   - the recovery OS gives the main OS fresh tries: "Boot main OS"
     (`ad5x-boot-main`) and a finished install (`ad5x-slot-b.sh
     postinst`) zero the state and the records and drop S00's `failed`
     files (`rc_uboot_fresh`). Without that a 6.6 recorded as failed would
     send every start back to the recovery OS: the release string is the
     same in every build.
   - a record naming another release than the installed one is dropped (an
     update), as S00 does; counts saturate at 250.
   - a kernel that can't be loaded is left out and the rules run again.
3. Command lines: `args_spl root=/dev/mmcblk0p4` (recovery: `p2`)
   `ad5x.uboot=1`; for 6.6/7.3 also `ad5x.kernel=own panic=10 loglevel=5`
   and `cmdline-extra`, as S00 adds them; for the recovery OS on Kiln's
   6.6 `ad5x.kernel=own panic=10 loglevel=5` without `cmdline-extra`.
   Never `ad5x.noslot`.
4. `ad5x_boot -n` prints the inputs and the decision without writing or
   booting.

Every failing sequence ends in the recovery OS within three unconfirmed
starts (7.3 once, 6.6 twice), or stays on the main OS when slot A is
broken (`test_bootlogic.py`, Simulation).

## Watchdog (findings D and the audit)

The X2600's watchdog counts the RTC clock, EXCLK / 512 = 46,875 Hz on this
board (no 32.768 kHz crystal), through a prescaler of 1, 4, 16, 64, 256 or
1024 into a 16-bit compare register (TDR): the longest timeout is 65,535 x
1024 / 46,875 = 1431.6 s (`X2600_WDT_MAX_MS` 1,431,000; the 7.3 driver
rounds its rate down to 45 Hz and allows 1456 s, which then lasts 1431 s).

| When | Timeout | By |
|---|---|---|
| boot ROM -> SPL | ROM's | the SPL stops it at once (start.S, as stock) |
| each SPL phase, armed before the console | 10 s | SPL |
| SPL -> U-Boot proper | 30 s | SPL |
| U-Boot proper | 120 s from `board_early_init_f` | U-Boot |
| the stop key (Ctrl-C or `kiln`) within `ad5x_delay` | off | U-Boot |
| nothing startable, no stop key | 10 ms: U-Boot gives up and resets, the SPL boots the slot | U-Boot |
| the jump into Kiln's 6.6 or 7.3 until its driver probes | **30 s** (`wdt_os`), `ad5x.wdt=30` on the command line | U-Boot (`board_preboot_os`) |
| from the driver's probe until userspace opens `/dev/watchdog` | the driver's (6.6: 15 s, 7.3: 5 s), fed by the kernel every half of it, for at most 300 s (`CONFIG_WATCHDOG_OPEN_TIMEOUT`) | kernel |
| userspace | 120 s, fed every 10 s (`/usr/lib/ad5x/watchdog.conf`) | `S05ad5x-watchdog` (BusyBox `watchdog`) |
| the main OS's start-up, started by U-Boot | not finished (`/run/ad5x-booted`) 900 s after boot (`START_LIMIT`), no print running: the feeder is stopped (SIGKILL), reset 120 s later | `S05ad5x-watchdog` (its guard) |
| halt, poweroff (and reboot) | stopped | rcK (`S05ad5x-watchdog stop`: magic close), and the drivers' `watchdog_stop_on_reboot` |
| the recovery OS, a `bootm` typed at the prompt | stopped before the jump | U-Boot |

`ad5x_wdt_seconds()` (`bootlogic.c`, tested on the host) leaves it running
only when all of these hold; otherwise U-Boot stops it before the jump:

- the start is the main OS on Kiln's 6.6 or 7.3 (from rootfs2);
- rootfs2 has `/usr/lib/ad5x/watchdog.conf`: that system's kernels take a
  running watchdog over (6.6 `kernel-ingenic66/patches/0018`, 7.3
  `kernel-mainline/patches/0080`) and its userspace feeds it. An older
  Kiln OS or a restored stock system lacks it and would be reset over and
  over;
- `/data/ad5x/watchdog.disable` doesn't exist (the owner's off switch,
  which `S05ad5x-watchdog` honours too: with it, it stops a watchdog that
  runs anyway, e.g. when U-Boot couldn't read /data);
- `wdt_os` isn't 0 (at most 1431).

The recovery OS always starts with it stopped, as from the stock SPL:
its `S05ad5x-data` may run `e2fsck` on /data for longer than a kernel
feeds a running watchdog (300 s). Its own feeder starts it after that.

Why 30 s: the drivers probe within a few seconds of the jump (built in,
before the root is mounted), so 30 s is ten times that; short enough that
a kernel whose driver doesn't take over resets before `S99ad5x-booted`
confirms the start, so the boot rules count it and fall back (7.3 -> 6.6 ->
the recovery OS, without the watchdog) instead of a confirmed start being
reset over and over. Why 300 s for the kernel's own feeding: the main OS reaches
`S05ad5x-watchdog` in well under a minute (no fsck in the main OS's
`S05ad5x-data`); a userspace that never gets there (a hang in a start
script, `init=` broken) resets. Why 120 s/10 s in userspace: only a real
stall of userspace for two minutes resets the board; a busy printer (MCU
flashing, a recovery install writing the eMMC) still feeds it from a
daemon at nice -20 that the OOM killer doesn't pick.

A start script that hangs after the feeder has started (the daemon still
runs) is caught by the start-up limit: with U-Boot the boot flag stays on
slot B (`S01ad5x-tryboot`), so without the limit such a start would sit
there until a power cycle. Started by U-Boot, `S05ad5x-watchdog` also
starts a guard that waits for `S99ad5x-booted`'s `/run/ad5x-booted`; 900 s
after boot without it (and without a print running, as Moonraker reports
it), it kills the feeder without the magic close. The watchdog resets the
board 120 s later; U-Boot finds the state it wrote before the jump
unconfirmed and counts it (7.3 once, 6.6 twice, then the recovery OS). It
says so on the console and in the boot trace, which survives the reset.
900 s is well beyond a normal start (under a minute to `S05`, 1-2
minutes to `S99`) and beyond `S68ad5x-update-agent`'s 600 s grace for
reboots during start-up.

## Userspace and kernel changes U-Boot needs

What the systems do differently when U-Boot started them (`ad5x.uboot=1`);
most are done (branches v1-step4 and v1-step5):

- **S99ad5x-booted**, when `ad5x.uboot=1`: confirm the start by clearing
  the state. **Done** (`lib/uboot.sh`, `uboot_booted` in S99, branch
  v1-step4): at the point S99 marks start-up finished (SSH up, the flag
  read back on this slot) it zeroes sector 0x480 (`conv=fsync,notrunc`),
  reads it back (O_DIRECT when BusyBox's dd has it) and says in its output
  and the boot trace which start it confirmed (`kernel`, `release`,
  `tries`) or that it couldn't. Zeros are what `ad5x_state_parse()` reads
  as "no unconfirmed start". U-Boot's records (0x481) are logged there
  too and **kept**: they are the only account of why a start fell back,
  and they keep U-Boot off a kernel that failed, as S00's `failed` files
  do; `ad5x-kernel` shows them and `ad5x-kernel retry` zeroes them (only
  when the sector holds records). Without `ad5x.uboot=1` nothing reads or
  writes either sector. Required before phase 7 (U-Boot proper at
  0xA400): without it every start counts as unconfirmed, and after two
  the rules fall back from 6.6 to the recovery OS on a printer that is
  fine.
- **The installer of the SPL (phase 6)**: Kiln's SPL refuses a slot whose
  uImage has a bad header or data CRC (the stock SPL never checked them and
  started whatever was there). Before it writes anything, the installer
  must CRC-check both kernels, p1 and p3, read-only (`mkimage -l`-style:
  magic, header CRC, data CRC over `ih_size`), and refuse when either is
  bad; then follow the write plan (re-read and compare the first MiB,
  write only 0x4-0x7 and 0x4400-0xA3FF, read back). Every later writer of
  a kernel slot (`ad5x-update`, `ad5x-slot-b.sh`, a recovery install)
  must leave a uImage whose CRCs are right, as they do today.
- **S01ad5x-tryboot**, when `ad5x.uboot=1`: don't point the flag at the
  other slot. U-Boot counts and falls back; a stock-SPL flag flip would
  boot recovery without U-Boot seeing the failure. **Done** (v1-step5).
  What then catches a start-up that hangs in userspace: before
  `S05ad5x-watchdog` the kernel feeds the watchdog for 300 s at most;
  after it, the start-up limit (`START_LIMIT`, 900 s; "Watchdog" above)
  stops the feeder, so the board resets 120 s later and U-Boot counts
  the start. A whole-system stall resets after 120 s as before.
- **S00ad5x-kernel**, when `ad5x.uboot=1`: never chainload (U-Boot chose
  the kernel). **Done** (v1-step5): on the stock kernel it does nothing,
  on ours it is a direct start (a `pending` from the chain is dropped
  with a history line). U-Boot's records: `ad5x-kernel` shows them and
  `ad5x-kernel retry` zeroes sector 0x481 (done); Moonraker's
  `/machine/kiln_os/kernel` doesn't read them yet.
- **ad5x-boot-main** (recovery's "Boot main OS") and a **successful
  recovery install** (`ad5x-slot-b.sh postinst`): zero the state and the
  records (sectors 0x480, 0x481) and drop S00's `failed` files, each with
  a history line, so the main OS gets fresh tries (`rc_uboot_fresh` in
  recovery.sh). **Done** (v1-step5). The records too: with no stock rung
  a 6.6 recorded as failed would send every start back to the recovery
  OS.
- **The kernel slots** (v1-no510): with Kiln's SPL in the first MiB
  (`boot_loader` in slot.sh: its `KILNCLK` record), whoever started the
  boot, no Flashforge kernel is left in a slot. `S99ad5x-update-recovery`
  puts the main OS's own 6.6 (`/usr/lib/ad5x/kernel66/xImage`, a whole
  uImage named as Kiln's 6.6, the one running now, or on 7.3 one not
  recorded as failed: `kiln_slot_kernel` in uboot.sh) into p1 (`ad5x-update
  --install-recovery`) and p3 (`ad5x-update --kernel2`), header last, read
  back, at most 3 tries each; nothing else ever goes there (never
  kernel2's 5.10). With Flashforge's SPL p1 gets kernel2's kernel as on
  the stock chain, but never Kiln's U-Boot or Kiln's 6.6. The recovery
  OS: an update that brings a kernel is refused, an empty kernel2 gets
  only a Kiln 6.6 from p1, `ad5x-restore` (and the USB rescue's flash)
  takes only Kiln's 6.6 for kernel or kernel2, and Flashforge's first MiB
  only over Flashforge's 5.10 in both slots, written last.
  `ad5x-restore-stock` leads to the recovery OS's Return to Flashforge
  firmware (`ad5x-return-stock`, `docs/recovery-os.md`): U-Boot out,
  stock's root and 5.10 into slot B, started by Kiln's SPL (5.10 in a slot
  is allowed once Kiln's U-Boot is gone). On the bench:
  `tools/bench/ad5x-spl-flash --restore` puts the saved stock kernel
  (`/data/ad5x/stock/kernel.img`, sha256 as SHA256SUMS there) into any
  slot that doesn't hold a 5.10 before Flashforge's SPL.
- **Kiln's SPL alone** (U-Boot proper missing, failed, or removed with
  `ad5x-uboot-flash --restore`): it starts Kiln's 6.6 directly from the
  flagged slot with the stock command line (`console=ttyS0,115200n8
  loglevel=8 mem=236M@0x0 rmem=16M@0xec00000 rtos_size=4M@0xfc00000
  mem=256M@0x30000000 init=/linuxrc root=/dev/mmcblk0p4 rootwait
  rootfstype=squashfs ro lpj=11935744`, p2 for slot A; no `ad5x.uboot=1`,
  no `ad5x.kernel=own`, no `panic=10`) and the watchdog stopped.
  `S00ad5x-kernel` takes it as a direct start (a chain's pending marker
  dropped), `S01ad5x-tryboot` points the flag at slot A for the start-up
  as on the chain (nothing else counts the start), `S05ad5x-watchdog`
  starts the feeder (no start-up limit), `S99ad5x-booted` points it back,
  U-Boot's sectors untouched. CPSPR `0x00004B68` (slot B). The SPL's
  slot loader takes the 6.6 uImage (load = entry 0x80F00000, under the 8
  MiB slot limit, CRCs; `test_spl_uimage.py`, KernelSlot, also over the
  real build's uImage when it is there).
- **ad5x-status**, the recovery UI, `/machine/kiln_os/kernel`: read state
  and records (text; check the CRC32 line) for "last start fell back
  because ...", tries and kernel.
- **ad5x-update --install-recovery**: it copies kernel2 to p1 when they
  differ; with U-Boot in kernel2 that would put U-Boot into slot A. Skip a
  kernel2 whose uImage is U-Boot (load 0x80100000, name `Kiln U-Boot`).
  **Done** (v1-step5, `uimage_is_uboot` in slot.sh; also in
  `S99ad5x-update-recovery`'s comparison).
- **ad5x-slot-b.sh**: keeps a kernel2 that holds a uImage, which a U-Boot
  uImage is: fine; installing or updating U-Boot in kernel2 needs a step of
  its own (name and CRC check, read-back).
- **ad5x-boot-main**: its "kernel2 holds a uImage" check passes for U-Boot.
- **rc_slot / slot.sh**: U-Boot passes `root=/dev/mmcblk0p2|p4`, so
  PARTLABEL support isn't required by it.
- **ad5x-restore-stock**: under Kiln's boot loader (both the main OS's
  and the recovery OS's) it leads to Return to Flashforge firmware
  (`ad5x-return-stock`, recovery OS): Kiln's U-Boot is removed first, so
  stock in slot B is started by Kiln's SPL alone and never by U-Boot,
  which starts only Kiln OS. **Done** (v1-revert; v1-step5 refused).
- `/etc/fw_env.config` + libubootenv only for changing U-Boot settings
  (`wdt_os`, `ad5x_delay`) from Linux: `/dev/mmcblk0p5 0x80000 0x8000`,
  `/dev/mmcblk0p5 0x88000 0x8000`.
- jolting's S99 change (BusyBox `watchdog`, `fw_setenv boot_pending`) is
  superseded by the above.

The watchdog items are done (branch v1-watchdog): both kernels' drivers
detect a running watchdog at probe (`WDOG_HW_RUNNING`, the core feeds it
until userspace opens `/dev/watchdog`) and stop it on halt/poweroff
(`watchdog_stop_on_reboot()`); `S05ad5x-watchdog` feeds it in the main and
the recovery OS; `wdt_os` defaults to 30.

## E: U-Boot in a kernel slot (phase 5)

`u-boot-kernel-slot.img` is U-Boot proper as a Linux uImage, load = entry
0x80100000: the stock SPL (and Kiln's) loads it like a kernel, flushes the
caches and jumps to it. Its flag-A path is the recovery OS from p1, so it
works whether the stock SPL or U-Boot handles slot A. Script changes it
needs are listed above (ad5x-update, S00, S01, S99, ad5x-boot-main). One
catch: a main OS started by this U-Boot puts its own 6.6 into p1, and with
U-Boot in kernel2 it is the stock SPL that handles flag A, so it would
start that 6.6 directly with its stock command line. Untried; phase 7
(U-Boot at 0xA400) is the path in use.

## jolting's tests (2026-11-14/15, by chainload; no slot or first-MiB writes)

From the stock 5.10 kernel with `kernel-ingenic66/chainload`, its
trampoline's `LOAD_ADDR` changed to 0x80100000, after setting PE9/PE10
(the DEBUG header) to UART0:

- the prompt, `time sleep 10` = 10.000 s;
- `mmc info` (SanDisk `DA2016`, 52 MHz High Speed mode at 50 MHz), `mmc
  part`, the `ota` and `kernel2` sectors;
- a direct boot of 6.6 from `rootfs2` (5.6 MiB in about 0.3 s), up to the
  main OS with Klipper ready;
- `saveenv` at the old location (0x8A400): a dump of the first MiB before
  and after differed only in 0x8A400-0x9274B;
- a start with `boot_pending` set: flag to slot A, the stock kernel from
  `kernel`, the recovery OS up;
- the watchdog: after `ad5x_wdt 600` the counter runs at about 45 Hz,
  `ad5x_wdt off` stops it; `reset` restarts the board through the SPL;
  armed for 300 s into 6.6 and fed by BusyBox's `watchdog` there was no
  reset, killing the feeder reset the board 60 s later;
- his SPL (generic MMC stack, DDR setup skipped) chainloaded from Linux
  booted the stock kernel to the main OS.

What changed since then is **untested on hardware**: the SPL's eMMC reader,
pins, clock parents, tries and U-Boot path; the boot rules; the
environment and records in `ota`; ramoops kept; everything in 0018-0023
(the start-up order, UART0's clock and timeout, the OST set-up, the eMMC
clock with bit 21 and parent 3 in both the SPL and U-Boot proper, the
1-bit fallback, U-Boot proper giving up, the stop key), and 0024-0025
(the MSC0 gate, the USB start and its DDR test). The laptop checks
cover only the logic: the tries and the stop key (`test_ad5x_start.py`),
the image, checker and write plan, the stack, the USB loader's transfers
against a fake device and the bench helper with stubs
(`test_ad5x_usbboot.py`, `test_usbboot_bench.py`).

## Open questions that need hardware

- Does the boot ROM honour the new header (25 blocks) and the INGE length?
  Which of the two fields does it use (both are set)? Does it check
  anything else (the params copy at 0x4500)?
- What is 0x80001000-0x80007000 physically (SRAM or locked cache)? The SPL
  flushes by address range only, so either works; the stock SPL's
  `flush_cache_all()` suggests SRAM.
- The boot ROM's own stack: the SPL no longer uses it (sp = 0x80007000);
  that 0x80006800-0x80007000 is free for us is from the SDK's 24 KiB window.
- The own eMMC reader at 25 MHz, 4-bit, PIO on this SanDisk part and on
  others. Without a power control write after the controller reset (as
  the stock SPL and the SDK): does the bus stay powered on every unit?
  The 1-bit fallback after a refused CMD6 is untried (no card refuses it
  here).
- The identification clock with bit 21 and parent 3 (as the stock SPL
  sets it): 400 kHz in the SPL and in U-Boot proper (jolting's `mmc info`
  ran with parent 2); and the chainload test from 0x20108003 (the ROM's
  MSC0CDR) while Linux had the eMMC running.
- UART0's clock gate (CLKGR0 bit 12) is opened now; is the 2 ms per
  character enough on every unit, and does a UART that times out leave the
  rest of the start unharmed?
- The OST at /1 set up whatever the ROM left: does `time sleep 10` still
  give 10 s in U-Boot proper started from the stock SPL (which leaves /4)?
- CPSPR: kept over a watchdog reset (as Ingenic's code assumes)? Its value
  at power-on (not one of Kiln's 0x4b00-0x4bff by chance; one of those
  would cost a try or two, never a loop)? Bits 0-7 kept as written?
- The watchdog armed first in `board_init_f` and the 10 s per phase:
  enough for the console, DDR training plus eMMC init on every unit? The
  give-up reset from U-Boot proper (10 ms after its message) and the SPL
  booting the slot after it; the stop key over the DEBUG header.
- U-Boot's ext4 read of /data after an unclean shutdown ignores the journal:
  are the small files read right?
- Behaviour on the Nov 2025 board build (00437): its SPL and GPT differ;
  `check_first_mib.py` refuses it until its stock SPL's DDR table and
  clock immediates match Kiln's (or Kiln's SPL is made for its values);
  build its first MiB with `FIRST_MIB_DUMP` from that unit's own dump.
- USB boot (phase 4, `USB-BOOT.md`, "Only hardware can tell"): the ROM
  taking spl-usb.bin at 0x80001000 and starting 0x80001800, FLUSH_CACHE
  before PROG_START1, the SPL's clocks/DDR/eMMC from the ROM's USB state,
  whether the ROM clears CPM_SLPC itself. The SPL boots the slot; it
  doesn't return to the ROM (the SDK's `RUN_FIRMWARE_VIA_USB_BOOT`).
- The watchdog into Linux (0017 and the kernel patches): both kernels log
  `running at boot` and don't reset while booting with `wdt_os=30`; a
  `kill -9` of the feeder resets after 120 s; HelixScreen's and the
  recovery UI's Shut down stay off for good (minutes), Reboot comes back;
  `poweroff -f` stays off; a recovery `.swu` install and MCU flashing run
  through; `watchdog.disable` starts the kernel with it stopped. Also the
  chain without U-Boot (5.10 -> chainload 6.6/7.3): the feeder starts it,
  the 6.6 driver puts it on EXCLK/512 (is OPCR bit 2 clear at power-on
  under the stock SPL?).

Writing the boot loader can make the printer unable to start until it is
reprogrammed over J28. Don't install it on a printer you can't open.
