# Write your first plugin

From an empty folder to a plugin running on your printer: make it from
the template, edit it, check it, upload it in Fluidd, switch it on and
see it in Fluidd. What a plugin may use is in `docs/plugin-api.md`; how
plugins are switched and loaded is in `docs/plugins.md`.

Commands run on your computer unless they are marked as console commands
(Fluidd's console, or HelixScreen's). `PRINTER` stands for your printer's
address.

## 1. Get the tools

You need `bash` and `python3` (Linux, macOS, or WSL on Windows) and a copy
of Kiln OS:

```
git clone https://github.com/djvalic/kiln-os
cd kiln-os
```

## 2. Make the plugin

```
tools/new_plugin.sh ~/myplugin --python
```

The last part of the path is the plugin's name: `a-z`, `0-9`, `-` and
`_`, starting with a letter, no digit as the second character (Klipper
refuses command names like `M3_HELLO`), not starting with `ad5x-` or
`kiln-` (kept for Kiln OS).
Without options you get a plugin of Klipper config only; `--python` adds a
Klipper module, `--moonraker` a Moonraker component. Both work together.

| File | What |
|---|---|
| `plugin.json` | Name, description, version `0.1.0`, and `requires_os`: the plugin API of the Kiln OS you made it with |
| `plugin.cfg` | Klipper config: the `MYPLUGIN_HELLO` macro (and with `--python` the `[myplugin]` section that creates the module's object) |
| `README.md` | What it does, how to use it |
| `extras/myplugin.py` | `--python`: a Klipper module with the command `MYPLUGIN_GREET` and the status `printer.myplugin` |
| `moonraker.conf`, `moonraker/components/myplugin.py` | `--moonraker`: a component with the endpoint `GET /server/myplugin/hello` |
| `tests/` | Offline tests for each part |

## 3. Edit it

- `plugin.json`: say what it does in `description`, fill in `author` and
  `url`. Raise `version` with each change you hand out. Keep
  `requires_os` at the plugin API you tested with (`LIST_PLUGINS` on the
  printer shows the printer's).
- `plugin.cfg`: your macros and config sections. Start your macro,
  module and variable names with the plugin name (`MYPLUGIN_...`,
  `myplugin_...`); `docs/plugin-api.md` lists the macros, commands and
  status fields of Kiln OS you may use.
- `extras/myplugin.py`: a Klipper module as in Klipper's own `extras/`.
  Look up other objects in `klippy:connect`, not in `__init__`.
- `tests/`: change them with the code. `tests/test_plugin.py` loads the
  plugin through Kiln's plugin manager as the printer does, on a stand-in
  printer (`tools/plugin_harness.py`); the others test the module and the
  component on their own.

## 4. Check it

```
tools/check_plugin.py ~/myplugin
```

```
myplugin: Klipper's own module names not checked (--klippy DIR)
myplugin: tests/test_klipper.py: passed (all passed)
myplugin: tests/test_plugin.py: passed (all passed)
myplugin: OK (0 warnings, plugin API 1.6)
```

It checks the plugin the way the printer's plugin manager does (the
folder name and `plugin.json`'s `name`, `requires_os` against this Kiln
OS, `plugin.cfg` as Klipper parses it, module names that would clash,
modules, components, sections and macros starting with `kiln_` or `ad5x_`
(kept for Kiln OS and its own plugins: the printer won't enable yours), a
`root/` folder packed as the printer sends it to root: no links, FIFOs or
devices, at most 8 MB), plus unknown `plugin.json` keys, command names
Klipper refuses and Python syntax, then runs the
plugin's tests (`test_*.py` and `tests/test_*.py`). An error is
something that stops the plugin on the printer; a warning is worth a
look. The exit status is 1 when there is an error.

Klipper's own module names (`extras/led.py` would clash) are checked
against a Klipper source tree:

```
git clone https://github.com/Klipper3d/klipper ~/klipper
tools/check_plugin.py --klippy ~/klipper/klippy ~/myplugin
```

One test on its own: `python3 ~/myplugin/tests/test_klipper.py`.
`tests/test_plugin.py` needs Kiln's tools for the plugin manager part:
`KILN_TOOLS=$PWD/tools python3 ~/myplugin/tests/test_plugin.py`.

## 5. Upload it to the printer

Your plugins go in `/data/ad5x/plugins/<name>`; the folder's name must be
the plugin's name. Fluidd shows that folder as `plugins` in its file
manager (**Configuration**, next to `printer.cfg`):

1. Open **Configuration** and click the `plugins` folder.
2. **Upload Folder** (the upload button's menu) and pick `~/myplugin`.
   Fluidd uploads it with everything in it as `plugins/myplugin`.

Single files go the same way: open the plugin's folder and upload them,
or make one with **New file** and paste its text. Any file of the plugin
can be opened and edited there, like a config file. Fluidd's own **Upload
Files** picker lists config files first; switch it to all files for
`.py` and `.json`. The plugin's `.git` folder is not shown and can't be
changed from the browser.

Uploading runs nothing. A plugin's `root/` scripts run as root only after
`ENABLE_PLUGIN NAME=<name> ROOT=1`; if you change `root/` of a plugin that
is already on, the next Klipper start warns that it changed, and
`ENABLE_PLUGIN NAME=<name> ROOT=1` runs its `update.sh`
(`docs/plugin-root-hooks.md`).

Or copy it over SSH as root:

```
scp -O -r ~/myplugin root@PRINTER:/data/ad5x/plugins/
ssh root@PRINTER chown -R klipper:klipper /data/ad5x/plugins/myplugin
```

(`-O`: the printer has no SFTP server, so `scp` uses its classic way;
leave `-O` out if your `scp` doesn't know it.)

A plugin in a git repository can be cloned on the printer instead, as
user `klipper`, under the plugin's name:

```
ssh root@PRINTER
cd /data/ad5x/plugins
su klipper -s /bin/sh -c 'git clone https://github.com/you/kiln-myplugin.git myplugin'
```

Plugins in the catalog of your Kiln OS (`/usr/share/ad5x/plugin-catalog.json`,
listed under Settings > Plugins on the touch screen) are installed from the
console instead: `INSTALL_PLUGIN NAME=notify ENABLE=1`.

## 6. Switch it on

Console:

```
ENABLE_PLUGIN NAME=myplugin
```

Klipper restarts with the plugin (not during a print). If the plugin has
a Moonraker part, Moonraker restarts too. When `ENABLE_PLUGIN` refuses,
its message says why (an unknown name lists the plugins it found).

## 7. See it in Fluidd

Console:

```
LIST_PLUGINS
MYPLUGIN_HELLO NAME=you
```

`LIST_PLUGINS` shows `[on]  myplugin 0.1.0 (user): ...`, and
`MYPLUGIN_HELLO` answers `Hello, you!`. The macro is also a button in
Fluidd's Macros panel. The module's status and the Moonraker endpoint:

```
curl "http://PRINTER/printer/objects/query?myplugin"
curl http://PRINTER/server/myplugin/hello
```

## 8. Change it

Edit it in Fluidd (`plugins/myplugin`), or on your computer: run
`tools/check_plugin.py` again and upload it again (step 5). Then
`RESTART` in the console: Klipper reads the plugin's
config and Python code afresh. A changed Moonraker part is read when
Moonraker restarts: `DISABLE_PLUGIN NAME=myplugin` and
`ENABLE_PLUGIN NAME=myplugin` again, or reboot.

When something is wrong:

- Klipper starts but warns `Plugin myplugin skipped: <reason>`: the
  plugin isn't loaded at all. Fix the reason, upload, `RESTART`.
- Klipper stops with a config error naming the plugin: `DISABLE_PLUGIN
  NAME=myplugin` still works from the console.
- Python errors are in `klippy.log` (Fluidd: the logs folder in the file
  manager).

## 9. Share it

Put the folder in a git repository of its own (the repository's root is
the plugin folder). For updates from Fluidd, add an `[update_manager]`
section to its `moonraker.conf`: `docs/plugins.md`, "Keeping a git plugin
up to date".
