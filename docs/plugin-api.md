# Plugin API

What a plugin (`docs/plugins.md`) may rely on, and how that is versioned.
Every command, macro, status field, config option and file listed here
has a **since** version: the plugin API version from which every Kiln OS
release has it. Everything not listed here is internal and may change
with any system update ("Public and internal names" below).

## Version

Current: **1.9**.

- In Klipper: `printer.ad5x_plugins.api_version` (also printed by
  `LIST_PLUGINS`).
- On the system: `AD5X_PLUGIN_API="1.9"` in `/usr/lib/os-release`
  (`/etc/os-release`), for scripts.
- In the code: `PLUGIN_API_VERSION` in `klipper/extras/ad5x_plugins.py`
  (the build copies it to os-release). `tools/test_plugin_api_doc.py`
  checks that every command and status field of Kiln's Klipper modules
  is listed on this page or marked internal there.

Rules for system updates:

- **Minor** (1.4 -> 1.5): additions only (new commands, parameters,
  status fields, macros). Nothing listed here changes meaning or goes
  away. From 1.6 on, every addition raises the minor version (one exception, 1.9\*, below).
- **Major** (1.x -> 2.0): something listed here changed or was removed;
  "Changes" below lists what. Plugins built for 1.x are refused until
  updated.

A plugin states the version it was written for in `plugin.json`,
`requires_os: "1.0"`. It is accepted when the major numbers are equal and
the system's minor is the same or newer: `1.0` runs on 1.0, 1.3; not on
0.9 or 2.0. Without `requires_os` it is accepted (not recommended). Put
the highest **since** of what your plugin uses there.

`ENABLE_PLUGIN` refuses an incompatible plugin. Each time Klipper starts
(boot, `RESTART`, `FIRMWARE_RESTART`) an enabled plugin that can't run is
skipped entirely: its `plugin.cfg`, Python extras and Moonraker part are
not loaded, and Klipper shows one warning naming the plugin and the
reason. That is a plugin that is incompatible (enabled before an update
that made it so), missing, has a bad `plugin.json` or a `plugin.cfg`
Klipper can't parse, `requires` a plugin that isn't loaded (off, or
skipped itself), `conflicts` with a plugin listed before it in
`plugins.cfg`, or drives the IFS (`owns_ifs`) while the IFS isn't on
Klipper firmware or a plugin listed before it drives it already ("A
plugin that drives the IFS"). Its line stays in
`plugins.cfg` (`DISABLE_PLUGIN` removes it); `docs/plugins.md`, "How
they are loaded".

### History

| Version | Date | First release | What came |
|---|---|---|---|
| 1.0 | 2026-10-16 | (none) | The plugin layout, `plugin.json`, the commands, macros and status fields marked 1.0 |
| 1.1 | 2026-10-16 | v0.0.1 | Factory/user config split (`docs/config-layout.md`): the `macros/` files in the config order, `CONFIG_BACKUPS`, `printer.ad5x_config`, `PRINT_START`'s `mesh_every_print` and `retract`, `_PRIME_LINE`'s variables. The macros marked "macros/" now live in the printer's editable `macros/` files, with the same names and parameters |
| 1.2 | 2026-10-19 | v0.0.5 | The Klipper event `ifs:loaded`, IFS auto-refill, power-loss recovery |
| 1.3 | 2026-10-20 | v0.0.6 | A plugin's `python/` libraries and `moonraker/components/`, `git` on the printer |
| 1.4 | 2026-10-20 | v0.0.7 | The plugin catalog (`INSTALL_PLUGIN`, `UPDATE_PLUGIN`, `REMOVE_PLUGIN`), Moonraker restarted by a switch, the bed heat soak, the speaker, the nozzle size, auto-refill colour matching |
| 1.5 | 2026-11-07 | v0.0.49 | A plugin that drives the IFS (`owns_ifs`), packages in `extras/`, `printer.load_object()` finding plugin modules; and everything the 1.4 releases added after v0.0.7 that this page now lists (tool map mode, Z offset estimate, IFS operation status, swap abort template, ...) |
| 1.6 | 2026-11-13 | v0.1.0-rc1 | Root scripts like zMod's plugins have (`root/install.sh`, `update.sh`, `uninstall.sh`, `docs/plugin-root-hooks.md`), `ENABLE_PLUGIN ROOT=1`, `INSTALL_PLUGIN ROOT=1`, `printer.ad5x_plugins` `available.<name>.root` and `root_installed`, the job actions `root install`/`root update`/`root uninstall`; warnings when two plugins bring the same Moonraker component, `python/` package or Klipper section ("Names"); `kiln_` and `ad5x_` module, component, section and macro names refused for plugins that are not Kiln's own ("Names"); Moonraker's `[machine] provider: kiln_agent` (service restarts, "Moonraker"). The named root actions are removed ("Changes") |
| 1.7 | 2026-11-16 | v1.0.0-rc3 | Klipper module names with capitals (`extras/AFC_lane.py`; names that differ only in case count as one, also for the `kiln_`/`ad5x_` rule); `plugin.json` `module_dirs`: more Klipper module folders inside the plugin (a checkout of another project), imported when needed as Klipper imports its own ("Plugin layout", "Module folders"); `INSTALL_PLUGIN` and `UPDATE_PLUGIN` fetch the plugin's git submodules, https only ("Submodules"); `BED_MESH_CALIBRATE`, `LINE_PURGE` and `VORON_PURGE` skipped after `PRINT_START`'s mesh / prime line (or the same step already run) in the same print, `FORCE=1` (issue #73) |
| 1.8 | 2026-11-18 | v1.0.0-rc4 | Extended memory mode on printers with 512 MiB (`docs/memory.md`): the macro `KILN_MEMORY_MODE [ENABLE=0\|1]` (macros/ `system.cfg`), Moonraker's `GET`/`POST /machine/kiln_os/memory` and `POST /machine/kiln_os/memory_notice_seen` and the feature name `memory_mode` (`docs/api.md`); the IFS firmware switch: Moonraker's `GET`/`POST /machine/kiln_os/ifs_firmware`, the feature name `ifs_firmware` and the owner's opt-in `/data/ad5x/ifs-switch.enable` ("A plugin that drives the IFS"); bed screws: `[screws_tilt_adjust]`, `SCREWS_TILT_CALCULATE` with tare and the macro `BED_LEVEL_SCREWS_TUNE` (macros/ `quick_actions.cfg`, issue #69) |
| 1.9 | 2026-11-18 | v1.0.0-rc5 | The setup wizard's filament step (`SETUP_WIZARD_STEP STEP=filament`, `MATERIAL_<n>=`, `HEAD=`), `printer.ad5x_setup` `action`, `action_arg`, `step_started`, `prompt`, `filament`, `zoffset_plan`; `IFS_FIND_HEAD_SLOT`, `printer.ifs` `find_result`, `head_found`, `tube_blocked`, `loaded_source` (a slot only adopted at startup is a guess: `IFS_SWAP` to it loads it again, its unload is checked, the find and the wizard don't trust it). A Z offset step ends after a second `accept` (the test print is off the bed). `HOME=1` on `IFS_LOAD`, `IFS_UNLOAD`, `IFS_SWAP`, `IFS_EJECT`, `IFS_FIND_HEAD_SLOT`, `IFS_TUNE`: an idle printer that isn't homed homes first instead of the error, `printer.ifs` `phase` `homing_printer` meanwhile |

**1.5\*** marks the few items that came with a later 1.5 release:
`LOG_MODE` and `printer.ad5x_log` (v0.0.53), `printer.ad5x_soak.cancel`
(v0.0.60), and in the release after v0.0.60: `_PURGE_BOX_POS` and Kiln's
IFS macros stopping with a message while a plugin drives the IFS. A
plugin that uses them and must also run on an early 1.5 release checks
first (`'ad5x_log' in printer`, `'cancel' in printer.ad5x_soak`,
`'gcode_macro _PURGE_BOX_POS' in printer`).

**1.9\***: `HOME=1` on the IFS commands and `printer.ifs` `phase`
`homing_printer` came with v1.0.0-rc6, after 1.9 first shipped in rc5. A
plugin that uses them and must also run on rc5 checks first that the
printer knows the phase (v1.0.0 and later all do).

### Changes

- `_PRIME_LINE` `variable_unretract` (1.1) was renamed `variable_owed`
  in Kiln OS v0.0.30 (the retraction the start left, put back first, then
  cleared). A plugin or `local.cfg` that set `unretract` sets `owed`.
- 1.6: the named root actions (`plugin.json` `root_actions`,
  `DEV_ROOT_REQUEST`, `DEV_ROOT_STATUS`, a developer feature outside the
  version promise) are removed; root scripts (`root/`,
  `docs/plugin-root-hooks.md`) replace them. No plugin used them, so this
  is a minor version.

## Plugin layout

A plugin is a directory named like the plugin (`a-z`, `0-9`, `-`, `_`;
starts with a letter or digit; at most 48 characters; "Names" below):

```
myplugin/                 the git repository; cloned as /data/ad5x/plugins/myplugin
  plugin.json             metadata (required)
  plugin.cfg              Klipper config (required, may be only comments)
  README.md               what it does, how to use it
  extras/                 optional: Klipper modules
    myplugin_led.py
    myplugin_lib/         optional (1.5): a package (__init__.py), imported as extras.myplugin_lib
  moonraker.conf          optional: Moonraker sections (update manager, ...)
  python/                 optional (1.3): pure-Python libraries the plugin needs
  moonraker/components/   optional (1.3): Moonraker components (name.py)
  root/                   optional (1.6): scripts that run as root (docs/plugin-root-hooks.md)
    install.sh              on ENABLE_PLUGIN ROOT=1, before the plugin is on
    update.sh               after an update that changed root/
    uninstall.sh            on DISABLE_PLUGIN / REMOVE_PLUGIN
  vendor/extras/          optional (1.7): more Klipper modules, listed in plugin.json module_dirs
```

The clone's directory name must match `name` in `plugin.json`
(`git clone <url> myplugin`).

Klipper module names are letters, digits and `_`, starting with a letter;
since 1.7 they may have capitals, as other projects' modules do
(`AFC_lane.py`, section `[AFC_lane lane1]`). Two names that differ only
in case count as one name: `Heaters.py` has the name of Klipper's
`heaters`, and `AFC_Lane.py` next to `AFC_lane.py` is the same module
twice. Plugins that use capitals need `"requires_os": "1.7"`.

**Module folders (`module_dirs`, 1.7).** A plugin that runs another
project's Klipper modules (AFC-Klipper-Add-On, cloned into the plugin
folder at a pinned commit) lists their folder in `plugin.json`:

