# Architecture

How Kiln OS fits together, from the boot ROM to the touch screen, where
each piece lives in this repository, and how a change gets to a printer.
Read this first. The pages it links have the detail. Unfamiliar words are
in the [glossary](glossary.md).

## The printer in one picture

```
 Flashforge AD5X
 ┌───────────────────────────────────────────────────────────────────────┐
 │ Ingenic X2600 SoC (MIPS32r5, 256 or 512 MiB RAM, 8 GB+ eMMC)          │
 │                                                                       │
 │  boot ROM ─► U-Boot SPL (eMMC) ─► reads boot flag (ota, p5)           │
 │                 │                                                     │
 │       slot B (normal)                        slot A                   │
 │       kernel2 p3: stock 5.10                 kernel p1: stock 5.10    │
 │       rootfs2 p4: Kiln OS main               rootfs p2: recovery OS   │
 │                 │                                  │                  │
 │   S00ad5x-kernel: chainload ─► Kiln 6.6        stays on 5.10          │
 │   (opt-in 7.3; falls back to 5.10)                 │                  │
 │                 │                              SWUpdate (8080),       │
 │   init scripts (BusyBox rcS, S01..S99)         touch UI, backup,      │
 │                 │                              USB rescue, restore    │
 │   ┌─────────────┴────────────────────────────────────────────┐        │
 │   │ Klipper host (klippy) ◄─ unix socket ─► Moonraker :7125  │        │
 │   │      │                                    ▲      ▲       │        │
 │   │      │ serial                     websocket│      │HTTP  │        │
 │   │      │                         HelixScreen │   nginx :80 │        │
 │   │      │                         (touch, fb0)│   Fluidd,   │        │
 │   │      │                                     │   /webcam/, │        │
 │   │      │                                     │   /screen/  │        │
 │   │      │       ustreamer :8090/:8091 (cameras), fbstream :8092      │
 │   │      │       update agent (root) ◄─ files ─ Moonraker kiln_os     │
 │   └──────┼───────────────────────────────────────────────────┘        │
 │          │ /data (userdata p7): config, logs, state, plugins          │
 └──────────┼────────────────────────────────────────────────────────────┘
            │
   ┌────────┼──────────────┬─────────────────────┬──────────────────┐
   ▼ ttyS2  ▼ ttyS5        ▼ ttyS4 (RS-485)      ▼ ttyS7
 mainboard  eboard         IFS                   bed weighing
 N32G455    (toolhead)     (4 filament slots)    board
 Klipper    N32G455        Flashforge firmware,  (stock firmware,
 firmware   Klipper fw     or Klipper with       ad5x_weight.py)
                           ifs-klipper.enable
```

## Layer by layer

### 1. Boot loader and slots

The boot ROM loads U-Boot's SPL from the eMMC. The SPL reads the boot
flag in the `ota` partition and boots slot A or slot B. There is no
fallback in Flashforge's SPL. Kiln OS uses the printer's own A/B layout;
with Flashforge's boot loader (the default) it never writes the boot
loader or the kernel partitions. Kiln's own boot loader (opt-in,
[own-boot-loader.md](own-boot-loader.md)) replaces the SPL, adds U-Boot
with its own fallbacks, and puts Kiln's 6.6 in both kernel partitions.
The main OS lives in slot B, the recovery OS in slot A. The diagram shows
the default.

"Try once" gives the fallback the SPL lacks: the main OS's first script
points the flag at recovery, its last script (once SSH is up) points it
back. A main OS that doesn't finish starting lands in recovery at the next
power cycle.

Details: [boot-slots.md](boot-slots.md), [recovery-os.md](recovery-os.md).

### 2. Kernels

With Flashforge's boot loader (the default) both slots boot the
printer's stock **Linux 5.10** first: it is what that SPL can start, and
it stays in the kernel partitions. On the main OS the
first boot script, `S00ad5x-kernel`, loads **Kiln's 6.6** kernel from the
image into RAM and jumps to it with `chainload.ko` (the stock kernel has
no kexec). With the switch `/data/ad5x/kernel/mainline` it starts the
**mainline 7.3** kernel instead. Markers in `/data/ad5x/kernel/` record
each start. A start that fails sends the next boots back to 6.6 (from 7.3)
or to the stock kernel (from 6.6) until you run `ad5x-kernel retry`. The
recovery OS runs on the stock kernel there. With Kiln's own boot loader
U-Boot starts Kiln's kernel directly (7.3, then 6.6, then the recovery OS,
which runs on Kiln's 6.6 too) and there is no 5.10 pass.

