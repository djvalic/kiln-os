# Glossary

Words used in the Kiln OS code and docs, in alphabetical order. Each entry
points to the page or file with the detail.

**A/B slots** — The printer's eMMC has two kernel + root pairs: slot A
(`kernel` p1, `rootfs` p2) and slot B (`kernel2` p3, `rootfs2` p4). The
boot loader starts one of them, chosen by the boot flag. On Kiln OS the
main OS lives in slot B and the recovery OS in slot A. Both kernel
partitions keep the printer's stock 5.10 kernel. See
[boot-slots.md](boot-slots.md).

**ad5x-\*** — Prefix of Kiln OS's internal names: commands
(`ad5x-update`, `ad5x-mcu`), paths (`/data/ad5x`), init scripts
(`S05ad5x-data`), Klipper modules (`ad5x_*.py`). It predates the name
Kiln OS and stays, because installed printers find their files by it.

**Bambufy** — A set of slicer profiles and macros for the AD5X used with
zMod. Kiln OS prints its G-code through the `bambufy-compat` plugin. See
[zmod-compat.md](zmod-compat.md).

**Bed heat soak** — See *soak*.

**Boot flag** — The first 11 bytes of the `ota` partition (p5).
`ota:kernel2` makes the boot loader start slot B; anything else starts
slot A. Kiln OS writes it in `S01ad5x-tryboot`, `S99ad5x-booted`,
`ad5x-update`, `ad5x-boot-recovery` and the recovery OS.

**Boot trace** — The list of start-up steps with their times, kept in
`/run/ad5x-boot.log` and copied into the `ota` partition so it survives a
hang (`ad5x-bootlog`). See [boot-order.md](boot-order.md).

**Chainload** — Starting another kernel from a running one. The stock 5.10
kernel has no kexec, so `chainload.ko` (`kernel-ingenic66/chainload/`)
copies Kiln's kernel into RAM and jumps to it. `S00ad5x-kernel` does this
at every boot of the main OS. Because of it, `rcS` runs twice: once on the
stock kernel, once on Kiln's. See [boot-order.md](boot-order.md).

**Content ID** — A hash over the recovery image's files
(`/etc/ad5x-recovery-id`), without the build date. The main OS rewrites
slot A only when the recovery OS it carries has another content ID.

**Daily package** — A Klipper or Moonraker build published between Kiln
OS releases (a GitHub pre-release). It unpacks into `/data/ad5x/apps/` and
runs instead of the image's copy while it is newer. See
[updates.md](updates.md).

**Deviation** — Any behaviour that differs from the stock AD5X firmware.
Each one is listed, with its risk and how to go back, in
[deviations-from-stock.md](deviations-from-stock.md).

**Eboard** — The toolhead board ("extruder board"): a Nations N32G455
behind Flashforge's bootloader, on `/dev/ttyS5`. It runs mainline Klipper
firmware on Kiln OS (`[mcu eboard]` in `ad5x.cfg`). Its application must be
started over serial at boot (`ad5x-mcu boot`, `boot_eboard.py`).

**Factory config** — `/usr/share/ad5x/config/ad5x.cfg` (repo
`klipper/ad5x.cfg`): the hardware and stock behaviour, read-only, updated
with the image. Your own changes go in `local.cfg`. See
[config-layout.md](config-layout.md).

**FLASHED / FLASHED_IFS** — Files in `klipper/mcu-dicts/` naming the board
firmware version an image carries. `ad5x-mcu` flashes a board that runs
anything else.

**Fluidd** — The web interface on port 80, served by nginx, talking to
Moonraker. Its copy in `/data/ad5x/web/fluidd` can update itself.

**HelixScreen** — The touch screen interface (upstream project, with Kiln
patches in `buildroot/package/helixscreen/`). It talks to Moonraker. See
[helixscreen-integration.md](helixscreen-integration.md).

**IFS** — Flashforge's Intelligent Filament System: the AD5X's 4-slot
filament changer. Its controller (an N32G455) is on `/dev/ttyS4` over
RS-485. Kiln OS drives it with `klipper/extras/ifs.py`, on Flashforge's
firmware by default, or as a Klipper MCU with `ifs-klipper.enable`. See
[ifs-protocol.md](ifs-protocol.md).

**Kiln OS** — The product name. Use it in anything people read.

**klipper.enable** — The switch `/data/ad5x/klipper.enable`: Klipper
starts only when it exists. `ad5x-mcu` creates it once both boards run
Kiln's Klipper firmware. See [data-layout.md](data-layout.md).

**Lane** — One IFS slot as Moonraker's `lane_data` shows it to slicers
and screens (`moonraker/components/kiln_lanes.py`).

**Mainboard** — The motion controller board: a Nations N32G455 on
`/dev/ttyS2` (`[mcu]` in `ad5x.cfg`), running mainline Klipper firmware.

**Main OS** — Kiln OS proper, in slot B: Klipper, Moonraker, Fluidd,
HelixScreen. Built from `buildroot/configs/ad5x_defconfig`.

**Moonraker** — The API server (port 7125) between Klipper and Fluidd,
HelixScreen and slicers. Kiln adds the components `kiln_os` (updates,
kernel status, recovery) and `kiln_lanes`.

**nopoop** — zMod's purge modes for colour changes during a print, set
by the slicer's start G-code (`use_trash_on_print`): `0` the prime tower
takes the purge, `2` the slicer purges at the purge box itself, `1` or
unset the printer purges at the box as usual. Kiln OS's `nopoop` plugin
takes the same G-code. See `klipper/plugins/nopoop/README.md` and
[zmod-compat.md](zmod-compat.md).