```json
  "module_dirs": ["AFC-Klipper-Add-On/extras"]
```

Each folder joins the `extras` package path like the plugin's own
`extras/`, so its modules import each other (`from extras.AFC_utils import
...`) and `printer.load_object()` finds them. Unlike `extras/`, their
modules are imported the way Klipper imports its own: only when a config
section names one (`[AFC]`, `[AFC_stepper lane1]`, in `plugin.cfg` or
the user's config), `printer.load_object()` asks for one, or another
module imports it. Modules for hardware the printer doesn't have are
never imported. The same name rules apply: a module named like a Klipper
module or another module of an enabled plugin (in any case) stops
Klipper, and `kiln_`/`ad5x_` names are refused ("Names").

The folders are paths inside the plugin, `/` between folders: each part
letters, digits, `_`, `-` and `.`, not starting with `.` (so no `..` and
no hidden folders); not `extras`, `python`, `moonraker` or `root` or a
folder in them, which have their own use; at most 8. Anything else makes
`plugin.json` invalid, and the plugin can't be enabled. A folder that
isn't there (yet) gives a warning and the rest of the plugin loads; a
`RESTART` picks its modules up once it is. A folder, or a module in it,
that is a link leading out of the plugin's folder is not read (a
warning). Plugins that use `module_dirs` need `"requires_os": "1.7"`: an
older Kiln OS ignores the field and loads the plugin without these
modules.

**Submodules (1.7).** The other project can be a git submodule of the
plugin's repository (`git submodule add
https://github.com/ArmoredTurtle/AFC-Klipper-Add-On.git`, then
`"module_dirs": ["AFC-Klipper-Add-On/extras"]`). `INSTALL_PLUGIN` and
`UPDATE_PLUGIN` then run `git submodule update --init --recursive` after
the clone or pull, in the same background job, so the modules are there
before Klipper's first start and no network is needed then (a plugin
clone made shallow by hand gets shallow submodules). Rules, checked before anything is
fetched:

- URLs in `.gitmodules` are `https://`, or relative (`../other.git`),
  resolved against the plugin's own URL and staying on its host.
  `ssh://`, `git@host:`, `git://`, `http://`, `file://`, local paths and
  `ext::` are refused, and git itself is allowed no transport but https
  for the submodules and theirs (nested ones are fetched under the same
  rule).
- Submodule paths are folders inside the plugin (no `..`, nothing in
  `.git`); `update = !command` is refused.
