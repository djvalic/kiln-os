# Kiln OS Buildroot images

A Buildroot external tree for Kiln OS: the main OS (`ad5x_defconfig`, slot
B) and the recovery OS (`ad5x_recovery_defconfig`, slot A, see "Recovery
image" below). Both run on the printers; releases are built from this tree.

## Build

Besides Buildroot, the main OS needs two things outside the tree, both for
the kernels it carries:

- **Ingenic's 6.6 SDK kernel** for `ad5x-kernel66` (`kernel-ingenic66/`):
  a checkout at `~/workspace/ingenic-sdk-6.6` (or set
  `BR2_PACKAGE_AD5X_KERNEL66_SDK`), as `kernel-ingenic66/README.md`
  describes. Releases are built from commit
  `a98c2e1f22e4263ddd4153a4eca4db4dcfd2777b`.
- **A prepared linux-5.10.186 tree** for `chainload.ko`, made with this
  tree's toolchain by `kernel-ingenic66/chainload/setup.sh` (into
  `~/workspace/chainload-build`, or set `BR2_PACKAGE_AD5X_KERNEL66_KDIR510`).
  So the toolchain is built first.

The mainline 7.3 kernel (`ad5x-kernel-mainline`) downloads its source and
Wi-Fi firmware from kernel.org itself (sha256-pinned).

```
git clone --depth 1 --branch 2026.02.3 https://github.com/buildroot/buildroot.git buildroot/src
git clone --filter=blob:none \
  https://github.com/Llixuma/ingenic-linux-kernel6.6-x2000-v1.0-20250221.git \
  ~/workspace/ingenic-sdk-6.6
git -C ~/workspace/ingenic-sdk-6.6 checkout a98c2e1f22e4263ddd4153a4eca4db4dcfd2777b
export AD5X_VENDOR_FREE=1

# Recovery OS first: the main OS carries it
make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot ad5x_recovery_defconfig
make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot

# Main OS: toolchain, the 5.10 tree for chainload.ko, then the image
make -C buildroot/src O=$PWD/buildroot/output BR2_EXTERNAL=$PWD/buildroot ad5x_defconfig
make -C buildroot/src O=$PWD/buildroot/output BR2_EXTERNAL=$PWD/buildroot toolchain
kernel-ingenic66/chainload/setup.sh
AD5X_RECOVERY_IMAGE=$PWD/buildroot/output-recovery/images/rootfs.squashfs \
  make -C buildroot/src O=$PWD/buildroot/output BR2_EXTERNAL=$PWD/buildroot
```

Without `AD5X_RECOVERY_IMAGE` the main OS carries no recovery OS, and a
printer updated with it keeps the one it has. `AD5X_VERSION` sets the
version the image reports (default: from `git describe`). `tools/release.sh`
runs the two image builds for a release (with the SDK and the 5.10 tree
already in place) and makes the update and install files.

`buildroot/src`, `buildroot/dl`, `buildroot/output` and
`buildroot/output-recovery` are git-ignored. Output in
`buildroot/output/images/` (see the `README.txt` there).

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
- Storage: 7.6 GB eMMC `mmcblk0`, GPT names, **A/B slots** (read on one
  printer, 2026-10-15):

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
- BusyBox init and mdev (as stock), read-only squashfs root.
- Python 3 with Klipper's dependencies; mainline Klipper at the same commit
  as the MCU images, `c_helper.so` cross-compiled, this project's extras and
  default `printer.cfg` / `ifs.cfg`.
- Moonraker (`package/moonraker`, v0.11.0 plus the commits up to the one
  `moonraker.mk` pins; port 7125, user `klipper`, `S62moonraker`), with
  packages for its missing dependencies (`python-inotify-simple`,
  `python-libnacl`, `python-streaming-form-data`) and Kiln's patches in
  `package/moonraker/`. Runs without Klipper.
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
- Start-up (`package/ad5x-system/init.d`): on Kiln's kernels
  `S02ad5x-logo` puts the default boot logo on the screen first, from
  frames rendered ahead (`usr/share/ad5x/logo-16.raw.gz` and
  `logo-32.raw.gz`, `tools/make_logo.py --raw`), `S05ad5x-data` mounts
  `userdata` at `/data` (our files under `/data/ad5x`, stock files left
  alone), `S06ad5x-modules` checks the printer's own vendor files
  (`ad5x-vendor ensure`: `/data/ad5x/vendor`, filled from the saved stock
  system or a stock slot when missing) and loads the stock drivers from
  there, `S07ad5x-board` runs the PC11 heartbeat and the boot logo with
  stock's board tools (`/usr/bin/cmd_*` are wrappers that run them from
  `/data/ad5x/vendor` with their own libraries), `S42ad5x-wifi` runs
  wpa_supplicant on `/data/ad5x/wpa_supplicant.conf` (stock's saved
  networks on the first start; HelixScreen joins and saves networks, its
  switch turns the radio off; `/data/ad5x/wifi.disable`: no Wi-Fi), `S60ad5x-eboard` starts the
  toolhead board (`tools/boot_eboard.py`), `S61klipper` runs klippy as user
  `klipper` at nice -10, only when `/data/ad5x/klipper.enable` exists:
  `ad5x-mcu boot` (run by `S60ad5x-eboard`) writes the boards' Klipper
  firmware and creates that file once both boards run it.
