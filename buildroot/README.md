# AD5X Buildroot image

A Buildroot external tree for the open AD5X OS. First stage: **our own
userspace on the stock kernel**. Nothing here has been put on a printer.

## Build

```
git clone --depth 1 --branch 2026.02.3 https://github.com/buildroot/buildroot.git buildroot/src
make -C buildroot/src O=$PWD/buildroot/output BR2_EXTERNAL=$PWD/buildroot ad5x_defconfig
make -C buildroot/src O=$PWD/buildroot/output BR2_EXTERNAL=$PWD/buildroot
```

`buildroot/src`, `buildroot/dl` and `buildroot/output` are git-ignored.
Output in `buildroot/output/images/` (see the `README.txt` there).

### Vendor-free (default) and private builds

The default build is **vendor-free**: no Flashforge/Ingenic file goes into
the images or `images/`. The printer uses its own copies instead: the stock
driver modules and board tools in `/data/ad5x/vendor` (filled by the
installer or at boot by `ad5x-vendor`, `docs/install.md`), and the stock
kernel already in its kernel partitions (updates carry no kernel). Check any
image or release file with:

```
tools/check_vendor_free.sh buildroot/output/images/rootfs.squashfs \
    buildroot/output-recovery/images/rootfs.squashfs ad5x-main-*.zip
```

A **private build** (your own printer only, never to be published) can
still bundle them from the local, git-ignored firmware download: set
`BR2_AD5X_BUNDLE_VENDOR=y` (menu "AD5X" in `make menuconfig`) or build with
`AD5X_VENDOR_FREE=0` in the environment (`AD5X_VENDOR_FREE=1` forces a
vendor-free build whatever the configuration says). Then:

| What | Default | Override |
|---|---|---|
| Stock driver modules (`/module_driver`) and board tools (`/usr/lib/ad5x/stock-tools`) | `firmware/ff-repo/stock5x` | `AD5X_STOCK_ROOTFS` |
| Stock kernels (copied to `images/`) | `firmware/stock-3.1.0/unpacked/kernel-2.0.1` | `AD5X_STOCK_KERNEL_DIR` |

`/usr/lib/ad5x/vendor-mode` in the image says `none` or `bundled`;
`images/IMAGES.txt` says which build it is.

## Hardware facts this is built on

From the stock kernel image and root filesystem (3.1.0 updater):

- SoC **Ingenic X2600** (XBurst2, MIPS32r5; device tree `ingenic,x2600`,
  blocks named `ad100`), plus a RISC-V co-processor (`rtos` partition).
- Stock kernel **Linux 5.10.186**, built by Ingenic's GCC 12.1 toolchain,
  u-boot legacy image loaded at 0x80F00000. Two builds ship: eMMC and
  SD-NAND (`dev_type=SDNAND` on the kernel command line).
- Stock userspace: Buildroot 2020.02, glibc 2.33, **hard float with a 64-bit
  FPU, NaN2008**. Drivers for display, touch, ADC, I2C, Ethernet, PWM and
  watchdog are out-of-tree modules in `/module_driver`
  (`vermagic 5.10.186+ SMP preempt MIPS32_R5`), loaded by a stock script.
