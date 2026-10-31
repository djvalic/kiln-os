# Recovery OS (slot A)

A small recovery and update system for the AD5X, meant for slot A
(`kernel` p1 + `rootfs` p2) while the main system (Kiln OS) lives in slot B
(`kernel2` p3 + `rootfs2` p4). Built on the laptop and tested under
qemu-user with fake devices (see "Tests"), and in use on the developer's
printer: it installs every Kiln OS update. Background on the slots and the boot loader: `docs/boot-slots.md`.

## Design

- **Boot flag unchanged.** The SPL boots slot B on `ota:kernel2` and
  slot A on anything else. The main OS's try-once (`S01ad5x-tryboot`) points
  the flag at A at the start of every boot and `S99ad5x-booted` points it
  back at B once start-up has finished. A main boot that fails after its init
  has started therefore lands in recovery at the next power cycle. Recovery
  never changes the flag at boot. Only a successful update, `ad5x-boot-main`
  or `ad5x-restore --set-flag` change it.
- **Same kernel** as the main OS (the printer's own stock 5.10.186 uImage in
  p1) and the same driver start-up. `S06ad5x-modules` is installed unchanged
  from `package/ad5x-system`: `ad5x-vendor ensure` (the printer's own vendor
  files in `/data/ad5x/vendor`, filled from the saved stock system or a stock
  slot when missing; `docs/install.md`, "Vendor files"), then utils and
  `gpio_backlight` first, stock's `driver_default_init_script.sh`,
  `tsc2007_touch` with stock's parameters, and `8821cu` from usershare if it
  is there.
- **Vendor-free image** (default build): no Flashforge/Ingenic files; drivers
  and board tools come from `/data/ad5x/vendor`, the kernel from p1. A private
  build can still bundle them (`buildroot/README.md`).
- **Size**: 6.9 MB squashfs (LZO; 6,946,816 bytes on 2026-10-17, vendor-free),
  including `unsquashfs` and SWUpdate's web page (1.6 MB). The slot holds
  100 MiB. There is no Python and no Klipper.

### Start-up (`/etc/init.d`)

