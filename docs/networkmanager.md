# NetworkManager

Status: built (`feature-networkmanager`), not yet tested on the printer.

## Why

Kiln brings networking up with its own scripts: `S41ad5x-eth` (Ethernet:
stock's MAC, DHCP or a static address) and `S42ad5x-wifi` (242 lines:
wpa_supplicant, udhcpc driven by wpa_cli, importing stock's networks,
`scan_ssid`, power saving off, the rfkill off switch, `wifi.log`). Every
new case (two links up at once, issue #8; a Wi-Fi switch that strands
the printer, issue #37; hidden networks; roaming) means more script, and
HelixScreen needs Kiln patches (0016, 0044, 0045) to drive wpa_supplicant
directly. NetworkManager handles all of these itself, and HelixScreen
already has a NetworkManager backend (`nmcli`), which it picks on its own
when NetworkManager runs.

## Decisions (the user's)

- **eudev replaces mdev** in both images: buildroot's NetworkManager
  needs udev.
- **The recovery OS moves to NetworkManager too:** one network stack
  everywhere.
- **One-way import:** the existing networks are imported into
  NetworkManager once. `wpa_supplicant.conf` is left in place but not
  kept in sync, so after a rollback to an image from before the switch,
  networks added under NetworkManager are missing (those from before it
  are all there).

## What changes

### Packages (main and recovery images)

- `BR2_ROOTFS_DEVICE_CREATION_DYNAMIC_EUDEV` instead of `..._MDEV`.
- `network-manager` with `nmcli`; it brings D-Bus, glib, gnutls, libndp,
  util-linux's libuuid/libmount.
- `wpa_supplicant` with its D-Bus control interface (NetworkManager
  drives it over D-Bus); the CLI stays for diagnostics.
- udhcpc, `S41ad5x-eth` and `S42ad5x-wifi` go; NetworkManager does DHCP
  itself (its internal client).
- HelixScreen: its wpa_supplicant patches (0016, 0044, 0045) are dropped
  where the NetworkManager backend makes them moot.

### Size (the first thing to measure)

The main squashfs is 87.8 MB of a 100 MiB (104.9 MB) slot, and it holds
the recovery OS (6.9 MB) inside. NetworkManager's stack lands twice:
once in the main image, once in the recovery image inside it. A trial
build measures both before anything else is done.

Measured (2026-11-09, a trial build with Kiln's toolchain): what's new to
Kiln (NetworkManager with nmcli, glib, D-Bus, eudev, readline, ncurses,
pcre2) is 19 MB of files, 6.6 MB in the image's squashfs (LZO, 128K
blocks). eudev's hardware database (9.8 MB of `.hwdb` text, vendor
names Kiln has no use for) is left out (`BR2_PACKAGE_EUDEV_ENABLE_HWDB`
off). With the recovery image growing by about the same inside it, the
main image goes from 87.8 to about 101 MB of the 104.9 MB slot: it
fits, with about 4 MB left. Trimming what Kiln doesn't use (test
programs, glib's tools, NetworkManager's dispatcher) wins back some of
it. If it ever doesn't fit,
the options are, in order: trim (no gnutls: NetworkManager can build
without crypto for WPA-PSK, since wpa_supplicant does the crypto; no
ModemManager, no PPP, no Bluetooth), drop NetworkManager from recovery
(back to wpa_supplicant there), or compress the main image with XZ
(the stock kernel reads only LZO, so this one needs care).

### Device handling (mdev -> eudev)

