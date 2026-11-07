# Boot slots (A/B) on the AD5X

How the AD5X boot loader picks between the two kernel/rootfs slots, how
stock's updater switches them, and how to put our OS in the spare slot
and get back. Worked out on the laptop (2026-10-16) from the user's eMMC
backup (`firmware/unit-ad5x-home/emmc-backup/`, see `docs/emmc-backup.md`)
and the stock 3.1.0 updater scripts. Nothing here has been tried on the
printer.

## Summary

- **U-Boot proper never runs.** The **U-Boot SPL** (2013.07, board
  `x2600_base`) loads the Linux kernel itself and starts it.
- The SPL reads the first sector of `ota`. If its first 11 bytes are
  `ota:kernel2`, it boots `kernel2` with `root=/dev/mmcblk0p4`.
  Anything else (`ota:kernel`, zeros, garbage) boots `kernel` with
  `root=/dev/mmcblk0p2`.
- The SPL doesn't read the GPT. Partition positions are **compiled
  into the SPL**.
- **There is no fallback**: no boot counter, no CRC check, no other slot
  after a failure, no console prompt, no key or GPIO check, and no
  USB or SD boot in the SPL.
- So a slot-B system that fails before it can switch the flag back
  stays stuck. The only way out without it is the SoC's USB boot ROM,
  which hasn't been looked at on this board yet.

## Layout of the first MiB (user area of `mmcblk0`)

| Offset | Size | What |
|---|---|---|
| 0x0 | 0x80 used | Ingenic boot ROM parameter block, magic `INGE`, inside the protective-MBR sector (MBR signature at 0x1FE) |
| 0x200 | | GPT header (`EFI PART`) |
| 0x400 | 7 × 128 B | GPT entries (p1–p7) |
| 0x4400 | 0x4600 | SPL image: header `LPSM` (`MSPL` reversed), then at 0x4500 a second copy of the `INGE` block, then code from 0x4C00. Loaded at 0x80001000 (code at 0x80001800). Ends at 0x8A00 |
| 0xA400 | 0x2A600 | U-Boot 2013.07 proper, same build (`Sep 26 2024 - 23:34:47`, `-dirty`), linked at 0x80100000. Not started by the SPL in normal boot |
| 0x34A00 to 0x100000 | | zero |

The eMMC boot areas (`mmcblk0boot0/1`) are all zero.

### U-Boot proper (unused)

Its default environment (file offset 0x2C100) is `bootargs=` (empty),
`bootcmd=` (empty), `bootdelay=1`, `baudrate=115200`, `loads_echo=1`. It has
no bootcount, `bootlimit` or `altbootcmd`. No saved environment block
exists in the first MiB. Where `env_mmc` would write one is unknown. It
has a prompt (`x2600_base# `), `Hit any key to stop autoboot`, `mmc`,
`fatload`/`ext4load`, `tftpboot`, `bootm`, a custom `boota` (Android)
command and `softburn` ("Ingenic usb soft burn"). Because the SPL never
loads it, none of this is reachable on a stock unit. A way to reach it
is described under "Recovery options".

## What the SPL does (from disassembly)

1. Prints its banner (`U-Boot SPL 2013.07-00190-g82c76c87e-dirty`) and
   `test uboot` on ttyS0. Sets up clocks and DDR (W634GU6QG).
2. Starts MSC0 (0xB3450000, the eMMC) and probes the card as SD, then
   as MMC. It doesn't look at any other boot device.
3. Looks up `ota` in its **built-in partition table**: 8 entries of
   {name, start LBA, sectors}, compared by exact name:

   | Name | Start LBA | Sectors | GPT agrees |
   |---|---|---|---|
   | xboot | 0x0 | 0x800 | (no GPT entry) |
   | kernel | 0x800 | 0x4000 | p1 |
   | rootfs | 0x4800 | 0x32000 | p2 |
   | kernel2 | 0x36800 | 0x4000 | p3 |
   | rootfs2 | 0x3A800 | 0x32000 | p4 |
   | ota | 0x6C800 | 0x800 | p5 |
   | usershare | 0x6D000 | 0x200000 | p6 |
   | userdata | 0x26D000 | 0xBAC000 | p7 |

   **Changing the GPT does not move what the SPL boots.** Never move
   p1–p5.
