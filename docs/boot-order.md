# Boot order

Every start-up script of the main OS and of the recovery OS, in the order
they run, with what each one reads and writes. The scripts are plain
BusyBox shell. Kiln's own scripts are in
`buildroot/package/ad5x-system/init.d/` (main OS) and
`buildroot/package/ad5x-recovery/init.d/` (recovery OS). The rest come
from Buildroot packages or from the board overlay
(`buildroot/board/ad5x/rootfs-overlay/etc/init.d/`).

For the slots and the boot flag, see [boot-slots.md](boot-slots.md). For
what the files under `/data/ad5x` mean, see [data-layout.md](data-layout.md).
Words like "slot", "chainload" and "try once" are in the
[glossary](glossary.md).

## Before the scripts

1. The SoC's boot ROM loads the U-Boot SPL from the eMMC.
2. The SPL reads the boot flag (first sector of the `ota` partition, p5).
   `ota:kernel2` boots slot B (`kernel2` p3, root `rootfs2` p4). Anything
   else boots slot A (`kernel` p1, root `rootfs` p2). It has no fallback
   of its own.
3. With Flashforge's boot loader both kernel partitions hold the
   printer's own **stock 5.10 kernel**, and Kiln OS never writes a kernel
   there; with Kiln's own boot loader ([own-boot-loader.md](own-boot-loader.md))
   both hold Kiln's 6.6 (`S99ad5x-update-recovery` writes it). The main OS
   is in slot B. The recovery OS is in slot A.
4. The kernel mounts the squashfs root read-only and runs `/linuxrc`
   (BusyBox init). `/etc/inittab` (Buildroot's BusyBox default) mounts
   `/proc`, runs `mount -a` (`/run`, `/tmp` and `/dev/shm` are tmpfs) and
   then runs `/etc/init.d/rcS`.

`rcS` is Kiln's copy from the board overlay (the recovery OS uses the same
file, copied by `board/ad5x-recovery/post-build.sh`). It sets `umask 022`,
starts a boot trace (`ad5x-bootlog`: `/run/ad5x-boot.log`, plus a copy in
the `ota` partition at 64 KiB, with a tick every 2 s for 3 minutes), then
runs every `/etc/init.d/S??*` in glob order with the argument `start`.
Two scripts with the same number run in name order, so `S01ad5x-tryboot`
runs before `S01seedrng`.

## rcS runs twice on the main OS

This is the one surprise in the boot. On the main OS, a normal start runs
`rcS` **twice**, once on each kernel:

1. **First pass, on the stock 5.10 kernel.** `rcS` starts the trace, then
   runs `S00ad5x-kernel`. That script loads Kiln's 6.6 kernel (or the
   opt-in 7.3) into RAM with `chainload.ko`, writes the `pending` marker
   to `/data/ad5x/kernel/` and jumps to the new kernel. It does not
   return. No other script runs in this pass.
2. **Second pass, on Kiln's kernel.** The new kernel boots with the same
   command line (Kiln's low RAM window; the second bank of a 512 MiB board
   only in extended memory) plus `ad5x.kernel=own panic=10 loglevel=5`,
   `cmdline-extra` and `ad5x.ram=256|512 ad5x.memmode=standard|extended`
   ([memory.md](memory.md), "Extended memory"), BusyBox init
   runs `inittab` again and `rcS` starts again from the top. Now
   `S00ad5x-kernel` sees `ad5x.kernel=own`, renames `pending` to
   `started` and exits. Every other script runs in this pass.

If `S00ad5x-kernel` decides not to jump (an earlier start of this release
failed, no `xImage`, the staging failed), it exits and the first pass goes
on as the only pass, on the stock kernel. So every script except `S00`
runs exactly once per boot, on whichever kernel ends up running.

Kiln's own boot loader (opt-in, [own-boot-loader.md](own-boot-loader.md))
starts Kiln's kernel directly, with no stock pass. `S00ad5x-kernel` tells this by the missing
`pending` marker on Kiln's kernel (with or without `ad5x.kernel=own`): it
does not chainload, writes `started` with the word `direct` at the end, and
`S99ad5x-booted` turns it into `last-ok` as usual. Such a start never counts
as a failure: a later stock pass drops an unfinished one without counting
it. `rcS` then runs once.
Scripts check which kernel they are on with `/usr/lib/ad5x/kernel.sh`
(`KERNEL=stock` for `uname -r` 5.10.*, else `own`).

The recovery OS has no `S00ad5x-kernel`, and `rcS` runs once. On
Flashforge's boot loader it boots the stock kernel from p1; with Kiln's
own boot loader U-Boot starts it on Kiln's 6.6. Its scripts work on both;
they check the kernel with the same `kernel.sh`.

## Main OS (slot B)

`/data` is not mounted until `S05ad5x-data`. Scripts before it that need
`/data` mount the partition themselves (`S00`) or work without it.
"Buildroot" in the second column means the script comes from a Buildroot
package, not from Kiln. BusyBox's `S50crond` is not in the main OS:
Kiln schedules nothing with cron, so its BusyBox has no `crond` or
`crontab` (`busybox.fragment`).

