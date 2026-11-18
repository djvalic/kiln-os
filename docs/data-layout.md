# Data layout: /data/ad5x and /run

Where Kiln OS keeps its state on the printer, who writes each file, who
reads it, and what it means. The root file system is a read-only squashfs
that an update replaces whole. Everything that has to survive a reboot or
an update lives on the data partition.

- `/data` is the printer's `userdata` partition (p7, ext4, about 5.8 GB),
  stock's `/usr/data`. `S05ad5x-data` mounts it (the recovery OS mounts the
  same partition). Kiln OS keeps its files in **`/data/ad5x/`** and leaves
  stock's and zMod's files there alone. Updates never touch `/data`.
- `/run` and `/tmp` are tmpfs: empty at every boot.
- `usershare` (p6, stock's `/usr/prog`) is only ever mounted read-only, to
  copy stock's root password, MAC address, saved Wi-Fi networks, Wi-Fi
  driver and per-printer calibration.

Paths below are under `/data/ad5x/` unless they start with `/`. "Main" and
"recovery" say which OS reads or writes a file. Who runs each script, and
when, is in [boot-order.md](boot-order.md).

## Switches

A switch is a file whose presence (or content) turns something on or off.
Create it with `touch`, delete it to undo. Most take effect at the next
boot or the next start of the service.

| File | Effect | Default | Read by | Written by |
|---|---|---|---|---|
| `klipper.enable` | Klipper starts at boot. Created once the boards run Kiln's Klipper firmware. | created by the first start | `S61klipper` | `ad5x-mcu boot` (`S60ad5x-eboard`) |
| `ifs-klipper.enable` | The IFS runs Klipper firmware: `ad5x-mcu` flashes it and keeps it current, `S61klipper` adds its `[mcu ifs]` config. Without it the IFS keeps Flashforge's firmware and `ifs.py` talks to that. | absent | `S61klipper`, `ad5x-mcu`, `ad5x_plugins.py` | you; the IFS firmware switch (`S68ad5x-update-agent`) creates it for a switch to Klipper; `ad5x-mcu flash-ifs` with Flashforge's `ifs.hex` (or `stock`) removes it |
| `ifs-switch.enable` | The owner allows the IFS firmware switch (Settings > Devices > IFS firmware, `POST /machine/kiln_os/ifs_firmware`): without it (and without `ifs-klipper.enable`, which counts too) a switch to Klipper is refused and the screen hides the row. The way back to stock needs none. `docs/mcu-flashing.md`, "IFS firmware switch". | absent | `S68ad5x-update-agent`, Moonraker `kiln_os` | you, as root (or a plugin's root script you allowed); the switch keeps it when it puts stock back on an IFS that had `ifs-klipper.enable` |
| `mcu.disable` | `ad5x-mcu boot` only starts the eboard and flashes nothing. | absent | `ad5x-mcu` | you |
| `helixscreen.disable` | HelixScreen does not start. (Older docs say `helixscreen.enable`: the screen is on by default now.) | absent | `S70helixscreen` | you |
| `helixscreen.drm` | HelixScreen draws through DRM instead of `/dev/fb0`, where the kernel has a DRM device (`/dev/dri/card0`: the opt-in 7.3). Ignored on 6.6 and stock. | absent | `S70helixscreen` | you |
| `wifi.disable` | No Wi-Fi at all: `wpa_supplicant` does not start, so the screen has nothing to switch on. The screen's own Wi-Fi switch is separate (HelixScreen's `settings.json`, rfkill). | absent | `S42ad5x-wifi` (main and recovery) | you |
| `recovery-update.disable` | The main OS never rewrites the recovery OS in slot A. | absent | `S99ad5x-update-recovery` | you |
| `watchdog.disable` | No hardware watchdog: a hung printer is not restarted on its own (a power cycle is needed, as before). Kiln's U-Boot then starts the kernel with the watchdog stopped, and `S05ad5x-watchdog` starts no feeder (and stops a watchdog that is running anyway). Takes effect at the next boot; `/etc/init.d/S05ad5x-watchdog start` applies it at once (with the feeder stopped first: `stop`). | absent (watchdog on, Kiln's kernels only) | `S05ad5x-watchdog` (main and recovery), U-Boot | you |
| `recovery/noauto` | The recovery OS installs nothing on its own at boot (no staged update, no USB stick, no rescue marker). | absent | `S85ad5x-auto` (recovery) | you |
| `kernel/mainline` | Start the opt-in mainline 7.3 kernel instead of 6.6. | absent | `S00ad5x-kernel`, `ad5x-kernel` | `ad5x-kernel mainline on` / `off` |
| `kernel/extended-memory` | Extended memory: on a 512 MiB board Kiln's kernels get the second bank (all 512 MiB) from the next start; without it every board runs in standard memory (256 MiB). Not on the first start after an install, nor while `kernel/extended-memory-failed` is there ([memory.md](memory.md), "Extended memory"). Root's, 0644. | absent | `S00ad5x-kernel`, Kiln's U-Boot, `ad5x-memory`, Moonraker `kiln_os` | `ad5x-memory extended on` / `off` (also via Kiln's API and the touch screen) |
| `kernel/cmdline-extra` | Extra kernel options added at the end of Kiln's kernel command line (for tests; `loglevel=8` brings the full console back). In standard memory a `mem=` word at 0x30000000 there is taken out. | absent | `S00ad5x-kernel` | you |
| `umask-ssh` | `077`: root's SSH sessions create private files (umask 077) instead of 022. | absent (022) | `S50dropbear` (main) | `ad5x-umask off` / `on` |