4. Reads 1 sector of `ota` (LBA 0x6C800) and compares it with
   `ota:kernel2` over 11 bytes (`strncmp`). If it matches, it uses partition
   `kernel2` and the bootargs string with `root=/dev/mmcblk0p4`.
   Otherwise it uses `kernel` and the string with `root=/dev/mmcblk0p2`.
   Both strings are fixed in the SPL (file offsets 0x81F8 and 0x8474):
   `console=ttyS0,115200n8 loglevel=8 [mem-start…mem-end] init=/linuxrc
   root=/dev/mmcblk0pN rootwait rootfstype=squashfs ro lpj=11935744`. The
   placeholder is replaced with `mem=`/`rmem=`/`rtos_size=` values.
   Only the root device differs between the two slots.
5. Reads the first sector of the chosen kernel partition and parses a
   legacy uImage header. It checks **only the magic 0x27051956**. It
   checks neither the header CRC nor the data CRC. With the magic
   present, it reads `ih_size + 64` bytes to `ih_load - 64` and, if
   `ih_os` is Linux, jumps to `ih_ep` with the bootargs. Without the
   magic, it treats the partition as raw U-Boot: it reads 512 KiB to
   0x80100000 and jumps there without arguments.
6. If the header read fails, it skips loading and goes on to the jump
   with whatever image info it has. The result is undefined, but it never
   tries the other slot. The "kernel not found" path can't happen because the
   table is built in.

Stock kernel (`xImage-stock`): uImage, Linux 5.10.186, not compressed,
4,837,376 bytes, load = entry = 0x80F00000. The `kernel` partition is
8 MiB.

## Stock updater: how it writes a slot and flips the flag

Path: a USB stick with `AD5X-*.tgz`, then `flashforge_init.sh`
`update_kernel`. That extracts `kernel-2.0.1.tar.xz` to
`/usr/prog/PROGRAM/kernel/<ver>`, checks `md5sum -c md5sum.list` and runs
`run.sh`. `run.sh` checks `uname -m` = mips and runs
`local_ota_update.sh ota_kernel/`. The SD-NAND variant
(`ota_kernel_sd/`) is used only when `/sys/block/mmcblk0/device/type` is
`SD` and the cmdline has `dev_type=SDNAND`. Helpers are in
`/etc/ota_bin/` (stock rootfs; identical copy in
`/usr/prog/etc/ota_bin/`). No stock binary calls these scripts; only the
USB package path does.

Sequence (`local_ota_update.sh`):

1. Version gate: `ota_config.in current_version=1` against
   `/etc/ota_info ota_version=0`. Because 0 < 1, every stock package
   with a kernel part re-flashes.
2. It requires `ota_v1/ota_v1.ok` and parses `ota_v1/ota_update.in`
   (`img_type` / `img_name` / `img_size` / `img_md5` for `kernel` and
   `rootfs`).
3. **Target slot = the one NOT named in `ota`** (`local_get_*_dev_path`).
   `ota` is read with `dd bs=1 count=256`, and the scripts grep for
   `ota:kernel2`: present means target `kernel`/`rootfs` (p1/p2),
   absent means target `kernel2`/`rootfs2` (p3/p4). Device nodes come
   from `fdisk -l` partition names. The target is chosen from the flag,
   not from the running root.
4. Size check: the image must fit the partition (`mmc_check_size`).
5. It writes kernel, then rootfs. Each image arrives in chunks
   (`<name>.NNNN.<md5>`), and each chunk's md5 is checked against
   `ota_md5_<name>.<md5>`. The chunks are piped by
   `ota_img_data_provider.sh` through `ota_update_{kernel,rootfs_squashfs}.sh`
   as a plain `cat … > /dev/mmcblk0pN`. Nothing is erased first, nothing
   is read back, and the whole image is not verified after writing.
6. Only if everything succeeded: `local_set_next_boot_device` writes
   `echo ota:kernel2 > /dev/mmcblk0pN` (or `ota:kernel`, the opposite of
   what was there), then `touch /tmp/ota_boot_set`. Nothing reads that
   file. The new slot is used at the next reboot.

Stock 3.1.0 package content: `xImage` 4,837,440 bytes (md5
`0eae9e9b…`), `rootfs.squashfs` 13,107,200 bytes (md5 `1d0a22a7…`).

