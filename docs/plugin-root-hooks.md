# Plugin root scripts: reference for developers and owners

Status: **built, plugin API 1.6.** The same model as zMod's plugins: a plugin
may ship scripts that run as root when it is enabled, updated and disabled,
and boot scripts that run at every start. Parts: the root update agent
`S68ad5x-update-agent` (it runs the scripts), the boot script runner
`S69ad5x-plugin-boot`, the shared code in `/usr/lib/ad5x/plugin-root.sh`, and
`ENABLE_PLUGIN`, `DISABLE_PLUGIN`, `REMOVE_PLUGIN` and `INSTALL_PLUGIN` in
`klipper/extras/ad5x_plugins.py`. Offline tests: `tools/test_plugin_root.sh`
(root's side) and `tools/test_plugin_root_klipper.py` (Klipper's side). A
printer test boot is still needed (end of this page).

Use them for a root step a plugin needs, for example:

- write an nginx config for a second web UI, check it with `nginx -t`, and
  restart nginx;
- write `camera.conf` and restart `S64ad5x-camera`;
- start a small watcher at boot that gives group `klipper` to a device node.

Plugins without a `root/` folder work as before; nothing here changes them.

## The plugin's `root/` folder

```
myplugin/
  plugin.json             "requires_os": "1.6"
  plugin.cfg
  root/
    install.sh            runs as root when the plugin is enabled (ENABLE_PLUGIN ROOT=1)
    update.sh             runs as root after the plugin was updated, if root/ changed
    uninstall.sh          runs as root when the plugin is disabled or removed
    ...                   anything else the scripts need (configs, a boot script)
```

- Any of the three scripts is optional. A plugin counts as one "with root
  scripts" when it has at least one of them.
- `root/` may hold only folders and plain files: no links, FIFOs or device
  nodes. At most 8 MB packed.
- Make a script executable to run it with its own `#!` line; otherwise it
  runs with `/bin/sh`.
- Set `"requires_os": "1.6"` in `plugin.json`: an older Kiln OS doesn't run
  root scripts and would enable the plugin without them.

## When each script runs

| Script | When | What it should do |
|---|---|---|
| `install.sh` | `ENABLE_PLUGIN NAME=<name> ROOT=1` (also from `INSTALL_PLUGIN ... ENABLE=1 ROOT=1`), before the plugin is switched on | Install its root parts, start them if they should run now, and return. If it fails, undo what it did: the plugin stays off |
| `update.sh` | At the first Klipper start after the plugin's files changed (`UPDATE_PLUGIN`, or Moonraker's update manager), when its `root/` is different from root's copy and is what git checked out; otherwise at `ENABLE_PLUGIN NAME=<name> ROOT=1` | Bring the installed parts up to date and return |
| `uninstall.sh` | `DISABLE_PLUGIN` and `REMOVE_PLUGIN`, before the plugin is switched off or removed | Stop what it started and remove what `install.sh` put in place. It may be called when nothing runs |

- **Consent:** `ROOT=1` is how the owner says yes. Without it, enabling a
  plugin with root scripts is refused with "runs code as root". The touch
  screen's Settings > Plugins asks the owner first ("This plugin runs some
  of its code as root ... Turn it on only if you trust where it comes
  from.") and sends `ROOT=1` only after Turn On. Updates run
  `update.sh` by themselves after that, as zMod does: the owner already said
  yes to this plugin.
- **Only what git checked out runs by itself:** a `root/` that changed any
  other way (files uploaded in Fluidd's `plugins` folder, edited there,
  copied in over SSH, a plugin that is not a git clone) never runs on its
  own. The next Klipper start warns "its root/ changed outside git", and
  `ENABLE_PLUGIN NAME=<name> ROOT=1` on the enabled plugin runs `update.sh`
  then. Shipped plugins (in the image) count as checked out.
- `install.sh` must say ok (exit 0) before the plugin is switched on. Any
  other answer, a refusal or no answer at all leaves the plugin off.
- `update.sh` runs once per change: when it fails, the new copy is kept and
  the failure shows in the console and in `printer.ad5x_plugins.job`. A
  plugin without `update.sh` just gets the new copy.
- `uninstall.sh` runs from **root's copy**, the one made at the install or
  the last update, never from the plugin's own folder. After it, root
  deletes its copy and the plugin's boot scripts, whatever it answered, and
  the plugin is switched off or removed. When root refused (a print, no
  answer from Moonraker) the copy stays: `DISABLE_PLUGIN NAME=<name>` runs
  `uninstall.sh` again, also for a plugin that is already off or removed.