- A failure (a refused URL, no network, a commit the submodule's
  repository doesn't have) fails the job: `INSTALL_PLUGIN` leaves
  nothing installed, `UPDATE_PLUGIN` puts the version from before the
  pull back (`git reset --keep`, its submodules as they were). Klipper
  restarts after an update only when the plugin is on and the plugin or
  its submodules changed.
- `UPDATE_PLUGIN` on a plugin with nothing new still fetches submodules
  that are missing (a plugin installed before it had them).
- `REMOVE_PLUGIN` deletes them with the plugin's folder (their git data
  is in its `.git/modules`).

Moonraker's update manager (`type: git_repo`) doesn't update submodules:
for a plugin with submodules, update with `UPDATE_PLUGIN` (Settings >
Plugins on the touch screen). Plugins with submodules need
`"requires_os": "1.7"`: an older Kiln OS clones the plugin without them.

`plugin.json`:

```json
{
  "name": "myplugin",
  "description": "One line for LIST_PLUGINS",
  "version": "1.2.0",
  "author": "Someone",
  "url": "https://github.com/someone/myplugin",
  "requires_os": "1.0",
  "requires": ["zmod-compat"],
  "conflicts": ["other-plugin"]
}
```

| Field | Required | Meaning | Since |
|---|---|---|---|
| `name` | yes (`tools/check_plugin.py` requires it; the printer uses the folder name when it is missing) | Same as the directory name | 1.0 |
| `description` | no | Shown by `LIST_PLUGINS` | 1.0 |
| `version` | no | Free text, shown by `LIST_PLUGINS` | 1.0 |
| `author`, `url` | no | Shown / available in `printer.ad5x_plugins` | 1.0 |
| `requires_os` | recommended | Plugin API version written for, `major.minor` | 1.0 |
| `requires` | no | Plugins that must be enabled first | 1.0 |
| `conflicts` | no | Plugins that can't be enabled together with this one | 1.0 |
| `owns_ifs` | no | `true`: the plugin drives the IFS instead of Kiln's `[ifs]` module ("A plugin that drives the IFS") | 1.5 |
| `module_dirs` | no | More folders of Klipper modules inside the plugin, relative to it (`["AFC-Klipper-Add-On/extras"]`, at most 8; no `..`, not in `extras`, `python`, `moonraker` or `root`). For code from another project that the plugin carries or fetches; see "Module folders" above | 1.7 |

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

## Names

Kiln OS keeps these prefixes for itself and its own plugins (the shipped
ones and the catalog's): `kiln`, `ad5x` (any case, followed by `_`, `-`
or nothing) for plugin names, macros, commands, Klipper modules and
sections, Moonraker components, `python/` packages and save variables. A
plugin of yours doesn't use them, so a later system update can't take
its names.

The plugin manager enforces the `kiln_` and `ad5x_` prefixes for the names
it reads from a plugin's files. A plugin using one of them can't be
enabled (`ENABLE_PLUGIN` refuses it, `LIST_PLUGINS` shows why) and is
skipped if `plugins.cfg` names it; `tools/check_plugin.py` reports each
name as an error:

| Name | Refused | Since |
|---|---|---|
| Klipper modules | `extras/kiln_*.py`, `extras/ad5x_*.py` and packages of these names; 1.7: any case (`Kiln_x.py`), and in `module_dirs` too | 1.6 |
| Moonraker components | `moonraker/components/kiln_*.py`, `ad5x_*.py` and packages; 1.7: any case | 1.6 |
| Config sections in `plugin.cfg` | `[kiln_...]`, `[ad5x_...]`, also with a name after it (`[ad5x_log]`, `[kiln_x two]`) | 1.6 |
| Macros in `plugin.cfg` | `[gcode_macro KILN_...]`, `[gcode_macro AD5X_...]`, any case, also with leading `_` (`_AD5X_UNIT`) | 1.6 |

Kiln's own plugins may use them: the shipped ones (`klipper/plugins/`)
and the catalog's plugins from Kiln's own repositories (a catalog `url`
starting with `https://github.com/djvalic/kiln-`, such as `kiln-notify`
with its `kiln_notify` component). A catalog plugin is known by its name,
so don't name your plugin like one. `tools/check_plugin.py --official`
checks a Kiln plugin that is not in the catalog yet.

Prefix everything of your own with your plugin's name:

| What | Your name | Example |
|---|---|---|
| Macros and commands | `MYPLUGIN_...`; helpers `_MYPLUGIN_...` | `MYPLUGIN_IDLE_LIGHT` |
| Klipper modules (`extras/`) and their sections | `myplugin_...` | `[myplugin_led]` |
| Moonraker components | `myplugin...` | `myplugin.py`, `[myplugin]` |
| `python/` packages | `myplugin...` (not a common library name: that one may arrive with the image later) | `myplugin_util/` |
| Save variables | `myplugin_...` | `SAVE_VARIABLE VARIABLE=myplugin_level` |

When two names meet anyway:

| Collision | What happens |
|---|---|
| A plugin in `/data/ad5x/plugins` named like a shipped one | Yours replaces the shipped one (`LIST_PLUGINS` shows `user`) |
| An `extras/` or `module_dirs` module named like a Klipper module, one of Kiln's, or another enabled plugin's (1.7: in any case) | Klipper stops with a config error naming the plugin |
| A G-code command a module registers twice (two plugins, or a plugin and Kiln) | Klipper stops (`gcode command ... already registered`) |
| A section two plugins define (`[gcode_macro X]`, `[ifs]`, ...) | Klipper merges them: the plugin later in `plugins.cfg` replaces the earlier one's options (a `gcode:` entirely). Klipper warns, unless the later plugin `requires` the earlier one (then it is meant) |
| A section a plugin shares with Kiln's config (`ad5x.cfg`, `ifs.cfg`, `macros/`) | Merged, the plugin's options win: that is how a plugin changes a default ("Config order"). No warning |
| A Moonraker component two plugins have | Moonraker's own components (also Kiln's `kiln_os`, `kiln_lanes`) come first, then the first plugin in `plugins.cfg`; the others' are not loaded. Klipper warns |
| A `python/` package two plugins have | The image's libraries come first, then the first plugin in `plugins.cfg`. Klipper warns |
| A save variable two plugins write | Nothing stops it: the last write wins. Use your prefix |

The warnings are Klipper's startup warnings (Fluidd, Mainsail and the
screen show them) and `printer.ad5x_plugins.warnings`.

## Rules for plugins

- Klipper merges sections of the same name from different files, so a
  `[gcode_macro PRINT_START]` in a plugin replaces options of ours (its
  `gcode:` replaces ours entirely); `rename_existing` can't wrap a macro
  that is itself defined in config. It does work for commands registered
  by Python modules (`SET_PRINT_STATS_INFO`, `M104`, `IFS_SWAP`, ...).
  Prefer new commands of your own over replacing listed macros; a plugin
  that replaces one takes over its upkeep.