## Configuration files you may edit

| File | What | Read by | Written by |
|---|---|---|---|
| `network.conf` | Ethernet: `MODE=dhcp` or `MODE=static`, `ADDRESS=a.b.c.d/nn`, `GATEWAY=`, `DNS="..."`, optional `IFACE=`. An invalid static setup falls back to DHCP. Shared with the recovery OS. | `/usr/lib/ad5x/network.sh` (`S41ad5x-eth`, main and recovery) | you |
| `wpa_supplicant.conf` | Saved Wi-Fi networks (mode 0600). The first start copies stock's networks. A file it can't read is moved to `wpa_supplicant.conf.bad-<date>` and a new one started. | `S42ad5x-wifi`, `wpa_supplicant` | `S42ad5x-wifi`, `wpa_supplicant` (when the screen saves a network) |
| `camera.conf` | `CAMERA=off`, `RESOLUTION=`, `FPS=`, per camera `RESOLUTION_2=` etc. Not read if others can write it. | `S64ad5x-camera` | you |
| `screen.conf` | The screen in the browser: `SCREEN=off`, `FPS=`, `QUALITY=`. | `S65ad5x-screen` | you |
| `logo.jpg` | Your own boot logo (800x480 JPEG), replaces Kiln's. | `S07ad5x-board`, `ad5x-mcu` (board update screens) | you |
| `recovery/logo.jpg` | Your own recovery logo (800x480 baseline JPEG). | `S07ad5x-board` (recovery) | you |
| `nginx/*.conf` | Extra nginx servers, for example a second web UI on another port. Must be root's: nginx runs as root. | nginx (`include` at the end of `/etc/nginx/nginx.conf`) | you, as root |
| `kiln-os.token` | Read token for a private update server. `S68` makes it `root:klipper` 0640. | Moonraker `kiln_os` (`token_file`) | you |
| `ssh/authorized_keys` | Root's SSH keys (`/root/.ssh` is a link to `ssh/`, in both OSes). | dropbear | you |

The Klipper config lives in `printer_data/config/` (below). Which file
there holds what is in [config-layout.md](config-layout.md).

## printer_data

`printer_data/` is Klipper's and Moonraker's data directory, owned by user
`klipper`. `/home/klipper/printer_data` is a link to it (board overlay), so
both paths name the same files.