Everything mdev does today must have a udev equivalent, checked on all
three kernels (stock 5.10, Kiln's 6.6, mainline): the serial ports for
Klipper (`ttyS2`, `ttyS4`, `ttyS5`, `ttyS7`; permissions for user
klipper), the camera (`/dev/video*`), the framebuffer and DRM device,
input devices, USB storage automount (if mdev does it), the PWM sound
channel set up by `S35ad5x-sound`, and firmware loading for stock's
vendor drivers (the 8821cu module). The mdev rules file is the checklist.

From `etc/mdev.conf` and `S10mdev`:

- `ttyS*` to group `dialout`, mode 660 (user klipper is in dialout;
  eudev's default rules do the same), `ttyUSB*` root 660, input devices
  root 640, the ALSA nodes group `audio`.
- Module autoloading from `MODALIAS` (eudev's module loading; on the
  stock kernel `S06ad5x-modules` still loads stock's drivers).
- **USB test mode** (`AD5X_USB`): Kiln runs beside stock, sharing the
  `/dev` that stock's own mdev runs; S10 only fixes the `ttyS*` group
  there. eudev must not start in that mode either.
- The recovery OS makes `/dev/disk/by-partlabel/*` links itself
  (`S01ad5x-recovery`) because mdev doesn't; eudev's standard rules make
  them, so the two must not fight.

### Configuration and migration (first boot with NetworkManager)

NetworkManager keeps its connections as keyfiles in
`/data/ad5x/NetworkManager/system-connections/` (the root is read-only),
pointed to by `/etc/NetworkManager/NetworkManager.conf`.

On the first start (no keyfile directory yet) a one-shot import:

- each network in `/data/ad5x/wpa_supplicant.conf` becomes a Wi-Fi
  connection (SSID, PSK or open, `hidden=true` where Kiln set
  `scan_ssid=1`, since stock never marks hidden networks; priority kept);
- `/data/ad5x/network.conf` (DHCP or static) becomes the Ethernet
  connection;
- with no `wpa_supplicant.conf` either (a fresh install from stock),
  stock's networks (usershare `/wifi/wpa_supplicant.conf`) are imported
  instead, as S42 does today.

The import writes a marker; it never runs again, and the old files are
left as they are (for older images and for reference).

### Behaviour to keep

- **Ethernet MAC:** stock's address (usershare `/MAC`) on every kernel:
  set as the Ethernet connection's `cloned-mac-address`.
- **Two links:** Ethernet preferred, Wi-Fi kept up as a fallback, by route
  metric (replaces the `ignore_routes_with_linkdown` workaround, #8).
- **Wi-Fi power saving off** (`wifi.powersave = 2`), needed by rtw88
  (#37).
- **Off switch:** HelixScreen's Wi-Fi switch (`nmcli radio wifi off`)
  stays off across reboots, with or without Ethernet, as S42 kept it
  since issue #44 (the touch screen is the way back). The recovery OS has
  no HelixScreen and shares NetworkManager's state on `/data`, so it turns
  the radio back on at its start.
  `/data/ad5x/wifi.disable` keeps meaning no Wi-Fi at all (the device is
  unmanaged).
- **Logs:** `printer_data/logs/wifi.log` keeps its role: what started,
  the driver and its settings, how many connections (no names or
  secrets), the previous start kept as `wifi.log.1`.
- **A broken config** must not leave the printer without a way to join a
  network: a keyfile NetworkManager can't load is put aside, and the
  screen can still add a network.

### Kernels

NetworkManager talks nl80211 to the Wi-Fi driver. Kiln's 6.6 and mainline
use rtw88 (nl80211). The stock 5.10 fallback uses Realtek's vendor 8821cu
module, which registers with cfg80211 too; that has to be checked on the
printer. If it doesn't work there, the fallback on the stock kernel keeps
wpa_supplicant for Wi-Fi (NetworkManager can leave a device to it).

## Testing

On the printer, on each of stock 5.10, 6.6 and mainline: first boot with
an existing `/data` (import), a fresh `/data` (stock's networks),
Ethernet only, Wi-Fi only, both (Ethernet preferred; unplugging it keeps
the printer reachable over Wi-Fi), a hidden network, a static address,
the screen's Wi-Fi switch off then a reboot, `wifi.disable`, and the
recovery OS joining Wi-Fi to fetch an update. Plus the device checklist
above, and Klipper connecting to all four MCUs.

## How it is built

| File | What it does |
|---|---|
| `configs/ad5x_defconfig`, `ad5x_recovery_defconfig` | eudev (no hardware database), D-Bus, NetworkManager with nmcli, wpa_supplicant's D-Bus interface |
| `board/ad5x/rootfs-overlay/etc/init.d/S10udevd` | Buildroot's udevd script, not started in USB test mode (only `ttyS*` to group dialout there, as S10mdev did) |
| `.../etc/udev/rules.d/80-net-name-slot.rules` | Empty: interfaces keep the names `eth0` and `wlan0` |
| `board/ad5x-recovery/rootfs-overlay/etc/udev/rules.d/60-persistent-storage.rules` | Empty, recovery only: no `/dev/disk/by-*` links from udev; `S01ad5x-recovery` makes the by-partlabel links, only for the partitions it has checked |
| `.../etc/NetworkManager/NetworkManager.conf` | keyfile plugin with the connections on `/data`, internal DHCP, `rc-manager=file` (`/etc/resolv.conf` links to `/run/resolv.conf`), `wifi.powersave=2`, no random MAC while scanning |
| `.../etc/default/NetworkManager` | Sourced by Buildroot's `S45NetworkManager`: not in USB test mode |
| `board/ad5x/network-nm.sh` | Both post-build scripts: `/var/lib/NetworkManager` linked to `/data/ad5x/NetworkManager/lib`, the old scripts' files and unused tools (pcre2/glib command line tools, the dispatcher, bash completion) removed |
| `package/ad5x-system/lib/nm-import.sh` | The one-time import (busybox sh and awk; recovery has no Python). SSIDs as byte lists (`od`: busybox awk counts characters, not bytes), keyfile strings escaped, WEP and enterprise networks left out and counted |
| `package/ad5x-system/init.d/S44ad5x-network` | Before S45: the directories on `/data`, the import once (`/data/ad5x/NetworkManager/imported`), `wifi.disable` as an unmanaged `wlan0` (`/run/NetworkManager/conf.d`); `/data` not writable: connections in RAM. Log `printer_data/logs/network.log` |
| `package/ad5x-system/init.d/S46ad5x-wifi` | After S45, in the background: `wifi.log`, the radio back on in the recovery OS, joined or not after 60 s, power saving |
| `package/ad5x-recovery/bin/ad5x-status` | `net_mode` from the active connection; a `network` key |

Removed: `S10mdev`, `etc/mdev.conf`, `S41ad5x-eth`, `S42ad5x-wifi`,
`lib/network.sh`. USB test mode (`board/ad5x/usb/flashforge_init.sh`)
keeps its own udhcpc.

HelixScreen picks its NetworkManager backend by itself (`/run/NetworkManager`
and `nmcli`). Its Kiln patches for the wpa_supplicant backend (0016, 0044,
0045) are left in until the screen has been tried with NetworkManager.