- `S41ad5x-eth`: Ethernet with stock's MAC (`usershare` `/MAC`), then DHCP
  or a static address from `/data/ad5x/network.conf` (`MODE=dhcp|static`,
  `ADDRESS=a.b.c.d/nn`, `GATEWAY=`, `DNS="..."`; shared with the recovery OS,
  helper `/usr/lib/ad5x/network.sh`; an invalid static setup falls back to
  DHCP).
- HelixScreen v1.1.0-rc.1 with Kiln's patches (`package/helixscreen`), the touch screen UI,
  built from source (git tag with its vendored submodules: LVGL, libhv,
  spdlog, libnl, wpa client, Lua) with our toolchain: upstream's MIPS
  target (fbdev, evdev, RGB565) but glibc and dynamic, `-march=mips32r5
  -mnan=2008 -mfp64`, packaging build (no mocks, no remote control), crash
  uploads and self-update off, no Bluetooth/systemd/SDL/DRM. Files in
  `/usr/lib/helixscreen` (printer pictures trimmed to FlashForge), settings
  and cache in `/data/ad5x/helixscreen`, log in
  `printer_data/logs/helixscreen.log`. `S70helixscreen` runs `helix-screen`
  on `/dev/fb0` against Moonraker at 127.0.0.1:7125; it is on by default,
  and `/data/ad5x/helixscreen.disable` turns it off. `/etc/os-release` carries
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
| `local.cfg` | This printer's own overrides (e.g. nozzle size), read last | You |
| `plugins.cfg` | Enabled plugins, read at the end of `ad5x.cfg` (`docs/plugins.md`); first boot: zmod-compat, nopoop (+ bambufy-compat / recommend after zMod) | Written once; `ENABLE_PLUGIN` / `DISABLE_PLUGIN` |
| `plugins-active.cfg` | `plugins.cfg` with the enabled plugins that can't run left out; what `ad5x.cfg` includes | Generated (Klipper before each config read, S61klipper) |
| `moonraker-plugins.conf` | Enabled plugins' Moonraker parts, read after `moonraker.conf` | Generated (S62moonraker, Klipper) |
| `variables.cfg` | Saved state: Z offset, loaded lane, colours, centre Z | Klipper |
| `moonraker.conf` | Moonraker | Template copied once |

Shipped plugins are in `/usr/share/ad5x/plugins` (from `klipper/plugins/`),
other people's and your own in `/data/ad5x/plugins` (never touched by
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

Checked against one printer (read-only) and rehearsed with our init
scripts under qemu (`AD5X_USB=1`):

- Stock's dropbear reads the root password and host key from `/etc`, which
  stock bind-mounts from `/usr/prog/etc` only *after* the stick hook. The
  script does that bind first, so SSH works as it does today.
- Stock already runs `mdev -df` on the shared `/dev`; ours stays off and
  only gives `/dev/ttyS*` group `dialout` (`S10mdev` in the overlay).
- DNS: stock also runs dhcpcd, which leaves no nameservers; the script hands the lease's DNS servers to our `/run/resolv.conf`.
- eth0 stays stock's (no second DHCP client; `/etc/network/interfaces` is
  loopback only). Our dropbear finds port 22 taken and stays off.

Touch screen: the stock boot logo stays on the panel and nothing else uses
`/dev/fb0`, so HelixScreen runs there as on the printer (`S70helixscreen`;
`/data/ad5x/helixscreen.disable` keeps it off).

Unplug and power-cycle to return to stock. Never put an `AD5X-*.tgz` on
the stick: stock installs that as a firmware update.

## Recovery image (slot A)

A second configuration in this tree, `ad5x_recovery_defconfig`: a small
recovery/update OS for slot A (same toolchain and stock kernel; SSH,
SWUpdate updates of slot B, unsigned by default, backup/restore, USB
rescue). Packages
`package/ad5x-recovery`, board files `board/ad5x-recovery`. Built into its
own output directory:

```
make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot ad5x_recovery_defconfig
make -C buildroot/src O=$PWD/buildroot/output-recovery BR2_EXTERNAL=$PWD/buildroot
```

That image takes unsigned updates (every file still has its sha256
checked). For one that requires signed updates, see `docs/recovery-os.md`,
"Open update mode" (`AD5X_SWU_SIGNED=1` and a public key).

Main-OS updates (rootfs only, no kernel): `tools/make_swu.sh`. Install
stick / SSH install files: `tools/make_install_stick.sh`. Tests:
`tools/test_recovery.sh`, `tools/test_install.sh`. Everything else:
`docs/recovery-os.md`, `docs/install.md`.

## Kernels and limits

- Kernels: the stock 5.10 kernel in the boot slots starts our 6.6 kernel
  (`kernel-ingenic66/`) from RAM at every boot (`chainload.ko`,
  `S00ad5x-kernel`); the mainline 7.3 kernel (`kernel-mainline/`) is
  in the image too, opt-in (`ad5x-kernel mainline on`). Own boot loader:
  not planned; the stock SPL boots the stock uImage unchanged.
- First install from stock (USB stick or SSH): `docs/install.md`
  (`tools/make_install_stick.sh`, `tools/install/`); done over SSH on a
  printer, from a USB stick under emulation only. The root slot is 100 MB,
  so the squashfs must stay under that.
