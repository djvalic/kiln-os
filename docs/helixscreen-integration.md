# HelixScreen integration

What HelixScreen (touch UI, github.com/prestonbrown/helixscreen) needs from
Klipper/Moonraker to run on an AD5X with an IFS, and how we close the gap.
Section 0 is what is implemented (option (a2) below); sections 1-4 are the
research it is based on, describing our stack before the change. Nothing
has run on hardware.

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

`buildroot/package/helixscreen/000*.patch`, listed with what each does in
`docs/setup-wizard.md` ("HelixScreen side"): the AD5X setup steps (0001,
0002, 0003, 0006 time zone), the IFS port sensors (0004), Settings >
Plugins (0005, `docs/plugins.md`) and the speaker with Settings > Sound >
Printer Sounds (0007, `docs/sound.md`).

## 0. Implemented (2026-10-15)

Our `ifs` module speaks the `FX` "module" contract; HelixScreen latches
its module dialect on the first `ifs` frame (`loaded_channels`/`activity`/
`tool_map` are always present). Checked against `H` `6f502ac` and `FX`
`422a4ce`; tested in `tools/test_ifs.py` (fake IFS) and a Klipper batch run
of the real configs. Not run against HelixScreen itself.

| Contract item | Ours |
|---|---|
| `ifs.loaded_channels` | F13 `silk_state` mask -> 1-based list (`[]` before the first poll) |
| `ifs.active_channel` | F13 `chan` (int; `null` before the first poll) |
| `ifs.activity`, `activity_channel` | `FFS_state` decoded with `FX`'s table (3 polling, 5 ready, 7/11/12/15 + 11·(ch−1), 127 `driver_error`) plus ours: 1 `selecting`, 10/14 + 11·(ch−1) `loading`/`unloading` (the values F10/F11 set), 0x7e `homing`; else `unknown(n)` |
| `ifs.error` | Text of the last failed operation or of a failed connect, `null` after a success or `IFS_RESET_DRIVER` |
| `ifs.tool_map` | `{"0": 1, ...}`; per print, reset when `print_stats` leaves `printing` for complete/cancelled/error/standby (as `FX`) |
| `ifs.channel_count`, `pending_insert_channels` | 4; F13 `ffs_channels_insert` decoded |
| `ifs_materials.slots` | `{"1": {"type", "color": "#RRGGBB", "temp"}}`, also `loaded`, `temperatures`, `available`, `channel_count`. Stored in save variable `ifs_materials` (migrated from `ifs_colors`). `temp` = per-slot override, else `FX`'s handling table (PLA 220, PETG 250, ...; `temp_<type>` in `[ifs]`) |
| save variable `ifs_loaded` | Written by every load/unload/`IFS_SET_CHANNEL` (replaces `ifs_channel`, which is still read once if `ifs_loaded` is absent) |
| `filament_switch_sensor toolhead` | `[adc_filament_sensor toolhead]` (renamed from `head`) also registers itself under that name: same object, same status, `SET_FILAMENT_SENSOR SENSOR=toolhead` |
| `IFS_LOAD SLOT=n [TEMP=]` | `IFS_SWAP CHANNEL=n`: cut and unload the loaded lane, load, purge (stock-recorded sequence) |
| `IFS_UNLOAD [SLOT=n] [TEMP=]` | Cut, unload, pull back 70 mm, `F39`; `SLOT` defaults to `ifs_loaded`; refused if it names a lane other than the loaded one |
| `IFS_EJECT SLOT=n` | Idle lane: `F24`, `F11 L1000 S1200` (until the IFS is ready), `F39`, no heat, no toolhead moves. Loaded lane: `IFS_UNLOAD` first. Refused when the toolhead holds filament of an unknown lane |
| `T0`-`T3` | `IFS_SWAP CHANNEL={tool_map[n]}`; `PRINT_START TOOL=` goes through the map too |
| `IFS_MAP_TOOL TOOL= SLOT=` / `RESET=1` | As `FX`: refused without a reading or for a lane without filament |
| `IFS_SET_MATERIAL SLOT= TYPE= COLOR= [TEMP=]` | As `FX`: absent = keep, empty = clear, bare or `#` hex, `RGB` or `RRGGBB`. `IFS_SET_COLOR CHANNEL= COLOR=` kept (slicer start G-code) |
| `IFS_STOP` | `F112`; during a background pre-feed it ends the pre-feed (F15) |
| `IFS_RESET_DRIVER` | `F15` (= `IFS_RESET`), clears `error` |
| Heat | `IFS_LOAD`/`IFS_UNLOAD`/`IFS_EJECT`/`IFS_SWAP`/`T<n>`: with `TEMP=` that; otherwise only when the nozzle target is below `min_extrude_temp` (idle): hottest slot material involved, else `default_temp` 220. Old target restored afterwards |
| Homing | Load/unload/eject of the loaded lane refuse with "home first (G28)" instead of failing mid-move; HelixScreen homes before these |
| Renamed | Our raw `IFS_LOAD CHANNEL=` -> `IFS_FEED`, `IFS_UNLOAD CHANNEL=` -> `IFS_RETRACT` (`FX` names) |
| Z offset | `SET_GCODE_OFFSET` wrapper saves `zoffset = {'z': ..}` (Helper-Script provider, section 4); first start seeds it from `unit.cfg` `z_offset`; `PRINT_START` applies it (`_APPLY_Z_OFFSET`); internal resets use `_SET_GCODE_OFFSET` |
| `LOAD_CELL_TARE` | Macro -> `WEIGHT_TARE` |

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
which `ifs` carries `loaded_channels`, `active_channel`, `activity` or `error`,
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
- Gains nothing over (a2) for the user.

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