- An install without enabling (`INSTALL_PLUGIN` alone) runs nothing.
- At boot no install, update or uninstall script runs; only the boot
  scripts below.

## How a script runs

- As root, in `/data/ad5x/plugins-root/<name>` (root's copy of the
  plugin's `root/`, also the current directory), with umask 022 and stdin
  from `/dev/null`.
- With a clean environment:

| Variable | Value |
|---|---|
| `PATH` | `/usr/sbin:/usr/bin:/sbin:/bin` |
| `HOME`, `LANG` | `/root`, `C` |
| `PLUGIN` | The plugin name |
| `PLUGIN_DIR` | The plugin's own folder, for example `/data/ad5x/plugins/myplugin`. User `klipper` can change it: read data from it, never run it |
| `KILN_ACTION` | `install`, `update` or `uninstall` (for a boot script: `start` or `stop`) |

- 300 seconds at most. Then the script's process group is killed (TERM, then
  KILL 2 s later): the script and what it started in the foreground or with
  `&`. A process started in its own session (`start-stop-daemon -b`,
  `setsid`) keeps running. The answer is "timed out".
- Exit 0 is "ok"; any other code is "failed: exit N".
- Output (stdout and stderr) goes to `/data/ad5x/kiln-log/plugins-root.log`,
  with each script's result. The log is cut to its last 64 KiB at each boot.
  Never print secrets there.
- Refused while a print runs or is paused, while the print state is unknown,
  or when Moonraker gives no answer ("refused: ..."). A Klipper that isn't
  ready (startup, error) can't be printing: then scripts run, so a broken
  plugin can still be disabled.
- One at a time, in the same loop as Kiln OS updates: a script never runs
  while an update is being installed.

**Never run or source files from `PLUGIN_DIR`, or from any other path user
`klipper` can write, in your scripts.** Read them as data only (parse the
values you need and check each one). Anything you run must be a system file
or a file in root's copy (the current directory). The same goes for the
`#!` interpreter.

## Boot scripts

`install.sh` and `update.sh` may write boot scripts into
`/data/ad5x/plugins-root/init.d`, named like the ones in `/etc/init.d`:
`S<NN><plugin>` or `S<NN><plugin>.<suffix>`, for example `S50myplugin` or
`S50myplugin.watch`. Plugin names can't contain a dot, so the name says whose
a script is. `S69ad5x-plugin-boot` runs them:

- At boot, in the background: it waits until `S99ad5x-booted` has marked the
  start-up complete (at most 5 minutes), 15 seconds more, and while the
  recovery OS is being written into slot A (at most 10 minutes), so a script
  can't get in the way of either. Then it runs each script with `start`, in
  name order, 30 seconds each. Klipper, Moonraker and the touch screen don't
  wait for it: boot scripts start about half a minute to a minute after the
  screen.
- At shutdown it runs each one with `stop`, in reverse order, 10 seconds
  each.
- A script runs only when it is a plain file owned by root and not writable
  by group or others, and root has a copy of its plugin
  (`plugins-root/<plugin>`). Copy it from root's copy (for example
  `cp init.d/S50myplugin /data/ad5x/plugins-root/init.d/`), never from
  `PLUGIN_DIR`. Anything else is skipped with a line in the log.
- The same clean environment as above, with `KILN_ACTION` `start` or
  `stop` and `$1` the same.
- A failing script is logged and the next one runs.
- `uninstall.sh` doesn't need to delete them: root removes the plugin's boot
  scripts after it. It should stop what they started.

A boot script should start a long-running process with `start-stop-daemon`
in the background and a pidfile in `/run`, and stop it with the same
pidfile:

```sh
start-stop-daemon -S -b -m -p /run/myplugin-watch.pid -x /bin/sh -- /data/ad5x/plugins-root/myplugin/watch.sh
start-stop-daemon -K -p /run/myplugin-watch.pid
```

## Klipper commands and status

- `ENABLE_PLUGIN NAME=<name> ROOT=1 [RESTART=0]`: runs `install.sh`, then
  enables the plugin and restarts Klipper. Without `ROOT=1` a plugin with
  root scripts is refused.
- `INSTALL_PLUGIN NAME=<name> ENABLE=1 ROOT=1`: clones it, then the same.
  `ENABLE=1` without `ROOT=1` installs it and leaves it off, with a message.
  The touch screen's Install sends `ENABLE=1` without `ROOT=1`: its status
  line shows that message, and the plugin's switch then asks and sends
  `ENABLE_PLUGIN NAME=<name> ROOT=1`.