Consequences for us:
- **A stock firmware update run from slot A (flag `ota:kernel`) overwrites
  slot B (our OS) and switches to it.** Users must not apply Flashforge
  packages with a kernel part while stock runs from slot A and our OS lives
  in slot B. (Our OS never reads such a stick; after `ad5x-restore-stock`,
  stock runs from slot B and its update writes slot A, the recovery OS: the
  way back to stock in both slots, docs/install.md.)
- Our installer must decide the target from `/proc/cmdline` `root=`,
  never from the flag alone. If the flag and the running root disagree,
  stock's logic would write the mounted root.

## Recovery options

| Option | Status |
|---|---|
| SPL fallback to the other slot | **None.** No counter, no CRC, no retry. |
| Boot loader console on ttyS0 | SPL output only, no input handling. U-Boot proper (`bootdelay=1`) is never started. Whether ttyS0 is on a reachable header on the mainboard is unknown. |
| SD/USB boot from the loader | None in the SPL (eMMC only). |
| Raw U-Boot in a kernel slot | Possible in principle: a kernel partition without uImage magic is loaded as U-Boot at 0x80100000 (512 KiB), the address the shipped U-Boot proper is linked at. Writing bytes 0xA400–0x34A00 of the first MiB into `kernel2` might give a U-Boot prompt (bootdelay 1) on ttyS0 when slot B is selected. Untried: what it expects from the SPL, where `saveenv` writes. Needs a serial line. |
| Ingenic USB boot ROM ("cloner"/usbboot) | Every Ingenic SoC has one in mask ROM. The ROM falls back to it when it finds no valid boot loader, and on some parts boot-select pins force it. X2600 boot-select pins and AD5X board test points are unknown. On NOR-flash Ingenic devices, shorting flash pins during power-on forces it; the eMMC equivalent (holding eMMC CLK or CMD) is untested. Needs Ingenic's cloner with an X2600 config, or a free tool that supports the X2600. |
| Stock (slot A) selected again without our OS running | Only by writing `ota` from outside: USB boot ROM, or a U-Boot prompt as above. Nothing on the printer does it by itself. |

Because of this, the safety has to come from our own install procedure
and early-boot logic, described next.

## Recommended install + rollback procedure

Prerequisites: whole-eMMC backup on the laptop (done, `docs/emmc-backup.md`);
our rootfs has already booted from the USB test stick (same kernel, same
userspace); root SSH from stock.

Image requirements:
- Kernel: legacy uImage, `ih_os` = Linux, size + 64 ≤ 8 MiB. The
  printer's own stock kernel, copied from the slot stock runs in (releases
  carry no kernel; see "Kernel partitions" below), until we have our own.
- Rootfs: squashfs (LZO, as stock) ≤ 100 MiB (ours is ~83 MB with the recovery OS inside, v0.0.6; git adds ~4 MB). It
  must provide `/linuxrc` (`init=/linuxrc` is fixed; Buildroot's links to
  busybox) and must work with `root=/dev/mmcblk0p4 ro`.

Install, run from stock in slot A:
1. Check `/proc/cmdline` has `root=/dev/mmcblk0p2` and `head -c 11
   /dev/mmcblk0p5` is not `ota:kernel2`. Stop otherwise.
2. Check that p3/p4 are not mounted. Check the GPT names p3=`kernel2`,
   p4=`rootfs2`, p5=`ota` and their start sectors (0x36800, 0x3A800,
   0x6C800), which must match the SPL table above.
3. On the printer, check the uImage magic and size and the squashfs
   magic `hsqs` of the files to be written. Then `dd` them to
   `/dev/mmcblk0p3` and `/dev/mmcblk0p4` (`conv=fsync`).
4. Read back exactly the written lengths and compare sha256 with the
   source files. Drop caches first (`echo 3 > /proc/sys/vm/drop_caches`)
   so the device is really read. On any mismatch, stop without touching
   `ota`.
5. Flip as stock does: `echo ota:kernel2 > /dev/mmcblk0p5; sync`. Read
   back the first 11 bytes.
6. Reboot.

Our OS, early boot ("try once"). This is the only automatic fallback
available, so it belongs in the first init script:
- As soon as `/` is mounted and init runs, write `ota:kernel` (stock)
  to p5 and sync. A crash, hang or power cut after this point then
  returns to stock on the next power cycle.
- Once the system is healthy (network, SSH, Klipper up), write
  `ota:kernel2` back.
