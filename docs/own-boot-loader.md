# Kiln's own boot loader (opt-in)

Every Kiln OS printer starts the way Flashforge built it: Flashforge's
boot loader (its SPL, a small first stage; Flashforge's U-Boot is on the
eMMC but never runs) starts Flashforge's Linux kernel, which then hands over to Kiln OS's own
kernel. That keeps working and nothing changes it by itself.

Kiln OS also carries a boot loader of its own: **Kiln's SPL** and
**mainline U-Boot** with Kiln's patches (source in `u-boot/`; the port to
the AD5X is jolting's work). With it, no Flashforge code runs when the
printer starts:

- Kiln's SPL sets up the memory and starts Kiln's U-Boot;
- U-Boot starts Kiln OS's kernel directly (6.6, or the opt-in 7.3) and
  watches whether the start finishes;
- if a kernel fails to start, it falls back by itself: 7.3, then 6.6, then
  the recovery OS (which then runs on Kiln's 6.6 too);
- if U-Boot itself fails, Kiln's SPL starts Kiln's 6.6 on its own.

**Read the risk below before you install it.** It is installed only when
you ask for it, from the recovery OS, and only on printers whose stock
boot loader is known to be the one Kiln's SPL was made for. The same Kiln
OS update goes to every printer either way.

## The risk, plainly

The boot loader lives in the first megabyte of the printer's memory
(eMMC). The installer writes it in an order where every step in between
still starts a system (except during the SPL write itself, a few
milliseconds, when a power cut leaves the printer in USB boot mode: see
"If nothing starts"), reads everything back, and can carry on after a
power cut. Still:

- **If Kiln's SPL doesn't start on your printer, the printer doesn't
  start at all** (black screen, no network), and no button or update can
  fix that. The only way back that has been proven so far needs the printer
  opened: the white 5-pin **J28** USB connector on the mainboard, a USB
  cable and Ingenic's USB tool (see "If the printer doesn't start"
  below). When Kiln's SPL runs but finds nothing it can start, it puts
  the chip into USB mode by itself after four tries; an SPL that doesn't
  run at all, or hangs before it can reset, also needs the K4 pads
  shorted.
- It has been proven on one printer so far (the developer's, with the
  cold-start and fallback tests in `tools/bench/README.md`). A second board
  is known to have byte for byte the same stock boot loader.
- Don't switch the printer off while it installs (under a minute).

If any of that worries you, don't install it: Kiln OS works the same on
Flashforge's boot loader.

## Is my printer one of the known boards?

The installer checks this itself and offers the install only on a known
board. To check by hand (and to help: every result, yes or no, tells us
whether other board versions exist), paste this into an SSH session on
the printer (zMod, Kiln OS, or stock with root). It only reads, and prints
hashes:

```sh
D=${D:-/dev/mmcblk0}
h() { dd if=$D bs=$1 skip=$2 count=$3 2>/dev/null | sha256sum | cut -c1-16; }
spl=$( { dd if=$D bs=128 skip=136 count=1; printf '\000\000\000\000'
  dd if=$D bs=4 skip=4385 count=95; dd if=$D bs=512 skip=35 count=47; } 2>/dev/null | sha256sum | cut -c1-16)
ddr=$(h 1 34872 188)
echo "length: $(dd if=$D bs=4 skip=1 count=1 2>/dev/null | od -An -tu4 | tr -d ' ')"
echo "spl:    $spl"
echo "uboot:  $(h 512 82 1966)"
echo "ddr:    $ddr $(dd if=$D bs=1 skip=34872 count=12 2>/dev/null)"
echo "banner: $(dd if=$D bs=512 skip=34 count=48 2>/dev/null | tr -cs 'A-Za-z0-9 :().-' '\n' | grep -m1 'U-Boot SPL')"
echo "ram:    MemTotal $(awk '$1 == "MemTotal:" { print $2 }' /proc/meminfo) kB; $(tr ' ' '\n' < /proc/cmdline | grep '^mem=' | tr '\n' ' ')"
echo "parts:  $(cat /sys/block/mmcblk0/mmcblk0p*/start 2>/dev/null | tr '\n' ' ')"
echo "emmc:   $(cat /sys/block/mmcblk0/device/name /sys/block/mmcblk0/size 2>/dev/null | tr '\n' ' ')"
[ "$spl $ddr" = "f7b9d763c1e83af8 61b7ee909c0baa50" ] && echo "match:  yes (tested boards)" || echo "match:  no, please post this"
```

