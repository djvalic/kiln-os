# Plugin API

What a plugin (`docs/plugins.md`) may rely on, and how that is versioned.
Everything not listed here is internal and may change with any system
update.

## Version

Current: **1.5** (1.5, 2026-11-07: additions only: a plugin can drive
the IFS itself (`owns_ifs`, "A plugin that drives the IFS" below), `[ifs]
enable: False`, packages in a plugin's `extras/`, `printer.load_object()`
finding plugin modules, `printer.ad5x_plugins` `ifs_owner` and
`available.<name>.owns_ifs`.
1.4, 2026-10-20: additions only: the plugin catalog
and `INSTALL_PLUGIN`, `UPDATE_PLUGIN`, `REMOVE_PLUGIN`;
`printer.ad5x_plugins` `catalog`, `job`; Moonraker restarts by itself when
a switch changes its plugin parts; the bed heat soak: `BED_SOAK_CALIBRATE`,
`PRINT_START SOAK=`, `printer.ad5x_soak`; the speaker: `M300`,
`PLAY_MIDI`, `PLAY_SOUND`, `SOUND_STOP`, `SOUND_SETUP`, `printer.ad5x_sound`;
the nozzle size: `SET_NOZZLE_SIZE`, `printer.ad5x_nozzle`; auto-refill
colour matching: `IFS_AUTO_REFILL MATCH=`, `printer.ifs` `refill_match`,
`refill_backups`, `refill_notice`.
1.3, 2026-10-20: additions only: a plugin's
`python/` libraries (Klipper and Moonraker) and `moonraker/components/`
(Moonraker components), and `git` on the printer for installing plugins.
1.2, 2026-10-20: additions only: the Klipper event
`ifs:loaded` (slot), `IFS_AUTO_REFILL` and `printer.ifs` `auto_refill`,
`refill`, power-loss recovery (`RESUME_INTERRUPTED`, `CLEAR_INTERRUPTED`,
`printer.ad5x_resume`).
1.1, 2026-10-17: factory/user config split,
`docs/config-layout.md`. Additions only: `CONFIG_BACKUPS`,
`printer.ad5x_config`, the `macros/` files in the config order,
`PRINT_START`'s `mesh_every_print` and `retract`, `_PRIME_LINE`'s new
variables. The listed macros keep their names and parameters; the ones
marked "macros/" below now live in the printer's editable `macros/`
files instead of the image.)

- In Klipper: `printer.ad5x_plugins.api_version` (also printed by
  `LIST_PLUGINS`).
- On the system: `AD5X_PLUGIN_API="1.5"` in `/usr/lib/os-release`
  (`/etc/os-release`), for scripts.
- In the code: `PLUGIN_API_VERSION` in `klipper/extras/ad5x_plugins.py`
  (the build copies it to os-release).

Rules for system updates:

- **Minor** (1.0 -> 1.1): additions only (new commands, parameters,
  status fields, macros). Nothing listed here changes meaning or goes
  away.
- **Major** (1.x -> 2.0): something listed here changed or was removed;
  docs list what. Plugins built for 1.x are refused until updated.

A plugin states the version it was written for in `plugin.json`,
`requires_os: "1.0"`. It is accepted when the major numbers are equal and
the system's minor is the same or newer: `1.0` runs on 1.0, 1.3; not on
0.9 or 2.0. Without `requires_os` it is accepted (not recommended).
`ENABLE_PLUGIN` refuses an incompatible plugin; one enabled before an
update that made it incompatible stays in `plugins.cfg`, its Python
extras and Moonraker part are not loaded, and Klipper shows a warning.

## Plugin layout

A plugin is a directory named like the plugin (`a-z`, `0-9`, `-`, `_`;
starts with a letter or digit; at most 48 characters):

```
ad5x-myplugin/            the git repository; cloned as /data/ad5x/plugins/myplugin
  plugin.json             metadata (required)
  plugin.cfg              Klipper config (required, may be only comments)
  README.md               what it does, how to use it
  extras/                 optional: Klipper modules
    myplugin_led.py
    myplugin_lib/         optional (1.5): a package (__init__.py), imported as extras.myplugin_lib
  moonraker.conf          optional: Moonraker sections (update manager, ...)
  python/                 optional (1.3): pure-Python libraries the plugin needs
  moonraker/components/   optional (1.3): Moonraker components (name.py)
```

