# Plugins

Optional features, switched on and off per printer, without touching the
system image or the printer's own config files by hand. Shipped plugins
come with the image; anyone can publish their own as a git repository.
The interface plugins may rely on is in `docs/plugin-api.md`.

## Where things live

| What | Where | Changed by |
|---|---|---|
| Shipped plugins | `/usr/share/ad5x/plugins/<name>/` (read-only image; repo `klipper/plugins/`) | System updates only |
| Other people's and your own plugins | `/data/ad5x/plugins/<name>/` (owned by user `klipper`) | You, or Moonraker's update manager; never system updates |
| Which plugins are on | `printer_data/config/plugins.cfg` | `ENABLE_PLUGIN` / `DISABLE_PLUGIN`, or you |
| Moonraker parts of the enabled plugins | `printer_data/config/moonraker-plugins.conf` (generated) | Klipper and `S62moonraker`; don't edit |
| Plugin manager | `klipper/extras/ad5x_plugins.py`, `[ad5x_plugins]` in `ad5x.cfg` | System updates |

`printer_data/config` is `/home/klipper/printer_data/config`, the same as
`/data/ad5x/printer_data/config`.

A plugin of yours with the same name as a shipped one replaces it (its
directory is the one used).

## Using plugins

On the touch screen: **Settings > Plugins** lists the installed plugins
with an on/off switch each, and the catalog's plugins with an Install
button (HelixScreen, our patch `0005`). The same from the console
(Fluidd, HelixScreen, or a macro):

```
LIST_PLUGINS
ENABLE_PLUGIN NAME=recommend
DISABLE_PLUGIN NAME=recommend
```

These are zMod's command names, so its `name=` spelling works too.
`ENABLE_PLUGIN` and `DISABLE_PLUGIN` edit `plugins.cfg`, then restart
Klipper (`RESTART=0`: write only, restart later). They refuse:

- during a print (paused counts);
- an unknown name (the message lists what there is);
- a plugin whose `requires_os` doesn't fit this system's plugin API, whose
  `plugin.json` is missing or broken, which needs a plugin that is off
  (`requires`), or which can't be on together with one that is on
  (`conflicts`, either side may declare it);
- disabling a plugin that another enabled plugin requires.

`LIST_PLUGINS` shows the plugin API version, then one line per plugin:
`[on]`/`[off]`, name, version, shipped or user, author, description, and
notes (requires, conflicts, incompatible, "until RESTART" when the file
and the running Klipper differ, "missing" for an enabled plugin whose
directory is gone). The same data is in `printer.ad5x_plugins`
(`api_version`, `enabled`, `available`, `warnings`).

If a plugin stops Klipper with a config error, `DISABLE_PLUGIN` and
`LIST_PLUGINS` still work from the console (they are available while
Klipper isn't ready, as long as the error comes from the plugin's own
sections). Otherwise delete the plugin's line in `plugins.cfg` (Fluidd's
config editor) and `RESTART`.

`plugins.cfg` is a plain Klipper file with one line per enabled plugin:

```
[include /usr/share/ad5x/plugins/zmod-compat/plugi[n].cfg]
```

The `[n]` makes the path a pattern: a plugin that disappears (deleted, or
dropped from a later image) is skipped instead of stopping Klipper, and
`LIST_PLUGINS` reports it as missing. Hand edits are kept; the commands
only add or remove plugin lines (and drop duplicates).

## How they are loaded

`ad5x.cfg` (read-only, in the image) ends with:

```
[ad5x_plugins]
[include /home/klipper/printer_data/config/plugin[s].cfg]
```

The `[s]` makes the include optional: no `plugins.cfg`, no error. So the
order of the whole config is: factory defaults (`ad5x.cfg`, with
`ifs.cfg` and `setup.cfg` / `ad5x-tuning.cfg`), the printer's editable
macros (`macros/*.cfg`, `docs/config-layout.md`), then the plugins in
`plugins.cfg` order, then `unit.cfg`, then `local.cfg`. Plugins may
change any default and the `macros/` files' macros; `local.cfg` still
overrides them. A plugin section
that already exists (for example `[ifs]` or `[gcode_macro T0]`) is
merged: the plugin's options replace those before it.

Existing printers needed no change to `printer.cfg`: the include sits in
`ad5x.cfg`, which comes with the image.

### Python extras

Klipper only loads modules from `klippy/extras`, which is in the
read-only image. `[ad5x_plugins]` comes before the plugins' sections, and
when Klipper creates it, it imports each enabled plugin's
`extras/<module>.py` as Klipper module `extras.<module>`, then creates
the objects for the config sections named after those modules, the way
Klipper's own loader does (`load_config` / `load_config_prefix`). No
Klipper patch: everything stays in our extra. Rules:

