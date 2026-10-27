# Print start

`PRINT_START` follows the order the stock app uses before every print,
recorded in the sandbox (`tools/qemu/run_firmwareexe.sh`, runs with and
without "level before print"). Values only, no vendor code. Two versions
(`docs/config-layout.md`): the factory one in `klipper/ad5x.cfg` (read-only
image) does exactly the stock steps; the printer's editable
`macros/print_start.cfg` (template `klipper/macros/print_start.cfg`),
read after it, replaces it with this system's start: a mesh of the print
area every print, a status line per step, a quick purge instead of a
reload when the first tool is already in, a prime line otherwise.

## Slicer start G-code

```
IFS_SET_COLOR CHANNEL=1 COLOR="{filament_colour[0]}"   ; one per used slot, optional
; or IFS_SET_MATERIAL SLOT=1 TYPE=PLA COLOR=FF0000 (bare hex)
PRINT_START BED=[bed_temperature_initial_layer_single] EXTRUDER=[nozzle_temperature_initial_layer] TOOL=[initial_tool]
```

| Parameter | Default | Meaning |
|---|---|---|
| `BED` | 60 | Bed temperature |
| `EXTRUDER` | 220 | Nozzle temperature |
| `TOOL` | -1 | First slicer tool; loads IFS channel `tool_map[TOOL]` (`TOOL+1` unless `IFS_MAP_TOOL` changed it). -1 or no IFS: skipped |
| `LEVEL` | `mesh_every_print` (1; factory: 0) | 1 = new bed mesh instead of the centre Z check, 0 = the stock check |
| `SOAK` | the calibrated settle time of the nearest calibrated bed temperature, scaled by how far the bed rose (a hotter target never gets less than the calibration), else `soak_per_degree` 3 s per °C it rose; at most `soak_max` 600 s; 0 when the bed was within 5 °C of `BED` already | Bed heat soak in seconds before the Z check / mesh, counted from when the bed reached `BED` (the purge and brushing count). Set it when the slicer heats the bed (`M190`) before `PRINT_START` |
| `ADAPTIVE` | `adaptive_mesh` (1; factory: 0) | 1 = the mesh covers only the print area (slicer object labels; whole bed without them). Not saved as a profile: the full `default` mesh stays |

## Steps (stock order)

1. Heaters and part fan off, absolute positioning and extrusion, mesh and
   Z offset cleared (`_SET_GCODE_OFFSET Z=0`: not saved). Home Z, X, Y.
2. To the purge box (X52.5, Y220 then Y229). Bed to `BED`, `Z5`, nozzle to
   `EXTRUDER`, wait for both.
3. Purge 90 mm at F300 with the fan off, fan S125 for 3 s, retract 3 mm,
   wipe (Y220/Y229 twice, end at Y220).
4. Nozzle to 180, brush twice across the box (X65 to X78 at Y229).
   Then the rest of the bed heat soak, if any ("Bed heat soak m:ss"): the
   plate's surface keeps warming and growing after the sensor reads the
   target, which would shift the Z check (e.g. a cold start to 80 °C:
   180 s from reaching it, about 2 minutes of which the purge and
   brushing already took).
5. `_CHECK_Z` (see `docs/bed-weighing-board.md`): tare and probe the front
   edge, scrub the nozzle there while it cools to 140 (screen: "Cleaning
   nozzle on the bed edge"; it runs just above the edge, it isn't
   printing), then either run `BED_MESH_CALIBRATE ADAPTIVE=1` ("Meshing
   print area", `LEVEL=1`, the `macros/` default) or tare, probe the
   centre and set the Z offset from the drift ("Checking Z", `LEVEL=0`,
   the stock default). Loads the mesh. The Z offset is then
   the saved one (`zoffset` in `variables.cfg`, written by every
   `SET_GCODE_OFFSET Z=`/`Z_ADJUST=`; seeded at first start from `unit.cfg`
   `z_offset` = stock `zProbeOffset`), as stock sends its tuned offset at
   print start; the measured drift is reported, not applied.
6. `Z50`, back to print temperatures, wait.
7. With `TOOL` ("Loading first colour"): load the first tool's channel
   (through the tool map) with `IFS_SWAP` (from an empty toolhead that is
   one purge round, as stock). The factory start always loads it fresh
   (`FORCE=1`, as stock); `macros/print_start.cfg` purges 90 mm once at the
   box instead when that channel is already loaded.

Without a tool load `macros/print_start.cfg` draws the prime line
(`_PRIME_LINE`, `macros/prime_line.cfg`, "Prime line"): back to the
plate's front, put the 3 mm retract back, prime 8 mm in place (a small
puddle that anchors the line), a 60 mm line 5 mm in front of the objects
at Z 0.3, 2.5 x the nozzle wide (1.5 mm on a 0.6 nozzle, about 11 mm of
filament at 10 mm/s), then a 10 mm wipe, 0.5 mm retract and lift. Beside
the objects when they reach the plate's front edge; skipped with a
message when there is no room. The old line (3 mm before, 6 mm over
60 mm at 20 mm/s) only undid the retract and didn't stick. The factory
start has no prime line (stock).

Screen status line (`M117`, also in the console) for each step: Homing,
Heating, Purging at the box, Checking Z, Cleaning nozzle on the bed edge,
Meshing print area / Meshing the bed / Checking Z, Heating, Loading first
colour or Prime line; cleared at the end.

The print file follows. Slicer end G-code: `PRINT_END` (retract 2 mm, lift 10 mm, park at X107.5 Y215, heaters, fans and X/Y/E motors off). `CANCEL_PRINT` does the same after stopping the file. Stock's swap at the first `T<n>` and the end of the
print are not part of this macro.