The clone's directory name must match `name` in `plugin.json`
(`git clone <url> myplugin`).

`plugin.json`:

```json
{
  "name": "myplugin",
  "description": "One line for LIST_PLUGINS",
  "version": "1.2.0",
  "author": "Someone",
  "url": "https://github.com/someone/ad5x-myplugin",
  "requires_os": "1.0",
  "requires": ["zmod-compat"],
  "conflicts": ["other-plugin"]
}
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Same as the directory name |
| `description` | no | Shown by `LIST_PLUGINS` |
| `version` | no | Free text, shown by `LIST_PLUGINS` |
| `author`, `url` | no | Shown / available in `printer.ad5x_plugins` |
| `requires_os` | recommended | Plugin API version written for, `major.minor` |
| `requires` | no | Plugins that must be enabled first |
| `conflicts` | no | Plugins that can't be enabled together with this one |
| `owns_ifs` | no | `true` (1.5): the plugin drives the IFS instead of Kiln's `[ifs]` module ("A plugin that drives the IFS") |

`plugin.cfg` example:

```
# myplugin: chamber light level when idle (docs: README.md)
[myplugin_led]
idle_brightness: 0.2

[gcode_macro MYPLUGIN_IDLE_LIGHT]
description: Chamber light to the idle level
gcode:
  SET_LED LED=chamber_led WHITE={printer.configfile.settings.myplugin_led.idle_brightness}
```

`extras/myplugin_led.py` (Klipper module, GPLv3 like Klipper):

```python
class MyPluginLed:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.idle = config.getfloat('idle_brightness', 0.2,
                                    minval=0., maxval=1.)
        self.printer.register_event_handler("klippy:ready", self._ready)
    def _ready(self):
        reactor = self.printer.get_reactor()
        reactor.register_callback(self._set_light)
    def _set_light(self, eventtime):
        gcode = self.printer.lookup_object('gcode')
        gcode.run_script("SET_LED LED=chamber_led WHITE=%.2f" % self.idle)

def load_config(config):
    return MyPluginLed(config)