| Script | What |
|---|---|
| `rcS` | The main image's rcS (boot trace). Recovery's `ad5x-bootlog` writes its trace into `ota` at **128 KiB**, so the main OS's trace at 64 KiB survives for diagnosis |
| `S01ad5x-recovery` | Saves the boot flag to `/run/ad5x/flag-at-boot` and creates `/dev/disk/by-partlabel/<GPT name>` links (mdev doesn't). A link is only made when the GPT entry matches the SPL's built-in table |
| `S05ad5x-data` | Mounts `userdata` read-write at `/data`. If the mount fails it runs one `e2fsck -p` and tries again; failing that, `/data` is a tmpfs. Stock's root password: usershare `/etc/shadow` hash bound over `/etc/shadow`. SSH host keys bound from `/data/ad5x/ssh/hostkeys`, the same keys as the main OS |
| `S06ad5x-modules` | The main OS's script (shared, see above): vendor files checked or filled (`ad5x-vendor ensure`), then the drivers from `/data/ad5x/vendor/module_driver`. Without vendor files: no display, touch or Ethernet, a message on the console and in the boot trace, start-up goes on |
| `S07ad5x-board` | PC11 heartbeat (stock `cmd_gpio`, from `/data/ad5x/vendor` through the `/usr/bin` wrapper), framebuffer on, recovery logo (`/usr/share/ad5x/recovery-logo.jpg`, or `/data/ad5x/recovery/logo.jpg`), backlight |
| `S10mdev` | The main image's (hotplug, so USB sticks appear) |
| `S41ad5x-eth` | The main OS's script: stock MAC from usershare `/MAC`, then DHCP or static from `/data/ad5x/network.conf` (`/usr/lib/ad5x/network.sh`) |
| `S42ad5x-wifi` | The main OS's script: Wi-Fi with the networks in `/data/ad5x/wpa_supplicant.conf` (made from stock's saved networks on the first start), unless `/data/ad5x/wifi.disable` exists or the Wi-Fi switch on the touch screen is off |
| `S50dropbear` | SSH, root login (stock's password, or a key in `/data/ad5x/ssh/authorized_keys`) |
| `S70swupdate` | SWUpdate daemon: web upload on **port 8080**, control socket `/tmp/sockinstctrl`, progress socket `/tmp/swupdateprog`, log `/run/ad5x/swupdate.log` |
| `S80ad5x-recovery-ui` | Starts `/usr/bin/ad5x-recovery-ui` (the touch UI, a separate package) if it is installed, and restarts it if it exits. Log `/run/ad5x/ui.log` |
| `S85ad5x-auto` | Starts `ad5x-recovery-auto` in the background (below). A file `/data/ad5x/recovery/noauto` turns it off |
| `S99ad5x-recovery-ready` | Writes `/run/ad5x/ready` |

### Network configuration (shared with the main OS)

`/data/ad5x/network.conf`, a shell-sourceable file:

```
MODE=dhcp|static          # dhcp when the file or MODE is missing
ADDRESS=192.168.1.50/24   # static: address/prefix
GATEWAY=192.168.1.1       # static, optional
DNS="192.168.1.1 1.1.1.1" # static, optional; written to /run/resolv.conf
IFACE=eth0                # optional
```

An invalid static setup falls back to DHCP and logs it. The stock MAC is
always set first.

## Updates (SWUpdate)

SWUpdate 2025.05 (Buildroot package), configured in
`package/ad5x-recovery/swupdate/swupdate.config`. It runs as a "single copy"
rescue-system updater that writes the *other* slot (B):

- **Signed images only.** The signature is RSA PKCS#1.5 with SHA-256 over
  `sw-description`, checked with mbedTLS against `/etc/swupdate/public.pem`.
  Every artifact carries a sha256 in the signed `sw-description`.
  `hardware-compatibility` `"1.0"` is checked against `/etc/hwrevision`
  (`ad5x 1.0`).
- **Handlers.** `raw` writes `/dev/disk/by-partlabel/rootfs2` and `kernel2`,
  and `shellscript` runs `ad5x-slot-b.sh` (in the .swu; source in
  `package/ad5x-recovery/swupdate/`).
- **Order** (SWUpdate's, images not `installed-directly`): the whole .swu is
  first unpacked into `/tmp` (RAM) and each artifact's sha256 is checked.
  Then the script's `preinst` step runs: it requires running from slot A,
  checks that `rootfs2`/`kernel2`/`ota` match the SPL table and that the
  by-partlabel links point at them, refuses a mounted rootfs2, and points the
  flag at A. An update without a kernel (the normal case, releases carry
  none) requires a uImage already in `kernel2`, which stays; if `kernel2`
  holds none, recovery copies its own kernel (p1, the printer's stock kernel)
  there first, read back. With no kernel in either, the update is refused
  before anything is written. Then the raw writes. Then `postinst`: it reads rootfs2 and
  kernel2 back and compares them with the sha256s and sizes from the signed
  `sw-description`, mounts rootfs2 read-only and requires `/etc/ad5x-release`
  and `/linuxrc`, and only then writes **`ota:kernel2`**. On any failure the
  flag stays on A (`postfailure` makes sure of it), so the printer stays in
  recovery.
- **Ways in:**
  1. **Web page**: `http://<printer>:8080`, drag the .swu in. "Restart"
     runs `swu-postupdate`, which reboots.
  2. **Drop folder**: copy `*.swu` to `/data/ad5x/update/` (e.g. with
     `scp` from the main OS, or with the main OS running), then boot
     recovery. At boot each file is installed (oldest first) and then
     renamed `*.swu.done` or `*.swu.failed`; after a success only that
     one is kept (older `.done`/`.failed` files are deleted, as the main
     OS does when it stages an update). The result goes to
     `/data/ad5x/update/last.log`. After a success the printer reboots into
     the main OS.
  3. **USB stick**: `.swu` files in the top directory of a FAT/ext4/exFAT
     partition. With a file named `ad5x-autoupdate` on the stick they are
     installed at boot. Each stick image is installed only once (its sha256
     goes to `/data/ad5x/update/applied.list`), so a bad image can't start
     an update-reboot loop. A log `ad5x-autoupdate.log` is written on the
     stick. Without the marker they are only offered: `ad5x-usb list`, the
     UI, or `ad5x-swu-apply`.
  4. **CLI/UI**: `ad5x-swu-apply FILE.swu`.

### Making a .swu (laptop)

```
tools/make_swu.sh                     # main image -> ./ad5x-main-<version>.swu (no kernel)
tools/make_swu.sh -o /tmp/x.swu -V 1.2 -r path/rootfs.squashfs
tools/make_swu.sh -k path/xImage ...  # PRIVATE only: also write this kernel to kernel2
```

The default rootfs is `buildroot/output/images/rootfs.squashfs`. Updates
carry **no kernel** by default: slot B keeps the printer's own stock kernel
(the only kernel there is belongs to Flashforge and must not be published).
`-k` adds one for private use (`xImage-stock` of a private build). The
script refuses a rootfs without `/etc/ad5x-release` or `/linuxrc`, or one
that is the recovery OS. Check a file before publishing it with
`tools/check_vendor_free.sh`.

### Keys

- **Private key**: `AD5X_SWU_KEY`, default
  `~/.config/ad5x/swupdate-private.pem`. Make it with
  `tools/make_swu.sh --genkey`, or:
  ```
  mkdir -p ~/.config/ad5x && chmod 700 ~/.config/ad5x
  openssl genrsa -out ~/.config/ad5x/swupdate-private.pem 2048
  openssl rsa -in ~/.config/ad5x/swupdate-private.pem -pubout \
      -out ~/.config/ad5x/swupdate-public.pem
  ```
  It must be **RSA-2048**: SWUpdate 2025.05's mbedTLS backend reads exactly
  256 signature bytes (`corelib/swupdate_rsa_verify_mbedtls.c`), so a 4096-bit
  signature fails as "Compatible SW not found". `make_swu.sh` checks this.
  **Never commit it.** `make_swu.sh` refuses a key path inside the repo.
- **Public key in the recovery image** (`board/ad5x-recovery/post-build.sh`):
  `AD5X_SWU_PUBKEY` if set, else `~/.config/ad5x/swupdate-public.pem`, else
  derived from the private key (`AD5X_SWU_KEY` or its default path).
  Without any of these the image is built with no key and SWUpdate doesn't
  start. The post-build refuses a private key given as the public one.
  Example build with a throwaway test key:
  ```
  AD5X_SWU_PUBKEY=/path/to/swupdate-public.pem \
    make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot
  ```
  Changing keys means rebuilding and reinstalling the recovery image.

## CLI tools (interface for scripts and the touch UI)

All are in `/usr/bin`, take `-h`/`--help`, and print one line per step
(`name: ...`). They exit 0 on success and non-zero on failure. The final
line is machine-checkable. They share `/usr/lib/ad5x-recovery/recovery.sh`.

| Command | What | Success line |
|---|---|---|
| `ad5x-status [--slots]` | State as `key=value` lines: `release slot root flag flag_at_boot net_mode net_if net_ip ssh swupdate web_port ui update_pending update_last auto stock_saved vendor usb data main_trace`; with `--slots` also `slot_a`/`slot_b` (`ad5x <release>`, `recovery <release>`, `stock`, `empty`, `unknown`) | (always 0) |
| `ad5x-swu-apply [--check] [--reboot] FILE.swu` | Install a .swu. It goes through the daemon when it runs, so progress appears on `/tmp/swupdateprog`; otherwise it runs swupdate itself. `--check` verifies only (signature, description, hashes) | `swu-apply: OK` / `swu-apply: CHECK OK` / `swu-apply: FAILED ...` |
| `ad5x-boot-main [--no-reboot] [--force]` | Flag → B and reboot, after checking that kernel2 is a uImage and rootfs2 holds a system | `boot-main: boot flag ota:kernel2` |
| `ad5x-backup [--all] [--no-boot] [--parts "..."] [--dry-run] [DEST]` | Raw images of `boot` (first MiB: GPT, SPL, U-Boot), `kernel rootfs kernel2 rootfs2 ota usershare`, plus `userdata` with `--all` (with /data remounted read-only meanwhile). DEST defaults to the first USB stick. Output `DEST/ad5x-backup-<date>-<n>/`: `NAME.img`, split into 1 GiB pieces `NAME.img.000…` on FAT when ≥ 4 GiB, plus `SHA256SUMS` and `MANIFEST.txt`. Every image is read back and checked | `backup: OK <dir>` |
| `ad5x-restore [--dry-run] [--i-know] [--set-flag A\|B] [--reboot] SRC PART[=FILE]...` | Write images back. Checks: SHA256SUMS, size, squashfs/uImage magic, SPL table, mounted state. Read-back after writing. Refuses `kernel`, `rootfs` (this recovery, p1/p2) and `boot` without `--i-know`, and refuses the running slot in any case. `userdata`: `/data` is unmounted first, and the source can't be on it | `restore: OK` |
| `ad5x-restore-stock [--dry-run] [--no-flag] [--reboot] [DIR]` | Writes the stock system saved by the main OS's `ad5x-update --replace-stock` (`/data/ad5x/stock/{rootfs.squashfs,kernel.img,SHA256SUMS}`) into slot B, then sets flag → B | `restore: OK` |
| `ad5x-usb mount [WAIT] \| list \| umount` | Mounts sticks at `/run/ad5x/usb/<dev>`. `list` prints one line per partition: `dev= mnt= fs= swu=a.swu,b.swu autoupdate=0/1 rescue_root=0/1 rescue_boot=0/1 rescue_flash=0/1` | (list output) |
| `ad5x-usb-rescue boot [--dry-run] [DEV]` / `flash [--dry-run] [--no-reboot] [DIR]` | USB rescue (below) | `rescue: running` / reboot |
| `ad5x-recovery-auto` | The boot-time actions (drop folder, USB autoupdate, rescue markers). Normally started by S85 | writes `/run/ad5x/auto.done` |
| `ad5x-bootlog TEXT` | Adds a line to the boot trace (ota at 128 KiB) | |

### Notes for the touch UI (`ad5x-recovery-ui`)

- Home screen: `ad5x-status`. Show `net_mode` (dhcp/static) and `net_ip`,
  `slot_b`, `flag_at_boot` and `main_trace` (the last step the main OS
  reached: why we are in recovery), `update_last`, and whether `swupdate`
  and `ssh` are running. Web upload is at `http://<net_ip>:8080`.
- Progress: connect to SWUpdate's progress socket `/tmp/swupdateprog` (the
  `progress_msg` stream, as `swupdate-progress` does). It reports updates
  from any source: web, drop folder, USB, `ad5x-swu-apply`.
- Actions: run the CLI tools above and show their stdout. The last line
  tells the result. Long jobs (`ad5x-backup`, `ad5x-restore`) print one line
  per partition.
- USB: `ad5x-usb mount 0` then `ad5x-usb list`. Offer `swu=` files
  (`ad5x-swu-apply`), backup to the stick, and rescue if
  `rescue_root=1`.
- Before `ad5x-usb-rescue boot` the UI is stopped (S80 stop), so the stick's
  own UI can take the framebuffer.
- Reboot to main: `ad5x-boot-main`.

## USB rescue ("ultimate recovery")

The SPL boots the eMMC only, so a USB system has to be started from a
running Linux. This recovery is that Linux. Markers go in the top directory
of any partition of the stick:

| Marker | At boot (`ad5x-recovery-auto`) |
|---|---|
| `ad5x-autoupdate` | Install the stick's `.swu` files (once each, see above) |
| `ad5x-rescue-flash` | `ad5x-usb-rescue flash`: write `rootfs.squashfs` (+ `kernel.img`, `xImage` or `uImage` if present, + `SHA256SUMS` if present) from that partition into slot B through `ad5x-restore` (all checks, read-back), set flag → B, reboot. **Unsigned**: having the stick in the printer is the trust |
| `ad5x-rescue-boot` | `ad5x-usb-rescue boot`: chroot into the stick's ext4 root that has `/etc/ad5x-release` (`usb-test.img`'s `AD5XROOT` works as is) and run its `rcS` with `AD5X_USB=1`, the same "USB test mode" `flashforge_init.sh` uses on stock. `/dev`, `/proc`, `/sys`, `/data` and usershare (read-only at `/tmp/usershare`) are shared. Recovery's network, SSH and SWUpdate stay up. The recovery UI is stopped. Reboot to leave |

`switch_root` is not possible: the root is not an initramfs and BusyBox
init is PID 1, so a chroot is used, as `flashforge_init.sh` does. Without a
marker nothing happens automatically. `ad5x-usb list` and the UI show what
is on the stick.

## Install onto slot A (by hand; how it was done on the first unit)

A printer on stock firmware is installed with the installer instead
(`docs/install.md`: USB stick or SSH; it writes both slots and saves stock).
The steps below are the manual way used on the first unit.

Prerequisites: a full eMMC backup on the laptop (done, `docs/emmc-backup.md`),
and the main OS running in slot B. Slot A currently holds stock.

1. **Save stock first** (from the main OS in slot B, slot A idle):
   ```
   ssh root@ad5x.home 'mkdir -p /data/ad5x/stock && cd /data/ad5x/stock &&
     used=$(od -An -t u8 -j 40 -N 8 /dev/mmcblk0p2 | tr -d " ") &&
     head -c $used /dev/mmcblk0p2 > rootfs.squashfs &&
     cat /dev/mmcblk0p1 > kernel.img &&
     sha256sum rootfs.squashfs kernel.img > SHA256SUMS'
   ```
   Also copy these to the laptop. This is the same layout `ad5x-update
   --replace-stock` writes, so `ad5x-restore-stock` can use it later.
2. Check the image: `head -c 4` is `hsqs`, size ≤ 100 MiB, and it contains
   `/etc/ad5x-recovery`.
3. From the main OS (root on p4): check `/proc/cmdline` has
   `root=/dev/mmcblk0p4`, that p2 is not mounted, and that the GPT start
   sectors match the SPL table (`docs/boot-slots.md`). Then write
   `rootfs.squashfs` to `/dev/mmcblk0p2` with `dd ... conv=fsync`, drop
   caches, and compare the read-back sha256. p1 already holds the stock
   kernel (the same one), so leave it. The main OS's `ad5x-update` would do
   all of this (`ad5x-update --replace-stock IMAGE SHA256`), **but it also
   flips the flag to A**. That is fine (it boots recovery once to test it;
   `ad5x-boot-main` then goes back), but be aware of it.
4. Test: `echo ota:kernel > /dev/mmcblk0p5; reboot`. Recovery should come up
   with SSH, the logo and `http://ad5x.home:8080`. Then `ad5x-boot-main`.

Going back to stock in slot A: from the main OS, write
`/data/ad5x/stock/rootfs.squashfs` to p2 and `kernel.img` to p1 (or use the
laptop backup).

## Main OS in slot A

Some printers run the main OS from slot A (`root=/dev/mmcblk0p2`, boot flag
`ota:kernel`) instead of slot B. Updates don't support this layout yet.
`ad5x-update` refuses with "slot A doesn't hold the recovery OS" or "slot A
holds a main OS, not stock or recovery: refusing", and says where this
section is.

Nothing is written blind. The steps below read first, make a backup, and
only then (if at all) write. Nothing here is tested on hardware.

**1. Triage (read only).** Run these on the printer and note the output:

```
cat /proc/cmdline                          # root=/dev/mmcblk0p2: main OS in slot A
head -c 11 /dev/mmcblk0p5 | tr -d '\0\n'  # boot flag: ota:kernel = A, ota:kernel2 = B
cat /etc/ad5x-release                      # which Kiln OS release is running
ls -l /data/ad5x/stock                     # saved stock system (rootfs.squashfs, kernel.img, SHA256SUMS)?
```

**2. Back up the eMMC first.** Copy the whole eMMC to a stick or the laptop
as described in `docs/emmc-backup.md`. Check the copy before going on. The
installer's stick backup covers only the first MiB and partitions p1 to p6,
so take the full image when you can.

**3a. If `/data/ad5x/stock` exists:** check the saved stock system:

```
ad5x-restore-stock --dry-run
```

It checks `rootfs.squashfs` and `kernel.img` against `SHA256SUMS` and writes
nothing. A run without `--dry-run` writes slot B and sets the boot flag to
B, so the printer boots stock. Do that only after reading the dry-run output
and deciding to. It is not part of this safe path.

**3b. If `/data/ad5x/stock` does not exist:** there is no saved stock to put
back. Use the USB-stick rescue in the "USB rescue" section above. The
`ad5x-rescue-boot` marker only chroots into the stick's root for
inspection. `ad5x-rescue-flash` writes slot B and sets the flag, so it is
not a dry run: use it only with an image you have checked and with the
backup from step 2 in hand.

Don't run `ad5x-update --install-recovery` or `--replace-stock` from slot A.
The script refuses there.

## Updates of the recovery OS itself

The recovery OS travels with the main OS (since v0.0.5). Each main image
carries the recovery image of the same release in `/usr/share/ad5x/recovery`
(`rootfs.squashfs`, `.sha256`, and `rootfs.id`, the recovery's content ID);
the build makes the recovery OS first and puts it into the main image
(`board/ad5x/post-build.sh`, `AD5X_RECOVERY_IMAGE`; `tools/release.sh`
refuses a main image that carries another one).

After a complete start (boot flag back on slot B), `S99ad5x-update-recovery`
compares slot A's `/etc/ad5x-recovery-id` with the carried one. Another ID,
or none (recovery OSes before v0.0.5), and it writes the carried image with
`ad5x-update --install-recovery` in the background: sha256 check, write,
read-back, at most 3 tries per image. Log: `/data/ad5x/recovery/update.log`.
`/data/ad5x/recovery-update.disable` turns it off.

The content ID is a sha256 over every path, mode and file in the recovery
tree except `/etc/ad5x-release` (which has the build date), so the slot is
only rewritten when the recovery OS really changed, not at every update.
`BR2_REPRODUCIBLE=y` keeps unchanged programs byte-identical between builds
(BusyBox would otherwise embed its build time).

A write cut short must not leave a slot A the printer would boot:
- `ad5x-update` writes the squashfs superblock last (block 0 zeroed first,
  then the rest, then block 0), so a partial write has no superblock;
- `S01ad5x-tryboot` doesn't point the boot flag at a slot whose root has no
  superblock;
- staging a main OS update (`ad5x-update FILE`, Fluidd's Update) waits for a
  running recovery write before pointing the boot flag at slot A;
- `S99ad5x-update-recovery` writes a slot A without a superblock again at
  the next start.
Only stock in slot A is never touched by it (`S99ad5x-install-recovery` is
the first install's step, `--replace-stock`).

A stock firmware update (an `AD5X-*.tgz` stick) run from slot B would write
slot A. Never apply one.

## Tests (laptop)

`tools/test_recovery.sh [SWU]` unpacks `output-recovery/images/rootfs.tar`
and runs the image's own scripts and BusyBox/SWUpdate binaries under
qemu-user in the bwrap sandbox (`tools/qemu_stock.sh`: empty `/dev`, no
network). The eMMC is faked by a sysfs tree with the seven GPT partitions
(names, start sectors, sizes as on the printer) and sparse files.
mount/umount/reboot are shims. It checks: every tool's `--help`; S01 links;
`ad5x-status`; `ad5x-backup` (dry run, refusing to back up userdata into
itself, a real backup with sha256 checks); `ad5x-restore` (refusals of p1/p2
and boot, sha256 mismatch, non-squashfs, a real restore with read-back and
`--set-flag`); `ad5x-restore-stock --dry-run`; `ad5x-boot-main`; USB listing
and rescue dry runs. With a .swu it also checks: `swupdate -c` signature and
description check; a tampered image and an image checked against another
key are refused; a full install into the fake slot B with flag → B; a failed
post-install check leaves the flag on A; and the boot-time drop-folder
install renames the file, logs, and reboots.

Rootfs-only updates (the default `.swu`/`.zip`, no kernel) are also
checked: `kernel2` is kept; an empty `kernel2` gets slot A's kernel; with no
kernel anywhere the update is refused before writing and the flag stays on
A. The fake kernels are stand-in uImage headers (no stock kernel needed).
Result on 2026-10-17: 73 checks pass (vendor-free images, rootfs-only .swu and
.zip). Vendor files and the installer: `tools/test_install.sh`
(`docs/install.md`).

Result on 2026-10-16: 60 checks pass. A second run in the sandbox started
`S70swupdate`: both sockets were created, the web page answered on
127.0.0.1:8080, `ad5x-swu-apply` installed through the daemon with
`swupdate-client`, `swupdate-progress` showed the steps, and the flag went to
`ota:kernel2`.

Not testable without the printer: real mounts, the drivers and board tools,
the network, and the web upload.

## Touch UI (`ad5x-recovery-ui`)

LVGL v9 program on the panel (`/dev/fb0`, 800x480, 32 bpp) with the
TSC2007 touch screen (evdev, found by its name `TSC2007 Touchscreen`).
Source in `recovery-ui/`, Buildroot package `package/ad5x-recovery-ui`
(LVGL 9.5.0 sources from `package/ad5x-lvgl`, release tarball with
sha256), on in `ad5x_recovery_defconfig`, started by `S80ad5x-recovery-ui`.
Dark theme in the boot logo's colours (gradient, accent 74,144,226),
Noto Sans (subset embedded, `recovery-ui/fonts/`, OFL), buttons at least
60 px high. Not tried on the printer yet.

### Screens

| Screen | What |
|---|---|
| Home | "Kiln OS — Recovery"; IP (`net_ip`, `net_if`, `net_mode`) and `ssh root@<ip>`; what slot B holds (`slot_b`) and where the next start goes (`flag`); how far the main OS's last start got (`main_trace`); `update_last`; a chip for SWUpdate. Eight tiles: Boot main OS, Install update, Back up, Restore, Restore stock, Network / SSH, Logs, Reboot / Power |
| Install update | USB card; `.swu` files in `/data/ad5x/update/` and the top folder of mounted sticks; the upload URL `http://<ip>:8080`. **Check** runs `ad5x-swu-apply --check`; **Install** (two confirmations) runs `ad5x-swu-apply FILE` |
| Back up | USB card; switch "Also userdata"; **Dry run** / **Start backup**: `ad5x-backup [--dry-run] [--all] <stick>` (the tool makes `ad5x-backup-<date>-<n>/`) |
| Restore | USB card; the stick's `ad5x-backup-*` folders (newest first); a checkbox per `NAME.img[.NNN]` in it. `kernel`, `rootfs` (recovery's own slot) and `boot` are greyed out: `ad5x-restore` refuses them without `--i-know`, which is left to the command line. **Check**: `ad5x-restore --dry-run SRC PART...`; **Restore** (two confirmations): `ad5x-restore SRC PART...` |
| Restore stock | Says whether `/data/ad5x/stock` holds a saved system (`stock_saved`). **Check**: `ad5x-restore-stock --dry-run`; **Restore stock firmware** (two confirmations): `ad5x-restore-stock`, then a Reboot button |
| Network / SSH | Address, name, `ssh root@<ip>`, upload URL with a QR code, recovery `release`, and what `ad5x-usb list` reports (updates on the stick, rescue system/markers) |
| Logs | Scrollable, monospace: this session (every command and its output), `/data/ad5x/update/last.log`, `/run/ad5x/swupdate.log`, the system log (`logread`) |
| Reboot / Power | Boot main OS (`ad5x-boot-main`), Reboot, Shut down (one confirmation each) |
| Job | Every command runs here: title, spinner, step text, progress bar, live output, Stop (backups and checks only), then a green or red result with the command's last line ("backup: OK ...", "swu-apply: FAILED ..."), and Boot main OS or Reboot where it fits. Back is disabled while it runs |

An update started anywhere else (browser upload, drop folder, USB
autoupdate) opens the Job screen by itself and follows it on SWUpdate's
progress socket.

**Destructive actions** (install, restore, restore stock) ask twice. The
second dialog swaps the buttons (the confirm button sits where Cancel was,
so a double tap can't go through both) and arms its button only after 2 s.
Boot main OS, Reboot and Shut down ask once. Backups, checks and dry runs
don't ask.

### Interface it relies on

All commands and paths are in one table, `recovery-ui/src/commands.c`; any
entry can be overridden without rebuilding with `AD5X_RUI_<NAME>` in the
environment (for example `AD5X_RUI_CMD_BACKUP='ad5x-backup --no-boot
{DRY} {ALL} {DEST}'`). Placeholders are shell-quoted.

| Entry | Default |
|---|---|
| `CMD_INSTALL` / `CMD_INSTALL_CHECK` | `ad5x-swu-apply {FILE}` / `ad5x-swu-apply --check {FILE}` |
| `CMD_BACKUP` | `ad5x-backup {DRY} {ALL} {DEST}` (DEST = the stick's mount point) |
| `CMD_RESTORE` | `ad5x-restore {DRY} {SRC} {PARTS}` |
| `CMD_RESTORE_STOCK` | `ad5x-restore-stock {DRY}` |
| `CMD_BOOT_MAIN` | `ad5x-boot-main` |
| `CMD_REBOOT` / `CMD_POWEROFF` | `sync; reboot` / `sync; poweroff` |
| `CMD_USB_MOUNT` / `CMD_USB_UMOUNT` / `CMD_USB_LIST` | `ad5x-usb mount 0` / `ad5x-usb umount` / `ad5x-usb list` |
| `CMD_STATUS` / `CMD_STATUS_SLOTS` | `ad5x-status` every 5 s / `ad5x-status --slots` at start and after each job (not while a job runs) |
| `CMD_SYSLOG` | `logread` (or `/var/log/messages`), last 300 lines |
| `PATH_SWU_SOCKET` | `/tmp/swupdateprog` |
| `PATH_UPDATE_DIR`, `PATH_LAST_LOG`, `PATH_SWU_LOG` | `/data/ad5x/update`, `.../last.log`, `/run/ad5x/swupdate.log` |
| `PATH_MOUNTS`, `PATH_SYS_BLOCK` | `/proc/mounts` (mounted sticks: `/dev/sd*` with vfat/exfat/ext4), `/sys/class/block` (sticks not mounted yet) |
| `PATH_OTA`, `PATH_MAIN_ROOTFS` | empty = the GPT partitions `ota` / `rootfs2`, read only as a fallback when `ad5x-status` gives no `flag` / `slot_b` |
| `PATH_BACKUP_PREFIX` | `ad5x-backup-` |
| `PATH_TOUCH_NAME`, `PATH_FBDEV` | `TSC2007 Touchscreen`, `/dev/fb0` |

- Commands run in their own process group (`/bin/sh -c`, stdin
  `/dev/null`, stdout and stderr together); a reader thread collects the
  output, and the UI polls it every 250 ms, so the screen never waits for
  a command. Quick queries (`ad5x-status`, `ad5x-usb`, logs) run the same
  way. Exit status 0 is success; the last line is shown as the result.
- Progress bar: an install takes it from SWUpdate. Other commands may print
  `@progress <0-100> [text]` or `@step <text>` lines (not shown in the
  log); otherwise the last `NN%` on a line is used, otherwise the bar is
  hidden and the spinner turns. `\r` progress lines (dd style) overwrite
  themselves. The current tools print one line per partition, so backups
  and restores show the line, not a percentage, unless they add `@progress`.
- A page with a USB card runs `ad5x-usb mount 0` once by itself when a
  stick is plugged in but not mounted; Eject runs `ad5x-usb umount`.
- SWUpdate progress: the Buildroot build links SWUpdate's own
  `libswupdate` (`progress_ipc_connect_with_path`, `progress_ipc_receive`)
  when SWUpdate is in the image; otherwise (laptop builds) a copy of the
  same small protocol (progress API 2.0, `src/swu_ipc_compat.h`). The
  connection is retried every second while the socket is missing.
- Touch: LVGL's evdev driver scales the device's ABS range to 800x480;
  stock's `tsc2007_touch` parameters already flip Y. If the mapping is off:
  `AD5X_RUI_TOUCH_CAL="minx miny maxx maxy"` (swap a pair to invert) and
  `AD5X_RUI_TOUCH_SWAP=1`. Display: page 0 of the double buffer is panned
  in at start (yoffset 0); LVGL draws XRGB8888 into it.

### Laptop builds and screenshots

```
cd recovery-ui
make                        # headless build (LVGL downloaded once to build/)
make shots SHOTS=/tmp/x     # every screen as PNG, with simulated data
make sim                    # SDL2 window, mouse = touch, same simulation
```

`sim/run-sim.sh` builds a fake recovery OS under `$TMPDIR/ad5x-rui-sim`
(update files, a "mounted" stick with two backup sets, stand-ins for the
`ad5x-*` tools that only print) and points every table entry at it; nothing
real is touched. `--shots DIR` also works with the MIPS binary under
qemu-user (`QEMU_LD_PREFIX=buildroot/output-recovery/target`).
`fonts/gen_fonts.py` regenerates the font subsets.

### Open items (UI)

- Not run on the panel yet: colour order of the 32 bpp framebuffer, the
  touch mapping and the speed of a full redraw on the X2600 are unchecked.
- No percentage for backups/restores until the tools print `@progress`.
- USB rescue (`ad5x-usb-rescue boot|flash`) is shown, not offered as a
  button.

## Open update mode (default since 2026-10-16)

The recovery OS accepts unsigned `.swu` files: no key to manage, the owner
installs what they like. Integrity checks stay: every artifact's sha256 in
`sw-description` (SWUpdate `HASH_VERIFY`), and `ad5x-slot-b.sh` reads the
written slot back and requires `/etc/ad5x-release` and `/linuxrc` before the
boot flag changes; a corrupted file is refused with the flag unchanged.
`tools/make_swu.sh` builds unsigned files; `--sign` signs.

Signed mode (optional): set `BR2_PACKAGE_SWUPDATE_CONFIG` to
`package/ad5x-recovery/swupdate/swupdate-signed.config` and build the recovery
image with `AD5X_SWU_SIGNED=1` (public key from `AD5X_SWU_PUBKEY` or
`~/.config/ad5x/swupdate-public.pem`); then `make_swu.sh --sign`.

## .zip updates

`tools/make_swu.sh --zip` (or `--both`) writes a plain zip next to / instead
of the `.swu`:

```
ad5x-main-VERSION.zip
  version.txt        "Kiln OS main system, version VERSION"
  SHA256SUMS         sha256 of the files below
  kernel.uimage      only in private updates (make_swu.sh -k); releases have none
  rootfs.squashfs    the main OS
```

The recovery OS takes it everywhere a `.swu` goes except SWUpdate's own web
page (port 8080, `.swu` only): `/data/ad5x/update/*.zip` at boot, USB sticks,
the touch UI, `ad5x-swu-apply FILE.zip`, and the main OS's `ad5x-update
FILE.zip`. `ad5x-zip-to-swu` unpacks it under `/data/ad5x/update/.work`,
checks `SHA256SUMS`, and packs the same `sw-description` (shared generator
`swupdate/mk-sw-description.sh`) and install script a laptop-built `.swu`
has, so both formats install the same way. Needs BusyBox `cpio -o`
(`board/ad5x-recovery/busybox.fragment`).

## Install log (unit ad5x.home, 2026-10-16)

1. From the main OS in slot B: `ad5x-update --install-recovery --replace-stock`
   wrote the recovery image (7.0 MB, sha256 `076a7340…`) into slot A. Stock root
   and kernel were saved first to `/data/ad5x/stock/` (rootfs `02d814b2…`, kernel
   `3144440…`, which matches the eMMC backup).
2. Flag `ota:kernel`, then power cycle: recovery booted in 11.2 s with DHCP
   192.168.1.50, SSH, the SWUpdate web page on 8080, and the touch UI. The user
   confirmed touch works.
3. Main OS zip `202610161726-c5bbe689` (69,243,794 bytes, sha256 `589ef2c4…`) was
   copied over SSH and installed with `ad5x-swu-apply`:
   - preinst wrote slot B;
   - postinst passed: "slot B verified (AD5X open OS 2026-10-16)", flag `ota:kernel2`;
   - result: `SWUPDATE successful`.
4. Reboot: main OS came up from `root=/dev/mmcblk0p4` in about 25 s (SSH).
   dropbear, klippy, moonraker and helix-screen are running, and Klipper is `ready`.
   S99 left the flag on `ota:kernel2`.