- `DISABLE_PLUGIN NAME=<name>` and `REMOVE_PLUGIN NAME=<name>`: run
  `uninstall.sh` first.
- Each request runs in the background like the git jobs:
  `printer.ad5x_plugins.job` shows `action` `root install`, `root update` or
  `root uninstall` while it runs (`state` `running`), then `done` or
  `failed` with root's answer in `message`; the console says the same.
  Klipper waits 360 seconds for an answer, then reports "no answer from
  root". One job at a time: another one is refused with "Busy".
- `LIST_PLUGINS` notes "root scripts installed" or "runs code as root:
  ENABLE_PLUGIN ROOT=1".
- `printer.ad5x_plugins.available.<name>` has `root` (it has root scripts)
  and `root_installed` (root has its copy).
- A plugin that is enabled and got root scripts later (an update added
  them) gets a warning at each start: disable it, then enable it with
  `ROOT=1`.

### How root checks a request

Klipper runs as user `klipper`, so it asks root through the update agent's
folder `/data/ad5x/kiln-update`: it packs the plugin's `root/` into
`plugin-<name>.tar` (the same files always give the same tar), then writes
`plugin-request` with three lines: the action, the plugin name and the tar's
sha256 (empty for `uninstall`). The agent:

1. moves both files into its own staging folder before it opens them (a link
   or a FIFO put there can't point root elsewhere or block it), and refuses
   anything but a plain file;
2. checks the action, the name (`a-z`, `0-9`, `_`, `-`) and the sha256;
3. refuses while a print may run;
4. unpacks the tar there (at most 8 MB), and refuses a link, a device node,
   a FIFO or a hard link to a file outside it;
5. makes everything root's (`root:root`, no group or other write, no
   set-user-ID bits), writes the sha256 into `.sha256`, and puts the result
   in place as `/data/ad5x/plugins-root/<name>`;
6. runs the script, and renames its answer into `plugin-status`.

Klipper compares the sha256 of the plugin's `root/` with `.sha256` at each
start to see whether `update.sh` must run, and runs it by itself only when
`git status` shows nothing changed, new or ignored in `root/`.

## Examples

### An nginx server for a second web UI

The image's nginx also reads `/data/ad5x/nginx/*.conf`. nginx doesn't check
who owns those files: keep them root's, as these scripts do (they run as
root). The plugin keeps its port in a file user `klipper` writes; the script
reads one value from it, checks it, writes the server, tests the whole
config, and restarts nginx. If the test fails, the old file comes back.

`root/install.sh` (and `root/update.sh`, a copy, or `exec ./install.sh`):

```sh
#!/bin/sh
CONF=/data/ad5x/nginx/myplugin.conf
# data only: one key, digits only, a fixed range
port=$(sed -n 's/^port *= *\([0-9]\{2,5\}\)$/\1/p' "$PLUGIN_DIR/settings.cfg" | head -n 1)
[ -n "$port" ] && [ "$port" -ge 81 ] && [ "$port" -le 65535 ] || port=81
mkdir -p /data/ad5x/nginx
rm -f /run/myplugin-old.conf
[ -f "$CONF" ] && cp "$CONF" /run/myplugin-old.conf
cat > "$CONF.new" <<EOF
server {
    listen $port;
    root /data/ad5x/plugins/myplugin/www;
}
EOF
mv "$CONF.new" "$CONF"
if nginx -t; then
	/etc/init.d/S63nginx restart
else
	echo "myplugin: nginx refused the config, the old one is back"
	if [ -f /run/myplugin-old.conf ]; then
		mv /run/myplugin-old.conf "$CONF"
	else
		rm -f "$CONF"
	fi
	exit 1
fi
```

`root/uninstall.sh`:

```sh
#!/bin/sh
rm -f /data/ad5x/nginx/myplugin.conf
nginx -t && /etc/init.d/S63nginx restart
```

nginx only serves the files in the plugin's folder: it reads them, it doesn't
run them.

### A device watcher at boot

`root/S50mywatch` is the boot script; `install.sh` puts it in place and
starts it, so it runs now and at every boot.

USB card readers don't need one from v1.0.1: `62-kiln-smartcard.rules`
gives every USB device with a smart-card (CCID) interface to group
`klipper` (0660), and USB serial adapters (CH340, CP210x, FTDI, PL2303,
CDC-ACM) are `/dev/ttyUSB*`/`/dev/ttyACM*` in group `dialout`, which
`klipper` is in. The example is for other USB devices:

