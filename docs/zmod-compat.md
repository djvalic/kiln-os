# Printing G-code made for zMod

G-code sliced with zMod's (and Bambufy's) AD5X slicer profiles calls macros
zMod defines. The plugins `zmod-compat`, `nopoop` and `bambufy-compat`
(`docs/plugins.md`) give those names to this system's own macros, so such
files print unchanged. Commands and behaviour follow zMod (ghzserg/zmod,
z_ad5x macro configs), ninjamida's nopoop and QuickSwap plugins and
Bambufy's documented slicer G-code; the macros were written for this
project, nothing was copied.

Checked against the user's files (about 140, two profile families):
"AD5X Nopoop .4/.6" (59 files: `SAVE_VARIABLE use_trash_on_print`,
`START_PRINT`, `T<n>`, `_GOTO_TRASH`, `_SBROS_TRASH`, `_DISABLE_SENSOR` /
`_ENABLE_SENSOR`, `END_PRINT`) and "Flashforge AD5X 0.4/0.6 nozzle - Home"
(81 files, Bambufy-based: firmware retraction, arcs, `_NOPOOP`). Klipper
batch runs of their tool-change blocks against the fake IFS: every command
exists and does what is described below.

## Command mapping

| zMod / slicer | Count in the files | Here | Plugin |
|---|---|---|---|
| `START_PRINT EXTRUDER_TEMP= BED_TEMP=` | 140 | `PRINT_START EXTRUDER= BED=`, then `LINE_PURGE`; without `EXTRUDER_TEMP=`/`BED_TEMP=` the temperatures the file already set (its own `M104`/`M140`), else zMod's 245 / 80 | zmod-compat |
| `START_PRINT` without `FORCE_*` | | `PRINT_START` decides: the printer's `macros/print_start.cfg` meshes the print area every print (zMod's `print_leveling: 1` + `use_kamp: 1`); the factory one does the stock Z check. The bed heat soak applies too; `SOAK=<s>` is passed on (ours, not zMod's) | zmod-compat |
| `START_PRINT FORCE_LEVELING=1` / `FORCE_KAMP=1` | | `PRINT_START LEVEL=1 ADAPTIVE=0` / `ADAPTIVE=1` | zmod-compat |
| `START_PRINT TOOL=n` (Bambufy) | | `PRINT_START TOOL=n` (loads it at the end of the start). TOOL must be a whole number or -1 (see the rule below) | zmod-compat |
| `START_PRINT SKIP_LEVELING= MESH= INTERNAL= EXTERNAL=` | | accepted, not needed | zmod-compat |
| `START_PRINT Z_OFFSET=` | | ignored, saved Z offset used (zMod with `load_zoffset: 1`, the user's setting) | zmod-compat |
| `END_PRINT` | 140 | `PRINT_END`; `unload_filament: 1` unloads the IFS lane first (zMod `remove_filament`) | zmod-compat |
| `T0`-`T3` | 5,665 | `IFS_SWAP` through the tool map (`ifs.cfg`); purge decided by the mode below | core / nopoop |
| `SAVE_VARIABLE VARIABLE=use_trash_on_print VALUE=0|2` | 50 | purge mode for the print's tool changes | nopoop |
| `_GOTO_TRASH [SPEED=]` | 337 | into the purge box: X 52.5, Y 229 plus this printer's offsets (`unit.cfg`); X first, leaving the box towards Y 220 if inside it; nothing if already there | zmod-compat |
| `_SBROS_TRASH` | 337 | out of the box to Y 220, back in, out again (knocks the purge off) | zmod-compat |
| `_DISABLE_SENSOR` / `_ENABLE_SENSOR` | 81 / 81 | toolhead runout sensor (`toolhead`) off / back on, only if it was on | zmod-compat |
| `_NOPOOP` | 1,962 | next tool change: prime only (the prime tower purges) | bambufy-compat |
| `_M106 FAN_MAX_SPEED=` | | part fan at the percentage x 0.5 | bambufy-compat |
| `TIMELAPSE_TAKE_FRAME` | 9,469 | nothing; the `timelapse` plugin ([kiln-timelapse](https://github.com/djvalic/kiln-timelapse)) replaces it | zmod-compat |
| `SET_ACTIVE_SPOOL ID=` / `CLEAR_ACTIVE_SPOOL` | 9 | Spoolman through Moonraker once `variable_spoolman: 1` (otherwise a message; without Moonraker's `[spoolman]` Klipper would stop the print) | zmod-compat |
| `SET_PRINT_STATS_INFO` | 138 | Klipper's, plus pause at a layer | zmod-compat |
| `SET_PAUSE_NEXT_LAYER`, `SET_PAUSE_AT_LAYER` | | pause when the layer starts (`MACRO=` default `PAUSE`); Fluidd/Mainsail use these too | zmod-compat |
| `M600` | | `PAUSE`, then wait at the purge box; `RESUME` returns | zmod-compat |
| `LINE_PURGE` | | `_PRIME_LINE FORCE=1` (line in front of the labelled objects; the printer's `macros/prime_line.cfg`, a message without it) | zmod-compat |
| `LED_ON`, `LED_OFF`, `LED S=0-100` | | chamber light | zmod-compat |
| `M300`, `PLAY_MIDI FILE=` | | the speaker (`ad5x_sound`, system): beep, MIDI files from the config folder's `midi/` or the image's sounds | system |
| `G10`, `G11`, `SET_RETRACTION` | 128,759 / 128,704 / 2 | Klipper `[firmware_retraction]`: 0.7 mm at 35 mm/s (zMod's values; the Home profile says 1.4 mm, which zMod didn't apply) | core (`ad5x.cfg`) |
| `G17` (and `G2`/`G3`) | 3,527 | Klipper `[gcode_arcs]` | core |
| `SET_VELOCITY_LIMIT`, `M204`, `M220`, `M106`, `SET_FAN_SPEED FAN=fanM106`, `G92`, `M104`/`M109`/`M190`, `M400`, `G4`, `M73`, `RESPOND`, `SAVE_VARIABLE`, `EXCLUDE_OBJECT_*`, `SET_PRESSURE_ADVANCE` | | Klipper's own, or `ad5x.cfg` (M106 P2 is ignored: no chamber fan) | core |
| `ENABLE_PLUGIN NAME=`, `DISABLE_PLUGIN NAME=` | | plugin manager (`docs/plugins.md`), plus `LIST_PLUGINS` | core |
| `CLEAR_NOZZLE`, `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `AUTO_FULL_BED_LEVEL` | | the printer's `macros/quick_actions.cfg` (screen quick actions, `docs/config-layout.md`) | core |
| `LOAD_CELL_TARE` | | `ad5x.cfg` (strain-gauge tare) | core |

`TOOL=` rule (issue #12, same check as `PRINT_START`): a whole number
loads that slicer tool; `-1` or no `TOOL=` loads none. Anything else loads
no tool and the console shows an error. That covers an unexpanded
placeholder such as `TOOL=[initial_tool]` (before this check it became tool
0) and an empty `TOOL=`, which used to load tool 0 and now loads none. Use
the slicer's expanded value.

Not provided (no file calls them; zMod-only machinery): `SAVE_ZMOD_DATA`,
`REBOOT` / `SHUTDOWN` (shell access from Klipper), `PID_TUNE_BED` /
`PID_TUNE_EXTRUDER` (use `SETUP_WIZARD_STEP STEP=pid`: its results are
kept in `ad5x-tuning.cfg`, which `SAVE_CONFIG` can't), `COLDPULL`, zMod's
camera, MIDI, Telegram and display macros, Bambufy's colour dialogs,
`POOP` and port sensors, QuickSwap's calibration macros (`IFS_TUNE` does
that here).

## Purge modes (nopoop plugin)

zMod's save variable `use_trash_on_print`, which the Nopoop profiles set
at the start of each file (the Home profile files don't set it):

| Value | zMod name | Tool change in a print here |
|---|---|---|
| 0 | nopoop | cut, unload, load, then only **prime**: IFS and extruder feed `prime_length` (12 mm) past the head sensor at the purge box, wipe on the box edge (`prime_gcode`), back to the print; the slicer's prime tower takes the purge |
| 2 | slicer-controlled purge | the same; the slicer then flushes at the box itself (`_GOTO_TRASH`, `G1 E...`, `_SBROS_TRASH`) |
| 1, unset, anything else | (default) | full purge at the box as stock: rounds of 90 mm push + flush |

- Outside a print (console, screen, `IFS_LOAD`) every swap purges, as on
  zMod.
- `_NOPOOP` (bambufy-compat) makes the next tool change prime only,
  whatever the variable says; a Bambufy file's tool changes without it
  keep the variable's mode (default: purge at the box, on top of the
  slicer's flush in Bambufy's "poop" mode).
- `IFS_SWAP PURGE=0|1` decides it for one swap, in a print or not.
- The value stays in `variables.cfg` until a file sets another one, as on
  zMod: a later file that doesn't set it (or a file from another profile)
  uses the last value. zMod's profile notes warn about the same.

Differences from zMod:

- zMod primes over the print from layer 2 on in mode 0 (and squiggles the
  blob flat); here the prime always happens at the purge box, then the
  head returns to where the print stopped. A few seconds more per change,
  no bead on the part.
- The first tool after `START_PRINT` in a mode-0/2 file only primes, as
  on zMod (its start purge and `LINE_PURGE` already cleared the nozzle
  with the previous filament).
- The prime length: zMod inserts 12 mm (plus its
  `filament_unload_before_cutting`, 0 by default); QuickSwap's
  `insert_base_distance` was 8 mm on the user's printer, plus its own
  pre-cut retract. This system doesn't retract before the cut, so 12 mm
  is the starting point. Thin first prime-tower lines: raise
  `prime_length` in `local.cfg` (`[ifs]`); blobs on the tower: lower it.
- After every tool change the head goes back to the print position
  (`after_gcode`); in mode 2 the slicer's `_GOTO_TRASH` then goes to the
  box again. zMod stayed at the box in mode 2.

## The user's zMod settings and their counterparts

| zMod (variables.cfg / user.cfg) | Here |
|---|---|
| plugins recommend, nopoop, quickswap | `recommend`, `nopoop` plugins (migration enables them); QuickSwap: `IFS_TUNE` |
| `use_trash_on_print = 0` (global) | set by each Nopoop file; Home files leave the last value |
| `clear = 'LINE_PURGE'`, `disable_priming = 0` | `START_PRINT` `variable_line_purge: 1`; the line itself: `macros/prime_line.cfg` (`_PRIME_LINE`) |
| `remove_filament = 1` | `END_PRINT` `variable_unload_filament` (0 by default; set 1 in `local.cfg` to unload at the end) |
| `load_zoffset = 1` | always: the saved Z offset (`zoffset`) |
| `use_kamp = 1`, `print_leveling = 1` | the default: `PRINT_START` meshes the print area every print (`variable_mesh_every_print: 1`, `variable_adaptive_mesh: 1` in `macros/print_start.cfg`; set 0 in `local.cfg` for the stock Z check) |
| `[extruder] pressure_advance: 0.035` (0.6 nozzle) | the files set it with `SET_PRESSURE_ADVANCE`; for others put it in `local.cfg` |
| `[quickswap] insert_base_distance: 8.0` | `[ifs] prime_length` (see above) |
| `[zmod_ifs]` | none needed (`klipper/extras/ifs.py`) |

Example `local.cfg` lines:

```
[gcode_macro END_PRINT]
variable_unload_filament: 1

[ifs]
prime_length: 14

[firmware_retraction]
retract_length: 0.8
```

## First tool load of a print

With the slicer's prime tower on (`use_trash_on_print` 0 or 2), the first tool
change after a print starts only primes (the nozzle is filled), and the bed
prime tower purges it. On 2026-10-17 a nopoop print started with the previous
colour in its first layer, which is why the box purge existed; in trash mode
(`use_trash_on_print` 1) that box purge still runs. Later changes follow
`use_trash_on_print`. A resume from pause is not
a new print; a first tool that is already loaded needs no purge (PRINT_START
purged the nozzle).