**Plugin** — An optional bundle of Klipper config, Klipper extras and
Moonraker parts, switched with `ENABLE_PLUGIN` / `DISABLE_PLUGIN` or on
the touch screen. Shipped ones are in `/usr/share/ad5x/plugins`
(`klipper/plugins/`), others in `/data/ad5x/plugins`. See
[plugins.md](plugins.md) and [plugin-api.md](plugin-api.md).

**Prime line** — The line drawn in front of the objects before a print,
to get the nozzle flowing (`klipper/macros/prime_line.cfg`). See
[print-start.md](print-start.md).

**printer_data** — Klipper's and Moonraker's data directory:
`/data/ad5x/printer_data`, also reached as `/home/klipper/printer_data`.
Holds `config/`, `logs/`, `gcodes/` and `comms/`.

**Purge box** — The chute at the back of the bed where the nozzle purges
old filament after a colour change and before a print (zMod calls the move
there `_GOTO_TRASH`). Its position can be moved with `TRASH_OFFSET`. See
[print-start.md](print-start.md).

**Recovery OS** — A small separate system in slot A: SSH, an update page
on port 8080, a touch UI, backup and restore, USB rescue, and the way back
to stock. It installs main-OS updates. A main OS that fails to finish
starting lands here. Built from `ad5x_recovery_defconfig`. See
[recovery-os.md](recovery-os.md).

**Root scripts** — A plugin's `root/install.sh`, `update.sh` and
`uninstall.sh`, run as root when the plugin is enabled (only with
`ENABLE_PLUGIN ... ROOT=1`, the owner's yes), updated and disabled, as
zMod's plugins have them (plugin API 1.6). Klipper asks root through the
update agent (`S68ad5x-update-agent`), which keeps root's own copy in
`/data/ad5x/plugins-root/<name>`; boot scripts a plugin left there are run
by `S69ad5x-plugin-boot`. See [plugin-root-hooks.md](plugin-root-hooks.md).

**SPL** — U-Boot's small first-stage loader in the eMMC. On the AD5X it
loads the Linux kernel itself (U-Boot proper never runs), reads the boot
flag, and has no fallback.

**Soak** — The bed heat soak: after the bed reaches temperature, the plate
keeps moving for a while as it heats through. The print start waits for
it, for a time measured on your printer with the load cells
(`BED_SOAK_CALIBRATE`, `klipper/extras/ad5x_soak.py`). See
[print-start.md](print-start.md).

**Stock** — Flashforge's own firmware for the AD5X (software 3.1.0,
board firmware control 1.1.1), with or without zMod. Kiln OS saves it in
`/data/ad5x/stock` at install and can put it back (`ad5x-restore-stock`).

**Stock kernel** — Flashforge's Linux 5.10.186 in the kernel partitions.
Every boot starts on it. The main OS then chainloads Kiln's kernel; the
recovery OS stays on it; the main OS falls back to it when Kiln's kernel
failed to start.

**.swu / update zip** — The main-OS update file: an SWUpdate image (`.swu`)
or the same content as a `.zip` (`kiln-os-<version>-update.zip`). Rootfs
only, no kernel. Made by `tools/make_swu.sh`, installed by the recovery OS.

**Switch** — A file in `/data/ad5x` whose presence turns something on or
off (`*.enable`, `*.disable`, `kernel/mainline`, `recovery/noauto`). All
listed in [data-layout.md](data-layout.md).

**Try once** — The fallback Kiln OS adds on top of the boot loader: the
main OS's first script points the boot flag at the recovery OS, and its
last script points it back once start-up has finished and SSH runs. A
start that never finishes ends in recovery at the next power cycle.

**unit.cfg** — Per-printer calibration values (Z offset, cutter and purge
box positions), written once at the first boot from stock's
`Adventurer5M.json`. See [config-layout.md](config-layout.md).

**Update agent** — `S68ad5x-update-agent`, a root loop. Moonraker runs as
user `klipper` and can't install or reboot; it drops a request in
`/data/ad5x/kiln-update` and the agent carries it out (not while
printing).

**usershare / userdata** — Stock's two data partitions: `usershare` (p6,
stock's `/usr/prog`: settings, MAC address, Wi-Fi driver), read-only to
Kiln OS; `userdata` (p7, stock's `/usr/data`), mounted as `/data`.

**USB rescue** — Starting a system from a USB stick through the recovery
OS (`ad5x-rescue-boot` / `ad5x-rescue-flash` marker files on the stick).
See [recovery-os.md](recovery-os.md).

**Vendor files** — Flashforge's driver modules and board tools, needed
only when the stock kernel runs. Copied from your own printer into
`/data/ad5x/vendor`; never in an image or this repository
(`ad5x-vendor`).

**Vendor-free** — An image or release file that contains no Flashforge
files. Every public build is vendor-free (`tools/check_vendor_free.sh`).

**Weighing board** — The bed's load-cell board on `/dev/ttyS7`, used for
probing and the soak calibration (`klipper/extras/ad5x_weight.py`). See
[bed-weighing-board.md](bed-weighing-board.md).

**zMod** — ghzserg's mod for the stock AD5X firmware. Kiln OS replaces the
whole system instead, but prints G-code sliced for zMod
(`zmod-compat` plugin) and carries zMod's plugin choices over. See
[zmod-compat.md](zmod-compat.md).