## Nozzle size

The factory config is for the 0.4 mm nozzle most AD5X have. After
fitting a different nozzle, the whole setup is not needed: the hotend
PID (`SETUP_WIZARD_STEP STEP=pid HEATERS=extruder`) and the first-layer
Z offset test are worth redoing (the touch screen offers both after a
change in Settings); the bed PID, mesh, input shaper and IFS tuning stay
valid. Another size
is set with `SET_NOZZLE_SIZE SIZE=0.6` (0.2, 0.25, 0.4, 0.6, 0.8, 1.0),
the setup wizard's Nozzle Size step or Settings > Nozzle Size on the touch
screen: it writes the printer's `nozzle.cfg` and restarts Klipper. The
prime line width (2.5 x the nozzle), the IFS purge lengths (nozzle / 0.4),
the setup wizard's first-layer test and Klipper's extrusion limits follow
it. A bigger nozzle can also flush faster at colour changes:
`[ifs] flush_speed` in `local.cfg` (stock 300 mm/min).

## Bed heat soak (`klipper/extras/ad5x_soak.py`)

The bed sensor reaches its target minutes before the plate's surface
stops warming and growing; a Z check made at once is off by what is still
to come. `BED_SOAK_CALIBRATE BED=80` measures it on this printer: from a
cold bed (below 40 °C), nozzle at 140 °C and held there 5 minutes
first (`NOZZLE_SOAK=`: the hotend keeps growing after its sensor reads
the target, which would count as bed movement), it probes the centre and
four points 30 mm in from the corners every 60 s, prints each round, and
stops when every point's 3-round average has stayed within 0.02 mm for 4
minutes (at most 25 minutes). The load cells scatter about 0.03 mm between
touches, hence the averaging and the 0.02 mm band. It saves per
temperature the centre's settle time (`PRINT_START` checks Z there), the
slowest corner's, the centre's total change and the shape change (corners
against the centre) in the save variable `ad5x_bed_soak`
(`printer.ad5x_soak.calibration`). Run it once per bed temperature you use
(60, 80, 100). `PRINT_START` then soaks the centre's settle time after the
bed is hot, minus the purge and brushing time.

Measured (2026-10-20, 60 °C from 17 °C): the centre moved 0.16 mm and was
within 0.02 mm of its final level after 5 minutes; the corners moved
0.06-0.12 mm, the front-right one crept about 0.03 mm more until 13
minutes. Saved soak: 300 s. At 80 °C (from 21 °C) the centre moved only
0.03-0.07 mm, within the probe's scatter (saved 540 s, capped to 300 s).
The difference was mostly the hotend: the 60 °C bed reached its
temperature 2 minutes after the nozzle, the 80 °C one 4; hence
`NOZZLE_SOAK`. Re-run at 60 °C with the nozzle held 5 minutes first (bed
from 34 °C): the centre moved 0.09 mm (0.07 mm in the first 7 minutes,
then about 0.005 mm a minute, the frame warming), the corners up to
0.04 mm less; settled within 0.02 mm after 420 s. Saved: 420 s for 60 and
80 °C.

A running calibration is stopped through the API (it holds the G-code
queue, so a G-code can't): `POST /printer/ad5x_soak/abort` (Moonraker
JSON-RPC `printer.ad5x_soak.abort`; the touch screen's Stop): heaters
off, nothing saved. On the touch screen: Settings > Bed Heat Soak (on/off,
the calibrated times, Calibrate with progress).

On or off for every print: `BED_SOAK_ENABLE ENABLE=0` / `ENABLE=1`
(saved; a calibration stays saved either way; `BED_SOAK_ENABLE` alone
says which it is). `PRINT_START SOAK=` in a file still sets that print's
soak.

`soak_mode: "probe"` in `macros/print_start.cfg` instead probes until two
readings 60 s apart agree within 0.005 mm (`soak_points` 1 or 5), at most
the soak time. With the load cells' 0.03 mm scatter two readings rarely
agree that closely, so in practice it waits the whole soak time with extra
probing: the calibrated time (the default) is the better choice.

## Not in the macro

- Stock reads the temperatures from the print file's own `M104`/`M109`
  lines; here the slicer passes them.
- Stock sets `SET_IDLE_TIMEOUT TIMEOUT=864000` during the start and
  switches the board fan on (`SET_FAN_SPEED FAN=pcb_fan SPEED=1`); here
  `[pcb_fan_watch]` (a reactor timer, so a long macro can't hold it off;
  issue #17) and the configured idle timeout handle both.
- Stock pre-feeds every newly inserted spool at power-on (`F24`, `F10 L600`
  stopped by `F112`, `F23`, `F39`; `F11 L100` back off when the strand
  reached the toolhead). Here the IFS module does it on its own
  (`prefeed_on_insert` in `ifs.cfg`), not this macro.

## Tested

Klipper's test mode with the simulated IFS and weighing board on ptys:
default path (offset applied from the saved centre, mesh loaded, channel 2
loaded with the same IFS commands stock sends), `LEVEL=1` with the tool
already loaded (three tares, centre saved, no reload), and no `TOOL`.
In test mode the probe triggers at the bottom of travel and the toolhead
sensor reads 0, so the sensor was off for these runs. Also (2026-10-15):
saved Z offset applied on both paths (seeded 0.025 from `unit.cfg`, then
the value from `SET_GCODE_OFFSET Z=` / `Z_ADJUST=`), and `TOOL=1` loading
channel 3 after `IFS_MAP_TOOL TOOL=1 SLOT=3`. Not run on hardware.
