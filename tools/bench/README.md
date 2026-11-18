# Bench tools (our printer only)

Scripts for the boot loader tests of the v1.0 plan on our own printer.
**Not in any image, not in the update or install path, not in HelixScreen,
Fluidd or the recovery UI.** For everyone else the recovery OS has the
opt-in installer, `ad5x-bootloader-install` ("Install Kiln's boot loader
(experimental)", `docs/own-boot-loader.md`), which writes the same ranges
in the same order from the images it carries, on boards on its allowlist. They are copied over SSH when a step needs
them and run by hand as root, one step at a time. Each one checks first,
says exactly what it would do, and does it only with `--yes`.

| Script | Runs on | What it does | Laptop test |
|---|---|---|---|
| `ad5x-uboot-chainload` | the recovery OS (slot A, Flashforge's 5.10) | starts Kiln's U-Boot proper from RAM; writes nothing to the eMMC (step 2) | `tools/test_bench_uboot_chainload.sh` |
| `ad5x-spl-flash` | the main OS (slot B) | writes Kiln's SPL into the first MiB, only 0x4-0x7 and 0x4400-0xA3FF; `--restore` puts Flashforge's back (step 3) | `tools/test_bench_spl_flash.sh` |
| `ad5x-uboot-flash` | the main OS (slot B) | writes Kiln's U-Boot proper at 0xA400 (only its sectors, header last) over Flashforge's, Kiln's SPL already there; `--restore` puts Flashforge's back; `--drill` sets U-Boot's state for a fallback drill (step 4) | `tools/test_bench_uboot_flash.sh` |
| `ad5x-usbboot-mode` | the main OS | the soft entry into the boot ROM's USB mode (`u-boot/USB-BOOT.md`) | `u-boot/tools/test_usbboot_bench.py` |

Printer: `$P` below is its address (`P=192.168.x.y`), root over SSH
(`scp -O`: Dropbear has no SFTP); `$BK` is the laptop folder that keeps
this printer's backups (`BK=~/ad5x-backups`).
`D` below is the U-Boot build's output (`u-boot/build.sh`, default
`~/workspace/u-boot-ad5x-build/out/dist`). Run the tests with
`tools/test_bench_uboot_chainload.sh`, `tools/test_bench_spl_flash.sh` and
`tools/test_bench_uboot_flash.sh`, under BusyBox with `AD5X_TEST_BB=DIR`
(applet links from `busybox --install -s DIR`).

## Before step 2: the files

1. **This printer's first MiB and a full backup**, after the test build is
   installed (plan step 1). The main OS saves the first MiB once, while it
   is still Flashforge's (`S99ad5x-booted`):

   ```
   mkdir -p $BK && cd $BK
   scp -O 'root@$P:/data/ad5x/stock/boot.img*' .
   sha256sum -c boot.img.sha256 && cat boot.img.info
   ```

   and the whole eMMC as in `docs/emmc-backup.md`.

2. **U-Boot and the SPL for this printer**, on the laptop:

   ```
   FIRST_MIB_DUMP=$BK/boot.img u-boot/build.sh --container
   ```

   `$D/report.txt` must say that the first-MiB check passed and that the
   write plan gives `first-mib.img`. That makes `first-mib.img`,
   `first-mib-plan.json`, `spl-mmc.img` and `u-boot-kernel-slot.img`, all
   in `$D/SHA256SUMS`.

3. **`chainload_uboot.ko`** (the bench build of `kernel-ingenic66/chainload`,
   below) from a builder run of a branch that has it: the run's
   `bench/` folder holds it and its `SHA256SUMS` (in the builder's logs,
   `<logs>/<run>/bench/`):

   ```
   B=~/ad5x-bench/<run>; mkdir -p $B
   cp '<logs>/<run>/bench/'* $B/
   (cd $B && sha256sum -c SHA256SUMS)
   ```

### The module

`kernel-ingenic66/chainload` builds two modules from one source:
`chainload.ko` (`make`, what `S00ad5x-kernel` uses at every start,
unchanged: the default build compiles to the same code as before) and
`build-uboot/chainload_uboot.ko` (`make uboot`, `-DCHAINLOAD_UBOOT
-DCHAINLOAD_LOAD=0x80100000`, its own directory and object names). The
bench build differs in three ways:

- its trampoline copies the image to 0x80100000, U-Boot proper's load and
  entry address, instead of 0x80F00000, then flushes L1 and L2 and jumps
  there as before (jolting's test changed `LOAD_ADDR` the same way);
- it takes only an uncompressed legacy uImage whose load and entry address
  are 0x80100000 and whose size is the rest of the file, that is
  `u-boot-kernel-slot.img`. The 64-byte header is skipped as for a kernel,
  so what lands at 0x80100000 is `u-boot.bin`. A raw `u-boot.bin` is
  refused: the header carries the CRCs the script checks and the address
  the module checks;
- `.modinfo` names it (`name=chainload_uboot`, `kiln_load=0x80100000`),
  which the script checks, so S00's module can't be taken for it.

Both are built against the same 5.10 header tree with Buildroot's
toolchain (`ad5x-kernel66.mk`). The bench one goes to Buildroot's
`images/bench/`, never into the rootfs, and `tools/autobuild.sh` copies
that folder into the run's logs. For a compile check on the laptop, with
the 5.10 tree from `kernel-ingenic66/chainload/setup.sh` and Debian's
cross compiler in the U-Boot build container:

```
podman run --rm --userns=keep-id -v ~/workspace/chainload-build/linux-5.10.186:/k:ro \
	-v "$PWD/kernel-ingenic66/chainload:/w" localhost/kiln-uboot-build \
	make -C /w uboot KDIR=/k CROSS_COMPILE=mipsel-linux-gnu- KCFLAGS=-Wno-error
```

Use the builder's module on the printer (same toolchain as
`chainload.ko`, which has run there since 2026-10-17).

## Step 2: U-Boot chainloaded from Flashforge's 5.10

Nothing is written to the eMMC by the script except its log
(`/data/ad5x/bench/uboot-chainload.log`) and, with `--main`, the boot
flag. A power cycle undoes the test: Flashforge's SPL starts the flagged
slot as before.

**Why the recovery OS, and why `--main`.** The module is built for
Flashforge's 5.10, and the recovery OS is the one system that runs on it
(the main OS has moved on to 6.6 by the time anyone can log in). But in
the recovery OS the boot flag is on slot A, and U-Boot's first rule is
"flag on slot A: the recovery OS". So the test has two parts: without
`--main` U-Boot starts the recovery OS again and the flag stays as it is;
with `--main` the script first points the flag at slot B with the recovery
OS's own `ad5x-boot-main --no-reboot` (what "Boot main OS" does), and
U-Boot starts the main OS on 6.6.

**What U-Boot itself writes**, all in `ota` (p5), never the first MiB or a
slot: its environment at 0x80000 and 0x88000 (once, when it finds none or
another build's), its state sector at 0x90000 before each main-OS start
(`tries`, `kernel`, `release`), and its records at 0x90200 only on a
fallback. The flag (bytes 0-11) only on a fallback too. Neither SPL nor
Linux reads these; later U-Boot starts do (below).

### 2a. U-Boot starts the recovery OS

1. Printer idle on the main OS. Boot into recovery (touch screen, or
   `ssh root@$P ad5x-boot-recovery`) and wait until SSH answers
   and the recovery screen shows.
2. Copy the files to `/tmp` (RAM: gone after the jump; nothing on the eMMC):

   ```
   mkdir -p /tmp/ut && cp tools/bench/ad5x-uboot-chainload $D/u-boot-kernel-slot.img $B/chainload_uboot.ko /tmp/ut/
   (cd $D && grep ' u-boot-kernel-slot.img$' SHA256SUMS; cd $B && grep ' chainload_uboot.ko$' SHA256SUMS) > /tmp/ut/SHA256SUMS
   ssh root@$P mkdir -p /tmp/ut && scp -O /tmp/ut/* root@$P:/tmp/ut/
   ```

3. Dry run: every check says `ok`, then the plan; exit 2.

   ```
   ssh root@$P /tmp/ut/ad5x-uboot-chainload
   ```

4. `ssh root@$P /tmp/ut/ad5x-uboot-chainload --yes`. SSH drops.
   Watch the screen (bed camera if nobody is at the printer: the screen
   goes dark, then the recovery logo comes back) and wait for SSH, up to
   3 minutes.
5. Check, read only:

   ```
   ssh root@$P 'cat /proc/cmdline; uname -r'
   ```

   Pass: `ad5x.uboot=1` and `root=/dev/mmcblk0p2` on the command line,
   `5.10.186+`. U-Boot added `ad5x.uboot=1`; Flashforge's SPL never does.

### 2b. U-Boot starts the main OS (6.6)

1. Still in the recovery OS (2a left it there): copy the files to `/tmp/ut`
   again (2a's copy went with the jump), dry run with `--main`. It also
   checks slot B and that U-Boot's state counts no unconfirmed start, and
   says which kernel U-Boot should pick (6.6; 7.3 when mainline is on).
2. `ssh root@$P /tmp/ut/ad5x-uboot-chainload --main --yes`.
   Watch the screen; wait for Fluidd (`http://$P`) or
   `curl -s http://$P:7125/server/info` to show `klippy_state`
   `ready`, up to 5 minutes.
3. Check, read only:

   ```
   ssh root@$P 'cat /proc/cmdline; uname -r; grep -e "directly" -e "own kernel" /run/ad5x-boot.log; cat /data/ad5x/kernel/last-ok'
   ```

   Pass: Klipper ready; the command line has `ad5x.uboot=1`,
   `root=/dev/mmcblk0p4` and `ad5x.kernel=own` (and `ad5x.wdt=30` when the
   installed build has the watchdog, `/usr/lib/ad5x/watchdog.conf`: U-Boot
   leaves it running into 6.6); `uname -r`
   is 6.6; the boot log says "own kernel started directly" (S00 saw no
   chainload marker); `last-ok` ends in `direct ok`.

### After the test

U-Boot's state now counts this main-OS start as unconfirmed unless the
installed build confirms U-Boot's starts (`S99ad5x-booted` with
`lib/uboot.sh`, branch v1-step4: it zeroes the state once start-up has
finished and logs `uboot: start confirmed` in `/run/ad5x-boot.log`).
Older builds don't: two of those starts and the next U-Boot start records
6.6 as failed and takes the stock kernel, so clear it before another
`--main` test (the script refuses until then); `ad5x-uboot-flash` (step 4)
zeroes it itself before it writes. On the main OS:

```
# read only: U-Boot's state and records
dd if=/dev/mmcblk0p5 bs=512 skip=1152 count=2 2>/dev/null | tr -d '\000'
# or, with the script copied there: ad5x-uboot-chainload --records
# clear the state sector (0x90000) only, then read it again
dd if=/dev/zero of=/dev/mmcblk0p5 bs=512 seek=1152 count=1 conv=fsync,notrunc
```

Records (0x90200, `seek=1153`) are only there after a fallback; clear them
the same way once read. The environment can stay (U-Boot resets one from
another build itself). To remove every trace of U-Boot from `ota`:
`dd if=/dev/zero of=/dev/mmcblk0p5 bs=512 seek=1024 count=130
conv=fsync,notrunc` (0x80000-0x903FF: both environments, state, records;
nothing else lives there: the boot traces are at 64 and 128 KiB).

**If nothing comes back** in 3 minutes (2a) or 5 (2b): power-cycle (the
smart plug, below). U-Boot's watchdog resets a U-Boot that hangs after it
started (120 s); a hang in the trampoline or before U-Boot's watchdog
needs the power cycle. Flashforge's SPL then starts the flagged slot:
recovery after 2a, the main OS (stock chain) after 2b. Keep
`/run/ad5x-uboot-chainload.log` if the jump was refused (it says why).

**Serial console (optional):** U-Boot prints on UART0, the DEBUG header's
PE9/PE10 (`docs/serial-console.md`). Under Flashforge's 5.10 those pins
are GPIO unless PC6 was high at power-on, so the header may stay silent;
jolting switched them to UART0 before his chainload. The test doesn't
need it.

## Step 3: Kiln's SPL written, Flashforge's U-Boot left alone

The new SPL finds no U-Boot uImage at 0xA400 (Flashforge's is raw) and
boots the flagged slot as Flashforge's SPL does, with the same command
line, now checking the kernel's CRCs (`u-boot/README.md`, "SPL
behaviour"). **A hang of the new SPL leaves the printer down until it is
restored over J28** (risk accepted, contingency below).

### What the script checks and writes

Refuses unless: root; the main OS on slot B with start-up finished
(`/run/ad5x-booted` and the flag `ota:kernel2`); Moonraker answers and
Klipper is not printing or paused (`--moonraker-down-ok` only if you know);
no update or restore running; `/data/ad5x/stock/boot.img` 1 MiB, matching
`boot.img.sha256`, Flashforge's SPL by `boot.img.info` and its own bytes;
the disk a block device, not read-only, not mounted whole, no partition
below 0xA400, the GPT's entries (at the LBA its header names: 2 on ours,
32 on alexshev86's) ending before 0x4400 (on ours: 8 entries to 0x800,
first usable LBA 34 = 0x4400, p1 at LBA 2048); the disk's first
MiB, read with caches dropped (O_DIRECT when BusyBox's dd can), equal to
`boot.img` byte for byte; `first-mib.img` and `spl-mmc.img` matching
`SHA256SUMS`; `first-mib.img` differing from `boot.img` only inside
0x4-0x7 and 0x4400-0xA3FF (`cmp -l`), its SPL range being `spl-mmc.img`
(with `boot.img`'s params copy at 0x4500, as `ad5x_spl_image.py` makes it)
and 0xFF fill, its length fields agreeing (length = blocks × 512 = the
image's size); `first-mib-plan.json`'s hashes, if it is there; both kernel
slots with good uImage header and data CRCs (Kiln's SPL refuses a bad
one; Flashforge's never checked); 1 MiB free on `/data`. No Python: the
candidate is a whole first MiB that the shell compares byte for byte.

It writes, with `dd ... conv=notrunc,fsync`, in this order: zeros over
sector 34, the SPL's header (`if=/dev/zero bs=512 seek=34 count=1`); the
SPL's body (sectors 35-81, `bs=512 skip=35 seek=35 count=47`); the length
(4 bytes at 0x4, `bs=4 skip=1 seek=1 count=1`); the header sector (`bs=512
skip=34 seek=34 count=1`), all but the zeros from `first-mib.img`. After
each it reads the first MiB back and compares that range, then the whole
MiB.
A failed write or read-back writes `boot.img`'s bytes back for the same
ranges at once (two tries) and checks them. `--restore` writes `boot.img`'s
bytes with the same checks (not the candidate's) and the same read-back.
`--status` only says what the first MiB holds: `stock`, `flashed`,
`partial` (an interrupted write: only the two ranges differ, and they
aren't `first-mib.img`'s), `not stock, no first-mib.img ... to compare`
(the same without a candidate to tell Kiln's SPL from an interrupted
write) or `other` (with Kiln's U-Boot at 0xA400 it says so and points at
`ad5x-uboot-flash`, whose `--restore` goes first). Without DIR it looks
for the candidate next to itself, then in `/data/ad5x/bench`.
Everything goes to `/data/ad5x/bench/spl-flash.log`.

Exit codes: 0 done (or nothing to do), 1 refused (nothing written), 2 dry
run, 3 failed but `boot.img`'s bytes are back and read back right, 4 failed
and the first MiB is not as before.

### Write order

The boot ROM reads the SPL's header at 0x4400 (sector 34: `LPSM` and the
block count) and the length at 0x4 (LBA 0); it checks no checksum. With
no valid header it goes into USB boot mode by itself, with no K4 short:
alexshev86 proved that on his printer by zeroing sector 34 (issue #68).
Flashforge's SPL needs 0x4600 bytes, Kiln's 0x3600.

- **Flash and restore alike: the header sector zeroed first, then the
  body (sectors 35-81), then the length, then the header sector last.**
  While sector 34 is zero the boot ROM finds no SPL, so a power cut then
  leaves the printer in USB boot mode (J28 + USBCloner with `boot.img`,
  no K4: "Contingency" below). Before the zeroing the old SPL and length
  are whole and agree; after the header is written the new ones are. No
  moment leaves a valid header in front of a body cut short, which the
  boot ROM would start (a hang that only K4 gets out of). The length is
  written while no header is in place, so its value can't matter then.
- **Changed after the printer tests (2026-11-16).** Steps 3-5 below were
  run on our printer with the earlier order: the 48-sector SPL range in
  one `dd`, and the length first when it grew, last when it shrank (so it
  always covered the SPL in place). That order left a valid new header in
  front of a half-written body during the SPL `dd`; it is replaced
  consistently here, in `ad5x-bootloader-install` and in Return to
  Flashforge firmware (`lib/bootloader.sh`'s `bl_put_spl`). The new order
  has not been run on the printer yet; its tests are
  `tools/test_bench_spl_flash.sh`, `tools/test_bootloader_install.sh` and
  `tools/test_return_stock.sh`.
- The script ignores HUP, INT, TERM and PIPE while writing, so an SSH drop
  doesn't stop it half-way.
- The block layer writes whole sectors (and the page cache whole pages):
  the 4-byte write rewrites LBA 0 and the GPT sectors around it with the
  bytes they already hold (checked equal to `boot.img` just before).

### Steps

1. Step 2 passed; `boot.img` and the full backup are on the laptop; `$D`
   is from this printer's `boot.img` (above). The printer idle on the main
   OS; the smart plug reachable.
2. Copy (`/tmp` for this run; a second copy of the script on `/data` so
   that `--restore` works later without the laptop):

   ```
   ssh root@$P 'mkdir -p /tmp/spl /data/ad5x/bench'
   scp -O tools/bench/ad5x-spl-flash $D/first-mib.img $D/spl-mmc.img $D/first-mib-plan.json $D/SHA256SUMS root@$P:/tmp/spl/
   scp -O tools/bench/ad5x-spl-flash root@$P:/data/ad5x/bench/
   ```

3. Dry run, and read it: every line `ok`, "first MiB now: stock", then
   1. sector 34 zeroed, 2. the SPL's body (Flashforge's banner ->
   Kiln's), 3. the length `00460000 -> 00360000`, 4. sector 34 from
   `first-mib.img`, last; exit 2.

   ```
   ssh root@$P /tmp/spl/ad5x-spl-flash /tmp/spl
   ```

4. Write: `ssh root@$P /tmp/spl/ad5x-spl-flash --yes /tmp/spl`.
   It takes about a second. Expect "done: the first MiB reads back ... as
   first-mib.img byte for byte", exit 0. Copy the log off:
   `scp -O root@$P:/data/ad5x/bench/spl-flash.log $BK/`.
   - Exit 3: Flashforge's SPL is back and checked; nothing else changed.
     Stop, keep the log.
   - Exit 4: **don't power off or reboot.** Run
     `/data/ad5x/bench/ad5x-spl-flash --restore --yes` (it needs only
     `boot.img`); if that fails too, keep the printer on and go to the
     contingency.
5. First start of the new SPL: power-cycle (below, one cycle). Wait for
   Klipper ready, up to 5 minutes. Then, read only:

   ```
   ssh root@$P 'devmem 0x10000034 32; /data/ad5x/bench/ad5x-spl-flash --status; cat /proc/cmdline'
   ```

   `0x10000034` is CPSPR, the scratch pad Kiln's SPL writes as it starts
   the kernel: `0x00004B68` (phase 6 "kernel started", bit 3 slot B,
   attempt 0; `u-boot/README.md`, "Tries"). Flashforge's SPL leaves no
   `0x4B__` value there. Read it after a power cycle, not after a reboot
   (Linux writes its own value on reboot). `--status` says `flashed`; the
   command line is the stock one (`lpj=11935744`), so S00 chainloads 6.6
   as before.
6. The cold-start loop, 20 times (below). Pass: 20 of 20 to Klipper ready,
   CPSPR `0x00004B68` each time (an attempt above 0, `0x4B69`-`0x4B6B`,
   or a forced slot means a start failed and was retried: note it).
7. To go back to Flashforge's SPL while the new one boots:
   `ssh root@$P /data/ad5x/bench/ad5x-spl-flash --restore --yes`,
   then one power cycle; after it `--status` says `stock` and CPSPR holds
   no `0x4B__` value.

## Step 4: Kiln's U-Boot proper at 0xA400

Kiln's SPL (step 3) finds a U-Boot uImage at 0xA400 and starts it; U-Boot
proper picks the kernel by its rules (`u-boot/README.md`, "Boot rules")
and starts Kiln's 6.6 or 7.3 from rootfs2 directly. No Flashforge code
runs on a normal start of the main OS any more. With step 4's U-Boot the
recovery OS still starts on Flashforge's 5.10 from p1 and the stock-kernel
rung is Flashforge's 5.10 too; step 5 (below) removes both.
`ad5x-uboot-flash` writes U-Boot's sectors only (82-768,
0xA400-0x601FF for step 4's 351,644 bytes; 82-769 for 0026's 351,836), from
`first-mib-uboot.img`; nothing else of the first MiB changes.

**Why a half-written U-Boot doesn't stop the printer**: Kiln's SPL starts
U-Boot only when its header and data CRCs (and the rest of its header)
check, else it boots the flagged slot exactly as after step 3
(`u-boot/README.md`, "U-Boot proper at 0xA400", with the code's lines;
`u-boot/tools/test_spl_uimage.py` runs that code over every way the write
can be cut). The tool writes the body first and the header sector last,
so until the very end 0xA400 holds no uImage magic at all. A U-Boot that
starts but hangs is reset by the SPL's watchdog (30 s, then U-Boot's own
120 s), and the next attempt skips U-Boot proper and boots the slot
(CPSPR `0x00004B6D`: attempt 1, phase 6, slot B, bit 2 "without U-Boot
proper"). What can
still stop the printer is what could in step 3: an SPL that hangs
(contingency below).

### What the script checks and writes

Refuses (nothing written) unless: everything `ad5x-spl-flash` checks
about the system, the printer and `boot.img` (root, main OS on slot B,
start-up finished, idle, no update, `boot.img` Flashforge's and checking,
with Flashforge's raw U-Boot at 0xA400); the installed system confirms
U-Boot's starts (`/usr/lib/ad5x/uboot.sh` and `uboot_booted` in
`S99ad5x-booted`; without that U-Boot falls back after two good starts);
the disk's first MiB, read past the caches, is `first-mib.img` byte for
byte (Kiln's SPL in front, Flashforge's U-Boot behind) and CPSPR says
Kiln's SPL started this boot's kernel from slot B (`0x4B68`; a later
attempt `0x4B69`-`0x4B6B` is noted); `first-mib.img`,
`first-mib-uboot.img` and `u-boot-emmc.img` match `SHA256SUMS`;
`first-mib.img` is `boot.img` with Kiln's SPL only; `first-mib-uboot.img`
is `first-mib.img` with `u-boot-emmc.img` in U-Boot's sectors and nothing
else; `u-boot-emmc.img` is a uImage Kiln's SPL starts (magic, both CRCs,
MIPS, OS U-Boot) and Kiln's (load = entry 0x80100000, `Kiln U-Boot`);
U-Boot's range ends before the first partition (GPT and sysfs: LBA 2048,
1 MiB); both kernel slots' CRCs good; U-Boot's records (ota 0x90200)
don't name the installed 6.6 or 7.3 as failed (`ad5x-kernel retry`
first); U-Boot's stored settings (ota 0x80000), if any, have
`bootcmd=ad5x_boot`; 1 MiB free on `/data`.

It writes, with `dd ... conv=notrunc,fsync`, each read back past the
caches (O_DIRECT where BusyBox's dd can): 1. U-Boot's state sector (ota
0x90000, `seek=1152`) zeroed, if step 2 left starts counted there (they
would count against the first start; the settings stay: U-Boot resets
settings from another build itself, and the step-4 build is the step-2
one); 2. sectors 83-768 (`bs=512 skip=83 seek=83 count=686`); 3. sector
82 (`skip=82 seek=82 count=1`), the header, last; then the whole first
MiB. A failed write or read-back writes `boot.img`'s bytes back from
0xA400 at once, header sector first (two tries). `--restore` does that on
request (needs only `boot.img`; it covers every sector from 0xA400 that
differs from `boot.img`). `--status` is read only: the first MiB (with or
without the candidate), CPSPR, the command line, U-Boot's state, records
and settings. `--drill` is for the drills below. Log:
`/data/ad5x/bench/uboot-flash.log`. Exit codes as `ad5x-spl-flash`'s (0
done, 1 refused, 2 dry run, 3 failed with the first MiB as before, 4
failed and it is not: don't power off, `--restore --yes`).

### Steps

1. Step 3 passed (10 of 10 cold starts so far). The printer runs a build
   with the U-Boot confirmation (a builder run of v1-step4 or later,
   installed as usual):

   ```
   ssh root@$P 'ls /usr/lib/ad5x/uboot.sh; grep -c "uboot_started && uboot_booted" /etc/init.d/S99ad5x-booted'
   ```

   says the file and `1`. Idle on the main OS, the smart plug reachable.

2. **The candidate, on the SPL already on the printer.** The build puts
   its date (`SOURCE_DATE_EPOCH`, the last commit to `u-boot/`) into the
   SPL's banner, so a new build's `first-mib.img` is not step 3's and the
   script refuses it. Build with step 3's date:

   ```
   S3=~/workspace/u-boot-ad5x-build-e66ec47/out/dist     # step 3's dist
   SOURCE_DATE_EPOCH=$(sed -n 's/^SOURCE_DATE_EPOCH=//p' $S3/report.txt) \
   WORK=~/workspace/u-boot-ad5x-build-step4 \
   FIRST_MIB_DUMP=$BK/boot.img u-boot/build.sh --container
   D=~/workspace/u-boot-ad5x-build-step4/out/dist
   cmp $D/first-mib.img $S3/first-mib.img && cmp $D/u-boot-emmc.img $S3/u-boot-emmc.img && echo "same SPL, same U-Boot"
   grep -e '^first MiB with Kiln.s SPL and U-Boot' -e 'U-Boot proper at 0xA400' $D/report.txt
   ```

   `first-mib.img` must be `fe93be50...` (what `spl-flash.log` says was
   written), and `report.txt` must say both first-MiB checks passed. With
   the patches unchanged U-Boot proper is then byte for byte the one step 2
   started (`u-boot-kernel-slot.img` is the same `u-boot.bin`).

3. Copy, to `/data/ad5x/bench` (it stays there for `--restore`, `--status`
   and the drills, next to the step 3 script, which then also finds its
   candidate there):

   ```
   ssh root@$P mkdir -p /data/ad5x/bench
   scp -O tools/bench/ad5x-uboot-flash tools/bench/ad5x-spl-flash $D/first-mib.img $D/first-mib-uboot.img \
   	$D/u-boot-emmc.img $D/spl-mmc.img $D/first-mib-plan.json $D/SHA256SUMS root@$P:/data/ad5x/bench/
   ```

4. Dry run, and read it: every line `ok`; "first MiB now: 0-0xA3FF Kiln's
   SPL (first-mib.img); from 0xA400 Flashforge's U-Boot (boot.img)";
   CPSPR `0x00004B68`; U-Boot's state, records and settings (from step
   2: `ad5x_build` names the build that saved them, `bootcmd=ad5x_boot`;
   settings of another build U-Boot replaces with its own defaults at
   its first start); the kernel U-Boot should start; then the plan:
   (the state sector, if step 2 left a start there), sectors 83-768,
   sector 82 last. Exit 2.

   ```
   ssh root@$P /data/ad5x/bench/ad5x-uboot-flash
   ```

   `ad5x-spl-flash --status` says `other` now and names U-Boot at 0xA400;
   that is expected after the write, not before it.

5. Write: `ssh root@$P /data/ad5x/bench/ad5x-uboot-flash --yes`.
   About a second. Expect "done: the first MiB reads back ... as
   first-mib-uboot.img byte for byte", exit 0. Copy the log off:
   `scp -O root@$P:/data/ad5x/bench/uboot-flash.log $BK/`.
   Exit 3: `boot.img`'s bytes are back from 0xA400, nothing else changed:
   stop, keep the log. Exit 4: don't power off or reboot;
   `/data/ad5x/bench/ad5x-uboot-flash --restore --yes`; if that fails too,
   keep the printer on and ask (the SPL still boots the slot with any
   non-uImage there, but stop anyway).

6. **First start through U-Boot**: power-cycle (one cycle). Wait for
   Klipper ready, up to 5 minutes, then `/run/ad5x-booted`. Read only:

   ```
   ssh root@$P 'devmem 0x10000034 32; cat /proc/cmdline; uname -r; cat /data/ad5x/kernel/last-ok;
   	grep -e "started directly" -e "chainload" -e "uboot" /run/ad5x-boot.log; ad5x-kernel; /data/ad5x/bench/ad5x-uboot-flash --status'
   ```

   It passed when all of these hold:
   - CPSPR `0x00000000`: U-Boot proper writes 0 just before it jumps to a
     kernel (`board_preboot_os`); Kiln's SPL starting a slot leaves
     `0x00004B68` (step 3), and a `0x4B6_` value with bit 2 set
     (`0x00004B6D` after one try) means U-Boot proper failed this start
     and the SPL booted the slot itself: stop, `--status`, the log;
   - the command line has `ad5x.uboot=1` (only U-Boot adds it),
     `root=/dev/mmcblk0p4`, `ad5x.kernel=own` and `ad5x.wdt=30` (U-Boot
     left the watchdog running into Kiln's kernel);
   - `uname -r` is 6.6 (7.3 with mainline on), the boot log says "own
     kernel started directly" and no "chainload own kernel" (no 5.10
     pass), `last-ok` ends in `direct ok`;
   - the boot log says `uboot: start confirmed, state cleared (read back
     as zeros, ...)` and `--status` says "U-Boot's state (ota 0x90000):
     empty" and "from 0xA400 Kiln's U-Boot (first-mib-uboot.img)";
   - `ad5x-kernel` shows "boot loader: Kiln's U-Boot" and no "U-Boot
     failed" line.

7. The cold-start loop (below), counting on from step 3: cycles 11 to 30.
   Each one as the step-6 checks, in short: CPSPR `0x00000000`,
   `ad5x.uboot=1`, the expected kernel, U-Boot's state empty once
   start-up has finished. In the laptop loop, `seq 11 30` and this log
   line instead of the one there:

   ```
   	echo "$n $(date -Is) $(( $(date +%s) - t0 ))s ${ok:+ready} $(ssh root@$P 'for i in $(seq 60); do [ -f /run/ad5x-booted ] && break; sleep 2; done; devmem 0x10000034 32; grep -o "ad5x.uboot=1" /proc/cmdline; uname -r; dd if=/dev/mmcblk0p5 bs=512 skip=1152 count=1 2>/dev/null | tr -d "\000" | wc -c' 2>/dev/null | tr '\n' ' ')" | tee -a cold-starts.log
   ```

   Pass: 20 of 20 (30 in all), each ending in `0x00000000 ad5x.uboot=1
   <kernel> 0` (the last 0: the state sector holds nothing). A `0x4B__`
   value or a missing `ad5x.uboot=1` is a start without U-Boot: stop. A
   non-zero last field means S99 didn't confirm: `/run/ad5x-boot.log`,
   stop before the second one (two unconfirmed 6.6 starts and U-Boot
   records 6.6 as failed).

### Fallback drills

Only after step 7 passed, idle, one drill at a time, each from a normal
start (`ad5x-kernel` without "U-Boot failed", U-Boot's state empty). A
drill changes nothing on the eMMC but U-Boot's sectors in `ota` (and the
boot flag, where U-Boot itself writes it): slot B, its rootfs and the
first MiB stay as they are. Stop at anything not listed as expected:
power-cycle once, read `--status`, `ad5x-kernel` and `/run/ad5x-boot.log`,
and go back to step 3's state ("Going back", below) if the printer doesn't
start normally after `ad5x-kernel retry`.

**Drill 1: 7.3 doesn't finish starting, U-Boot falls back to 6.6.**
Nothing in the system can make 7.3 itself unbootable without changing
rootfs2 (the kernels are inside the SquashFS), and a command-line option
reaches both kernels. So the drill gives U-Boot what such a start leaves
behind: U-Boot writes "tries 1, kernel 73, release ..." before it jumps to
7.3, and a 7.3 that hangs, panics (`panic=10`) or is reset by the watchdog
before `S99ad5x-booted` leaves it there. `--drill 73` writes exactly that
sector (U-Boot's format, CRC included) and nothing else.

1. `ssh root@$P 'ad5x-kernel mainline on; reboot'`; after the
   start: `uname -r` 7.3, `ad5x.uboot=1`.
2. `ssh root@$P /data/ad5x/bench/ad5x-uboot-flash --drill 73`
   (dry run: shows the sector and what follows), then `--drill 73 --yes`,
   then `ssh root@$P reboot`.
3. Expected: back within 5 minutes on 6.6 (`uname -r`), `ad5x.uboot=1`;
   `ad5x-kernel` says "U-Boot failed: mainline 7.3.4-ad5x (6.6 until
   ad5x-kernel retry)" and "U-Boot fallbacks: N; last: mainline kernel
   7.3.4-ad5x did not finish starting; 6.6 until ad5x-kernel retry";
   `/run/ad5x-boot.log` has the same in a `uboot records:` line and
   `uboot: start confirmed`; `--status` shows the records and an empty
   state. Another reboot stays on 6.6.
4. Undo: `ssh root@$P 'ad5x-kernel retry; reboot'` ("Kiln's
   U-Boot's records: cleared"): 7.3 again, no "U-Boot failed" line. To
   leave mainline off again: `ad5x-kernel mainline off; reboot`.

Stop if it comes back on 7.3 (U-Boot didn't take the state: keep
`--status` and the logs) or doesn't come back.

**Drill 2: the watchdog after start-up.** U-Boot left the watchdog
running into the kernel (`ad5x.wdt=30`), the kernel's driver took it over
and `S05ad5x-watchdog` feeds it every 10 s with a 120 s timeout. Kill the
feeder without the magic close:

1. Check first: `ssh root@$P 'grep -o ad5x.wdt=30 /proc/cmdline; ls /data/ad5x/watchdog.disable; cat /run/ad5x-watchdog.pid'`:
   `ad5x.wdt=30`, no such file, a pid.
2. `ssh root@$P 'kill -9 $(cat /run/ad5x-watchdog.pid)'`; note
   the time.
3. Expected: the printer resets by itself about 120 s later (SSH and
   Fluidd drop, the screen goes dark, the start begins), and comes back
   through SPL and U-Boot as a normal start: CPSPR `0x00000000` (step
   5's U-Boot: `0x00005511`), `ad5x.uboot=1`, the same kernel, no "U-Boot
   failed" line (the last start had been confirmed, so U-Boot counts
   nothing against it). A watchdog reset is not a power cycle: CPSPR
   after it is U-Boot's last write, which the SPL treats as a fresh
   start.
4. Undo: nothing. Stop if nothing happens within 180 s: start the feeder
   again (`/etc/init.d/S05ad5x-watchdog start`) and note it; the watchdog
   isn't running as `u-boot/README.md` ("Watchdog") says.

U-Boot's own watchdog windows (30 s from the jump until the kernel's
driver probes, 120 s inside U-Boot) can't be drilled from the main OS:
that needs a kernel that hangs early or the stop key over the DEBUG
header (`docs/serial-console.md`).

**Drill 3: 6.6 fails too, U-Boot starts the recovery OS.** Needs step
5's U-Boot (patch 0026; step 4's still had a stock-kernel rung between 6.6
and the recovery OS, which this drill showed there). With mainline off
(`ad5x-kernel mainline off; reboot`): `--drill 66 --yes` (tries 2, kernel
66), then `reboot`. Expected: U-Boot records 6.6 as failed (`failed-own`),
points the flag at slot A, clears its state and starts the recovery OS:
the recovery screen; over SSH `uname -r` 6.6 (Kiln's 6.6 in p1, step 5),
`/proc/cmdline` with `root=/dev/mmcblk0p2 ad5x.uboot=1 ad5x.kernel=own
panic=10 loglevel=5` and no `ad5x.wdt`, CPSPR `0x00005503`,
`head -c 11 /dev/mmcblk0p5` `ota:kernel`, and U-Boot's records (`dd
if=/dev/mmcblk0p5 bs=512 skip=1153 count=1 | strings`) say "own kernel
6.6... did not finish starting, 2 in a row: recovery OS". Back: "Boot main
OS" on the touch screen (or `ssh root@$P ad5x-boot-main`): it
says "U-Boot's state and records cleared (Boot main OS)", and the main OS
starts on 6.6 again (CPSPR `0x00005511`), `ad5x-kernel` without a "U-Boot
failed" line, `/data/ad5x/kernel/history` with the "recovery OS: U-Boot's
last fallback was: ..." line. With mainline on, U-Boot goes to 7.3
instead, as `--drill 66` says.

**Drill 4: a start-up that hangs.** Started by U-Boot, `S05ad5x-watchdog`
stops feeding when start-up hasn't finished (`/run/ad5x-booted`)
`START_LIMIT` seconds after boot (900, in the read-only
`/usr/lib/ad5x/watchdog.conf`). The drill runs that guard by hand with a
60 s limit on a printer that has finished starting, so nothing in the
image changes:

```
ssh root@$P 'mkdir -p /tmp/wl && cp /usr/lib/ad5x/* /tmp/wl/ 2>/dev/null;
	sed -i "s/^START_LIMIT=.*/START_LIMIT=60/" /tmp/wl/watchdog.conf;
	mv /run/ad5x-booted /run/ad5x-booted.drill;
	AD5X_LIB=/tmp/wl setsid /etc/init.d/S05ad5x-watchdog guard </dev/null >/dev/console 2>&1 &'
```

Expected: within 30 s the console says "start-up not finished ... feeder
stopped", the boot trace (`ad5x-bootlog` in `ota`) gets "watchdog:
start-up unfinished after N s, feeder stopped", and the printer resets
about 120 s later and starts normally through U-Boot (the last start had
been confirmed, so nothing is counted). Idle only: the guard waits while
Klipper prints. Stop: `mv /run/ad5x-booted.drill /run/ad5x-booted` before
the 30 s pass (the guard then ends by itself).

`--drill clear --yes` zeroes a drill's state again if you change your
mind before the reboot.

**Drill 5: nothing started, the boot ROM's USB mode (patch 0028).** When
its four attempts found nothing to start, Kiln's SPL asks the boot ROM
for its USB mode (CPM_SLPC = 0x42575302, a watchdog reset) instead of
stopping; a power cycle tries the eMMC again (`u-boot/README.md`,
"Tries"). Laptop-checked (`test_ad5x_start.py`); this drill checks the
part only the chip can tell: that the ROM takes the request after the
SPL's own watchdog reset, and that a power cycle from there starts
normally.

Needs: an SPL with patch 0028 on the printer. The SPL from steps 3-5 is
older (it stops). Putting a new build on is "Going back" to Flashforge's
SPL (below), then steps 3 and 4 with the new build's `first-mib.img` and
`first-mib-uboot.img`, 10 cold starts after each. Check:
`ssh root@$P 'dd if=/dev/mmcblk0 bs=512 skip=34 count=48 2>/dev/null | grep -c "boot ROM USB mode"'`
says `1`. Also J28 wired to the laptop (Contingency, step 1; the udev
rule from `u-boot/USB-BOOT.md`), the console logged (`tio -L`), the smart
plug reachable, the printer idle on the main OS with start-up finished.

5a. **The request, nothing written.** The drill puts into CPSPR what
the fourth failed attempt leaves there and lets the watchdog reset the
board (a `reboot` wouldn't do: Linux's restart writes 0x3535 to CPSPR
first):

1. Checks as drill 2, step 1 (`ad5x.wdt=30`, no `watchdog.disable`, a
   feeder pid); on the laptop `lsusb -d a108:eaef` shows nothing.
2. `0x4b53` = attempt 3 (the fourth), phase 5 (loading the slot), slot
   A; CPSPR needs its unlock word in CPSPPR (`0x10000038`) around the
   write:

   ```
   ssh root@$P 'devmem 0x10000038 32 0x5a5a; devmem 0x10000034 32 0x4b53; devmem 0x10000038 32 0; devmem 0x10000034 32'
   ```

   It must read back `0x00004B53`; if not, stop (nothing else changed;
   the next start is a fresh one).
3. `ssh root@$P 'kill -9 $(cat /run/ad5x-watchdog.pid)'`; note the time.
4. Expected about 120 s later, on the console: `U-Boot SPL 2026.10
   (...)`, `SPL: boot ROM`, `SPL: nothing started after 4 attempts (last
   0x4b53): boot ROM USB mode (J28); power-cycle to try the eMMC again`,
   then nothing more. On the laptop within a few seconds: `lsusb -d
   a108:eaef`, and `u-boot/tools/ad5x_usbboot.py info` answers (log its
   output). The printer is off the network.
   - If instead, right after it, a second banner and `SPL: the boot
     ROM started the eMMC, not its USB mode (0x4c53, SLPC cleared):
     stopped, power cycle to retry`: the ROM ignored the request after
     this reset. Note it, then step 5; patch 0028 then only adds one
     reset before the old stop.
   - Stop and power-cycle if nothing happens within 180 s (the feeder
     isn't what drill 2 found).
5. **Power cycle** (plug off 10 s, on). Expected: a normal start through
   SPL and U-Boot, no `started over USB`, no `attempt` line (the marker
   `0x4c53` without the request is a fresh start); in the main OS CPSPR
   `0x00005511`, `ad5x.uboot=1`, the same kernel, `ad5x-kernel` without
   "U-Boot failed".

5b. **A start over USB from there.** Steps 1-4 of 5a again, then from
the USB mode, with this build's `spl-usb.bin`:
`u-boot/tools/ad5x_usbboot.py run-spl $D/spl-usb.bin`. Expected:
`SPL: started over USB (soft entry, SLPC cleared); scratch pad 0x4c53
not counted: a fresh start` (without "(soft entry ...)" if the ROM
clears CPM_SLPC itself: note which, `USB-BOOT.md` asks), the DDR test
good, then the main OS as after a cold start. One power cycle after it,
to finish on a normal start.

5c. **Optional, really nothing to start** (destructive; only with the
USBCloner restore of the Contingency ready, and after 5a passed). Under
Kiln's SPL and U-Boot, zeroed kernel slots alone are not "nothing": U-Boot
starts the main OS from rootfs2, and alexshev86's test 4 (#68) applies to
the SPL's own fallback to the slots. So: save, then zero, the sector of
U-Boot's uImage header (82, 0xA400: the SPL then says "no U-Boot at
0xA400" and boots the slots itself) and the first sector of each kernel
slot (p1, LBA 0x800; p3, LBA 0x36800):

```
ssh root@$P 'cd /data/ad5x/bench && dd if=/dev/mmcblk0 bs=1M count=1 of=first-mib-now.img && for l in 2048 223232; do dd if=/dev/mmcblk0 bs=512 skip=$l count=1 of=sector-$l.bin; done; sha256sum first-mib-now.img sector-*.bin'
scp -O "root@$P:/data/ad5x/bench/first-mib-now.img" "root@$P:/data/ad5x/bench/sector-*.bin" $BK/
sha256sum $BK/first-mib-now.img $BK/sector-*.bin    # the same as on the printer
# then, idle, and only then:
ssh root@$P 'sync; for l in 82 2048 223232; do dd if=/dev/zero of=/dev/mmcblk0 bs=512 seek=$l count=1 conv=fsync,notrunc; done; reboot'
```

Expected on the console: `no U-Boot at 0xA400: the slot, as the stock
SPL`, then four attempts (slot B, slot A forced, slot B, slot A: each
`SPL: no good uImage in the slot; attempt N of 4 failed`), then the USB
mode line as in 5a, `a108:eaef` on the laptop within about a minute. A power cycle gives the same again (the eMMC tried from attempt
0, still nothing). Restore over J28 only (no system starts): USBCloner
(Contingency, step 3) with three entries: `first-mib-now.img` (this
printer's first MiB from just before the drill) at `0x0`, the saved
`sector-2048.bin` at `0x100000` and `sector-223232.bin` at `0x6D00000`
(writes at those offsets with USBCloner are untried; the first MiB at 0x0
is proven), then a power cycle: a normal start, and `ad5x-uboot-flash
--status` as after step 4.
Without that restore ready, don't run 5c: 5a and 5b check the same SPL
code (the decision depends only on what CPSPR and CPM_SLPC hold as the
SPL starts) without writing anything.

### Going back

- **To step 3's state** (Kiln's SPL, Flashforge's U-Boot at 0xA400):
  `ssh root@$P /data/ad5x/bench/ad5x-uboot-flash --restore --yes`,
  then one power cycle. After it: CPSPR `0x00004B68`, no `ad5x.uboot=1`,
  `ad5x-uboot-flash --status` says "from 0xA400 Flashforge's U-Boot
  (boot.img)". With 5.10 still in kernel2 (step 4) the boot log says
  "chainload own kernel"; with Kiln's 6.6 there (step 5) Kiln's SPL starts
  it directly: "own kernel started directly".
- **Fully to Flashforge** (also Flashforge's SPL): the U-Boot range first,
  as above, then `/data/ad5x/bench/ad5x-spl-flash --restore --yes` (it
  refuses while Kiln's U-Boot is at 0xA400). It puts the saved stock kernel
  (`/data/ad5x/stock/kernel.img`, sha256 as `SHA256SUMS` there) back into
  every slot that doesn't hold Flashforge's 5.10 first (header last, read
  back), then Flashforge's SPL: it never goes back over Kiln's 6.6. Then
  one power cycle. After it: CPSPR holds no `0x4B__` value,
  `ad5x-spl-flash --status` says `stock`, both slots name `Linux-5.10...`.
  U-Boot's sectors in `ota` may stay (Flashforge's SPL never reads them,
  `S99ad5x-booted` only with `ad5x.uboot=1`); to remove them, step 2's
  "After the test" has the `dd` for 0x80000-0x903FF.
- **If the printer doesn't start after the write**: Kiln's SPL should
  fall back to the slot by itself (above); give it 5 minutes and one more
  power cycle, then `--restore --yes` from the main OS it starts. If no
  system comes up, the contingency below (J28), as for step 3.

## Step 5: no Flashforge kernel left (the recovery OS on Kiln's 6.6)

U-Boot patches 0026-0027 and the v1-step5 and v1-no510 userspace
(`u-boot/README.md`, "Boot rules" and "Userspace and kernel changes U-Boot
needs"). With Kiln's SPL in the first MiB no Flashforge kernel is left on
the printer's slots and nothing can start one:

- U-Boot's order is 7.3 -> 6.6 -> the recovery OS, and it starts the
  recovery OS only from Kiln's 6.6 in p1 (a 5.10 there: slot A not
  startable);
- the main OS puts its own 6.6 into p1 and p3 once Kiln's SPL is in
  (`S99ad5x-update-recovery`, `/data/ad5x/recovery/update.log`), whoever
  started it; never 5.10 again while Kiln's SPL is there;
- Kiln's SPL alone (U-Boot proper missing or failing) then starts 6.6
  directly from the slot, with the stock command line (no
  `ad5x.uboot=1`): CPSPR `0x00004B68`;
- `S01ad5x-tryboot` leaves the flag on slot B under U-Boot, `S00ad5x-kernel`
  never chainloads, `S05ad5x-watchdog` resets a start-up that hasn't
  finished after 900 s;
- "Boot main OS" and an install in the recovery OS clear U-Boot's state
  and records; `ad5x-restore-stock` leads to the recovery OS's Return to
  Flashforge firmware (`ad5x-return-stock`); `ad5x-spl-flash --restore`
  puts the saved 5.10 back into both slots before Flashforge's SPL;
- U-Boot leaves `0x55NK` in CPSPR (K 1 = 6.6, 2 = 7.3, 3 = recovery OS;
  N the start count): `0x00005511` is a normal 6.6 start.

The new U-Boot is built with step 3's `SOURCE_DATE_EPOCH`, so the SPL and
`first-mib.img` stay byte for byte what is on the printer (`fe93be50...`):

```
S3=~/workspace/u-boot-ad5x-build-e66ec47/out/dist
SOURCE_DATE_EPOCH=$(sed -n 's/^SOURCE_DATE_EPOCH=//p' $S3/report.txt) \
WORK=~/workspace/u-boot-ad5x-build-step5 \
FIRST_MIB_DUMP=$BK/boot.img u-boot/build.sh --container
D=~/workspace/u-boot-ad5x-build-step5/out/dist
cmp $D/first-mib.img $S3/first-mib.img && echo "same SPL"
```

Each numbered step that writes is its own approval; the rest is read
only.

0. Read only, first: the saved stock kernel, which going back needs
   (`ad5x-spl-flash --restore`): `ssh root@$P 'cd
   /data/ad5x/stock && sha256sum -c SHA256SUMS && head -c 64 kernel.img |
   strings'` says `kernel.img: OK` and `Linux-5.10.186+`. Copy it off:
   `scp -O root@$P:/data/ad5x/stock/{kernel.img,SHA256SUMS}
   $BK/`. Also save both slots' kernels
   as they are now: `ssh root@$P 'cat /dev/mmcblk0p1' >
   p1-before-step5.img`, the same for p3.
1. **Write: install a builder test build of v1-no510** (by hand, as in
   step 1: `ad5x-update --reboot ZIP SHA256`), still on step 4's U-Boot.
   After its start-up `S99ad5x-update-recovery` writes, in the
   background, the new recovery OS into p2, Kiln's 6.6 into p1
   (`--install-recovery`) and Kiln's 6.6 into p3 (`--kernel2`): all part
   of this step. Check: the boot log has "tryboot: started by Kiln's
   U-Boot; boot flag stays on slot B" and "uboot: start confirmed", the
   flag reads `ota:kernel2` all through start-up,
   `/data/ad5x/recovery/update.log` ends in "OK, recovery OS ..." and
   "OK, Kiln's 6.6 in kernel2", and `head -c 64 /dev/mmcblk0p1 | strings`
   and the same for `/dev/mmcblk0p3` name `Linux-6.6-ad5x`. Reboot once
   more: the log adds nothing (both slots already hold it).
2. **Write: start the recovery OS once** (`ad5x-boot-recovery`, or the
   touch screen's Boot into recovery). Step 4's U-Boot starts it from p1,
   now Kiln's 6.6. Check: the recovery screen (logo, taps reach their
   buttons, Back top left), SSH, `uname -r` 6.6, `/proc/cmdline` with
   `root=/dev/mmcblk0p2 ad5x.uboot=1`, Ethernet and Wi-Fi addresses,
   `/etc/init.d/S05ad5x-watchdog status` "fed". This is the gate "the
   recovery OS on 6.6 boots under Kiln's loader".
3. **Write: "Boot main OS"** on the touch screen. It writes the flag and
   clears U-Boot's state and records ("U-Boot's state and records
   cleared (Boot main OS)" in the job's output). The main OS comes back
   on its usual kernel.
4. **Write: `ad5x-uboot-flash --restore --yes`** (step 4's U-Boot out,
   Flashforge's bytes back at 0xA400; the tool can't replace one Kiln
   U-Boot with another directly).
5. **Power cycle** (the HA plug): the drill "U-Boot gone". Kiln's SPL
   boots kernel2, now Kiln's 6.6, directly. Check: CPSPR `0x00004B68`,
   `/proc/cmdline` the stock one (`console=ttyS0,115200n8 loglevel=8 ...
   root=/dev/mmcblk0p4 ... lpj=11935744`, no `ad5x.uboot=1`, no
   `ad5x.kernel=own`), `uname -r` 6.6, the boot log "own kernel started
   directly" and no "chainload", the flag `ota:kernel` during start-up
   (try once, as on the chain) and `ota:kernel2` after, Klipper ready,
   `/data/ad5x/recovery/update.log` adds nothing (6.6 stays in both
   slots).
6. **Write: copy step 5's files** to `/data/ad5x/bench/step5/` (as in
   step 4, item 3, from `$D`), then dry run `ad5x-uboot-flash
   /data/ad5x/bench/step5` (exit 2, every line ok, "kernel: Kiln's 6.6"
   and "kernel2: Kiln's 6.6", sectors 82-769).
7. **Write: `ad5x-uboot-flash --yes /data/ad5x/bench/step5`**, and copy
   the log off.
8. **Power cycle.** Check: CPSPR `0x00005511`, `ad5x.uboot=1`, 6.6 (or
   7.3 with mainline on: `0x00005512`), "own kernel started directly",
   "uboot: start confirmed", the flag `ota:kernel2` during start-up too.
9. Cold starts with the HA plug, 10 or more: each `0x00005511
   ad5x.uboot=1 <kernel> 0` in the step-4 loop's log line.
10. **Writes (one each): the drills**: drill 1 (7.3 -> 6.6), drill 3
    (6.6 -> the recovery OS on 6.6: CPSPR `0x00005503`, back with "Boot
    main OS"), drill 4 (the start-up limit), drill 2 (the watchdog) again
    if wanted. Each from a normal start, one at a time.
11. Read only: `ad5x-restore-stock --dry-run` on the main OS (before
    v1-revert) says
    "starts only Kiln OS: put Flashforge's boot loader back first", and
    `ad5x-spl-flash --restore` (dry run, after `ad5x-uboot-flash
    --restore` only) lists the saved stock kernel going into both slots
    before Flashforge's SPL.

Going back: "Going back" above. `ad5x-uboot-flash --restore --yes` and a
power cycle give step 3's state with Kiln's 6.6 in both slots (Kiln's SPL
starts it directly); fully to Flashforge, `ad5x-spl-flash --restore --yes`
puts the saved 5.10 back into both slots first, then Flashforge's SPL.


## The cold-start loop (Home Assistant smart plug)

Our bench's plug is a Home Assistant switch (`PLUG` below). The scripts here
don't switch it: run the loop from the laptop (or by hand in Home
Assistant), one cycle at a time, and stop at the first failure.

Each cycle:

1. **Only when idle.** `curl -s 'http://$P:7125/printer/objects/query?print_stats'`
   says `standby`, `complete`, `cancelled` or `error` (not `printing`,
   not `paused`), and start-up has finished:
   `ssh root@$P 'test -f /run/ad5x-booted && head -c 11 /dev/mmcblk0p5'`
   says `ota:kernel2`. Before that the flag is on slot A (the main OS's
   try-once), and a power cut would start the recovery OS: not a failure
   of the SPL, but not the test either.
2. `ssh root@$P sync` (the power cut is the test; the files on
   `/data` needn't suffer for it).
3. Plug off, wait 10 s (long enough for a real cold start), plug on.
4. Poll `curl -s -m 5 http://$P:7125/server/info` every 5 s
   until `"klippy_state": "ready"`, at most 300 s.
5. Log one line: cycle, date and time, seconds to SSH and to Klipper
   ready, CPSPR (`ssh ... devmem 0x10000034 32`), ok or timeout.
6. Wait about a minute (idle) before the next cycle.

On a timeout: stop the loop; one more power cycle by hand to see whether
it was transient; then the contingency. Never cycle while a print or an
update runs.

A minimal laptop loop (a Home Assistant long-lived token in `HA_TOKEN`,
`HA` its URL, `PLUG` the plug's entity, e.g. `switch.smart_plug`):

```
ha() { curl -fsS -X POST -H "Authorization: Bearer $HA_TOKEN" -H 'Content-Type: application/json' \
	-d "{\"entity_id\": \"$PLUG\"}" "$HA/api/services/switch/turn_$1" >/dev/null; }
for n in $(seq 1 20); do
	curl -s 'http://$P:7125/printer/objects/query?print_stats' | grep -Eq '"state": *"(standby|complete|cancelled|error)"' || { echo "$n: not idle, stop"; break; }
	[ "$(ssh root@$P 'test -f /run/ad5x-booted && head -c 11 /dev/mmcblk0p5')" = ota:kernel2 ] || { echo "$n: start-up not finished, stop"; break; }
	ssh root@$P sync; ha off; sleep 10; ha on; t0=$(date +%s); ok=
	while [ $(( $(date +%s) - t0 )) -lt 300 ]; do
		curl -s -m 5 http://$P:7125/server/info | grep -q '"klippy_state": *"ready"' && { ok=1; break; }
		sleep 5
	done
	echo "$n $(date -Is) $(( $(date +%s) - t0 ))s ${ok:+ready} $(ssh root@$P devmem 0x10000034 32 2>/dev/null)" | tee -a cold-starts.log
	[ -n "$ok" ] || { echo "$n: timeout, stop"; break; }
	sleep 60
done
```

## Contingency: J28 + K4 + USBCloner

When the printer doesn't start after the SPL write and power cycles don't
help (bench recovery, not a gate; `docs/boot-slots.md` "J28" and
"Recovery with USBCloner", `u-boot/USB-BOOT.md`):

1. Open the printer; J28 (the white 5-pin `USB` connector) to the laptop
   or a Windows PC: D+, D-, GND; measure `5V` first and never feed a
   second supply.
2. Power the printer off and on fully (a reboot isn't enough) and check
   whether `a108:eaef` appears: with no valid SPL header (a write cut
   short while sector 34 was zero) the boot ROM is in USB mode by itself
   (alexshev86, #68). With an SPL that has patch 0028 and finds nothing
   to start, it appears after the SPL's four attempts (drill 5; up to
   about three minutes when something hangs). If it doesn't appear (an
   SPL that starts and then hangs, or an older SPL that stops), close K4
   (boot_sel 101 -> 111) so that the boot ROM goes to USB mode at
   power-on even with an SPL on the eMMC.
3. Proven path (alexshev86, #66): Ingenic USBCloner 2.5.36.1 with
   `x2600_mmc0_ddr3_linux.cfg` (2.5.48 or later with
   `x2600h_mmc0_ddr3l_linux.cfg` for large reads), one POLICY entry:
   `FILE`, `MMC0`, offset `0x0`, the full backup image; Force erase none;
   Readback and CRC check on; 15-40 minutes, power and USB untouched.
   Proven too (alexshev86, #68): USBCloner 2.5.50, one entry `type=0`,
   `ops="6,2,0"` (MMC0), offset `0x0`, this printer's own 1 MiB `boot.img`,
   `force_erase=0`, `force_reset=0`, `cpu_info_length=5`; then a full
   power cycle. Only ever this printer's own first MiB (the GPTs differ).
   Afterwards 0x4480-0x4483 read `84 00 84 00` (USBCloner's DDR type,
   unused by both SPLs).
4. Untried alternative without USBCloner: start Kiln's SPL over USB
   (`u-boot/tools/ad5x_usbboot.py run-spl spl-usb.bin`); it boots the slot
   from the eMMC read-only, and the main OS can then run
   `/data/ad5x/bench/ad5x-spl-flash --restore --yes`.
5. Open K4 again (if it was closed), power-cycle.
