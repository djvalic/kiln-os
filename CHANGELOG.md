# Changelog

What changed for people using Kiln OS. Each release's notes (Gitea and
GitHub) take its section from here: `## vX.Y.Z`, or `## Unreleased` when
the release has no section of its own yet (rename it after the release).

When an entry fixes a reported issue, add its number as `(issue #N)` in the
entry, so the GitHub release links to the issue. A release does not close
the issue: it is closed by hand after the release.

## Unreleased

### Fixed
- **ad5x-update explains a printer that runs the main OS from slot A, and points to the recovery steps** (issue #26): updates refused such a printer with messages that did not say why. The refusals now say the printer runs the main OS from slot A, that updates don't support that layout, and where `docs/recovery-os.md` ("Main OS in slot A") gives the read-only triage and the safe path.
- **Print start no longer reads the whole job file on the main thread** (issue #22): the IFS filament scan read every line of the job, which took about 3 s on a large file and could stall the MCU into "Timer too close". It now reads only the start and the end of the file, where the slicers write the filament lines.
- **IFS slot changes from the console or a plugin show on the screen** (issue #13): the lane records Kiln writes for OrcaSlicer no longer carry the `vendor` key, which HelixScreen treated as its own, so a slot change (for example from `IFS_SET_MATERIAL`) was ignored on the screen. Each changed slot now gets the time of the change. Needs a printer check with HelixScreen.
- **A lane loaded under zMod is recorded at startup** (issue #13): when the IFS has a lane selected with a spool in it and the toolhead sensor sees filament, Kiln takes that lane as loaded. A load error that finds filament at the toolhead now names the fix (`IFS_UNLOAD SLOT=n`, or `IFS_SET_CHANNEL CHANNEL=n`).
- **A failed unload releases the lane on any error** (issue #13): not only IFS errors. If the release fails too, the error says `IFS_RELEASE CHANNEL=n` frees the lane.
- **Tool map reset after a paused print is cancelled** (issue #13): the map resets when a paused print ends, and `CANCEL_PRINT` resets it at once.
- **Idle timeout leaves heaters on during a print or pause**: the stock idle timer turned the heaters off and disabled the steppers after 30 minutes with no movement, even while a print was paused. It now does so only when no print is printing or paused, no IFS swap is running, and no heater target changed in the last minute; the console says when it turns them off or leaves them on.
- **Chamber light off at idle sleep with LED auto state on**: with "Chamber light off when the screen sleeps" on, the light now turns off when the screen sleeps while the printer is idle, even with LED auto state on. It still stays on while a print is preparing, running or paused, and on wake the light comes back with LED auto state's own colour.
### Changed
- **HelixScreen pinned to v1.1.0-beta.14** (was beta.13): the patch stack 0001-0035 applies to the beta.14 tag. New upstream features come with it: FILAMENTS chips on the print-file screen, OrcaSlicer exact filament preset ids, a move-clearance lift after a print, a CPU budget for the 3D preview, and the mixed-temperature material warning. The door-open warning stays off, because the AD5X has no door sensor. The stop-during-preparing and IFS unload paths need a supervised printer test.
- **Language picker** offers English, Chinese, Japanese, German, Spanish, Italian, Russian, Portuguese and Turkish (the stock 3.1.3 set without Korean, which waits for the Hangul font). French is removed from the picker; its translation stays in the source.
- **Home screen Toolhead tile** replaces the Motion tile on the AD5X layout (layout revision kiln-2, so existing layouts pick it up). It shows the toolhead position and plate, and a tap opens the Motion panel for homing and jog.
- **Install screen says what to do at the end** (issue #21): "Done, restarting" tells the user to remove the USB stick, and to power-cycle the printer if nothing happens after 3 minutes. Needs a new install stick to show.
- **Side-scroll buttons on by default on the AD5X** (issue #21): HelixScreen's page-scroll buttons are on for new installs and for units that have no saved choice yet. A choice made in the settings is kept.
- **Russian screen names**: "Z Offset" reads "Z-смещение" on the Russian screen, and the "Wifi" item reads "WiFi" as in the rest of the Russian text. Patch 0030 (translation YAML).
- **IFS wording kept in the translation source**: the non-English screens' IFS wording (patch 0028) now also lives in the translation YAML (patch 0030), so a rebuild keeps it. No change on the screen.

### Added
- **Korean and Turkish translations** of HelixScreen (patch 0032, 4455 keys each). Turkish is in the picker with its flag; Korean is not offered until the Hangul font is added. Native-speaker review is pending for the safety and warning text.
- **Recovery screens in the setup wizard's language**: the recovery UI reads the `language` key of the main OS's settings.json (same codes as the picker: en, zh, ja, de, es, it, ru, pt, ko, tr) and shows its strings from one table (`recovery-ui/i18n/`). Missing or unknown values give English. The translations themselves are still English placeholders, filled in later; Chinese, Japanese and Korean need a CJK font first.
- **Chamber light off when the screen sleeps** (Settings > Display, off by default): with the option on, the chamber light turns off when the screen goes to sleep, but not while a print is preparing, running or paused. It comes back on when the screen wakes or a print starts, with LED auto state's own colour if it is on.
- **Set the heater idle timeout**: `HEATER_IDLE_TIMEOUT MINUTES=n` sets how long the printer may sit with no print and no heater change before the nozzle and bed heaters go off (the stock idle timer, now settable). The value is saved and comes back after a restart. Default 30 minutes, the same as before; at least 5. Without MINUTES it shows the current value.
- **Developer root actions, Klipper side** (off by default; needs the owner's grant): a plugin lists the named root actions it needs in `plugin.json` (`root_actions`). `DEV_ROOT_REQUEST PLUGIN=<name> ACTION=<action> [ARGS="a b"]` asks root to run one, and `DEV_ROOT_STATUS` shows the declared actions, which are granted, and pending requests. Installing or enabling a plugin lists its root actions in the console; nothing is granted until the owner turns them on at the printer (`ad5x-dev-root enable`). Needs the root side and a printer check.
- **PAUSE and RESUME macros** (issue #13): `ad5x.cfg` has pass-through `PAUSE` and `RESUME` macros over `pause_resume`, so Mainsail stops warning "gcode_macro PAUSE/RESUME not defined". The print pauses and resumes as before, with no parking.
- **Extra nginx servers** (issue #13): nginx includes `/data/ad5x/nginx/*.conf` in its `http` block, for a second web UI or port (e.g. Mainsail on 81). Nothing is there by default. A file that does not parse stops nginx and the web UI.

## v0.0.33

### Fixed
- **zMod start keeps an unexpanded tool out of tool 0** (issue #12): `START_PRINT TOOL=[initial_tool]` used to load tool 0 through the zMod-compat plugin. Now no tool is loaded and the console shows an error, as for PRINT_START.
- **Public export keeps symlinks to printer paths** (issue #15): `tools/export_public.sh` dropped a link when its target exists only on the printer (`/data/...`). The link is now kept as a link.
- **Installer accepts a smaller user-data partition** (issue #14): stock 3.1.6 printers have a user-data partition of 11935744 sectors instead of 12238848. The installer now logs the difference and continues; the other partitions still have to match exactly. Needs a printer check on a 3.1.6 printer.

### Added
- **IFS backup from the printer itself**: at boot and with `ad5x-mcu tools`, the IFS flashing tools and Flashforge's IFS firmware (`IFSCommand`, `ifsF37`, `ifs.hex`) are copied from stock's copy on the usershare partition into `/data/ad5x/vendor/mcu`, so a return to stock needs no outside files. Best effort: a missing copy doesn't stop boot.
- **IFS Klipper firmware built** (`tools/build_mcu.sh`, `klipper/mcu-configs/ad5x-ifs.mainline.config`): `ifs.hex` is built from the eboard config with serial 115200 and PA11 driven high, and shipped in the image at `/usr/share/ad5x/mcu`. Not flashed by default.

## v0.0.32

### Added
- **IFS Klipper mode (code only, not active in this release)**: `ifs.py` can drive the filament unit's feeder and selector through Klipper (`mode: auto` in `ifs.cfg`, `klipper/generic-flashforge-ifs.cfg`) instead of the serial link. It needs the IFS board running Klipper firmware, which this release does not include, and it is only tried if `/data/ad5x/ifs-klipper.enable` exists. No file is created by default, so the IFS keeps its Flashforge firmware and serial link as before. Code from GitHub pull request #16 by Hunter Laux (`docs/deviations-from-stock.md`).
- **Half-duplex serial keep-alive** (GitHub pull request #16 by Hunter Laux, for the IFS on Klipper firmware): the keep-alive waits 20 ms after every command, not only after the last poll, so it cannot land on a command on the shared RS-485 line (`buildroot/package/klipper/0001-serialhdl-add-half-duplex-RS-485-TDD-support.patch`). Only used in the IFS Klipper mode, so not in this release.

### Fixed
- **Homing leaves the bed 5 mm off the Z stop**: after `G28 Z` the nozzle is lowered to Z 215, so the swap's +5 mm lift no longer runs the bed into the top of Z travel. Z zero and the mesh are unchanged.
- **IFS flash stops when the bootloader erase fails** (`ad5x-mcu flash-ifs`, boot path): ifsF37's exit status is checked before IFSCommand writes anything; a failure is logged to `/data/ad5x/mcu/ifsF37.log` and the flash stops. Before, the write went ahead regardless. Only in the IFS Klipper mode, so not in this release.
- **IFS as a Klipper MCU: IFS_STOP cuts a push** (IFS Klipper mode, not in this release; `klipper/extras/ifs.py`): the push moves the feeder and extruder in short steps, so a stop switches the feeder off within one step. Before, the whole push ran on after IFS_STOP.
- **IFS as a Klipper MCU: a load with no toolhead sensor stops at the length limit** (IFS Klipper mode, not in this release): the feeder has no stall detection, so without `head_sensor` a load used to run its full length and report success. It now fails with an error at `load_length`, and a warning at start says so.
- **IFS as a Klipper MCU: a selector that does not find its endstop fails the load** (IFS Klipper mode, not in this release): the homing error names the endstop, and the selector motor is switched off. Before, the G-code error escaped without a reset.
- **IFS as a Klipper MCU: a stop during the wait for queued moves is kept** (IFS Klipper mode, not in this release; not yet covered by a test): IFS_STOP pressed while an earlier move still runs is no longer cleared before the next command starts. **IFS errors name a failed reset**, in both modes: after an error the reset runs (F15 on the serial link, the motors off in MCU mode); if it fails, the error says so instead of hiding it.

## v0.0.31

### Fixed
- **Kernel (test boot first): eMMC clock cap 50 MHz** (`kernel-ingenic66/ad5x.dts`): stock caps the eMMC at 25 MHz; HS200 was negotiated and reads ran at about 21 MiB/s. Needs a test boot: 10 cold boots, no mmc errors, a read/write loop.
- **Kernel (test boot first): CMA reserve 32 MB to 16 MB** (`kernel-ingenic66/ad5x.config`): about 8 MB is in use. Needs a test boot: display and camera come up on a cold boot.
- **Kernel (test boot first): DMA probe no longer logs "IRQ pdmam not found"** (`kernel-ingenic66/patches/0008`): the X2600 PDMA node has no pdmam interrupt; the lookup is now optional.
- **Kernel (test boot first): `ifconfig eth0 hw ether` no longer warns "Incorrect netdev->dev_addr"** (`kernel-ingenic66/patches/0009`): the address setter updates both copies.
- **Webcam name**: the first camera is named "Chamber/Bed" in Fluidd, HelixScreen and Moonraker (was "camera1"). Later cameras keep "Camera n". Set in `init.d/S64ad5x-camera`; takes effect on the next boot.
- **Webcam: the dead USB device is no longer the main camera**: a UVC device with ID 0bda:d565 ("Snapshot Camera", on the board's OTG port) answered no probe, so the main webcam tile was dead while the bed camera on the hub worked. The camera script now skips that ID (`CAMERA_IGNORE` in `init.d/S64ad5x-camera`), so the bed camera is camera 1. Needs a printer test boot: `/webcam/?action=snapshot` returns a JPEG of the bed.
- **Motor currents set to the community values** (`klipper/ad5x.cfg`): X and Y run 1.1 to 0.9 A RMS, Z 0.9 to 0.6 A RMS (hold the same). The values come from the AD5M shipping settings, which the community reports working. Needs a printer check: a long print for step loss on X, Y and Z (Z under bed load), and a homing repeat test.
- **Homing: Y back-off no longer zeroes Z** (`klipper/ad5x.cfg`, `_HOME_ZXY`): `G28 Y` with Y already on its endstop set Z to 0 without homing Z. Z now keeps its current height. Needs a printer check: `G28 Y` with the carriage on the Y endstop, then `GET_POSITION`.
- **Docs: MCU version, RAM and homing notes** now match the printer (MCU v0.13.0-803, N32G455 128 KB RAM patch, the back-off difference from stock).
- **Runout sensor during swaps**: the toolhead sensor is now switched off during an IFS swap and put back to its previous state after it (`klipper/ifs.cfg`). The sensor was forced back on after a swap, even if it had been off before. It is now put back to the state it had. Needs a printer check: a multi-colour print with the sensor on.
- **Print start purge**: a colour already in the nozzle gets the prime line instead of a second 90 mm purge. A colour that has to be loaded skips the box purge, because the IFS swap purges (`macros/print_start.cfg`). Needs a printer check: the first layer after the first colour.
- **Print start retraction**: the 3 mm retraction the start leaves is put back on every path (prime line, IFS purge, prime line off, no room on the plate), so the first extrusion is not short (`macros/print_start.cfg`, `macros/prime_line.cfg`).
- **Print start checks**: a BED or EXTRUDER that is not a number (an unexpanded placeholder) stops the start with an error, instead of heating to 0. The factory fallback PRINT_START checks TOOL the same way (`ad5x.cfg`).
- **Print without a saved centre Z**: the start stops with an error and runs `BED_MESH_CALIBRATE` first. Before, the print ran with no mesh loaded (`klipper/ad5x.cfg`, `_CHECK_Z_APPLY`).
- **Quick actions and IFS_PURGE_TEST keep the extrusion mode**: LOAD_FILAMENT, UNLOAD_FILAMENT (without an IFS) and IFS_PURGE_TEST put back the M82/M83 mode they found (`macros/quick_actions.cfg`, `klipper/ifs.cfg`).
- **IFS_PURGE_RESULT** without `DOT=` gives a clear error (`klipper/ifs.cfg`).
- **UNLOAD_FILAMENT with a lane Kiln has no record of** (issue #13): when `ifs_loaded` is 0 but the IFS reports the selected lane as holding filament, UNLOAD_FILAMENT runs `IFS_UNLOAD` on that lane instead of a plain 50 mm retract. The plain retract is only used when no lane is loaded (`macros/quick_actions.cfg`). Needs a printer check: a lane loaded under zMod, then UNLOAD_FILAMENT.
- **A failed IFS unload releases the lane** (issue #13): when an unload fails, the lane is released after the error, so the spool can be pulled by hand. Not after `IFS_STOP` (`klipper/extras/ifs.py`, `_unload_toolhead`). Needs a printer check: an unload that fails with the toolhead sensor still reading filament.

- **Board fan during long macros** (issue #17): the board fan (`pcb_fan`, cools the TMC2209 drivers) is kept on by a reactor timer, `[pcb_fan_watch]` (`klipper/extras/pcb_fan_watch.py`), instead of a delayed_gcode that waited behind a long macro such as bed leveling. Same rule: on while a motor or heater is on or a print runs, off 30 s after. Needs a printer check: a bed level with the fan on, and the fan off 30 s after the level.
- **Wi-Fi (USB rtw88) crash at boot fixed** (`kernel-ingenic66/patches/0010`): receive started before mac80211 had a channel, and the receive status read a NULL channel. Receive now starts after the hardware is registered, as upstream does. Needs a kernel test boot before release: no oops in `dmesg`, Wi-Fi associates.
- **Wi-Fi regulatory database built into the kernel** (`kernel-ingenic66/ad5x.config`, `build.sh`, `ad5x-kernel66.mk`): cfg80211 asks for `regulatory.db` before the root filesystem is mounted, so the file on `/lib/firmware` was never found. It is now built in with its signature, from the wireless-regdb package. Needs a printer check after the next kernel build: no "failed to load regulatory.db" in `dmesg`, and `iw reg get` shows a country.

### Changed
- **IFS swaps refuse an empty slot** before anything is cut: a tool change to a slot with no filament stops with an error (`klipper/extras/ifs.py`, same check as `IFS_MAP_TOOL`).
- **Shared-slot warning**: at print start, a message when two tools map to one slot but the file names different filament for them. A message only; nothing else changes.
- **CLEAR_NOZZLE** description now says it moves to the purge box and brushes, with no purge and no heating.

## v0.0.29

- **IFS wording on the screen**: the touch screen says IFS everywhere: the "IFS is busy" and "No IFS Detected" messages, the wizard and print-start text, and the telemetry labels. Patch 0028. Code names are unchanged.

## v0.0.28

- **Spoolman grams on the slot tile**: a slot linked to a Spoolman spool shows its remaining grams under the material (for example 750g), where it used to show nothing. Slots without a Spoolman link are unchanged (HelixScreen patch 0027, `ams_state.cpp`).
- **New logo and brand guide** (`docs/brand/`): a frost-blue ring with four gaps, one per IFS slot, and a solid K. One colour; the slot is read by position. App icon and lockup included.
- **IFS channel count in one place** (`klipper/extras/ifs.py`): the four channels come from one constant, and the reply parser and the status lists follow it. No change on the printer: still four channels. This is groundwork for other IFS hardware; it does not add support for any.

## v0.0.27

### Added
- **Spoolman spool per IFS slot on the screen** (with the `kiln-spoolman` plugin only): the spool a slot was given with `SPOOLMAN_SET_SLOT` is linked to that slot in HelixScreen, and its name and remaining grams show in the IFS slot view. Without the plugin, or without Spoolman, nothing changes (HelixScreen patch 0026, `ams_backend_ad5x_ifs.cpp`). A spool picked on the screen stays until the plugin's value changes; clearing a slot in the plugin does not unlink it on the screen.

### Changed
- **HelixScreen v1.1.0-beta.13**: the screen moves from beta.11 to beta.13. Patches 0011 (home layout), 0013 (keyboard underscore) and 0016 (network menu) are rebased onto it.
- **First tool load of a print primes only when the slicer purges on the bed**: with `use_trash_on_print` 0 or 2, the first colour no longer purges at the purge box; the bed prime tower purges it. Trash mode still purges at the box (`klipper/extras/ifs.py`, `tools/test_ifs.py`). Needs a printer check: the first layer after the first colour, and that the prime fills the nozzle.

### Fixed
- **Print start loads the tool you chose** (issue #12): a `TOOL=` value that is not a number, such as an unexpanded `[initial_tool]`, used to load tool 0 (spool 1). Now no tool is loaded and the console shows an error. Use the number from your slicer's start G-code (`macros/print_start.cfg`).

## v0.0.24

### Fixed
- **Ethernet shows disconnected when unplugged** (issue #8): the Network Settings row
  kept saying "Connected" with the old address after the cable was pulled. It now
  shows "No cable" (HelixScreen patch 0024).
- **Network Settings updates while open**: the Ethernet row re-reads every 3 s
  while Network Settings is open, so plugging or unplugging the cable shows
  straight away (HelixScreen patch 0025). Nothing runs when the screen is closed.

### Changed
- **No LED strip prompts**: the setup wizard's LED step and the Hardware Health
  "LED strip available" item are no longer shown. The chamber LED is declared
  for every printer, so they asked everyone. The LED controls stay, and a strip
  is set up in Settings > LED Settings (HelixScreen patch 0023).
- **Camera settings file is read as data, not run**: `/data/ad5x/camera.conf`
  used to run as shell code as root at boot. It is now read as settings only:
  `CAMERA`, `RESOLUTION`, `FPS` and their numbered forms (`RESOLUTION_2`,
  `FPS_2`), each value checked. Other lines are skipped with a log line, and a
  file that is not owned by root, or that others can write, is not read. Write
  `FPS=15`: spaces around `=` are no longer accepted.

## v0.0.23

### Added
- **IFS tool map mode `loaded`**: `IFS_MAP_MODE MODE=loaded` maps each tool to
  the loaded slot that matches the file's filament: the same material with the
  nearest colour (from the file's `; filament_type` and `; filament_colour`
  lines, so files made before this change work too). Without those lines, tools
  use the loaded slots in slot order; with one slot loaded, every tool uses it.
  `MODE=fixed` (the default) keeps T0-T3 -> slots 1-4. The mode is saved across
  restarts and applied at each print start. An `IFS_MAP_TOOL` line in the file
  still wins.
- **Settings > Filament Auto-Refill > Tool to slot**: choose **Slot per file**
  (the file's own slot for each tool) or **Auto colour** (the `loaded` mode
  above, on the touch screen).

### Changed
- **Filament and cutter readings hidden from temperature charts**: the AD5X
  toolhead `filamentValue` and `cutValue` readings are raw sensor values, not
  temperatures. HelixScreen now starts them disabled, so they no longer show in
  the temperature widgets and graphs (HelixScreen patch 0022). They are still
  there for the printer's own use. There is no switch for them on the touch
  screen yet.

## v0.0.22

### Changed
- **IFS reconnects by itself**: when the IFS is not answering (at start, or
  after a loose cable), the printer tries again every 10 seconds, so a replug
  needs no restart. If it does not come back in line, see
  `docs/ifs-troubleshooting.md`.

### Fixed
- **IFS abort puts the printer back**: a swap that fails or is stopped restores
  the toolhead sensor, the part fan and the G-code state (`abort_gcode`). The Z
  lift stays, so a move never happens mid-print.
- **Home screen tiles stay put under a finger**:
  a tile held for about 0.4 s and then dragged no longer moves. A quick swipe
  from a tile still pages.

## v0.0.21

### Changed
- **Reboot host**: Moonraker's reboot works; `klipper` may run `/sbin/reboot` with no arguments.

### Fixed
- **Setup wizard**: Abort also stops a bed soak's wait; the soak's heat wait gives up after 15 min; a PID test that left a heater off refuses to start until Klipper restarts; an aborted Z offset step restores zero when no offset was saved; the summary step counts its steps correctly.
- **Buttons stay put under a finger**: a press that moved a little used to
  scroll the panel behind the button. Plain buttons no longer pass the drag
  on; list rows still scroll when dragged.
- **Reboot host works from Fluidd and HelixScreen**: Moonraker runs
  `sudo reboot`, and the image had no `sudo`. It now has `sudo`, with a rule
  letting only `klipper` run `/sbin/reboot`.
- **Fan step no longer comes back at every start**: the AD5X preset named an
  aux fan the printer doesn't have (`chamber_fan`), and the empty aux role was
  filled from it at each boot. The preset now leaves aux empty.
- **Dead cameras are not Fluidd tiles**: the camera list is no longer fixed in
  `moonraker.conf`. At boot each USB camera is registered once its stream
  answers, and disabled when it doesn't (the "Snapshot Camera" on the OTG port
  shows as disabled).

## v0.0.20

### Added
- **OrcaSlicer filament profiles** (`orca/`): `AD5X PLA`, `AD5X PETG` and
  `AD5X TPU`, starting points with temperatures and volumetric speed limits
  (see `orca/README.md`). Not yet tried in the Orca GUI.

### Changed
- **HelixScreen beta.11**, patches rebased onto it (0010, 0011 kept as before).
- **Moonraker** pin moved to `b559b9a`; **Klipper** pin moved to `v0.13.0-816`.
- **Orca printer profiles**: every machine G-code field is set.
- **Setup wizard: Z offset test** checks only the centre, not the whole bed
  (no full-bed mesh); the buttons say **Closer** and **Away** instead of
  `-` and `+`.
- **Setup wizard: purge box** is one row of arrows (Left, Right, Front, Back,
  Factory), so Accept and Abort fit on the page without scrolling. The 0.1 mm
  steps are gone; use 1 mm and Z offset as needed.
- **Setup wizard: bed soak** cools a warm bed first (heater off, up to 15 min
  of waiting, shown on the screen) instead of stopping with "the bed is still
  warm".
- **Setup wizard: IFS tuning** unloads filament left in the toolhead first, when
  the slot is known. If it isn't, the screen says to pull it out by hand, then Retry.

### Fixed
- **Network settings: Test Network stays on screen** when Wi-Fi and Ethernet
  are both connected. The status cards scroll above the button.
- **Wi-Fi IP shows right away** (issue #7): when wpa_supplicant's status has no
  IP address, the screen reads the address from the kernel, so a connected
  network no longer shows an empty IP.
- **No junk network names**: a hidden network whose name is all zero bytes is
  left out of the list (it showed as `\x00\x00…`).
- **Wi-Fi reachable after unplugging Ethernet** (issue #8): routes through a
  port with no cable are ignored, so the Wi-Fi replies no longer go out the
  dead Ethernet port. The printer needed a reboot before.
- **Wi-Fi band label** (issue #6): the "2.4GHz only" note follows the scan. A
  5 GHz network in the list means the radio can see 5 GHz.

## v0.0.18 (2026-10-22)
### Fixed
- **Home screen: a finger drifting to the edge no longer pages the screen**
  when the arrows page it (resistive touch): the Unload button in the corner
  is pressed reliably. Swiping still works in widget edit mode.
- **Keyboard: the second period on the number page is now an underscore**
  (`_`), for Wi-Fi passwords and commands. The period stays on the row above.
- **The purge box offset applies everywhere**: the box moves at the start
  of a print, the wipe and the nozzle brush used the fixed spot and ignored
  unit.cfg's offset; now every box move uses it (and TRASH_OFFSET's value).
- **Nozzle 10 °C hotter than the file** (245 instead of 235): a file whose
  start line is zMod's `START_PRINT` without `EXTRUDER_TEMP=` (Orca
  profiles that send their own `M104` first) got zMod's default of 245
  for the whole print. `START_PRINT` and `PRINT_START` now keep the
  temperatures the file already set and use the defaults only when it set
  none. Files that give `EXTRUDER_TEMP=` work as before.

### Added
- **Touch screen: purge box check, bed soak and summary steps** in the
  setup wizard, plus the Z offset's load cell estimate (off until
  `zoffset_estimate: 1`), Wi-Fi's Add Hidden Network in the wizard, and
  Settings > Purge Box to move the trash bin.
- **`TRASH_OFFSET X= Y= [RESET=1]`**: moves the purge box (the trash bin)
  from its factory spot (X 52.5, Y 229) and saves it, so it survives
  restarts and updates. X -10 to 10, Y -14 to 2 mm. `RESET=1` goes back to
  the value in unit.cfg. A menu entry and a wizard step can follow.
- **OrcaSlicer printer profiles for every nozzle size** (`orca/`):
  import one per nozzle (0.2 to 1.0 mm) in Orca with File > Import; each
  has the machine G-code and build area. Retraction is from the 0.6 mm
  profile, to be checked on the others (see `orca/README.md`).
- **Recommended OrcaSlicer machine G-code** (`docs/orcaslicer.md`): start,
  end, layer change and colour change G-code to paste into OrcaSlicer's
  printer settings, where the printer does the heating, mesh, first load
  and the purge at the box.

## v0.0.17 (2026-10-22)
### Fixed
- **Home screen: a finger drifting to the edge no longer pages the screen**
  when the arrows page it (resistive touch): the Unload button in the corner
  is pressed reliably. Swiping still works in widget edit mode.
- **Keyboard: the second period on the number page is now an underscore**
  (`_`), for Wi-Fi passwords and commands. The period stays on the row above.
- **The purge box offset applies everywhere**: the box moves at the start
  of a print, the wipe and the nozzle brush used the fixed spot and ignored
  unit.cfg's offset; now every box move uses it (and TRASH_OFFSET's value).
- **Nozzle 10 °C hotter than the file** (245 instead of 235): a file whose
  start line is zMod's `START_PRINT` without `EXTRUDER_TEMP=` (Orca
  profiles that send their own `M104` first) got zMod's default of 245
  for the whole print. `START_PRINT` and `PRINT_START` now keep the
  temperatures the file already set and use the defaults only when it set
  none. Files that give `EXTRUDER_TEMP=` work as before.

### Added
- **Touch screen: purge box check, bed soak and summary steps** in the
  setup wizard, plus the Z offset's load cell estimate (off until
  `zoffset_estimate: 1`), Wi-Fi's Add Hidden Network in the wizard, and
  Settings > Purge Box to move the trash bin.
- **`TRASH_OFFSET X= Y= [RESET=1]`**: moves the purge box (the trash bin)
  from its factory spot (X 52.5, Y 229) and saves it, so it survives
  restarts and updates. X -10 to 10, Y -14 to 2 mm. `RESET=1` goes back to
  the value in unit.cfg. A menu entry and a wizard step can follow.
- **OrcaSlicer printer profiles for every nozzle size** (`orca/`):
  import one per nozzle (0.2 to 1.0 mm) in Orca with File > Import; each
  has the machine G-code and build area. Retraction is from the 0.6 mm
  profile, to be checked on the others (see `orca/README.md`).
- **Recommended OrcaSlicer machine G-code** (`docs/orcaslicer.md`): start,
  end, layer change and colour change G-code to paste into OrcaSlicer's
  printer settings, where the printer does the heating, mesh, first load
  and the purge at the box.

## v0.0.16 (2026-10-21)
### Fixed
- **Nozzle 10 °C hotter than the file** (245 instead of 235): a file whose
  start line is zMod's `START_PRINT` without `EXTRUDER_TEMP=` (Orca
  profiles that send their own `M104` first) got zMod's default of 245
  for the whole print. `START_PRINT` and `PRINT_START` now keep the
  temperatures the file already set and use the defaults only when it set
  none. Files that give `EXTRUDER_TEMP=` work as before.

### Added
- **Recommended OrcaSlicer machine G-code** (`docs/orcaslicer.md`): start,
  end, layer change and colour change G-code to paste into OrcaSlicer's
  printer settings, where the printer does the heating, mesh, first load
  and the purge at the box.

## v0.0.15 (2026-10-21)

### Fixed
- **"WiFi system not ready" on the touch screen**: Wi-Fi now waits longer
  for a slow USB Wi-Fi adapter (10 s instead of 3), and a saved Wi-Fi
  file it can't read (for example one brought over from stock) is put
  aside so Wi-Fi still starts and a network can be joined again. Either
  used to leave the screen's Wi-Fi without its service.
- **A fresh install's first Z offset could overwrite the wizard's.** At
  start-up the offset carried over from stock is copied once; if a
  command was already running then (the setup wizard's Z offset step),
  the copy waited and wrote the old value over the new one afterwards.
  Found by the new emulated wizard test.
- **Setup wizard bed mesh: "Probe samples exceed samples_tolerance"**.
  The mesh step now cleans the nozzle first, as a print does (one touch
  at the bed's front edge, then a scrub along it). Plastic left on the tip
  squashed a little more at every touch, so the probe's three samples
  disagreed.

### Added
- **`logs/wifi.log`** (in Fluidd's log files): what Wi-Fi did at start:
  kernel, adapter driver, number of saved networks (no names or
  passwords), and the exact error if it didn't start. Send it along with
  `helixscreen.log` when Wi-Fi misbehaves.
- **Emulated setup wizard test on a fresh install** in every build: the
  image's own Klipper runs the wizard's steps on a newly installed data
  partition (with a Z offset carried over from stock), and the saved
  results are checked.

## v0.0.14 (2026-10-21)

### Fixed
- **`SAVE_CONFIG` after `PROBE_CALIBRATE`, `Z_OFFSET_APPLY_PROBE` or
  `PID_CALIBRATE`** no longer fails with "conflicts with included value".
  A probe Z offset becomes the printer's saved Z offset (the same first
  layer; the one the touch screen shows and every print uses), and PID or
  input shaper results go to `ad5x-tuning.cfg`, like the setup wizard's.
- **Setup wizard Z offset no longer scrapes the bed**: the test patch now
  starts fresh every time at 0.1 mm, a little high, instead of at the
  offset already saved (which after an install from stock or zMod was
  never tested on Kiln OS). Lower it with - until the lines touch and
  flatten, then Accept.
- **Hidden Wi-Fi networks** saved on the Flashforge screen are found
  now: every saved network is searched for by name (stock saves only the
  name and password). New hidden networks: Settings > Connection > Network
  Settings > Add Hidden Network (the setup wizard lists visible networks
  only).

## v0.0.13 (2026-10-21)

### Fixed
- **Wi-Fi works without Ethernet**: Wi-Fi now always starts, so the
  touch screen can find and join networks and remembers them: in the
  setup wizard, or any time in Settings > Connection > Network Settings.
  Before, a printer installed without Ethernet had no way to get online.
  The networks saved on the Flashforge screen come over on the first
  start.

### Added
- **Wi-Fi switch**: if you only use Ethernet, turn Wi-Fi off in Settings >
  Connection > Network Settings; it stays off after a restart (it comes
  back on by itself only when no Ethernet is connected, so the printer
  can't be cut off).

## v0.0.12 (2026-10-21)

### Changed
- **New home screen on the touch screen**: nozzle and bed temperature,
  fans and notifications along the top, a big print status card (progress,
  file, layer, time left; the last print when idle), and on the right the
  IFS slots, Preheat/Cool Down, the light switch, the live Z offset (tap
  it for baby steps), Motion and Unload (Preheat/Cool Down and Unload are
  greyed out while a print is running or paused). The printer
  picture, temperature graph (tap a temperature to open it) and tips are
  gone. A home screen you never rearranged switches to it with the update;
  one you edited stays as it is.

## v0.0.11 (2026-10-20)

### Added
- **Auto-refill settings**: `IFS_AUTO_REFILL MATCH=exact|similar|any` picks
  how close a backup spool's colour must be (default similar). The printer
  shows which slots back each other up, and a print that loads a slot with
  no backup gets a notice instead of a surprise pause later. A spool put
  in during a print is fed in when a refill needs it.
- **Nozzle size** in the setup wizard (after the time zone) and in
  Settings on the touch screen, or `SET_NOZZLE_SIZE SIZE=0.6`: kept in the
  printer's `nozzle.cfg`. The defaults stay for the 0.4 mm nozzle; line
  widths, purge lengths and the first-layer test follow the setting.
- `BED_SOAK_ENABLE ENABLE=0|1`: the bed heat soak on or off for every
  print (saved; calibrations are kept).
- **Bed heat soak on the touch screen** (Settings > Bed Heat Soak): on/off,
  the calibrated times, and Calibrate with progress and Stop.
- After a nozzle change in Settings, the screen offers just the hotend PID
  tune and the first-layer Z offset test, not the whole setup
  (`SETUP_WIZARD_STEP STEP=pid HEATERS=extruder`).

### Fixed
- The speaker played nothing: the PWM driver refuses to switch off a
  channel that was never set up, which the player did before every note.

### Changed
- **Our 6.6 kernel always.** No more choice of kernel (`ad5x-kernel own`
  / `stock` are gone): Kiln OS runs our kernel on every printer, new
  installs included. The stock kernel stays in its boot slot only as the
  fallback when a start of ours fails, until an update brings another
  release of ours (`ad5x-kernel retry` tries again).

- Bed soak calibration holds the nozzle at its temperature for 5 minutes
  before heating the bed (`NOZZLE_SOAK=`), so the hotend still growing
  isn't counted as bed movement.
- Bed soak calibration copes with the load cells' scatter (about 0.03 mm):
  readings are averaged over 3 rounds and "settled" means within 0.02 mm,
  so it ends on its own instead of running 25 minutes; the saved time is
  the centre's (where the Z check probes), with the slowest corner's
  alongside.
- zMod's `START_PRINT` (zMod-sliced files) passes `SOAK=` on to
  `PRINT_START`; the soak applied to those files already.
- A cooler bed than the calibrated one never soaks longer than measured
  (a 55 °C PLA print after the 60 °C calibration: 420 s, not 565 s).
- A bed temperature without its own calibration uses the nearest one,
  scaled by how far the bed heats (an 80 C PETG print after a 60 C
  calibration soaks longer, not shorter); at most 10 minutes.

## v0.0.7

### Added
- **The speaker works:** short chimes when a print starts, finishes,
  fails or pauses and when the IFS auto-refills; `M300` beeps and zMod's
  `PLAY_MIDI FILE=` plays your own MIDI files (config folder `midi/`).
  On/off, volume and the sound per event on the touch screen (Settings >
  Sound > Printer sounds) or with `SOUND_SETUP`. HelixScreen's own sounds
  play on it too.
- **Time zone** as the first step of the setup wizard (also in "Run Setup
  Wizard"), for the screen's clock.
- **Plugins on the touch screen:** Settings > Plugins switches plugins on
  and off and installs, updates and removes the ones from the catalog
  (Notifications, Timelapse, Spoolman). No SSH, no reboot: Moonraker
  restarts by itself when needed. Console: `INSTALL_PLUGIN NAME=`,
  `UPDATE_PLUGIN`, `REMOVE_PLUGIN` (plugin API 1.4).

### Changed
- **Bed heat soak** before the Z check: the bed waits a little after
  reaching its temperature when it started cold, so the plate has stopped
  growing when Z is measured; the purge and brushing count. How long:
  measured on your printer with `BED_SOAK_CALIBRATE BED=80` (probes the
  centre and corners until they stop moving, saved per temperature), else
  3 s per degree the bed rose, at most 10 minutes. Optional "probe until
  stable" mode; `PRINT_START SOAK=` overrides; settings in the printer's
  `macros/print_start.cfg`.

## v0.0.6

### Added
- `git` on the printer, so plugins from their own repositories can be
  installed and then updated from Fluidd (docs/plugins.md).
- Plugin API 1.3: plugins can bring Python libraries and Moonraker
  components. Two new plugins use it:
  [kiln-notify](https://github.com/djvalic/kiln-notify) (notifications with
  a photo to Telegram, Discord, ntfy, e-mail and 100+ more) and
  [kiln-timelapse](https://github.com/djvalic/kiln-timelapse) (timelapse
  videos, with ffmpeg built for the printer).

### Changed
- The Spoolman plugin moved to its own repository,
  [kiln-spoolman](https://github.com/djvalic/kiln-spoolman), and updates
  from Fluidd on its own. It is no longer in the image.

### Fixed
- Installed updates no longer pile up on the data partition (each
  left an ~80 MB copy behind; 26 of them filled 2 GB). Only the latest is
  kept, and earlier ones are removed when the next update is staged.
- The recovery OS shows its release and real build date (it showed a
  fixed 2026-06-16).

## v0.0.5

### Added
- **Power-loss recovery.** While printing, the print's state is saved every
  10 s. After a power cut, `RESUME_INTERRUPTED CONFIRM=1` continues the
  print where it stopped (no Z homing into the part); `CLEAR_INTERRUPTED`
  forgets it.
- **IFS auto-refill** (off by default, `IFS_AUTO_REFILL ENABLE=1`): when a
  slot runs out mid-print, the printer switches to another slot with the
  same material and colour and carries on.
- **OrcaSlicer filament sync:** the IFS slots (material, colour,
  temperature) appear in Moonraker's `lane_data`, which OrcaSlicer's
  Moonraker printer agent reads. See docs/orcaslicer.md.
- **Spoolman plugin** (shipped, off): a Spoolman spool per IFS slot; the
  loaded slot's spool becomes the active one.
- **Recovery OS updates itself** together with the main OS.
- Releases publish their source code (GPL).

### Changed
- Starts about 20 s faster (11.6 s from start-up to ready, was 33 s).
- The clock starts at the last known time instead of 1970 until the
  network time is there.
- Smaller image (79 MB, was 92 MB): Python libraries as bytecode only.
- HelixScreen v1.1.0-beta.10.
- Klipper's `PID_CALIBRATE` now suggests about half the values it used
  to (an upstream fix). If temperatures oscillate, run the PID step again.
