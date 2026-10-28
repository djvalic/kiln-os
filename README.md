![Kiln OS](docs/brand/logo/kiln-lockup-single-dark.svg)

# Kiln OS

*An open operating system for the Flashforge Adventurer 5X: mainline Klipper, Fluidd and a touch screen, with a recovery system.*

An open operating system for the **Flashforge Adventurer 5X (AD5X)**. It
replaces the stock firmware with a Buildroot Linux system running mainline
Klipper on the host and on both printer boards, Moonraker, Fluidd, the
HelixScreen touch interface, a Klipper driver for the AD5X's 4-colour IFS,
and a small recovery OS for updates and rescue.

> Not affiliated with or endorsed by Flashforge. "Flashforge" and
> "Adventurer 5X" are their trademarks. Use at your own risk: this replaces
> the printer's firmware.

## Status

Runs daily on one AD5X (0.6 mm nozzle). It was installed on that printer
from the stock firmware (with zMod) over SSH, and every release since has
been installed from Fluidd, through the recovery OS. Installing from a USB
stick has been tested under emulation only
([docs/install.md](docs/install.md)). Expect rough edges, and read
[docs/deviations-from-stock.md](docs/deviations-from-stock.md) before
installing: it lists every behaviour that differs from stock, what to look
for if it goes wrong, and how to go back.

## Compared with the stock firmware

