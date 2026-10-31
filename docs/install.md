# Installing Kiln OS

How to put Kiln OS on a Flashforge AD5X that runs its stock firmware,
how to go back to stock, and what the installer does to the printer. Two
ways in: a USB stick (no tools needed) or SSH (with root access, for example
after zMod).

**Status (2026-10-20):** installed on one AD5X over SSH on 2026-10-19
(installer v0.0.3; stock firmware with zMod, stock running from slot B):
all six steps, the first start of the main OS and its writing of the
recovery OS, and the updates since (v0.0.4 to v0.0.8, from Fluidd). The
USB-stick route (stock's USB hook, the install screens) and the other slot
layout (stock in slot A) have run under qemu only (`tools/test_install.sh`,
every release).

> **⚠ Your settings and configs do not come with you.** Kiln OS starts
> with its own Klipper configuration. It does **not** use the `printer.cfg`,
> macros or other `.cfg` files you edited on stock or zMod, your saved bed
> mesh, PID or input shaper results, Fluidd/Mainsail settings or print
> history. **Back up anything you want to keep before installing**
> (for example: download the `config` folder in Fluidd or Mainsail).
>
> Carried over: the Z offset, cutter and purge-box positions from stock's
> settings (`unit.cfg`), the Wi-Fi networks saved on stock's screen, and
> which zMod plugins were on
> (`docs/zmod-compat.md`). Nothing is deleted: the old files stay on the data
> partition and the stock system is saved for going back, but Kiln OS
> doesn't read them. After the install, run the setup wizard on the touch
> screen (PID, bed mesh, input shaper, Z offset; its Wi-Fi step joins a
> network if you don't use Ethernet).

> **The two boards get new firmware.** At its first start Kiln OS writes
> mainline Klipper firmware to the mainboard and the toolhead board (about a
> minute; the screen says "Updating the boards"). If the screen then says
> "Switch off and on", do that: the toolhead board takes new firmware only
> right after power-on. Going back to stock puts Flashforge's board firmware
> back by itself at stock's first start (switch off and on). Details:
> `docs/mcu-flashing.md`, "Automatic updates".

## What you need

- An AD5X running its stock firmware, with or without
  [zMod](https://github.com/ghzserg/zmod). Any firmware that still has stock's
  USB hook (`/usr/prog/app_startup.sh` runs `flashforge_init.sh` from a stick)
  works for the USB method; 3.1.0 has it.
- The install files of a release: `kiln-os-<version>-install.zip` (made by
  `tools/make_install_stick.sh`). It contains the recovery OS, the main OS as
  an update `.zip`, the installer and its screens. **It contains no
  Flashforge files and no kernel**: the drivers, board tools and kernel come
  from your own printer (see "Vendor files" and "Kernel" below).
- For the USB method: a USB stick, FAT32. 256 MB is enough; with 2 GB or more
  the installer also copies the printer's eMMC to the stick first (about
  1.3 GB, see "Backups").
- About 250 MB free on the printer's data partition (`/usr/data`): the saved
  stock system (~22 MB), the vendor files (~1 MB) and the images waiting for
  the first start.
- Network: the main OS uses the same Ethernet MAC as stock and DHCP. Wi-Fi
  starts with the networks saved on stock's screen (switched off ones stay
  off); join or change one on the touch screen (setup wizard, or any time
  in Settings > Connection > Network Settings), where the Wi-Fi switch
  also turns it off for good if you only use Ethernet. Saved in `/data/ad5x/wpa_supplicant.conf`;
  `/data/ad5x/wifi.disable` turns Wi-Fi off completely.

## Method 1: USB stick (recommended)

1. Unzip `kiln-os-<version>-install.zip` into the top folder of a FAT32
   stick. It holds `flashforge_init.sh`, `README.txt` and the folder
   `ad5x-install/`. **Never put an `AD5X-*.tgz` on the same stick**: stock
   would install it as a Flashforge firmware update.
   (On Linux, `sudo tools/make_install_stick.sh --device /dev/sdX` partitions,
   formats and fills a stick in one go; it asks you to type the device name.)
2. Printer off, stick in, printer on.
3. Stock starts, finds `flashforge_init.sh` and runs it before its own app.
   The screen shows "Installing, step n of 6". It takes a few minutes (longer
   with the eMMC copy). Don't switch the printer off.
4. "Done, restarting": remove the USB stick, then wait. The printer restarts
   by itself into the new system. The first start takes a few minutes more
   (see "First start"). If nothing happens after 3 minutes, power-cycle the
   printer. The switch is already made, so this is safe.
5. Leave the stick in or take it out: Kiln OS never runs
   `flashforge_init.sh`. The log is `ad5x-install.log` on the stick.

If the screen says **"Not installed"** or **"Installation failed"**, the
printer waits with the message on screen. Remove the stick and power-cycle:
it starts its old firmware as before. Nothing is switched before every check
has passed, and the boot flag is the very last thing written. Read
`ad5x-install.log` on the stick for the reason.

Markers you can put next to `flashforge_init.sh` on the stick:

| File | Effect |
|---|---|
| `ad5x-no-emmc-backup` | Skip the eMMC copy to the stick |
| `ad5x-install-retry` | Install again after an earlier attempt switched to Kiln OS and the printer is back on stock (see "If the new system doesn't start"). Deleted when used, so it can't start a loop |

## Method 2: SSH

You need root on the stock system: stock's own SSH (port 22). After zMod is
installed its password is `root`. Log in to **stock's** SSH, not a shell inside
zMod's chroot (the installer refuses to run there).

```
# on the computer: the ad5x-install folder from the stick zip
scp -r ad5x-install root@<printer>:/usr/data/ad5x-install
ssh root@<printer>
sh /usr/data/ad5x-install/ad5x-install.sh --check     # checks only, writes nothing
sh /usr/data/ad5x-install/ad5x-install.sh --reboot    # asks for YES, installs, restarts
```

`--check` prints what it would do: which slot gets which system, the saved
kernel, free space, whether zMod is there. Other options: `--yes` (don't
ask), `--emmc-backup DIR` (copy the eMMC to DIR, e.g. a mounted stick),
`--recovery`, `--main`, `--sums` with files or `http(s)://` URLs (fetched with
stock's curl) instead of the folder's files, `--retry`. `sh ad5x-install.sh
--help` lists them. Log: `/usr/data/ad5x/install/install.log`.

## What the installer does

The AD5X has two system slots on its eMMC (`docs/boot-slots.md`): slot A
(`kernel` p1 + `rootfs` p2) and slot B (`kernel2` p3 + `rootfs2` p4), and a
flag (`ota` p5) that tells the boot loader which one to start. Stock runs from
one of them; out of the factory both hold the same stock system. Kiln OS
puts its recovery OS in slot A and the main OS in slot B.

1. **Checks** (nothing is written before all pass):
   - an AD5X: device tree `ingenic,x2600` and stock's machine name `AD5X`;
   - the eMMC partitions where the boot loader expects them (names, start
     sectors and sizes of p1 to p7);
   - the running system is stock (not Kiln OS: then it says to use an
     update instead), it runs from the slot the boot flag names, and that
     slot's kernel partition holds a kernel (uImage);
   - the install files match `SHA256SUMS`, the main update has no kernel, the
     images fit their slots, and `/usr/data` has room;
   - no earlier install already switched to Kiln OS (see below).
2. **Stock is saved** to `/usr/data/ad5x/stock/`: `rootfs.squashfs` (the
   running root, its used bytes), `kernel.img` (the running slot's kernel
   partition), `SHA256SUMS`, `MANIFEST.txt`. Copied and read back. A copy that
   is already there and matches is kept. `ad5x-restore-stock` uses it. Then the
   optional eMMC copy (stick, or `--emmc-backup`).
3. **Vendor files** are copied from the running stock system into
   `/usr/data/ad5x/vendor/` (below), from a fresh read-only mount of the stock
   root, so nothing zMod binds over it is taken.
4. **The free slot is written** and read back (sha256), then mounted to check
   it holds what it should:
   - stock in slot A (the usual case): the main OS goes into slot B;
   - stock in slot B (after a stock update): the recovery OS goes into slot A.

   Its kernel partition gets the printer's own stock kernel, copied from the
   running slot (skipped when it already matches).
5. **The other system waits for the first start**:
   - main in B: the recovery image is left in
     `/usr/data/ad5x/install/recovery.squashfs`;
   - recovery in A: the main OS update is left in `/usr/data/ad5x/update/`.
6. **The boot flag** is pointed at the written slot, read back, and the
   printer restarts (USB, or SSH with `--reboot`).

State: `/usr/data/ad5x/install/state` (`checked`, `backed-up`, `vendor`,
`slot-written`, `staged`, `flag-set`, `done`). Running the installer again
after a failure goes through the same steps; finished ones are checked and
not repeated (a matching stock copy, slot or kernel is left as is).

### First start

- **Main OS in slot B (stock was in A)**: the main OS starts with its
  try-once safety (`docs/boot-slots.md`): if it doesn't finish starting, the
  next power cycle returns to stock in slot A. Once it is fully up (SSH
  running, boot flag back on B), `S99ad5x-install-recovery` writes the recovery
  OS into slot A in the background: `ad5x-update --install-recovery
  --replace-stock` (stock saved again first, read-back check). Log:
  `/data/ad5x/install/install.log`. Up to three tries, one per start.
  From then on slot A holds the recovery OS and stock lives only in
  `/data/ad5x/stock`.
- **Recovery OS in slot A (stock was in B)**: recovery starts, finds the
  update in `/data/ad5x/update/`, installs it into slot B (checks, read-back),
  points the flag at B and restarts into the main OS.

Either way the end state is the same: recovery in slot A, main OS in slot B,
stock saved in `/data/ad5x/stock`, vendor files in `/data/ad5x/vendor`, both
kernel partitions holding the printer's own stock kernel. The main OS uses
zMod's settings it finds on the data partition (plugins, `docs/zmod-compat.md`);
zMod's files stay where they are.

### If the new system doesn't start

With stock in slot A, a main OS that fails during start-up lands back on stock
at the next power cycle. If the install stick is still in, stock runs it
again; it sees that an earlier install already switched (state `flag-set`)
and stops with "Not installed" instead of installing in a loop. Take the
stick out to use stock, look at `/usr/data/ad5x/install/install.log` and the
boot trace (`docs/boot-slots.md`), and use `ad5x-install-retry` (stick) or
`--retry` (SSH) to try again.

## Vendor files

The stock kernel needs Flashforge/Ingenic's out-of-tree drivers (display,
touch, backlight, Ethernet, I2C, ADC, PWM, GPIO, watchdog), and the board
needs stock's tools for its heartbeat and the display (`cmd_gpio`, `cmd_fb`,
`cmd_jpeg_display` with `libhardware2.so`, `libutils2.so`, `libjpeg.so.9`).
These files belong to Flashforge/Ingenic, so release images don't contain
them. Each printer uses its own copy:

