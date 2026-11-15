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
3. Both kernel partitions hold the printer's own **stock 5.10 kernel**.
   Kiln OS never writes a kernel there. The main OS is in slot B. The
   recovery OS is in slot A.
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
   command line plus `ad5x.kernel=own panic=10 loglevel=5`, BusyBox init
   runs `inittab` again and `rcS` starts again from the top. Now
   `S00ad5x-kernel` sees `ad5x.kernel=own`, renames `pending` to
   `started` and exits. Every other script runs in this pass.

If `S00ad5x-kernel` decides not to jump (an earlier start of this release
failed, no `xImage`, the staging failed), it exits and the first pass goes
on as the only pass, on the stock kernel. So every script except `S00`
runs exactly once per boot, on whichever kernel ends up running.
Scripts check which kernel they are on with `/usr/lib/ad5x/kernel.sh`
(`KERNEL=stock` for `uname -r` 5.10.*, else `own`).

The recovery OS has no `S00ad5x-kernel`. It always runs on the stock
kernel, and `rcS` runs once.

## Main OS (slot B)

`/data` is not mounted until `S05ad5x-data`. Scripts before it that need
`/data` mount the partition themselves (`S00`) or work without it.
"Buildroot" in the second column means the script comes from a Buildroot
package, not from Kiln.

