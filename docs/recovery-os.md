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
- **Stock kernel** (the printer's own stock 5.10.186 uImage in p1, what
  the main OS starts with before it chainloads ours) and the same driver
  start-up. The userspace also runs on our 6.6 (see "Our kernel" below),
  which Kiln's own U-Boot starts from p1 once the main OS has put it there.
  `S06ad5x-modules` is installed unchanged
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
| `S01ad5x-recovery` | Saves the boot flag to `/run/ad5x/flag-at-boot` and creates `/dev/disk/by-partlabel/<GPT name>` links. A link is only made when the GPT entry matches the SPL's built-in table (udev makes none here: the recovery image replaces its `60-persistent-storage.rules`) |
| `S05ad5x-data` | Mounts `userdata` read-write at `/data`. If the mount fails it runs one `e2fsck -p` and tries again; failing that, `/data` is a tmpfs. Root's password: the hash saved with `passwd`/`ad5x-passwd` (`/data/ad5x/ssh/root-password`, checked as in the main OS, `lib/rootpw.sh`), else stock's usershare `/etc/shadow` hash, bound over `/etc/shadow`. SSH host keys bound from `/data/ad5x/ssh/hostkeys`, the same keys as the main OS |
| `S05ad5x-watchdog` | The main OS's script (shared): the hardware watchdog feeder, on Kiln's 6.6 only (see "Our kernel"); nothing on the stock kernel. `/data/ad5x/watchdog.disable` turns it off |
| `S06ad5x-modules` | The main OS's script (shared, see above): vendor files checked or filled (`ad5x-vendor ensure`), then the drivers from `/data/ad5x/vendor/module_driver`. Without vendor files: no display, touch or Ethernet, a message on the console and in the boot trace, start-up goes on |
| `S07ad5x-board` | PC11 heartbeat (stock `cmd_gpio`, from `/data/ad5x/vendor` through the `/usr/bin` wrapper), framebuffer on, recovery logo (`/usr/share/ad5x/recovery-logo.jpg`, or `/data/ad5x/recovery/logo.jpg`), backlight. On our 6.6: see "Our kernel" |
| `S10udevd` | The main image's eudev (hotplug, so USB sticks appear); network interfaces keep the names `eth0` and `wlan0`; the owner's rules in `/data/ad5x/udev/rules.d` are not used here |
| `S41ad5x-eth` | The main OS's script: stock MAC from usershare `/MAC`, then DHCP or static from `/data/ad5x/network.conf` (`/usr/lib/ad5x/network.sh`) |
| `S42ad5x-wifi` | The main OS's script: Wi-Fi with the networks in `/data/ad5x/wpa_supplicant.conf` (made from stock's saved networks on the first start), unless `/data/ad5x/wifi.disable` exists. The main OS's Wi-Fi switch (HelixScreen's `wifi_enabled`) is not applied here: recovery has no HelixScreen, so Wi-Fi stays on |
| `S50dropbear` | SSH, root login (the main OS's password, set with `passwd`, else stock's; or a key in `/data/ad5x/ssh/authorized_keys`) |
| `S70swupdate` | SWUpdate daemon: web upload on **port 8080**, control socket `/tmp/sockinstctrl`, progress socket `/tmp/swupdateprog`, log `/run/ad5x/swupdate.log` |
| `S80ad5x-recovery-ui` | Starts `/usr/bin/ad5x-recovery-ui` (the touch UI, a separate package) if it is installed, and restarts it if it exits, with the main OS's touch calibration from `/data/ad5x/recovery/touch-cal` when it is usable and the running kernel's touch units (see Touch UI). Log `/run/ad5x/ui.log` |
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

The recovery OS stays on `wpa_supplicant` and `udhcpc` (`S41ad5x-eth`,
`S42ad5x-wifi`, `lib/network.sh`); it has no NetworkManager. The main OS
runs NetworkManager by default ([network.md](network.md)), but it reads the
same `network.conf` and `wpa_supplicant.conf` at every start and writes the
Wi-Fi networks joined, changed or forgotten on the touch screen back into
`wpa_supplicant.conf`, so the recovery OS joins the same networks. The
guard in `S41`/`S42` that skips them on the main OS's NetworkManager reads
`/run/ad5x-network/mode`, which only the main OS's `S40ad5x-network`
writes: here they always run.

## Updates (SWUpdate)

SWUpdate 2025.05 (Buildroot package), configured in
`package/ad5x-recovery/swupdate/swupdate.config`. It runs as a "single copy"
rescue-system updater that writes the *other* slot (B):

- **Unsigned by default, signing optional.** Every artifact carries a
  sha256 in `sw-description`, which SWUpdate checks (`HASH_VERIFY`). A
  recovery image built for signed updates (see "Open update mode" below)
  also requires an RSA PKCS#1.5 signature with SHA-256 over
  `sw-description`, checked with mbedTLS against `/etc/swupdate/public.pem`.
  `hardware-compatibility` `"1.0"` is checked against `/etc/hwrevision`
  (`ad5x 1.0`).
- **Handlers.** `raw` writes `/dev/disk/by-partlabel/rootfs2` and `kernel2`,
  and `shellscript` runs `ad5x-slot-b.sh` (in the .swu; source in
  `package/ad5x-recovery/swupdate/`).