| | |
|---|---|
| Where | `/data/ad5x/vendor/` (stock's `/usr/data/ad5x/vendor/`): `module_driver/` (stock's `/module_driver` as is), `bin/`, `lib/`, `MANIFEST` (source, date, kernel version magic), `SHA256SUMS` |
| Made by | the installer (from the running stock system), or at boot by `ad5x-vendor ensure` (`S06ad5x-modules`, main and recovery OS) |
| Used by | `S06ad5x-modules` (loads the drivers in stock's order), `/usr/bin/cmd_gpio`, `cmd_fb`, `cmd_jpeg_display` (our wrappers: they run stock's binaries from there with their own libraries and our C library), `S07ad5x-board` |
| Checked | at every start (`SHA256SUMS`); a missing or damaged copy is filled again |

At boot, a missing or damaged copy is filled from what is on the printer, in
this order:

1. the image itself, if it is a private build that bundles them;
2. a slot that holds the stock system (mounted read-only);
3. the saved stock system `/data/ad5x/stock/rootfs.squashfs` (read with
   `unsquashfs`, the stock kernel has no loop devices);
4. a slot that holds an older Kiln OS image that still bundled them
   (updates from private builds).

Stock's `usershare` partition (p6) holds only the Wi-Fi driver `8821cu.ko`,
which is loaded from there as before; it is not a source for the others.