- Only enabled plugins' code is loaded, and only when the plugin's
  `plugin.json` is valid and its `requires_os` fits.
- A module named like a Klipper module (`extras/gcode_macro.py`, ...) or
  like another enabled plugin's module stops Klipper with a config error
  naming the plugin. Rename it.
- Sections of plugin modules are created when `[ad5x_plugins]` is
  created. Look up other objects in `klippy:connect`, not in `__init__`.
  `printer.load_object()` can't find plugin modules; import a sibling
  module of the same plugin as `from . import <module>` only if it sorts
  before yours, or keep a plugin's code in one module.

### Moonraker parts

A plugin can ship `moonraker.conf` with Moonraker sections, typically its
own `[update_manager <name>]`. The printer's `moonraker.conf` belongs to
the user and is never edited by the system, so `S62moonraker` starts
Moonraker on a small top file it writes at each start,
`/run/moonraker/moonraker.conf`:

```
[include /usr/share/ad5x/moonraker-updates.conf]
[include /home/klipper/printer_data/config/moonraker.conf]
[include /home/klipper/printer_data/config/moonraker-plugins.conf]
```

(`moonraker-updates.conf` is the system's own `[update_manager]` with
Fluidd's update entry, so Fluidd can update itself from Fluidd.)

`moonraker-plugins.conf` lists the enabled plugins' `moonraker.conf`
files; `S62moonraker` regenerates it from `plugins.cfg` just before
Moonraker starts (`ad5x_plugins.py moonraker`, the same code Klipper
uses), and Klipper rewrites it whenever plugins change. When at least
one listed part has `[update_manager ...]` sections, the list adds
`[update_manager]` with `enable_system_updates: False` (this system has
no package manager). Moonraker reads it at its next start: after enabling
a plugin with a Moonraker part, reboot (or restart Moonraker). If you
include `moonraker-plugins.conf` from `moonraker.conf` yourself,
`S62moonraker` leaves its own include out (Moonraker refuses the same file
twice).

## What system updates do and don't touch

- Replaced with each image: `ad5x.cfg`, `ifs.cfg`, `setup.cfg`, the
  shipped plugins in `/usr/share/ad5x/plugins`, `ad5x_plugins.py`.
- Replaced when the image's template changes: `macros/*.cfg` in the
  config directory (an edited file is kept as `<name>.cfg.bak-<date>`
  first; `docs/config-layout.md`).
- Never changed once they exist: `plugins.cfg`, `printer.cfg`,
  `unit.cfg`, `local.cfg`, `moonraker.conf`, `variables.cfg`,
  `ad5x-tuning.cfg`, and everything in `/data/ad5x/plugins`.
- Regenerated (not yours to edit): `moonraker-plugins.conf`,
  `/run/moonraker/moonraker.conf`.

So an update can bring new versions of shipped plugins (enabled ones
change behaviour with it), new shipped plugins (off until enabled), and
can drop a shipped plugin (skipped, reported missing; disable it). It
never switches a plugin on or off. Shipped plugins keep the plugin API's
rules too (`docs/plugin-api.md`).

### First boot and the move from zMod

`S05ad5x-data` writes `plugins.cfg` once, when it doesn't exist, from the
image's default: `zmod-compat` and `nopoop`, so G-code sliced for zMod
prints (nopoop changes nothing until a file sets `use_trash_on_print`).
On a printer that ran zMod it also reads zMod's own files on the data
partition (`/data/config/mod_data/plugins.cfg` and `variables.cfg`) and
adds:

- `bambufy-compat` if zMod's `plugins.cfg` enables bambufy or its
  `variables.cfg` has `bambufy_*` variables (bambufy was installed; files
  sliced with Bambufy profiles call `_NOPOOP`);
- not `recommend`, even when zMod had it: it changes the probe speed, which moves the calibrated Z offset. Enable it by hand and re-run the Z offset step.

zMod's QuickSwap has no plugin here: `IFS_TUNE` (setup wizard) does the
same tuning in the IFS module. An existing `plugins.cfg` is never
touched; delete it and reboot to get the default again.

## Shipped plugins

| Plugin | Default | What |
|---|---|---|
| `zmod-compat` | on | zMod's macro names for slicer G-code and the console: `START_PRINT`, `END_PRINT`, `_GOTO_TRASH`, `_SBROS_TRASH`, sensors, timelapse, Spoolman, pause at layer, ... (`docs/zmod-compat.md`) |
| `nopoop` | on | zMod's purge modes: in a print, `use_trash_on_print` 0 (prime tower) or 2 (slicer flush) makes tool changes prime only, without purge rounds |
| `bambufy-compat` | off (on when migrating from a zMod with Bambufy) | Bambufy profiles: `_NOPOOP`, `_M106`; needs `zmod-compat` |
| `recommend` | off (also after zMod; probe speed moves the Z offset) | zMod's recommended probing, mesh and corner values |

Each has a `README.md` in its directory.

## Plugins in their own repositories

Installed into `/data/ad5x/plugins` ("Keeping a git plugin up to date"
below) and updated from Fluidd, separately from Kiln OS:

| Plugin | Repository | What |
|---|---|---|
| `spoolman` | [kiln-spoolman](https://github.com/djvalic/kiln-spoolman) | A Spoolman spool per IFS slot: the loaded slot's spool is the active one (plugin API 1.2, `ifs:loaded`) |
| `notify` | [kiln-notify](https://github.com/djvalic/kiln-notify) | Notifications with a camera photo through Apprise (Telegram, Discord, ntfy, e-mail, ...): print events, progress, auto-refill, interrupted prints; set up with `NOTIFY_SETUP` (plugin API 1.3) |
| `timelapse` | [kiln-timelapse](https://github.com/djvalic/kiln-timelapse) | moonraker-timelapse with an ffmpeg built from source for the printer; Fluidd's Timelapse tab (plugin API 1.3) |

They are listed in the image's catalog (`klipper/plugin-catalog.json`,
`/usr/share/ad5x/plugin-catalog.json`), which `INSTALL_PLUGIN` and
HelixScreen's Settings > Plugins offer, and each release is tested with
them (`tools/test_plugin_repos.sh`): their own tests, and Moonraker
starting with all of them enabled.

## Writing a plugin

The layout, `plugin.json` fields and an example are in
`docs/plugin-api.md` ("Plugin layout"). In short: a directory named like
the plugin, with `plugin.json`, `plugin.cfg`, `README.md`, and optionally
`extras/*.py` and `moonraker.conf`. Put it in `/data/ad5x/plugins/<name>`
(as user `klipper`, or `chown -R klipper:klipper` it), then
`ENABLE_PLUGIN NAME=<name>`.

### Installing from the catalog

The plugins in their own repositories that this release offers and was
tested with are in its catalog (`/usr/share/ad5x/plugin-catalog.json`):

```
INSTALL_PLUGIN NAME=notify ENABLE=1   (clone it into /data/ad5x/plugins, switch it on)
UPDATE_PLUGIN NAME=notify             (git pull; restarts what it needs if on)
REMOVE_PLUGIN NAME=notify             (switch it off and delete it)
```

Spoolman is installed the same way, with `INSTALL_PLUGIN NAME=spoolman ENABLE=1`.
Use `INSTALL_PLUGIN`, not `ENABLE_PLUGIN`: the image has no spoolman copy of
its own (older images had an unusable one in `/usr/share/ad5x/plugins/spoolman`,
which is removed at each build).

`git` runs in the background (`printer.ad5x_plugins.job`, the result also
in the console); not during a print. When a switch changes what Moonraker
loads (a plugin's `moonraker.conf`, `python/` or components), Moonraker is
restarted too (by the root update agent, `S68ad5x-update-agent`), so no
reboot is needed. A plugin not in the catalog is installed by hand as
below.

### Keeping a git plugin up to date

Moonraker's update manager updates a git repository; it doesn't switch
the plugin on or off (that stays `ENABLE_PLUGIN`). Ship this in the
plugin's own `moonraker.conf`:

```
[update_manager myplugin]
type: git_repo
path: /data/ad5x/plugins/myplugin
origin: https://github.com/someone/ad5x-myplugin.git
primary_branch: main
is_system_service: False
managed_services: klipper
```

Clone it once by hand, as user `klipper` so Moonraker can pull:

```
cd /data/ad5x/plugins
su klipper -s /bin/sh -c 'git clone https://github.com/someone/ad5x-myplugin.git myplugin'
```

then `ENABLE_PLUGIN NAME=myplugin` (Moonraker restarts and reads the new
`[update_manager]`). Fluidd then shows it under updates.
This system's Moonraker has no service manager (`provider: none`), so
`managed_services: klipper` can't restart Klipper after an update: run
`RESTART` (or `FIRMWARE_RESTART`) yourself. A plugin that isn't enabled
has no Moonraker part, so it isn't updated either; enable it, or put the
`[update_manager]` section in `moonraker.conf` yourself.

Several printers: each printer has its own `plugins.cfg` and its own
clones; the same repository and the same image work on all of them.