- The stock kernel has **no cgroups**, so systemd can't run on it.
- Storage: 7.6 GB eMMC `mmcblk0`, GPT names, **A/B slots** (read on the
  user's unit, 2026-10-15):

  | Part | Name | Size | Use |
  |---|---|---|---|
  | p1 / p3 | `kernel` / `kernel2` | 8 MB | kernel slots |
  | p2 / p4 | `rootfs` / `rootfs2` | 100 MB | LZO squashfs root slots |
  | p5 | `ota` | 1 MB | text `ota:kernel` or `ota:kernel2`: slot to boot |
  | p6 | `usershare` | 1 GB | stock `/usr/prog` (ext4) |
  | p7 | `userdata` | 5.8 GB | stock `/usr/data` (ext4) |

- Kernel command line: `console=ttyS0,115200n8 ... init=/linuxrc
  root=/dev/mmcblk0p2 rootwait rootfstype=squashfs ro`. RAM ~480 MB.
- The kernel has USB storage, vfat, ext4, squashfs; **no loop devices**.

## What the image contains

- Toolchain: glibc, GCC 14, kernel headers 5.10, `-march=mips32r5
  -mfp64 -mnan=2008` (stock userspace is r2 code; the CPU is r5).
- BusyBox init (as stock) and eudev, read-only squashfs root.
- Python 3 with Klipper's dependencies; mainline Klipper at the same commit
  as the MCU images, `c_helper.so` cross-compiled, this project's extras and
  default `printer.cfg` / `ifs.cfg`.
- Moonraker v0.11.0 (`package/moonraker`, port 7125, user `klipper`,
  `S62moonraker`), with packages for its missing dependencies
  (`python-inotify-simple`, `python-libnacl`, `python-streaming-form-data`)
  and two small patches (stdlib `importlib.metadata`; `smart_open` only
  for S3/GCS uploads). Runs without Klipper.
- Fluidd (`package/fluidd`, release zip, `/usr/share/fluidd`; it updates
  itself from Fluidd into `/data/ad5x/web/fluidd`, `S61ad5x-web`) on
  port 80 through nginx (`S63nginx`; `rootfs-overlay/etc/nginx`), which
  proxies Moonraker's API and websocket. Pid and temp files in
  `/run/nginx`, log in `/var/log/nginx` (tmpfs); text files are gzipped
  at build time. Buildroot's own `S50nginx` is removed (`post-build.sh`).
- Klipper and Moonraker are compiled to bytecode at build time (the root
  is read-only, so Python couldn't cache it on the printer).
- Per-printer calibration: at first boot `S05ad5x-data` writes
  `printer_data/config/unit.cfg` from stock's `Adventurer5M.json`
  (`usershare` partition) with `ad5x-unit-cfg`.
- Start-up (`package/ad5x-system/init.d`): `S05ad5x-data` mounts
  `userdata` at `/data` (our files under `/data/ad5x`, stock files left
  alone), `S06ad5x-modules` checks the printer's own vendor files
  (`ad5x-vendor ensure`: `/data/ad5x/vendor`, filled from the saved stock
  system or a stock slot when missing) and loads the stock drivers from
  there, `S07ad5x-board` runs the PC11 heartbeat and the boot logo with
  stock's board tools (`/usr/bin/cmd_*` are wrappers that run them from
  `/data/ad5x/vendor` with their own libraries), NetworkManager
  (`S44ad5x-network`, `S45NetworkManager`, `S46ad5x-wifi`,
  docs/networkmanager.md) runs Ethernet and Wi-Fi (stock's saved networks
  imported on the first start; HelixScreen joins and saves networks, its
  switch turns the radio off; `/data/ad5x/wifi.disable`: no Wi-Fi), `S60ad5x-eboard` starts the
  toolhead board (`tools/boot_eboard.py`), `S61klipper` runs klippy as user
  `klipper` at nice -10. Both start only when `/data/ad5x/klipper.enable`
  exists: the boards still run stock firmware until they are reflashed.
- Ethernet: NetworkManager with stock's MAC (`usershare` `/MAC`); on the
  first start `S44ad5x-network` imports DHCP or the static address from
  `/data/ad5x/network.conf` (`MODE=dhcp|static`, `ADDRESS=a.b.c.d/nn`,
  `GATEWAY=`, `DNS="..."`), shared with the recovery OS.
- HelixScreen v1.1.0-beta.9 (`package/helixscreen`), the touch screen UI,
  built from source (git tag with its vendored submodules: LVGL, libhv,
  spdlog, libnl, wpa client, Lua) with our toolchain: upstream's MIPS
  target (fbdev, evdev, RGB565) but glibc and dynamic, `-march=mips32r5
  -mnan=2008 -mfp64`, packaging build (no mocks, no remote control), crash
  uploads and self-update off, no Bluetooth/systemd/SDL/DRM. Files in
  `/usr/lib/helixscreen` (printer pictures trimmed to FlashForge), settings
  and cache in `/data/ad5x/helixscreen`, log in
  `printer_data/logs/helixscreen.log`. `S70helixscreen` runs `helix-screen`
  on `/dev/fb0` against Moonraker at 127.0.0.1:7125, only when
  `/data/ad5x/helixscreen.enable` exists. `/etc/os-release` carries
  `VERSION_CODENAME="AD5X"` so it picks its AD5X touch calibration.
- Dropbear SSH, root key from `/data/ad5x/ssh/authorized_keys`. Serial
  login on the debug console, ttyS0 (the other UARTs belong to boards).

## Klipper configuration on the printer

`/home/klipper/printer_data/config` (on `/data`, kept across updates):

| File | What | Updated by |
|---|---|---|
| `printer.cfg` | Short: includes `/usr/share/ad5x/config/ad5x.cfg` (factory defaults: hardware and stock behaviour; it includes `ifs.cfg`, `setup.cfg`, then `macros/*.cfg` and `plugins.cfg` from this directory), then `unit.cfg`, then `local.cfg`; Klipper's SAVE_CONFIG block below | Template copied once; SAVE_CONFIG |
| `macros/*.cfg` | This system's editable defaults beyond stock: `print_start.cfg` (mesh every print, status line), `prime_line.cfg`, `quick_actions.cfg`, `ifs_templates.cfg` (`docs/config-layout.md`) | Copied at first boot from `/usr/share/ad5x/defaults/macros`; an update with a changed template replaces the file, keeping an edited one as `<name>.cfg.bak-<date>` (`config-updates.txt`, `CONFIG_BACKUPS`); `.ad5x-templates.json` records the template versions |
| `unit.cfg` | Per-printer values from stock's `Adventurer5M.json` | Written once at first boot |
| `local.cfg` | This printer's own overrides (e.g. nozzle size), read last | The user |
| `plugins.cfg` | Enabled plugins, read at the end of `ad5x.cfg` (`docs/plugins.md`); first boot: zmod-compat, nopoop (+ bambufy-compat / recommend after zMod) | Written once; `ENABLE_PLUGIN` / `DISABLE_PLUGIN` |
| `moonraker-plugins.conf` | Enabled plugins' Moonraker parts, read after `moonraker.conf` | Generated (S62moonraker, Klipper) |
| `variables.cfg` | Saved state: Z offset, loaded lane, colours, centre Z | Klipper |
| `moonraker.conf` | Moonraker | Template copied once |

Shipped plugins are in `/usr/share/ad5x/plugins` (from `klipper/plugins/`),
other people's and the user's own in `/data/ad5x/plugins` (never touched by
updates); plugin API version in `/usr/lib/os-release` (`AD5X_PLUGIN_API`,
`docs/plugin-api.md`).

The factory defaults update with the image; the `macros/` files with it
too (edited ones backed up first, `ad5x-config-templates` in
`S05ad5x-data`); everything else here is never replaced. Lasting personal
changes go in `local.cfg`. Which file holds what, and why:
`docs/config-layout.md`. SAVE_CONFIG can't override an option the
defaults set (PID results etc.): copy those into `local.cfg`. A full
`printer.cfg` from before this layout is converted at boot (`S05ad5x-data`):
old copy kept in `backup-full-config-<n>/`, SAVE_CONFIG block carried over.

Root login uses stock's root password (taken from `/usr/prog/etc/shadow` at
boot); keys in `/data/ad5x/ssh/authorized_keys`; SSH host keys kept in
`/data/ad5x/ssh/hostkeys`.