In the recovery OS, `ad5x-bootloader-install --fingerprint` prints the same
lines, plus `chip:` (X2600H, X2600E-class or unknown, from the `ram:`
values). It finds the DDR table by its name rather than at 34872: the
Nov 2025 stock SPL (banner `2013.07-00437`) is one image for X2600H and
X2600E boards with a table per chip (`X2600H-DDR3L`, `X2600E-DDR3`, ...),
so there the `ddr:` line is the table for this chip and a `tables:` line
lists them all. That build isn't on the list. On Kiln's boot loader already, put `D=/data/ad5x/stock/boot.img` on
a line of its own first: it then reads the saved stock copy instead.
`ad5x-bootloader-install --fingerprint` does that by itself, and after a
wipe of `/data` it reads the copy in usershare's `kiln-stock-backup/` (or
on a USB stick that is plugged in) instead.

`spl` is the hash of the stock SPL (0x4400-0xA3FF) with 4 bytes at 0x4480
read as zeros. Ingenic's USBCloner writes its DDR type (`84 00 84 00`)
there whenever it writes the eMMC from its start, and no SPL reads those
bytes, so a board that was restored over USB keeps its fingerprint. On
other boards the bytes are zeros anyway, and the hash is the same as the
plain hash of the range that older versions of this snippet printed.

Known boards so far (`spl` and `ddr` above):

| spl | ddr | DDR chip | Boards |
|---|---|---|---|
| `f7b9d763c1e83af8` | `61b7ee909c0baa50` | W634GU6QG-11 | the developer's (where it was proven) and alexshev86's (the same by its dump) |

The full output on those boards (from before the `ram:` line was added):

```
length: 17920
spl:    f7b9d763c1e83af8
uboot:  07d3d653be88bdec
ddr:    61b7ee909c0baa50 W634GU6QG-11
banner: U-Boot SPL 2013.07-00190-g82c76c87e-dirty (Sep 26 2024 - 23:34:47)
parts:  2048 18432 223232 239616 444416 446464 2543616
emmc:   58A398 15269888
match:  yes (tested boards)
```