```

`moonraker.conf` example: see "Keeping a git plugin up to date" in
`docs/plugins.md`.

`python/` and `moonraker/components/` (1.3) are used only while the
plugin is enabled and compatible:

- `python/` goes at the end of Klipper's and Moonraker's `sys.path`
  (after their own libraries, so it can't replace them). For libraries
  the image lacks; pure Python (no compiler on the printer, no pip).
- `moonraker/components/<name>.py` is loaded by Moonraker like its own
  components when a `[<name>]` section names it (the plugin's
  `moonraker.conf` can hold that section). A name Moonraker already has
  is Moonraker's.
- Moonraker is restarted when a switch changes these (1.4; before: at its
  next start).

Rules for plugins:

- Prefix your own macros, modules and variables with the plugin name
  (`_MYPLUGIN_...`, `myplugin_...`).
- Klipper merges sections of the same name from different files, so a
  `[gcode_macro PRINT_START]` in a plugin replaces options of ours (its
  `gcode:` replaces ours entirely); `rename_existing` can't wrap a macro
  that is itself defined in config. It does work for commands registered
  by Python modules (`SET_PRINT_STATS_INFO`, `M104`, `IFS_SWAP`, ...).
  Prefer new commands of your own over replacing listed macros; a plugin
  that replaces one takes over its upkeep.
- Don't redefine sections the user owns (`[gcode_macro _AD5X_UNIT]`) or
  write to files outside the config directory.
- A module name can't be the name of a Klipper module or another
  plugin's module (refused at startup).

### A plugin that drives the IFS (1.5)

For a multi-material engine of its own (Happy Hare, ...) on an IFS
running Klipper firmware (`/data/ad5x/ifs-klipper.enable`, set by the
owner as root; `docs/deviations-from-stock.md`). With `"owns_ifs": true`
in `plugin.json`:

- `ENABLE_PLUGIN` refuses it unless the IFS answered as Klipper at this
  boot, and while another plugin drives the IFS.
- While it is enabled, Kiln's IFS pins (`generic-flashforge-ifs.cfg`:
  `[mcu ifs]`, the feeder and selector steppers, drivers, sensors) are
  left out from the next Klipper start; the plugin's `plugin.cfg` brings
  its own `[mcu ifs]` and pins. They come back when it is disabled.
- Its `plugin.cfg` must set `[ifs]` `enable: False`: Kiln's IFS module
  then makes no `printer.ifs`, `printer.ifs_materials` or `IFS_*`
  commands (the section's other options, such as templates, are
  accepted and unused), and the setup wizard skips its IFS step.
  `PRINT_START` loads no first tool then (it checks `'ifs' in printer`);
  the slicer's tool change does.
- `T0`-`T3` (`ifs.cfg`) are Kiln's IFS swaps, and `UNLOAD_FILAMENT`
  (`macros/`) only retracts 50 mm without Kiln's IFS: the plugin replaces
  them with its own `[gcode_macro ...]` (plugins.cfg comes after both).
  Next version: `T0`-`T3` it leaves as they are stop with a message, as do
  `IFS_TUNE_RUN`, `IFS_TUNE_CLEAR`, `IFS_INFO`, `IFS_PURGE_TEST` and
  `IFS_PURGE_RESULT`; `RESUME_INTERRUPTED` restores no IFS slot, and the
  setup wizard's Z offset step with an empty toolhead asks to load it with
  the plugin.
- A plugin listed after it in `plugins.cfg` that defines `T0`-`T3` too
  replaces its tool changes. `bambufy-compat` does (its `T0`-`T3` drive
  Kiln's IFS); next version: they stop with a message then. Don't enable
  it together with such a plugin.
- Klipper stops with a config error naming the plugin when: two such
  plugins are enabled, the IFS doesn't answer as Klipper, `[ifs]` is still
  on, or `plugins.cfg` was edited by hand so the pins changed hands (then
  `RESTART` once: the pins are set for the next start).

## Config order

```
printer.cfg
  ad5x.cfg            factory defaults: hardware, stock behaviour (image)
    ifs.cfg           IFS and stock swap templates (image)
    setup.cfg         setup wizard (image)
      ad5x-tuning.cfg PID / shaper results (printer, optional)
    [ad5x_config]
    macros/*.cfg      editable defaults beyond stock, name order (printer, optional)
    [ad5x_plugins]
    plugins.cfg       enabled plugins, in file order (printer, optional)
  unit.cfg            per-printer calibration (printer)
  local.cfg           the user's overrides (printer)
  SAVE_CONFIG block
```

A plugin's options replace earlier values of the same section and
option, including those of the `macros/` files; `unit.cfg` and
`local.cfg` replace a plugin's. Without the `macros/` files the macros
marked "macros/" below don't exist and `PRINT_START` is the stock one
(`docs/config-layout.md`): check with `'gcode_macro _PRIME_LINE' in
printer` before calling one.

## Paths

| Path | |
|---|---|
| `/usr/share/ad5x/plugins/<name>` | Shipped plugins (read-only) |
| `/data/ad5x/plugins/<name>` | Installed plugins (user `klipper` owns the directory) |
| `/home/klipper/printer_data/config` | Config directory (= `/data/ad5x/printer_data/config`) |
| `.../config/plugins.cfg` | Enabled plugins |
| `.../config/variables.cfg` | `[save_variables]` file |
| `.../config/macros/*.cfg` | The printer's editable macros (refreshed by updates; `docs/config-layout.md`) |
| `/home/klipper/printer_data/gcodes` | G-code files (`virtual_sdcard`) |

## G-code commands and macros

### Print

| Command | Parameters | |
|---|---|---|
| `PRINT_START` | `BED=` `EXTRUDER=` (temperatures), `TOOL=` (first slicer tool, -1 none), `LEVEL=1|0` (new mesh / the stock Z check; default `mesh_every_print`, 0 in the factory one), `ADAPTIVE=0|1` (mesh only the print area; default `adaptive_mesh`, 0 in the factory one) | Home, heat, purge, brush, Z check or mesh, load the first tool or prime line (macros/ `print_start.cfg`; factory: the stock start) |
| `PRINT_END` | | Retract, lift, park, heaters/fans/motors off |
| `CANCEL_PRINT` | | Cancel, park, heaters and fans off |
| `PAUSE`, `RESUME`, `CLEAR_PAUSE` | Klipper's | |
| `_PRIME_LINE` | `FORCE=1` | Prime line in front of the print area (`variable_prime_line`); macros/ `prime_line.cfg` |
| `_PURGE_BOX` | | Into the purge box (no offsets applied) |
| `_PURGE_WIPE` | | Wipe on the box edge, ending outside |
| `_NOZZLE_BRUSH` | | Brush the nozzle across the box |
| `M106` / `M107` | `S` 0-255, `P`/`T` index (2, 101, 102 ignored) | Part fan (`fan_generic fanM106`) |
| `SET_GCODE_OFFSET` | Klipper's; `Z=`/`Z_ADJUST=` also saved as `zoffset` | Print Z offset |
| `BED_MESH_CALIBRATE` | Klipper's | Tares the strain gauges first, saves the centre Z after |
| `WEIGHT_TARE`, `LOAD_CELL_TARE` | | Zero the bed strain gauges |
| `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `CLEAR_NOZZLE`, `AUTO_FULL_BED_LEVEL` | as in macros/ `quick_actions.cfg` | Screen quick actions |
| `_PRINT_STATUS` | `MSG=` (none: clear) | Status line on the screen (`M117`) and the console |
| `M300` | `[S=Hz]` `[P=ms]` (1.4): a beep on the speaker |
| `PLAY_MIDI` | `FILE=` (1.4): a MIDI file from the config folder's `midi/` or the image's sounds |
| `PLAY_SOUND`, `SOUND_STOP` | `EVENT=` startup\|start\|complete\|error\|cancelled\|paused\|refill (1.4) |
| `SOUND_SETUP` | `[ENABLE=0\|1]` `[VOLUME=0-100]` `[<EVENT>=<file>\|0]` (1.4) |
| `BED_SOAK_CALIBRATE` | `BED=` `[POINTS=5\|1]` `[NOZZLE=140]` `[INTERVAL=]` `[STABLE=0.005]` `[WINDOW=120]` `[MAX=1500]` `[FORCE=1]` (1.4): measure the bed's settling after heating (`docs/print-start.md`) |
| `SET_NOZZLE_SIZE` | `SIZE=` 0.2\|0.25\|0.4\|0.6\|0.8\|1.0 `[RESTART=0]` (1.4): saved in `nozzle.cfg`, Klipper restarts |
| `SETUP_WIZARD_STEP STEP=pid HEATERS=` | `extruder`\|`bed`\|`both` (1.4; default both) |
| `BED_SOAK_ENABLE` | `[ENABLE=0\|1]` (1.4): the soak on/off for every print, saved |
| `BED_SOAK_START`, `BED_SOAK_WAIT` | `PRINT_START`'s soak (1.4; `BED=` `FROM=` `[SECONDS=]` `[MODE=time\|probe]` `[POINTS=]`) |
| `CONFIG_BACKUPS` | `ACK=1` (clear the notice) | List `macros/` files an update replaced and the backups of edited ones |
| `G10`, `G11`, `SET_RETRACTION` | Klipper's `[firmware_retraction]` | |
| `G2`, `G3`, `G17`-`G19` | Klipper's `[gcode_arcs]` | |

### IFS (`klipper/extras/ifs.py`)

| Command | Parameters |
|---|---|
| `T0`-`T3` | Load the slot the tool map names (macros in `ifs.cfg`) |
| `IFS_SWAP` | `CHANNEL=` `[TEMP=]` `[FLUSH=mm]` `[ROUNDS=]` `[PURGE=0|1]` |
| `IFS_LOAD` | `SLOT=` `[TEMP=]` `[PURGE=0|1]` |
| `IFS_UNLOAD` | `[SLOT=]` `[TEMP=]` |
| `IFS_EJECT` | `SLOT=` |
| `IFS_MAP_TOOL` | `TOOL=` `SLOT=`, or `RESET=1` |
| `IFS_SET_MATERIAL` | `SLOT=` `[TYPE=]` `[COLOR=]` `[TEMP=]` |
| `IFS_SET_COLOR` | `CHANNEL=` `COLOR=` |
| `IFS_SET_CHANNEL` | `CHANNEL=` (0 = none loaded) |
| `IFS_STATUS`, `IFS_MATERIALS`, `IFS_STOP`, `IFS_RESET_DRIVER` | |
| `IFS_AUTO_REFILL` | `[ENABLE=0|1]` (1.2) `[MATCH=exact|similar|any]` (1.4) |
| `IFS_PURGE_TEST`, `IFS_PURGE_RESULT`, `IFS_SET_FLUSH` | Purge tuning |
| `IFS_TUNE`, `IFS_TUNE_RESET` | Swap tuning |

Swap templates in `[ifs]` a plugin may replace (same parameters):
`before_gcode` (`OLD`, `NEW`), `cut_gcode` (`OLD`, `NEW`; next version:
`AT_PRINT=1` when the swap primes at the print: go back to the print
position, before_gcode's saved state `ifs_swap`, instead of the box),
`unload_gcode` (`OLD`, `NEW`, `LENGTH`, `SPEED`, `RETRACT`: 1 when the template retracts the extruder, 0 on IFS Klipper firmware where the module retracts it with the feeder), `purge_start_gcode`
(`OLD`, `NEW`, `ROUND`, `ROUNDS`), `purge_gcode` (`OLD`, `NEW`,
`ROUND`, `ROUNDS`, `FLUSH`, `FLUSH_SPEED`), `prime_gcode` (`OLD`,
`NEW`; in macros/ `ifs_templates.cfg`), `prime_at_print_gcode` (`OLD`,
`NEW`; next version, in macros/ `ifs_templates.cfg`: after a prime at the
print position, instead of `prime_gcode`), `after_gcode` (`OLD`, `NEW`).
A later definition replaces a whole template. Templates must not call
`IFS_*` commands. Options a plugin may set: `purge_mode_variable`,
`prime_length`, `prime_at_print` (next version), and the documented
lengths, speeds and timeouts in `ifs.cfg`.

Purge decision of a swap: `PURGE=` if given; else, while
`print_stats.state` is `printing` and `purge_mode_variable` is set, that
save variable: 0 or 2 = prime only, other = purge; else purge. A swap
that only primes does it at the print position (no `purge_start_gcode`)
when `prime_at_print` is on, the variable is 0, `print_stats.info.current_layer`
is 2 or more, the toolhead had filament to cut, and `exclude_object` lists
objects with outlines, none of them current, the print position at least
5 mm outside each outline's bounding box; else at the box.

### Power-loss recovery (`klipper/extras/ad5x_resume.py`, 1.2)

| Command | |
|---|---|
| `RESUME_INTERRUPTED` | `CONFIRM=1`: continue the print a power cut ended |
| `CLEAR_INTERRUPTED` | Forget it |

### Setup wizard and plugins

| Command | |
|---|---|
| `SETUP_WIZARD_STEP` | `STEP=selfcheck|pid|mesh|shaper|ifs|zoffset|finish`, `ACTION=start|abort|adjust|accept|wizard` (`docs/setup-wizard.md`); API endpoint `ad5x_setup/control` |
| `SETUP_WIZARD` | Run the wizard again on the screen (macros/ `quick_actions.cfg`; `SETUP_WIZARD_STEP ACTION=wizard` does the same) |
| `ENABLE_PLUGIN`, `DISABLE_PLUGIN` | `NAME=` `[RESTART=0]` |
| `LIST_PLUGINS` | |
| `INSTALL_PLUGIN` | `NAME=` (a catalog plugin) `[ENABLE=1]` (1.4) |
| `UPDATE_PLUGIN`, `REMOVE_PLUGIN` | `NAME=` (a plugin in `/data/ad5x/plugins`) (1.4) |

## Printer objects and status fields

| Object | Fields |
|---|---|
| `printer.ifs` | `connected`, `version`, `busy`, `channel` (loaded, 0 none), `state`, `selected`, `inserted[4]`, `colors[4]`, `channel_count`, `active_channel`, `loaded_channels`, `pending_insert_channels`, `activity`, `activity_channel`, `error`, `tool_map` (`"0"`-`"3"` -> slot), `tune`, `auto_refill`, `refill` (1.2: last auto-refill message), `refill_match`, `refill_backups` (`"1"`-`"4"` -> the slots that would take over, nearest colour first; `[]` none), `refill_notice` (a print loaded a slot with no backup; "" otherwise) (1.4); next version: `mode` (`mcu`/`serial`), `operation`, `phase`, `target_channel`, `error_channel`, `tune.flush` (`docs/helixscreen-integration.md`, section 0) |
| `printer.ad5x_nozzle` | `size` (running), `saved` (nozzle.cfg, null), `local` (local.cfg sets it), `sizes` (1.4) |
| `printer.ad5x_sound` | `speaker`, `enabled`, `volume`, `events` (event -> file, "" off), `files`, `playing` (1.4) |
| `printer.ad5x_soak` | `enabled`, `calibration` (1.4: per bed temperature `settle`, `drift`, `warp`, `points`, `from`, `stable`, `date`), `running`, `soak`, `last` |
| `printer.ad5x_resume` | `available`, `file`, `z`, `time` (1.2: an interrupted print) |
| `printer.ifs_materials` | `available`, `channel_count`, `slots` (`"1"`-`"4"`: `type`, `color`, `temp`), `loaded`, `temperatures` |
| `printer.ad5x_setup` | `step`, `state`, `message`, `progress`, `results`, `checks`, `pending_save`, `zoffset` |
| `printer.ad5x_config` | `notices` (lines of `config-updates.txt`), `backups` (`macros/*.bak-*`) |
| `printer.ad5x_plugins` | `api_version`, `enabled`, `available` (per plugin: `source`, `description`, `version`, `author`, `url`, `requires_os`, `compatible`, `owns_ifs` (1.5)), `ifs_owner` (1.5: the plugin driving the IFS at this start, "" Kiln's `[ifs]`), `catalog` (1.4, per plugin: `title`, `description`, `url`, `requires_os`, `compatible`, `installed`), `job` (1.4: `name`, `action`, `state` idle/running/done/failed, `message`), `warnings` |
| `printer.ad5x_weight` | `connected`, `weight` |
| `printer['gcode_macro _AD5X_UNIT']` | `z_offset`, `cut_x_offset`, `cut_y_offset`, `x_offset`, `y_offset` (purge box at X 52.5 + `x_offset`, Y 229 + `y_offset`; cut at X `cut_x_offset` - 2.5, Y `cut_y_offset` - 7.5) |
| `printer['filament_switch_sensor toolhead']` | Klipper's runout fields (`enabled`, `filament_detected`); also `adc_filament_sensor toolhead`; `SET_FILAMENT_SENSOR SENSOR=toolhead` |
| `printer['fan_generic fanM106']`, `printer['fan_generic pcb_fan']` | Part fan, board fan |
| `printer['led chamber_led']` | Chamber light (`SET_LED LED=chamber_led WHITE=`) |
| `printer['temperature_sensor filamentValue']`, `printer['temperature_sensor cutValue']` | Toolhead filament and cutter ADCs (`QUERY_ADC`) |
| `printer['gcode_macro PRINT_START']` | `mesh_every_print`, `adaptive_mesh`, `retract` (with macros/ `print_start.cfg`) |
| `printer['gcode_macro _PRIME_LINE']` | `prime_line`, `length`, `height`, `width` (0 = 2.5 x nozzle), `gap`, `flow`, `speed`, `unretract`, `prime`, `prime_speed`, `margin`, `wipe`, `retract` (with macros/ `prime_line.cfg`) |

Save variables (`printer.save_variables.variables`): `ifs_loaded`,
`ifs_materials`, `zoffset` (`{'z': ..}`), `ad5x_center_z`,
`use_trash_on_print` (nopoop), the `IFS_TUNE` values (`ifs_speed`,
`ifs_load_dist_<n>`, `ifs_unload_dist`, `ifs_tube_unload`, `ifs_flush`).
Read them; write only your own (prefixed) variables, except
`use_trash_on_print`.

## Python extras

- Loaded by `[ad5x_plugins]` as `extras.<module>`, only for enabled,
  compatible plugins; `load_config(config)` / `load_config_prefix(config)`
  as for any Klipper module (`docs/plugins.md`, "Python extras").
- 1.5: `extras/` may hold packages (`extras/<name>/__init__.py`); the
  plugin's modules import each other as Klipper's do (`from .mylib import
  x`), and `printer.load_object(config, '<module> <name>')` also finds
  plugin modules.
- Klipper is mainline (`KLIPPER_DESCRIBE` in `buildroot/package/klipper`,
  v0.13.0-827 now); its
  module interfaces are Klipper's, not part of this API's promise. Python
  3 is the image's (3.14 now); no compiler on the printer, no pip.
- Our modules' Python classes (`ifs.IFS`, ...) are internal: use their
  commands and status fields.
- Events (`printer.register_event_handler`): `"ifs:loaded"` (1.2), with
  the slot now in the nozzle (1-4, 0 = emptied), after every load,
  unload, swap and `IFS_SET_CHANNEL`.

## Moonraker

A plugin's `moonraker.conf` is included after the printer's
`moonraker.conf` while the plugin is enabled (`docs/plugins.md`,
"Moonraker parts"). Moonraker v0.11.0, `[machine] provider: none` (no
service restarts), no package manager.
