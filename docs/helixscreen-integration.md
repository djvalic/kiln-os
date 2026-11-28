# HelixScreen integration

What HelixScreen (touch UI, github.com/prestonbrown/helixscreen) needs from
Klipper/Moonraker to run on an AD5X with an IFS, and how we close the gap.
Section 0 is what is implemented (option (a2) below); sections 1-4 are the
research it is based on, describing our stack before the change. Kiln OS
now runs HelixScreen v1.2.0-alpha.1 with its patches on every printer; the
sections below keep the state of the day they were written.

Sources (read 2026-10-15):

| Tag | Source | Revision |
|---|---|---|
| `H` | HelixScreen, a local clone | `6f502ac` |
| `ZA` | zMod AD5X tree, github.com/ghzserg/z_ad5x | `04902da` |
| `LW` | lessWaste plugin, github.com/Hrybmo/lesswaste | `3d42421` |
| `FX` | Preston Brown's "standalone IFS module" (Forge-X AD5X port), github.com/prestonbrown/ff5m branch `feat/ad5x-support` | `422a4ce` |

`H` paths are relative to the HelixScreen root. URLs for `ZA` are
`https://github.com/ghzserg/z_ad5x/blob/04902daf41075df1a33040715fb9b80e5e997e7c/<path>`,
for `FX` `https://github.com/prestonbrown/ff5m/blob/422a4ce36d8d6f76d1f89d2538a86f4bd931be4a/<path>`,
for `LW` `https://github.com/Hrybmo/lesswaste/blob/3d42421a6ed020baaa7563c94a56ad76ead2a799/<path>`.

## Our patches

`buildroot/package/helixscreen/*.patch` on HelixScreen v1.2.0-alpha.1: 101
files, `0001` to `0111` (the missing numbers were dropped because upstream
has them, or with the move to 1.2: 0061, the Z offset arrows, whose buttons
1.2 names for what moves, and 0073, a test fix 1.2 has). `docs/setup-wizard.md` ("HelixScreen side") lists `0001` to
`0019` with what each does: among them the AD5X setup steps (0001, 0002,
0003, 0006 time zone), the IFS port sensors (0004), Settings > Plugins
(0005, `docs/plugins.md`) and the speaker with Settings > Sound > Printer
Sounds (0007, `docs/sound.md`). The later ones are listed in
`docs/deviations-from-stock.md` (row "HelixScreen source").

## 0. Implemented (2026-10-15)

Our `ifs` module speaks the `FX` "module" contract; HelixScreen latches
its module dialect on the first `ifs` frame (`loaded_channels`/`activity`/
`tool_map` are always present). Checked against `H` `6f502ac` and `FX`
`422a4ce`; tested in `tools/test_ifs.py` (fake IFS) and a Klipper batch run
of the real configs. Not run against HelixScreen itself.