## USB test mode

`images/usb-test.img`, written whole to a USB stick, starts our system
without changing the printer. Stock `/usr/prog/app_startup.sh` runs
`flashforge_init.sh` from a FAT USB stick at boot, as root, before the
Flashforge app and zMod. Ours (`board/ad5x/usb/flashforge_init.sh`) mounts
the stick's ext4 partition, repeats what stock start-up would still do
(PC11 heartbeat `sys_start.sh`, Ethernet MAC from `/usr/prog/MAC`, Wi-Fi
and touch drivers), chroots into our root and runs our init scripts, then
never returns so the stock app doesn't start. Stock's dropbear stays up
(root/root): the way back in. Log: `ad5x-usb.log` on the stick.

Checked against the user's unit (read-only) and rehearsed with our init
scripts under qemu (`AD5X_USB=1`):

- Stock's dropbear reads the root password and host key from `/etc`, which
  stock bind-mounts from `/usr/prog/etc` only *after* the stick hook. The
  script does that bind first, so SSH works as it does today.
- Stock already runs `mdev -df` on the shared `/dev`; ours stays off and
  only gives `/dev/ttyS*` group `dialout` (`S10udevd` in the overlay).
- DNS: stock also runs dhcpcd, which leaves no nameservers; the script hands the lease's DNS servers to our `/run/resolv.conf`.
- eth0 stays stock's (no second DHCP client; `/etc/network/interfaces` is
  loopback only). Our dropbear finds port 22 taken and stays off.

Touch screen: the stock boot logo stays on the panel and nothing else uses
`/dev/fb0`, so HelixScreen can be tried by creating
`/data/ad5x/helixscreen.enable` (SSH) and running
`/etc/init.d/S70helixscreen start` (or rebooting).

Unplug and power-cycle to return to stock. Never put an `AD5X-*.tgz` on
the stick: stock installs that as a firmware update.

## Recovery image (slot A)

A second configuration in this tree, `ad5x_recovery_defconfig`: a small
recovery/update OS for slot A (same toolchain and stock kernel; SSH,
signed SWUpdate updates of slot B, backup/restore, USB rescue). Packages
`package/ad5x-recovery`, board files `board/ad5x-recovery`. Built into its
own output directory:

```
make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot ad5x_recovery_defconfig
AD5X_SWU_PUBKEY=~/.config/ad5x/swupdate-public.pem \
  make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot
```

Main-OS updates (rootfs only, no kernel): `tools/make_swu.sh`. Install
stick / SSH install files: `tools/make_install_stick.sh`. Tests:
`tools/test_recovery.sh`, `tools/test_install.sh`. Everything else:
`docs/recovery-os.md`, `docs/install.md`.

## Not done yet

- Own kernel: Ingenic's 6.6 SDK kernel runs the printer when started from
  RAM (`kernel-ingenic66/`, chainload: Klipper, IFS, screen, touch);
  a mainline (7.x / 6.18 LTS) port is prepared in `kernel-mainline/`.
  Own boot loader: not planned; the stock SPL boots our uImage unchanged.
- First install from stock (USB stick or SSH): `docs/install.md`
  (`tools/make_install_stick.sh`, `tools/install/`); tested under qemu
  only. The root slot is 100 MB, so the squashfs must stay under that.