If none of these exist, the system still starts, without display, touch,
backlight and Ethernet (Wi-Fi may still work), and says so on the console, in
the boot trace (`vendor: MISSING`) and in `ad5x-vendor status` (recovery:
`ad5x-status` key `vendor`). Fix: copy a stock root's files with
`ad5x-vendor populate SRC`, where SRC is a stock `rootfs.squashfs` or an
unpacked stock root.

```
ad5x-vendor status            # vendor=ok|missing|damaged, source=...
ad5x-vendor verify
ad5x-vendor populate [SRC]
```

## Kernel

Releases carry no kernel. Kiln OS runs on the printer's own stock Linux
5.10 kernel (the drivers above are built for it):

- the installer copies the running slot's kernel into the other slot's kernel
  partition (and saves it in `/data/ad5x/stock/kernel.img`);
- updates (`.zip`, `.swu`) are rootfs-only: the recovery OS keeps the kernel in
  `kernel2` after checking it is a uImage; if `kernel2` holds none, it copies
  its own (`kernel`, p1), never one from the update;
- `ad5x-update --install-recovery` copies the main OS's kernel to slot A when
  they differ.

Private builds can still put the stock kernel in an update (`make_swu.sh -k`).

## Backups

- Always: stock root and kernel in `/data/ad5x/stock` (enough to put stock
  back, below).