| Path | What | Written by |
|---|---|---|
| `printer_data/config/` | `printer.cfg`, `unit.cfg`, `local.cfg`, `plugins.cfg`, `moonraker.conf`, `variables.cfg`, `macros/*.cfg` and the generated `plugins-active.cfg` and `moonraker-plugins.conf`; see [config-layout.md](config-layout.md) | `S05ad5x-data` (first-boot copies, `macros/` templates), Klipper, `S61klipper`, `S62moonraker`, you |
| `printer_data/logs/` | `klippy.log` (and dated copies, at most 5 and 50 MB), `moonraker.log`, `helixscreen.log`, `wifi.log` (+ `.1`); see [logs.md](logs.md) | the services, `S42ad5x-wifi` |
| `printer_data/gcodes/` | Uploaded print files | Moonraker |
| `printer_data/comms/klippy.sock` | Klipper's API socket | Klipper (`S61klipper` passes the path) |
| `printer_data/comms/log-mode` | `short` or `extended [until]`: log detail for Moonraker (`-v`) and HelixScreen | Klipper's `LOG_MODE` (`ad5x_log.py`); read by `S62moonraker`, `S70helixscreen` |
| `printer_data/comms/run-setup-wizard` | Run the setup wizard once more at the next screen start | `SETUP_WIZARD` (`ad5x_setup.py`); HelixScreen deletes it |
| `printer_data/comms/klippy-config.json` | Remembers whether the current `klippy.log` already holds the full config | Klipper (host patch 0006) |

## State the system keeps