- **Order** (SWUpdate's, images not `installed-directly`): the whole .swu is
  first unpacked and each artifact's sha256 is checked. It is unpacked into
  `/data/ad5x/swupdate-tmp` on the data partition (SWUpdate's `TMPDIR`; a
  run of `ad5x-swu-apply` without the daemon uses
  `/data/ad5x/swupdate-apply.PID`), so a 256 MiB board doesn't hold the
  root filesystem image in RAM. Only when the data partition isn't ext4
  mounted read-write or has less than 256 MiB free is it `/tmp` (RAM), as
  before. SWUpdate deletes the unpacked files after each install; whatever a
  power cut leaves is deleted at the next start of `S70swupdate`. The
  control and progress sockets stay in `/tmp` (`swupdate.config`).
  Then the script's `preinst` step runs: it requires running from slot A,
  checks that `rootfs2`/`kernel2`/`ota` match the SPL table and that the
  by-partlabel links point at them, refuses a mounted rootfs2, and points the
  flag at A. An update without a kernel (the normal case, releases carry
  none) requires a uImage already in `kernel2`, which stays; if `kernel2`
  holds none, recovery copies its own kernel (p1, the printer's stock kernel)
  there first, read back. With no kernel in either, the update is refused
  before anything is written. Then the raw writes. Then `postinst`: it reads rootfs2 and
  kernel2 back and compares them with the sha256s and sizes from the
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
     the main OS. A file still there when the main OS starts again was
     staged before that start: the main OS renames it `*.stale`, and the
     recovery OS doesn't install it ([updates.md](updates.md), "Staged
     updates"); boot recovery in the same main OS session as the copy.
  3. **USB stick**: `.swu` files or release `.zip` files in the top
     directory of a FAT32 or ext4 partition (not exFAT). With a file named
     `ad5x-autoupdate` on the stick they are installed at boot of the
     recovery OS; the main OS never reads the stick, so the printer has to
     start the recovery OS first (`docs/updates.md`, "From a USB stick",
     says how). Each stick image is installed only once (its sha256
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
carry **no kernel** by default: slot B keeps the kernel it has (with
Flashforge's boot loader the printer's own stock kernel, which belongs to
Flashforge and must not be published).
`-k` adds one for private use (`xImage-stock` of a private build). The
script refuses a rootfs without `/etc/ad5x-release` or `/linuxrc`, or one
that is the recovery OS. Check a file before publishing it with
`tools/check_vendor_free.sh`.

### Keys (only for signed updates)

Releases are unsigned and the default recovery image takes them without a
key. The keys below matter only if you build a recovery image with signing
on (`AD5X_SWU_SIGNED=1`, "Open update mode" below; `docs/update-signing.md`).

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
- **Public key in the recovery image** (`board/ad5x-recovery/post-build.sh`,
  only with `AD5X_SWU_SIGNED=1`): `AD5X_SWU_PUBKEY` if set, else `~/.config/ad5x/swupdate-public.pem`, else
  derived from the private key (`AD5X_SWU_KEY` or its default path).
  With signing on but none of these, the image is built with no key and
  SWUpdate doesn't start; without `AD5X_SWU_SIGNED=1` no key goes in and
  the image takes unsigned updates. The post-build refuses a private key given as the public one.
  Example build with a throwaway test key:
  ```
  AD5X_SWU_SIGNED=1 AD5X_SWU_PUBKEY=/path/to/swupdate-public.pem \
    make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot
  ```
  Changing keys means rebuilding and reinstalling the recovery image.

## CLI tools (interface for scripts and the touch UI)

All are in `/usr/bin`, take `-h`/`--help`, and print one line per step
(`name: ...`). They exit 0 on success and non-zero on failure. The final
line is machine-checkable. They share `/usr/lib/ad5x-recovery/recovery.sh`.

| Command | What | Success line |
|---|---|---|
| `ad5x-status [--slots]` | State as `key=value` lines: `release slot root flag flag_at_boot net_mode net_if net_ip ssh swupdate web_port ui update_pending update_last auto stock_saved vendor usb data return_stock return_stock_open bootloader_install bootloader_kind bootloader_open main_trace` (`auto`: `running`, `done` or `off`, the start-up actions still running, done, or skipped by `/data/ad5x/recovery/noauto`; `return_stock`: `none`, `unfinished` or `done`, from `/data/ad5x/return-stock/state`; `return_stock_open`: `request`, `usb`, `resume` or empty, the page to open at start); `bootloader_install`: `none`, `started`, `installed`, `verified`, `unverified` or `removed` (Return to Flashforge firmware took Kiln's U-Boot out; `/data/ad5x/bootloader/state`); `bootloader_kind`: `install`, `upgrade` or empty (what that record's run was); `bootloader_open`: `result`, `resume` or empty; with `--slots` also `slot_a`/`slot_b` (`ad5x <release>`, `recovery <release>`, `stock`, `empty`, `unknown`) and `bootloader` (`flashforge`, `kiln`, `kiln-spl`, `unknown`) / `bootloader_upgrade` (`yes`, `no`) / `bootloader_offer` (`yes`, `no`), and with Kiln's boot loader `bootloader_build` (its build date) / `bootloader_carries` (the build this recovery OS carries, empty without images) / `bootloader_same` (`yes`, `no`) / `bootloader_carries_newer` (`yes`, `no`, `unknown`: the carried build later than the disk's by build time) | (always 0) |
| `ad5x-swu-apply [--check] [--reboot] FILE.swu` | Install a .swu. It goes through the daemon when it runs, so progress appears on `/tmp/swupdateprog`; otherwise it runs swupdate itself. `--check` verifies only (signature, description, hashes) | `swu-apply: OK` / `swu-apply: CHECK OK` / `swu-apply: FAILED ...` |
| `ad5x-boot-main [--no-reboot] [--force]` | Flag → B and reboot, after checking that kernel2 is a uImage and rootfs2 holds a system. Refused (even with `--force`) while a Return to Flashforge firmware is unfinished | `boot-main: boot flag ota:kernel2` |
| `ad5x-backup [--all] [--no-boot] [--parts "..."] [--dry-run] [DEST]` | Raw images of `boot` (first MiB: GPT, SPL, U-Boot), `kernel rootfs kernel2 rootfs2 ota usershare`, plus `userdata` with `--all` (with /data remounted read-only meanwhile). DEST defaults to the first USB stick. Output `DEST/ad5x-backup-<date>-<n>/`: `NAME.img`, split into 1 GiB pieces `NAME.img.000…` on FAT when ≥ 4 GiB, plus `SHA256SUMS` and `MANIFEST.txt`. Every image is read back and checked | `backup: OK <dir>` |
| `ad5x-restore [--dry-run] [--i-know] [--set-flag A\|B] [--reboot] SRC PART[=FILE]...` | Write images back. Checks: SHA256SUMS (or `FILE.sha256` next to the image), size (`boot`: exactly 1 MiB, 1048576 bytes; with `INGE` at 0, a GPT header `EFI PART` at 512 whose entries sit where it says (LBA 2, or 32 on some boards) and end before the SPL at 0x4400, both GPT CRCs right, and the SPL table's partitions in it at their start and size, as this disk has them: refused otherwise, even with `--i-know`), squashfs/uImage magic, SPL table, mounted state. `ad5x-restore --i-know /data/ad5x/stock boot` writes back the first MiB the main OS saved (`boot.img`). Read-back after writing. Refuses `kernel`, `rootfs` (this recovery, p1/p2) and `boot` without `--i-know`, and refuses the running slot in any case. `userdata`: `/data` is unmounted first, and the source can't be on it | `restore: OK` |
| `ad5x-restore-stock [--dry-run] [--no-flag] [--reboot] [DIR]` | With Flashforge's boot loader: writes the stock system saved by the main OS's `ad5x-update --replace-stock` (`/data/ad5x/stock/{rootfs.squashfs,kernel.img,SHA256SUMS}`) into slot B, then sets flag → B. With Kiln's boot loader it runs `ad5x-return-stock` (`--dry-run` = `--check`, DIR = `--source`; `--no-flag` refused) | `restore: OK` |
| `ad5x-return-stock [--check\|--yes\|--status\|--forget] [--source SRC] [--keep-kiln-spl\|--flashforge-spl] [--remove-kiln-data [--remove-prints]]` | Return to Flashforge firmware (below): checks, finds Flashforge's files, puts stock into slot B and makes it start, resuming from what the eMMC holds; with `--remove-kiln-data` it then deletes Kiln's data in `/data/ad5x` (step 9, below). Puts Flashforge's own boot loader back by default whenever this printer's `boot.img` matches (`--keep-kiln-spl` keeps Kiln's SPL, `--flashforge-spl` refuses without `boot.img`). Lines `source:`, `target:`, `config:`, `config_failed:`, `spl_option:`, `spl_missing:`, `wipe_option:`, `kiln_data_kb:`, `prints_kb:`, `prints_files:`, `wipe_asked:` and `result:` for the touch UI (after step 9 `wipe_removed_kb:` with `wipe_prints:`, or `wipe_failed: yes`), with fixed codes the UI translates (`source_kind:`, `source_file:`, `target_kind:`, `config_kind:`, `config_lines:`); exit 0 done, 1 refused, 2 checked (no `--yes`), 3 a write failed (flag still on slot A), 4 the boot loader area not as before, 5 the return done but step 9 not run | `result: done. ...` |
| `ad5x-bootloader-install [--check\|--yes\|--fingerprint\|--status\|--offer\|--verify-start] [--upgrade] [--unsupported-board]` | Kiln's own boot loader (`docs/own-boot-loader.md`): checks (board on the allowlist, stock first MiB saved, main OS ready), saves the stock first MiB if needed, writes Kiln's SPL, Kiln's 6.6 into p3 and p1, clears U-Boot's area in `ota`, writes Kiln's U-Boot, each read back, resuming from what the eMMC holds. With Kiln's boot loader of another build on the disk, `--yes` upgrades it instead (`upgrade:` line: the build on the disk and the one carried); `--upgrade` refuses anything but such an upgrade (or one that stopped), and a downgrade (the carried build older than the disk's, by build time: each build's later date of SPL and U-Boot, the zones taken off), and is what the screen's Update runs; `--yes` alone over SSH also downgrades, with a note. Lines `board:`, `upgrade:` and `result:` for the touch UI; `--offer` prints `bootloader=`, `bootloader_upgrade=` (`yes`: another Kiln build there to upgrade) and `bootloader_offer=` (`ad5x-status --slots`; `yes` on a board on the allowlist without Kiln's boot loader, or for an install that stopped part-way), with Kiln's boot loader there also `bootloader_build=`, `bootloader_carries=`, `bootloader_same=` (the dates as in the version strings' brackets, `SPL date / U-Boot date` when they differ) and `bootloader_carries_newer=` (`yes`, `no`, `unknown`; `bootloader_upgrade=yes` only for `yes` or `unknown`) for the screen's status line; `--unsupported-board` only on a terminal with a typed confirmation. Exit 0 done, or nothing to do (`result: already installed (this build)`: the disk holds this build's first MiB byte for byte and no run is unfinished; that result even when another job or the start-up actions run, since nothing would be written), 1 refused, 2 checked (`result: ready to install`, or `ready to go on` only for a run that stopped: the record says `started`, or Kiln's SPL or part of its U-Boot is on the disk; a saved `boot.img` and a blank `ota` area alone are a fresh install), 3 a write failed (every system still starts), 4 the boot loader area not as before | `result: done. ...` |
| `ad5x-ff-decrypt [-p PASSFILE]` | Decrypts a Flashforge `AD5X-*.tgz` (OpenSSL des3, MD5 key derivation) from stdin to stdout; Flashforge's public update password is built in | (exit 0) |
| `passwd`, `ad5x-passwd [--default\|--stock\|--status]` | Root's password, shared with the main OS (`/data/ad5x/ssh/root-password`, a SHA-512 hash): set (asked twice), `root`, or back to stock's (the default `root` when there is no stock password); applied at once, kept for both OSes. With no password at all (none set, none from stock) SSH and the serial console take root/root, here as in the main OS, and the recovery image's own `/etc/shadow` has the same default. The touch screen's reset and its lock are the main OS's only (`S68ad5x-update-agent`); the recovery OS has neither | (0, or 1 with the reason) |
| `ad5x-stock-copy usershare\|usb\|DIR [--space-check [--with-boot]]` | Copies `/data/ad5x/stock` (and `boot.img`) into `kiln-stock-backup/` on usershare, the first mounted stick, or DIR, checked before and after. Writes only inside `kiln-stock-backup/`. A `boot.img` already there stays when the source has none (a whole one with Flashforge's SPL). The new copy is made next to the old one; without room for both, the old copy's `kernel.img`, `rootfs.squashfs`, `SHA256SUMS` and `MANIFEST.txt` go first, but never when the old copy holds the only `boot.img` that checks (then it is refused and the old copy stays whole). `--space-check` only runs that room test (usershare read-only), as `ad5x-bootloader-install --check` does | `stock-copy: OK <dir>` |
| `ad5x-usb mount [WAIT] \| list \| umount` | Mounts sticks at `/run/ad5x/usb/<dev>`. `list` prints one line per partition: `dev= mnt= fs= swu=a.swu,b.swu autoupdate=0/1 rescue_root=0/1 rescue_boot=0/1 rescue_flash=0/1 return_stock=0/1` | (list output) |
| `ad5x-usb-rescue boot [--dry-run] [DEV]` / `flash [--dry-run] [--no-reboot] [DIR]` | USB rescue (below) | `rescue: running` / reboot |
| `ad5x-recovery-auto` | The boot-time actions (drop folder, USB autoupdate, rescue markers). Return to Flashforge firmware comes first: asked for by the main OS (`/data/ad5x/return-stock/request`), by a stick's `kiln-return-to-stock`, or left unfinished, it only writes `/run/ad5x/return-stock.open` (the UI opens the page) and runs nothing else. While it installs an update it keeps `/run/ad5x/auto-install` up to date, and the touch screen shows Installing Kiln OS with the step and "Don't switch the printer off". Normally started by S85 | writes `/run/ad5x/auto.done` |
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
| `kiln-return-to-stock` | Opens Return to Flashforge firmware on the screen (no update, no rescue at that start). Nothing is written until it is tapped there |
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
   ssh root@PRINTER 'mkdir -p /data/ad5x/stock && cd /data/ad5x/stock &&
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
   with SSH, the logo and `http://PRINTER:8080`. Then `ad5x-boot-main`.

Going back to stock in slot A: from the main OS, write
`/data/ad5x/stock/rootfs.squashfs` to p2 and `kernel.img` to p1 (or use the
laptop backup).

## Main OS in slot A

Some printers run the main OS from slot A (`root=/dev/mmcblk0p2`, boot flag
`ota:kernel`) instead of slot B. Updates don't support this layout yet, and
no tool in this release can move the main OS to slot B. `ad5x-update`
refuses every mode there with: "this printer runs the main OS from slot A
(root=/dev/mmcblk0p2). Updates don't support that layout: see docs/recovery-os.md,
section 'Main OS in slot A'." It writes nothing.

A code step to move the main OS to slot B is not supported in 1.0, so a printer in this layout can't take a Fluidd update. Recovering it
means a manual write, so do that only with the backup from step 2 in hand.

Nothing is written blind. The steps below read first, make a backup, and
only then (if at all) write. Nothing here is tested on hardware, and the
restore from a backup in `docs/emmc-backup.md` is untested too.

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

**3. Stock rollback is not available from this layout.** `ad5x-restore-stock`
refuses to run in slot A, and this layout can't boot recovery. The
USB rescue route also needs the recovery OS in slot A, so it can't be reached
either. Do not try a manual `dd` into slot B from memory. If you need stock
back, the only recovery is the eMMC backup from step 2, written by hand and
untested.

Check first whether the saved stock system exists. It is read-only:

```
ls -l /data/ad5x/stock
```

If it exists, `ad5x-restore-stock` would write slot B and arm stock's board
update, which needs a power-off and power-on after it runs. From the main OS
in slot A it refuses, and this section does not cover it.

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
read-back, at most 3 tries per image. The same when slot A's kernel is not
the same as slot B's (which `--install-recovery` copies there; with Kiln's
boot loader the main OS's own 6.6 instead, also into p3, "Our kernel"
below): a copy cut
short or an older kernel. Log: `/data/ad5x/recovery/update.log`.
`/data/ad5x/recovery-update.disable` turns it off.

The recovery OS carries its release's images of Kiln's own boot loader
(`/usr/share/ad5x/bootloader`), but a new recovery OS in slot A never
writes them by itself: the boot loader is updated only from Reboot /
Power > Update Kiln's boot loader (`docs/own-boot-loader.md`, "Upgrading
the boot loader"), and only to a newer build. After its own write (or
when none was due), `S99ad5x-update-recovery` runs
`ad5x-bootloader-notice --start`, which compares the build in the first
MiB with slot A's and, when slot A's is newer, has the main OS's touch
screen say once that a boot loader update is ready (on Flashforge's boot
loader on a known board, after 3 complete starts, once per printer, that
Kiln's can be installed). Its line: `/data/ad5x/bootloader-notice/last`.

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
- `S99ad5x-update-recovery` writes a slot A without a superblock, or with
  a kernel other than slot B's, again at the next start;
- the kernel copy writes the uImage header last as well, and staging an
  update (and `ad5x-boot-recovery`) refuses while slot A's kernel is not a
  whole uImage (header and data CRC; exit code 4, Moonraker's `no_recovery`).
Only stock in slot A is never touched by it (`S99ad5x-install-recovery` is
the first install's step, `--replace-stock`).

A stock firmware update (an `AD5X-*.tgz` stick) run from slot B writes slot
A, this recovery system. After Return to Flashforge firmware that is the way
to a printer that is stock in both slots (docs/install.md, "Going back to
stock"); Kiln OS itself never reads such a stick to install it (Return to
Flashforge firmware only takes the kernel and root out of it).

## Return to Flashforge firmware (`ad5x-return-stock`)

Puts Flashforge's stock system back into slot B and makes the printer start
it, with only the touch screen, a USB stick and a power cycle. The ways in:
the recovery screen's Restore stock tile; HelixScreen's Settings > System >
Return to Flashforge firmware (with Settings > Advanced settings on) or
`POST /machine/kiln_os/return_stock` (the
main OS restarts into this recovery OS, which opens the page); the main
OS's `ad5x-restore-stock`; a stick with `kiln-return-to-stock`. The page
opens by itself in those cases and waits for a tap.

**Stock files**, the first that checks: `/data/ad5x/stock` (kernel.img,
rootfs.squashfs, SHA256SUMS; saved at install); its copy on usershare
(`kiln-stock-backup/`, made by the main OS's `S99ad5x-stock-copy`); on a
stick a copy saved with Save files to USB (`kiln-stock-backup/`), the
install stick's backup (`ad5x-backup-install-N/`: the images of the slot
stock ran from, as its `MANIFEST.txt` says), or Flashforge's own update
file `AD5X-*.tgz` (decrypted with `ad5x-ff-decrypt`; its kernel part
unpacked, every file checked against `md5sum.list`, the eMMC images in
`ota_kernel/ota_vN` put together from their chunks and checked against the
package's md5 lists; any version will do, stock can update itself after).
The kernel must be a whole Linux-5.10 uImage (header and data CRCs), the
root a squashfs with `/etc/ota_bin` and no Kiln OS release file.

**Steps** (each read back; the boot flag stays on slot A, this recovery OS,
until the last; `ad5x-return-stock --check` lists which are done):

| | What | Only with |
|---|---|---|
| 1 | Kiln's U-Boot out of 0xA400: the header sector first, then the rest; this printer's `boot.img` bytes there when it matches the disk, else zeros | Kiln's SPL |
| 2 | `ota` 0x80000-0x903FF zeroed: U-Boot's settings, state and records; the boot flag and both boot traces stay | |
| 3 | rootfs2 (p4) <- the stock root | |
| 4 | kernel2 (p3) <- the stock 5.10 kernel: 4 KiB of zeros, the rest, the header last | |
| 5 | kernel (p1) <- the stock kernel, the same way | Flashforge's SPL back |
| 6 | Flashforge's SPL from `boot.img`: the SPL's header sector (0x4400) zeroed, 0x4600-0xA3FF, the boot ROM's length (0x4-0x7), the header sector last (a power cut leaves a whole SPL or none, and with none the boot ROM goes to USB mode); never the GPT. A write that doesn't read back puts Kiln's SPL back | Flashforge's SPL back |
| 7 | stock's own board update armed (`Update`, `UpdateM` on usershare), Kiln's eboard record dropped, `/data/ad5x/install/state` = `returned` (the install stick works again); with Kiln's SPL staying, `boot.img` (+ `.sha256`, `.info`) into usershare's `kiln-stock-backup/` when it isn't there; `[include]` lines of stock's `printer.cfg` that stock's Klipper can't load switched off (below). The `boot.img` copy and the `printer.cfg` edit are tried at every run that reaches step 7 and never stop the return: one that fails is said (loudly for `printer.cfg`), logged, recorded in the state (`usboot=failed`, `cfg=failed`), and the return goes on; a later `--yes` tries it again | |
| 8 | the boot flag -> slot B, after steps 1-7 are checked once more | |
| 9 | Kiln's data in `/data/ad5x` deleted (below), once steps 1-8 are done and the boot flag reads back on slot B | `--remove-kiln-data` |

U-Boot goes first, so Flashforge's 5.10 is never in a slot while Kiln's
U-Boot is installed. **Flashforge's SPL back** (steps 5 and 6) is the
default whenever `boot.img` (this printer's first MiB, saved before Kiln's
boot loader; the first that matches of `/data/ad5x/stock`, the chosen
source, usershare's `kiln-stock-backup/`, a stick's `kiln-stock-backup/`)
is Flashforge's, equals the disk outside Kiln's ranges and has the same DDR
table as Kiln's SPL on the disk, for every caller (the page, the main OS's
request, a stick's `kiln-return-to-stock`, SSH, `ad5x-restore-stock`).
With `--keep-kiln-spl`, or without a matching `boot.img`, Kiln's SPL stays
and starts stock from slot B as Flashforge's SPL would (with the stock
command line); slot A keeps this recovery OS on Kiln's 6.6, which Kiln's
SPL starts when slot B's kernel doesn't check. Without `boot.img` the check
and the log say plainly that Flashforge's own boot loader can't be put back
(`spl_missing: yes`, the page shows it as a note) and the return goes on;
`--flashforge-spl` refuses then instead. An unfinished return goes on with
the choice it started with (`spl=` in its record; one an older recovery OS
started, whose default kept Kiln's SPL, the same); `--keep-kiln-spl` or
`--flashforge-spl` given then changes it, except while a write of
Flashforge's SPL that was cut short is finished from `boot.img`. A finished
return that kept Kiln's SPL, checked again without `--keep-kiln-spl`, has
only steps 5 and 6 left. On a printer with Flashforge's boot loader steps
1, 5 and 6 don't apply and nothing of this changes.

**Kiln's data** (`/data/ad5x`) stays by default, so Kiln OS installed
again finds the owner's settings. With `--remove-kiln-data` (the page's
box "Also remove Kiln OS's settings and files") it is deleted as step 9,
the last: only in a run in which steps 1-8 are all done (checked on the
disk, steps 1-7 once more before the boot flag) and the boot flag reads
back on slot B just before it, so a return that is refused, fails or stops (a power cut)
deletes nothing. Kiln OS installed later is then a first install, with the
setup wizard at its first start. `--remove-prints` (the box "...and the
uploaded print files too", usable only with the first) deletes
`printer_data/gcodes` too; without it the print files stay.

- Deleted: everything in `/data/ad5x` but what is kept below, for example
  `printer_data/` (Klipper's config with the Z offset, mesh and
  `variables.cfg`, Moonraker's database, logs), `helixscreen/`,
  `NetworkManager/`, `wpa_supplicant.conf`, `network.conf`, `plugins/`,
  `plugins-root/`, `ssh/` (root's keys and the host keys), `kiln-log/`,
  `update/`, `kiln-update/`, `kiln-stage/`, `apps/`, `web/`, `nginx/`,
  `kernel/`, `mcu/`, `install/` (the install stick then starts afresh),
  `recovery/` (but `touch-cal`), the switches (`*.enable`, `*.disable`),
  `clock`, `logo.jpg`, `camera.conf`, `screen.conf`, `kiln-os.token`.
- Kept: `stock/` and `stock.prev-*/` (Kiln's copy of Flashforge's own
  files: a later return takes them, `boot.img` is the way back to
  Flashforge's boot loader, `vendor/` is refilled from them, a later
  install and boot loader install compare with them); `vendor/`
  (Flashforge's drivers and board tools, which this recovery OS needs on
  Flashforge's kernel for the screen, touch and Ethernet; it stays in slot
  A as the safety net); `recovery/touch-cal` (its touch range);
  `bootloader/` (the record of Kiln's boot loader writes,
  `ad5x-bootloader-install` reads it; Kiln's SPL stays in the first MiB
  unless Flashforge's boot loader is put back too); `return-stock/` (this
  return's log and record); `printer_data/gcodes` unless `--remove-prints`.
- Nothing outside `/data/ad5x`: stock's own files on the data partition
  (`config/`, `zmod/`) and the usershare partition are never touched.
- Refused (nothing written at all) when `/data` isn't mounted, `/data/ad5x`
  isn't a folder, anything is mounted inside it, or, with the print files
  kept, `printer_data` is a link or `printer_data/gcodes` a link into
  `/data/ad5x`. Links are never followed: a link is deleted itself, never
  what it points to.
- Each part is renamed into `/data/ad5x/.kiln-removed` first (the same
  partition, so each part goes at once), then that folder is deleted; one
  left by a power cut is deleted by the next run. Each part and its size go
  into the return's log (`/data/ad5x/return-stock/log`). A part that can't
  be deleted doesn't undo the return: it ends with `wipe_failed: yes` (the
  screen warns), and `--yes --remove-kiln-data` tries again.
- `--check` lists what goes, with sizes, and what stays; an unfinished
  return that was asked to delete it says so (`wipe_asked:`), and the
  screen ticks the boxes again (it then asks again before going on).

**Stock's printer.cfg** (`/usr/data/config/printer.cfg`, this data
partition's `config/printer.cfg`): stock's Klipper stops at start-up
("Unable to open config file") when an `[include]` names a missing file.
A printer that had zMod keeps zMod's `[include ./mod/...]` and
`[include ./mod_data/...]` lines after zMod's folder (`/usr/data/zmod`) is
gone. Step 7 turns exactly these lines into comments
(`#kiln-off (Return to Flashforge: WHY) [include ...]`): lines whose file
is missing (links followed as stock sees them), and with zMod gone the
lines into `mod/` and `mod_data/`. Wildcards and paths outside `/usr/data`
stay. The old file is kept as `printer.cfg.before-kiln-return` (`-2`, ...
if one is there), the new one is checked to differ only in those lines
before it replaces the old one, and a second run finds nothing to do. The
check lists the lines, and its `config:` line shows on the page. If the
file can't be written (a full or damaged data partition), it is left
exactly as it was and the return still finishes: being held in the
recovery OS would be worse than stock's Klipper stopping at a missing
include, which you can fix in `printer.cfg`. The output says so in a
block of `!!` lines with the lines to remove, the log and the state record
it, and the page and the result screen show "Flashforge's printer.cfg
couldn't be changed" (`config_failed: yes`).

Kiln's IFS slot record (step 7 too): Kiln's `variables.cfg`
(`/data/ad5x/printer_data/config`, kept for a later install) names the
slot Kiln last loaded into the nozzle. Stock loads and unloads with its
own record, so once stock runs Kiln's no longer holds. Step 7 drops the
`[Variables]` lines `ifs_loaded`, `ifs_channel` (its old name),
`ifs_loaded_source` and the notes of an unfinished slot search
(`ifs_find_open`, `ifs_tube_blocked`); every other line stays byte for
byte (new file next to it, checked, renamed over it), a second run finds
nothing to do, and a file that can't be written is left as it was
without holding the return (a note; the installer tries again). Kiln OS
installed again then knows no slot and finds the one in the toolhead.
The check names the lines it would drop.

**Refused, nothing written**, unless: root, the recovery OS in slot A, no
other job (update, backup, restore, USB rescue, start-up actions), the eMMC
writable and its slots not mounted, the partitions where the boot loader's
table has them (p1-p6, p7's start), Kiln's or Flashforge's boot loader in
the first MiB, slot A's kernel whole and its root a squashfs, and a source
that checks.

**A stop or a power cut**: the recovery OS starts again (the flag is still
on slot A), the page opens (`return_stock=unfinished`), and Continue (or
`--yes`) finishes from what the eMMC holds. A write of Flashforge's SPL cut
short is finished from `boot.img` (the first MiB before it is kept as
`/data/ad5x/return-stock/before-spl.img` until the return is done). While a
return is unfinished, Boot main OS and installs refuse; `ad5x-return-stock
--forget` drops the record (slot B may then hold neither system: install a
Kiln OS update before Boot main OS). Log: `/data/ad5x/return-stock/log`.

After it: switch the printer off and on (Shut down on the job screen, then
the switch). Stock starts from slot B, writes its own board firmware back,
and its next update (a stick with `AD5X-*.tgz`, or online) writes slot A.
A Flashforge `.tgz` left on the stick is installed by stock at that start.

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
`--set-flag`; `boot` from `/data/ad5x/stock` with `boot.img.sha256`);
`ad5x-restore-stock --dry-run`; `ad5x-boot-main`; `root=PARTLABEL=` slots;
USB listing and rescue dry runs. `AD5X_TEST_SOURCES=1` runs the
repository's recovery scripts over the image's (no rebuild). With a .swu it also checks: `swupdate -c` signature and
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
Dark theme in the brand's Nord colours (`docs/brand`, as the boot logos and
install screens),
Noto Sans (subset embedded, `recovery-ui/fonts/`, OFL: Latin-1, the whole
Russian alphabet and every other character of the string table), buttons at least
60 px high.
Language: the touch screen's, read from the `language` key of HelixScreen's
`settings.json` (`src/lang.c`): English or Russian, as on the touch screen.
Any other code, such as one saved before Kiln OS left out its other
languages (de, zh, ...), shows English. Strings: `i18n/en.txt` and
`i18n/ru.txt`, the two built (`LANGS` in `i18n/gen_i18n.py`); the other
languages' files stay in `i18n/` and are checked, not built.

### Screens

| Screen | What |
|---|---|
| Home | "Kiln OS — Recovery"; IP (`net_ip`, `net_if`, `net_mode`) and `ssh root@<ip>`; what slot B holds (`slot_b`) and where the next start goes (`flag`); how far the main OS's last start got (`main_trace`); `update_last`; a chip for SWUpdate. Eight tiles: Boot main OS, Install update, Back up, Restore, Restore stock, Network / SSH, Logs, Reboot / Power |
| Install update | USB card; `.swu` files in `/data/ad5x/update/` and the top folder of mounted sticks; the upload URL `http://<ip>:8080`. **Check** runs `ad5x-swu-apply --check`; **Install** (two confirmations) runs `ad5x-swu-apply FILE` |
| Back up | USB card; switch "Also userdata"; **Dry run** / **Start backup**: `ad5x-backup [--dry-run] [--all] <stick>` (the tool makes `ad5x-backup-<date>-<n>/`) |
| Restore | USB card; the stick's `ad5x-backup-*` folders (newest first); a checkbox per `NAME.img[.NNN]` in it. `kernel`, `rootfs` (recovery's own slot) and `boot` are greyed out: `ad5x-restore` refuses them without `--i-know`, which is left to the command line. **Check**: `ad5x-restore --dry-run SRC PART...`; **Restore** (two confirmations): `ad5x-restore SRC PART...` |
| Restore stock (Return to Flashforge firmware) | Runs `ad5x-return-stock --check` when it opens and shows the files it found (`source:`), what the printer ends with (`target:`), the `printer.cfg` lines it switches off (`config:`, zMod leftovers), each in the screen's language from the codes next to them (`source_kind:`, `target_kind:`, `config_kind:`) and the result (ready, a stopped return to finish, done, or why not). A box "Also put back Flashforge's own boot loader" shows, ticked, when this printer's saved first MiB matches for a new return (`spl_option: yes`): ticked passes `--flashforge-spl`, unticked `--keep-kiln-spl`; without a match (`spl_missing: yes`) there is no box and a note says Flashforge's own boot loader can't be put back because the printer's saved copy wasn't found, and that stock works anyway; a stopped return shows no box and goes on with its own choice. Two more boxes, both off: "Also remove Kiln OS's settings and files (size)" (`--remove-kiln-data`, shown when `wipe_option: yes`) and, indented under it and usable only with it ticked, "...and the uploaded print files too (N files, size)" (`--remove-prints`); with the first ticked a note says what goes and what stays, both confirmation steps say what is deleted with its size and that it can't be undone, and the result says what was removed (or warns when not all of it could be). **Check** shows the whole check; **Save files to USB** runs `ad5x-stock-copy usb`; **Return to Flashforge** (two confirmations; **Continue** without asking again after a stop) runs `ad5x-return-stock --yes`, then a Shut down button. It opens by itself at start when the main OS asked for it, a stick has `kiln-return-to-stock`, or a return was left unfinished (`return_stock_open`, `return_stock`); while one is unfinished Boot main OS and Install lead to it |
| Network / SSH | Address, name, `ssh root@<ip>`, upload URL with a QR code, recovery `release`, and what `ad5x-usb list` reports (updates on the stick, rescue system/markers) |
| Logs | Scrollable, monospace: this session (every command and its output), `/data/ad5x/update/last.log`, `/run/ad5x/swupdate.log`, the system log (`logread`) |
| Reboot / Power | Boot main OS (`ad5x-boot-main`), Reboot, Shut down (one confirmation each); **Install Kiln's boot loader** only when `bootloader_offer=yes` (a board on the allowlist without Kiln's U-Boot) or an install stopped (`bootloader_install=started`); **Update Kiln's boot loader** instead when `bootloader_upgrade=yes` (Kiln's boot loader of an older build, or one of unknown age, on a board on the allowlist) or an update stopped (`bootloader_install=started`, `bootloader_kind=upgrade`); never for an older build than the disk's (`bootloader_carries_newer=no`: a downgrade only over SSH with `--yes`). Above them a read-only line, always there (issue #97): Kiln's boot loader installed with its build and "up to date" (`bootloader_same=yes`), "update available" (the Update entry shown), "this recovery carries an older build, Y" (`bootloader_carries_newer=no`, no entry), another build in this recovery that isn't offered, only Kiln's SPL (`kiln-spl`), or not installed with Flashforge's boot loader starting the printer; "reading" until the first `--slots` run has finished (and while the start-up actions run, after which the screen reads the slots once more), and only then, in yellow, "state unknown" when `bootloader` is missing or `unknown`. The line and the entry follow each new read while the page is open |
| Kiln's boot loader | Runs `ad5x-bootloader-install --check` when it opens: the board (`board:`), the result (ready, an install to finish, done, or why not). **Check** shows the whole check; **Install** (two confirmations with the risk; **Continue** after a stop) runs `ad5x-bootloader-install --yes`, then a Reboot button. Opens by itself at the first start after an install (the result: started by Kiln's U-Boot or not) and when an install stopped (`bootloader_open`). The result page (`bootloader_open=result`, or the record `verified` or `unverified`) leads with the outcome from the record: installed and this start came through it, or installed but this start didn't, with what to do; the check's line goes under it ("installed and up to date", Install hidden, when the tool says `already installed (this build)`), never a refusal as the headline. On every boot loader page the check waits for the start-up actions (`auto=running`, polled) before it runs, instead of saying "busy: start-up-actions". **Update Kiln's boot loader** is the same page and flow with its own words: it runs `ad5x-bootloader-install --check --upgrade` and shows both builds (`upgrade:` line: now on the printer, after the update), **Update** (two confirmations with the same risk note; **Continue** after a stop) runs `ad5x-bootloader-install --yes --upgrade`, then Reboot, and the page opens with the result at the next start (`bootloader_kind=upgrade`). `--upgrade` makes the tool refuse an install, so this page can only ever upgrade |
| Job | Every command runs here: title, spinner, elapsed time ("2:14", it stays when the command ends), step text, progress bar, live output, Stop (backups and checks only), then a green or red result with the command's last line ("backup: OK ...", "swu-apply: FAILED ..."), and Boot main OS or Reboot where it fits. Back is disabled while it runs |
| Installing Kiln OS | Opens by itself while `ad5x-recovery-auto` installs an update at start-up: the first start after the install stick, or an update the main OS staged (drop folder, USB autoupdate). "Step n of 3": 1 unpacking and checking the update, 2 writing Kiln OS (with SWUpdate's percentage), 3 restarting into Kiln OS, with a spinner and the elapsed time. A large "Don't switch the printer off". No buttons while it runs. If the install fails: "Kiln OS was not installed" and a Done button (the reason is in Logs > Updates); when `ad5x-recovery-auto` then goes on with the next file (the drop folder's next one, a USB autoupdate stick), its progress and "Don't switch the printer off" replace the failure. It follows `/run/ad5x/auto-install` (below) |

An update started anywhere else (browser upload) opens the Job screen by
itself and follows it on SWUpdate's progress socket. An install by
`ad5x-recovery-auto` opens Installing Kiln OS instead; a failed one still
on the screen (no Done yet) doesn't hold a browser upload back: its Job
screen opens, and the failure counts as seen.

**Destructive actions** (install, restore, Return to Flashforge firmware, Kiln's boot loader) ask twice. The
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
| `CMD_RESTORE_STOCK` | `ad5x-restore-stock {DRY}` (no longer used by the screens) |
| `CMD_RETURN_CHECK` / `CMD_RETURN_STOCK` | `ad5x-return-stock --check {SPL}` / `ad5x-return-stock --yes {SPL}` (`{SPL}`: `--flashforge-spl` with the boot loader box ticked, `--keep-kiln-spl` unticked, empty when there is no box) |
| `CMD_STOCK_COPY_USB` | `ad5x-stock-copy usb` |
| `CMD_BOOTLOADER_CHECK` / `CMD_BOOTLOADER_INSTALL` | `ad5x-bootloader-install --check` / `ad5x-bootloader-install --yes` (never `--unsupported-board`) |
| `CMD_BOOTLOADER_UPGRADE_CHECK` / `CMD_BOOTLOADER_UPGRADE` | `ad5x-bootloader-install --check --upgrade` / `ad5x-bootloader-install --yes --upgrade` (never `--unsupported-board`) |
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
| `PATH_AUTO_INSTALL` | `/run/ad5x/auto-install`: `ad5x-recovery-auto`'s install, key=value lines `state=` (`check`, `write`, `restart`, `failed`), `step=`, `steps=`, `file=`, `pid=` (`rc_install_state` in `lib/recovery.sh`; `ad5x-swu-apply` moves it to `write` just before SWUpdate starts). A `check` or `write` whose process is gone is ignored |

- Commands run in their own process group (`/bin/sh -c`, stdin
  `/dev/null`, stdout and stderr together); a reader thread collects the
  output, and the UI polls it every 250 ms, so the screen never waits for
  a command. Quick queries (`ad5x-status`, `ad5x-usb`, logs) run the same
  way. Exit status 0 is success; the last line is shown as the result.
- Progress bar: an install takes it from SWUpdate. Other commands may print
  `@progress <0-100> [text]` or `@step <text>` lines (not shown in the
  log). A text may start with a fixed code, `[code]` or `[code:arg]`
  (`@progress 30 [rs_root] Writing Flashforge's root (slot B)`,
  `@progress 4 [rs_unpack:AD5X-….tgz] Unpacking AD5X-….tgz`): the screen
  then shows the string `pg_<code>` in its language (`recovery-ui/src/progress.c`,
  `i18n/*.txt`, the arg for its `%s`), and the tool's English text when the
  screen is in English, the code is unknown or the language has no such
  string. `ad5x-bootloader-install` and `ad5x-return-stock` print codes;
  their logs stay English. Otherwise the last `NN%` on a line is used, otherwise the bar is
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
- Touch: stock's `tsc2007_touch` parameters scale to 0-800 x 0-480 and
  already flip Y, but the panel never reports its edges, so the driver's
  full range would put taps off target away from the middle (Back in the
  top left corner unreachable, issue #47). The UI maps the calibrated range
  instead: `AD5X_RUI_TOUCH_CAL="minx miny maxx maxy"` (swap a pair to
  invert), which `S80ad5x-recovery-ui` takes from
  `/data/ad5x/recovery/touch-cal`. The main OS's `S70helixscreen` writes
  that file from HelixScreen's touch calibration (`ad5x-touch-units
  --recovery-cal`, in stock units; HelixScreen's affine correction is left
  out). A missing or odd file gives the seed range `60 72 723 404`
  (`src/touch_cal.h`); `ui.log` names the range used. `S80ad5x-recovery-ui
  touch-cal` prints what the UI gets. `AD5X_RUI_TOUCH_SWAP=1` swaps X and
  Y. On our 6.6 kernel the tsc2007 reports raw 0-4095 with Y not flipped:
  `S80ad5x-recovery-ui` passes `AD5X_RUI_TOUCH_UNITS=raw` (`touch-units`
  prints it; `stock` on the stock kernel) and the UI converts the range,
  the file's or the default, edge for edge (`x * 4096 / 800`,
  `(480 - y) * 4096 / 480`; the inverse of `ad5x-touch-units
  --recovery-cal`). The file stays in stock units. Display: page 0 of the
  double buffer is panned in at start (yoffset 0); LVGL draws XRGB8888
  into it. The console is put in graphics mode first (`KDSETMODE
  KD_GRAPHICS` on `/dev/tty0`, as HelixScreen does): on our 6.6 the
  framebuffer console would otherwise draw its cursor and kernel messages
  into the UI. The stock kernel has no such console.

### Our kernel (6.6)

The recovery OS boots whatever kernel p1 holds. On Flashforge's SPL that
is the stock kernel, and it stays so. Its userspace also runs on our 6.6
(`kernel-ingenic66/`): on a printer with Kiln's own boot loader (Kiln's
SPL in the first MiB), the main OS puts its own 6.6
(`/usr/lib/ad5x/kernel66/xImage`, the same file U-Boot starts the main OS
with) into p1 and p3 (`S99ad5x-update-recovery`, `ad5x-update
--install-recovery` and `--kernel2`; header last, read back), and nothing
puts a Flashforge kernel back while Kiln's SPL is there. Kiln's U-Boot
starts the recovery OS only from that 6.6 (patch 0027), with
`ad5x.uboot=1 ad5x.kernel=own panic=10 loglevel=5` and the watchdog
stopped (recovery's `S05ad5x-data` may run `e2fsck`; its own feeder starts
it after that). Kiln's SPL alone (U-Boot proper missing or failing) starts
it with the stock command line (`root=/dev/mmcblk0p2`, no
`ad5x.uboot=1`). The slots only ever get a 6.6 that has just started the
main OS on this printer (or, on 7.3, one not recorded as failed). Going
back to Flashforge's boot loader puts the saved 5.10 back first
(`tools/bench/ad5x-spl-flash --restore`). The scripts check
the kernel with the main OS's `/usr/lib/ad5x/kernel.sh` (`KERNEL=own` for
anything but `uname -r` 5.10.*), as the main OS does:

| Part | Stock 5.10 | Our 6.6 |
|---|---|---|
| Drivers (`S06ad5x-modules`, shared) | Flashforge's modules from `/data/ad5x/vendor`, `8821cu` from `usershare` | All built in: nothing to load |
| Heartbeat (`S07ad5x-board`) | `cmd_gpio` | sysfs GPIO: PC11 = base of the `GPC` gpiochip + 11 |
| Logo (`S07ad5x-board`) | `cmd_fb enable`, `cmd_jpeg_display` of `recovery-logo.jpg` or `/data/ad5x/recovery/logo.jpg` | `recovery-logo-32.raw.gz` (the same logo rendered ahead by `tools/make_logo.py --raw`, XRGB8888, stride 3200) written to `/dev/fb0` with busybox, then the pan to frame 0. No Python here, so no custom logo on 6.6 (the UI covers the logo within seconds anyway). fbcon's cursor blink off |
| Backlight (`S07ad5x-board`) | `brightness` 1 | `bl_power` 0 and `brightness` at its maximum: 6.6's gpio-backlight probes powered off. On even when the logo can't be drawn |
| Touch (`S80`, UI) | stock units (0-800 x 0-480, Y flipped by the driver) | raw 0-4095, Y not flipped: the stock-unit calibration converted at use (Touch UI above) |
| Console | none | fbcon on fb0: the UI sets graphics mode |
| Ethernet (`S41ad5x-eth`, shared) | Flashforge's module | built in (`INGENIC_MAC`); same script, same `eth0` |
| Watchdog (`S05ad5x-watchdog`, shared) | off, as stock (U-Boot starts this kernel with it stopped) | BusyBox's `watchdog` feeds `/dev/watchdog` every 10 s, reset after 120 s without a feed. It is a daemon of its own, so it keeps feeding through `.swu` installs, `ad5x-restore`, `ad5x-backup` and USB rescues (none of them stop it; `/data` can be unmounted under it); only a hang stops it. Stopped cleanly at shutdown, so "Shut down" stays off |
| Wi-Fi (`S42ad5x-wifi`, shared) | `8821cu` (`power_on=PB07`) | rtw88 with its firmware and `regulatory.db` built in; same script, same `wlan0`. Power saving is turned off with `iw`, now in the recovery image too (issue #37) |

The framebuffer is 32 bpp on 6.6 (`panel-kx070.c`: `.bpp = 32`; stride
3200 since `patches/0003`), the depth the UI is built for (`LV_COLOR_DEPTH
32` in `recovery-ui/lv_conf.h`). Mainline 7.3 (16 bpp, RGB565) is not a
target for the recovery OS: `S07ad5x-board` draws no logo there (backlight
on only) and the UI would not match the framebuffer.

**Carrying the kernel.** The main image already has our 6.6 in
`/usr/lib/ad5x/kernel66/` (`xImage`, a legacy uImage with the DTB built in,
and `chainload.ko`). For the recovery image to carry its own copy:

1. `ad5x_recovery_defconfig`: `BR2_PACKAGE_AD5X_KERNEL66=y` (the line is
   there, off). It needs what the main build needs: the Ingenic SDK and the
   5.10 tree for `chainload.ko` (`BR2_PACKAGE_AD5X_KERNEL66_SDK`,
   `..._KDIR510`). The package selects `BR2_PACKAGE_WIRELESS_REGDB`
   (`regulatory.db` is built into the kernel). The kernel is then built a
   second time, in `output-recovery`.
2. `board/ad5x-recovery/post-image.sh` puts it next to the image as
   `xImage-6.6` (and in `IMAGES.txt`) whenever the image has it; nothing
   else changes. The image grows by the kernel (about 6 MB, well inside the
   100 MiB slot), and the main image grows by the same, since it carries
   the recovery image.
3. Not needed for Kiln's U-Boot: it starts the recovery OS with p1's
   kernel, and the main OS writes its own 6.6 there (above). A copy in the
   recovery image would make the recovery image about 6 MB bigger, the
   kernel would be built twice, and its build isn't reproducible, so the
   recovery content ID would change with every build and slot A would be
   rewritten after every update. The recovery image has no
   `S00ad5x-kernel`: on Flashforge's SPL it stays on the stock kernel.

**Printer test (the chainload way; on printers with Kiln's own boot loader U-Boot starts the recovery OS on 6.6 at every recovery start).** Start the recovery root on 6.6 from the
main OS with the chainload tool (`kernel-ingenic66/chainload/README.md`)
and the command line `root=/dev/mmcblk0p2 ... ad5x.noslot` (recovery's own
slot check reads `root=` and sees slot A; `root=PARTLABEL=rootfs` works as
well, `rc_slot` takes both). Put `/data/ad5x/recovery/noauto` in place first, or
recovery installs a staged update on its own. Check: the heartbeat, the
logo, the backlight, the UI with no kernel text over it, taps hitting their
buttons (Back in the top left corner), Ethernet and Wi-Fi addresses, SSH, an
`.swu` install and a USB rescue; and the same on the stock kernel. The boot
flag is not changed by any of this: a power cycle starts the main OS again.

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

`tools/make_recovery_shots.sh OUTDIR [LANG...]` renders every screen in
both languages the UI ships (`LANGS` in `i18n/gen_i18n.py`: en, ru; or the
ones named, where another code shows English), in parallel, into
`OUTDIR/<lang>/`. It fails when a screen check fails or a language shows a
different set of screens than English. The builder runs it in each run
(step `recovery-shots`) and keeps the shots in the run's log folder,
`recovery-shots/`.

### Open items (UI)

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

## Install log (the developer's printer, 2026-10-16)

1. From the main OS in slot B: `ad5x-update --install-recovery --replace-stock`
   wrote the recovery image (7.0 MB, sha256 `076a7340…`) into slot A. Stock root
   and kernel were saved first to `/data/ad5x/stock/` (rootfs `02d814b2…`, kernel
   `3144440…`, which matches the eMMC backup).
2. Flag `ota:kernel`, then power cycle: recovery booted in 11.2 s with a DHCP
   address, SSH, the SWUpdate web page on 8080, and the touch UI. Touch was
   confirmed to work.
3. Main OS zip `202610161726-c5bbe689` (69,243,794 bytes, sha256 `589ef2c4…`) was
   copied over SSH and installed with `ad5x-swu-apply`:
   - preinst wrote slot B;
   - postinst passed: "slot B verified (AD5X open OS 2026-10-16)", flag `ota:kernel2`;
   - result: `SWUPDATE successful`.
4. Reboot: main OS came up from `root=/dev/mmcblk0p4` in about 25 s (SSH).
   dropbear, klippy, moonraker and helix-screen are running, and Klipper is `ready`.
   S99 left the flag on `ota:kernel2`.
