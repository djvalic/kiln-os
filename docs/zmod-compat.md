# Printing G-code made for zMod

G-code sliced with zMod's (and Bambufy's) AD5X slicer profiles calls macros
zMod defines. The plugins `zmod-compat`, `nopoop` and `bambufy-compat`
(`docs/plugins.md`) give those names to this system's own macros, so such
files print unchanged. Commands and behaviour follow zMod (ghzserg/zmod,
z_ad5x macro configs), ninjamida's nopoop and QuickSwap plugins and
Bambufy's documented slicer G-code; the macros were written for this
project, nothing was copied.

Checked against the developer's G-code files (about 140, two profile families):
"AD5X Nopoop .4/.6" (59 files: `SAVE_VARIABLE use_trash_on_print`,
`START_PRINT`, `T<n>`, `_GOTO_TRASH`, `_SBROS_TRASH`, `_DISABLE_SENSOR` /
`_ENABLE_SENSOR`, `END_PRINT`) and "Flashforge AD5X 0.4/0.6 nozzle - Home"
(81 files, Bambufy-based: firmware retraction, arcs, `_NOPOOP`). Klipper
batch runs of their tool-change blocks against the fake IFS: every command
exists and does what is described below.

## Command mapping

| zMod / slicer | Count in the files | Here | Plugin |
|---|---|---|---|
| `START_PRINT EXTRUDER_TEMP= BED_TEMP=` | 140 | `PRINT_START EXTRUDER= BED=`, which draws the prime line (zMod's line purge); `LINE_PURGE` after it only when that line is off (`[gcode_macro _PRIME_LINE] variable_prime_line: 0`), so the line is drawn once either way; without `EXTRUDER_TEMP=`/`BED_TEMP=` the temperatures the file already set (its own `M104`/`M140`), else zMod's 245 / 80. A temperature that is not a number or is out of range stops the start (see the rule below) | zmod-compat |
| `START_PRINT` without `FORCE_*` | | `PRINT_START` decides: the printer's `macros/print_start.cfg` meshes the print area every print (zMod's `print_leveling: 1` + `use_kamp: 1`); the factory one does the stock Z check. The bed heat soak applies too; `SOAK=<s>` is passed on (ours, not zMod's) | zmod-compat |
| `START_PRINT FORCE_LEVELING=1` / `FORCE_KAMP=1` | | `PRINT_START LEVEL=1 ADAPTIVE=0` / `ADAPTIVE=1` | zmod-compat |
| `START_PRINT TOOL=n` (Bambufy) | | `PRINT_START TOOL=n` (loads it at the end of the start). TOOL must be a whole number or -1 (see the rule below) | zmod-compat |
| `START_PRINT SKIP_LEVELING= MESH= INTERNAL= EXTERNAL=` | | accepted, not needed | zmod-compat |
| `START_PRINT Z_OFFSET=` | | ignored, saved Z offset used (zMod with `load_zoffset: 1`, the developer's setting) | zmod-compat |
| `END_PRINT` | 140 | `PRINT_END`; `unload_filament: 1` unloads the IFS lane first (zMod `remove_filament`) | zmod-compat |
| `T0`-`T3` | 5,665 | `IFS_SWAP` through the tool map (`ifs.cfg`); purge decided by the mode below | core / nopoop |
| `SAVE_VARIABLE VARIABLE=use_trash_on_print VALUE=0|2` | 50 | purge mode for the print's tool changes | nopoop |
| `SAVE_ZMOD_DATA USE_TRASH_ON_PRINT=0|1|2` | | the same save variable (zMod's documented way); another value is refused, not saved. `REMOVE_FILAMENT`, `DISABLE_PRIMING`, `PRINT_LEVELING`, `USE_KAMP`: not saved, a line names the `local.cfg` setting here (table below). Other keys: one line, ignored | zmod-compat |
| `_GOTO_TRASH [SPEED=]` | 337 | into the purge box: X 52.5, Y 229 plus this printer's offset (`TRASH_OFFSET`, else `unit.cfg`; as `_PURGE_BOX_POS` holds it); X first, leaving the box towards Y 220 if inside it; nothing if already there | zmod-compat |
| `_SBROS_TRASH` | 337 | out of the box to Y 220, back in, out again (knocks the purge off) | zmod-compat |
| `_DISABLE_SENSOR` / `_ENABLE_SENSOR` | 81 / 81 | toolhead runout sensor (`toolhead`) off / back on, only if it was on | zmod-compat |
| `_NOPOOP` | 1,962 | next tool change: prime only (the prime tower purges) | bambufy-compat |
| `_M106 FAN_MAX_SPEED=` | | part fan at the percentage x 0.5 | bambufy-compat |
| `TIMELAPSE_TAKE_FRAME` | 9,469 | nothing; the `timelapse` plugin ([kiln-timelapse](https://github.com/djvalic/kiln-timelapse)) replaces it | zmod-compat |
| `SET_ACTIVE_SPOOL ID=` / `CLEAR_ACTIVE_SPOOL` | 9 | Spoolman through Moonraker once `variable_spoolman: 1` (otherwise a message; without Moonraker's `[spoolman]` Klipper would stop the print) | zmod-compat |
| `SET_PRINT_STATS_INFO` | 138 | Klipper's, plus pause at a layer | zmod-compat |
| `SET_PAUSE_NEXT_LAYER`, `SET_PAUSE_AT_LAYER` | | pause when the layer starts (`MACRO=` default `PAUSE`); Fluidd/Mainsail use these too | zmod-compat |
| `M600` | | filament change: `PAUSE`, lift (zMod's park lift, 50 mm, at most to 5 mm under the top of Z; `variable_lift` in `local.cfg`), then `_GOTO_TRASH` into the purge box. `RESUME` goes back like the IFS swap: still lifted, Y first (out of the box), then X, then Z down over the print position, ending in the same G-code state (modes, speed, E) as before; a filament purged by hand at the box no longer gets dragged onto the bed or the print. `T=`/`TRASH=` do nothing on the AD5X, as in zMod. Not homed: pauses only. The plugin's `PAUSE`/`RESUME` are `ad5x.cfg`'s pass-throughs plus this way back: a pause without `M600` (screen, Fluidd, runout, IFS auto-refill) resumes with Klipper's single move as without the plugin | zmod-compat |
| `LINE_PURGE` | | `_PRIME_LINE FORCE=1` (line in front of the labelled objects; the printer's `macros/prime_line.cfg`, a message without it). During a print, skipped with a console line once `PRINT_START` has drawn its prime line; `LINE_PURGE FORCE=1` draws anyway ("KAMP" below) | zmod-compat |
| `LED_ON`, `LED_OFF`, `LED S=0-100` | | chamber light | zmod-compat |
| `M300`, `PLAY_MIDI FILE=` | | the speaker (`ad5x_sound`, system): beep, MIDI files from the config folder's `midi/` or the image's sounds | system |
| `G10`, `G11`, `SET_RETRACTION` | 128,759 / 128,704 / 2 | Klipper `[firmware_retraction]`: 0.7 mm at 35 mm/s (zMod's values; the Home profile says 1.4 mm, which zMod didn't apply) | core (`ad5x.cfg`) |
| `G17` (and `G2`/`G3`) | 3,527 | Klipper `[gcode_arcs]` | core |
| `SET_VELOCITY_LIMIT`, `M204`, `M220`, `M106`, `SET_FAN_SPEED FAN=fanM106`, `G92`, `M104`/`M109`/`M190`, `M400`, `G4`, `M73`, `RESPOND`, `SAVE_VARIABLE`, `EXCLUDE_OBJECT_*`, `SET_PRESSURE_ADVANCE` | | Klipper's own, or `ad5x.cfg` (M106 P2 is ignored: no chamber fan) | core |
| `ENABLE_PLUGIN NAME=`, `DISABLE_PLUGIN NAME=` | | plugin manager (`docs/plugins.md`), plus `LIST_PLUGINS` | core |
| `CLEAR_NOZZLE`, `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `AUTO_FULL_BED_LEVEL`, `BED_LEVEL_SCREWS_TUNE` | | the printer's `macros/quick_actions.cfg` (screen quick actions, `docs/config-layout.md`) | core |
| `LOAD_CELL_TARE` | | `ad5x.cfg` (strain-gauge tare) | core |

`TOOL=` rule (issue #12, same check as `PRINT_START`): a whole number
loads that slicer tool; `-1` or no `TOOL=` loads none. Anything else loads
no tool and the console shows an error. That covers an unexpanded
placeholder such as `TOOL=[initial_tool]` (before this check it became tool
0) and an empty `TOOL=`, which used to load tool 0 and now loads none. Use
the slicer's expanded value.

Temperature rule (same check in `START_PRINT` and both `PRINT_START`s): an
`EXTRUDER_TEMP=`/`BED_TEMP=` (`EXTRUDER=`/`BED=`) that is not a number, such
as an unexpanded `[nozzle_temperature_initial_layer]` or
`{first_layer_temperature[0]}`, or an empty value, stops the print before
anything heats, with an error naming the parameter and the value received.
So does a nozzle below `min_extrude_temp` (170 here; never below 150) or
above `max_temp` (350), and a bed above its `max_temp` (130). Bed 0 is
accepted: the bed stays off, which some PLA profiles choose. zMod itself
turns such text into 0 with `|float` and then skips heating that heater
(`_WAIT_TEMP` heats only a non-zero target), so the print starts with a
cold nozzle or bed; before this check START_PRINT here passed the 0 on and
`PRINT_START` heated to 0. A missing parameter is not an error: the file's
own `M104`/`M140`, else the default (above).

Not provided (no file calls them; zMod-only machinery): zMod's other
`SAVE_ZMOD_DATA` settings (see the table), `REBOOT` / `SHUTDOWN` (shell
access from Klipper), `PID_TUNE_BED` / `PID_TUNE_EXTRUDER` (use
`SETUP_WIZARD_STEP STEP=pid`: its results are kept in `ad5x-tuning.cfg`,
which `SAVE_CONFIG` can't), `COLDPULL`, zMod's
camera, MIDI, Telegram and display macros, Bambufy's colour dialogs,
`POOP` and port sensors, QuickSwap's calibration macros (`IFS_TUNE` does
that here).

## Purge modes (nopoop plugin)

zMod's save variable `use_trash_on_print`, which the Nopoop profiles set
at the start of each file (the Home profile files don't set it;
`SAVE_ZMOD_DATA USE_TRASH_ON_PRINT=` sets it too):

| Value | zMod name | Tool change in a print here |
|---|---|---|
| 0 | nopoop | layer 1 (or no layer info): cut, unload, load, then only **prime**: IFS and extruder feed `prime_length` (12 mm) past the head sensor at the purge box, wipe on the box edge (`prime_gcode`), back to the print. From layer 2 on (`prime_at_print`, as zMod): cut, back to where the print stopped (the prime tower, at print Z), unload, load and prime there, flatten the bead (`prime_at_print_gcode`), go on. The slicer's prime tower takes the purge |
| 2 | slicer-controlled purge | the layer-1 way (prime at the box) on every layer; the slicer then flushes at the box itself (`_GOTO_TRASH`, `G1 E...`, `_SBROS_TRASH`) |
| 1, unset, anything else | (default) | full purge at the box as stock: rounds of 90 mm push + flush |

With 0 or 2, `PRINT_START` doesn't purge at the box either (the prime line
flushes the nozzle, as zMod's line purge; `docs/print-start.md`).

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

- Mode 0 from layer 2 on primes at the print, as zMod, only when it is
  safe: the layer must be known (`SET_PRINT_STATS_INFO`, which zMod
  profiles send), the file must label its objects, and the print position
  must be at least 5 mm outside every object's outline and not inside an
  object. Otherwise (and with `prime_at_print: False` in `local.cfg`'s
  `[ifs]`) the change primes at the box, which costs a few seconds and
  keeps the bead off the part. zMod primes wherever the head is, so a
  file in mode 0 without a prime tower gets the bead on the part there.
- The flatten move here is a 3 mm square around the bead without
  extrusion (`prime_at_print_gcode`), not zMod's pattern.
- The first tool after `START_PRINT` in a mode-0/2 file only primes, as
  on zMod. Neither purges at the box at the start: zMod's line purge (with
  KAMP) and the prime line here flush the nozzle. When `PRINT_START` loads
  the first colour itself (`TOOL=`), the prime line runs after that load,
  so it flushes the new colour.
- The prime length: zMod inserts 12 mm (plus its
  `filament_unload_before_cutting`, 0 by default); QuickSwap's
  `insert_base_distance` was 8 mm on the developer's printer, plus its own
  pre-cut retract. This system doesn't retract before the cut, so 12 mm
  is the starting point. Thin first prime-tower lines: raise
  `prime_length` in `local.cfg` (`[ifs]`); blobs on the tower: lower it.
- After every tool change the head goes back to the print position
  (`after_gcode`); in mode 2 the slicer's `_GOTO_TRASH` then goes to the
  box again. zMod stayed at the box in mode 2.

## The developer's zMod settings and their counterparts

| zMod (variables.cfg / user.cfg) | Here |
|---|---|
| plugins recommend, nopoop, quickswap | `recommend`, `nopoop` plugins (migration enables them); QuickSwap: `IFS_TUNE` |
| `use_trash_on_print = 0` (global) | set by each Nopoop file; Home files leave the last value |
| `clear = 'LINE_PURGE'`, `disable_priming = 0` | `START_PRINT` `variable_line_purge: 1`; the line itself: `macros/prime_line.cfg` (`_PRIME_LINE`) |
| `remove_filament = 1` | `END_PRINT` `variable_unload_filament` (0 by default; set 1 in `local.cfg` to unload at the end) |
| `load_zoffset = 1` | always: the saved Z offset (`zoffset`) |
| `use_kamp = 1`, `print_leveling = 1` | the default: `PRINT_START` meshes the print area every print (`variable_mesh_every_print: 1`, `variable_adaptive_mesh: 1` in `macros/print_start.cfg`; set 0 in `local.cfg` for the stock Z check); no KAMP include needed ("KAMP" below) |
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

## KAMP

zMod ships its own modified copy of KAMP (the `KAMP/` folder next to its
macro configs), not upstream KAMP:

- The mesh macro is renamed `_KAMP_BED_MESH_CALIBRATE`. zMod's own
  `BED_MESH_CALIBRATE` calls it only when `use_kamp` is 1 (otherwise
  Klipper's full mesh), and zMod's `KAMP` macro calls it for
  `START_PRINT FORCE_KAMP=1`.
- Its `LINE_PURGE` is the line behind zMod's `clear` default
  (`LINE_PURGE`); `_SMART_PARK` parks next to the print area;
  `_KAMP_Settings` holds the print area zMod reads from the file
  (`fast_*` variables).
- It depends on zMod-only macros and settings: `_TEST_MIN_MAX`,
  `_CLEAR2`, `_CLIENT_VARIABLE`, the `[zmod]` section's language, and
  `_DISABLE_SENSOR` / `_ENABLE_SENSOR` (zmod-compat has these two). Copying
  zMod's `KAMP/` folder to this printer therefore fails at print time with
  unknown commands. Don't copy it.

Here `PRINT_START` does both jobs itself (`macros/print_start.cfg`: a mesh
of the print area every print; `macros/prime_line.cfg`: the prime line in
front of the objects), so no KAMP files are needed (neither zMod's copy
nor upstream KAMP) and slicer profiles don't need `BED_MESH_CALIBRATE` or
`LINE_PURGE` in their start G-code; zMod-made files call only
`START_PRINT`.

`use_kamp` differs: on zMod it changes every `BED_MESH_CALIBRATE`, the
one typed in the console included. Here `variable_adaptive_mesh`
changes only the mesh `PRINT_START` makes; `BED_MESH_CALIBRATE` from the
console stays Klipper's mesh (whole bed unless `ADAPTIVE=1`).

Since issue #73, during a print a `BED_MESH_CALIBRATE`, `LINE_PURGE` or
`VORON_PURGE` (upstream KAMP's `Voron_Purge.cfg`) after `PRINT_START` is
skipped with a console line, as `PRINT_START` has already meshed and drawn
its prime line (`FORCE=1` runs it anyway; a `BED_MESH_CALIBRATE` with
`PROFILE=` or `ADAPTIVE=0` always runs). `SMART_PARK` (upstream
`Smart_Park.cfg`) is harmless and not skipped. This check is Kiln's own:
zMod has none, as its profiles put only `START_PRINT` in the start
G-code.

Klipper start shows a warning (Fluidd and Mainsail list it with Klipper's
warnings; also in the console) when a config replaces the `gcode:` of
these commands, not for an include as such:

- `BED_MESH_CALIBRATE`: upstream KAMP's `Adaptive_Meshing.cfg` does this
  (zMod's copy doesn't: its macro has another name). Kiln's mesh then runs
  without the strain gauge tare, and no full mesh saves the bed centre
  (`ad5x_center_z`) any more.
- `LINE_PURGE` (upstream KAMP's `Line_Purge.cfg`, or another config): only
  while Kiln's prime line is on.

With upstream KAMP's `BED_MESH_CALIBRATE` in place, don't turn Kiln's mesh
off (`mesh_every_print: 0`): the stock Z check then needs a saved bed
centre, which only Kiln's full mesh writes, so without one each print stops
at the start with "no saved centre Z". Remove the KAMP include instead.

`docs/print-start.md`, "One mesh and one prime line per print", has the
details and the settings to let the slicer's mesh or line run instead.

## First tool load of a print

With the slicer's prime tower on (`use_trash_on_print` 0 or 2), the first tool
change after a print starts only primes (the nozzle is filled), and the bed
prime tower purges it. On 2026-10-17 a nopoop print started with the previous
colour in its first layer, which is why the box purge existed; in trash mode
(`use_trash_on_print` 1) that box purge still runs. Later changes follow
`use_trash_on_print`. A resume from pause is not
a new print. In trash mode a first tool that is already loaded needs no
purge (PRINT_START purged the nozzle at the box); in mode 0 or 2
PRINT_START doesn't purge at the box and the prime line flushes it.