- Don't redefine sections that belong to each printer's own calibration
  (`[gcode_macro _AD5X_UNIT]`), and don't write to files outside the
  config directory.
- Call only public commands and macros ("Public and internal names");
  read only the status fields listed here.

### A plugin that drives the IFS (1.5)

For a multi-material engine of its own (Happy Hare, ...) on an IFS
running Klipper firmware (`/data/ad5x/ifs-klipper.enable`, set by the
owner as root; `docs/deviations-from-stock.md`). From 1.8 the owner can
also turn on the IFS firmware switch instead (`/data/ad5x/ifs-switch.enable`;
Settings > Devices > IFS firmware, `docs/mcu-flashing.md`), which writes
Klipper's firmware and the enable file itself. A plugin's
`root/install.sh` may create `ifs-switch.enable` (the owner allows root
scripts with `ROOT=1`); it must not flash the IFS itself. With
`"owns_ifs": true` in `plugin.json`:

- `ENABLE_PLUGIN` refuses it unless the IFS answered as Klipper at this
  boot, and while another plugin drives the IFS (the message names both
  and which one to disable).
- Only one plugin drives the IFS. With two enabled anyway (`plugins.cfg`
  edited by hand), the first one in `plugins.cfg` drives it and the
  second is skipped at each Klipper start, like a `conflicts` plugin,
  with one warning naming both; Klipper starts.
- Enabled while the IFS didn't answer as Klipper at this boot (no
  `ifs-klipper.enable`, the IFS back on Flashforge's firmware, or it
  didn't answer), it is skipped at each Klipper start, with one warning
  that says why and how to turn the Klipper IFS on (or `DISABLE_PLUGIN`).
  The printer then works as if the plugin were off: Kiln's `[ifs]`
  module runs the IFS, and so does a plugin that `requires` it get
  skipped. S61klipper, Klipper and Moonraker's plugin list decide this
  from the same record (`/run/ad5x/ifs-klipper`, written at boot).
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
- 1.5\*: `T0`-`T3` it leaves as they are stop with a message, as do
  `IFS_TUNE_RUN`, `IFS_TUNE_CLEAR`, `IFS_INFO`, `IFS_PURGE_TEST` and
  `IFS_PURGE_RESULT`; `RESUME_INTERRUPTED` restores no IFS slot, and the
  setup wizard's Z offset step with an empty toolhead asks to load it with
  the plugin.
- A plugin listed after it in `plugins.cfg` that defines `T0`-`T3` too
  replaces its tool changes (Klipper warns, "Names"). `bambufy-compat`
  does (its `T0`-`T3` drive Kiln's IFS; 1.5\*: they stop with a message
  then). Don't enable it together with such a plugin.
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
    plugins-active.cfg  plugins.cfg without the skipped plugins: enabled
                      plugins, in file order (printer, generated)
  unit.cfg            per-printer calibration (printer)
  local.cfg           your own overrides (printer)
  SAVE_CONFIG block
