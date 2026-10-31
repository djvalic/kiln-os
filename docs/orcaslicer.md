# OrcaSlicer with Kiln OS

## Uploading and printing

Add the printer in OrcaSlicer as a physical printer with host type
**Octo/Klipper** and the printer's address (e.g. `192.168.1.56`). Moonraker
answers on port 80 through nginx (and on 7125).

Send G-code, not 3MF: turn **off** "Use 3MF instead of G-code" for this
printer in OrcaSlicer. Kiln OS does not unpack a `.gcode.3mf` upload: Moonraker
accepts it (the upload answers 201) and stores it as a plain file, which the
printer does not print. Delete any such file in Fluidd's Files page.

## Recommended machine G-code

What works best with Kiln OS: the printer does the heating, nozzle
cleaning, bed mesh, loading the first colour and the purge at every colour
change itself, so the slicer's G-code stays short. In OrcaSlicer: Printer
settings > Machine G-code, replace each box with the text below.

**Machine start G-code**

```
SAVE_VARIABLE VARIABLE=use_trash_on_print VALUE=1
PRINT_START BED=[bed_temperature_initial_layer_single] EXTRUDER=[nozzle_temperature_initial_layer] TOOL=[initial_tool]
SET_PRINT_STATS_INFO TOTAL_LAYER=[total_layer_count]
```

- `use_trash_on_print 1`: the printer purges at the box at each colour
  change. A file sliced with a zMod "nopoop" profile sets 0 (purge in the
  slicer's prime tower) and that value stays on the printer; this line
  puts it back for files from this profile.
- `PRINT_START` (`docs/print-start.md`): home, heat, purge and brush at
  the box, bed heat soak, mesh of the print area, the saved Z offset, then
  the first slicer tool loaded from its IFS slot (T0 = slot 1 unless
  `IFS_MAP_TOOL` maps it).
- The temperatures come from the **filament** profile: for PLA at 235 /
  60, set Nozzle (initial layer and other layers) to 235 and the bed for
  your plate type to 60 there. Because this line has the temperature
  placeholders, OrcaSlicer doesn't add its own heating commands before it.

**Machine end G-code**

```
PRINT_END
```

**Before layer change G-code**

```
;BEFORE_LAYER_CHANGE
;[layer_z]
G92 E0
```

**Layer change G-code**

```
;AFTER_LAYER_CHANGE
;[layer_z]
SET_PRINT_STATS_INFO CURRENT_LAYER={layer_num + 1}
```

(the layer count on the touch screen and in Fluidd, and pause at a layer)

**Change filament G-code**

```
T[next_extruder]
```

`T0`-`T3` swap to the tool's IFS slot: cut, unload, load, purge at the
box (the amount from the two colours) and wipe. Turn **Prime tower** off
(Others > Prime tower): the purge happens at the box, not on the plate.
The flushing volumes are then only used for OrcaSlicer's time and
filament estimates.

**Timelapse G-code** (only with the [kiln-timelapse](https://github.com/djvalic/kiln-timelapse) plugin)

```
TIMELAPSE_TAKE_FRAME
```

**Pause G-code**

```
PAUSE
```

Printer settings > Basic information: G-code flavor **Klipper**.

zMod profiles keep working unchanged (`START_PRINT`, `END_PRINT`,
`_GOTO_TRASH`, nopoop, `docs/zmod-compat.md`); this is the simpler choice
for new profiles.

## The IFS slots in OrcaSlicer (filament sync)

Kiln OS keeps the IFS slots in Moonraker's database, namespace `lane_data`,
in the format the AFC filament changer uses (Moonraker component
`kiln_lanes`, `moonraker/components/kiln_lanes.py`):

| Record | Fields |
|---|---|
| `lane1` .. `lane4` (IFS slot 1-4) | `lane`: slicer tool `"0"`..`"3"` (slot 1 = T0); `material` (`""` when the slot has no filament or no type); `color` (`#RRGGBB`); `nozzle_temp`; `bed_temp` (0); `spool_id` (null); `scan_time` (UTC, set when the slot changes; empty until the first change after start). No `vendor` or `name` key: HelixScreen treats `vendor` as its own and would not adopt a later edit |

It's updated whenever a slot's material, colour or temperature changes
(touch screen, `IFS_SET_MATERIAL`) or a spool goes in or out.

OrcaSlicer's **Moonraker printer agent** reads it and fills its filament
list with what is loaded. In OrcaSlicer builds that have it (nightlies after
2.4.2): Preferences > Developer > Experimental Features > "Use printer
agents instead of print hosts", then pick the printer in the Device tab and
sync the filaments. Without that option OrcaSlicer uploads as before and
ignores `lane_data`.

Read it by hand:

    curl http://192.168.1.56/server/database/item?namespace=lane_data

## Tools and slots

A slicer tool T0-T3 loads IFS slot 1-4 unless the file maps it otherwise
with `IFS_MAP_TOOL TOOL=n SLOT=m` (per print). The separate OrcaSlicer
plugin [kiln-orca](https://github.com/djvalic/kiln-orca) adds those lines to exported
G-code by matching each tool's material and colour against the slots.

To print with whatever is loaded, without a plugin: `IFS_MAP_MODE MODE=loaded`
(saved; it applies at each print start). Each tool then goes to the loaded slot
with the same material and the nearest colour, read from the file's
`; filament_type` and `; filament_colour` lines when it starts, so an older
file that maps to the wrong slot is corrected too. Without those lines, tools
use the loaded slots in slot order; with only slot 2 loaded, every tool uses it.
An `IFS_MAP_TOOL` line in the file still wins, so a file exported by the
kiln-orca plugin keeps the map the plugin wrote.
`IFS_MAP_MODE MODE=fixed` goes back to T0-T3 -> slots 1-4. An explicit
`IFS_MAP_TOOL` in the file still wins for the tools it names.
