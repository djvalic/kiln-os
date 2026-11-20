# Logs

Where Kiln OS writes its logs, how much it keeps, and how to get more when
you are chasing a problem.

## klippy.log

`printer_data/logs/klippy.log` (Fluidd and Mainsail: Logs). Klipper starts a
new file at midnight (`klippy.log.YYYY-MM-DD`); each file starts with the
config and the current limits (the rollover header).

### Log modes

| | `short` (the default) | `extended` |
|---|---|---|
| Stats line (Klipper's once-a-second status: load, MCU timing, heaters) | Once a minute while the printer is busy, and the first one after an idle spell | Every second while busy, as upstream Klipper |
| Before a shutdown ("Timer too close", `M112`, a heater error) | The last 2 min of Stats lines of this start, one a second, written ahead of `Transition to shutdown state` (see below) | Already in the log |
| An MCU that fails at connect | The same 2 min, from the session before | Already in the log |

The held back lines come as one block, `ad5x_log: N Stats lines held back
(shutdown):`. Those older than the last Stats line already in the log are
written as `held Stats ...`, the rest as plain `Stats ...` lines. That keeps
the plain ones in time order, which Klipper's `scripts/logextract.py`
needs to place them next to the MCU's dump.

```
LOG_MODE                          ; which mode is on
LOG_MODE MODE=extended            ; every Stats line, until set back
LOG_MODE MODE=extended HOURS=4    ; every Stats line for 4 h, then short
LOG_MODE MODE=short
```

The mode is saved (`save_variables`: `ad5x_log_mode`, `ad5x_log_until`) and
kept across restarts; `HOURS` counts across restarts too. The status is in
`printer.ad5x_log` (`mode`, `until` as Unix time). Root scripts read it from
`printer_data/comms/log-mode` (`short`, or `extended` with the end time).

Klipper's statistics still run every second in both modes (the heater
checks and the MCU clock depend on them); only the writing changes. For
Klipper's `scripts/graphstats.py` over a whole print, use `extended`: in
`short` it has one point a minute.

Code: `klipper/extras/ad5x_log.py`, `[ad5x_log]` in `ad5x.cfg`.

### Other klippy.log changes

- The config is written in full once per log file: a later start or
  `RESTART` with the same config writes one line instead
  (`===== Config file unchanged since ... in full further up this log =====`).
  A changed config, a new file or a new day writes it in full again. State:
  `printer_data/comms/klippy-config.json`. Klipper patch 0006.
- Messages from a board that no handler takes (`got {...}`, typically
  `analog_in_state` from a board still in shutdown after an emergency stop
  and a reboot) are logged in full for the first 20 of each kind, then
  counted once a minute. Klipper patch 0005.
- `SET_VELOCITY_LIMIT` isn't logged on every call (slicers send it per
  feature); the limits are in each file's header. Klipper patch 0004.

### How many old logs

Klipper keeps at most 5 dated files. Before Klipper starts (boot, Klipper
service restart), `S61klipper` also removes the oldest dated files once
they and `klippy.log` pass 50 MB together; `klippy.log` and the newest dated
file always stay (`buildroot/package/ad5x-system/lib/logs.sh`).

## The touch screen's and Moonraker's logs

The log mode also sets these, read from `printer_data/comms/log-mode` when
each one starts:

| | `short` | `extended` |
|---|---|---|
| `helixscreen.log` (HelixScreen) | warnings and errors | debug; the screen also follows a change at once (patch 0049) |
| `moonraker.log` | as upstream | verbose (`-v`): every API request and reply, from Moonraker's next start |

HelixScreen's own Log Level setting is hidden while Klipper has `[ad5x_log]`.
In `extended`, `moonraker.log` can hold secrets sent through the console or
the API, for example a notification URL with a bot token given to
`NOTIFY_SETUP`. Read it before attaching it to a public issue, or set
`LOG_MODE MODE=short` and restart Moonraker first.

Moonraker's database (`printer_data/database/moonraker-sql.db`) runs in
SQLite's write-ahead log mode (Moonraker patch 0005): the touch screen's
presence row every 10 minutes no longer costs a journal file and three
syncs each time.

## Kiln's own logs

Kiln's scripts append to a few small logs of their own: the update log
(`/data/ad5x/update/last.log`), the recovery update log
(`/data/ad5x/recovery/update.log`), the board tool's log
(`/data/ad5x/mcu/log`), the update agent's (`/data/ad5x/kiln-log/agent.log`),
the plugins' root scripts' (`/data/ad5x/kiln-log/plugins-root.log`,
`docs/plugin-root-hooks.md`) and `/data/ad5x/umask.log`. At each boot `S05ad5x-data` cuts each one to its
last 64 KiB, starting at a whole line (`kiln_logs_trim` in
`lib/logs.sh`). `wifi.log` (in `printer_data/logs`) keeps the current and
the previous start (`wifi.log.1`), and so does `network.log` (main OS: the
network stack chosen at start, NetworkManager's connections, its safety
net and the Wi-Fi networks written back to `wpa_supplicant.conf`;
[network.md](network.md)).

## Sending a log for an issue

1. If the problem isn't a shutdown (a stutter, a slow move, a print that
   looks wrong), run `LOG_MODE MODE=extended HOURS=24` first and reproduce.
2. Download `klippy.log` from Fluidd or Mainsail (Logs), and the dated file
   too if the problem was before midnight.
3. Attach both to the issue.