On the stock kernel the drivers are Flashforge's out-of-tree modules,
copied from the printer itself into `/data/ad5x/vendor` (never shipped in
an image). Kiln's kernels have their drivers built in.

| Kernel | Source in the repo | Built by | Installed at |
|---|---|---|---|
| Stock 5.10 | not in the repo (the printer's own) | Flashforge | kernel partitions p1/p3 |
| Kiln 6.6 (default) | `kernel-ingenic66/` (patches, device tree, panel driver, `build.sh`) on Ingenic's X2600 SDK | `buildroot/package/ad5x-kernel66` | `/usr/lib/ad5x/kernel66/` |
| `chainload.ko` | `kernel-ingenic66/chainload/` | `ad5x-kernel66`, against a 5.10 header tree | `/usr/lib/ad5x/kernel66/` |
| Mainline 7.3 (opt-in) | `kernel-mainline/` (patches, `kiln.config`, `build.sh`) | `buildroot/package/ad5x-kernel-mainline` | `/usr/lib/ad5x/kernel-mainline/` |

Details: `kernel-ingenic66/README.md`, `kernel-mainline/README.md`,
[boot-order.md](boot-order.md) ("rcS runs twice").

### 3. Start-up

BusyBox init runs `rcS`, which runs the `S??` scripts in order. They mount
`/data`, load drivers (stock kernel only), start the heartbeat and the boot
logo, bring up the network, flash the boards if needed, and start the
services. The last script marks the start as finished. Every script and
the files it reads and writes: [boot-order.md](boot-order.md).

### 4. Services (main OS)

| Service | What it does | Code in the repo | Start script |
|---|---|---|---|
| Klipper host | Motion, heaters, macros, the IFS driver, Kiln's extras | upstream Klipper pinned in `buildroot/package/klipper/klipper.mk`, host patches `buildroot/package/klipper/0*.patch`, Kiln's extras `klipper/extras/`, config `klipper/*.cfg`, `klipper/macros/`, plugins `klipper/plugins/` | `S61klipper` |
| Moonraker | API on port 7125 for Fluidd, HelixScreen and slicers; update manager | upstream pinned in `buildroot/package/moonraker/` (with patches), Kiln components `moonraker/components/` (`kiln_os.py`: updates, kernel, recovery; `kiln_lanes.py`: IFS slots), default config `moonraker/*.conf` | `S62moonraker` |
| nginx + Fluidd | Web UI on port 80; proxies Moonraker, cameras, the screen stream | `buildroot/board/ad5x/rootfs-overlay/etc/nginx/`, `buildroot/package/fluidd/` | `S61ad5x-web`, `S63nginx` |
| HelixScreen | Touch UI on the panel (fbdev; DRM opt-in on 7.3), talks to Moonraker's websocket | upstream pinned in `buildroot/package/helixscreen/helixscreen.mk`, Kiln patches `buildroot/package/helixscreen/0*.patch` | `S70helixscreen` |
| Cameras | One `ustreamer` per USB camera, at most two | `S64ad5x-camera` | `S64ad5x-camera` |
| Screen in the browser | `ad5x-fbstream` streams the displayed framebuffer (through DRM on 7.3, else `/dev/fb0`) with touch | `buildroot/package/ad5x-system/src/ad5x-fbstream.c` | `S65ad5x-screen` |
| Update agent | Root loop that carries out what Moonraker and Klipper ask for: install an update or a daily package, restart Moonraker, start, stop or restart a service (Fluidd's service buttons, Moonraker's `kiln_agent` provider), retry the kernel, boot recovery, run a plugin's root scripts | `S68ad5x-update-agent`, `bin/ad5x-update` | `S68ad5x-update-agent` |
| Plugin root scripts | The update agent runs a plugin's `root/install.sh`, `update.sh`, `uninstall.sh` when Klipper asks (enabled with `ROOT=1`, updated, disabled); the boot runner starts the boot scripts plugins left in `/data/ad5x/plugins-root/init.d` ([plugin-root-hooks.md](plugin-root-hooks.md)) | `lib/plugin-root.sh`, `S69ad5x-plugin-boot`, `klipper/extras/ad5x_plugins.py` | `S68ad5x-update-agent`, `S69ad5x-plugin-boot` |
| Network | NetworkManager (Ethernet, Wi-Fi, `nmcli` for HelixScreen) with connections made from `network.conf` and `wpa_supplicant.conf` at every start and Wi-Fi networks written back; the old `wpa_supplicant`/`udhcpc` way as a choice and safety net ([network.md](network.md)) | `S40ad5x-network`, `lib/ad5x_network.py`, `board/ad5x/rootfs-overlay/etc/NetworkManager/`, `board/ad5x/network-nm.sh`; the old way `S41ad5x-eth`, `S42ad5x-wifi`, `lib/network.sh` | `S40ad5x-network`, `S45NetworkManager` (or `S41`/`S42`) |
| SSH | Dropbear, root login | board overlay `S50dropbear` | `S50dropbear` |

Kiln's own shell tools (`ad5x-update`, `ad5x-kernel`, `ad5x-mcu`,
`ad5x-vendor`, `ad5x-restore-stock`, ...) are in
`buildroot/package/ad5x-system/bin/`, and the helpers they share
(`slot.sh`, `kernel.sh`, `network.sh`, `ad5x_network.py`, `apps.sh`, `logs.sh`) in
`buildroot/package/ad5x-system/lib/`. A few runtime programs are Python
files in `tools/` that the image installs (`boot_eboard.py`,
`flash_iap.py`, `flash_n32.py`, `mcu_version.py`, `ad5x_unit_cfg.py`;
see `ad5x-system.mk`).