```

A plugin's options replace earlier values of the same section and
option, including those of the `macros/` files; `unit.cfg` and
`local.cfg` replace a plugin's. Without the `macros/` files (1.1) the
macros marked "macros/" below don't exist and `PRINT_START` is the stock
one (`docs/config-layout.md`): check with `'gcode_macro _PRIME_LINE' in
printer` before calling one.

## Paths

| Path | | Since |
|---|---|---|
| `/usr/share/ad5x/plugins/<name>` | Shipped plugins (read-only) | 1.0 |
| `/data/ad5x/plugins/<name>` | Installed plugins (user `klipper` owns the directory). Files user `klipper` can't write show read-only in Fluidd (`chown -R klipper:klipper` makes them editable), as does a plugin with a `type: git_repo` update entry while it is enabled (`docs/plugins.md`) | 1.0 |
| `/home/klipper/printer_data/config` | Config directory (= `/data/ad5x/printer_data/config`) | 1.0 |
| `.../config/plugins.cfg` | Enabled plugins | 1.0 |
| `.../config/plugins-active.cfg` | What Klipper reads: `plugins.cfg` with the skipped plugins left out (generated) | 1.5 |
| `.../config/variables.cfg` | `[save_variables]` file | 1.0 |
| `.../config/macros/*.cfg` | The printer's editable macros (refreshed by updates; `docs/config-layout.md`) | 1.1 |
| `/home/klipper/printer_data/gcodes` | G-code files (`virtual_sdcard`) | 1.0 |

## G-code commands and macros

"macros/": a macro in the printer's editable `macros/` files (1.1).

### Print

| Command | Parameters | What | Since |
|---|---|---|---|
| `PRINT_START` | `BED=` `EXTRUDER=` (temperatures), `TOOL=` (first slicer tool, -1 none), `LEVEL=1\|0` (new mesh / the stock Z check; default `mesh_every_print`, 0 in the factory one), `ADAPTIVE=0\|1` (mesh only the print area; default `adaptive_mesh`, 0 in the factory one); 1.4: `SOAK=` (bed heat soak seconds, 0 none) | Home, heat, purge, brush, Z check or mesh, load the first tool or prime line (macros/ `print_start.cfg`; factory: the stock start) | 1.0 |
| `PRINT_END` | | Retract, lift, park, heaters/fans/motors off | 1.0 |
| `CANCEL_PRINT` | | Cancel, park, heaters and fans off | 1.0 |
| `PAUSE`, `RESUME`, `CLEAR_PAUSE` | Klipper's | | 1.0 |
| `_PRIME_LINE` | `FORCE=1` | Prime line in front of the print area (`variable_prime_line`); macros/ `prime_line.cfg` | 1.0 |
| `_PURGE_BOX` | | Into the purge box (no offsets applied) | 1.0 |
| `_PURGE_WIPE` | | Wipe on the box edge, ending outside | 1.0 |
| `_NOZZLE_BRUSH` | | Brush the nozzle across the box | 1.0 |
| `TRASH_OFFSET` | `X=` `Y=` (mm from the factory spot, -10..10 / -14..2), `DX=` `DY=` (added), `[MOVE=1]`, or `RESET=1` (back to unit.cfg's) | Move the purge box spot, saved; shows it without parameters | 1.5 |
| `M106` / `M107` | `S` 0-255, `P`/`T` index (2, 101, 102 ignored) | Part fan (`fan_generic fanM106`) | 1.0 |
| `M900` | `K=` `[E=]` | Pressure advance, Marlin style | 1.0 |
| `SET_GCODE_OFFSET` | Klipper's; `Z=`/`Z_ADJUST=` also saved as `zoffset` | Print Z offset | 1.0 |
| `BED_MESH_CALIBRATE` | Klipper's; 1.7: `FORCE=1` | Tares the strain gauges first, saves the centre Z after; 1.7: while a print runs, skipped after `PRINT_START`'s mesh (or another mesh) of that print (a console line says so) unless `FORCE=1`, `PROFILE=` or `ADAPTIVE=0` (issue #73) | 1.0 |
| `LINE_PURGE`, `VORON_PURGE` | `FORCE=1` | The zmod-compat plugin's (or another config's) purge line; Kiln adds: while a print runs, skipped after `PRINT_START`'s prime line or another of these that ran in that print, unless `FORCE=1` (issue #73). Only there when a plugin or config defines it | 1.7 |
| `SAVE_CONFIG` | Klipper's | PID and input shaper results go to `ad5x-tuning.cfg`, a probe `z_offset` becomes the saved print Z offset; the rest as Klipper | 1.5 |
| `WEIGHT_TARE`, `LOAD_CELL_TARE` | | Zero the bed strain gauges | 1.0 |
| `Z_OFFSET_ESTIMATE` | `[X=]` `[Y=]` `[MAX_FORCE=]` `[STEP=]` `[CLEAN=0]` `[SAVE=1]` | Estimate the print Z offset from the bed load cells (homed first); result in `printer.ad5x_zestimate`; `SAVE=1` sets it when the fit is good | 1.5 |
| `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `CLEAR_NOZZLE`, `AUTO_FULL_BED_LEVEL` | as in macros/ `quick_actions.cfg` | Screen quick actions | 1.0 |
| `SCREWS_TILT_CALCULATE` | Klipper's (`DIRECTION=`, `MAX_DEVIATION=`, ...) | Probe at the four bed screws (`[screws_tilt_adjust]` in `ad5x.cfg`) and show the turns; tares the strain gauges over screw1 and makes one uncounted `PROBE` there first, refuses when not homed; results in Klipper's `printer.screws_tilt_adjust` | 1.8 |
| `BED_LEVEL_SCREWS_TUNE` | `BED_TEMP=` (80), `EXTRUDER_TEMP=` (130; 0 leaves a heater off), `DIRECTION=CW\|CCW` | zMod's bed screw levelling (macros/ `quick_actions.cfg`): heat, home if needed, `SCREWS_TILT_CALCULATE`, nozzle to the bed centre 50 mm up; heaters stay on; refused during a print | 1.8 |
| `_PRINT_STATUS` | `MSG=` (none: clear) | Status line on the screen (`M117`) and the console | 1.0 |
| `GET_FILAMENT_VALUE`, `GET_CUT_VALUE` | | Raw ADC of the toolhead filament sensor / the cutter sensor (stock names) | 1.0 |
| `HEATER_IDLE_TIMEOUT` | `[MINUTES=]` (at least 5) | Minutes with no print and no heater change before the heaters go off; saved; shows it without parameters | 1.5 |
| `M300` | `[S=Hz]` `[P=ms]` | A beep on the speaker | 1.4 |
| `PLAY_MIDI` | `FILE=` | A MIDI file from the config folder's `midi/` or the image's sounds | 1.4 |
| `PLAY_SOUND`, `SOUND_STOP` | `EVENT=` startup\|start\|complete\|error\|cancelled\|paused\|refill | An event's sound / stop | 1.4 |
| `SOUND_SETUP` | `[ENABLE=0\|1]` `[VOLUME=0-100]` `[<EVENT>=<file>\|0]` | Speaker settings | 1.4 |
| `BED_SOAK_CALIBRATE` | `BED=` `[POINTS=5\|1]` `[NOZZLE=140]` `[INTERVAL=]` `[STABLE=0.005]` `[WINDOW=120]` `[MAX=1500]` `[FORCE=1]` | Measure the bed's settling after heating (`docs/print-start.md`) | 1.4 |
| `BED_SOAK_ENABLE` | `[ENABLE=0\|1]` | The soak on/off for every print, saved | 1.4 |
| `BED_SOAK_START`, `BED_SOAK_WAIT` | `BED=` `FROM=` `[SECONDS=]` `[MODE=time\|probe]` `[POINTS=]` | `PRINT_START`'s soak | 1.4 |
| `SET_NOZZLE_SIZE` | `SIZE=` 0.2\|0.25\|0.4\|0.6\|0.8\|1.0 `[RESTART=0]` | Saved in `nozzle.cfg`, Klipper restarts | 1.4 |
| `CONFIG_BACKUPS` | `ACK=1` (clear the notice) | List `macros/` files an update replaced and the backups of edited ones | 1.1 |
| `LOG_MODE` | `[MODE=short\|extended]` `[HOURS=]` | How much of Klipper's Stats line goes to `klippy.log` (short: once a minute while active; extended: every second, as upstream); `HOURS=` back to short after that long; saved; shows it without `MODE` (`docs/logs.md`) | 1.5\* |
| `G10`, `G11`, `SET_RETRACTION` | Klipper's `[firmware_retraction]` | | 1.0 |
| `G2`, `G3`, `G17`-`G19` | Klipper's `[gcode_arcs]` | | 1.0 |

### IFS (`klipper/extras/ifs.py`)

| Command | Parameters | What | Since |
|---|---|---|---|
| `T0`-`T3` | | Load the slot the tool map names (macros in `ifs.cfg`) | 1.0 |
| `IFS_SWAP` | `CHANNEL=` `[TEMP=]` `[FLUSH=mm]` `[ROUNDS=]` `[PURGE=0\|1]` `[HOME=1]` | Change to a slot. To the loaded slot: nothing to do, unless `printer.ifs.loaded_source` is `adopted` (then loaded again, 1.9). Not homed: refused; `HOME=1` (1.9): an idle printer homes first (`printer.ifs.phase` `homing_printer`), never during a print or a pause | 1.0 |
| `IFS_LOAD` | `SLOT=` `[TEMP=]` `[PURGE=0\|1]` `[HOME=1]` | Load a slot, unloading the loaded one first; `HOME=1` as `IFS_SWAP` (1.9) | 1.0 |
| `IFS_UNLOAD` | `[SLOT=]` `[TEMP=]` `[HOME=1]` | Cut and unload; the lane stays threaded. Refused while `printer.ifs.tube_blocked` (1.9); `HOME=1` as `IFS_SWAP` (1.9) | 1.0 |
| `IFS_EJECT` | `SLOT=` `[HOME=1]` | Pull a slot's filament out of the IFS (unloads the nozzle first when it is the loaded one; `HOME=1` as `IFS_SWAP`, 1.9) | 1.0 |
| `IFS_PREFEED` | `CHANNEL=` (not the loaded one) | Feed a new spool up to the IFS, as stock does | 1.0 |
| `IFS_MAP_TOOL` | `TOOL=` `SLOT=`, or `RESET=1` | Tool map for this print | 1.0 |
| `IFS_MAP_MODE` | `[MODE=fixed\|loaded]` `[ZMOD=1]` | Tool map mode, saved: fixed (`T0`-`T3` -> slots 1-4) or loaded (tools use the slots with filament); `ZMOD=1` puts the mode back at the print's end (zmod-compat's `START_PRINT`); shows it without `MODE` | 1.5 |
| `IFS_SET_MATERIAL` | `SLOT=` `[TYPE=]` `[COLOR=]` `[TEMP=]` | Slot material | 1.0 |
| `IFS_SET_COLOR` | `CHANNEL=` `COLOR=` | Slot colour | 1.0 |
| `IFS_SET_CHANNEL` | `CHANNEL=` (0 = none loaded) | Tell the module what is loaded (`loaded_source` `user`, 1.9). While `tube_blocked` only `CHANNEL=0` (pulled out by hand), which lifts it (1.9) | 1.0 |
| `IFS_STATUS`, `IFS_MATERIALS`, `IFS_STOP`, `IFS_RESET_DRIVER` | | Show state / materials, stop feeding, recover after a fault | 1.0 |
| `IFS_AUTO_REFILL` | `[ENABLE=0\|1]` (1.2) `[MATCH=exact\|similar\|any]` (1.4) | Auto-refill on runout | 1.2 |
| `IFS_PURGE_TEST`, `IFS_PURGE_RESULT`, `IFS_SET_FLUSH` | `IFS_SET_FLUSH LENGTH=` or `RESET=1` | Purge tuning | 1.0 |
| `IFS_TUNE` | `[CHANNEL=]` `[SPEED=1]` `[LOAD=1]` `[UNLOAD=1]` `[TUBE=0]` `[TEMP=]` `[HOME=1]` | Swap tuning, all steps; saved in `variables.cfg`. `HOME=1` (1.9) for the unload of a loaded slot, as `IFS_SWAP` | 1.0 |
| `IFS_TUNE_SPEED`, `IFS_TUNE_LOAD` | `[CHANNEL=]` | One tuning step: the feed speed / each slot's load distance | 1.0 |
| `IFS_TUNE_UNLOAD` | `[CHANNEL=]` (loads it first when nothing is loaded) `[TUBE=1]` | One tuning step: the unload length | 1.0 |
| `IFS_TUNE_RESET` | | Forget the tuning | 1.0 |
| `IFS_FIND_HEAD_SLOT` | `[TEMP=]` `[SLOT=n]` `[HOME=1]` | Filament in the toolhead from a slot Kiln doesn't know (loaded before the install): cut; retract the extruder alone the unload length; if that cleared the toolhead sensor the slot can't be found this way (the strand goes back, `find_result` `pick`, or `tube` if it stayed above the sensor); else pull each slot with filament back that far, lane only, feeding a wrong one back, until one clears the sensor; that one is fed back to the sensor to confirm, then unloaded. Heats like `IFS_UNLOAD`, to at least `[ifs] find_temp` (240) when a slot it may try has no material. Nothing moves when the toolhead is empty or the slot is known (Kiln loaded it or the user named it: a slot only adopted at startup, `loaded_source` `adopted`, is found like an unknown one, tried first). No slot clears: an error (pull the filament out by hand). A failure or stop after the strand left the sensor sets `tube_blocked` (`find_result` `tube`; the error names the slot when it was known). `SLOT=n`: the user names the slot (recorded as loaded; with `tube_blocked`, lane n is pulled back out of the tube) | 1.9 |

Swap templates in `[ifs]` a plugin may replace (same parameters). A
later definition replaces a whole template. Templates must not call
`IFS_*` commands.

| Template | Parameters | When | Since |
|---|---|---|---|
| `before_gcode` | `OLD`, `NEW` | Start of a swap (saves the G-code state `ifs_swap`) | 1.0 |
| `cut_gcode` | `OLD`, `NEW`; 1.5: `AT_PRINT=1` when the swap primes at the print (go back to the print position, before_gcode's saved state, instead of the box) | The cut | 1.0 |
| `unload_gcode` | `OLD`, `NEW`, `LENGTH`, `SPEED`, `RETRACT` (1 when the template retracts the extruder, 0 on IFS Klipper firmware where the module retracts it with the feeder) | The unload | 1.0 |
| `purge_start_gcode` | `OLD`, `NEW`, `ROUND`, `ROUNDS` | Before each purge round | 1.0 |
| `purge_gcode` | `OLD`, `NEW`, `ROUND`, `ROUNDS`, `FLUSH`, `FLUSH_SPEED` | Each purge round | 1.0 |
| `prime_gcode` | `OLD`, `NEW` | After a prime-only swap at the box (macros/ `ifs_templates.cfg`) | 1.0 |
| `prime_at_print_gcode` | `OLD`, `NEW` | After a prime at the print position, instead of `prime_gcode` (macros/ `ifs_templates.cfg`) | 1.5 |
| `after_gcode` | `OLD`, `NEW` | End of a swap: back to the print as stock, still lifted, Y, then X, then Z (to the position `before_gcode` notes; a replaced `before_gcode` that doesn't note it gets one `RESTORE_GCODE_STATE MOVE=1`) | 1.0 |
| `abort_gcode` | `OLD`, `NEW` | A swap failed or was stopped after `before_gcode` ran: put back the state without moving | 1.5 |

Options a plugin may set: `purge_mode_variable`, `prime_length`,
`prime_at_print` (1.5), `enable` (1.5, "A plugin that drives the IFS"),
and the documented lengths, speeds and timeouts in `ifs.cfg` (1.0).

Purge decision of a swap: `PURGE=` if given; else, while
`print_stats.state` is `printing` and `purge_mode_variable` is set, that
save variable: 0 or 2 = prime only, other = purge; else purge. A swap
that only primes does it at the print position (1.5; no
`purge_start_gcode`) when `prime_at_print` is on, the variable is 0,
`print_stats.info.current_layer` is 2 or more, the toolhead had filament
to cut, and `exclude_object` lists objects with outlines, none of them
current, the print position at least 5 mm outside each outline's
bounding box; else at the box.

### Power-loss recovery (`klipper/extras/ad5x_resume.py`)

| Command | Parameters | What | Since |
|---|---|---|---|
| `RESUME_INTERRUPTED` | `CONFIRM=1` | Continue the print a power cut ended (refused while `printer.ifs.tube_blocked`, 1.9) | 1.2 |
| `CLEAR_INTERRUPTED` | | Forget it | 1.2 |

### Setup wizard and plugins

| Command | Parameters | What | Since |
|---|---|---|---|
| `SETUP_WIZARD_STEP` | `STEP=selfcheck\|pid\|mesh\|shaper\|ifs\|trash\|zoffset\|soak\|summary\|finish`, `ACTION=start\|abort\|adjust\|accept\|wizard`; 1.4: `STEP=pid HEATERS=extruder\|bed\|both`; 1.9: `STEP=filament` `[MATERIAL_<n>=]` `[HEAD=<n>\|0\|KEEP\|AUTO]`, `STEP=zoffset HEAD=KEEP`, `ACTION=accept` also confirms the prompt `clear_bed` (a Z offset step now needs two accepts: the offset, then the bed cleared) | One wizard step (`docs/setup-wizard.md`); API endpoint `ad5x_setup/control` | 1.0 |
| `SETUP_WIZARD` | | Run the wizard again on the screen (macros/ `quick_actions.cfg`; `SETUP_WIZARD_STEP ACTION=wizard` does the same) | 1.0 |
| `ENABLE_PLUGIN`, `DISABLE_PLUGIN` | `NAME=` `[RESTART=0]`; 1.6: `ENABLE_PLUGIN ROOT=1`, needed for a plugin with root scripts (`docs/plugin-root-hooks.md`) | Switch a plugin | 1.0 |
| `LIST_PLUGINS` | | The plugins and the API version | 1.0 |
| `INSTALL_PLUGIN` | `NAME=` (a catalog plugin) `[ENABLE=1]`; 1.6: `[ROOT=1]` | Clone it into `/data/ad5x/plugins`; 1.7: with its git submodules ("Submodules") | 1.4 |
| `UPDATE_PLUGIN`, `REMOVE_PLUGIN` | `NAME=` (a plugin in `/data/ad5x/plugins`) | `git pull` / switch off and delete; 1.7: `UPDATE_PLUGIN` updates its git submodules too | 1.4 |

### Buttons (macros/ `system.cfg`)

Fluidd lists only macros, not module commands; these run one command
each, for its macro panel.

| Macro | Runs | Since |
|---|---|---|
| `PLUGINS_LIST`, `PLUGIN_ENABLE NAME=`, `PLUGIN_DISABLE NAME=` | `LIST_PLUGINS`, `ENABLE_PLUGIN`, `DISABLE_PLUGIN` | 1.1 |
| `IFS_TUNE_RUN [CHANNEL=]`, `IFS_TUNE_CLEAR`, `IFS_INFO` | `IFS_TUNE`, `IFS_TUNE_RESET`, `IFS_STATUS` | 1.1 |
| `CONFIG_BACKUPS_SHOW [ACK=1]` | `CONFIG_BACKUPS` | 1.1 |
| `KILN_MEMORY_MODE [ENABLE=0\|1]` | Moonraker's remote method `kiln_memory_mode` (`docs/api.md`, `/machine/kiln_os/memory`): Extended memory on or off from the next start, or the mode without `ENABLE`; the answer in the console. Printers with 256 MiB answer "not available" | 1.8 |

## Public and internal names

**Public** (plugins, slicer G-code, the screen and other clients may call
them): every command and macro in the tables above. They keep their
names and parameters within a major version.

**Internal** (may change or go in any update; don't call them):

- Every name starting with `_` that is not in the tables above. The
  public ones that start with `_` are older names kept as they were:
  `_PRIME_LINE`, `_PURGE_BOX`, `_PURGE_WIPE`, `_NOZZLE_BRUSH`,
  `_PRINT_STATUS`, and the variables of `_AD5X_UNIT` and
  `_PURGE_BOX_POS` (read only). New public names don't start with `_`.
- These commands, bench and debugging tools: `IFS_SEND`, `IFS_SELECT`,
  `IFS_FEED`, `IFS_RETRACT`, `IFS_RELEASE`, `IFS_RESET`,
  `IFS_SET_CURRENT`, `WEIGHT_READ`, `WEIGHT_SEND`.

The test `tools/test_plugin_api_doc.py` keeps this list and the code in
step.

## Printer objects and status fields

| Object | Fields | Since |
|---|---|---|
| `printer.ifs` | `connected`, `version`, `busy`, `channel` (loaded, 0 none), `state`, `selected`, `inserted[4]`, `colors[4]`, `silk[4]`, `stall[4]` (raw per-slot sensor counts as the IFS reports them, for diagnostics), `channel_count`, `active_channel`, `loaded_channels`, `pending_insert_channels`, `activity`, `activity_channel`, `error`, `tool_map` (`"0"`-`"3"` -> slot), `tune` (`speed`, `load_dist` (`"1"`-`"4"`), `unload_dist`, `tube_unload`, `running`, `progress`, `message`; tuned values, null where the `[ifs]` defaults apply); 1.2: `auto_refill`, `refill` (last auto-refill message); 1.4: `refill_match`, `refill_backups` (`"1"`-`"4"` -> the slots that would take over, nearest colour first; `[]` none), `refill_notice` (a print loaded a slot with no backup; "" otherwise); 1.5: `map_mode` (`fixed`/`loaded`), `mode` (`mcu`/`serial`), `operation`, `phase`, `target_channel`, `error_channel`, `tune.flush` (`docs/helixscreen-integration.md`, section 0); 1.9: `find_result` (the last `IFS_FIND_HEAD_SLOT`: `found`, `pick`, `tube`, `none`, `error`; "" none), `head_found` (its slot, 0 none), `tube_blocked` (a strand sits in the tube above the toolhead sensor, after a `tube` result, or a find or an unload (`IFS_UNLOAD`, a swap's first half) that failed or was stopped after the strand had left the sensor (nothing recorded as loaded then): loads, `IFS_UNLOAD`, `IFS_SET_CHANNEL CHANNEL=n`, tuning and pre-feeds are refused until `IFS_FIND_HEAD_SLOT SLOT=n` pulls lane n back or `IFS_SET_CHANNEL CHANNEL=0` says it was pulled out by hand), `loaded_source` (how `channel` is known: `kiln` a load of Kiln's own, also a channel saved before 1.9; `user` named with `IFS_SET_CHANNEL` or `IFS_FIND_HEAD_SLOT SLOT=n`; `adopted` only a guess at startup (no slot saved, filament at the toolhead, the IFS pointing at it); "" nothing loaded; saved, kept across restarts. An `adopted` slot: `IFS_SWAP` to it loads it again, its first unload must clear the toolhead sensor or nothing is recorded as loaded, `IFS_FIND_HEAD_SLOT` finds the slot (that one first), the setup wizard treats it as unknown) | 1.0 |
| `printer.ifs_materials` | `available`, `channel_count`, `slots` (`"1"`-`"4"`: `type`, `color`, `temp`), `loaded`, `temperatures` | 1.0 |
| `printer.ad5x_setup` | `step`, `state`, `message`, `progress`, `results`, `checks`, `pending_save`, `zoffset`; 1.5: `estimate` (the Z offset step uses `Z_OFFSET_ESTIMATE`: setup.cfg `zoffset_estimate`); 1.9: `action` (what the step does now, a short key; "" idle), `action_arg` (its slot or patch number, 0 none), `step_started` (Unix time the step started, 0 none), `prompt` (null, `clear_bed`, `head_unknown`, `pick_slot`), `filament` (`present`, `materials`, `head`, `head_source` (`loaded`, `user`, `found`, `unknown`, `kept`, `tube`, `empty`), `head_filament`; null without Kiln's IFS module), `zoffset_plan` (`slot`, `material`, `nozzle`, `bed`, `guess`, `source`; null before the Z offset step) (`docs/setup-wizard.md`) | 1.0 |
| `printer.ad5x_weight` | `connected`, `weight` | 1.0 |
| `printer.ad5x_config` | `notices` (lines of `config-updates.txt`), `backups` (`macros/*.bak-*`) | 1.1 |
| `printer.ad5x_resume` | `available`, `file`, `z`, `time` (an interrupted print) | 1.2 |
| `printer.ad5x_nozzle` | `size` (running), `saved` (nozzle.cfg, null), `local` (local.cfg sets it), `sizes` | 1.4 |
| `printer.ad5x_sound` | `speaker`, `enabled`, `volume`, `events` (event -> file, "" off), `files`, `playing` | 1.4 |
| `printer.ad5x_soak` | `enabled`, `calibration` (per bed temperature `settle`, `drift`, `warp`, `points`, `from`, `stable`, `date`), `running`, `soak`, `last`; 1.5\*: `cancel` (a cancel arrived during the print start and waits for it to end) | 1.4 |
| `printer.ad5x_zestimate` | Empty until the first `Z_OFFSET_ESTIMATE`, then: `estimate` (mm, the print Z offset it suggests), `press_in` (mm, first contact relative to where the probe fires), `stiffness` (g/mm), `r2` (fit quality, below 0.95 poor), `points`, `trigger_force` (g, null), `saved` (the saved Z offset then, null), `drift` (g), `first_touch` (mm above the trigger, null) | 1.5 |
| `printer.ad5x_log` | `mode` (`short`/`extended`), `until` (Unix time back to short, null) | 1.5\* |
| `printer.ad5x_mlock` | `locked` (Klipper's memory is locked in RAM), `flags` (`current,future,onfault`), `limit` (bytes, null: unlimited), `error` (why not, null; `off (...)` with `/data/ad5x/klipper-mlock.disable`) | 1.8 |
| `printer.ad5x_plugins` | `api_version`, `enabled`, `available` (per plugin: `source`, `description`, `version`, `author`, `url`, `requires_os`, `compatible`; 1.5: `owns_ifs`; 1.6: `root` (it has root scripts), `root_installed` (its `install.sh` ran)), `warnings`; 1.4: `catalog` (per plugin: `title`, `description`, `url`, `requires_os`, `compatible`, `installed`), `job` (`name`, `action`, `state` idle/running/done/failed, `message`; 1.6: `action` `root install`/`root update`/`root uninstall` for the root scripts); 1.5: `ifs_owner` (the plugin driving the IFS at this start, "" Kiln's `[ifs]`) | 1.0 |
| `printer['gcode_macro _AD5X_UNIT']` | `z_offset`, `cut_x_offset`, `cut_y_offset`, `x_offset`, `y_offset` (purge box at X 52.5 + `x_offset`, Y 229 + `y_offset`; cut at X `cut_x_offset` - 2.5, Y `cut_y_offset` - 7.5) | 1.0 |
| `printer['gcode_macro _PURGE_BOX_POS']` | `x`, `y` (the purge box spot, with the saved `TRASH_OFFSET`), `dx`, `dy` (its offset from X 52.5 / Y 229: `TRASH_OFFSET`, else unit.cfg's `x_offset`/`y_offset`); what every Kiln box move uses | 1.5\* |
| `printer['filament_switch_sensor toolhead']` | Klipper's runout fields (`enabled`, `filament_detected`); also `adc_filament_sensor toolhead`; `SET_FILAMENT_SENSOR SENSOR=toolhead` | 1.0 |
| `printer['fan_generic fanM106']`, `printer['fan_generic pcb_fan']` | Part fan, board fan | 1.0 |
| `printer['led chamber_led']` | Chamber light (`SET_LED LED=chamber_led WHITE=`) | 1.0 |
| `printer['temperature_sensor filamentValue']`, `printer['temperature_sensor cutValue']` | Toolhead filament and cutter ADCs (`QUERY_ADC`) | 1.0 |
| `printer['gcode_macro PRINT_START']` | `mesh_every_print`, `adaptive_mesh`, `retract`; 1.4: `soak_per_degree`, `soak_max`, `soak_mode`, `soak_points` (with macros/ `print_start.cfg`) | 1.1 |
| `printer['gcode_macro _PRIME_LINE']` | `prime_line`, `length`, `height`, `width` (0 = 2.5 x nozzle), `gap`, `flow`, `speed`, `prime`, `prime_speed`, `margin`, `wipe`, `retract`; 1.5: `owed` (was `unretract`, "Changes") (with macros/ `prime_line.cfg`) | 1.1 |

Save variables (`printer.save_variables.variables`, 1.0): `ifs_loaded`,
`ifs_materials`, `zoffset` (`{'z': ..}`), `ad5x_center_z`,
`use_trash_on_print` (nopoop), the `IFS_TUNE` values (`ifs_speed`,
`ifs_load_dist_<n>`, `ifs_unload_dist`, `ifs_tube_unload`, `ifs_flush`).
Read them; write only your own (prefixed) variables, except
`use_trash_on_print`.

## Python extras

- Loaded by `[ad5x_plugins]` as `extras.<module>`, only for enabled,
  compatible plugins; `load_config(config)` / `load_config_prefix(config)`
  as for any Klipper module (`docs/plugins.md`, "Python extras"; 1.0).
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
`moonraker.conf` while the plugin is enabled (1.0; `docs/plugins.md`,
"Moonraker parts"). Moonraker v0.11.0, `[machine] provider: kiln_agent`
(1.6: klipper, moonraker, nginx, helixscreen and ad5x-camera restart
through the root agent, not while printing; before: `provider: none`, no
service restarts), no package manager.