**Please post your output** (it is only hashes, offsets and names) in
[issue #68](https://github.com/djvalic/kiln-os/issues/68). Boards are
added to the list as they are confirmed.

Printers with SD-NAND instead of eMMC are not supported: Kiln's SPL reads
only eMMC.

## Before you start

- Kiln OS up to date in the main slot, and started at least once since
  the update (it brings the recovery OS that carries the installer up to
  date).
- On the recovery screen: **Restore stock** > **Save files to USB**, and
  keep that stick. It holds this printer's own stock boot loader
  (`boot.img`) and Flashforge's system, which is what going back needs if
  the printer's own copies are ever lost. A full eMMC backup
  (`docs/emmc-backup.md`) is better still.
- The rescue stick: each release has `kiln-os-VERSION-rescue.zip`, a
  computer's tools to check, back up and repair the eMMC when nothing
  starts, with the files that start Kiln's U-Boot over USB
  ([emmc-repair.md](emmc-repair.md)). Download it and keep it with the
  stick above.

## Install from the recovery screen

The recovery screen shows the button on every printer whose board is on
the allowlist and doesn't have Kiln's boot loader yet; nothing has to be
set up over SSH first (before v1.0.0-rc7 it needed
`/data/ad5x/bootloader-offer.enable`; that file does nothing now). An
install that stopped part-way is offered to finish. The SSH commands below
work too.

The main OS's touch screen says once that this exists, from the third
complete start of Kiln OS on: "Kiln OS has its own boot loader for this
printer. To install it: Settings > System > Boot into recovery > Reboot /
Power > Install Kiln's boot loader. Read the boot loader
guide first; it explains the risk and the rescue stick", with this page's
address. Only on a printer the recovery screen would offer it on (a known
board, an X2600H, eMMC, Kiln's boot loader images in the recovery OS),
only at idle (not during the setup wizard, not while a print runs), and
never again once closed (`/data/ad5x/bootloader-notice/install-dismissed`;
the same script as the update notice below, "The main OS tells you").

1. Boot into recovery (touch screen: Settings > System > Boot into
   recovery).
2. Tap **Reboot / Power**. On a known board without Kiln's boot loader
   there is a button **Install Kiln's boot loader**. It
   isn't there on other boards.
3. The page checks everything first and shows the result. Nothing is
   written yet.
4. Tap **Install** and confirm twice. Wait until the screen says it is
   done.
5. Tap **Reboot**. The printer starts this recovery screen again, now
   through Kiln's boot loader, and the page opens by itself with the
   result on top: "Done: Kiln's boot loader is installed and started this
   recovery." Under it: "Kiln's boot loader is installed and up to date",
   and no Install button. The page waits for the recovery OS's start-up
   actions to finish before it checks (a few seconds). If the start didn't
   come through Kiln's U-Boot (Kiln's SPL started the system itself), the
   page says so: the printer works and **Boot main OS** starts Kiln OS;
   please post it, with what **Check** shows, in
   [issue #68](https://github.com/djvalic/kiln-os/issues/68). Then **Boot
   main OS**.

If the power goes off during the install, the recovery screen comes back
(the boot flag stays on the recovery OS all through the install), the page
opens by itself and **Continue** finishes from where it stopped.

## Install over SSH

In the recovery OS (`ssh root@<printer>` while the recovery screen shows):

```
ad5x-bootloader-install            # every check, the fingerprint, the plan; writes nothing
ad5x-bootloader-install --yes      # install (or finish an install that stopped)
ad5x-bootloader-install --status   # which boot loader and build, and the install record
reboot
```

The log is `/data/ad5x/bootloader/log`, the install record
`/data/ad5x/bootloader/state`.

The check's last line says where things stand: `result: ready to install`
(nothing written yet; a stock first MiB saved earlier and a blank U-Boot
area in `ota`, as Flashforge's factory reset leaves it, are still a fresh
install), `result: ready to go on` (an install that stopped part-way: its
record says `started`, or Kiln's SPL or part of Kiln's U-Boot is on the
disk; `--yes` finishes it), `result: already installed (this build)`
(nothing to do, exit 0; also while another job or the start-up actions
run, since nothing would be written) or `result: refused` with the
failed checks. Exit codes: 0 done or nothing to do, 1 refused, 2 checked,
3 a write failed but every system still starts, 4 the boot loader area is
not as before (run it again at once).

## What the installer writes

After its checks (the recovery OS in slot A, an eMMC with Flashforge's
partition layout, the saved stock boot loader matching this printer, a
known board, the images it carries checking out, a Kiln OS main system
that confirms U-Boot's starts and has a whole 6.6 kernel), in this order:

0. If missing: this printer's stock first MiB saved as
   `/data/ad5x/stock/boot.img` (from the disk, while it still holds
   Flashforge's SPL), and its copy on the usershare partition
   (`kiln-stock-backup`). If the data partition was wiped and the disk
   holds Kiln's SPL, `boot.img` comes back from usershare's
   `kiln-stock-backup` or a USB stick's `kiln-stock-backup`, after the same
   checks as the saved one (it must match this disk). The check already
   runs `ad5x-stock-copy`'s room test for that copy (`--space-check`), so
   a usershare without room is refused before anything is written.
1. Kiln's SPL: the SPL's first sector (its header, 0x4400) is zeroed
   first, then the rest of the SPL (0x4600-0xA3FF) and the boot ROM's
   length field at 0x4 are written, and the header sector last.
   Flashforge's U-Boot behind it stays and is no longer started.
2. Kiln's 6.6 (the main OS's own) into the main slot's kernel partition
   (p3), the header last.
3. The same into the recovery slot's kernel partition (p1), the header
   last.
4. U-Boot's settings and records in the `ota` partition cleared, so its
   first start is a fresh one.
5. Kiln's U-Boot at 0xA400: its body first, its header last (until then
   Kiln's SPL doesn't see a U-Boot and starts the slot itself).

Each step is read back. The partition table and everything else in the
first MiB are never written.

Why the header goes last: the boot ROM checks only the SPL's header (a
magic word and a length, no checksum) before it starts the SPL. With no
header it goes into USB boot mode by itself (see "If nothing starts"
below), but a valid header in front of half an SPL would start a broken
SPL, and getting out of that needs the printer opened and the K4 pads
shorted. With the header written last, a power cut during the SPL write
(a few milliseconds) leaves either Flashforge's SPL, or no SPL (USB boot
mode), or Kiln's SPL whole. Return to Flashforge firmware writes
Flashforge's SPL back the same way. The images are in the recovery OS:
`/usr/share/ad5x/bootloader/` (`spl-mmc.img`, `u-boot-emmc.img`,
`SHA256SUMS`, and the build's `report.txt`).

After the install the main OS keeps both kernel partitions on its own 6.6
with every update, and updates never touch the boot loader.

## Upgrading the boot loader

The recovery OS carries the boot loader of its own release. When the
printer has Kiln's boot loader of an older build (an earlier install, or
the bench tools), it can be upgraded to the one this release carries.
Nothing updates it by itself: a Kiln OS update brings a new recovery OS
(the main OS writes it into slot A after its first complete start), and
that recovery OS brings the new boot loader images, but writing them is
always your step, because a power cut in the SPL write needs the USB-boot
rescue.