- Failures *before* init (bad kernel, unreadable squashfs, missing
  `/linuxrc`) can't be caught this way. Steps 3–4 and the earlier USB
  stick test are the protection against those. If one happens anyway,
  only the USB boot ROM (or a serial U-Boot) can recover.

Rollback from our OS: `echo ota:kernel > /dev/mmcblk0p5; sync; reboot`.
Stock in slot A is untouched and boots as before. Offer this as a
command and a UI button.

Updating our OS later: from our OS (slot B running), only p4/p3 are ours
and p4 is mounted. Either switch to stock first and rewrite slot B from
there, or write a new image only after `ota` points at stock (with the
same read-back check), then flip back.

Never: move or resize p1–p5, write the first MiB, or apply a Flashforge
package with a kernel part while our OS lives in slot B.

## Open questions

- The user's quoted running cmdline has no `lpj=11935744`, but the SPL's
  string ends with it. Re-read `/proc/cmdline` on the printer to confirm
  the SPL is the cmdline source (or find what strips `lpj`).
- Does the stock kernel reboot on panic? There's no `panic=` in the
  cmdline, and `CONFIG_PANIC_TIMEOUT` is unknown (the kernel payload's
  strings aren't readable as plain text). Does anything enable a hardware
  watchdog before init? If neither, a slot-B root mount failure hangs
  with no reboot.
- X2600 boot ROM: boot-select pins, the order of boot media, and how to
  force USB boot on the AD5X mainboard (button, test pads, eMMC CLK/CMD).
  Which cloner/usbboot build supports the X2600?
- Is ttyS0 broken out on the mainboard (pads, connector)?
- Would the shipped U-Boot proper run when loaded from a kernel slot by
  the SPL (any SPL→U-Boot handoff data)? Where does its `env_mmc` store
  the environment?
- What does the `INGE` block at 0x0 hold (SPL offset/size, checksum)?
  This only matters if the first MiB is ever rewritten, which we avoid.
- How the `rtos` image (RISC-V co-processor, `rtos_size=4M@0xfc00000`)
  is loaded: the SPL table has no `rtos` partition, and the stock scripts'
  `local_get_rtos_dev_path` would find none.

## Implemented: try once

`S01ad5x-tryboot` (first init script) writes `ota:kernel` when the kernel
command line has `root=/dev/mmcblk0p4`; `S99ad5x-booted` (last) writes
`ota:kernel2` again if dropbear is running. A system that fails after its
init has started comes back up on stock at the next power cycle. Both do
nothing in USB test mode or when booted from slot A.

## Install log (user's unit)

| Date | Step | Result |
|---|---|---|
| 2026-10-16 | Slot B kernel (p3) | sha256 `3144440205c5f17e…` = stock kernel in the eMMC backup; left as is |
| 2026-10-16 | Write rootfs2 (p4) from slot A (root p2, flag `ota:kernel`, p4 unmounted) | `rootfs.squashfs` 64,217,088 bytes; read-back sha256 `c93e6f28a9639ffb…` = image |
| 2026-10-16 | Smoke test under the real kernel | p4 mounted read-only as squashfs; `/linuxrc` present; in a chroot: Python 3.14.5, klippy + chelper, Moonraker, HelixScreen, nginx, Dropbear, BusyBox all run |
| 2026-10-16 | First flag flip to slot B | Booted slot B; S01 reset the flag; the board reset during S06 (stock drivers): came back up on stock. No logs |
| 2026-10-16 | Second try, with the boot trace | Trace: all steps fine up to `start S06ad5x-modules`, then reset |
| 2026-10-16 | Third try: drivers in stock's order (utils, gpio_backlight first), PC11 heartbeat and display via stock's cmd_gpio/cmd_fb from slot A | **Booted on slot B**: rcS done at 13.1 s, S99 set `ota:kernel2`; Klipper ready, IFS connected, Moonraker, Fluidd, HelixScreen, SSH (root password from stock). Touch needed `tsc2007_touch` (loaded by stock's app_startup.sh), added to S06 |

## Updating the installed system

The running root (slot B) can't be rewritten while booted from it. Until
there are two open slots: `echo ota:kernel > /dev/mmcblk0p5`, power-cycle
(stock), write p4 and verify, `echo ota:kernel2 > /dev/mmcblk0p5`,
power-cycle.
| 2026-10-16 | First update through stock (flag to stock, power-cycle, write p4, verify, flag back, power-cycle) | `13f2587d…` installed; slot B boot 14.3 s; touch (`tsc2007_touch`) and Wi-Fi driver (`8821cu`, `wlan0` present) load at boot |

## Both slots ours: `ad5x-update`

Since 2026-10-16 the image runs without stock in slot A: `S07ad5x-board` runs
the PC11 heartbeat, display and logo with stock's board tools (`cmd_gpio`,
`cmd_fb`, `cmd_jpeg_display` and their Ingenic libraries). They were bundled
in the image at first; since 2026-10-17 images are vendor-free and use the
printer's own copies in `/data/ad5x/vendor` (`docs/install.md`). Try once works for either slot (`/usr/lib/ad5x/slot.sh`):
`S01ad5x-tryboot` points the flag at the other slot, `S99ad5x-booted` back at
this one.

`ad5x-update [--reboot] [--replace-stock] IMAGE|- [SHA256]` (on the printer):
writes the idle slot, read-back and mount check (`/etc/ad5x-release`,
`/linuxrc`), copies this slot's kernel if the other differs, flips the flag.
Never touches the running slot. From the laptop:

```
ssh root@ad5x.home ad5x-update - $(sha256sum < rootfs.squashfs | cut -d' ' -f1) < rootfs.squashfs
```

`--replace-stock`: when the idle slot holds stock, its root (squashfs
`bytes_used`) and kernel are first saved to `/data/ad5x/stock/` with sha256s.
Restore stock into a slot from our system: write `rootfs.squashfs` to that
slot's rootfs partition and `kernel.img` to its kernel partition, then set the
flag to that slot.

## With the recovery OS in slot A (docs/recovery-os.md)

The main OS's `ad5x-update` no longer writes the idle slot (that would be
recovery). `ad5x-update [--reboot] FILE.swu|-` stages a signed `.swu` in
`/data/ad5x/update`, points the flag at recovery and reboots; recovery
installs and verifies slot B and boots it. `ad5x-update --install-recovery
[--replace-stock] IMAGE|- [SHA256]` writes the recovery image into slot A
(only from slot B, only an image with `/etc/ad5x-recovery`, saving stock to
`/data/ad5x/stock` first when slot A still holds it). Try once on the main
OS now falls back to recovery.