Users of the printer only ever edit files on `/data`: the config in
`printer_data/config/` ([config-layout.md](config-layout.md)) and the
switches and settings in `/data/ad5x/` ([data-layout.md](data-layout.md)).

### 5. Recovery OS (slot A)

A small separate system: SSH, SWUpdate with its web page on port 8080, a
touch UI (`recovery-ui/`, LVGL), backup and restore, USB rescue, and
"Restore stock". It installs main-OS updates into slot B. It shares a few
start-up scripts and helpers with the main OS (see
[boot-order.md](boot-order.md)), so a change to those is a change to both.
The main image carries the recovery image it was released with and
rewrites slot A after an update when the recovery OS changed.

| Piece | Where |
|---|---|
| Buildroot configuration | `buildroot/configs/ad5x_recovery_defconfig`, `buildroot/board/ad5x-recovery/` |
| Scripts and tools | `buildroot/package/ad5x-recovery/` (`init.d/`, `bin/`, `lib/recovery.sh`, `swupdate/`) |
| Touch UI | `recovery-ui/` (built by `buildroot/package/ad5x-recovery-ui`, LVGL from `ad5x-lvgl`) |

Details: [recovery-os.md](recovery-os.md).

### 6. The boards

The printer's controllers each run their own firmware. Kiln OS writes
mainline Klipper firmware to the mainboard and the eboard at the first
start, and again when an update carries newer board firmware
(`ad5x-mcu boot` in `S60ad5x-eboard`).

| Board | Chip | Port | Firmware on Kiln OS | Built from | Flashed by |
|---|---|---|---|---|---|
| Mainboard (motion) | Nations N32G455 | `/dev/ttyS2` | mainline Klipper | `tools/build_mcu.sh`, configs `klipper/mcu-configs/`, patches `klipper/mcu-patches/`; binaries in `klipper/mcu-firmware/<version>/` | `ad5x-flash-n32` (`tools/flash_n32.py`), ROM bootloader |
| Eboard (toolhead) | Nations N32G455 behind a bootloader | `/dev/ttyS5` | mainline Klipper | same | `ad5x-flash-iap` (`tools/flash_iap.py`), its bootloader |
| IFS (filament unit) | Nations N32G455 | `/dev/ttyS4`, RS-485 | Flashforge's by default, driven by `klipper/extras/ifs.py`; Klipper with `ifs-klipper.enable` | same (`FLASHED_IFS`) | `ad5x-flash-ifs` |
| Bed weighing board (load cells) | not known | `/dev/ttyS7`, 9600 baud | stock, never flashed; not a Klipper MCU, driven by `klipper/extras/ad5x_weight.py` | | |

`klipper/mcu-dicts/FLASHED` and `FLASHED_IFS` name the firmware version
an image carries; `klipper/mcu-dicts/` holds the data dictionaries that
`tools/test_image.sh` checks the host against. Details:
[mcu-flashing.md](mcu-flashing.md), [ifs-protocol.md](ifs-protocol.md),
[bed-weighing-board.md](bed-weighing-board.md).

## Repository map