| Script | From | What it does | Reads | Writes |
|---|---|---|---|---|
| `S00ad5x-kernel` | Kiln | Stock pass: checks the kernel markers (drops an unfinished direct start without counting it), then starts Kiln's 6.6 (or 7.3 with the `mainline` switch) from RAM with `chainload.ko`. Memory ([memory.md](memory.md), "Extended memory"): the board from the stock line's bank at 0x30000000; that bank goes to our kernel only with the `extended-memory` switch, no `extended-memory-failed` and not on the first start after an install, else it is taken out (also from `cmdline-extra`); `ad5x.ram=` and `ad5x.memmode=` last; an extended start also writes `extended-memory-pending`, and one found at the next stock pass (before the kernel markers are judged) becomes `extended-memory-failed`, that start's `pending`/`started` dropped uncounted, our kernel again in standard memory. Own-kernel pass: renames `pending` to `started`; without `pending` (a direct start by a boot loader) writes `started` ending in `direct`. Started by Kiln's U-Boot (`ad5x.uboot=1`): never chainloads; on the stock kernel it does nothing, on ours a `pending` (and `extended-memory-pending`) left from the chain is dropped (history line) and the start is `direct`; U-Boot's `failed-mem` record is copied into `extended-memory-failed`. Mounts the data partition itself at `/tmp/kdata`. Does nothing outside slots A/B (USB test mode). | `/proc/cmdline`, `/proc/kallsyms`, `/usr/lib/ad5x/kernel66/{xImage,chainload.ko,release}`, `/usr/lib/ad5x/kernel-mainline/`, `/data/ad5x/kernel/{pending,started,unfinished,failed,failed-mainline,mainline,cmdline-extra,extended-memory,extended-memory-pending,extended-memory-failed}`, `/data/ad5x/clock`, `/data/ad5x/install/recovery.squashfs` (exists: first start after an install), `ota` 0x90200 (U-Boot's records, with `ad5x.uboot=1`) | `/data/ad5x/kernel/{pending,started,unfinished,failed,failed-mainline,history,extended-memory-pending,extended-memory-failed}` |
| `S01ad5x-tryboot` | Kiln | Try once: points the boot flag at the **other** slot (the recovery OS), so a start that never finishes lands in recovery at the next power cycle. Skips this if the other slot holds no squashfs, or its kernel partition no uImage with a right header CRC. Started by Kiln's U-Boot (`ad5x.uboot=1`): the flag stays on this slot (U-Boot counts the start; the start-up limit in `S05ad5x-watchdog` resets a hung one). | `/proc/cmdline` (which slot; `root=/dev/...` or `root=PARTLABEL=...`), the other slot's root superblock and kernel header | `ota` partition (boot flag) |
| `S01seedrng` | Buildroot (urandom-scripts) | Feeds the saved random seed to the kernel. Its seed directory is `/var/lib/seedrng` on the read-only root, so the seed is probably not kept between boots (check). | `/var/lib/seedrng` | (none that persists) |
| `S01syslogd` | Buildroot (BusyBox) | System log daemon. | | `/var/log/messages` (`/var/log` is `/tmp`, RAM) |
| `S02ad5x-logo` | Kiln | On Kiln's kernels only: puts the default boot logo into the framebuffer with BusyBox alone (pre-rendered frames), turns the backlight on. Runs in the background. | `/sys/class/graphics/fb0`, `/usr/share/ad5x/logo-{16,32}.raw.gz` | `/dev/fb0`, backlight sysfs, `/run/ad5x/logo-early` |
| `S02klogd` | Buildroot (BusyBox) | Kernel log to syslog. | | |
| `S02sysctl` | Buildroot (BusyBox) | Applies `/etc/sysctl.conf` and `/etc/sysctl.d/`. Kiln ships none of these (check the image if you rely on it). | `/etc/sysctl*` | |
| `S04ad5x-memory` | Kiln (main OS only) | Memory settings by board (docs/memory.md): `vm.min_free_kbytes` 4096, size limits on `/tmp` (24M), `/run` (8M) and `/dev/shm` (8M); under 300000 kB (256 MiB board, or a 512 MiB board in standard memory) 64 MiB of zram swap (lz4, else lzo-rle), `vm.swappiness` 100, `vm.page-cluster` 0. Writes `MEM_KB`, `LOW_MEM`, `HW_MEM_MIB` and `MEM_MODE` (`lib/memory.sh`). One boot-log line with the RAM, board and memory mode. | `/proc/meminfo`, `/proc/cmdline` (`ad5x.ram=`, `ad5x.memmode=`, the bank at 0x30000000), `/sys/block/zram0/comp_algorithm` | `/proc/sys/vm/*`, `/dev/zram0` (swap), `/run/ad5x-memory.conf`, `/run/ad5x-boot.log` |
| `S05ad5x-data` | Kiln | Mounts `userdata` (p7) at `/data` (tmpfs if it fails). Restores the last saved clock. Mounts pstore. Lays out `printer_data`. Takes stock's root password from `usershare`. Writes `unit.cfg` once from stock's `Adventurer5M.json`. Binds SSH host keys. Converts an old full `printer.cfg`. Creates `plugins.cfg` once (adds bambufy-compat after zMod). Copies first-boot config files. Installs and updates `macros/*.cfg` (`ad5x-config-templates`). Migrates `moonraker.conf`. Trims Kiln's logs. | `usershare` (p6): `/etc/shadow`, `/config/Adventurer5M.json`; `/data/config/mod_data/` (zMod's files); `/usr/share/ad5x/defaults/` | `/data/ad5x/printer_data/{config,logs,gcodes,comms}`, `/data/ad5x/ssh/`, `/data/ad5x/plugins/` (created), `/run/ad5x/shadow` (bound over `/etc/shadow`), `/run/dropbear` (bind of `/data/ad5x/ssh/hostkeys`), the system clock |
| `S05ad5x-memtest` | Kiln (main OS, package `ad5x-memtest`) | In extended memory only (`MEM_MODE=extended`), once: `ad5x-memtest-high` tests the second bank (`docs/memory.md`); a fault or an unfinished earlier test writes `kernel/extended-memory-failed` and restarts the printer in standard memory. Runs before `S05ad5x-watchdog`; the kernel feeds a running watchdog until then (at most 300 s) | `/run/ad5x-memory.conf`, `/proc/zoneinfo`, `/proc/self/pagemap`, `/data/ad5x/kernel/extended-memory-{tested,failed,testing}` | `/data/ad5x/kernel/extended-memory-{tested,failed,testing}`, `/run/ad5x-boot.log` |
| `S05ad5x-watchdog` | Kiln (shared with recovery) | The hardware watchdog: on Kiln's kernels only, starts BusyBox's `watchdog -F -T 120 -t 10 /dev/watchdog` through `start-stop-daemon` (nice -20, kept from the OOM killer): fed every 10 s, the board resets after 120 s without a feed. With `watchdog.disable` it starts nothing and writes the magic `V` to `/dev/watchdog`, which stops a watchdog the boot loader left running. Until it runs, the kernel feeds a watchdog Kiln's U-Boot left running (at most 300 s). Stock kernel: nothing. Started by Kiln's U-Boot (main OS): a guard in the background stops the feeder with SIGKILL when `/run/ad5x-booted` isn't there `START_LIMIT` (900) s after boot, unless a print may run; the watchdog then resets the board and U-Boot counts the start. At shutdown its `stop` ends the guard, sends SIGTERM (the daemon writes `V` and closes: watchdog stopped) and waits; never SIGKILL. | `/usr/lib/ad5x/{kernel.sh,watchdog.conf}`, `/data/ad5x/watchdog.disable`, `/proc/cmdline`, `/run/ad5x-booted`, Moonraker's print state | `/dev/watchdog`, `/run/ad5x-watchdog.pid`, `/run/ad5x-watchdog-guard.pid` |
| `S06ad5x-modules` | Kiln (shared with recovery) | Stock kernel only: checks the vendor files (`ad5x-vendor ensure`) and loads Flashforge's driver modules from them in stock's order, then the touch driver. Loads the Wi-Fi driver from `usershare` if it is not loaded. On Kiln's kernels the drivers are built in: nothing to do. | `/data/ad5x/vendor/`, `/data/ad5x/stock/` (to refill the vendor files), `usershare` `/modules/8821cu.ko` | `/data/ad5x/vendor/` (when refilled), `/run/usershare` (mount point) |
| `S07ad5x-board` | Kiln | The board heartbeat (PC11 toggled every second) and the boot logo with backlight. Kiln's kernels: sysfs GPIO and `ad5x-fb-show` (skipped when `S02` already drew the default logo). Stock kernel: stock's `cmd_*` tools from the vendor files. | `/data/ad5x/logo.jpg` (your own logo), `/run/ad5x/logo-early`, `/data/ad5x/vendor/` | GPIO, `/dev/fb0`, backlight |
| `S10udevd` | Board overlay (Buildroot's, changed) | Copies the owner's rules from `/data/ad5x/udev/rules.d` to `/run/udev/rules.d` (only when the folders and each file are root's and writable by root only), starts eudev's `udevd`, triggers and settles (up to 30 s). eudev's rules and `61-kiln-serial.rules` give `ttyS*`, `ttyACM*` and `ttyUSB*` group `dialout`; `/dev/serial/by-id` and `/dev/v4l/by-id` links; `80-net-name-slot.rules` keeps `eth0`/`wlan0`; `60-persistent-v4l.rules` skips `v4l_id` on the H.264 decoder. In USB test mode stock's mdev keeps `/dev` and only `ttyS*` get group `dialout`. | `/etc/udev/rules.d`, `/lib/udev/rules.d`, `/data/ad5x/udev/rules.d` | `/dev`, `/run/udev` |
| `S11modules` | Buildroot (initscripts) | Loads modules listed in `/etc/modules-load.d/`. Kiln has none, so it exits. | | |
| `S30dbus-daemon` | Buildroot (dbus) | The D-Bus system bus, for NetworkManager and its `wpa_supplicant` (started over D-Bus). Moonraker stays off it (`S62moonraker`). Runs on the old network way too, unused there. | | `/run/dbus/`, `/tmp/dbus/machine-id` |
| `S35ad5x-sound` | Kiln | Kiln's kernels: exports the speaker's PWM channel (pwmchip0, channel 13) for user `klipper`. No speaker on the stock kernel. | `/sys/class/pwm/pwmchip0` | `/run/ad5x-sound.conf`, `/run/ad5x-sound/` |
| `S40ad5x-network` | Kiln (main OS only) | Chooses this start's network stack ([network.md](network.md)): NetworkManager, or the old way (`S41`/`S42`) with `network-legacy`, `network-legacy.auto`, or a failed setup. On NetworkManager: makes its connections from `network.conf` and `wpa_supplicant.conf` (`lib/ad5x_network.py`), resets its switches, starts the write-back watcher (`inotifyd`) and, in the background, the safety net (NetworkManager running in 30 s, an IPv4 address in 120 s, else the old way in this start). Sets `ignore_routes_with_linkdown`. `stop`: a last write-back. | `/data/ad5x/network-legacy`, `network-legacy.auto`, `network.conf`, `wpa_supplicant.conf`, `wifi.disable`, `usershare` `/MAC` and `/wifi/wpa_supplicant.conf`, HelixScreen's `settings.json` (Wi-Fi switch) | `/run/ad5x-network/` (`mode`, `connections/`, `manifest`), `/run/NetworkManager/conf.d/`, `/data/ad5x/wpa_supplicant.conf` (new or written back), `/data/ad5x/NetworkManager/`, `network-legacy.auto`, `printer_data/logs/network.log` |
| `S40network` | Buildroot (ifupdown-scripts) | `ifup -a`. Kiln's `/etc/network/interfaces` has the loopback only. | `/etc/network/interfaces` | |
| `S41ad5x-eth` | Kiln (shared with recovery) | Main OS: only on the old network way (`/run/ad5x-network/mode`). Ethernet with stock's MAC, then DHCP (in the background) or a static address. Sets `ignore_routes_with_linkdown` first. | `usershare` `/MAC`, `/data/ad5x/network.conf` | `/run/resolv.conf` (static DNS), `/var/run/udhcpc.eth0.pid` |
| `S42ad5x-wifi` | Kiln (shared with recovery) | Main OS: only on the old network way. `wpa_supplicant` on `wlan0` (unless switched off), DHCP on join, power saving off. The first start copies the networks stock saved. A config it can't read is put aside. | `/data/ad5x/wifi.disable`, `/data/ad5x/wpa_supplicant.conf`, `usershare` `/wifi/wpa_supplicant.conf`, HelixScreen's `settings.json` (Wi-Fi switch) | `/data/ad5x/wpa_supplicant.conf` (0600), `wpa_supplicant.conf.bad-*`, `printer_data/logs/wifi.log` (+ `.1`), `/tmp/ad5x-wifi-start.txt` |
| `S45NetworkManager` | Buildroot (network-manager) | NetworkManager, only when `S40` chose it (`/etc/default/NetworkManager` ends the script otherwise, and in USB test mode). Config: `/etc/NetworkManager/NetworkManager.conf`. | `/run/ad5x-network/connections/`, `/run/NetworkManager/conf.d/` | `/run/NetworkManager/`, `/run/resolv.conf`, `/data/ad5x/NetworkManager/`, saved networks in `/run/ad5x-network/connections/` |
| `S46ad5x-wifi-log` | Kiln (main OS only) | On NetworkManager, in the background: `wifi.log` (driver, firmware, saved networks counted, the join, power saving turned off if still on, issue #37). Nothing on the old way (`S42` writes the log). | `/run/ad5x-network/mode`, `nmcli` | `printer_data/logs/wifi.log` (+ `.1`) |
| `S49chronyd` | Buildroot (chrony) | NTP client (`pool.ntp.org`, `makestep`). `/etc/default/chronyd` from the overlay makes `/run/chrony`. | `/etc/chrony.conf` | `/run/chrony/` |
| `S50dropbear` | Board overlay (Buildroot's, changed) | SSH server. Root sessions get umask 022, or 077 if you chose that with `ad5x-umask off`. Host keys stay in `/data/ad5x/ssh/hostkeys` (through the `/run/dropbear` bind from `S05`). `/root/.ssh` is a link to `/data/ad5x/ssh`. | `/data/ad5x/umask-ssh`, `/data/ad5x/ssh/` | removes the old `/data/ad5x/umask-root` |
| `S51ad5x-clock` | Kiln | Saves the current time every 15 minutes, and once more at stop (the printer has no battery clock). | | `/data/ad5x/clock`, `/run/ad5x-clock.pid` |
| `S60ad5x-eboard` | Kiln | `ad5x-mcu boot`: flashes the mainboard and eboard with the Klipper firmware this image carries when they run anything else (and the IFS, with its enable file), then starts the eboard's application. Creates `klipper.enable` once both boards run it. While it writes, "Updating the boards" moves (`ad5x-fb-progress` on Kiln's kernels: the board, its percentage, a bar, the elapsed time). May call `S99ad5x-booted` early before it asks for a power cycle. | `/usr/share/ad5x/mcu/`, `/data/ad5x/mcu.disable`, `/data/ad5x/ifs-klipper.enable`, `/data/ad5x/mcu/` | `/data/ad5x/mcu/` (log, records), `/data/ad5x/klipper.enable`, the boards' flash |
| `S61ad5x-web` | Kiln | Copies the image's Fluidd to `/data/ad5x/web/fluidd` when that copy is missing, broken or older, so Moonraker can update it. Tells nginx which copy to serve. | `/usr/share/fluidd/`, `/data/ad5x/web/fluidd/release_info.json` | `/data/ad5x/web/fluidd/`, `/run/nginx/fluidd-root.conf` |
| `S61klipper` | Kiln | Klipper host as user `klipper` at nice -10, from the image or from a newer daily package (`lib/apps.sh`). Only with `klipper.enable`. Checks the IFS for Klipper firmware (with `ifs-klipper.enable`), writes `plugins-active.cfg`, trims old dated klippy logs. Raises klippy's memory lock limit (`ulimit -l unlimited`; klippy locks its memory itself, `ad5x_mlock`). | `/data/ad5x/klipper.enable`, `/data/ad5x/ifs-klipper.enable`, `/data/ad5x/apps/klipper/`, `printer_data/config/plugins.cfg` | `/run/ad5x/ifs-mcu/*.cfg`, `/run/ad5x/ifs-klipper`, `printer_data/config/plugins-active.cfg`, `printer_data/logs/klippy.log`, `printer_data/comms/klippy.sock`, `/var/run/klipper.pid` |
| `S62moonraker` | Kiln | Moonraker as user `klipper` on port 7125, from the image or a daily package. Writes the list of enabled plugins' Moonraker parts and a small top config that includes `moonraker-updates.conf`, your `moonraker.conf` and that list. Verbose when the log mode is extended. Two glibc malloc arenas (`MALLOC_ARENA_MAX=2`), temporary files in `/data/ad5x/moonraker-tmp`. | `printer_data/config/{moonraker.conf,plugins.cfg}`, `printer_data/comms/log-mode`, `/data/ad5x/apps/moonraker/` | `printer_data/config/moonraker-plugins.conf`, `/run/moonraker/moonraker.conf`, `/var/run/moonraker.pid` |
| `S63nginx` | Kiln | nginx: Fluidd on port 80, proxies Moonraker's API and websocket, the cameras and the screen stream. Buildroot's own `S50nginx` is removed by `post-build.sh`. | `/etc/nginx/nginx.conf`, `/run/nginx/fluidd-root.conf`, `/data/ad5x/nginx/*.conf` | `/run/nginx/`, `/var/log/nginx/` |
| `S64ad5x-camera` | Kiln | One `ustreamer` per USB (UVC) camera, at most two (ports 8090, 8091; nginx `/webcam/`, `/webcam2/`). Registers each with Moonraker in the background once its snapshot answers. | `/data/ad5x/camera.conf`, `/sys/class/video4linux/` | `/run/ad5x-camera/*.pid`, Moonraker's webcam database |
| `S65ad5x-screen` | Kiln | The touch screen in the browser: `ad5x-fbstream` on port 8092 (nginx `/screen/`), registered as the "screen" webcam. Reads the framebuffer the display shows through DRM where `/dev/dri/card0` exists (7.3; it drops DRM master right after opening, so HelixScreen can take it), else `/dev/fb0`. | `/data/ad5x/screen.conf` | `/run/ad5x-screen.pid`, Moonraker's webcam database |
| `S66ad5x-fluidd-defaults` | Kiln | Writes Fluidd's macro categories into Moonraker's database once, only while Fluidd has no macro settings yet. In the background. | `/usr/share/ad5x/fluidd-macros.json` | Moonraker database (`fluidd` / `macros`) |
| `S68ad5x-update-agent` | Kiln | Root loop (every 3 s) that carries out what Moonraker (user `klipper`) can't: installs a downloaded Kiln OS update or daily package, restarts Moonraker, retries Kiln's kernel, boots the recovery OS, starts, stops or restarts a service for Moonraker's `kiln_agent` provider (Fluidd's service buttons), reboots or powers off for the same provider (Moonraker's `/machine/reboot`, `/machine/shutdown`; not while printing, during a recovery OS write or in the first 10 minutes while start-up hasn't finished), and runs a plugin's root scripts when Klipper asks ([plugin-root-hooks.md](plugin-root-hooks.md)). Refuses while a print may run. | `/data/ad5x/kiln-update/{install,restart-moonraker,kernel-retry,boot-recovery,service,reboot,shutdown,plugin-request,plugin-<name>.tar}`, `/run/ad5x-booted` and the downloaded file, `/data/ad5x/kiln-os.token` | `/data/ad5x/kiln-update/{status,plugin-status}`, `/data/ad5x/kiln-stage/` (root-only), `/data/ad5x/plugins-root/`, `/data/ad5x/kiln-log/{agent.log,plugins-root.log}`, `/data/ad5x/apps/`, `/data/ad5x/update/` (through `ad5x-update`), `/run/ad5x-update-agent.pid` |
| `S69ad5x-plugin-boot` | Kiln | Plugins' root boot scripts ([plugin-root-hooks.md](plugin-root-hooks.md)): in the background, waits until `S99ad5x-booted` marked the start good (at most 5 min) and while the recovery OS is written, then runs each `S<NN><plugin>` script with `start`, 30 s each; at shutdown with `stop`, in reverse. Only root-owned scripts whose plugin root has a copy of. | `/data/ad5x/plugins-root/{init.d,.off}`, `/data/ad5x/plugins-root/<plugin>/` | `/data/ad5x/kiln-log/plugins-root.log`, `/run/ad5x-plugin-boot.pid` |
| `S70helixscreen` | Kiln | HelixScreen on `/dev/fb0` (through DRM with `helixscreen.drm` where `/dev/dri/card0` exists, the opt-in 7.3) as root at nice 10, against Moonraker at 127.0.0.1:7125. On unless `helixscreen.disable` exists. Seeds `settings.json` on the first start (so the setup wizard runs once). Writes the touch calibration for the recovery OS. Two glibc malloc arenas (`MALLOC_ARENA_MAX=2`). | `/data/ad5x/helixscreen.disable`, `/data/ad5x/helixscreen.drm`, `/data/ad5x/helixscreen/config/settings.json`, `/data/ad5x/helixscreen/offer-setup-wizard` (the screen asks once whether to run the setup wizard after a reinstall over stock, then deletes it), `/run/ad5x-sound.conf`, `printer_data/comms/{log-mode,run-setup-wizard}`, `/run/ad5x-bootloader-notice` and `/data/ad5x/bootloader-notice/` (the boot loader notices, patch 0094) | `/data/ad5x/helixscreen/{config,cache,.helixscreen}`, `/data/ad5x/recovery/touch-cal`, `printer_data/logs/helixscreen.log`, `/var/run/helixscreen.pid` |
| `S99ad5x-booted` | Kiln | Start-up finished: renames updates still staged for the recovery OS `*.stale` (staged before this start, never installed; first run of the boot only), then, if `dropbear` runs, points the boot flag back at this slot, marks a start of Kiln's kernel as good and makes `/run/ad5x-booted` (the flag read back first): the agent, `ad5x-update` and `ad5x-boot-recovery` go ahead only with both. Without SSH the flag stays on recovery. In slot B, saves the first MiB of the eMMC once (read only). | `/data/ad5x/kernel/{started,pending,unfinished,extended-memory-pending}`, `/data/ad5x/update/`, the first MiB of `mmcblk0`, U-Boot's start confirmation (`ota` 0x90000, with Kiln's own boot loader) | `ota` (boot flag), `/run/ad5x-booted`, `/data/ad5x/update/*.stale`, `/data/ad5x/kernel/last-ok`, `/data/ad5x/kernel/extended-memory-failed` (U-Boot's `failed-mem`, when not copied yet), `/data/ad5x/stock/boot.img{,.sha256,.info}` (once, only Flashforge's boot loader; again after a save cut short); removes `started`, `pending`, `unfinished`, `extended-memory-pending` |
| `S99ad5x-install-recovery` | Kiln | Last step of a first install from stock: writes the recovery OS into slot A (`ad5x-update --install-recovery --replace-stock`), in the background, at most 3 tries; then the install state is `done`. When the installer wrote slot A itself (no `recovery.squashfs`), it sets the install state from `flag-set` to `done` at this first finished start (`start_done`). Only in slot B, after `S99ad5x-booted`. | `/data/ad5x/install/{recovery.squashfs,recovery.sha256,recovery.tries}`, boot flag | slot A (p1/p2), `/data/ad5x/stock/` (saved stock system), `/data/ad5x/install/{state,install.log,recovery.tries}` |
| `S99ad5x-stock-copy` | Kiln | A second copy of the stock files on usershare (`ad5x-stock-copy usershare --if-changed`: `kiln-stock-backup/` there, only with 64 MiB left free), a minute after start-up in the background at low priority; nothing when the copy has the same files. Return to Flashforge firmware takes them from there after a wipe of the data partition. Only in slot B. | `/data/ad5x/stock/`, `/data/ad5x/stock-copy.disable` | usershare (p6) `kiln-stock-backup/`, `/data/ad5x/stock/.usershare-copy`, `/data/ad5x/kiln-log/stock-copy.log` |
| `S99ad5x-update-recovery` | Kiln | Writes the recovery OS this image carries into slot A when slot A holds a recovery OS with another content ID or a kernel other than the one it is to hold (slot B's; with Kiln's SPL in the first MiB this system's own 6.6, never 5.10), or an empty slot from a write cut short. Never over stock. With Kiln's SPL also its 6.6 into kernel2 (`ad5x-update --kernel2`). At most 3 tries per image or kernel. | `/usr/share/ad5x/recovery/{rootfs.squashfs,rootfs.sha256,rootfs.id}`, slot A's `/etc/ad5x-recovery-id`, `/data/ad5x/recovery-update.disable`, boot flag; then `ad5x-bootloader-notice --start` (`/data/ad5x/bootloader-notice/`) | slot A, `/data/ad5x/recovery/{update.log,update.tries}`, `/run/ad5x-recovery-check` (mount point) |

Notes:

- `S00`, `S01`, `S99ad5x-booted` and the two `S99` recovery writers do
  nothing when `SLOT` is empty (`/usr/lib/ad5x/slot.sh`: not booted from
  `rootfs`/`rootfs2`, USB test mode, or `ad5x.noslot` on the command line).
- Klipper, Moonraker, nginx, the cameras and HelixScreen start in the
  background. `rcS` does not wait for them, so `S99ad5x-booted` marks the
  start as finished once the scripts have run and SSH is up, not when
  Klipper is ready.
- Before the next script runs, a background part of a script may still be
  working: `S02` (logo), `S07` (heartbeat loop, logo), `S41`/`S42`
  (DHCP), `S64`/`S65`/`S66` (wait for Moonraker), and the `S99`
  recovery writers.

### Shutdown

BusyBox init runs `/etc/init.d/rcK` (Buildroot's): every `S??*` script
with the argument `stop`, in reverse order (scripts without a `stop`
branch do nothing). Scripts with a `stop` branch include
`S05ad5x-watchdog` (stops the watchdog cleanly, so a printer that is shut
down stays off; it runs after every script from `S06` on and just before
`S05ad5x-data`), `S05ad5x-data` (unmounts `/data`), `S51ad5x-clock` (saves the clock),
`S61klipper`, `S62moonraker` (each waits up to 10 s, then kills),
`S41ad5x-eth`, `S40ad5x-network` (writes NetworkManager's networks back to
`wpa_supplicant.conf` once more), `S35ad5x-sound` and the service scripts.

The watchdog is stopped for a reboot too: BusyBox init runs the same rcK
for reboot, poweroff and halt and doesn't tell the scripts which one it
is. A reboot then restarts through the kernel (on 7.3 the watchdog driver's
restart handler, on 6.6 the SoC code, both a watchdog reset with a
millisecond timeout). From the feeder's stop to the end, a hang in the
remaining steps (unmounting `/data`, the inittab's `umount -a`) is not
caught: a power cycle, as without the watchdog. `reboot -f` and
`poweroff -f` skip rcK: the kernels' drivers stop the watchdog on halt and
poweroff themselves (`watchdog_stop_on_reboot`).

## Recovery OS (slot A)

Built from `ad5x_recovery_defconfig`. It shares `S05ad5x-watchdog`, `S06ad5x-modules`,
`S41ad5x-eth` and `S42ad5x-wifi` with the main OS (installed from the main
package's sources by `ad5x-recovery.mk`; there is no `S40ad5x-network`
and no NetworkManager here, so they always run, [network.md](network.md)), and `rcS`, `S10udevd`, its
rules in `/etc/udev/rules.d` (network names, v4l, serial ports) and
`/etc/network/interfaces` from the main overlay. A
change to one of those shared files changes both systems: test the
recovery OS too.

| Script | From | What it does | Reads | Writes |
|---|---|---|---|---|
| `S01ad5x-recovery` | Kiln | Notes the boot flag it found and makes `/dev/disk/by-partlabel/<name>` links (only for partitions whose GPT entry matches the SPL's built-in table). Does **not** change the boot flag. | `ota` (boot flag), the GPT | `/run/ad5x/flag-at-boot`, `/dev/disk/by-partlabel/` |
| `S01seedrng` | Buildroot | As in the main OS. | | |
| `S01syslogd` | Buildroot | As in the main OS. | | |
| `S02klogd` | Buildroot | As in the main OS. | | |
| `S02sysctl` | Buildroot | As in the main OS. | | |
| `S05ad5x-data` | Kiln (recovery's own) | Mounts `userdata` at `/data` (one `e2fsck -p` and a second try if the mount fails; tmpfs without it). Restores the clock. Stock's root password from `usershare`. Binds the SSH host keys (the same keys as the main OS). | `usershare` `/etc/shadow`, `/data/ad5x/clock` | `/data/ad5x/{ssh/hostkeys,update,recovery}` (created), `/run/ad5x/shadow`, `/run/dropbear` |
| `S05ad5x-watchdog` | Kiln (shared) | As in the main OS: only on Kiln's 6.6, so not on the stock kernel recovery starts by default (U-Boot starts recovery with the watchdog stopped). On 6.6 the feeder opens `/dev/watchdog` (which starts the watchdog) and keeps feeding through SWUpdate installs, restores and USB rescues: only a hang stops it. | `/data/ad5x/watchdog.disable` | `/dev/watchdog` |
| `S06ad5x-modules` | Kiln (shared) | Stock kernel (recovery's default): loads Flashforge's drivers from the vendor files, and `8821cu` from `usershare`. On Kiln's 6.6 the drivers (and rtw88 Wi-Fi) are built in: nothing to do. | `/data/ad5x/vendor/`, `/data/ad5x/stock/` | `/data/ad5x/vendor/` (when refilled) |
| `S07ad5x-board` | Kiln (recovery's own) | Heartbeat and the recovery logo, then the backlight. Stock kernel: stock's board tools. Kiln's 6.6: sysfs GPIO, `recovery-logo-32.raw.gz` written with busybox (32 bpp only, no custom logo), `bl_power` 0. | `/usr/lib/ad5x/kernel.sh`, `/data/ad5x/recovery/logo.jpg` (stock kernel), `/data/ad5x/vendor/`, `/usr/share/ad5x/recovery-logo-32.raw.gz` (6.6) | GPIO, `/dev/fb0`, backlight |
| `S10udevd` | Main overlay | As in the main OS, without the owner's rules from `/data/ad5x/udev/rules.d`. udev makes no `/dev/disk/by-*` links here (the recovery overlay's empty `60-persistent-storage.rules`): `S01ad5x-recovery` makes the by-partlabel ones. | | |
| `S11modules` | Buildroot | As in the main OS. | | |
| `S40network` | Buildroot | Loopback only. | | |
| `S41ad5x-eth` | Kiln (shared) | As in the main OS. | `/data/ad5x/network.conf` | |
| `S42ad5x-wifi` | Kiln (shared) | As in the main OS (no HelixScreen here, so the radio is never blocked at start). | `/data/ad5x/wpa_supplicant.conf`, `/data/ad5x/wifi.disable` | as in the main OS |
| `S50crond` | Buildroot | BusyBox `crond`, unused. | | |
| `S50dropbear` | Buildroot (unchanged) | SSH. `/root/.ssh` links to `/data/ad5x/ssh`. Unlike the main OS, root sessions get Buildroot's umask 077. | `/data/ad5x/ssh/` | |
| `S70swupdate` | Kiln | SWUpdate daemon: takes `.swu` images from its web page (port 8080), from `ad5x-swu-apply` and from the touch UI. Checks signatures only when the image has a public key. Replaces Buildroot's `S80swupdate`, removed by `post-build.sh`. | `/etc/swupdate/public.pem` (if built with one) | `/run/ad5x/swupdate.log`, `/tmp/sockinstctrl`, `/tmp/swupdateprog` |
| `S80ad5x-recovery-ui` | Kiln | The recovery touch UI (`recovery-ui/`, LVGL), restarted if it exits. Passes the touch calibration the main OS saved (stock units) and the touch units of the running kernel (`raw` on Kiln's 6.6), so the UI converts it there. | `/data/ad5x/recovery/touch-cal`, `/usr/lib/ad5x/kernel.sh` | `/run/ad5x/ui.log` |
| `S85ad5x-auto` | Kiln | Starts `ad5x-recovery-auto` in the background: installs `/data/ad5x/update/*.swu` and `*.zip`, then a USB stick's update if the stick has an `ad5x-autoupdate` file, then a USB rescue marker. Skipped with `noauto`. | `/data/ad5x/recovery/noauto`, `/data/ad5x/update/`, USB sticks | `/data/ad5x/update/{*.done,*.failed,last.log,applied.list}`, `/run/ad5x/auto.log`, `/run/ad5x/auto.done`, `/run/ad5x/auto-install` (the touch screen's Installing Kiln OS page), slot B, boot flag |
| `S99ad5x-recovery-ready` | Kiln | Marks start-up as finished. Leaves the boot flag alone: a successful update has already pointed it at slot B. | | `/run/ad5x/ready` |

The recovery OS has no chrony, no Klipper and no web server other than
SWUpdate's page on port 8080.

## When you add or change a script

- Pick the number by what it needs: after `S05` for `/data`, after `S41`/`S42`
  for the network, after `S62` for Moonraker (and still wait for its port:
  it starts in the background).
- Start it with `umask 022` like the others (`tools/test_ad5x_umask.sh`
  checks this).
- Anything that writes the boot flag or a slot belongs in the boot path:
  read [boot-slots.md](boot-slots.md) and test a boot of the recovery OS
  as well when you change a shared file.
- Update this page and [data-layout.md](data-layout.md) in the same commit.