```sh
#!/bin/sh
# root/install.sh
cp S50mywatch /data/ad5x/plugins-root/init.d/S50mywatch
chmod 755 /data/ad5x/plugins-root/init.d/S50mywatch
/data/ad5x/plugins-root/init.d/S50mywatch start
```

```sh
#!/bin/sh
# root/uninstall.sh (root deletes the boot script after this)
/data/ad5x/plugins-root/init.d/S50mywatch stop
```

```sh
#!/bin/sh
# root/S50mywatch: group klipper on the readers' USB nodes, rechecked every 5 s.
# The readers are fixed here by their USB ids, not read from a klipper file.
READERS="072f:2200 04e6:5591"
PID=/run/mywatch.pid
fix() {
	for u in /sys/bus/usb/devices/*; do
		[ -f "$u/idVendor" ] && [ -f "$u/busnum" ] || continue
		id="$(cat "$u/idVendor"):$(cat "$u/idProduct")"
		case " $READERS " in *" $id "*) ;; *) continue ;; esac
		node=/dev/bus/usb/$(printf %03d "$(cat "$u/busnum")")/$(printf %03d "$(cat "$u/devnum")")
		[ -c "$node" ] && chgrp klipper "$node" && chmod g+rw "$node"
	done
}
case $1 in
start) start-stop-daemon -S -b -m -p $PID -x /bin/sh -- "$0" watch ;;
watch) while :; do fix; sleep 5; done ;;
stop) start-stop-daemon -K -p $PID; rm -f $PID ;;
esac
exit 0
```

The watcher runs the boot script itself again (`$0`, root's file), so what
keeps running is root's copy too. Keep a watcher slow (seconds between
passes, not a busy loop).

## Files

| Path | Owner | |
|---|---|---|
| `/data/ad5x/plugins-root/` | root, 0755 | Root's copies of the plugins' `root/` folders |
| `/data/ad5x/plugins-root/<name>/` | root, nothing group/other-writable | The copy the scripts run from; `.sha256`, the sha256 of the tar it came from |
| `/data/ad5x/plugins-root/init.d/` | root, 0755 | The plugins' boot scripts |
| `/data/ad5x/plugins-root/.off` | root | While it exists, no boot script runs |
| `/data/ad5x/kiln-update/plugin-request`, `plugin-<name>.tar` | klipper | Klipper's request; root moves them away before reading them |
| `/data/ad5x/kiln-update/plugin-status` | root, renamed into klipper's folder | Root's answer |
| `/data/ad5x/kiln-stage/` | root, 0700 | Where root unpacks a request before it is put in place |
| `/data/ad5x/kiln-log/plugins-root.log` | root, 0644 | Output and results |

## Switching it off when the printer doesn't start

If a boot script keeps the main system from working (for example nginx or
the network), boot into the recovery system (`docs/recovery-os.md`), log in
over SSH and run one of these, then reboot into the main system:

- `touch /data/ad5x/plugins-root/.off`: no boot script runs (`rm` it again
  to switch them back on);
- `rm -f /data/ad5x/plugins-root/init.d/S??<name>*`: that plugin's boot
  scripts are gone;
- `rm -rf /data/ad5x/plugins-root/<name>`: root's copy is gone too, so its
  boot scripts are skipped; also delete the plugin's line in
  `printer_data/config/plugins.cfg` so it stays off.

The recovery system never runs plugin scripts: it has neither
`S69ad5x-plugin-boot` nor `plugin-root.sh`. Boot scripts also wait until the
start-up was marked complete, so a plugin can't stop the printer from keeping
a new system after an update.

## Limits

- A root script can do anything root can. `ROOT=1` is the only check, the
  same as with zMod: enable only plugins you trust, and read their `root/`
  first.
- `update.sh` runs after a plugin update (git) without asking again.

## Printer test (after an image build)

`S02sysctl`, `S68` and `S69` run at every main boot, so this needs a test
boot: `sysctl fs.protected_hardlinks fs.protected_symlinks
fs.protected_fifos fs.protected_regular` (all 1), `ENABLE_PLUGIN ROOT=1` with
a trial plugin (log, `printer.ad5x_plugins.job`), the refusal during a print,
an update with a changed `root/`, `DISABLE_PLUGIN`, a boot script after
`S99ad5x-booted`, then a reboot. And the recovery check: boot recovery,
`.off` works, `ad5x-boot-main`.