| Script | From | What it does | Reads | Writes |
|---|---|---|---|---|
| `S00ad5x-kernel` | Kiln | Stock pass: checks the kernel markers, then starts Kiln's 6.6 (or 7.3 with the `mainline` switch) from RAM with `chainload.ko`. Own-kernel pass: renames `pending` to `started`. Mounts the data partition itself at `/tmp/kdata`. Does nothing outside slots A/B (USB test mode). | `/proc/cmdline`, `/proc/kallsyms`, `/usr/lib/ad5x/kernel66/{xImage,chainload.ko,release}`, `/usr/lib/ad5x/kernel-mainline/`, `/data/ad5x/kernel/{pending,started,unfinished,failed,failed-mainline,mainline,cmdline-extra}`, `/data/ad5x/clock`, `/data/ad5x/install/recovery.squashfs` (exists: first start after an install) | `/data/ad5x/kernel/{pending,started,unfinished,failed,failed-mainline,history}` |
| `S01ad5x-tryboot` | Kiln | Try once: points the boot flag at the **other** slot (the recovery OS), so a start that never finishes lands in recovery at the next power cycle. Skips this if the other slot holds no squashfs. | `/proc/cmdline` (which slot), the other slot's root superblock | `ota` partition (boot flag) |
| `S01seedrng` | Buildroot (urandom-scripts) | Feeds the saved random seed to the kernel. Its seed directory is `/var/lib/seedrng` on the read-only root, so the seed is probably not kept between boots (check). | `/var/lib/seedrng` | (none that persists) |
| `S01syslogd` | Buildroot (BusyBox) | System log daemon. | | `/var/log/messages` (`/var/log` is `/tmp`, RAM) |
| `S02ad5x-logo` | Kiln | On Kiln's kernels only: puts the default boot logo into the framebuffer with BusyBox alone (pre-rendered frames), turns the backlight on. Runs in the background. | `/sys/class/graphics/fb0`, `/usr/share/ad5x/logo-{16,32}.raw.gz` | `/dev/fb0`, backlight sysfs, `/run/ad5x/logo-early` |
| `S02klogd` | Buildroot (BusyBox) | Kernel log to syslog. | | |
| `S02sysctl` | Buildroot (BusyBox) | Applies `/etc/sysctl.conf` and `/etc/sysctl.d/`. Kiln ships none of these (check the image if you rely on it). | `/etc/sysctl*` | |
| `S05ad5x-data` | Kiln | Mounts `userdata` (p7) at `/data` (tmpfs if it fails). Restores the last saved clock. Mounts pstore. Lays out `printer_data`. Takes stock's root password from `usershare`. Writes `unit.cfg` once from stock's `Adventurer5M.json`. Binds SSH host keys. Converts an old full `printer.cfg`. Creates `plugins.cfg` once (adds bambufy-compat after zMod). Copies first-boot config files. Installs and updates `macros/*.cfg` (`ad5x-config-templates`). Migrates `moonraker.conf`. Trims Kiln's logs. | `usershare` (p6): `/etc/shadow`, `/config/Adventurer5M.json`; `/data/config/mod_data/` (zMod's files); `/usr/share/ad5x/defaults/` | `/data/ad5x/printer_data/{config,logs,gcodes,comms}`, `/data/ad5x/ssh/`, `/data/ad5x/plugins/` (created), `/run/ad5x/shadow` (bound over `/etc/shadow`), `/run/dropbear` (bind of `/data/ad5x/ssh/hostkeys`), the system clock |
| `S06ad5x-modules` | Kiln (shared with recovery) | Stock kernel only: checks the vendor files (`ad5x-vendor ensure`) and loads Flashforge's driver modules from them in stock's order, then the touch driver. Loads the Wi-Fi driver from `usershare` if it is not loaded. On Kiln's kernels the drivers are built in: nothing to do. | `/data/ad5x/vendor/`, `/data/ad5x/stock/` (to refill the vendor files), `usershare` `/modules/8821cu.ko` | `/data/ad5x/vendor/` (when refilled), `/run/usershare` (mount point) |
| `S07ad5x-board` | Kiln | The board heartbeat (PC11 toggled every second) and the boot logo with backlight. Kiln's kernels: sysfs GPIO and `ad5x-fb-show` (skipped when `S02` already drew the default logo). Stock kernel: stock's `cmd_*` tools from the vendor files. | `/data/ad5x/logo.jpg` (your own logo), `/run/ad5x/logo-early`, `/data/ad5x/vendor/` | GPIO, `/dev/fb0`, backlight |
| `S10mdev` | Board overlay (Buildroot's, changed) | Starts the `mdev` daemon (device nodes, `/etc/mdev.conf` gives the board UARTs group `dialout`) and coldplugs modules. | `/etc/mdev.conf` | `/dev` |
| `S11modules` | Buildroot (initscripts) | Loads modules listed in `/etc/modules-load.d/`. Kiln has none, so it exits. | | |
| `S35ad5x-sound` | Kiln | Kiln's kernels: exports the speaker's PWM channel (pwmchip0, channel 13) for user `klipper`. No speaker on the stock kernel. | `/sys/class/pwm/pwmchip0` | `/run/ad5x-sound.conf`, `/run/ad5x-sound/` |
| `S40network` | Buildroot (ifupdown-scripts) | `ifup -a`. Kiln's `/etc/network/interfaces` has the loopback only. | `/etc/network/interfaces` | |
| `S41ad5x-eth` | Kiln (shared with recovery) | Ethernet with stock's MAC, then DHCP (in the background) or a static address. Sets `ignore_routes_with_linkdown` first. | `usershare` `/MAC`, `/data/ad5x/network.conf` | `/run/resolv.conf` (static DNS), `/var/run/udhcpc.eth0.pid` |
| `S42ad5x-wifi` | Kiln (shared with recovery) | `wpa_supplicant` on `wlan0` (unless switched off), DHCP on join, power saving off. The first start copies the networks stock saved. A config it can't read is put aside. | `/data/ad5x/wifi.disable`, `/data/ad5x/wpa_supplicant.conf`, `usershare` `/wifi/wpa_supplicant.conf`, HelixScreen's `settings.json` (Wi-Fi switch) | `/data/ad5x/wpa_supplicant.conf` (0600), `wpa_supplicant.conf.bad-*`, `printer_data/logs/wifi.log` (+ `.1`), `/tmp/ad5x-wifi-start.txt` |
| `S49chronyd` | Buildroot (chrony) | NTP client (`pool.ntp.org`, `makestep`). `/etc/default/chronyd` from the overlay makes `/run/chrony`. | `/etc/chrony.conf` | `/run/chrony/` |
| `S50crond` | Buildroot (BusyBox) | BusyBox `crond`. Kiln schedules nothing with it. | | |
| `S50dropbear` | Board overlay (Buildroot's, changed) | SSH server. Root sessions get umask 022, or 077 if you chose that with `ad5x-umask off`. Host keys stay in `/data/ad5x/ssh/hostkeys` (through the `/run/dropbear` bind from `S05`). `/root/.ssh` is a link to `/data/ad5x/ssh`. | `/data/ad5x/umask-ssh`, `/data/ad5x/ssh/` | removes the old `/data/ad5x/umask-root` |
| `S51ad5x-clock` | Kiln | Saves the current time every 15 minutes, and once more at stop (the printer has no battery clock). | | `/data/ad5x/clock`, `/run/ad5x-clock.pid` |
| `S60ad5x-eboard` | Kiln | `ad5x-mcu boot`: flashes the mainboard and eboard with the Klipper firmware this image carries when they run anything else (and the IFS, with its enable file), then starts the eboard's application. Creates `klipper.enable` once both boards run it. May call `S99ad5x-booted` early before it asks for a power cycle. | `/usr/share/ad5x/mcu/`, `/data/ad5x/mcu.disable`, `/data/ad5x/ifs-klipper.enable`, `/data/ad5x/mcu/` | `/data/ad5x/mcu/` (log, records), `/data/ad5x/klipper.enable`, the boards' flash |
| `S61ad5x-web` | Kiln | Copies the image's Fluidd to `/data/ad5x/web/fluidd` when that copy is missing, broken or older, so Moonraker can update it. Tells nginx which copy to serve. | `/usr/share/fluidd/`, `/data/ad5x/web/fluidd/release_info.json` | `/data/ad5x/web/fluidd/`, `/run/nginx/fluidd-root.conf` |
| `S61klipper` | Kiln | Klipper host as user `klipper` at nice -10, from the image or from a newer daily package (`lib/apps.sh`). Only with `klipper.enable`. Checks the IFS for Klipper firmware (with `ifs-klipper.enable`), writes `plugins-active.cfg`, trims old dated klippy logs. | `/data/ad5x/klipper.enable`, `/data/ad5x/ifs-klipper.enable`, `/data/ad5x/apps/klipper/`, `printer_data/config/plugins.cfg` | `/run/ad5x/ifs-mcu/*.cfg`, `/run/ad5x/ifs-klipper`, `printer_data/config/plugins-active.cfg`, `printer_data/logs/klippy.log`, `printer_data/comms/klippy.sock`, `/var/run/klipper.pid` |
| `S62moonraker` | Kiln | Moonraker as user `klipper` on port 7125, from the image or a daily package. Writes the list of enabled plugins' Moonraker parts and a small top config that includes `moonraker-updates.conf`, your `moonraker.conf` and that list. Verbose when the log mode is extended. | `printer_data/config/{moonraker.conf,plugins.cfg}`, `printer_data/comms/log-mode`, `/data/ad5x/apps/moonraker/` | `printer_data/config/moonraker-plugins.conf`, `/run/moonraker/moonraker.conf`, `/var/run/moonraker.pid` |
| `S63nginx` | Kiln | nginx: Fluidd on port 80, proxies Moonraker's API and websocket, the cameras and the screen stream. Buildroot's own `S50nginx` is removed by `post-build.sh`. | `/etc/nginx/nginx.conf`, `/run/nginx/fluidd-root.conf`, `/data/ad5x/nginx/*.conf` | `/run/nginx/`, `/var/log/nginx/` |
| `S64ad5x-camera` | Kiln | One `ustreamer` per USB (UVC) camera, at most two (ports 8090, 8091; nginx `/webcam/`, `/webcam2/`). Registers each with Moonraker in the background once its snapshot answers. | `/data/ad5x/camera.conf`, `/sys/class/video4linux/` | `/run/ad5x-camera/*.pid`, Moonraker's webcam database |
| `S65ad5x-screen` | Kiln | The touch screen in the browser: `ad5x-fbstream` on port 8092 (nginx `/screen/`), registered as the "screen" webcam. | `/data/ad5x/screen.conf` | `/run/ad5x-screen.pid`, Moonraker's webcam database |
| `S66ad5x-fluidd-defaults` | Kiln | Writes Fluidd's macro categories into Moonraker's database once, only while Fluidd has no macro settings yet. In the background. | `/usr/share/ad5x/fluidd-macros.json` | Moonraker database (`fluidd` / `macros`) |
| `S68ad5x-update-agent` | Kiln | Root loop (every 3 s) that carries out what Moonraker (user `klipper`) can't: installs a downloaded Kiln OS update or daily package, restarts Moonraker, retries Kiln's kernel, boots the recovery OS, starts, stops or restarts a service for Moonraker's `kiln_agent` provider (Fluidd's service buttons), and runs a plugin's root scripts when Klipper asks ([plugin-root-hooks.md](plugin-root-hooks.md)). Refuses while a print may run. | `/data/ad5x/kiln-update/{install,restart-moonraker,kernel-retry,boot-recovery,service,plugin-request,plugin-<name>.tar}` and the downloaded file, `/data/ad5x/kiln-os.token` | `/data/ad5x/kiln-update/{status,plugin-status}`, `/data/ad5x/kiln-stage/` (root-only), `/data/ad5x/plugins-root/`, `/data/ad5x/kiln-log/{agent.log,plugins-root.log}`, `/data/ad5x/apps/`, `/data/ad5x/update/` (through `ad5x-update`), `/run/ad5x-update-agent.pid` |
| `S69ad5x-plugin-boot` | Kiln | Plugins' root boot scripts ([plugin-root-hooks.md](plugin-root-hooks.md)): in the background, waits until `S99ad5x-booted` marked the start good (at most 5 min) and while the recovery OS is written, then runs each `S<NN><plugin>` script with `start`, 30 s each; at shutdown with `stop`, in reverse. Only root-owned scripts whose plugin root has a copy of. | `/data/ad5x/plugins-root/{init.d,.off}`, `/data/ad5x/plugins-root/<plugin>/` | `/data/ad5x/kiln-log/plugins-root.log`, `/run/ad5x-plugin-boot.pid` |
| `S70helixscreen` | Kiln | HelixScreen on `/dev/fb0` as root at nice 10, against Moonraker at 127.0.0.1:7125. On unless `helixscreen.disable` exists. Seeds `settings.json` on the first start (so the setup wizard runs once). Writes the touch calibration for the recovery OS. | `/data/ad5x/helixscreen.disable`, `/data/ad5x/helixscreen/config/settings.json`, `/run/ad5x-sound.conf`, `printer_data/comms/{log-mode,run-setup-wizard}` | `/data/ad5x/helixscreen/{config,cache,.helixscreen}`, `/data/ad5x/recovery/touch-cal`, `printer_data/logs/helixscreen.log`, `/var/run/helixscreen.pid` |
| `S99ad5x-booted` | Kiln | Start-up finished: if `dropbear` runs, points the boot flag back at this slot and marks a start of Kiln's kernel as good. Without SSH the flag stays on recovery. | `/data/ad5x/kernel/{started,pending,unfinished}` | `ota` (boot flag), `/data/ad5x/kernel/last-ok`; removes `started`, `pending`, `unfinished` |
| `S99ad5x-install-recovery` | Kiln | Last step of a first install from stock: writes the recovery OS into slot A (`ad5x-update --install-recovery --replace-stock`), in the background, at most 3 tries. Only in slot B, after `S99ad5x-booted`. | `/data/ad5x/install/{recovery.squashfs,recovery.sha256,recovery.tries}`, boot flag | slot A (p1/p2), `/data/ad5x/stock/` (saved stock system), `/data/ad5x/install/{state,install.log,recovery.tries}` |
| `S99ad5x-update-recovery` | Kiln | Writes the recovery OS this image carries into slot A when slot A holds a recovery OS with another content ID (or an empty slot from a write cut short). Never over stock. At most 3 tries per image. | `/usr/share/ad5x/recovery/{rootfs.squashfs,rootfs.sha256,rootfs.id}`, slot A's `/etc/ad5x-recovery-id`, `/data/ad5x/recovery-update.disable`, boot flag | slot A, `/data/ad5x/recovery/{update.log,update.tries}`, `/run/ad5x-recovery-check` (mount point) |

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
`S05ad5x-data` (unmounts `/data`), `S51ad5x-clock` (saves the clock),
`S61klipper`, `S62moonraker` (each waits up to 10 s, then kills),
`S41ad5x-eth`, `S35ad5x-sound` and the service scripts.

## Recovery OS (slot A)

Built from `ad5x_recovery_defconfig`. It shares `S06ad5x-modules`,
`S41ad5x-eth` and `S42ad5x-wifi` with the main OS (installed from the main
package's sources by `ad5x-recovery.mk`), and `rcS`, `S10mdev`,
`/etc/mdev.conf` and `/etc/network/interfaces` from the main overlay. A
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
| `S06ad5x-modules` | Kiln (shared) | Loads Flashforge's drivers from the vendor files (always: recovery runs the stock kernel). | `/data/ad5x/vendor/`, `/data/ad5x/stock/` | `/data/ad5x/vendor/` (when refilled) |
| `S07ad5x-board` | Kiln (recovery's own) | Heartbeat and the recovery logo, with stock's board tools. | `/data/ad5x/recovery/logo.jpg`, `/data/ad5x/vendor/` | GPIO, `/dev/fb0`, backlight |
| `S10mdev` | Main overlay | As in the main OS. | | |
| `S11modules` | Buildroot | As in the main OS. | | |
| `S40network` | Buildroot | Loopback only. | | |
| `S41ad5x-eth` | Kiln (shared) | As in the main OS. | `/data/ad5x/network.conf` | |
| `S42ad5x-wifi` | Kiln (shared) | As in the main OS (no HelixScreen here, so the radio is never blocked at start). | `/data/ad5x/wpa_supplicant.conf`, `/data/ad5x/wifi.disable` | as in the main OS |
| `S50crond` | Buildroot | BusyBox `crond`, unused. | | |
| `S50dropbear` | Buildroot (unchanged) | SSH. `/root/.ssh` links to `/data/ad5x/ssh`. Unlike the main OS, root sessions get Buildroot's umask 077. | `/data/ad5x/ssh/` | |
| `S70swupdate` | Kiln | SWUpdate daemon: takes `.swu` images from its web page (port 8080), from `ad5x-swu-apply` and from the touch UI. Checks signatures only when the image has a public key. Replaces Buildroot's `S80swupdate`, removed by `post-build.sh`. | `/etc/swupdate/public.pem` (if built with one) | `/run/ad5x/swupdate.log`, `/tmp/sockinstctrl`, `/tmp/swupdateprog` |
| `S80ad5x-recovery-ui` | Kiln | The recovery touch UI (`recovery-ui/`, LVGL), restarted if it exits. Passes the touch calibration the main OS saved. | `/data/ad5x/recovery/touch-cal` | `/run/ad5x/ui.log` |
| `S85ad5x-auto` | Kiln | Starts `ad5x-recovery-auto` in the background: installs `/data/ad5x/update/*.swu` and `*.zip`, then a USB stick's update if the stick has an `ad5x-autoupdate` file, then a USB rescue marker. Skipped with `noauto`. | `/data/ad5x/recovery/noauto`, `/data/ad5x/update/`, USB sticks | `/data/ad5x/update/{*.done,*.failed,last.log,applied.list}`, `/run/ad5x/auto.log`, `/run/ad5x/auto.done`, slot B, boot flag |
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
