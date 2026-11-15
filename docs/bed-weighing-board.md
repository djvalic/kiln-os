# Bed weighing board (strain gauges) and the stock Z routine

How the stock AD5X tares its bed strain gauges and sets Z before a print,
recorded by running the stock app (`firmwareExe` 3.1.0) in the sandbox
(`tools/qemu/run_firmwareexe.sh -L -X ttyS7`). Behaviour and values only.
Not yet seen on hardware.

## The board

- Own host UART: **`/dev/ttyS7`, 9600 baud**, 8N1. Not a Klipper MCU and
  not in the stock Klipper config. Its trigger output is presumably the
  probe pin (`[probe] pin: !PB3` on the mainboard).
- The app sends a command followed by `\n`. A reply counts once it is
  **longer than 12 bytes and contains `ok`**; the app waits up to 1 s for
  more bytes and sends the command up to 5 times.
- (On the AD5M the same job is done with Klipper pins `level_h1` and
  `check_level_pin` and a `weightValue` sensor, see the ff5m project. The
  AD5X has none of these in its config.)

| Command | Use in the stock app | Reply |
|---|---|---|
| `H1` | Tare ("clear") the strain gauges | Not parsed beyond the rule above |
| `H7` | Read the gauges | The reading is the **fifth space-separated field**, an integer |
| `H2 S500` | Hidden "WeightAdjust" calibration screen | Unknown |
| `H3 S100`, `H3 S200` | Same screen | Unknown |

Exact reply text from a real board is still unknown; the sandbox runs used
`H1 ok. tare done` and `H7 ok. weight value: <n>`.

## Tare check ("checkLevelPinStatus")

Up to 10 times: send `H1`, then `H7`; done when |reading| < 31. If no try
succeeds the app cancels the print (bed mesh dropped, heaters and fan off,
motors off) and shows **"Leveling sensor cannot be cleared. Please check
the sensor."** With no board answering, the reading parses as 0 and the
check passes.

It runs right before every probing step: before each `PROBE_CALIBRATE` used
to measure Z, and before `BED_MESH_CALIBRATE`.

## Z routine before every print ("checkZ")

Z homes to its max endstop and keeps that zero. Each print then:

1. Home Z, X, Y. To the purge box, bed and nozzle to print temperature,
   purge 90 mm, retract 3 mm, wipe. Nozzle to 180, then brush it twice
   across the box (X65 to X78 at Y229).
2. `Z5`, move to **X60 Y-3** (front edge). Tare check, then
   `PROBE_CALIBRATE` followed at once by `ABORT`: the app only wants the
   `probe at X,Y is z=Z` line. Call it z1.
3. Part fan full, then **scrub the nozzle on the front edge**: `Z = z1 + 0.3`,
   X130 then X150 at F1200, `Z = z1 + 0.1`, nozzle to 140, 2 s, fan off,
   `Z5`.
4. Move to **X107.5 Y107.5** (bed centre). Tare check, probe again: z2.
5. diff = z2 minus the centre Z saved when the bed was last levelled
   (or, on a unit's first check, the centre point of the saved mesh
   minus 0.25). If **-0.5 <= diff <= 2.0**, `SET_GCODE_OFFSET Z=<diff>
   MOVE=1`; otherwise no offset, silently. Then `BED_MESH_PROFILE
   LOAD=MESH_DATA`, `Z50`, heat back to print temperature.

With "level before print" on, steps 2 and 3 run, then `BED_MESH_CALIBRATE`
(after its own tare check), `BED_MESH_OUTPUT`, `BED_MESH_PROFILE
LOAD=default`.

Either way the print then starts with `SET_GCODE_OFFSET Z=<zProbeOffset>
MOVE=1`: the per-unit Z offset tuned on the screen (0.025 on the
developer's printer). Klipper's `Z=` is absolute, so this replaces the drift offset from
step 5 a few seconds after it was set (both appear in the stock app's
log in the sandbox, drift first). On stock the drift therefore has no
effect on the print; `_CHECK_Z_APPLY` does the same unless
`apply_drift` is set.

## Open stack

- `klipper/extras/ad5x_weight.py`: `[ad5x_weight]` on `/dev/ttyS7`, with
  `WEIGHT_TARE` (stock's tare check: 10 tries, |reading| < 31, same error
  text), `WEIGHT_READ` and `WEIGHT_SEND CMD=...`. Tests:
  `tools/test_ad5x_weight.py`.
- `klipper/ad5x.cfg`: `BED_MESH_CALIBRATE` tares first, then probes the
  bed centre and saves it (`ad5x_center_z`). `_CHECK_Z` does steps 2 to 5.
  Differences are in `docs/deviations-from-stock.md`.

## To confirm on hardware

- ~~The board's real reply text~~: read on the developer's printer (USB test
  mode, 2026-10-15, `tools/probe_boards.py`): `H7` →
  `command H7 ok. 8596371 60 g \r\n`, three reads within 1 raw count
  of each other. Fields: raw ADC count, then grams; the fifth field (what
  stock and `ad5x_weight` read) is the grams. 60 g untared, nothing on the
  bed. Nothing was sent to the board unasked: no reply before `H7`.
- That `H1` really tares and the probe pin triggers on contact after it.
- What `H2 S500`, `H3 S100` and `H3 S200` calibrate (likely a known
  weight in grams); don't send them until known.
- Whether Y-3 is on the bed's edge or past it (where the scrub happens).