## First install from stock: the installer (docs/install.md)

`tools/install/ad5x-install.sh` (USB stick through stock's
`flashforge_init.sh` hook, or SSH) does the procedure above on any AD5X running
stock, whichever slot stock runs from:

| Stock runs from | Written now (from stock) | Boot flag | First start |
|---|---|---|---|
| slot A (`root=/dev/mmcblk0p2`, flag not `ota:kernel2`): the usual case | main OS → `rootfs2` (p4); stock kernel p1 → p3 | `ota:kernel2` | main OS with try-once (a failure returns to stock in A); once up, `S99ad5x-install-recovery` writes the recovery OS into slot A (`ad5x-update --install-recovery --replace-stock`) |
| slot B (`root=/dev/mmcblk0p4`, flag `ota:kernel2`): after a stock update | recovery OS → `rootfs` (p2); stock kernel p3 → p1 | `ota:kernel` | recovery installs the main OS from `/data/ad5x/update` into slot B, flag → B |

The target slot is chosen from `/proc/cmdline` `root=` and must agree with the
flag. Before anything is written: the SPL table checked against the GPT, stock
root and kernel saved to `/data/ad5x/stock`, the vendor files copied to
`/data/ad5x/vendor`. Each slot write is read back (sha256) and mounted; the flag
is the last write and is read back.

## Kernel partitions

Kiln OS releases contain no kernel. Both kernel partitions hold the
printer's own stock kernel:

- the installer copies the running slot's kernel to the other kernel
  partition (skipped when equal) and saves it in `/data/ad5x/stock/kernel.img`;
- main-OS updates are rootfs-only: recovery keeps `kernel2` after checking its
  uImage header; an empty `kernel2` gets recovery's own kernel (p1); no
  kernel anywhere refuses the update before writing (`ad5x-slot-b.sh`);
- `ad5x-update --install-recovery` copies the main OS's kernel (p3) to p1 when
  they differ;
- `ad5x-restore-stock` writes the saved `kernel.img` back with stock's root.

On the user's unit both kernel partitions already hold the stock kernel
(install log above), so nothing changes there.
