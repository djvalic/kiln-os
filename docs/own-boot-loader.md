# Kiln's own boot loader (experimental, opt-in)

Every Kiln OS printer starts the way Flashforge built it: Flashforge's
boot loader (a small first stage, the SPL, and a second stage, U-Boot)
starts Flashforge's Linux kernel, which then hands over to Kiln OS's own
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

**This is experimental and at your own risk.** It is installed only when
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
  opened: the white 5-pin **J28** USB connector on the mainboard, the K4
  pads shorted (a Kiln SPL that starts and then hangs keeps the chip out
  of USB mode), a USB cable and Ingenic's USB tool (see "If the printer
  doesn't start" below).
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
echo "parts:  $(cat /sys/block/mmcblk0/mmcblk0p*/start 2>/dev/null | tr '\n' ' ')"
echo "emmc:   $(cat /sys/block/mmcblk0/device/name /sys/block/mmcblk0/size 2>/dev/null | tr '\n' ' ')"
[ "$spl $ddr" = "f7b9d763c1e83af8 61b7ee909c0baa50" ] && echo "match:  yes (tested boards)" || echo "match:  no, please post this"
```

In the recovery OS, `ad5x-bootloader-install --fingerprint` prints the same
lines. On Kiln's boot loader already, put `D=/data/ad5x/stock/boot.img` on
a line of its own first: it then reads the saved stock copy instead.

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

The full output on those boards:

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

## Install from the recovery screen

For now the recovery screen shows the button only after
`touch /data/ad5x/bootloader-offer.enable` over SSH (in the main OS or the
recovery OS), until the install has been tested on more printers. An
install that stopped part-way is offered to finish without it. Deleting
the file hides the button again. The SSH commands below work either way.

1. Boot into recovery (touch screen: Settings > System > Boot into
   recovery).
2. Tap **Reboot / Power**. On a known board without Kiln's boot loader
   (and with the file above) there is a button **Install Kiln's boot
   loader (experimental)**. It isn't there on other boards.
3. The page checks everything first and shows the result. Nothing is
   written yet.
4. Tap **Install** and confirm twice. Wait until the screen says it is
   done.
5. Tap **Reboot**. The printer starts this recovery screen again, now
   through Kiln's boot loader, and the page shows the result: "Done: Kiln's
   boot loader is installed and started this recovery." Then **Boot main
   OS**.

If the power goes off during the install, the recovery screen comes back
(the boot flag stays on the recovery OS all through the install), the page
opens by itself and **Continue** finishes from where it stopped.

## Install over SSH

In the recovery OS (`ssh root@<printer>` while the recovery screen shows):

```
ad5x-bootloader-install            # every check, the fingerprint, the plan; writes nothing
ad5x-bootloader-install --yes      # install (or finish an install that stopped)
ad5x-bootloader-install --status   # which boot loader, and the install record
reboot
```

The log is `/data/ad5x/bootloader/log`, the install record
`/data/ad5x/bootloader/state`.

## What the installer writes

After its checks (the recovery OS in slot A, an eMMC with Flashforge's
partition layout, the saved stock boot loader matching this printer, a
known board, the images it carries checking out, a Kiln OS main system
that confirms U-Boot's starts and has a whole 6.6 kernel), in this order:

0. If missing: this printer's stock first MiB saved as
   `/data/ad5x/stock/boot.img` (from the disk, while it still holds
   Flashforge's SPL), and its copy on the usershare partition
   (`kiln-stock-backup`).
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
with every update, and updates never touch the boot loader. Updating the
boot loader itself isn't supported yet: to put another build on, go back
first (below), then install again.

## Going back

**Return to Flashforge firmware** (recovery screen: **Restore stock**,
`docs/install.md` "Going back to stock") works with Kiln's boot loader:
it removes Kiln's U-Boot, and with **Also put back Flashforge's own boot
loader** it writes this printer's stock SPL back from `boot.img`. Then
install Kiln OS again with the install stick if you want Kiln OS on
Flashforge's boot loader.

## If the printer doesn't start

1. **Wait five minutes.** Kiln's SPL retries by itself: a U-Boot that
   hangs is reset by the watchdog and skipped, a slot that doesn't load is
   replaced by the other one.
2. **Switch it off and on once or twice.**
3. If the recovery screen comes up, the boot loader works and Kiln OS's
   main system didn't start: **Boot main OS** tries again, **Restore
   stock** goes back. Over SSH, `ad5x-bootloader-install --status` says
   how this start came up. Please post what happened in
   [issue #68](https://github.com/djvalic/kiln-os/issues/68).
4. If nothing starts at all (dark screen, no network after several power
   cycles), see "If nothing starts" below. Ask in
   [issue #68](https://github.com/djvalic/kiln-os/issues/68) before you
   try it.

### If nothing starts

alexshev86 tried this out on his own printer (issue #68): he zeroed the
SPL's header sector on purpose and brought the board back over USB. What
he found:

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
body, or that hangs. Then the boot ROM starts it, and only the K4 pads
(boot_sel to USB) get the chip into USB mode: `u-boot/USB-BOOT.md` and
`tools/bench/README.md` ("Contingency") describe that, with the
USBCloner settings for a full backup (alexshev86's, issue #66). This is
why Kiln OS writes the SPL's header last.

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

The developers' bench tools (`tools/bench/`: `ad5x-spl-flash`,
`ad5x-uboot-flash`, run from the main OS) are how the boot loader was
proven step by step; `tools/bench/README.md` has those steps. The
installer writes the same ranges in the same order.
