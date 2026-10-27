# Changelog

What changed for people using Kiln OS. Each release's notes (Gitea and
GitHub) take its section from here: `## vX.Y.Z`, or `## Unreleased` when
the release has no section of its own yet (rename it after the release).

## Unreleased

### Fixed
- **Spoolman grams on the slot tile**: a slot linked to a Spoolman spool shows its remaining grams under the material (for example 750g), where it used to show nothing. Slots without a Spoolman link are unchanged (HelixScreen patch 0027, `ams_state.cpp`).

### Changed
- **IFS channel count in one place** (`klipper/extras/ifs.py`): the four channels come from one constant, and the reply parser and the status lists follow it. No change on the printer: still four channels. This is groundwork for other IFS hardware; it does not add support for any.
- **New logo and brand guide** (`docs/brand/`): a frost-blue ring with four gaps, one per IFS slot, and a solid K. One colour; the slot is read by position. App icon and lockup included.

## v0.0.27

### Added
- **Spoolman spool per IFS slot on the screen** (with the `kiln-spoolman` plugin only): the spool a slot was given with `SPOOLMAN_SET_SLOT` is linked to that slot in HelixScreen, and its name and remaining grams show in the AMS slot view. Without the plugin, or without Spoolman, nothing changes (HelixScreen patch 0026, `ams_backend_ad5x_ifs.cpp`). A spool picked on the screen stays until the plugin's value changes; clearing a slot in the plugin does not unlink it on the screen.

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