| Path | What |
|---|---|
| `buildroot/` | Buildroot external tree: both defconfigs, board files (overlays, post-build scripts), packages (`ad5x-system`, `ad5x-recovery`, `klipper`, `moonraker`, `fluidd`, `helixscreen`, kernels, recovery UI). [buildroot/README.md](../buildroot/README.md) |
| `buildroot/package/ad5x-system/` | The main OS's own scripts: `init.d/`, `bin/`, `lib/`, `src/` |
| `buildroot/package/ad5x-recovery/` | The recovery OS's own scripts and SWUpdate files |
| `klipper/` | Kiln's Klipper side: `ad5x.cfg` (factory config), `ifs.cfg`, `setup.cfg`, `macros/`, `extras/` (Python modules), `plugins/` (shipped plugins), `mcu-*` (board firmware) |
| `moonraker/` | Kiln's Moonraker components and default config |
| `kernel-ingenic66/` | Kiln's 6.6 kernel and `chainload.ko` |
| `kernel-mainline/` | The opt-in 7.3 kernel |
| `recovery-ui/` | The recovery OS's touch UI (C, LVGL) |
| `translations/` | Translator kits |
| `orca/` | OrcaSlicer profiles ([orcaslicer.md](orcaslicer.md)) |
| `tools/` | Build, release and install scripts, the runtime Python tools the image installs, and the tests (`tools/test_*`). [CONTRIBUTING.md](../CONTRIBUTING.md) says which are public. |
| `tools/install/` | The first-install script from stock (USB stick or SSH) |
| `docs/` | Documentation. [Index](README.md) |
| `os/` | Leftover from an earlier systemd plan; no build uses it |

The repository holds no Flashforge files. `firmware/` (the stock firmware
download, backups) is git-ignored and stays on your own machine.

## How a change gets to a printer

```
 edit in the repo ─► Buildroot build ─► images ─► update files ─► release
   (master)          recovery first,     rootfs     kiln-os-V-update.zip   on GitHub
                     then main with      .squashfs  (+ .swu, install.zip)
                     the recovery inside    │
                                            ▼
 printer: Moonraker kiln_os sees a newer release than /etc/kiln-version
   ─► Fluidd "Kiln OS a -> b", Update button
   ─► Moonraker downloads the zip, checks SHA256SUMS,
      puts it in /data/ad5x/kiln-update and writes "install"
   ─► update agent (root): refuses while printing; else ad5x-update
      stages it in /data/ad5x/update, boot flag -> slot A, reboot
   ─► recovery OS: installs slot B, verifies it, boot flag -> slot B, reboot
   ─► main OS starts (try once); S99ad5x-booted keeps slot B;
      S99ad5x-update-recovery rewrites slot A if its recovery OS changed;
      ad5x-mcu reflashes the boards if the firmware version changed
```

1. **Build.** Buildroot builds the recovery image first, then the main
   image, which carries the recovery image (`AD5X_RECOVERY_IMAGE`). Both
   are squashfs root file systems, vendor-free (`tools/check_vendor_free.sh`).
   See [CONTRIBUTING.md](../CONTRIBUTING.md) for what you can build today.
2. **Test.** The maintainer's builder runs the tests in `tools/test_*`
   against the built images before anything is released.
3. **Package.** `tools/make_swu.sh` makes the update (`.zip` and `.swu`,
   rootfs only, no kernel). `tools/make_install_stick.sh` makes the first
   install files. `tools/release.sh` puts them together with checksums and
   release notes from `CHANGELOG.md`.
4. **Publish.** Releases go to GitHub. Daily Klipper and Moonraker packages
   are pre-releases (they update just that program, without a reboot).
5. **Install.** From Fluidd (above), with a release zip on a USB stick that
   holds an `ad5x-autoupdate` file (read by the recovery OS), or by hand
   with `ad5x-update` over SSH.

Details: [updates.md](updates.md), [install.md](install.md),
[recovery-os.md](recovery-os.md).

## Names

The product is **Kiln OS**: use that name in anything a person reads
(screens, release notes, docs). Internal names keep the older `ad5x`
prefix on purpose: commands (`ad5x-update`), paths (`/data/ad5x`,
`/usr/lib/ad5x`), release marks (`/etc/ad5x-release`), the hostname `ad5x`
and Klipper modules (`ad5x_*.py`). Installed printers find their files by
these names, so they don't change. Moonraker components and new
user-facing pieces use `kiln_`/`kiln-` (`kiln_os.py`, `kiln-os-*.zip`).
