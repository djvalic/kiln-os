# Memory: 256 MiB and 512 MiB boards

Not every AD5X has the same amount of RAM. Some units have an Ingenic
X2600E with 256 MiB, others an X2600H with 512 MiB. One Kiln OS image runs
on both: it looks at the RAM at every start and adapts.

By default Kiln OS uses 256 MiB on every printer (standard memory): Kiln's
kernels get the low bank only, so an X2600H behaves like an X2600E and
every printer is tested the same way. On a 512 MiB board, Extended memory
can be switched on to use all of it (see "Extended memory" below).

| Board | RAM | MemTotal (stock 5.10) | MemTotal (Kiln's kernels, 236 MiB window) | MemTotal (Kiln's kernels, 252 MiB window) |
|---|---|---|---|---|
| X2600E | 256 MiB | about 229 MB | about 216-229 MB | about 16 MB more (to be measured) |
| X2600H | 512 MiB (two 256 MiB banks, the second at 0x30000000) | | about 470-480 MB (the owner's printer: 480992 kB) | standard memory (default): as the X2600E; Extended memory: about 16 MB more than with 236 MiB (to be measured) |

Kiln's kernels get 16 MiB more of the low bank than the stock kernel (see
"Memory map" below), and their configs leave out what Kiln doesn't use
("Kernels").

`grep MemTotal /proc/meminfo` shows which one you have; the boot log names
it too (see below).

## How much the system uses

Measured on an idle 512 MiB printer (proportional set size): Moonraker
34 MB, HelixScreen 31 MB, Klipper 24 MB, the camera streamer (ustreamer)
10 MB. During a print a 256 MiB board is estimated to peak at 140-170 MB,
which leaves little room on about 216 MB.

## What changes at start-up

`S04ad5x-memory` runs early in the main OS's start-up, before the data
partition is mounted and before any service starts.

On every board:

- `vm.min_free_kbytes` 4096: the kernel keeps 4 MiB free for allocations
  that can't wait (USB, Wi-Fi, the eMMC driver), instead of the ~1.8 MiB it
  picks on its own.
- Size limits on the RAM folders. Buildroot mounts `/tmp`, `/run` and
  `/dev/shm` with none, so each could fill half the RAM. Now `/tmp` holds
  at most 24 MiB, `/run` 8 MiB and `/dev/shm` 8 MiB. A full folder gives
  "No space left on device" to whatever writes there; nothing Kiln ships
  comes close (logs and the syslog are small, uploads don't go there, see
  below).

On a board with less than 300000 kB (a 256 MiB board, and a 512 MiB board
in standard memory), also:

- 64 MiB of compressed swap in RAM (zram, lz4 where the kernel has it,
  else lzo-rle). Memory the services hold but rarely touch is compressed
  there, typically to a half or a third of its size, before the system
  runs out.
- `vm.swappiness` 100 and `vm.page-cluster` 0: memory goes to zram before
  the kernel drops the cache of the read-only system files (which it would
  have to read and decompress again), one page at a time.
- The camera streamer runs with two capture buffers per camera
  (`--buffers=2`) instead of its default, one per CPU core plus one (three
  on the two-core X2600).

The result is in `/run/ad5x-memory.conf`, which other scripts and plugins
can read:

| Key | Value |
|---|---|
| `MEM_KB` | MemTotal in kB |
| `LOW_MEM` | `1` under 300000 kB (the profile above), else `0` |
| `HW_MEM_MIB` | `256` or `512`: the board's RAM, whatever this start uses |
| `MEM_MODE` | `standard` or `extended`: what this start got |
| `MEM_MODE_FIXED` | `1`: the boot loader can't choose the mode (an older Kiln U-Boot, below), else `0` |

and in one line of the boot log (`/run/ad5x-boot.log`):

```
12.34   memory: 221000 kB, 256 MiB board (X2600E), zram swap 64M (lz4)
12.34   memory: 240500 kB, 512 MiB board (X2600H), standard memory, zram swap 64M (lz4)
```

`swapon -s` or `cat /proc/swaps` shows the swap; `cat /proc/pressure/memory`
how long programs waited for memory (pressure stall information, on Kiln's
6.6 and 7.3 kernels).

## When memory runs out

The kernel's out-of-memory killer then ends one program. Kiln sets the
order, so the print is the last thing to go:

| Program | `oom_score_adj` | Set by |
|---|---|---|
| Camera streamer (ustreamer) | +500, goes first | `S64ad5x-camera` |
| Touch screen (HelixScreen) | +300 | `S70helixscreen` |
| Moonraker | -200 | `S62moonraker` |
| Klipper | -900 | `S61klipper` |
| Watchdog feeder | -1000, never | `S05ad5x-watchdog` |

`dmesg | grep -i "out of memory"` shows when it happened and what was
killed.

## Files that used to go to RAM