- USB method, stick with room (about 1.3 GB): `ad5x-backup-install-<n>/` on the
  stick with the first MiB of the eMMC (GPT, boot loader) and partitions p1 to
  p6 (`boot.img`, `kernel.img` ... `usershare.img`, `SHA256SUMS`,
  `MANIFEST.txt`), in the format of the recovery OS's `ad5x-backup`, so
  `ad5x-restore` can write them back. `usershare` is copied while stock has it
  mounted. The data partition (p7, 5.8 GB, mounted) is not copied. Copy the
  folder to a computer.
- Recommended in addition: the full eMMC image of `docs/emmc-backup.md`, or
  `ad5x-backup --all` from the recovery OS once it is installed.

## Going back to stock

From the recovery OS (touch screen "Restore stock", or SSH):

```
ad5x-restore-stock --dry-run     # checks /data/ad5x/stock
ad5x-restore-stock --reboot      # stock -> slot B, flag -> B, restart
```

Stock then starts from slot B and stays (it has no try-once). Slot A still
holds the recovery OS; stock doesn't use it. To make slot A stock too (from
stock, as root over SSH):

```
cd /usr/data/ad5x/stock && sha256sum -c SHA256SUMS
dd if=rootfs.squashfs of=/dev/mmcblk0p2 bs=1M conv=fsync
dd if=kernel.img of=/dev/mmcblk0p1 bs=1M conv=fsync
```

`/usr/data/ad5x` (our settings, the stock copy, the vendor files) can then be
deleted. A whole-eMMC backup (`docs/emmc-backup.md`) restores everything,
including the boot loader area.

**Never** apply a Flashforge firmware update (`AD5X-*.tgz`) while AD5X open
OS is installed: stock's updater writes whichever slot the flag doesn't name.

## Updating a printer that already runs Kiln OS

Use updates, not the installer (`docs/recovery-os.md`): `ad5x-update FILE.zip`
on the main OS, a `.zip`/`.swu` on a stick in the recovery OS, or the recovery
web page.

The first vendor-free update on a printer installed with an earlier build
(whose images still bundled the vendor files): nothing to do by hand. The new
main OS fills `/data/ad5x/vendor` at its first start from
`/data/ad5x/stock/rootfs.squashfs` (saved when the recovery OS was installed),
or from the older recovery image in slot A, before it loads the drivers. To
have it ready before the update, run the new `ad5x-vendor` once on the old
system, which copies its own bundled files:

```
ssh root@<printer> 'sh -s populate' < buildroot/package/ad5x-system/bin/ad5x-vendor
ssh root@<printer> 'sh -s status' < buildroot/package/ad5x-system/bin/ad5x-vendor
```

The kernel partitions stay as they are.

## For developers

```
tools/make_install_stick.sh -o DIR [--zip FILE] [-r recovery.squashfs] [-m main.zip]
tools/check_vendor_free.sh FILE-or-DIR...     # 0 = no Flashforge/Ingenic files
tools/test_install.sh                          # vendor files + installer under qemu
```

`make_install_stick.sh` refuses images that contain vendor files unless
`--private` (your own stick, never to be shared). Sources: installer
`tools/install/ad5x-install.sh`, stick entry `tools/install/flashforge_init.sh`,
screens `tools/make_install_screens.py`, vendor helper
`buildroot/package/ad5x-system/bin/ad5x-vendor`.

## To check on the hardware

Done 2026-10-19 (SSH, stock in slot B, zMod present): writing the free
slot from stock, the first start of that layout, the main OS writing slot
A in the background (`S99ad5x-install-recovery`), `ad5x-vendor ensure` at
the first start.

Not done yet:

- The USB hook with our `flashforge_init.sh` on stock and on zMod, the screens
  (`cmd_jpeg_display` while stock's logo is up), and the restart.
- A second mount of the running root (`mount -t squashfs -o ro /dev/mmcblk0p2`)
  on stock; the installer falls back to `/` if it fails.
- The other layout (stock running from slot A).
- `ad5x-vendor ensure` at the first start (`unsquashfs` of the saved stock
  root before any driver is loaded: a few seconds longer start-up, once).
- The eMMC copy to a FAT stick (time, 1 GB `usershare.img`).