**On our config:** no provider matches (no `SAVE_ZMOD_DATA`, `SET_MOD` or
`SET_GCODE_OFFSET` wrapper), so HelixScreen reads the live
`gcode_move.homing_origin`. Strategy is `firmware_managed` because the model
is AD5X. Every offset HelixScreen sets is live only: `PRINT_START` resets it
(`SET_GCODE_OFFSET Z=0`, then `_CHECK_Z_APPLY` sets `_AD5X_UNIT.z_offset`,
`klipper/ad5x.cfg:382-402`, `unit.cfg:8`), so calibration and baby-steps
are lost at the next print while the UI says they were saved. The panel's
`G1 Z0.1` also probes nothing and does not tare the load cell; HelixScreen's
tare prep only runs for a `LOAD_CELL_TARE` macro (`H printer_database.json:84`,
ours is `WEIGHT_TARE`). If detection ever falls through to the generic
`probe_calibrate` strategy instead, "save" runs `Z_OFFSET_APPLY_PROBE` +
`SAVE_CONFIG`, which folds the live offset (including `_AD5X_UNIT.z_offset`)
into `[probe] z_offset`, and `PRINT_START` then adds `_AD5X_UNIT.z_offset`
again: double-counted whenever it is non-zero.

Fix (our side, small): persist the unit Z offset in `save_variables` and
expose it as one of the provider schemas. Simplest match: wrap
`SET_GCODE_OFFSET` (`rename_existing`) to mirror Z into
`save_variables.zoffset = {'z': ..}` (Helper-Script schema) and make
`_CHECK_Z_APPLY` use that value instead of the static `unit.cfg` one; the
Helper-Script row is refuted unless that variable is present, so it must be
written. Alternatively mirror zMod's `gcode_offsets` + `load_zoffset` +
`SAVE_ZMOD_DATA`, but that macro name also flips other zMod assumptions
(`_TEST_POINT` clear). Either way, alias `LOAD_CELL_TARE` -> `WEIGHT_TARE` so
HelixScreen tares before probe accuracy / Z calibration / mesh.

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

## Fan setup wizard at every boot (fixed on the user's unit, 2026-10-16)

HelixScreen's `ad5x` preset (`assets/config/presets/ad5x.json`) names zMod's
fans: part `fan_generic fanM106`, aux `fan_generic chamber_fan`, board
`fan_generic pcb_fan`. Ours are `fan`, `heater_fan heat_fan` and
`controller_fan pcb_fan`; there is no chamber fan. At every start the
preset seeded `fans/aux` with the missing chamber fan (config.cpp seeds
empty role keys), the missing fan cleared it again, and a one-step "Printer
Setup: Fans" wizard opened. The wizard has no field for aux. Fix: set
`printers.<id>.fans.aux` to an existing fan (`controller_fan pcb_fan`) in
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
| Seed | `helixscreen-settings.json`: `wizard_completed: false` (both levels), so a fresh install runs the wizard once; existing settings are never overwritten |

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
7. Layout at 800x480: card, buttons and the footer fit; text wraps.

The first draft's contract problem (abort/adjust queued behind a blocking
G-code) is solved on the Klipper side: steps run in the background and the
screen sends every action through `printer.ad5x_setup.control`, which is not
behind the G-code lock. Homing, `BED_MESH_CALIBRATE` and `SHAPER_CALIBRATE`
still finish their current command before an abort ends the step.