- **Uploads to Moonraker** (G-code from a slicer or Fluidd) are written to
  Moonraker's temporary folder whole before they are moved into `gcodes`.
  That folder was `/tmp`, so a 100 MB file took 100 MB of RAM. It is now
  `/data/ad5x/moonraker-tmp` (`TMPDIR`, `S62moonraker`), on the same
  partition as `gcodes`, so the move is a rename. It is emptied at each
  Moonraker start.
- **Updates in the recovery OS**: SWUpdate unpacks the whole `.swu` (up to
  ~100 MiB) before writing it. It now unpacks into `/data/ad5x/swupdate-tmp`
  when the data partition is mounted read-write with 256 MiB free, else
  into `/tmp` as before ([recovery-os.md](recovery-os.md), "Updates").

## Extended memory

A 512 MiB board can use all of its RAM. It is off by default and not
needed: Kiln OS is made to run in 256 MiB.

Switch it on (as root over SSH; Kiln's API, the touch screen's Settings >
System and the `KILN_MEMORY_MODE` macro use the same command):

```
ad5x-memory extended on     # from the next start
ad5x-memory extended off
ad5x-memory status          # hw_mem_mib, mem_kb, enabled, active, restart_needed, failed,
                            # bootloader_update_needed
```

`on` is refused on a 256 MiB board ("refused: this printer has 256 MiB").
The choice is the file `/data/ad5x/kernel/extended-memory`
([data-layout.md](data-layout.md)): it survives reboots and updates.

How a start gets its memory:

- Whoever starts Kiln's kernel puts the board's RAM and the mode on the
  command line: `ad5x.ram=256|512` and `ad5x.memmode=standard|extended`.
  Extended means the second bank, `mem=256M@0x30000000`, is passed;
  standard means it is not. `lib/memory.sh` reads them (`S04ad5x-memory`,
  `ad5x-memory`, and the boot loader installer's chip check, which takes
  `ad5x.ram=512` as an X2600H whatever the mode). Without the tokens (the
  stock 5.10, the recovery OS on it) the bank and MemTotal tell.
- The stock SPL's chain (`S00ad5x-kernel`): the board is 512 MiB when the
  stock kernel's command line has a `mem=` bank at 0x30000000. Our kernel
  gets that bank only when the switch is on, there is no failure record
  (below) and it isn't the first start after an install. Otherwise every
  `mem=` word at 0x30000000 is taken out, also one in `cmdline-extra`.
  The stock kernel's own command line is never changed.
- Kiln's U-Boot reads the same switch from the data partition and decides
  the same way (`u-boot/README.md`). Kiln's SPL alone (U-Boot missing or
  failed) always starts standard.
- The recovery OS: on the stock chain it runs Flashforge's 5.10 with the
  stock command line as before; under Kiln's boot loader standard memory.

An older Kiln U-Boot (installed before the memory mode, such as the rc3
opt-in boot loader) can't choose the mode. It writes the command line
itself (`ad5x.uboot=1`) and passes the board's banks as they are: a
512 MiB board always starts with the second bank (extended), with no
`ad5x.ram=` or `ad5x.memmode=`. `lib/memory.sh` (`mem_mode_fixed`) spots
that, `S04ad5x-memory` writes `MEM_MODE_FIXED=1` and the boot log says
"(set by an older boot loader)". A restart changes nothing there, so
`ad5x-memory status` says `bootloader_update_needed=1` and
`restart_needed=0`, Kiln's API `bootloader_update_needed: true` with no
restart and no notice, and the touch screen's row "Needs a boot loader
update to take effect." `ad5x-memory extended on|off` still writes the
switch; it counts once the boot loader is updated. Kiln's SPL alone and
the stock chain are not affected: neither adds `ad5x.uboot=1`.

If a start in extended memory doesn't finish (it never reaches
`S99ad5x-booted`: a hang, a crash, a power cut during start-up), the next
start is in standard memory by itself and stays so:

- on the stock chain `S00ad5x-kernel` writes
  `/data/ad5x/kernel/extended-memory-pending` before such a start and
  `S99ad5x-booted` removes it; found at the next start, the memory is
  blamed, not the kernel: `extended-memory-failed` gets "the printer
  didn't finish starting with it" and when, and our kernel is started
  again in standard memory (the failed start is not counted against the
  kernel; a failure of that standard start counts as usual);
- Kiln's U-Boot counts it as one of its tries and keeps a record of its
  own (`failed-mem` in its records sector); the main OS copies it into
  `extended-memory-failed` at the next start. On 6.6 the next start is
  the same kernel in standard memory. 7.3 has only one try, so there the
  failed start also counts against 7.3: the next start is 6.6 in
  standard memory, and both `ad5x-memory extended on` and
  `ad5x-kernel retry` are needed to go back to 7.3 with extended
  memory.

