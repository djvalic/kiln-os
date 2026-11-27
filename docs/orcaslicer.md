# OrcaSlicer with Kiln OS

## Uploading and printing

Add the printer in OrcaSlicer as a physical printer with host type
**Octo/Klipper** and the printer's address (shown on the touch screen under Settings > Connection > Network Settings). Moonraker
answers on port 80 through nginx (and on 7125).

G-code and sliced 3MF both print. With "Use 3MF instead of G-code" on, Orca
sends a `.gcode.3mf`; Kiln OS (since v0.0.45) unpacks the sliced plate's
G-code to `<name>.gcode`, drops the `.3mf` and prints it. A `.3mf` with
several sliced plates is unpacked to `<name>_plate<N>.gcode`, one file per
plate, and none is started: start the one you want in Fluidd or on the
screen. A project `.3mf` that was never sliced is refused with a message.

When an upload asked to print and the print doesn't start (a print is
already running or paused, Klipper isn't ready or refused the file), Fluidd's
console shows `!! Upload <file>: print not started: <reason>`.

Before v0.0.45 a `.gcode.3mf` upload was stored without printing (the upload
still answered 201, issue #35). Delete such files in Fluidd's Files page and
send them again.

## Kiln profiles for OrcaSlicer

The quickest start: Kiln's OrcaSlicer profiles (OrcaSlicer 2.5) have the
machine G-code below already in, for every nozzle size, plus process and
filament profiles. Download `kiln-ad5x-orcaslicer-profiles.zip` from
[kiln-orca's latest release](https://github.com/djvalic/kiln-orca/releases/latest),
then File > Import > Import Configs... and pick the zip; choose the printer
for your nozzle, for example **AD5X 0.4 nozzle (Kiln)**. What they set and
what still needs a print test:
[kiln-orca/profiles](https://github.com/djvalic/kiln-orca/blob/main/profiles/README.md).
The rest of this page is for setting up your own profile.

## Recommended machine G-code

What works best with Kiln OS: the printer does the heating, nozzle
cleaning, bed mesh, loading the first colour and the purge at every colour
change itself, so the slicer's G-code stays short. In OrcaSlicer: Printer
settings > Machine G-code, replace each box with the text below.

**Machine start G-code**

```
SAVE_VARIABLE VARIABLE=use_trash_on_print VALUE={if enable_prime_tower}0{else}1{endif}
PRINT_START BED=[bed_temperature_initial_layer_single] EXTRUDER=[nozzle_temperature_initial_layer] TOOL=[initial_tool]
SET_PRINT_STATS_INFO TOTAL_LAYER=[total_layer_count]
```

- `use_trash_on_print`, from OrcaSlicer's prime tower switch: tower off
  (the default here), 1, the printer purges at the box at each colour
  change; tower on, 0, the printer only primes the nozzle (the nopoop
  plugin, on by default) and the tower purges, with "Flush into objects'
  infill" or "Flush into objects" if they are on. The value stays on the
  printer until a file sets another one, so every file sets it.
- `PRINT_START` (`docs/print-start.md`): home, heat, purge and brush at
  the box, bed heat soak, mesh of the print area, the saved Z offset, then
  the first slicer tool loaded from its IFS slot (T0 = slot 1 unless
  `IFS_MAP_TOOL` maps it).
- The temperatures come from the **filament** profile: for PLA as
  Flashforge's Generic PLA, set Nozzle (initial layer and other layers) to
  220 and the bed for every plate type to 55 (first layer) / 50 there. Because this line has the temperature
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
box (the amount from the two colours) and wipe. With **Prime tower** off
(Others > Prime tower) the purge happens at the box, not on the plate.
The flushing volumes are then only used for OrcaSlicer's time and
filament estimates: OrcaSlicer's flush settings (flush volumes, multiplier,
flush into infill or objects) don't change what the printer purges.

The printer's purge is set on the printer. By default it is stock's: one
or two rounds of a 90 mm push plus a 90 mm flush per colour change. To
purge less, measure what your printer needs once:
`IFS_PURGE_TEST FROM=<dark slot> TO=<light slot>` prints a row of dots on
the bed front, and `IFS_PURGE_RESULT DOT=<first clean dot>` saves it
(`docs/deviations-from-stock.md`, "Colour-change purge length"); every
colour change then purges once, the push plus that length.

With the prime tower on, the start G-code above sets purge mode 0: the
printer only primes the nozzle at the box (12 mm), and OrcaSlicer's tower
and flush volumes do the purging; "Flush into objects' infill" and "Flush
into objects" (per object) move part of it into the print
(`docs/zmod-compat.md`, "Purge modes").

Colour painted on a top surface is carried down through the top shell
layers, and each of those layers changes colour: on a part like a coin with
a painted face, fewer top shell layers (3) means fewer colour changes.

Tool-change retraction (Printer settings > Extruder, "Length" and "Extra
length on restart" under Retraction when switching material): 3 mm and 0.
The printer pulls the new filament back 3 mm after its purge, and these put
it back exactly. Flashforge's own AD5X profile (5 mm and -3) leaves 2 mm
too much.

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
| `lane1` .. `lane4` (IFS slot 1-4) | `lane`: slicer tool `"0"`..`"3"` (slot 1 = T0); `material` (`""` when the slot has no filament or no type); `color` (`#RRGGBB`); `nozzle_temp`; `bed_temp` (the slot's `BED_TEMP`, else 0 or the touch screen's); `filament_id` (the slot's `FILAMENT_ID` exactly as set, else Kiln's OrcaSlicer profile for the slot's type, see below; no key for other types or an empty slot); `spool_id` (the slot's `SPOOL_ID`, else null or the touch screen's); `vendor_name`, `name` (the slot's `VENDOR` and `NAME`, else the touch screen's or no key); `scan_time` (UTC, set when the slot changes; empty until the first change). The slot's values are set with `IFS_SET_MATERIAL` (plugin API 1.12). No `vendor` key: HelixScreen treats `vendor` as its own and would not adopt a later edit |

It's updated whenever a slot's material, colour or temperature changes
(touch screen, `IFS_SET_MATERIAL`) or a spool goes in or out, only the
slots that changed.

OrcaSlicer's **Moonraker printer agent** reads it and fills its filament
list with what is loaded. In OrcaSlicer 2.5 it is off by default: turn on
Preferences > Developer > Experimental Features > "Use printer agents
instead of print hosts", then pick the printer in the Device tab and sync
the filaments. Without that option OrcaSlicer uploads as before and ignores
`lane_data`.

`filament_id` names the filament profile OrcaSlicer picks for the slot.
For the IFS types it is the id of Kiln's own filament profile (the
[kiln-orca profiles](#kiln-profiles-for-orcaslicer), from the release after
kiln-orca v1.1.1 on; import that zip again if you imported an older one):

| Slot type | `filament_id` | Profile |
|---|---|---|
| PLA | `PKLNPLA` | AD5X PLA |
| SILK | `PKLNSLK` | AD5X Silk PLA |
| PLA-CF | `PKLNPCF` | AD5X PLA-CF |
| PETG | `PKLNPET` | AD5X PETG |
| PETG-CF | `PKLNPGC` | AD5X PETG-CF |
| ABS | `PKLNABS` | AD5X ABS |
| TPU | `PKLNTPU` | AD5X TPU |

With Kiln's profiles imported and one of its printers selected (the
filament profiles are made for those), the sync picks them. Without them,
or for a slot with a type you typed yourself (no `filament_id`),
OrcaSlicer matches the slot's `material` against its own system profiles,
as before (a `filament_id` it doesn't have falls back the same way, with a
notice). Imported profiles are never picked by `material` alone, so
without `filament_id` the sync didn't pick Kiln's profiles.

The touch screen (HelixScreen) writes these records too, when a slot is
edited there or a Spoolman spool is linked to it. Its `filament_id` is
the linked spool's own (the Spoolman filament's extra field
`orca_filament_id`, a brand profile), the one of a filament picked from
the screen's list, or null. The two share each record: Kiln changes only
its own fields (`lane`, `material`, `color`, `nozzle_temp`, `bed_temp`,
`filament_id`, `scan_time`) and keeps everything the screen stored (spool,
brand, weight, its `helix_` fields). The screen replaces the whole record
when it writes, so Kiln checks a few seconds after each slot change and
once a minute, and puts its fields back where they are missing or out of
date (a database read; a write only for a record that needs it).

With the afc-kiln plugin (AFC-Klipper-Add-On) installed, AFC writes
`lane_data` itself, as `T0`..`T3` for the same four slots. Kiln then
leaves the namespace to AFC: at each Klipper start it checks for AFC's
`AFC` object, and while it's there Kiln writes nothing and deletes the
`lane1`..`lane4` records it wrote, so OrcaSlicer and Fluidd list each slot
once. A record the touch screen wrote is left as it is.

- **`filament_id`**: the screen's brand id (marked
  `helix_filament_id_source`, or written with a filament from its list,
  `helix_catalog_id`) is kept, so a linked spool's own profile wins over
  Kiln's. It stays when the slot's material changes, as the screen keeps
  it: unlink the spool (or pick another one) when a different filament
  goes in. Otherwise Kiln's id for the type, or none.
- **Filament out**: `material` and `color` become `""`, the temperatures
  0 and Kiln's `filament_id` goes; the spool link (`spool_id`) and the
  screen's fields stay, as the screen and kiln-spoolman keep the link over
  an empty slot. OrcaSlicer shows a slot with an empty `material` as
  empty, whatever its `filament_id`.
- **`bed_temp`**: Kiln has none (0); the screen's stays until the slot's
  material changes or it empties.
- Kiln never sets `writer`: the screen doesn't write a record another
  program signed.

Read it by hand:

    curl http://PRINTER/server/database/item?namespace=lane_data

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