Which build is newer is told by the build dates in the version strings
(`U-Boot SPL 2026.10 (Nov 19 2026 - 08:31:00 +0000)` in the SPL, the same
form in U-Boot), read as times with their zones. SPL and U-Boot come from
one build and their dates differ by seconds at most; where they differ
more (a mixed pair from the bench tools), a build counts as new as its
newer half. A build whose dates can't be read, or two builds of the same
time with other bytes, can't be told apart: the update is offered as
before.

### The main OS tells you

Most people rarely start the recovery OS, so the main OS's touch screen
says it once when an update is waiting: "A boot loader update is ready.
To install it: Settings > System > Boot into recovery > Reboot / Power >
Update Kiln's boot loader." It shows when the printer has Kiln's boot
loader and the recovery OS in slot A carries a newer build (on a known
board, eMMC), at idle only: not during the setup wizard, not while a
print runs, not over another dialog. OK (or tapping beside it) closes it
for that build; it comes back only for a newer one.

At each complete start, `ad5x-bootloader-notice --start`
(S99ad5x-update-recovery, after it has written slot A when that was due)
reads the first MiB's version strings and slot A's
`/usr/share/ad5x/bootloader` images (slot A mounted read-only for a
moment), checks the board by the stock first MiB saved before Kiln's boot
loader (`/data/ad5x/stock/boot.img`, or after a wiped `/data` its copy in
usershare's or a mounted USB stick's `kiln-stock-backup/`, as the recovery
finds it; usershare is only read) and writes `/run/ad5x-bootloader-notice`, which HelixScreen reads
(patch 0094). It reads slot A itself, not the recovery image the main OS
brings (that one reaches slot A only after the first complete start) and
not a file the recovery OS would write (one from the recovery OS before
an update would still name the old build). What was shown is kept in
`/data/ad5x/bootloader-notice/` (`update-seen`, `install-dismissed`;
`starts` counts the complete starts, `last` says what the last check
found). `ad5x-bootloader-notice --print` shows what it finds without
writing anything. Nothing there writes the boot loader.

### On the recovery screen

1. Boot into recovery (touch screen: Settings > System > Boot into
   recovery).
2. Tap **Reboot / Power**. When the printer has Kiln's boot loader of
   an older build (on a known board), there is a button **Update Kiln's
   boot loader**. No opt-in file is needed: you installed Kiln's boot
   loader already. The button isn't there when the boot loader is already
   this release's, nor when it is newer than this recovery OS's (you went
   back to an older Kiln release): then the line above the buttons says
   "installed, build X (this recovery carries an older build, Y)", and
   the screen never offers that downgrade (over SSH it is possible, see
   below).
3. The page checks everything first and shows the build on the printer
   and the one after the update. Nothing is written yet.
4. Tap **Update** and confirm twice (the same risk note as the install).
   Wait until the screen says it is done.
5. Tap **Reboot**. The printer starts this recovery screen again through
   the new boot loader, and the page shows the result. Then **Boot main
   OS**.

If the power goes off during the update, the recovery screen comes back,
the page opens by itself and **Continue** finishes it. The screen runs
`ad5x-bootloader-install --yes --upgrade`: `--upgrade` refuses anything
that isn't an upgrade, so this button never installs Kiln's boot loader
over Flashforge's, and it never uses `--unsupported-board`.

### Over SSH

The same command upgrades it, over SSH in the recovery OS:

```
ad5x-bootloader-install --status   # the build on the disk and the one carried
ad5x-bootloader-install            # checks; prints "upgrade: Kiln boot loader <old> -> <new>"
ad5x-bootloader-install --yes      # upgrade (or finish one that stopped)
```