- **Mainline Klipper everywhere.** Host and both boards (mainboard and
  toolhead "eboard") run mainline Klipper v0.13 instead of Flashforge's
  2024 fork. Kiln OS writes the tested board firmware itself and puts
  Flashforge's back when you return to stock
  ([docs/mcu-flashing.md](docs/mcu-flashing.md)). Mainline's
  safety checks stay on: TMC driver fault checks (off in stock's fork) and
  the default hotend heating check.
- **Open web and touch interfaces.** Fluidd on port 80 with Moonraker, and
  HelixScreen on the panel. The touch screen can also be used from the
  browser. USB cameras stream to Fluidd (one `ustreamer` per camera).
- **Recovery OS and A/B slots.** Kiln OS uses the printer's own two eMMC
  slots: the main system in one, a recovery OS in the other. A main system
  that fails to finish starting lands in recovery at the next power cycle.
  Recovery installs updates, makes and restores backups, and can boot from
  USB ([docs/boot-slots.md](docs/boot-slots.md),
  [docs/recovery-os.md](docs/recovery-os.md),
  [docs/emmc-backup.md](docs/emmc-backup.md)).
- **Updates from Fluidd.** A **Kiln OS** entry in Fluidd's update manager
  installs new releases through the recovery OS (about 3 minutes). Between
  releases, Klipper and Moonraker can be updated on their own entries as
  tested packages. Every release is built and tested against the boards'
  flashed firmware first ([docs/updates.md](docs/updates.md)).
- **Print start.** Every print probes a mesh of the print area, then draws
  a prime line in front of the objects. Both can be turned off per printer.
  From a cold bed it first waits for the plate to stop moving, measured
  on your printer with the load cells (`BED_SOAK_CALIBRATE`)
  ([docs/print-start.md](docs/print-start.md)).
- **Setup wizard** on the touch screen at first boot: time zone,
  self-check, PID, bed mesh, input shaper, IFS tuning and a first-layer Z
  offset test ([docs/setup-wizard.md](docs/setup-wizard.md)).
- **Plugins.** Optional bundles of config and Klipper extras, switched on
  the touch screen (Settings > Plugins) or with `ENABLE_PLUGIN` /
  `DISABLE_PLUGIN`, with a documented API for your own. The screen also
  installs the tested ones from their own repositories: notifications
  with a camera photo ([kiln-notify](https://github.com/djvalic/kiln-notify)),
  timelapse ([kiln-timelapse](https://github.com/djvalic/kiln-timelapse)),
  Spoolman ([kiln-spoolman](https://github.com/djvalic/kiln-spoolman))
  ([docs/plugins.md](docs/plugins.md), [docs/plugin-api.md](docs/plugin-api.md)).
- **Sound.** The speaker plays chimes on print events, `M300` and your own
  MIDI files (zMod's `PLAY_MIDI`), set on the screen
  ([docs/sound.md](docs/sound.md)).
- **Editable config.** The image holds the hardware and stock behaviour.
  This system's choices live in editable files on the printer, and your
  own changes go in `local.cfg`. Updates refresh the editable files and
  back up the ones you changed ([docs/config-layout.md](docs/config-layout.md)).
- **IFS.** Swap tuning (`IFS_TUNE`, like QuickSwap), a measured
  colour-change flush (`IFS_PURGE_TEST`), an optional sensor-checked purge
  that uses much less filament, early heating for swaps while idle, and
  new-spool pre-feed. The stock sequence stays the default (see
  [IFS](#ifs) below).
- **No Flashforge files in the images.** The drivers, board tools and
  stock kernel the system needs are copied from your own printer by the
  installer ([docs/install.md](docs/install.md)).

## Compared with zMod

[zMod](https://github.com/ghzserg/zmod) adds Klipper extras, macros and a
web interface to the stock firmware: it runs in a chroot hooked into stock's
start-up, next to Flashforge's system. Kiln OS replaces that system:

- **The whole OS is open.** No Flashforge user space runs, and the boards
  run mainline Klipper firmware built from source.
- **Recovery and rollback built in.** It has a recovery OS in the other
  slot, try-once boots into the main system, backups and USB rescue, and
  the way back to stock ([docs/install.md](docs/install.md)).
- **Updates are images.** Each update replaces the whole system, is tested
  before release, and installs from Fluidd.
- **Your zMod G-code keeps working.** G-code sliced with zMod's and
  Bambufy's AD5X profiles prints unchanged: `START_PRINT`, `END_PRINT`,
  `_GOTO_TRASH`, the nopoop purge modes and Bambufy's `_NOPOOP` map to
  this system's macros ([docs/zmod-compat.md](docs/zmod-compat.md)).
  There is one difference: in prime-only mode the prime happens at the
  purge box, not over the print, so the part gets no bead.
- **Moving over keeps your settings.** On a printer that ran zMod, the
  first boot reads zMod's plugin settings and enables the matching plugins
  ([docs/plugins.md](docs/plugins.md)). zMod's files stay where they are.

## The kernel

Kiln OS runs **our own Linux 6.6**, built from Ingenic's X2600 SDK kernel
with AD5X patches ([kernel-ingenic66/](kernel-ingenic66/)). Its drivers are
built in from source instead of Flashforge's out-of-tree modules:

- the display: an LVDS panel driver for the KX070 and fixes to Ingenic's
  display driver, so the kernel starts the screen itself;
- the speaker on its PWM pin ([docs/sound.md](docs/sound.md));
- RS-485 transmit enable for the IFS port;
- Wi-Fi through mainline `rtw88`, and the touch screen through mainline
  `tsc2007`.

The printer's stock 5.10 kernel stays in its boot slot, and every boot
still begins with it: the first boot script (`S00ad5x-kernel`) loads our
kernel from the release image and starts it from RAM (`chainload.ko`; the
stock kernel has no kexec). Nothing is written to the boot slots or the
boot flag, and there is no setting to choose a kernel.

The stock kernel is only the safety net: if a start of ours doesn't
complete (a hang, then a power cycle; or a panic, which reboots by itself),
the printer comes up on the stock kernel instead, with Flashforge's drivers
(Klipper, the screen and the network still run; no speaker), and stays on
it until an update brings another release of our kernel, which is tried
at once. `ad5x-kernel` shows the running kernel and any failure;
`ad5x-kernel retry` tries ours again from the next boot. Details:
[docs/deviations-from-stock.md](docs/deviations-from-stock.md) (last
section).

## IFS

The IFS (the AD5X's 4-colour filament system) is driven by a Klipper module,
`klipper/extras/ifs.py`. It handles tool changes, cut, unload and load,
purge modes, swap tuning and new-spool pre-feed. HelixScreen shows an IFS
panel. The serial protocol, as far as it is known, is documented in
[docs/ifs-protocol.md](docs/ifs-protocol.md). Each IFS behaviour that
differs from stock is listed in
[docs/deviations-from-stock.md](docs/deviations-from-stock.md).
If the IFS drops off, it retries every 10 seconds on its own; if it does not
come back in line, see [docs/ifs-troubleshooting.md](docs/ifs-troubleshooting.md).

## Install, update, recover, go back

> **Before installing:** your stock or zMod settings and configs are not
> used by Kiln OS (only the Z offset, cutter and purge-box positions and
> zMod's plugin choices carry over). Back up your `config` folder and your
> calibration first. At its first start Kiln OS writes mainline Klipper
> firmware to both boards by itself; going back to stock writes Flashforge's
> back ([docs/mcu-flashing.md](docs/mcu-flashing.md)). Details:
> [docs/install.md](docs/install.md).

- **Install** from the stock firmware (zMod optional) with a FAT32 USB
  stick, or over SSH. The installer saves the stock system first:
  [docs/install.md](docs/install.md).
- **Update** from Fluidd (Settings → Software Updates → Kiln OS), or with a
  release `.zip` on a USB stick: [docs/updates.md](docs/updates.md).
- **Recover**: [docs/recovery-os.md](docs/recovery-os.md). A failed start
  lands in the recovery OS, which has SSH, an update page on port 8080,
  backup and restore, and USB rescue.
- **Back to stock**: the saved stock system goes back into its slot with
  `ad5x-restore-stock` ([docs/install.md](docs/install.md)).

## Building

See [buildroot/README.md](buildroot/README.md). Two Buildroot
configurations, `ad5x_defconfig` (main OS) and `ad5x_recovery_defconfig`
(recovery OS), build with the project's own toolchain. The MCU firmware is
built by `tools/build_mcu.sh`, the update and install files by
`tools/make_swu.sh` and `tools/make_install_stick.sh`.
`tools/check_vendor_free.sh` checks that an image contains no Flashforge
files.

## Credits

This builds on the work of many projects:

- [Klipper](https://www.klipper3d.org/) (GPL-3.0) and
  [Moonraker](https://github.com/Arksine/moonraker) (GPL-3.0)
- [Fluidd](https://github.com/fluidd-core/fluidd) (GPL-3.0)
- [HelixScreen](https://github.com/prestonbrown/helixscreen) (GPL-3.0); our
  patches are in `buildroot/package/helixscreen/`
- [zMod](https://github.com/ghzserg/zmod) by ghzserg (GPL-3.0): macro names
  and behaviour, for compatibility
- [xblax's AD5M Klipper mod](https://github.com/xblax/flashforge_ad5m_klipper_mod):
  the MCU bootloader patches in `klipper/mcu-patches/` (GPL-3.0)
- [QuickSwap](https://github.com/ninjamida/quickswap-5x) and NoPoop by
  ninjamida, and Bambufy: ideas and G-code interfaces (no code copied)
- Hunter Laux ([@jolting](https://github.com/jolting)): the native Klipper
  firmware for the IFS board, proposed in GitHub pull request #16. Not yet
  merged; credited here for the work and its ideas
- Ingenic's Linux 6.6 SDK kernel for the X2000/X2600 (GPL-2.0)
- [Buildroot](https://buildroot.org/), BusyBox, [SWUpdate](https://sbabic.github.io/swupdate/),
  [LVGL](https://lvgl.io/) (MIT), Noto fonts (OFL-1.1)

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). Third-party components keep their
own licences: Klipper, Moonraker, Fluidd and HelixScreen are GPL-3.0, and the
Linux kernel is GPL-2.0. The images contain no Flashforge files. The parts
that only Flashforge can provide (drivers, board tools, the stock kernel)
come from your own printer at install time and are never in this
repository or its releases.

Source code: each release's own code is this repository at its tag. The
source of every third-party package in the images (with its patches) is in
the [sources](../../releases/tag/sources) release, including the 6.6 kernel
tree and the Klipper commit the board firmware is built from. Each release's
`kiln-os-<version>-licenses.tar.gz` lists every package with its licence,
version and source archive, and holds the licence texts.
