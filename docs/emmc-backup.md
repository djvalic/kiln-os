# eMMC backup of the user's unit

Taken 2026-10-15 in USB test mode (stock app not running, printer idle),
read-only over SSH. Stored outside git in
`firmware/unit-ad5x-home/emmc-backup/` (Flashforge binaries and user data,
never committed).

| File | What |
|---|---|
| `mmcblk0.img.zst` | Whole eMMC, 7,818,182,656 bytes (zstd, 1.05 GB). sha256 of the raw image in `mmcblk0.img.sha256` (`61e4a2cf…`) |
| `partitions.sha256` | sha256 of each partition p1–p7, cut from that image |
| `mmcblk0-gap-0-1MiB.img` | First 1 MiB: GPT and the boot loader (U-Boot SPL 2013.07, built 2024-09-26, board `x2600_base`) |
| `mmcblk0boot0.img`, `mmcblk0boot1.img` | eMMC boot areas, 4 MiB each: all zero (not used) |

Taken with `sync; dd if=/dev/mmcblk0 bs=1M` piped to the laptop. Checked
afterwards: decompressed image hash matches the stream hash; GPT lists the
seven partitions as in `buildroot/README.md`; `e2fsck -fn` on the two ext4
copies reports no errors (they were mounted read-write while copied, so
they show "needs journal recovery"; nothing was writing to them beyond
Moonraker's log and database in `/usr/data/ad5x`).

Findings:

- The boot loader lives in the first MiB of the user area (not in the
  eMMC boot areas). Restoring the whole image restores it.
- `kernel` = `kernel2` and `rootfs` = `rootfs2`, byte for byte: both slots
  hold the same stock build. `ota` reads `ota:kernel`. The kernel is the
  stock 3.1.0 eMMC kernel (`xImage-stock`).

## Restoring

This section is from 2026-10. For a restore today, use
[emmc-repair.md](emmc-repair.md) (over USB, with the rescue kit) or
`ad5x-backup` and the recovery OS's restore ([recovery-os.md](recovery-os.md)).

- `kernel`/`kernel2`/`ota` (p1, p3, p5) and `rootfs2` (p4) are not
  mounted while the printer runs and can be written back with `dd` from
  a running system. `rootfs` (p2) is the mounted root: write it only from
  another root (the other slot, or a future recovery stick).
- `usershare`/`userdata` (p6, p7) are mounted by stock's init scripts
  before the USB hook runs, so they can't be restored safely from the
  current USB test mode. A restore needs a boot path that doesn't mount
  them (open question).
- Whole-disk restore without a working Linux on the printer would need the
  SoC's USB boot mode (Ingenic's cloner tool); not looked at yet.

## Backups made by the installer

The first install (`docs/install.md`) always saves the running stock root and
kernel to `/usr/data/ad5x/stock`. From a USB stick with about 1.3 GB free it
also copies the first MiB and partitions p1 to p6 to
`ad5x-backup-install-<n>/` on the stick (`SHA256SUMS`, `MANIFEST.txt` in the
recovery OS's `ad5x-backup` format), while stock runs, so `usershare` is read
while mounted and `userdata` is left out. That is less than the image above:
take the full one too when you can.