`ad5x-bootloader-install --yes` also goes back to an older build than
the one on the disk (a downgrade, the same steps and checks): `--check`
and `--status` say so ("this recovery OS carries an older build than the
one on the disk: a downgrade"). The screen's `--upgrade` refuses it.

It needs the same as an install (`/data/ad5x/stock/boot.img` above all:
the disk no longer has Flashforge's SPL), and the disk must be exactly
that `boot.img` with a whole Kiln SPL and U-Boot in it. It keeps the old
first MiB as `/data/ad5x/bootloader/before-upgrade.img`, then writes the
new SPL (as step 1 above), then the new U-Boot: the old U-Boot's header
first zeroed, the body up to the end of the old or new U-Boot, whichever
is longer, the header last. U-Boot's settings, state and records in
`ota` stay. Every state on the way starts: the new SPL starts the old
U-Boot, and while U-Boot is written the SPL starts the recovery OS
itself. As in an install, the SPL write (milliseconds) is the one moment
a power cut leaves no SPL (USB boot mode, "If nothing starts"). If the new SPL doesn't read back, the old Kiln SPL goes back
(never Flashforge's, which can't start a Kiln U-Boot). When the disk
already holds the carried build byte for byte, there is nothing to do.
Return to Flashforge firmware works after an upgrade as after an install.

## Going back

**Return to Flashforge firmware** (recovery screen: **Restore stock**,
`docs/install.md` "Going back to stock") works with Kiln's boot loader:
it removes Kiln's U-Boot and, whenever this printer's `boot.img` is found
(`/data/ad5x/stock`, usershare's or a USB stick's `kiln-stock-backup`),
writes this printer's stock SPL back from it too. The page's box **Also put
back Flashforge's own boot loader** is ticked then; untick it (over SSH:
`ad5x-return-stock --keep-kiln-spl`) to keep Kiln's SPL, which starts
stock the way Flashforge's does. Without a matching `boot.img` Kiln's SPL
stays, and the page says plainly that Flashforge's own boot loader can't be
put back because the printer's saved copy wasn't found; stock works all the
same. `--flashforge-spl` makes the return refuse instead. A stopped return
goes on with the choice it started with, also one an older recovery OS
started (it kept Kiln's SPL by default). Then install Kiln OS again with
the install stick if you want Kiln OS on Flashforge's boot loader.

## If the printer doesn't start

1. **Wait five minutes.** Kiln's SPL retries by itself: a U-Boot that
   hangs is reset by the watchdog and skipped, a slot that doesn't load is
   replaced by the other one. On an eMMC that only reads at the slow
   setting (above), a start takes about 2 minutes longer.
2. **Switch it off and on once or twice.**
3. If the recovery screen comes up, the boot loader works and Kiln OS's
   main system didn't start: **Boot main OS** tries again, **Restore
   stock** goes back. Over SSH, `ad5x-bootloader-install --status` says
   how this start came up. Please post what happened in
   [issue #68](https://github.com/djvalic/kiln-os/issues/68).
4. If nothing starts at all (dark screen, no network after several power
   cycles), see "If nothing starts" below. Ask in
   [issue #68](https://github.com/djvalic/kiln-os/issues/68) before you
   try it. When Kiln's SPL found nothing to start, it has put the printer
   into USB boot mode by itself, ready for that.

### If nothing starts

**With Kiln's SPL, a printer with nothing bootable left waits in USB
boot mode by itself.** Kiln's SPL tries four times (U-Boot, then each
kernel slot); when none of that starts a kernel, it asks the chip's boot
ROM for its USB mode and restarts into it. No K4 short is needed: a
computer on **J28** sees USB device `a108:eaef`, as below. The serial
console's last line says so: `SPL: nothing started after 4 attempts ...:
boot ROM USB mode (J28); power-cycle to try the eMMC again`. It happens
within seconds when the kernels are simply missing or damaged (up to
about three minutes when something hangs on the way).

**Switching the power off and on makes it try the eMMC again**: the
request doesn't survive a power cut, so the printer starts normally if
something bootable is back, and otherwise ends up in USB mode again after
its four tries. If USBCloner doesn't see the chip, power-cycle and wait
for `a108:eaef` to come back. Should the chip's boot ROM ever ignore the
request, Kiln's SPL stops on the next start instead of trying again (the
old behaviour: then only K4 gets the chip into USB mode).

This answers alexshev86's test 4 (issue #68): with both kernel slots'
headers zeroed, Flashforge's SPL hangs and only K4 helps. With Kiln's
boot loader, U-Boot still starts the main OS from its own partition in
that case; where nothing at all can start, Kiln's SPL now goes to USB
mode instead of hanging (`u-boot/README.md`, "Tries").

alexshev86 also tried the case of a missing SPL on his own printer (test
1, issue #68): he zeroed the SPL's header sector on purpose and brought
the board back over USB. What he found:

- **A dead SPL header puts the chip into USB boot mode by itself.** The
  boot ROM finds no SPL and waits for a computer on the white 5-pin
  **J28** USB connector (D+, D-, GND only; measure 5V first and never feed
  a second supply). No K4 short is needed. A computer sees it as USB
  device `a108:eaef`. The serial console stays silent, because the SPL is
  the first thing that prints.
- **Switch the power off and on fully before USBCloner can see the
  chip.** A `reboot` from Linux wasn't enough.
- **USBCloner** (2.5.50 in his test) with a profile of one entry: file
  `type=0`, `ops="6,2,0"` (MMC0), offset `0x0`, the file this printer's
  own 1 MiB backup (`boot.img` from `/data/ad5x/stock`, Save files to USB,
  or `dd if=/dev/mmcblk0 bs=1M count=1`), `force_erase=0`,
  `force_reset=0` (switch the power off and on yourself after the write,
  so a soft reset can't hide whether it worked), `cpu_info_length=5`.
  Then a full power cycle, and the printer started as before.
- **Write back only this printer's own first MiB, never another
  printer's**: the partition tables differ between boards.
- After a USBCloner write from the start of the eMMC, the 4 bytes at
  0x4480 read `84 00 84 00` (USBCloner's DDR type). That is harmless: no
  SPL reads them, and the fingerprint above ignores them.
- Boards differ in where the partition table keeps its entries: his keeps
  them at sector 32 (0x4000), the developer's at sector 2. Kiln OS reads
  the place from the partition table's header, so both work for
  `ad5x-restore boot`, the installer and Return to Flashforge firmware.
  He also saw that a first MiB read over USB can be laid out differently
  from a `dd` copy of the same board: write back the `dd` copy (or
  `boot.img`), not a USB read.

What this does **not** cover: an SPL that has a valid header but a broken
body, or that hangs before it can reset (Kiln's SPL arms the watchdog as
the first thing it does, so a later hang resets into its next try and in
the end into USB mode). Then the boot ROM starts it, and only the K4 pads
(boot_sel to USB) get the chip into USB mode: `u-boot/USB-BOOT.md` and
`tools/bench/README.md` ("Contingency") describe that, with the
USBCloner settings for a full backup (alexshev86's, issue #66). This is
why Kiln OS writes the SPL's header last.

### The whole eMMC from a computer (jolting's tools)

Hunter Laux (jolting) added three ways in for a printer in USB boot mode
or without a serial cable (u-boot patches 0034-0048, PRs #75, #77, #78,
#79). They are in Kiln's U-Boot, so they work whatever is on the eMMC
past its first MiB. Nothing of them runs on a normal start.

- **The eMMC as a USB disk.** With the printer in USB boot mode on J28,
  `u-boot/tools/ad5x_usbboot.py run-uboot spl-usb2.bin u-boot.bin` starts
  Kiln's SPL (memory only) and then Kiln's U-Boot from the computer, which
  offers the whole eMMC as a USB disk. The start itself writes nothing.
  How to use it: `u-boot/USB-BOOT.md` ("The eMMC as a USB disk"); backing
  up and repairing: `docs/emmc-repair.md`.
- **The network rescue.** When only USBCloner reaches a printer, it can
  write one 1 MiB file with Kiln's SPL and U-Boot and a rescue record in
  the last sector; Kiln's U-Boot then fetches the rest of the eMMC from a
  computer on the network, checks every piece and writes it.
  `docs/emmc-repair.md` has the steps. It tries three times at most and
  then starts as without it; the record stays until `ad5x_rescue clear`
  at the U-Boot prompt, a rescue that finishes, or
  `ad5x-bootloader-install`, which puts the saved stock bytes back in
  that sector before it installs or upgrades (`--status` shows a record).
- **Netconsole.** `echo <your computer's IP> > /data/ad5x/netconsole`
  (as root in Kiln OS) sends U-Boot's console to that computer at every
  start; keys from it (the stop key, the U-Boot prompt) need
  `/data/ad5x/netconsole-input` as well. `docs/emmc-repair.md`,
  "Netconsole"; `u-boot/README.md`, "U-Boot proper".

Kiln's U-Boot now ends one sector earlier, before that rescue record's
place; `ad5x-bootloader-install` refuses an image that doesn't.

## Build SPL and U-Boot yourself

The source is all in this repository: `u-boot/` (the U-Boot v2026.10
release, pinned by its sha256, plus `u-boot/patches`), and
`u-boot/build.sh` builds and checks it (the boot ROM's 24 KiB limit, the
SPL's memory map and stack, U-Boot's size):

```
u-boot/build.sh --container        # podman or docker, u-boot/Containerfile
ls ~/workspace/u-boot-ad5x-build/out/dist
```

`spl-mmc.img` and `u-boot-emmc.img` are the two images the installer
writes; `report.txt` lists what was checked. The Kiln OS build makes the
same with Buildroot's compiler (`buildroot/package/ad5x-bootloader`).
`FIRST_MIB_DUMP=boot.img` (your printer's saved first MiB) also makes
`first-mib-uboot.img`, the first MiB the install leads to, for comparing.

To install your own build with the installer, copy the two images to the
printer's recovery OS and point the installer at them:

```
P=192.168.x.y
D=~/workspace/u-boot-ad5x-build/out/dist
(cd $D && sha256sum spl-mmc.img u-boot-emmc.img > /tmp/SHA256SUMS)
ssh root@$P mkdir -p /tmp/kiln-bl
scp -O $D/spl-mmc.img $D/u-boot-emmc.img /tmp/SHA256SUMS root@$P:/tmp/kiln-bl/
ssh root@$P AD5X_BOOTLOADER_FILES=/tmp/kiln-bl ad5x-bootloader-install
ssh -t root@$P AD5X_BOOTLOADER_FILES=/tmp/kiln-bl ad5x-bootloader-install --yes
```

On a board that isn't on the list yet, the installer refuses. If you
understand the risk above and can open the printer if needed, the expert
override is `--unsupported-board` (over SSH only, with `ssh -t`: it asks
you to type a sentence to confirm; the touch screen never offers it). It
prints the board's fingerprint: please post it in issue #68 either way.

The AD5X ships with two chips: X2600H (512 MiB DDR3L, the board Kiln's
SPL was proven on) and X2600E (256 MiB DDR3). Kiln's SPL reads the chip
type at power-on and sets up the memory for either. From eMMC it has
run on one X2600E so far (a tester's board, warm and cold start, issue
#68), and an SPL that sets the memory up wrong leaves the printer in
USB mode. So an X2600E is still treated like a board
that isn't on the list: never offered on the touch screen, and installed
only with `--unsupported-board`. A board where the installer can't tell
the chip is refused, even with `--unsupported-board`. It tells them apart read-only, from `MemTotal` in
`/proc/meminfo` (at least 400000 kB: an X2600H; less: a 256 MiB board) and the `mem=...@0x30000000`
bank on the kernel command line (only an X2600H has RAM there); the
`chip:` line of the fingerprint shows what it found. (The chip's eFuse
says it directly, but reading the eFuse needs register writes, so the
installer doesn't.)

The eMMC chips differ between printers too. Kiln's SPL reads the eMMC
the way the boot ROM left it. If a read fails, it moves the sample point
to the middle of the window (RX phase 3) and reads again; if that fails
too, it starts the eMMC again at the slow setting it uses to identify the
card (400 kHz, 1 bit) and, if that works, boots that way. That start is
slow: about 2 extra minutes for the kernel. Each step prints a line on
the serial console (`u-boot/README.md`, "Chip variants"); please post
them in issue #68. The kernel gets `lpj=11935744` on an X2600H (what
Flashforge's 2024 boot loader passes) and `lpj=11476992` on an X2600E
(measured on one; Flashforge's 2025 boot loader passes it).

The developers' bench tools (`tools/bench/`: `ad5x-spl-flash`,
`ad5x-uboot-flash`, run from the main OS) are how the boot loader was
proven step by step; `tools/bench/README.md` has those steps. The
installer writes the same ranges in the same order.