| Contract item | Ours |
|---|---|
| `ifs.loaded_channels` | F13 `silk_state` mask -> 1-based list (`[]` before the first poll). IFS on Klipper firmware: from its inlet sensors, read every `presence_interval` (0.25 s), also during an operation |
| `ifs.active_channel` | F13 `chan` (int; `null` before the first poll). IFS on Klipper firmware: the slot the selector was last moved to, the loaded slot (`channel`) until the selector has homed (after start or a reset) |
| `ifs.activity`, `activity_channel` | `FFS_state` decoded with `FX`'s table (3 polling, 5 ready, 7/11/12/15 + 11·(ch−1), 127 `driver_error`) plus ours: 1 `selecting`, 10/14 + 11·(ch−1) `loading`/`unloading` (the values F10/F11 set), 0x7e `homing`; else `unknown(n)`. While an operation runs and F13 reads `ready` (between the IFS's own moves; on Klipper firmware always), the step the module runs: `homing` (selector homing, channel 0), `selecting`, `loading` (load, pre-feed, refill, tuning feed, push, purge), `unloading` (cut, retract, eject), with the slot it moves (a swap: the old slot while unloading, the new one from its select on). `driver_error` (channel = `error_channel`) after an operation failed with a motor, homing or feed fault, until `IFS_RESET`/`IFS_RESET_DRIVER` or the next successful command |
| `ifs.error` | Text of the last failed operation or of a failed connect, `null` after a success or `IFS_RESET_DRIVER` |
| `ifs.mode` (ours) | `"mcu"` (IFS on Klipper firmware) or `"serial"` (stock firmware over the serial link) |
| `ifs.operation`, `phase`, `target_channel` (ours) | While a command runs: `operation` `load` (empty nozzle) / `swap` (a slot in it) / `unload` / `eject` / `prefeed` / `refill` (auto-refill's pre-feed and swap) / `tune` / `select` (also `IFS_RELEASE`) / `feed` / `retract`; `phase` `heating` (waiting for the nozzle) / `cutting` / `unloading` / `homing` (the IFS selector) / `selecting` / `feeding` / `purging` / `priming` / `homing_printer` (G28 first, `HOME=1`), as the steps run (the swap templates included); `target_channel` the slot loaded, or taken out for unload/eject. Idle: `""`, `""`, 0 |
| `ifs.error_channel` (ours) | Slot the last error concerns (the slot the failed step moved, else the operation's target), 0 none or unknown |
| `ifs.tune` (ours) | `speed`, `load_dist` (`"1"`-`"4"`), `unload_dist`, `tube_unload`, `flush` (tuned value or `null`), `running`, `progress`, `message` |
| `ifs.tool_map` | `{"0": 1, ...}`; per print, reset when `print_stats` leaves `printing` for complete/cancelled/error/standby (as `FX`) |
| `ifs.channel_count`, `pending_insert_channels` | 4; F13 `ffs_channels_insert` decoded |
| `ifs_materials.slots` | `{"1": {"type", "color": "#RRGGBB", "temp"}}`, also `loaded`, `temperatures`, `available`, `channel_count`. Stored in save variable `ifs_materials` (migrated from `ifs_colors`). `temp` = per-slot override, else `FX`'s handling table (PLA 220, PETG 250, ...; `temp_<type>` in `[ifs]`) |
| save variable `ifs_loaded` | Written by every load/unload/`IFS_SET_CHANNEL` (replaces `ifs_channel`, which is still read once if `ifs_loaded` is absent) |
| `filament_switch_sensor toolhead` | `[adc_filament_sensor toolhead]` (renamed from `head`) also registers itself under that name: same object, same status, `SET_FILAMENT_SENSOR SENSOR=toolhead` |
| `IFS_LOAD SLOT=n [TEMP=]` | `IFS_SWAP CHANNEL=n`: cut and unload the loaded lane, load, purge (stock-recorded sequence) |
| `IFS_UNLOAD [SLOT=n] [TEMP=]` | Cut, unload, pull back 70 mm, `F39`; `SLOT` defaults to `ifs_loaded`; refused if it names a lane other than the loaded one, and while `printer.ifs.tube_blocked` (a strand left in the tube) |
| `IFS_EJECT SLOT=n` | Idle lane: `F24`, `F11 L1000 S1200` (until the IFS is ready), `F39`, no heat, no toolhead moves. Loaded lane: `IFS_UNLOAD` first. Refused when the toolhead holds filament of an unknown lane |
| `T0`-`T3` | `IFS_SWAP CHANNEL={tool_map[n]}`; `PRINT_START TOOL=` goes through the map too |
| `IFS_MAP_TOOL TOOL= SLOT=` / `RESET=1` | As `FX`: refused without a reading or for a lane without filament |
| `IFS_SET_MATERIAL SLOT= TYPE= COLOR= [TEMP=] [SPOOL_ID=] [VENDOR=] [NAME=] [FILAMENT_ID=] [BED_TEMP=]` | As `FX`: absent = keep, empty = clear, bare or `#` hex, `RGB` or `RRGGBB`. The spool's details (not `FX`'s; plugin API 1.12, issue #101) go into `lane_data` through kiln_lanes. `IFS_SET_COLOR CHANNEL= COLOR=` kept (slicer start G-code) |
| `IFS_STOP` | `F112`; during a background pre-feed it ends the pre-feed (F15) |
| `IFS_RESET_DRIVER` | `F15` (= `IFS_RESET`), clears `error` |
| Heat | `IFS_LOAD`/`IFS_UNLOAD`/`IFS_EJECT`/`IFS_SWAP`/`T<n>`: with `TEMP=` that; otherwise only when the nozzle target is below `min_extrude_temp` (idle): hottest slot material involved, else `default_temp` 220. Old target restored afterwards |
| Homing | Load/unload/eject of the loaded lane, `IFS_FIND_HEAD_SLOT` and the tuning's unload refuse with "home the printer first (G28)" instead of failing mid-move. With `HOME=1` an idle printer homes first instead, inside the operation (`phase` `homing_printer`, a line "IFS: homing first (G28)"); during a print or a pause never, the error then says so. HelixScreen's module-mode load, unload, eject and tune send `HOME=1` (patch 0087), and so does `UNLOAD_FILAMENT`; typed in the console without it, nothing moves that the command didn't ask for |
| Renamed | Our raw `IFS_LOAD CHANNEL=` -> `IFS_FEED`, `IFS_UNLOAD CHANNEL=` -> `IFS_RETRACT` (`FX` names) |
| Z offset | `SET_GCODE_OFFSET` wrapper saves `zoffset = {'z': ..}` (Helper-Script provider, section 4); first start seeds it from `unit.cfg` `z_offset`; `PRINT_START` applies it (`_APPLY_Z_OFFSET`); internal resets use `_SET_GCODE_OFFSET` |
| `LOAD_CELL_TARE` | Macro -> `WEIGHT_TARE` |
| Screws Tilt screen (issue #69) | Shown once `[screws_tilt_adjust]` is in the config (`ad5x.cfg`; `H src/printer/printer_discovery_parse.cpp:865`). It homes every run, sends `LOAD_CELL_TARE` (database rule `zmod_load_cell_tare`), then `SCREWS_TILT_CALCULATE` (the default of the Screws Tilt macro slot, `H src/printer/standard_macros.cpp:78`), which on Kiln tares again over the front-left screw, makes one touch there that isn't counted, tares, and probes the four screws; no heating. `BED_LEVEL_SCREWS_TUNE` (heats first, `macros/quick_actions.cfg`) can be picked for that slot in HelixScreen's settings |

Not matched / open:

- **Cancel cannot interrupt.** `IFS_STOP` (and `IFS_RESET_DRIVER`) are G-code
  commands, queued behind a running `IFS_LOAD`/`IFS_UNLOAD`; they only reach a
  background pre-feed. Same limit for `FX`'s macros.
- **Heat policy differs from `FX`**: `FX` heats to the slot material
  even when a target is set; ours keeps a set target (mid-print `T<n>` must
  not change the print temperature).
- `IFS_SELECT` is still ours (point the switch at a lane, no load); `FX`'s
  `IFS_SELECT SLOT=` is a load with save/restore. HelixScreen doesn't send it.
- No `moving_channels` (`FX` reads F13 `stall_state` as a motion mask; we
  have not confirmed that), no `ifs_at_hub`, no `params`, no `probed`.
- Eject waits for the IFS to finish the full 1000 mm (`FX` stops early
  when the motion bit goes quiet). Length unmeasured on our printer.
- `IFS_UNLOAD` releases the lane (`F39`, as `FX`); stock's swap does not
  release the old lane before selecting the next.
- Preset defaults (`fan_generic fanM106`, `LOAD_FILAMENT`, ... in
  `H assets/config/presets/ad5x.json`): the fan is stock's name again and
  the quick-action macros are in the printer's `macros/quick_actions.cfg`
  (`docs/config-layout.md`).
- The Z calibration panel's `G1 Z0.1` does not probe; the saved offset is
  whatever it sends.

## Key finding

HelixScreen's AD5X backend (`AmsBackendAd5xIfs`) speaks **two** firmware
dialects, not one (`H include/ams_backend_ad5x_ifs.h:44-60`,
`H docs/devel/FILAMENT_BACKEND_AD5X_IFS.md:25-68`):

1. **zMod**: `zmod_ifs` / `zmod_color` objects, `Adventurer5M.json`,
   `GET_ZCOLOR` / `IFS_STATUS` text scraping, `INSERT_PRUTOK_IFS` macro
   family, optionally the lessWaste/bambufy `_IFS_VARS` plugin.
2. **"Standalone IFS module"** (`FX`, the HelixScreen author's own GPLv3
   Klipper module for the AD5X IFS): a Klipper object literally named
   **`ifs`**, plus `ifs_materials`, save variable `ifs_loaded`, and
   `IFS_LOAD SLOT=` / `IFS_UNLOAD` / `IFS_EJECT` / `IFS_SET_MATERIAL` /
   `IFS_MAP_TOOL` / `T0`-`T3`.

Our `klipper/extras/ifs.py` also registers an object named `ifs`. HelixScreen
therefore already treats our printer as an AD5X IFS, but our `ifs` status
carries none of the fields that switch it into the module dialect, so it
falls back to the zMod dialect, none of whose commands exist on our side.

## 1. What HelixScreen needs

### 1a. Printer objects it subscribes to

`required_status_objects()` (`H src/printer/ams_backend_ad5x_ifs.cpp:218-236`)
subscribes `save_variables` always, plus whichever of `ifs`,
`ifs_materials`, `zmod_ifs`, `zmod_color`, `gcode_macro END_CHANGE_FILAMENT`
appear in `objects/list`. The start-up `objects.query`
(`:286-338`) also asks for the sensors below, `extruder`
(`target`, `temperature`, drives the load/unload phase tracker) and
`webhooks`.

| Object | Dialect | Fields read | Meaning (source) |
|---|---|---|---|
| `ifs` | module | `loaded_channels` (int[], 1-based), `active_channel` (int), `activity` (`polling`/`ready`/`clamped`/`loading`/`unclamping`/`unloading`/`driver_error`), `error` (str), `tool_map` (`{"0":1,..}` string tool keys, 1-based lane values) | `H ams_backend_ad5x_ifs.cpp:5044-5170`, `:1022-1060`. Producer: `FX .py/klipper/plugins/ifs.py:555-594` (also `connected`, `channel_count`, `version`, `probed`, `state`, `activity_channel`, `moving_channels`, `pending_insert_channels`, `params`) |
| `ifs` (Kiln OS, our patches 0037-0039) | module | `operation`, `phase`, `target_channel`, `activity_channel` (action, steps, detail line, pulsing and header slot of an operation the driver runs); `auto_refill`, `refill_match`, `refill_backups` (Endless Spool, runout pop-up wait); `map_mode`, `version`, `tune` (device operations) | Producer: `klipper/extras/ifs.py` `get_status()`. Each is optional: without it the screen behaves as upstream |
| `ifs_materials` | module | `slots` = `{"1": {"type": "PLA", "color": "#RRGGBB" or "#RGB", "temp": 220}, ...}` | `H :5001-5040`. Producer: `FX ifs_materials.py:206-234` (also `available`, `enabled`, `loaded`, `purge_first_mm`, `temperatures`) |
| `save_variables` | module | `ifs_loaded` (int, 1-based, 0 = none): lane in the nozzle, written at the end of a successful `IFS_LOAD`/`IFS_UNLOAD` | `H :938-960`; `FX macros/ifs.cfg:609,791` |
| `filament_switch_sensor toolhead` | module | `filament_detected` | Head-presence authority (`H :334-336`); `FX` registers it as `[ifs_toolhead_sensor toolhead]` |
| `zmod_ifs` | zMod | `Chan` (seated lane, 1-based), `Ports` (bool[4], per-lane presence) | `H :4859-4889`. Producer `ZA .shell/zmod_ifs.py:191-201`: `available`, `color_limit` + `ifs_data.get_values()` (`:1416-1428`: `RawData`, `State`, `Ports`, `Silk`, `Chan`, `Insert`, `NeedInsert`, `Stall`, `stall_state`) |
| `zmod_color` | zMod | `ifs` (bool), `channel`, `slots[] {ID, Material, Color, HEX, hasFilament}` | `H :4891-4930`. Producer `ZA .shell/zmod_color.py:663-697` (reads `Adventurer5M.json` FFMInfo, mtime-cached) |
| `gcode_macro END_CHANGE_FILAMENT` | zMod | `last_data.channel` (99 = idle) | `H :206-209`; `ZA translate/en/ad5x_display_off.cfg:104` |
| `filament_switch_sensor head_switch_sensor`, `filament_motion_sensor ifs_motion_sensor`, `zmod_ifs_switch_sensor head_switch_sensor`, `zmod_ifs_motion_sensor ifs_motion_sensor` | zMod | `filament_detected` | Toolhead switch / post-hub motion (`H :297-309`) |
| `filament_switch_sensor _ifs_port_sensor_{1-4}`, `gcode_macro _ifs_vars` | lessWaste/bambufy | per-lane presence; plugin existence latch | `H :293-296` |
| `save_variables` `<less_waste or bambufy>_colors/_types/_tools/_current_tool/_external` | lessWaste/bambufy | slot colours/types, 16-entry tool->port map, bypass | `H :777-` (`parse_save_variables`); `LW lesswaste.cfg:940` (`_IFS_VARS`) |

The module dialect latches (`ifs_module_live_`) on the first status frame in
which `ifs` carries `loaded_channels`, `active_channel`, `activity` or `error`
(with patches 0037-0039 also one of the Kiln fields above),
or `ifs_materials` carries a parsable `slots` entry (`H :5045-5115`). An `ifs`
object with other fields only does **not** latch it. Once latched, every zMod
poll and command stands down (`H :4684-4690`, `:4739`).

### 1b. Commands it sends

| Action | Module dialect | zMod dialect |
|---|---|---|
| Load lane n | `IFS_LOAD SLOT=n` (`H :1932-1938`) | `INSERT_PRUTOK_IFS PRUTOK=n` (`H :1940`) |
| Unload toolhead | `IFS_UNLOAD [SLOT=n]` (`H :2122-2133`) | `_IFS_REMOVE_CURRENT_PRUTOK` (`H :2135`) |
| Select lane, no load | refused (`H :2240-2245`) | `SET_EXTRUDER_SLOT SLOT=n` (`H :2248`) |
| Tool change | `T<n>` after `G28` if unhomed (`H :2288-2293`) | `A_CHANGE_FILAMENT CHANNEL=n` (`H :2306`) |
| Eject lane (cold) | `IFS_EJECT SLOT=n` (`H :2365-2372`) | `IFS_F24 PRUTOK=n`, `IFS_F11 PRUTOK=n LEN= SPEED= CHECK=0`, `IFS_F39 PRUTOK=n` (`H :2385-2394`) |
| Recover / reset | `IFS_RESET_DRIVER` | `IFS_UNLOCK` (`H :2458`, `:2482`, `:2583`) |
| Cancel | `IFS_STOP` | `IFS_UNLOCK` (`H :2561`) |
| Edit slot colour/material | `IFS_SET_MATERIAL SLOT=n TYPE=PLA COLOR=7EC8E3` (bare hex) (`H :3056-3067`) | read-modify-write of `Adventurer5M.json` (`H :3083-3090`), plus `_IFS_VARS colors=[..]` / `types=[..]` with a plugin (`H :3510-3513`) |
| Tool remap | `IFS_MAP_TOOL TOOL=t SLOT=n`, `IFS_MAP_TOOL RESET=1` (`H :3309`, `:3347`) | `_IFS_VARS tools=[16 ints]` (plugin only) |
| Endless Spool on/off (Kiln, 0038) | `IFS_AUTO_REFILL ENABLE=0\|1` | none |
| Device operations (Kiln, 0039) | `IFS_AUTO_REFILL MATCH=exact\|similar\|any`, `IFS_MAP_MODE MODE=fixed\|loaded`, `IFS_TUNE`, `IFS_PREFEED CHANNEL=n` | none |
| State refresh | none | `IFS_STATUS` (expects one JSON line with `Chan`, `Ports`) then `GET_ZCOLOR SILENT=1` (`// ` text lines) (`H :4776`, `:4801`) |

Material names are limited to the zMod whitelist `PLA, PLA-CF, SILK, TPU, ABS,
PETG, PETG-CF` (`H include/ams_backend_ad5x_ifs.h:178`).

zMod semantics of those commands (`ZA`):

- `INSERT_PRUTOK_IFS PRUTOK=n`: resolves the lane's material temperature and
  feed parameters, calls `_INSERT_PRUTOK_IFS` = `_G28` (home only if
  unhomed), heat, unload current lane if any, feed, purge to trash, wipe
  (`.shell/zmod_ifs.py:752-791`, `translate/en/ad5x_display_off.cfg:386`).
- `_IFS_REMOVE_CURRENT_PRUTOK`: `_G28`, `IFS_REMOVE_CURRENT_PRUTOK NEED_TRASH=1
  BYPASS_TEMPERATURE_CHECK=1` (heat to the lane's temperature, cut, retract into
  the tube), heater off (`ad5x_display_off.cfg:614`; `zmod_ifs.py:1172`).
- `SET_EXTRUDER_SLOT SLOT=n` -> `_SET_EXTRUDER_SLOT`, points the IFS at a port
  (`translate/en/ad5x_generic.cfg:74`; `zmod_color.py:593`).
- `IFS_UNLOCK` = `IFS_F18` (release all lanes) (`ad5x_display_off.cfg:610`).
- `IFS_STATUS` prints `json.dumps(ifs_data.get_values())` (`zmod_ifs.py:1120-1122`).
- `A_CHANGE_FILAMENT` is not in the zMod tree; it comes from the stock
  Flashforge config (`H :2294-2305` comment). zMod ships `_A_CHANGE_FILAMENT`
  (`ad5x_generic.cfg:584`).
- `_IFS_VARS key=value` is lessWaste/bambufy, not zMod: a `gcode_macro` holding
  `tools`, `colors`, `types`, `backup`, ... and mirroring them to
  `save_variables` (`LW lesswaste.cfg:940`).

`FX` semantics (`macros/ifs.cfg`, `docs/IFS_MODULE.md`):

- `IFS_LOAD SLOT=n` (`:614`): full tool change: heat from the slot's material,
  unload the outgoing lane itself, select, feed to the toolhead sensor, purge,
  wipe, record `ifs_loaded`.
- `IFS_UNLOAD [SLOT=n]` (`:567`): nozzle contents back into the lane (cut,
  retract), lane left threaded; `SLOT` defaults to `ifs_loaded`; clears
  `ifs_loaded`/`ifs_at_hub`.
- `IFS_EJECT SLOT=n` (`:831`): retract the lane out of the machine.
- `T0`-`T3` (`:810-829`) -> `IFS_SELECT SLOT=tool_map[n]` (`:953`), which wraps
  `IFS_LOAD` with mid-print state save/restore.
- `IFS_SET_MATERIAL SLOT= TYPE= COLOR=` (`ifs_materials.py:261`): absent = keep,
  empty = clear; stores in `Adventurer5M.json` when present, else its own file.
- `IFS_MAP_TOOL TOOL= SLOT=` / `RESET=1` (`ifs.py:247`): per-print map, refused
  for an empty lane, cleared at print end.
- `IFS_STOP` (stop feeding), `IFS_RESET_DRIVER` (F15) (`ifs.py:263-282`).

### 1c. Files

`Adventurer5M.json` (stock settings file; `FFMInfo.ffmColor1-4`,
`ffmType1-4`, `channel`). zMod dialect only.

- Read: Moonraker file API, root `config`, path `Adventurer5M.json`
  (= `~/printer_data/config/Adventurer5M.json`), every 5 s idle / 30 s printing
  (`H :4030`, `include/ams_backend_ad5x_ifs.h:158`). A 404 disables the poll
  for the session (`H :3999-4005`).
- Write: same root via upload, or directly to `/usr/prog/config/Adventurer5M.json`
  or `/opt/config/Adventurer5M.json` when HelixScreen runs on the printer and
  the file exists and is writable (`H :3668-3700`).

### 1d. save_variables keys

| Key | Who | Notes |
|---|---|---|
| `ifs_loaded` | module | int 1-based, 0 = none |
| `ifs_at_hub` | module (macros only; mock publishes it) | lane parked at the hub |
| `less_waste_*` / `bambufy_*` (`colors`, `types`, `tools`, `current_tool`, `external`) | plugin | only read after `gcode_macro _ifs_vars` exists |
| `gcode_offsets` (`{'z':..}`), `load_zoffset` | zMod Z offset, see 4 | |

## 2. Detection

Two independent detectors.

**Filament system** (`H src/printer/printer_discovery_parse.cpp:409-437`):
`AmsType::AD5X_IFS` when `objects/list` has `filament_switch_sensor
_ifs_port_sensor_*`, `filament_motion_sensor _ifs_motion_sensor_*`,
`filament_motion_sensor ifs_motion_sensor`, **or an object named `ifs` or
`ifs_materials`**. Gated on no Happy Hare / AFC already found.

**Printer model** (`H src/printer/printer_detector.cpp:515-600`, scored
heuristics in `H assets/config/printer_database.json:625-700`, entry
`flashforge_ad5x`): object `zmod_ifs` (98), object `ifs_materials` (98),
macro name containing `_IFS_` (95), macro `SET_EXTRUDER_SLOT` (95),
**hostname containing `ad5x` (96)**, 4 heaters (85, corroborating only),
`weightValue` sensor (80), MIPS CPU (70, corroborating), hostname
`flashforge` (80), corexy (30). Patterns are substring matches. Excludes:
`gcode_button extruder_grab1`, `zmod_afclite` (Creator 5). The AD5M entries
exclude hostname `ad5x` and macros `_IFS_` / `SET_EXTRUDER_SLOT`.

**On our system as-is:** hostname `ad5x` (`buildroot/configs/ad5x_defconfig:22`)
-> model "FlashForge Adventurer 5X", preset `ad5x`. Object `ifs` -> IFS type (HelixScreen's code name for it is AMS)
AD5X IFS. Our `_IFS_STATE` macro also matches `_IFS_` (+95). The module dialect does not latch (our `ifs` has
`connected, version, busy, channel, state, selected, inserted, silk, stall,
colors`, `klipper/extras/ifs.py:389-403`), so the backend runs the zMod
dialect.

What follows on our stack today:

| Feature | Result |
|---|---|
| Lane colours/materials | Empty: `Adventurer5M.json` 404 (poll disabled), no `zmod_color`, `IFS_STATUS` output is not JSON |
| Lane presence, active lane | Unknown (no `Ports`/`Chan`/`loaded_channels`) |
| Load, unload, select, tool change, eject, recover, cancel | "Unknown command" (`INSERT_PRUTOK_IFS`, `_IFS_REMOVE_CURRENT_PRUTOK`, `SET_EXTRUDER_SLOT`, `A_CHANGE_FILAMENT`, `IFS_F24/F11/F39`, `IFS_UNLOCK`) |
| Edit slot | Fails: read-modify-write of a missing `Adventurer5M.json` |
| Refresh | Every trigger (IFS screen open, sensor edges) sends `IFS_STATUS` (ours: serial F13 through `_run`, which calls `toolhead.wait_moves()`, `klipper/extras/ifs.py:591-596`) and `GET_ZCOLOR SILENT=1` (unknown command, `!!` in console; the error does not demote the query, `H :4817-4823`) |
| Head sensor | Invisible: ours is `adc_filament_sensor head`; HelixScreen only picks up `filament_switch_sensor *` / `filament_motion_sensor *` (`H printer_discovery_parse.cpp:497-498`) |
| Preset defaults | Fans `fan_generic fanM106` / `chamber_fan`, sensor `head_switch_sensor`, macros `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `CLEAR_NOZZLE`, `AUTO_FULL_BED_LEVEL` (`H assets/config/presets/ad5x.json`): `fan_generic fanM106` as stock; the four macros in the printer's `macros/quick_actions.cfg` (zMod names, `docs/config-layout.md`) |

**Hazard (fix regardless of option):** `IFS_STATUS` from a UI during a print
drains the move queue (`wait_moves`) between file lines. It is a status
query; it should not wait for moves or take the operation mutex. Same for any
other read-only `IFS_*` command a UI may poll.

## 3. Integration options

### (a) Compatibility layer on our side

Two possible targets.

**(a1) Emulate zMod.** Publish `zmod_ifs` (`Chan`, `Ports`, ...) and
`zmod_color`, keep an `Adventurer5M.json` in `~/printer_data/config`, register
`INSERT_PRUTOK_IFS`, `_IFS_REMOVE_CURRENT_PRUTOK`, `SET_EXTRUDER_SLOT`,
`A_CHANGE_FILAMENT`, `IFS_F11/F24/F39`, `IFS_UNLOCK`, `GET_ZCOLOR SILENT=1`
(exact `// Extruder: ... | IFS: True` text), a JSON `IFS_STATUS`, a
`filament_switch_sensor head_switch_sensor`; optionally `_IFS_VARS` for
remapping. Large surface (~15 names, two text formats parsed by regex), tied to
zMod internals HelixScreen keeps re-learning (bugs #965, #981, #995, #1065 in
`H` comments), and `IFS_STATUS` must change format, breaking our own console
use. Not recommended.

**(a2) Speak the `FX` module contract with our `ifs` object** (recommended).
HelixScreen already supports it upstream, with a mock
(`HELIX_MOCK_AMS=ifs-module`, `H src/api/moonraker_client_mock.cpp:2199-2260`)
and tests (`H tests/unit/test_ams_ad5x_ifs_module.cpp`). Changes, all in
`klipper/` (owned by other agents; listed here as a design):

1. `ifs.get_status()` adds:
   - `active_channel`: F13 `chan`.
   - `loaded_channels`: F13 `silk_state` bitmask decoded to 1-based lanes (our
     `silk` list is the F21 counters, not presence).
   - `activity` / `activity_channel`: decode `FFS_state` as `FX
     .py/klipper/plugins/ifs_status.py:30-75` does (base 3 polling, 5 ready,
     7 clamped, 11 loading, 12 unclamping, 15 unloading, 127 driver_error,
     per-channel stride 11). Agrees with our `STATE_READY = 5`,
     `STATE_FAULT = 0x7f`; `0x7e` (homing) is not in their table.
   - `error`: last `IfsError` text or `None`.
   - `tool_map`: `{"0": 1, "1": 2, "2": 3, "3": 4}` (string keys).
   - `channel_count: 4`. Existing fields can stay.
2. A second status object `ifs_materials` (`printer.add_object` from `ifs.py`
   or a tiny extra): `slots: {"1": {"type": .., "color": "#RRGGBB", "temp": ..}}`.
   Needs a per-slot material type; we store only colours (`ifs_colors`).
3. Save variable `ifs_loaded` (rename of, or mirror to, our `ifs_channel`).
4. Commands, matching `FX` names and parameters:
   - `IFS_LOAD SLOT=n` = our `IFS_SWAP CHANNEL=n` (heat if cold: we do not
     heat today, PRINT_START heats first).
   - `IFS_UNLOAD [SLOT=n]` = new: cut, unload, `_set_channel(0)`, heater
     handling. Our swap's first half.
   - `IFS_EJECT SLOT=n` = full-length retract of an idle lane.
   - `IFS_SET_MATERIAL SLOT= TYPE= COLOR=` (bare hex; superset of
     `IFS_SET_COLOR`).
   - `IFS_MAP_TOOL TOOL= SLOT=` / `RESET=1`, `T0`-`T3` routed through the map;
     `_PRINT_START_TOOL` must route through it too (today it loads
     `TOOL+1` directly, `klipper/ad5x.cfg:458-472`).
   - `IFS_STOP`, `IFS_RESET_DRIVER` -> our F15 reset.
   - **Name clash:** our `IFS_LOAD CHANNEL=` (raw feed) and `IFS_UNLOAD
     CHANNEL=` (raw retract) are primitives; `FX` uses those names for the
     full operations. Rename ours (e.g. `IFS_FEED`, `IFS_RETRACT`, as `FX`
     does) and update `docs/ifs-*.md`.
5. Toolhead sensor also visible as `filament_switch_sensor toolhead` (second
   `printer.add_object` name in `adc_filament_sensor.py`, same status), so
   HelixScreen gets head presence and the pre-print "filament in toolhead"
   check works.

Effort: about 1-2 days of Python/cfg plus tests against the HelixScreen mock
contract; no HelixScreen changes. Risk: low on our side (additive status
fields; renames are local). Contract risk: `FX` is a branch, not a release,
and HelixScreen may change it; mitigated because the same author owns both.
What HelixScreen then gives us: lane colours/types/presence, active lane,
load/unload/eject/edit, tool remap before print, untracked activity
(slicer `T1`) shown live, Spoolman linkage.

Variant worth considering: adopt `FX`'s module outright instead of ours. Same
licence (GPLv3), already measured on hardware (speeds, sensor timing), but it
is "portions derived from zmod" while ours is written from our own protocol
notes, and its choreography differs from the stock-recorded swap
(`docs/ifs-swap-capture.md`). Comparing the two is a separate task; its
`docs/AD5X_IFS_PROTOCOL.md` is worth reading against `docs/ifs-protocol.md`
either way.

### (b) New HelixScreen backend for our `ifs`

A third dialect in `AmsBackendAd5xIfs` or a new `AmsBackend` subclass:
subscribe `ifs`, map `selected/channel/inserted/silk/stall/colors`, send
`IFS_SWAP CHANNEL=`, `IFS_SET_COLOR CHANNEL= COLOR=`, `IFS_UNLOAD`,
`IFS_RESET`, plus registry/detection entries, mock, unit tests.

- Effort: 1-2 weeks. The existing AD5X backend is 8.5 k lines
  (`H src/printer/ams_backend_ad5x_ifs.cpp` 6834, header 1667); a lean
  backend still needs the phase tracker, error mapping, override store,
  mock and test-suite conventions.
- Detection conflict: HelixScreen already claims `ifs` for the `FX` module
  (`H printer_discovery_parse.cpp:434`), so ours would need a discriminator
  (e.g. absence of `ifs_materials` or of `tool_map`) inside the same
  backend.
- Upstream risk: high. A maintainer who ships his own AD5X module has little
  reason to carry a third AD5X dialect; the natural review answer is "publish
  the module contract". Out-of-tree, we would rebase against a very active
  repo.
- Gains nothing over (a2) for the printer's owner.

### Recommendation

(a2): make our `ifs` speak the `FX` module contract (status fields,
`ifs_materials`, `ifs_loaded`, `FX` command names, `filament_switch_sensor
toolhead`). Do the `IFS_STATUS` `wait_moves` fix first regardless. If anything
is missing from the contract (e.g. a load-free select, homing state), propose it
upstream to `FX`/HelixScreen together rather than adding a dialect. Every added
command/field goes in `docs/deviations-from-stock.md`.

## 4. Z offset and print-start checks

### Z offset

HelixScreen's model (`H include/z_offset_persistence.h:4-20`,
`H src/printer/z_offset_persistence.cpp:222-262`): providers keyed on a
macro:

| Provider | Detect macro | Stored value |
|---|---|---|
| zMod | `SAVE_ZMOD_DATA` | `save_variables.gcode_offsets.z`; enable flag `load_zoffset`; one-shot `SAVE_ZMOD_DATA LOAD_ZOFFSET=1`; clears `_TEST_POINT.temp_z_offset` before idle saves |
| Forge-X (AD5M) | `SET_MOD` | `mod_params.variables.z_offset` |
| Helper-Script | `gcode_macro SET_GCODE_OFFSET` | `save_variables.zoffset.z` |

zMod side: `SET_GCODE_OFFSET` is wrapped (`rename_existing: _SET_GCODE_OFFSET`)
to persist every change in `gcode_offsets`; `LOAD_GCODE_OFFSET` re-applies at
print start (`ZA translate/en/base.cfg:2105`, `:2187`; `SAVE_ZMOD_DATA`
`translate/en/ad5x_config_native.cfg:1`).

Separately the printer DB gives the AD5X entry
`z_offset_calibration_strategy: firmware_managed`
(`H printer_database.json:631`), applied by model
(`H src/printer/printer_profile_state.cpp:44-60`). With it:

- Z calibration panel: `G28` if unhomed, `G1 X110 Y110 Z5`, `G1 Z0.1`, user
  jogs with `G91 G1 Z±d`, accept sends `SET_GCODE_OFFSET Z=<total jog>`
  (`H src/ui/ui_panel_calibration_zoffset.cpp:505-520`, `:628-640`,
  `:677-700`) and toasts "Z-offset is auto-saved by firmware"
  (`H src/ui/z_offset_utils.cpp:36-44`).
- Print tune "save": does nothing, firmware assumed to persist
  (`H z_offset_utils.cpp:159-163`).

**On our config:** the `SET_GCODE_OFFSET` wrapper in `klipper/ad5x.cfg`
saves every Z change (`Z=` or `Z_ADJUST=`: the Z calibration panel,
baby-steps from any UI or the console) as `save_variables.zoffset =
{'z': ..}`, so HelixScreen picks the Helper-Script provider and reads the
saved value back. `PRINT_START` applies it (`_APPLY_Z_OFFSET`); its own
resets use `_SET_GCODE_OFFSET`, so they are not saved. The first start
copies `unit.cfg`'s `z_offset` into `zoffset` (`_SEED_ZOFFSET`). With the
zmod-compat plugin on, its `SAVE_ZMOD_DATA` would select the zMod row;
HelixScreen patch 0069 makes that row need zMod's `_TEST_POINT` too, so
Kiln stays on Helper-Script (issue #57). Calibration and baby-steps
therefore survive the next print. `LOAD_CELL_TARE` is a macro that runs
`WEIGHT_TARE`, so HelixScreen's tare before probing runs too. The
`firmware_managed` strategy stays (the model is AD5X): accept sends
`SET_GCODE_OFFSET Z=`, which the wrapper saves.

Before this (kept for the record): no provider matched, every offset
HelixScreen set was live only and lost at the next print while the UI
said it was saved, and the generic `probe_calibrate` strategy would have
double-counted `unit.cfg`'s offset through `Z_OFFSET_APPLY_PROBE` +
`SAVE_CONFIG`.

### Print-start checks

`H src/printer/print_start_checks.cpp:847-862`: gates run before HelixScreen
starts a file: printer-stopping command in file, spool weight, lane weight,
bypass engaged, filament in toolhead not accounted for by any lane, required
lanes empty, unresolved tools (no lane mapped), material mismatch.

- Backends with `auto_unloads_after_print()` (AD5X does) skip the
  "required filament present" toolhead warning (`:249-256`).
- Lane checks need per-lane presence and the tool map: on our stack today
  there is neither, so lane checks have nothing to check and the
  unresolved-tools gate cannot remap (`remap_ready()` false without
  `ifs.tool_map` or `_IFS_VARS`).
- "Filament in toolhead" needs the head switch: invisible today (see 2).
- HelixScreen sends no print-start macro parameters for the AD5X (no
  `pre_print_options` in its DB entry), so our `PRINT_START BED= EXTRUDER=
  TOOL= LEVEL=` from the slicer is untouched.

With (a2) these start working; the remap ones additionally need `T0`-`T3` and
`PRINT_START TOOL=` to go through `tool_map`.

## Fan setup wizard at every boot (fixed on the developer's printer, 2026-10-16)

HelixScreen's `ad5x` preset (`assets/config/presets/ad5x.json`) names zMod's
fans: part `fan_generic fanM106`, aux `fan_generic chamber_fan`, board
`fan_generic pcb_fan`. Kiln's were then `fan`, `heater_fan heat_fan` and
`fan_generic pcb_fan` (kept on by `[pcb_fan_watch]`); there is no chamber fan. At every start the
preset seeded `fans/aux` with the missing chamber fan (config.cpp seeds
empty role keys), the missing fan cleared it again, and a one-step "Printer
Setup: Fans" wizard opened (the part fan is `fan_generic fanM106` now,
as stock, `klipper/ad5x.cfg`). The wizard has no field for aux. Fix: set
`printers.<id>.fans.aux` to an existing fan (`fan_generic pcb_fan`) in
`/data/ad5x/helixscreen/config/settings.json` with HelixScreen stopped;
the preset then leaves it alone. A cleaner fix for new installs: a
HelixScreen preset for this firmware, or seeding settings.json at first
boot.

## Setup wizard (HelixScreen patches, 2026-10-16)

First HelixScreen source changes: three Buildroot patches in
`buildroot/package/helixscreen/` (design and screens in
`docs/setup-wizard.md`, section "HelixScreen side"). Until now the
integration was Klipper-side only.

| Area | Change |
|---|---|
| Wizard | Seven new steps (`StepId::Ad5xSelfcheck` ... `Ad5xFinish`, between `FilamentSensor` and `InputShaper`), one class `WizardAd5xSetupStep`, driving Klipper's API endpoint `printer.ad5x_setup.control` (start/abort/adjust/accept; G-code `SETUP_WIZARD_STEP` as fallback) and showing the `ad5x_setup` status object. Shown only with preset `ad5x` or an `ad5x_setup` object |
| Telemetry | The preset first-run telemetry opt-in step is skipped on AD5X (`telemetry_enabled` stays false from the seed) |
| Subscription | `ad5x_setup` (whole object) added to the discovery subscription when `objects/list` has it |
| Settings | Settings > Printer > Run Setup Wizard (same condition): the AD5X steps as a targeted wizard session |
| Start | `HELIX_WIZARD_FLAG_FILE` (S70: `/data/ad5x/printer_data/comms/run-setup-wizard`): full wizard once, flag deleted, preset/host/hardware kept. While running, `// action:ad5x_setup_wizard` (SETUP_WIZARD) opens the AD5X steps at once |
| Reinstall | `HELIX_WIZARD_OFFER_FILE` (S70: `/data/ad5x/helixscreen/offer-setup-wizard`, written by the installer over old settings; patch 0088): with no wizard running, "Run the setup wizard?" once; Run deletes it and opens the Settings session, Skip deletes it; a wizard running anyway or a SETUP_WIZARD deletes it too |
| Seed | `helixscreen-settings.json`: `wizard_completed: false` (both levels), so a fresh install runs the wizard once; the stock touch range with `input.calibration.valid: false`, so the wizard starts with the touch calibration (issue #90); existing settings are never overwritten |
| Touch hold | A press held 10 s anywhere opens touch calibration (patch 0089, PR #91 by jolting, issue #90). Timed in `calibrated_read_cb` on the driver's point before the affine; it fires once, then waits for 3 s with no touch; the widget under the finger gets `PRESS_LOST` (twice: at once and from LVGL at the release) and the release is no click. Patch 0090 (review): the timing in `TouchHoldGesture` (`touch_hold_gesture.h`, tests `test_kiln_touch_hold.cpp`); releases under 70 ms (two readings) are noise, not 200 ms, and a release seen then a press after the gap is a new press; the finger must stay within 8% of the screen per axis; nothing fires while a calibration capture runs (`capture_active` / `is_touch_calibration_active()`: the wizard's step 1 or the overlay), also for a press that outlasts it; in the full wizard it opens the wizard's own touch step (`force_touch_calibration_step`, `ui_wizard_navigate_to_step`), never the overlay, whose close would hide the wizard's container; in a targeted wizard session it does nothing; open modals are closed first (`ModalCloseReason::External`), as they would cover Accept; on success the overlay path refreshes Settings > Touch & Input's status and clears `/input/force_calibration`. Patch 0091 (second review): every number in `touch_hold_gesture.h`; lifts of up to 200 ms (`kCalibrationHoldGapMs`, last pressed reading to the next: one released reading at the panel's slowest 100 ms) are bridged, but lifts of 70 ms and more (`kCalibrationHoldNoiseMs`) are counted and more than 3 (`kCalibrationHoldMaxLifts`) are taps, the hold starting again; only 2 readings in a row outside the radius (`kCalibrationHoldMovedReadings`) move it; refused over the lock screen or PIN pad and under the busy overlay or abort dialog (`current_app_covers()`) and while a wizard step change is pending; the first-run tour is ended without being marked done (`FirstRunTour::abandon()`); the wizard step goes through the Next/Back guard (`ui_wizard_request_step`); a targeted session is ended with its cancel callback (`ui_wizard_cancel_session`), then the overlay opens; `touch_hold_action()` decides at the hold and again on the next tick, and dialogs close only when something opens; `force_touch_calibration_step` is reset when the touch step is left or the wizard ends. Patch 0093 (issue #90): every capture runs under the device's declared ABS range in place of a stored range (`TouchCalibrationSession::begin_capture`, `ICalibrationSink::declared_touch_range`; restored on cancel, re-applied on retry), laid out as the stored range and its affine run together (`range_layout_with_affine`, `orient_declared_like`: the swap, each axis reversed when the range XOR the affine's `a`/`e` reverses it, the off-diagonal terms' signs when they dominate; without one, `uncalibrated_declared_orientation`, Y reversed on Kiln's own kernels), so a damaged stored range can't make the three taps degenerate and the screen stays the right way up; an affine-only result is saved with the capture range; `load_touch_range()` refuses a stored range through which the declared one reaches under 1/8 of an axis (`stored_touch_range_fits_declared`, `kStoredTouchRangeMinReach`), drops its affine, and sets `/input/force_calibration`, which `commit_calibration_result` clears on every successful commit |
| Boot loader notice | `HELIX_KILN_BL_NOTICE_FILE` (S70: `/run/ad5x-bootloader-notice`, written by `ad5x-bootloader-notice` at each complete start; patch 0094): `kind=update` (Kiln's boot loader there, slot A's recovery OS carries a newer build) shows "A boot loader update is ready" with the menu path once per carried build, `kind=install` (Flashforge's boot loader on a known board, from the 3rd complete start) "Kiln OS has its own boot loader for this printer" once per printer. A dialog with OK, only at idle: no setup wizard running, required, requested (`HELIX_WIZARD_FLAG_FILE`) or offered (0088), no print holding the printer, no other dialog; looked for every 10 s. OK or a backdrop tap is kept in `HELIX_KILN_BL_STATE_DIR` (`/data/ad5x/bootloader-notice`: `update-seen` with the key, `install-dismissed`). The path names Settings > System > Boot into recovery as each language shows it (0094 also translates 0055's six recovery strings into de, es, fr, it, ja, ko, pt, tr, zh); the recovery screen's entries stay English, as that screen shows them outside English and Russian. `docs/own-boot-loader.md` |

This also closes the "fresh install" half of the fan-wizard note below: the
seed already names our fans, so the wizard's pickers stay collapsed.

To check on the screen (nothing here has run):

1. Fresh install (delete `/data/ad5x/helixscreen/config/settings.json` with
   HelixScreen stopped): wizard starts at language (touch calibration
   skipped), Wi-Fi, then self-check without any hardware picker or
   connection step; step numbering "n of N" is sensible.
2. Each AD5X step: Start, progress and message updating live while the
   G-code blocks; Abort while running; failed state shows Retry and Skip;
   done shows the results and Next. Long self-check list scrolls.
3. Z offset: -/+ buttons change the shown offset during the test print
   (the change reaches the bed about 2 s later); New Patch prints another
   patch beside it; Accept ends it. Abort during PID/heating switches the
   heaters off at once.
4. Save: SAVE_CONFIG restart shows no disconnect/recovery dialog and the
   step ends in "Saved" after reconnect; then preferences, Finish, home
   screen; no telemetry page.
5. Reboot: no wizard. `touch /data/ad5x/printer_data/comms/run-setup-wizard`
   + `/etc/init.d/S70helixscreen restart`: wizard once, flag gone.
   `SETUP_WIZARD` in the console with the screen running: the AD5X steps
   open at once.
6. Settings > Printer > Run Setup Wizard: confirm, seven steps, Back on the
   first step and Finish on the last return to Settings.
7. After a reinstall (or `echo test > /data/ad5x/helixscreen/offer-setup-wizard`
   + `/etc/init.d/S70helixscreen restart`): "Run the setup wizard?" over the
   home screen; Run opens the Settings session and the file is gone; Skip
   leaves the home screen and the file is gone; no question at the next
   restart.
7. Layout at 800x480: card, buttons and the footer fit; text wraps.
8. Filament step (patch 0084): the slots with filament show a material
   dropdown, empty ones say Empty; the dropdowns start at each slot's
   material; Start with the toolhead on Auto finds an unknown slot (the
   live view says "Finding the slot in the toolhead"), then shows the
   result line. Slot n refused with the toolhead empty, None refused with
   filament in it (message, Retry). "Use the filament in the toolhead as
   it is" keeps a hand-fed strand; the IFS step then fails asking to pull
   it out.
   When the find can't tell the slot (`pick_slot`): the slot buttons show
   the slots with filament with their material and colour; a slot runs
   the filament step with that slot, "I pulled it out by hand" with
   `head=0`; from the Z offset card the filament run shows there, then
   Start runs the Z offset. With a strand in the tube the filament page
   warns to name the slot first.
9. Live view on long steps (PID, mesh, Z offset): the action phrase
   changes with the step, nozzle and bed now/target update every second,
   the elapsed time counts up (also on a printer whose clock is not set).
10. Z offset: the plan line ("Slot 2, PETG, 240/70 °C") appears before the
    nozzle heats; with no material set it says PLA's temperatures are used.
    After Accept: "Remove the test print from the bed" and Done; the next
    step starts only after Done. After an abort with a patch printed: the
    reminder with Done, which clears it. In Russian, every new text is
    Russian.

The first draft's contract problem (abort/adjust queued behind a blocking
G-code) is solved on the Klipper side: steps run in the background and the
screen sends every action through `printer.ad5x_setup.control`, which is not
behind the G-code lock. Homing, `BED_MESH_CALIBRATE` and `SHAPER_CALIBRATE`
still finish their current command before an abort ends the step.

## Root password reset (implemented: HelixScreen patch 0103)

Kiln OS's side: `S68ad5x-update-agent`, `ad5x-passwd`, `lib/rootpw.sh`,
`ad5x-fbstream`; user docs in [install.md](install.md), "SSH login and the
root password". The screen's side: patch
`0103-kiln-root-password-reset.patch` (`include/ui_settings_kiln_rootpw.h`,
`src/ui/ui_settings_kiln_rootpw.cpp`, the System page's XML and
`ui_settings_system.cpp`). It does two things. Both are Kiln OS builds only
(`HELIX_KILN_AD5X`; other builds show nothing and their factory reset is
upstream's).

### The request (the same for both)

HelixScreen runs as root. It talks to the root agent through files in
`/run/ad5x/screen-request/` (root's, 0700; the agent makes it at start), never
through Moonraker, Klipper or a G-code: those are reachable from the network,
the folder is not.

1. Delete `root-password-default.status` if it is there.
2. Write `root-password-default` with one line, `KIND STAMP`:
   - KIND `reset` (the button) or `factory-reset` (the factory reset);
   - STAMP the seconds since boot, `CLOCK_BOOTTIME` (the same clock as
     `/proc/uptime`), as a whole number with no leading zeros, taken **when
     the press began**: the button, the press that starts the 5 s hold; the
     factory reset, the press on the confirmation's Reset button
     (`LV_EVENT_PRESSED` on its `btn_primary`; with none seen, when the
     reset runs). Not the time of writing.

   Example: `reset 4182`. A new regular file (`.s.XXXXXX` by `mkstemp` in
   the folder, then renamed), mode 0600. No folder (or a link in its place):
   nothing is written, "Could not send the request to the system".
3. Wait for `root-password-default.status`, looked for every 250 ms. The
   agent's screen loop looks every second, apart from its main loop, so a
   long job (an update's checksum, a plugin's root script) never delays it.
   After 10 s the screen gives up: it deletes `root-password-default` if it
   is still there, so a late reset can't land, and says "No answer from the
   system, try again". One request at a time: a new one ends the waiting one
   as unanswered.
4. Its one line: `done`, or `refused: <reason>` / `failed: <reason>`. The
   reasons the screen translates:
   - `refused: password reset is locked (turned off over SSH)`
   - `refused: the screen was used from a browser; touch it on the printer itself and try again in 30 seconds`
   - `refused: a print is running`
   - `refused: the request came too late; try again`
   - `failed: bad request`
   - `failed: <ad5x-passwd's message>` is shown as it is (English: it comes
     from the OS), as is any other line.

The agent judges the request by STAMP, not by when it reads it: refused when
the press began more than 10 s ago (or in the future), checked again just
before the password changes, and when the browser screen view
(`/run/ad5x/remote-touch`) touched the screen at or after STAMP - 30 s, or
holds it now. A missing or malformed STAMP is a bad request. Moonraker gets
2 s to say whether a print runs; no answer counts as not printing (a reset
can't harm a print, a broken Moonraker shouldn't lock the owner out, and a
slow answer only makes the request too old).

`done` means root's password is now `root`, already in use (no restart).

### The button: Settings > System > Reset root password

- Just above Boot into recovery. Shown only with Settings > Advanced
  settings on (patch 0107) and when
  `/run/ad5x/screen-request/root-password-reset.state` exists (a plain file,
  not a link); it holds `unlocked` or `locked` (the agent rewrites it within
  3 s of a change). The screen reads it when the System page first opens, every
  2 s after that, at each press and after each answer.
  - `unlocked`: the row "Reset root password" with an open lock icon and the
    hint "Hold 5 seconds: SSH login root / root" (shown at every screen size).
    Greyed while a print is active (`print_active`).
  - `locked` (or anything other than `unlocked`): a greyed row with a closed
    lock, "Reset root password", and "Turned off over SSH (ad5x-passwd
    --unlock-reset)". It takes no press.
  - Missing (no agent): neither row.
- A 5 s hold, not a tap. The row's `LV_EVENT_PRESSED` starts it, only when
  `lv_indev_active()` is DisplayManager's own pointer
  (`DisplayManager::pointer_input()`): not HelixScreen's remote pointer
  (`helix::remote::RemotePointer`, a second indev) and not an event made
  without an input device (`ctl click`, a Lua plugin's events). The
  remote-control server is compiled out (`ENABLE_REMOTE_CONTROL=no`); the
  check is there anyway. Touches from Kiln's own browser screen view
  (`ad5x-fbstream`, nginx `/screen/`) arrive on the panel's own evdev node and
  can't be told apart here; the agent refuses those from its record
  (`/run/ad5x/remote-touch`). HelixScreen 1.2's Lua plugins run inside its
  process, and this check is what keeps them out: besides the indev, the
  panel must be down on the row when the press arrives, and the hold follows
  the panel's own state (below), not events, so an event sent from inside
  HelixScreen starts and keeps nothing.
- The hold itself is not LVGL's (whose long press comes after 300-1500 ms): an
  `lv_timer` every 50 ms looks at the panel's pointer, pressed, on the row,
  the row not greyed and nothing scrolling (`ResetHold`, no LVGL, tested on its
  own). A lift of up to 200 ms (`kCalibrationHoldGapMs`, as the hold to
  calibrate in `touch_hold_gesture.h`) from the last pressed reading does not
  end it; a longer one, a slide off the row, a scroll or the lock turned on
  during the hold ends it with nothing sent. It fires on a pressed reading 5 s
  after the press. The hold to calibrate opens calibration after 10 s anywhere;
  if the finger stays on, it covers the answer dialog (harmless).
- The hold fires once per press. After it fires, no new hold starts until
  the panel has been let go for more than 200 ms (looked at anywhere on the
  panel: the answer's dialog may be under the finger by then), so a finger
  kept down, or a press LVGL sees again after a short lift, never sends a
  second request. A new press starts a new hold with its own stamp.
- While held: a bar under the row fills over the 5 s, with "Keep holding...".
  At 5 s the request goes out with `reset` and the press's stamp, and the line
  says "Resetting...".
  The answer opens a dialog titled "Reset root password" with OK: `done` ->
  "Root password reset. Log in over SSH as root with the password root, then
  run passwd to choose your own." (Info); a refusal, failure or no answer ->
  its reason (Warning). The row is ready for another hold after that.

### The factory reset: Settings > System > Factory reset

`SystemSettingsOverlay::perform_factory_reset()` (`src/ui/settings/ui_settings_system.cpp`
in 1.2): after `config->reset_to_defaults(); config->save();` it writes the
request with `factory-reset` and the stamp of the press on the
confirmation's Reset button (`kiln_rootpw::request_factory_reset()`), shows
"Resetting..." while it waits (up to 10 s), then the answer's toast for 4 s,
and only then `app_request_restart_service()` (upstream restarts at once,
which leaves no time to read a toast). Only this function writes
`factory-reset`, and only on its own run (no other code path, button, `ctl`
command or plugin API writes it; a test reads the sources for that). The
request goes out whatever the state file says. The agent applies it whatever
the lock says and removes the lock (`FACTORY_RESET_HONOURS_LOCK=no` in the
agent): whoever locked themselves out can get back in, at the cost of the
screen's settings. It still refuses while a browser uses the screen and while
printing; the factory reset itself goes on then.

- The confirmation text gets one line: "The root password also becomes
  root."
- Toast: `done` -> "Settings reset to defaults. Root password is root.
  Restarting..." (Success); otherwise "Settings reset to defaults. The root
  password was not reset: <reason>. Restarting..." (Warning), the reason
  translated as above.

### Texts

The row, its hint, the locked hint, "Keep holding...", the result, the
reasons above, "No answer from the system, try again", "Could not send the
request to the system", "The request came too late; try again", the confirmation line and both toasts are in
`translations/en.yml`, `en-GB.yml` (empty: English) and de, es, fr, it, ja,
ko, pt, ru, tr, zh (the image ships the en and ru packs only, see
`docs/setup-wizard.md`, "Language"). "Resetting..." and "OK" were already there. Russian:
«Сбросить пароль root», «вход по SSH».

### Tests

`tests/unit/test_settings_kiln_rootpw.cpp`: the row's three states from the
state file (and a link refused), the status line and the texts for each
answer, the request file's content (with the press's stamp, CLOCK_BOOTTIME)
and mode with the old answer deleted and no
temporary file left, the 10 s timeout taking the request back, no folder, the
hold (5 s fires, an early lift cancels, a 150 ms lift doesn't, 200 ms is the
limit, the tick wrapping), the indev check (remote pointer and no indev
refused), the row from unlocked through holding and waiting to an answer done
or refused, locked (and locked during the hold), the answer's dialog, one
press sending one request (a finger kept down or pressed again after a
short lift sends no second one; a new press after letting go does, with its
own stamp), the factory reset writing `factory-reset` while locked, its
stamp from the press on Reset, that only
`perform_factory_reset` writes it (the sources), and the texts in every
language (Russian only Russian). `tests/unit/test_settings_system_callbacks.cpp`:
the System page's rows hidden, unlocked (greyed during a print), locked, the
bar and the line, and the press callback attached.

The tests drive the module's `lv_timer`s themselves (`pump()` in the test):
HelixScreen's test pump runs no periodic timer. `perform_factory_reset()`
itself is not run in a test (it resets the shared config and asks for a
restart); its request is `request_factory_reset()`, tested above, and the
source check pins the one call to it.

## Advanced settings (implemented: HelixScreen patch 0107)

A switch at the bottom of the Settings root, **Advanced settings** (no
subtitle), in its own card
under HELIXSCREEN. It is always shown. Off, Settings shows only the
everyday rows; on, every row as before. The navbar's Advanced tab is not
touched.

### The setting

- `advanced_settings` in `settings.json` (global, a JSON boolean), a
  `PersistedSetting` row of `SystemSettingsManager` (subject
  `settings_advanced`, default 1, telemetry key `advanced_settings`;
  `get_advanced_settings()` / `set_advanced_settings()`). The switch's
  callback `on_advanced_settings_changed` is registered with the root's
  callbacks (`register_settings_panel_callbacks`).
- **Updated printers keep it on**: a `settings.json` without the key
  reads 1, so a printer that had HelixScreen before sees every row.
- **New installs start with it off**: the seed
  `buildroot/board/ad5x/rootfs-overlay/usr/share/ad5x/helixscreen-settings.json`
  (copied by `S70helixscreen` only when there is no `settings.json`) has
  `"advanced_settings": false`.
- **Factory reset turns it off**: `Config::reset_to_defaults()` builds the
  document from `get_default_config(..., include_user_prefs=true)`, which
  now writes `advanced_settings: false`, and saves it before the restart.
  `S70helixscreen` then finds a `settings.json` and does not seed again, so
  the reset's own value is the one that counts. A first start without any
  `settings.json` and without the seed (not on Kiln OS) leaves the key out:
  on.

### What hides

Each hidden row (or its container) carries
`<bind_flag_if_eq subject="settings_advanced" flag="hidden" ref_value="0"/>`.
helix-xml composes bindings on one flag (`lv_xml_bind_compose.c`: the flag
is set while any of them holds), so a row's own capability or AD5X gate
keeps working in both modes, and the rows need no wrapper (a wrapper would
stay laid out at height 0 over a row its own gate hides).
`tests/unit/double_bind_widgets.inc` is regenerated
(`scripts/scan_double_binds.py --emit-cpp`) so `[bind_compose]` drives the
new pairs. The bindings follow the subject on pages already built, so the
switch takes effect at once, no restart. A `setting_group` hides its header
by itself when none of its rows shows.

| Page | Hidden while off |
|---|---|
| Settings | Touch & Input, Purge Box, Updates, Plugins (HelixScreen's own, under HELIXSCREEN; Kiln's Plugins under PRINTER stays) |
| Printer | the model row, Manage Printers (header button); name and image stay |
| Printing | Machine Limits, Retraction Settings, Multi-Filament System Management, Z Offset by Material, Allow cold load/unload, Number slots from 0, Apply start options to prints from other apps, Macro Buttons |
| Devices | Sensors, IFS firmware, Power Devices |
| Safety & Alerts | Cancel Escalation and Escalation Timeout, Confirm before running macros, the nozzle-hit guard's Sensitivity (the guard's switch stays) |
| Connection | Printers, Host, API Key, Screen Sharing (Network Settings stays) |
| System | Performance, Storage, Firmware Update, Share Usage Data and View Telemetry Data, Log Level and Log detail, Reset root password, Boot into recovery, Return to Flashforge firmware, Extended memory (with its notes) |
| Help & About | Upload Debug Bundle, Discord Community, Getting Started, User Guide |

Confirm shutdown and reboot (Safety & Alerts) stays hidden from C++ as
before (`ui_settings_safety.cpp`). A hidden setting keeps its value and
keeps working.

### Texts

"Advanced settings" and its description are in `translations/en.yml`,
`en-GB.yml` (empty: English) and `ru.yml` («Расширенные настройки»,
«Показывать все настройки, в том числе те, которые могут нарушить работу»;
not «Дополнительно», which is the Advanced tab). The other languages are
not shipped (`docs/setup-wizard.md`, "Language") and fall back to English.

### Tests

`tests/unit/test_settings_advanced.cpp`: each page built with the setting
on, then switched off and on again on the live page: every row above
hides and comes back to what its own gates gave it, and the everyday rows
around it don't change; a row's own gate (HelixScreen's Plugins) still
hides it with the setting on; the root's switch drives the setting and
`settings.json`, and follows it. `tests/unit/test_persisted_setting.cpp`
mirrors the new row (default, absent key, clamping, telemetry key).
`tests/unit/test_config.cpp`: a factory reset stores false, a first start
without the seed leaves the key out.

## Web interface (implemented: HelixScreen patch 0108)

Settings > System > **Web interface**: Fluidd or Mainsail at the
printer's address (`docs/web-interface.md`), under Extended memory. In
System, not Connection: it changes the printer's own system (Kiln's root
agent points nginx at the other interface), as the Kiln rows around it
do; Connection is about how this screen reaches printers. Behind
Settings > Advanced settings (patch 0107's binding on its container).

- **Shown** only on the AD5X build (`HELIX_KILN_AD5X`), when
  `machine.kiln_os.info` lists the `webui` feature (an older Kiln OS:
  hidden, nothing else asked) and `machine.kiln_os.get_webui` answered
  with at least one known interface. Both are asked in the discovery
  sequence (every connect and Klipper restart) and each time the System
  page opens (`SystemSettingsOverlay::on_activate`).
- **The choice**: a dropdown with only the interfaces in `available`
  (Fluidd, Mainsail; names Kiln OS doesn't know are left out), showing
  `webui`. `setting_dropdown_row` gained a `bind_options` prop for it
  (a string subject, one option per line; empty: none).
- **A pick** sends `machine.kiln_os.post_webui` `{"name": NAME}` (45 s
  timeout; the agent has 30 s) and greys the dropdown until the answer.
  Done with `changed`: a toast "Web interface is now Mainsail. Reload the
  printer's page in your browser." (or Fluidd). A second pick, or a
  fetch, while one is on its way sends nothing.
- **mainsail-kiln**: `plugin` set in the GET, or a `plugin_manages_webui`
  refusal: the row is replaced by a greyed one, "Managed by the
  mainsail-kiln plugin", showing the current interface (the refusal also
  says so in a toast).
- **Any other error** (`bad_parameter`, `not_available`, `agent_failed`,
  `agent_timeout`, `agent_unavailable`, a timeout): a toast "Can't switch
  the web interface: <Kiln's message>" and the dropdown back on the
  interface Kiln last reported.

Code: `include/ui_settings_kiln_webui.h`,
`src/ui/ui_settings_kiln_webui.cpp` (`helix::kiln_webui::WebuiModel`;
subjects `kiln_webui_state` 0 hidden / 1 the choice / 2 plugin,
`kiln_webui_options`, `kiln_webui_selected`, `kiln_webui_busy`,
`kiln_webui_locked`), the rows in `ui_xml/settings_system_overlay.xml`
(`container_kiln_webui`, `row_kiln_webui`, `row_kiln_webui_plugin`),
callback `on_kiln_webui_changed`.

Texts in `translations/en.yml`, `en-GB.yml` (empty) and `ru.yml`:
«Веб-интерфейс», «Что открывается по адресу принтера в браузере»,
«Управляется плагином mainsail-kiln», «Теперь веб-интерфейс — {}.
Обновите страницу принтера в браузере.», «Не удалось переключить
веб-интерфейс: {}». Fluidd and Mainsail are names, the same in every
language.

Tests: `tests/unit/test_settings_kiln_webui.cpp`: Kiln's object read
field by field (unknown names left out, the plugin, no interface); no
webui feature (and no `machine.kiln_os.info`) asks nothing more and
keeps the row hidden; nothing on another build; the GET's choice among
what Kiln has (one or two), the plugin's greyed row, the feature gone
again; a pick posts the name, greys the control, ignores a second pick
and a fetch, and on the answer shows the toast; the current one and a
line that isn't there send nothing, nor a pick before Kiln answered; a
refusal and a timeout put the choice back with the error; the
`plugin_manages_webui` refusal greys the row; on the built System page
the container hidden without the feature and with Advanced settings off,
the options and the selection from the GET, the dropdown's pick posting
and greying it, the rollback, the plugin row greyed, and the one-line
list. `tests/unit/test_settings_advanced.cpp` lists the container among
the advanced rows.

## Tips and problems behind Advanced settings (implemented: HelixScreen patch 0109)

With Settings > Advanced settings off (patch 0107), on-screen texts that
send the owner to a hidden row are handled by kind (owner's rule: a tip
that only leads to an advanced row isn't shown; a real problem is always
shown and says how to get there; unsure counts as a problem).

| Text | Kind | While off |
|---|---|---|
| Extended memory notice (0074, "You can switch Extended memory on in Settings > System") | Tip | Not posted. Kiln keeps `notice_pending` (nothing marks it seen), so it is posted when the root switch is turned on (`MemoryModel::advanced_turned_on`) or at the next connect with it on |
| Boot loader notices (0094, "Settings > System > Boot into recovery > ...", update and install) | Tip | A new gate `Gates::advanced_off`: the notice waits, not marked shown; it shows at the next look after the switch is turned on (the root switch looks at once, otherwise the 10 s poll) |
| "New plugin available: {}. Enable it in Settings > Plugins." and "{} new plugins available..." (HelixScreen's own plugins) | Tip | No toast. Not queued: a toast for the session, the plugins count as known as before |
| "{} firmware {} is available. Open Settings > System > Firmware Update to install it." | Tip | Not posted; the version announced is kept apart from the one found, so the first check with the switch on posts it |
| Tour step "Customize your home screen" ("turn on Allow Home Screen Editing in Settings > Touch & Input") | Tip | Step left out (`build_kiln_tour_steps(..., advanced)`); the tour is seen as usual and Replay Welcome Tour with the switch on has it |
| "An internal error occurred ... send a debug bundle from Settings > Help & About" | Problem | Shown; "(turn on Settings > Advanced settings first)" |
| "Not enough free space on the printer for this file. Free some in Settings > System > Storage." | Problem | Shown; the same addition |
| "This printer's Moonraker rejected its API key. Check the key in Settings > Connection." | Problem | Shown; the same addition |
| "This printer's Moonraker requires a login. Add its API key in Settings > Connection." | Problem | Shown; the same addition |
| "This printer's start macro sets a Z offset for each material ... Turn on Settings > Printing > Z Offset by Material ..." | Problem | Shown; "(shown with Settings > Advanced settings on)" |
| Telemetry explanation ("You can view the exact data in Settings > System > View Telemetry Data anytime", untranslated upstream text) | Problem (privacy statement, kept) | Shown; "(turn on Settings > Advanced settings first)" |

A problem text is one text for both modes (with the switch on, the
addition does no harm), so the call sites and their tests stay as they
were. The new English keys are in `translations/en.yml`, `en-GB.yml`
(empty) and `ru.yml` («сначала включите Настройки > Расширенные
настройки»); the old keys stay in the files, unused.

Shortcuts to a hidden page do nothing while the switch is off (no
navigation; the item stays as read-only information):

| Shortcut | Opens | While off |
|---|---|---|
| Printer page chips Filament Sensors and Width Sensors | Sensors | Tap does nothing; not clickable, so no press effect (`cap_chip_needs_advanced`, a `clickable` binding on the chip) |
| Printer page chip Retraction | Retraction Settings | The same |
| Printer page chip Power | Power Devices | The same |
| Controls, "N more sensors" link under the heaters | Sensors | Tap does nothing; the count stays. The link stays clickable (it takes the tap), so the tap doesn't reach the temperature card behind it and open the nozzle temperature |
| Home screen filament sensor tile, when its tap would open the sensor settings (no sensor state to show) | Sensors | Tap does nothing; its other taps (status, Load/Unload dialog) as before |
| HelixScreen's update banner (Update opens Settings > Updates) | Updates | Not shown: it hides as soon as the switch is turned off and comes back as soon as it is turned on (it observes `settings_advanced`; not dismissed); Update does nothing |

Left as they are: the navbar's Advanced tab and what it opens (the
owner's exception, including the HelixScreen plugin overview's Storage
link); the IFS screen's own Settings button (the device operations Multi-Filament
System Management also opens: Auto-Refill, Tune IFS and Pre-feed live
there and the tour points at it); the 10 s hold that opens the touch
calibration (a way out when taps land wrong, not a settings page); the
printer type mismatch review (a problem, its own dialog); the MCUs chip
(opens System, which shows). Inside a hidden page, its own links are
unreachable anyway.

Tests: `tests/unit/test_upgrade_banner.cpp` (the banner hides when the switch
is turned off and shows again when it is turned on, not dismissed),
`tests/unit/test_printer_manager_overlay.cpp` (which chips are gated; with
the switch off the Retraction chip is not clickable and its tap opens
nothing, an ungated chip keeps its tap; on, it opens its page again),
`tests/unit/test_settings_kiln_memory.cpp` (no notice while off,
not marked seen, posted once when turned on),
`tests/unit/test_kiln_bootloader_notice.cpp` (the gate; not shown and not
marked while off, shown once on), `tests/unit/test_settings_advanced_texts.cpp`
(the tour step, the problem texts in English and in Russian). The plugin
toast, the firmware notice, the Controls link and the filament sensor
tile have no unit test. A chip that is not clickable passes a tap to the
page body, which only ends a name edit.

## IFS status light follows screen sleep (implemented: HelixScreen patch 0110)

With Display > "light off when the screen sleeps" on, the screen sends
`IFS_LED SLEEP=1` to Klipper when it goes to sleep and `IFS_LED SLEEP=0`
when it wakes (only a change, and only when the printer has the `ifs`
object). Klipper's IFS module (`klipper/extras/ifs.py`) then switches the
IFS status light off while the printer is idle; during a print or IFS work
it stays on, and red always shows. No setting of its own.

## Wi-Fi status poll reads the last scan (implemented: HelixScreen patch 0111)

HelixScreen's NetworkManager backend polls the Wi-Fi status every 5 s and
reads the SSID and signal from `nmcli device wifi list`. nmcli scans
whenever its list is older than 30 s, so a connected printer scanned all
channels about every 45 s, about 12 s off its channel each time; the
RTL8821CU (rtw88) logs `timed out to flush queue 2` for each scan. On an
AD5X with HelixScreen stopped there were no scans in 3 minutes. The poll
now passes `--rescan no` and reads NetworkManager's last scan; the scan on
the Wi-Fi page still scans. Test: `tests/unit/test_wifi_backend_networkmanager.cpp`
(the fake nmcli marks a status read without `--rescan no`; the CONNECTED
case requires none).