`ad5x-memory status` (and the touch screen, Kiln's API) then shows
"Extended memory was turned off: the printer didn't finish starting with
it." `ad5x-memory extended on` clears the record (both) and tries again
at the next start.

What it changes when on: about 480 MB instead of about 240 MB MemTotal,
`LOW_MEM=0` (no zram swap, the camera's default buffers).

### The first start with Extended memory: a test of the second bank

The SPL's DDR test covers the low window only, so `S05ad5x-memtest` (package
`ad5x-memtest`, main OS only) runs `ad5x-memtest-high` once, on the first start
in extended memory. It tests the second bank's free pages (filtered through
`/proc/self/pagemap`, usually most of the 65536) with four write-all/read-all
passes (address, inverse, 0x55555555, 0xaaaaaaaa), in a few seconds and at most
60 s. A fault records `extended-memory-failed` and restarts the printer in
standard memory; a test that doesn't finish (hang or reset) is recorded the same
way at the next start. A pass is kept in `extended-memory-tested` and the test
doesn't run again (delete that file to test again); after a fault, turning the
mode on again (`ad5x-memory extended on`) tests again. The 6.6 kernel needs `CONFIG_PROC_PAGE_MONITOR` (in `ad5x.config`).

## Memory map

The low bank (256 MiB at 0, on both boards) as each kernel sees it. Only
the 512 MiB board has the second bank, 256 MiB at 0x30000000: RAM for the
stock 5.10, and for Kiln's kernels in extended memory only (above).

| Physical | Size | Stock 5.10 | Kiln's 6.6 and 7.3 |
|---|---|---|---|
| 0x00000000-0x0EBFFFFF | 236 MiB | RAM (`mem=236M@0x0`) | RAM |
| 0x0EC00000-0x0FBBFFFF | 15.75 MiB | `rmem=16M@0xec00000`, kept for Flashforge's media drivers | RAM |
| 0x0FBC0000-0x0FBFFFFF | 256 KiB | (end of rmem) | crash log (ramoops, reserved; [data-layout.md](data-layout.md) `/sys/fs/pstore`) |
| 0x0FC00000-0x0FFFFFFF | 4 MiB | `rtos_size=4M@0xfc00000`, the RISC-V core's | reserved, as stock |

Kiln's kernels get `mem=252M@0x0` and no `rmem=`: neither has
Flashforge's media drivers (a USB camera's MJPEG comes from the camera).
Whoever starts them changes the stock command line the same way:

- the stock SPL's chain (stock 5.10 first): `S00ad5x-kernel` (`kiln_mem`)
  when it chainloads 6.6 or 7.3; the stock kernel itself, and the recovery
  OS on it, keep `mem=236M@0x0` and `rmem=`;
- Kiln's U-Boot: for every kernel it starts (only Kiln's);
- Kiln's SPL alone (U-Boot proper missing or failed): when the slot's
  uImage is Kiln's 6.6 (`Linux-6.6-ad5x`), not for Flashforge's 5.10
  (`u-boot/patches/0031`, `x2600_args_kiln_low`).

U-Boot itself stays in the 236 MiB at 0 (`dram_init`), below 0x0EB00000
(`board_get_usable_ram_top`, the SPL's uImage window): it needs no more,
it never touches the crash log, and an older kernel's crash log (1 MiB at
0x0EB00000, before 2026-11) survives too. A kernel started with the old
`mem=236M@0x0` (an older U-Boot or SPL) should still find its crash log
there, outside its RAM (pstore maps it as I/O memory then; not tested).

The RISC-V core's 4 MiB stay reserved. Whether anything runs there under
Kiln is not known: on the owner's printer (Kiln's U-Boot, 7.3,
2026-11-17) the first words of 0x0FC00000 read 0x3A3C3A3C 0x3A185A3C,
0x0FC00100 0x3A3C1A34, the same two seconds later; that looks like an
uninitialised pattern rather than a program, but proves nothing.

## Kernels

- The mainline 7.3 device tree describes only the 256 MiB at 0, which
  every board has. On a 512 MiB board the second bank comes from the boot
  loader's `mem=` arguments, as on stock and on 6.6 (whose device tree has
  no memory node at all).
- Both kernels have zram with lz4 and lzo, and pressure stall information
  (`CONFIG_PSI`).
- What both leave out to save RAM (`kernel-ingenic66/ad5x.config`,
  `kernel-mainline/kiln.config`): loadable modules (everything is built
  in; `chainload.ko` is loaded by the stock 5.10 kernel), the media
  drivers except USB webcams (no TV, radio, SDR, test or SoC camera
  support), the BFQ and Kyber I/O schedulers; the log buffer is 64 KiB and
  the contiguous memory area (CMA) 8 MiB. 7.3 also has no symbol table of
  kernel data (`KALLSYMS_ALL`) and no io_uring (nothing in the image uses
  it). On 7.3 that makes the kernel about 1.5 MiB smaller in RAM (text,
  data and bss) and its image 0.6 MB smaller.

## Plugins

A plugin that needs a lot of memory can read `LOW_MEM` from
`/run/ad5x-memory.conf` and do less when memory is small (a 256 MiB board,
or a 512 MiB board in standard memory). `HW_MEM_MIB` says what the board
has, `MEM_MODE` what this start uses. Follow-up: the
kiln-timelapse plugin's video render should use a low-memory encode there.