| Path | What | Written by | Read by |
|---|---|---|---|
| `clock` | Last known time (seconds since 1970, UTC). The printer has no battery clock. | `ad5x-clock save` (`S51ad5x-clock`, every 15 min and at stop) | `ad5x-clock restore` (`S05ad5x-data`, main and recovery), `S00ad5x-kernel` (times in failure records) |
| `kernel/pending` | "UPTIME slot S RELEASE": Kiln's kernel was staged and jumped to, userspace not reached yet | `S00ad5x-kernel` (stock pass) | `S00ad5x-kernel` (next boot: a failure), `S99ad5x-booted` |
| `kernel/started` | Kiln's kernel reached userspace, start-up not finished yet. "UPTIME slot S RELEASE direct" when a boot loader started it directly (no stock pass, no `pending`): `S99ad5x-booted` makes it `last-ok` as any other; the next stock pass drops such a marker without counting it | `S00ad5x-kernel` (renames `pending`, or writes it on a direct start) | `S00ad5x-kernel`, `S99ad5x-booted` |
| `kernel/unfinished` | How many starts in a row reached userspace but not `S99ad5x-booted` (the second one counts as failed) | `S00ad5x-kernel` | `S00ad5x-kernel` |
| `kernel/failed` | Release of Kiln's kernel that didn't finish starting (line 1) and why and when (line 2). While it names the image's release, boots stay on the stock kernel. | `S00ad5x-kernel` | `S00ad5x-kernel`, `ad5x-kernel`, Moonraker `kiln_os` (Fluidd warning, `GET /machine/kiln_os/kernel`) |
| `kernel/failed-mainline` | The same for the opt-in 7.3: boots go on with 6.6 | `S00ad5x-kernel` | same as `failed` |
| `kernel/history` | One line per failed or unfinished start | `S00ad5x-kernel` | `ad5x-kernel` (last line), you |
| `kernel/last-ok` | The last start of Kiln's kernel that finished | `S99ad5x-booted` | you, `ad5x-kernel` |
| `kernel/extended-memory-pending` | "UPTIME slot S RELEASE" as `pending`: this start (on the stock SPL's chain) is in extended memory and hasn't finished yet. Found by the next stock pass: the start in extended memory failed (`extended-memory-failed`), that start's `pending`/`started` dropped without counting it, our kernel started again in standard memory | `S00ad5x-kernel` (stock pass, before the jump, synced) | `S00ad5x-kernel`; removed by `S99ad5x-booted` |
| `kernel/extended-memory-failed` | One line, "REASON, WHEN" (WHEN: the clock, "after ... (last saved clock)" or "date unknown"): a start in extended memory didn't finish. While it is there every start is in standard memory | `S00ad5x-kernel` (stock pass); copied from Kiln's U-Boot's `failed-mem` record by `S00ad5x-kernel` (our kernel, started by U-Boot) or `S99ad5x-booted` (`lib/uboot.sh`) | `S00ad5x-kernel`, Kiln's U-Boot, `ad5x-memory` (`failed=`), Moonraker `kiln_os`; removed by `ad5x-memory extended on` (which also takes `failed-mem` out of U-Boot's records) |
| `kernel/extended-memory-testing` | Present while `S05ad5x-memtest` runs the second bank's test (written and synced before it, removed after). Found at a start: the test didn't finish, and it becomes `extended-memory-failed` ("memtest: start did not finish, WHEN") | `S05ad5x-memtest` | `S05ad5x-memtest` |
| `kernel/extended-memory-tested` | "memtest: N/65536 high-bank pages tested, 4 passes, T ms, WHEN": the second bank passed its one-time test; not run again (delete it to test again) | `S05ad5x-memtest` | `S05ad5x-memtest` |
| `vendor/` | Flashforge's driver modules and board tools copied from this printer (`module_driver/`, `bin/`, `lib/`, `MANIFEST`, `SHA256SUMS`). Needed only on the stock kernel (fallback, recovery OS). Never in an image. | installer, `ad5x-vendor ensure` (`S06ad5x-modules`) | `S06ad5x-modules`, `S07ad5x-board`, `/usr/bin/cmd_*` wrappers (both OSes) |
| `stock/` | The stock system saved before it was replaced: `rootfs.squashfs`, `kernel.img`, their sha256s (`SHA256SUMS`) | installer, `ad5x-update --replace-stock` | `ad5x-restore-stock` (both OSes), `ad5x-vendor` (to refill `vendor/`), `ad5x-status` |
| `stock/boot.img`, `stock/boot.img.sha256`, `stock/boot.img.info` | The first MiB of the eMMC (the boot ROM's block, the GPT, Flashforge's SPL and its data), saved once, read only, before a boot loader of Kiln's own is ever written there. Its sha256 is in its own file, not in `SHA256SUMS`; `boot.img.info` names the SPL (its banner). Saved only from Flashforge's boot loader (`INGE` at 0, a GPT, `LPSM` at 0x4400, U-Boot SPL 2013.07), not from Kiln's own. Saved again unless `boot.img` is exactly 1 MiB (1048576 bytes) and its sha256 file checks; `ad5x-restore boot` takes only exactly 1 MiB with `INGE`, a GPT (entries where its header says, ending before 0x4400, CRCs right) and the SPL table's partitions. Kept when stock is saved again | `S99ad5x-booted` (main OS in slot B, when missing) | `ad5x-restore --i-know /data/ad5x/stock boot` (recovery OS), you (copy it off the printer) |
| `mcu/` | Board firmware records and logs: `log`, `eboard`, `ifs`, `mainboard.uid`, `nations.log`, `iap.log`, `ifs.log`, `klipper-enabled`, `.mbver` | `ad5x-mcu` | `ad5x-mcu` (`ad5x-mcu status`), you |
| `helixscreen/config/settings.json` | HelixScreen's settings (language, Wi-Fi switch, touch calibration, wizard done). Seeded on the first start; an existing file is never replaced. | `S70helixscreen` (first start), HelixScreen | HelixScreen, `S42ad5x-wifi` (Wi-Fi switch), `ad5x-touch-units`, the recovery UI (language) |
| `helixscreen/cache/`, `helixscreen/.helixscreen/` | HelixScreen's cache and settings backups | HelixScreen | HelixScreen |
| `recovery/touch-cal` | Touch range for the recovery UI, "min_x min_y max_x max_y" in stock-kernel units on every kernel (the UI converts it to raw units at use on our kernel) | `ad5x-touch-units --recovery-cal` (`S70helixscreen`) | `S80ad5x-recovery-ui` |
| `recovery/update.log`, `recovery/update.tries` | Rewriting slot A with this image's recovery OS: log, and "ID tries" | `S99ad5x-update-recovery` | `S99ad5x-update-recovery`, you |
| `ssh/hostkeys/` | SSH host keys, shared by both OSes (bound at `/run/dropbear`) | dropbear | dropbear |
| `plugins/` | Other people's and your own plugins (git clones, owned by `klipper`). Never touched by updates. | you, `INSTALL_PLUGIN`, Moonraker's update manager | `ad5x_plugins.py`, `S62moonraker` |
| `plugins-root/<name>/` | Root's copy of a plugin's `root/` folder (root-owned), made when `install.sh` or `update.sh` ran; `.sha256` says which `root/` it is. Deleted after `uninstall.sh`. ([plugin-root-hooks.md](plugin-root-hooks.md)) | `S68ad5x-update-agent` | `S68ad5x-update-agent` (runs the scripts from it), `ad5x_plugins.py` (`root_installed`, whether `update.sh` must run) |
| `plugins-root/init.d/` | Plugins' boot scripts (`S<NN><plugin>[.suffix]`), put there by their root scripts | the plugins' root scripts | `S69ad5x-plugin-boot` |
| `plugins-root/.off` | Skips all plugin boot scripts (create it from the recovery OS's SSH when one keeps the printer from working) | you | `S69ad5x-plugin-boot` |
| `web/fluidd/` | Fluidd that Moonraker can update (owned by `klipper`). Delete it and reboot to go back to the image's Fluidd. | `S61ad5x-web`, Moonraker's update manager | nginx (through `/run/nginx/fluidd-root.conf`) |
| `apps/klipper/`, `apps/moonraker/` | Daily Klipper/Moonraker packages. Used only while newer than the image's copy and the OS is at least the package's `os_min`. Delete to go back to the image's copy. | `S68ad5x-update-agent` | `/usr/lib/ad5x/apps.sh` (`S61klipper`, `S62moonraker`), Moonraker `kiln_os` |
| `umask.log` | Log of `ad5x-umask` changes | `ad5x-umask` | you |

Kiln's append-only logs (`update/last.log`, `recovery/update.log`, `mcu/log`,
`kiln-log/agent.log`, `kiln-log/plugins-root.log`, `umask.log`) are cut to their last 64 KiB at each boot
(`kiln_logs_trim`, `S05ad5x-data`).

## Updates and installs

| Path | What | Written by | Read by |
|---|---|---|---|
| `kiln-update/` | Moonraker's drop folder (owned by `klipper`): the downloaded `kiln-os-*-update.zip` or `klipper-*.tar.gz` / `moonraker-*.tar.gz`, and the requests `install` (file name, sha256), `restart-moonraker`, `kernel-retry`, `boot-recovery`, `service` ("ACTION NAME": start, stop or restart of klipper, moonraker, nginx, helixscreen or ad5x-camera), `ifs-firmware` (`stock` or `klipper`) | Moonraker `kiln_os` (`service` through the `kiln_agent` provider), `ad5x_plugins.py` (`restart-moonraker`) | `S68ad5x-update-agent` |
| `kiln-update/plugin-request`, `kiln-update/plugin-<name>.tar` | A plugin root script request: action, plugin name, sha256 of the packed `root/` folder (the tar) | `ad5x_plugins.py` | `S68ad5x-update-agent` |
| `kiln-update/status` | The agent's answer to the last request (`rebooting`, `refused: ...`, ...). Renamed into place, never written through. | `S68ad5x-update-agent` | Moonraker `kiln_os` |
| `kiln-update/plugin-status` | The agent's answer to a plugin request (`ok`, `failed: ...`, `timed out`, `refused: ...`), renamed into place | `S68ad5x-update-agent` | `ad5x_plugins.py` |
| `kiln-stage/` | Root-only (0700) staging: each request and file is moved here before root reads, hashes or unpacks it | `S68ad5x-update-agent` | `S68ad5x-update-agent` |
| `kiln-log/agent.log` | Log of the update agent (root's folder, readable by `klipper`) | `S68ad5x-update-agent` | you (over SSH) |
| `kiln-status/ifs-firmware` | The IFS firmware switch's last run (`target`, `state` running/done/failed, `phase`, `reason`, `message`, `version`; root's folder, readable by `klipper`). A run the printer's restart cut short is marked failed (`interrupted`) at the agent's start | `S68ad5x-update-agent` (`ad5x-mcu ifs-status`, `flash-ifs`) | Moonraker `kiln_os` (`GET /machine/kiln_os/ifs_firmware`) |
| `kiln-log/plugins-root.log` | Output and result of each plugin root script and boot script | `S68ad5x-update-agent`, `S69ad5x-plugin-boot` | you (over SSH) |
| `update/` | Updates staged for the recovery OS (`*.swu`, `*.zip`); after an install `*.done` or `*.failed`; `*.stale`: still staged when the main OS started, so staged before that start and never installed (docs/updates.md, "Staged updates"); `last.log`, `applied.list` (sha256s of USB stick images already installed), `.work/` | `ad5x-update` (main), the installer, `S99ad5x-booted` (`*.stale`), `ad5x-recovery-auto` (recovery) | `ad5x-recovery-auto`, `ad5x-status` (recovery) |
| `moonraker-tmp/` | Moonraker's temporary folder (`TMPDIR`, owned by `klipper`, 0700): uploads are written here whole, then renamed into `gcodes`; update downloads and components' temp files. Emptied at each Moonraker start | Moonraker | Moonraker |
| `swupdate-tmp/`, `swupdate-apply.PID/` | Recovery OS: where SWUpdate unpacks a `.swu` before writing it (the daemon's folder; a run of `ad5x-swu-apply` of its own), when the partition has 256 MiB free (else `/tmp`). Emptied at the next start of `S70swupdate` | SWUpdate (`S70swupdate`, `ad5x-swu-apply`) | SWUpdate |
| `install/` | First install from stock: `recovery.squashfs` + `recovery.sha256` (written into slot A after the first start), `recovery.tries`, `state`, `install.log`, `dl/` | `tools/install/ad5x-install.sh`, `S99ad5x-install-recovery` | `S99ad5x-install-recovery`, `S99ad5x-update-recovery` and `S00ad5x-kernel` (while `recovery.squashfs` exists, slot A still holds stock) |

## /run (RAM, gone at reboot)

Main OS:

| Path | What | Written by | Read by |
|---|---|---|---|
| `/run/ad5x-boot.log` | Boot trace: each script's start and end, uptime first | `rcS`, `ad5x-bootlog` | you, `ad5x-bootlog` (copies it into `ota` at 64 KiB) |
| `/run/ad5x-booted` | This boot's start-up has finished (empty file): made after the boot flag is back on this slot (`lib/slot.sh`, `start_done`) | `S99ad5x-booted` | `S68ad5x-update-agent`, `ad5x-update`, `ad5x-boot-recovery` |
| `/run/ad5x/logo-early` | `S02` drew the default logo (its depth in bpp) | `S02ad5x-logo` | `S07ad5x-board` |
| `/run/ad5x/shadow` | `/etc/shadow` with stock's root password, bound over `/etc/shadow` | `S05ad5x-data` | login, dropbear |
| `/run/dropbear` | Bind mount of `/data/ad5x/ssh/hostkeys` (`/etc/dropbear` points here) | `S05ad5x-data` | dropbear |
| `/run/ad5x-sound.conf`, `/run/ad5x-sound/` | `PWM=pwmchip0/pwm13`: where the speaker is (only on Kiln's kernels); the player's pid | `S35ad5x-sound`, `ad5x-sound` | Klipper's `ad5x_sound`, `S70helixscreen` |
| `/run/ad5x-memory.conf` | `MEM_KB=` (MemTotal), `LOW_MEM=1` under 300000 kB (a 256 MiB board, or a 512 MiB one in standard memory) else `0`, `HW_MEM_MIB=256\|512` (the board's RAM: `ad5x.ram=` from the boot loader, else the bank at 0x30000000, else MemTotal >= 400000 kB), `MEM_MODE=standard\|extended` (`ad5x.memmode=`, else whether that bank is on the command line), `MEM_MODE_FIXED=0\|1` (1: an older Kiln U-Boot started this, `ad5x.uboot=1` without `ad5x.memmode=`; it can't choose the mode, only a boot loader update changes it) (docs/memory.md, `lib/memory.sh`) | `S04ad5x-memory` | `S64ad5x-camera`, Moonraker `kiln_os`, plugins |
| `/run/resolv.conf` | Name servers of a static `network.conf` | `network.sh` | the resolver |
| `/run/ad5x/ifs-mcu/*.cfg` | The IFS's `[mcu ifs]` config, while it answers as Klipper and no plugin drives it | `S61klipper`, `ad5x_plugins.py` | Klipper (`ifs.cfg` includes it) |
| `/run/ad5x/ifs-klipper` | The IFS answered as Klipper at this start | `S61klipper` | `ad5x_plugins.py` |
| `/run/moonraker/moonraker.conf` | Moonraker's top config (includes `moonraker-updates.conf`, your `moonraker.conf`, the plugins' list) | `S62moonraker` | Moonraker |
| `/run/nginx/fluidd-root.conf` | Which Fluidd nginx serves (`root ...;`); also nginx's pid and temp files | `S61ad5x-web`, `S63nginx` | nginx |
| `/run/ad5x-camera/`, `/run/ad5x-screen.pid`, `/run/ad5x-clock.pid`, `/run/ad5x-watchdog.pid`, `/run/ad5x-update-agent.pid`, `/run/ad5x-plugin-boot.pid`, `/run/ad5x-plugin-root/`, `/var/run/{klipper,moonraker,helixscreen}.pid` | pid files | the scripts | the scripts' `stop` |
| `/run/ad5x-target`, `/run/ad5x-recovery-write.pid` | Mount point and lock while a slot is written | `ad5x-update`, `ad5x-boot-recovery` | the same |

Recovery OS:

| Path | What | Written by |
|---|---|---|
| `/run/ad5x/flag-at-boot` | The boot flag as recovery found it (why you are here) | `S01ad5x-recovery` |
| `/run/ad5x/swupdate.log` | SWUpdate's log | `S70swupdate` |
| `/run/ad5x/ui.log` | Touch UI log | `S80ad5x-recovery-ui` |
| `/run/ad5x/auto.log`, `/run/ad5x/auto.done` | Boot-time install log, and "done" | `ad5x-recovery-auto` |
| `/run/ad5x/usb/<dev>` | USB stick mounts | `ad5x-usb` |
| `/run/ad5x/rescue-root` | Root of a system started from a rescue stick | `ad5x-usb-rescue` |
| `/run/ad5x/ready` | Start-up finished (date) | `S99ad5x-recovery-ready` |
| `/run/ad5x-watchdog.pid` | The watchdog feeder (on Kiln's 6.6 only) | `S05ad5x-watchdog` |

## Other places outside /data/ad5x

| Path | What |
|---|---|
| `ota` partition (p5), first 11 bytes | The boot flag: `ota:kernel2` = slot B (main OS), anything else = slot A (recovery). Written by `S01ad5x-tryboot`, `S99ad5x-booted`, `ad5x-update`, `ad5x-boot-recovery` and the recovery OS. |
| `ota` partition at 64 KiB | The boot trace copy, readable after a hang: `dd if=/dev/mmcblk0p5 bs=1024 skip=64 count=8` |
| `/sys/fs/pstore` | Kiln's kernel's crash log (ramoops), mounted by `S05ad5x-data` |
| `/data/config/mod_data/` | zMod's files, read once by `S05ad5x-data` to carry plugin choices over. Kiln OS never changes them. |
| `/etc/kiln-version`, `/etc/ad5x-release`, `/etc/ad5x-recovery`, `/etc/ad5x-recovery-id`, `/usr/lib/os-release` | Read-only release marks in the image (version, which OS, recovery content ID, `AD5X_PLUGIN_API`) |

## Rules for new files

- Kiln's files go under `/data/ad5x/`, never loose in `/data` (stock and
  zMod own the rest).
- Name a switch `<thing>.enable` (off by default) or `<thing>.disable` (on
  by default), and check it with `[ -f ... ]` only.
- Root must not read, follow or write through a file that user `klipper`
  can replace: see how `S68ad5x-update-agent` stages requests and renames
  its answers.
- An append-only log should be added to `KILN_APPEND_LOGS` in
  `buildroot/package/ad5x-system/lib/logs.sh`, which keeps the last
  64 KiB of each at every boot.
- Add the file to this page in the same commit.
