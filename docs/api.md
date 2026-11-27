# Kiln OS API

What Kiln OS adds on top of stock Klipper and Moonraker, for anyone writing
a client, a slicer plugin or a dashboard. Everything else (printing,
files, temperatures, `printer.objects.*`, history, webcams, the update
manager's own endpoints) is upstream's API and is documented there:

- Moonraker: <https://moonraker.readthedocs.io/> (the printer runs
  Moonraker v0.11.0 with a few patches, `buildroot/package/moonraker/`;
  the ones that change the API are described below)
- Klipper status objects and G-code: <https://www.klipper3d.org/Status_Reference.html>,
  <https://www.klipper3d.org/G-Codes.html>

Plugins (code that runs on the printer) have their own page with the same
commands and status fields from the inside: `docs/plugin-api.md`.

In the examples, `PRINTER` stands for your printer's address (IP or host
name). "Since" is the first Kiln OS release that had it.

## Contents

- [Conventions](#conventions)
- [Moonraker endpoints added by Kiln](#moonraker-endpoints-added-by-kiln)
- [Changes to upstream Moonraker endpoints](#changes-to-upstream-moonraker-endpoints)
- [Update manager entries](#update-manager-entries)
- [Database namespace lane_data](#database-namespace-lane_data)
- [Warnings and notifications](#warnings-and-notifications)
- [Klipper status objects](#klipper-status-objects)
- [G-code commands](#g-code-commands)
- [Known quirks](#known-quirks)

## Conventions

### Where the API is

| | |
|---|---|
| HTTP | `http://PRINTER/` (nginx on port 80 passes `/printer/`, `/server/`, `/machine/`, `/access/`, `/api/` to Moonraker) or `http://PRINTER:7125/` (Moonraker itself) |
| Websocket (JSON-RPC 2.0) | `ws://PRINTER/websocket` or `ws://PRINTER:7125/websocket` |
| Login | None by default: Moonraker trusts clients on private networks (10/8, 172.16/12, 192.168/16, 169.254/16, link-local IPv6, localhost). Moonraker's API keys and users still work if you set them up |

Every endpoint has an HTTP form and a JSON-RPC method name. Moonraker
builds the method name from the path: `/machine/kiln_os/info` is
`machine.kiln_os.info`. Endpoints that Klipper provides (`/printer/...`)
take GET or POST alike; their method is the path with dots,
`printer.ad5x_setup.control`. An endpoint with both GET and POST gets
one method for each, `get_` or `post_` before the last part:
`/machine/kiln_os/memory` is `machine.kiln_os.get_memory` and
`machine.kiln_os.post_memory`.

### Replies

Every Kiln endpoint answers an object. Moonraker wraps HTTP replies in
`{"result": ...}` (not file uploads and downloads), so the HTTP body is
`{"result": {...}}`; over the websocket the object is the JSON-RPC
`result`. The examples show the HTTP body.

### Errors

A Kiln error has an HTTP status that says what kind of error it is, and a
short **reason** for programs at the start of the message, in brackets:

```json
{"error": {"code": 409, "message": "[printing] A print is running"}}
```

Over HTTP that is the body (Moonraker adds a `traceback` field), with
`code` as the HTTP status. Over the websocket it is the JSON-RPC error
object, `code` the same number, and Moonraker's endpoints add the reason
as `data`:

```json
{"jsonrpc": "2.0", "id": 7,
 "error": {"code": 409, "message": "[printing] A print is running",
           "data": {"reason": "printing"}}}
```

| Status | Kind |
|---|---|
| 400 | A bad or missing parameter, or a file the printer can't use (an upload) |
| 409 | Refused because of the printer's state: a print is running, start-up hasn't finished, nothing to retry |
| 500 | Something failed on the printer (the root agent's action, reading the kernel records) |
| 502 | An update download failed (update manager only) |
| 503 | The root update agent or Moonraker's database isn't there or didn't answer |
| 507 | Not enough storage (uploads only) |

The reason matches `^\[([a-z][a-z0-9_]*)\] ` at the start of the message:
read it there (it is the same over both transports) or from `data.reason`
where there is one. What follows it is meant for people: show that, as it
is. Moonraker's HTTP error body has no field for extra data (only `code`,
`message` and `traceback`), which is why the reason is in the message.
All reasons and where they come from: [Reasons](#reasons). A minor API
version can add reasons: handle one you don't know by its status.

Klipper's endpoints (`/printer/ad5x_*`) reach you through Moonraker, which
answers every Klipper error with **400** and without `data`; Kiln's
Klipper endpoints put the reason at the start of the message all the
same. Errors from Moonraker itself have no reason: 404 for an endpoint it
doesn't know (a Klipper endpoint before Klipper has connected once), 503
while Klipper is not connected, 400 for its own parameter checks. See
[Known quirks](#known-quirks).

Before v0.1.0-rc1 Kiln's errors had no reason and were all 400, and
`kernel_retry` and `boot_recovery` answered `{"result": "rebooting"}`
inside Moonraker's `result`; their replies keep that inner `result`
(deprecated) beside the new `state` (the CHANGELOG has the details).

#### Reasons

| Reason | Status | When | Endpoints |
|---|---|---|---|
| `bad_parameter` | 400 | A parameter is missing, unknown or out of range | `channel`, `memory`, `ifs_firmware`, `webui`, service actions, `ad5x_setup/control`, upload `plate` |
| `bad_3mf` | 400 | The uploaded `.3mf` can't be printed (no sliced plate, not a zip, encrypted, damaged, too large) | upload |
| `printing` | 409 | A print is running or paused | `kernel_retry`, `boot_recovery`, `ifs_firmware`, service actions, reboot and shutdown, Kiln OS and package updates, `ad5x_setup/control` |
| `print_state_unknown` | 409 | The agent couldn't tell whether a print is running (Klipper or Moonraker didn't say); try again | as `printing`, not `ad5x_setup/control` |
| `starting_up` | 409 | Start-up hasn't finished (the boot flag still points elsewhere, or `S99ad5x-booted` hasn't marked this boot's start-up finished); try again in a minute | `kernel_retry`, `boot_recovery`, Kiln OS update, reboot and shutdown (only in the first 10 minutes after boot) |
| `recovery_updating` | 409 | The recovery OS is being written into slot A; try again in a few minutes | `boot_recovery`, Kiln OS update, reboot and shutdown |
| `no_recovery` | 409 | Slot A doesn't hold the recovery OS, or not its whole kernel | `boot_recovery`, Kiln OS update |
| `refused` | 409 | Another refusal of the agent (the message says why) | `boot_recovery` |
| `nothing_to_retry` | 409 | Kiln's kernel runs and nothing is recorded as failed | `kernel_retry` |
| `no_own_kernel` | 409 | This image has no kernel of its own | `kernel_retry` |
| `not_available` | 409 | Extended memory needs a printer with 512 MiB (this one has 256 MiB, or its size is unknown); the image has no Klipper firmware for the IFS; the printer has no copy of that web interface | `memory` (POST), `ifs_firmware` (POST), `webui` (POST) |
| `plugin_manages_webui` | 409 | The mainsail-kiln plugin serves both web interfaces (ports 80 and 81) and picks port 80 itself (its `WEB` macro); disable it to switch with Kiln | `webui` (POST) |
| `not_enabled` | 409 | The owner hasn't turned the IFS firmware switch on (`/data/ad5x/ifs-switch.enable`) | `ifs_firmware` (POST, `klipper`) |
| `ifs_switching` | 409 | The IFS firmware is being switched (Klipper is stopped); try again in a few minutes | `ifs_firmware` (POST), `kernel_retry`, `boot_recovery`, `return_stock`, service actions, reboot and shutdown, Kiln OS and package updates |
| `printer_busy` | 409 | Klipper is running a command (`idle_timeout` `Printing`, such as a filament load from the console) | `ifs_firmware` (POST) |
| `step_running` | 409 | Another setup step is running or waiting (abort it first) | `ad5x_setup/control` |
| `not_waiting` | 409 | `adjust`/`accept` while no step waits for it | `ad5x_setup/control` |
| `restart_needed` | 409 | An aborted PID test left a heater off: restart Klipper first | `ad5x_setup/control` |
| `agent_failed` | 500 | The root agent's action failed (`ad5x-kernel retry`, an init script, `ad5x-update`, the boot flag, `ad5x-memory`, `ad5x-webui`) | `kernel_retry`, `boot_recovery`, `memory` (POST), `ifs_firmware` (POST), `webui` (POST), service actions, updates |
| `kernel_records_unreadable` | 500 | The kernel fallback's records can't be read | `kernel`, `kernel_retry` |
| `unpack_failed` | 500 | Writing the G-code of a `.3mf` failed | upload |
| `failed` | 500 (400 through Moonraker) | Another failure in a Kiln Klipper module (the message says what) | `ad5x_setup/control` |
| `internal_error` | 500 (400 through Moonraker) | An unexpected error in a Kiln Klipper module (a bug: please report it) | `ad5x_setup/control` |
| `download_failed` | 502 | The update download failed or doesn't match `SHA256SUMS` | Kiln OS and package updates |
| `agent_unavailable` | 503 | The root update agent's request folder isn't there (`S68ad5x-update-agent` never started) | `kernel_retry`, `boot_recovery`, `memory` (POST), `webui` (POST), service actions, reboot and shutdown, updates |
| `agent_timeout` | 503 | The root update agent didn't answer in time | `kernel_retry`, `boot_recovery`, `memory` (POST), `webui` (POST), service actions, reboot and shutdown, updates |
| `database_unavailable` | 503 | Moonraker's database isn't loaded | `channel`, `memory_notice_seen` |
| `no_space` | 507 | Not enough free space for the G-code of a `.3mf` | upload |

The statuses in brackets: `ad5x_setup/control` is a Klipper endpoint, and
Moonraker answers its errors with 400 (above).

### Versions

`GET /machine/kiln_os/info` gives two versions and a list of features:

- `os_version`: the Kiln OS release (`v1.0.0`, or `v1.0.0+3.gabc1234` for
  a build 3 commits after a release). Semver: a `-rc2` sorts before its
  release, `+...` is build metadata. It is not the API version below:
  Kiln OS 1.x and the API's own number move on their own.
- `api_version`: the Kiln API version, `MAJOR.MINOR`. It is the same
  number as the plugin API (`docs/plugin-api.md`), and the same rules
  apply to this page: a **minor** step only adds (endpoints, parameters,
  reply fields, status fields, commands); a **major** step changes or
  removes something listed here, and the release notes say what. Ignore
  fields you don't know: new ones can appear in any minor step.
- `features`: names of what this OS offers (below). Prefer checking a
  feature over comparing versions.

On a printer older than `/machine/kiln_os/info` (before v0.1.0-rc1), the
endpoint answers 404. Use `/server/info` (`klippy_state`) and the update
manager's `Kiln OS` entry (`version`) there.

#### Feature names

| Name | What it means |
|---|---|
| `ifs` | Kiln's IFS support: `printer.ifs`, `printer.ifs_materials`, the `IFS_*` commands. Whether a unit is connected is `printer.ifs.connected`; with a plugin that drives the IFS itself, `printer.ad5x_plugins.ifs_owner` names it and the `ifs` object is absent |
| `soak` | Bed heat soak: `printer.ad5x_soak`, `/printer/ad5x_soak/abort` |
| `setup_wizard` | `printer.ad5x_setup`, `/printer/ad5x_setup/control`, `SETUP_WIZARD_STEP` |
| `plugins` | Plugins: `printer.ad5x_plugins`, `ENABLE_PLUGIN` and friends |
| `kernel_retry` | `GET /machine/kiln_os/kernel`, `POST /machine/kiln_os/kernel_retry` |
| `boot_recovery` | `POST /machine/kiln_os/boot_recovery` |
| `return_stock` | `POST /machine/kiln_os/return_stock` |
| `3mf_upload` | Uploads of sliced `.gcode.3mf` are unpacked to G-code; form field `plate` |
| `print_error` | Upload replies carry `print_error` when a requested print didn't start |
| `updates` | The update manager has the `Kiln OS` entry (present unless `[kiln_os]` lost its `[update_manager]`) |
| `lane_data` | The `lane_data` database namespace is kept up to date (`[kiln_lanes]` loaded); with AFC in Klipper by AFC, not Kiln ([lane_data](#database-namespace-lane_data)) |
| `memory_mode` | This printer has 512 MiB and can use Extended memory mode: `/machine/kiln_os/memory`, `KILN_MEMORY_MODE`. Absent on 256 MiB printers |
| `ifs_firmware` | `GET`/`POST /machine/kiln_os/ifs_firmware`, the IFS firmware switch. Whether it can be offered on this printer is its `available` |
| `webui` | `GET`/`POST /machine/kiln_os/webui`, `KILN_WEBUI`: the web interface on port 80, Fluidd or Mainsail. Which ones this printer has is its `available` |

A feature is listed when Moonraker's side of it is there. The Klipper
objects behind `ifs`, `soak`, `setup_wizard` and `plugins` exist once
Klipper has started (`printer.objects.list`).

## Moonraker endpoints added by Kiln

| Endpoint | JSON-RPC | Since |
|---|---|---|
| `GET /machine/kiln_os/info` | `machine.kiln_os.info` | v0.1.0-rc1 |
| `GET /machine/kiln_os/kernel` | `machine.kiln_os.kernel` | v0.0.50 |
| `POST /machine/kiln_os/kernel_retry` | `machine.kiln_os.kernel_retry` | v0.0.50 |
| `POST /machine/kiln_os/boot_recovery` | `machine.kiln_os.boot_recovery` | v0.0.55 |
| `POST /machine/kiln_os/return_stock` | `machine.kiln_os.return_stock` | v1.0.0 |
| `POST /machine/kiln_os/channel` | `machine.kiln_os.channel` | v0.1.0-rc1 |
| `GET\|POST /machine/kiln_os/memory` | `machine.kiln_os.get_memory`, `machine.kiln_os.post_memory` | v1.0.0 |
| `POST /machine/kiln_os/memory_notice_seen` | `machine.kiln_os.memory_notice_seen` | v1.0.0 |
| `GET\|POST /machine/kiln_os/ifs_firmware` | `machine.kiln_os.get_ifs_firmware`, `machine.kiln_os.post_ifs_firmware` | (v1.0.0) |
| `GET\|POST /machine/kiln_os/webui` | `machine.kiln_os.get_webui`, `machine.kiln_os.post_webui` | (v1.0.1) |
| `GET\|POST /printer/ad5x_setup/control` | `printer.ad5x_setup.control` | v0.0.1 |
| `GET\|POST /printer/ad5x_soak/abort` | `printer.ad5x_soak.abort` | v0.0.10 |

The first ten are Moonraker's `kiln_os` component
(`moonraker/components/kiln_os.py`); the last two come from Klipper
(`klipper/extras/ad5x_setup.py`, `ad5x_soak.py`) and Moonraker passes them
on.

### GET /machine/kiln_os/info

The OS and API version, the running kernel, the feature names and the
update channel. No parameters. Never fails while Moonraker runs.

```sh
curl http://PRINTER/machine/kiln_os/info
```

```json
{"result": {
  "os_version": "v1.0.0",
  "api_version": "1.9",
  "kernel": "6.6.18-ad5x",
  "features": ["ifs", "soak", "setup_wizard", "plugins", "kernel_retry",
               "boot_recovery", "3mf_upload", "print_error", "return_stock",
               "ifs_firmware", "updates", "lane_data"],
  "update_channel": "stable"
}}
```

| Field | Type | |
|---|---|---|
| `os_version` | string | `VERSION` from `/etc/kiln-version`; `v0.0.0` when the file is missing |
| `api_version` | string or null | `AD5X_PLUGIN_API` from `/usr/lib/os-release` (the build copies Klipper's `PLUGIN_API_VERSION` there); null when missing |
| `kernel` | string | The running kernel's release (`uname -r`): `5.10.*` stock, `6.6.*` Kiln's default, `7.3.*` the opt-in mainline kernel |
| `features` | list of strings | See [Feature names](#feature-names) |
| `update_channel` | string | `stable` (default) or `test`: which Kiln OS releases the update manager offers (see [POST /machine/kiln_os/channel](#post-machinekiln_oschannel)) |

Since v0.1.0-rc1.

### POST /machine/kiln_os/channel

Sets the printer's update channel. Parameter `channel`: `stable` (the
default: `releases/latest`, no pre-releases) or `test` (the newest Kiln OS
release including pre-releases, so release candidates; no drafts). Kept
in Moonraker's database (namespace `kiln_os`, key `update_channel`;
protected: clients can read it with `/server/database/item`, only this
endpoint writes it), so it survives updates. Takes effect at the next
update check: the "Kiln OS" entry offers nothing until then (refresh with
`POST /machine/update/refresh?name=Kiln%20OS` or Fluidd's refresh
button). Switching back to `stable` never downgrades: an older stable
release is not offered. How to join and leave: docs/updates.md, "Test
channel".

```sh
curl -X POST 'http://PRINTER/machine/kiln_os/channel?channel=test'
```

```json
{"result": {"channel": "test", "previous": "stable"}}
```

Errors:

| Status | Reason | When |
|---|---|---|
| 400 | `bad_parameter` | No `channel`, or one other than `stable` or `test` (case and spaces don't matter) |
| 503 | `database_unavailable` | Moonraker's database is not loaded |

Since v0.1.0-rc1.

### GET /machine/kiln_os/kernel

Which kernel runs and what the boot-time kernel fallback recorded.
Kiln OS starts its own 6.6 kernel from the stock 5.10 one; when that
fails, the printer starts on 5.10 and records why (the same for the
opt-in 7.3 kernel, which falls back to 6.6). No parameters.

```sh
curl http://PRINTER/machine/kiln_os/kernel
```

```json
{"result": {
  "running": "5.10.186+",
  "stock": true,
  "ours": "6.6.18-ad5x",
  "failed": "6.6.18-ad5x",
  "failed_why": "start-up unfinished, 2 in a row",
  "ours_failed": true,
  "unfinished": 0,
  "mainline": "7.3.4-ad5x",
  "mainline_on": false,
  "mainline_failed": false,
  "mainline_failed_why": ""
}}
```

| Field | Type | |
|---|---|---|
| `running` | string | The running kernel's release |
| `stock` | bool | The stock 5.10 kernel runs |
| `ours` | string | The release of the 6.6 kernel in this image, "" if none |
| `failed` | string | The release the fallback recorded as failed, "" none |
| `failed_why` | string | Why, "" unknown (older records have no reason) |
| `ours_failed` | bool | `failed` is this image's 6.6 kernel: the printer runs stock until a retry |
| `unfinished` | int | Starts of the 6.6 kernel in a row that didn't finish (the fallback triggers at 2) |
| `mainline` | string | The release of the opt-in 7.3 kernel in this image, "" if none. Since v0.0.60 |
| `mainline_on` | bool | 7.3 is turned on (`ad5x-kernel mainline on`). Since v0.0.60 |
| `mainline_failed` | bool | This image's 7.3 kernel is recorded as failed (the printer runs 6.6). Since v0.0.60 |
| `mainline_failed_why` | string | Why. Since v0.0.60 |

Errors:

| Status | Reason | When |
|---|---|---|
| 500 | `kernel_records_unreadable` | The records can't be read (message: `[kernel_records_unreadable] Can't read the kernel records: ...`) |

The update manager's `Kiln OS` entry carries the same object as `kernel`;
there an unreadable record gives `{"error": "..."}` instead of the fields,
so the rest of the update status still shows. (Before v0.1.0-rc1 this
endpoint failed with an unexplained 500 then.)

Since v0.0.50 (the `mainline*` fields v0.0.60).

### POST /machine/kiln_os/kernel_retry

Clears the failure records and reboots, so the next start tries Kiln's
kernel again (6.6, and 7.3 if it is turned on). The printer's root update
agent does it; it refuses while a print may run. No parameters. Waits up
to 30 s for the agent.

```sh
curl -X POST http://PRINTER/machine/kiln_os/kernel_retry
```

```json
{"result": {"state": "rebooting", "result": "rebooting"}}
```

| Field | Type | |
|---|---|---|
| `state` | string | `rebooting` |
| `result` | string | **Deprecated**: the same value, kept for touch screens before v0.1.0-rc1 (they read `result.result`); removed at the next major API version. Read `state` |

The printer reboots right after this reply (about a minute). Moonraker's
`kiln_os_kernel` warning goes away at once.

Errors (the message after the reason, as an example):

| Status | Reason | Message | When |
|---|---|---|---|
| 409 | `nothing_to_retry` | `Kiln's kernel is running: nothing to retry` | 6.6 runs and nothing is recorded as failed |
| 409 | `no_own_kernel` | `This image has no kernel of its own` | No 6.6 kernel in this image |
| 409 | `printing` | `A print is running` | Printing or paused |
| 409 | `print_state_unknown` | `The print state is unknown, try again`, `No answer from Moonraker` | The agent couldn't tell |
| 409 | `starting_up` | `Start-up has not finished yet, try again in a minute` | Right after boot |
| 500 | `kernel_records_unreadable` | `Can't read the kernel records: ...` | The records are unreadable |
| 500 | `agent_failed` | `The update agent failed: ...` | `ad5x-kernel retry` failed |
| 503 | `agent_timeout` | `The update agent didn't answer in 30 s (is S68ad5x-update-agent running?)` | No answer in 30 s |
| 503 | `agent_unavailable` | `The update agent isn't available (...)` | The agent never started |

Since v0.0.50; `state` and these statuses and reasons since v0.1.0-rc1
(before: `{"result": {"result": "rebooting"}}`, and 400 with `Update
agent: ...` messages).

### POST /machine/kiln_os/boot_recovery

Reboots into the recovery OS (the small system in slot A that installs
updates and can restore the printer). Refused while a print may run, during
start-up, or when slot A doesn't hold the recovery OS. No parameters. Waits
up to 30 s for the agent. The touch screen's Settings > "Boot into
recovery" uses it.

```sh
curl -X POST http://PRINTER/machine/kiln_os/boot_recovery
```

```json
{"result": {"state": "rebooting", "result": "rebooting"}}
```

The fields as `kernel_retry`'s: read `state`; `result` is deprecated.

Errors:

| Status | Reason | Message | When |
|---|---|---|---|
| 409 | `printing` | `A print is running` | Printing or paused |
| 409 | `print_state_unknown` | `The print state is unknown, try again`, `No answer from Moonraker` | The agent couldn't tell |
| 409 | `starting_up` | `Start-up has not finished yet, try again in a minute` | Right after boot |
| 409 | `recovery_updating` | `The recovery OS is being written into slot A (...); try again in a few minutes` | A new recovery OS is being installed |
| 409 | `no_recovery` | `Slot A doesn't hold the recovery OS (it holds: ...)`, or `Slot A doesn't hold the recovery OS's kernel: no complete uImage in ... (header or data CRC wrong)` | The second: the recovery OS's kernel is incomplete (a reboot cut its write short) |
| 409 | `refused` | (the agent's text) | Any other refusal |
| 500 | `agent_failed` | `The update agent failed: can't write the boot flag` | |
| 503 | `agent_timeout`, `agent_unavailable` | As `kernel_retry` | |

Since v0.0.55; `state` and these statuses and reasons since v0.1.0-rc1
(before: `{"result": {"result": "rebooting"}}`, 400).

### POST /machine/kiln_os/return_stock

Reboots into the recovery OS, which then opens "Return to Flashforge
firmware" on its screen: it looks for Flashforge's files (the stock copy
on the printer, on usershare, or on a USB stick, or Flashforge's own
`AD5X-*.tgz` there) and puts Flashforge's firmware back only after a tap
there (`docs/install.md`, "Going back to stock"). This request itself
writes only the boot flag and the request file
`/data/ad5x/return-stock/request`. No parameters; the same answer, checks
and errors as `boot_recovery`. The touch screen's Settings > System >
"Return to Flashforge firmware" uses it.

```sh
curl -X POST http://PRINTER/machine/kiln_os/return_stock
```

```json
{"result": {"state": "rebooting", "result": "rebooting"}}
```

Since v1.0.0.

### GET /machine/kiln_os/memory

Extended memory mode (`docs/memory.md`). Every printer starts in
**standard** mode: Kiln OS uses 256 MiB, the same on every AD5X. A printer
with 512 MiB (X2600H) can switch **Extended memory** on, which gives the
kernel all 512 MiB from the next start. The switch is kept in `/data`
(`/data/ad5x/kernel/extended-memory`), so it survives restarts and
updates. A start in extended mode that doesn't finish turns it off by
itself: the next start is standard and `failed` says why. No parameters.
Never fails while Moonraker runs.

```sh
curl http://PRINTER/machine/kiln_os/memory
```

```json
{"result": {
  "available": true,
  "enabled": false,
  "active": "standard",
  "restart_needed": false,
  "failed": null,
  "notice_pending": true,
  "bootloader_update_needed": false,
  "hw_mem_mib": 512,
  "mem_kb": 243012
}}
```

| Field | Type | |
|---|---|---|
| `available` | boolean | The printer has 512 MiB, so Extended memory can be switched on. False on 256 MiB, and when the size is unknown (an OS whose `/run/ad5x-memory.conf` has no `HW_MEM_MIB`) |
| `enabled` | boolean | The switch is on and no failed start turned it off: the next start uses Extended memory |
| `active` | string | What this start got: `standard` or `extended` |
| `restart_needed` | boolean | `available` and `enabled` differ from `active`: the change takes effect at the next start. False when `bootloader_update_needed` (a restart wouldn't change it) |
| `failed` | string or null | Why Extended memory was turned off (the first line of `/data/ad5x/kernel/extended-memory-failed`: the reason and date); null when nothing failed. Switching it on again clears it. Show "Extended memory was turned off: the printer didn't finish starting with it." |
| `notice_pending` | boolean | Show the one-time notice "Extended memory available": `available`, this start standard, the switch off, the notice not seen yet ([POST /machine/kiln_os/memory_notice_seen](#post-machinekiln_osmemory_notice_seen)), and no `bootloader_update_needed` |
| `bootloader_update_needed` | boolean | `available`, and this start came from an older Kiln U-Boot (from before the memory mode, such as the rc3 opt-in boot loader) that can't choose the mode: it passes the board's memory as it always did, so only a boot loader update makes the switch count. Show "Needs a boot loader update to take effect." and don't offer a restart. `/run/ad5x-memory.conf` `MEM_MODE_FIXED=1` |
| `hw_mem_mib` | integer or null | The board's memory, 256 or 512, whatever mode this start got; null when unknown |
| `mem_kb` | integer or null | `MemTotal` of this start in kB (`/run/ad5x-memory.conf`); null when unknown |

Since v1.0.0. The feature name `memory_mode` is in
[`/machine/kiln_os/info`](#get-machinekiln_osinfo) on printers with
512 MiB.

### POST /machine/kiln_os/memory

Switches Extended memory on or off from the next start. Parameter
`enable`: `true` or `false` (also `1`/`0`, `on`/`off`; a JSON boolean over
the websocket). The root update agent runs `ad5x-memory extended on|off`,
which only writes or removes the switch (`on` also clears `failed`).
Nothing restarts and the running start doesn't change, so it is allowed
while printing. Restart the printer (`/machine/reboot`) to use it; the
touch screen offers that. Marks the notice seen. The reply is the same
object as `GET` after the change (`restart_needed` true until the
restart). With `bootloader_update_needed` the switch is still written; it
counts once the boot loader is updated (`restart_needed` stays false).
Waits up to 30 s for the agent.

```sh
curl -X POST 'http://PRINTER/machine/kiln_os/memory?enable=true'
```

```json
{"result": {
  "available": true, "enabled": true, "active": "standard",
  "restart_needed": true, "failed": null, "notice_pending": false,
  "bootloader_update_needed": false, "hw_mem_mib": 512, "mem_kb": 243012
}}
```

Errors:

| Status | Reason | When |
|---|---|---|
| 400 | `bad_parameter` | No `enable`, or not true or false |
| 409 | `not_available` | The printer has 256 MiB (or its size is unknown): `Extended memory needs 512 MiB of memory; this printer has 256 MiB` |
| 500 | `agent_failed` | `ad5x-memory` failed (the message has its output) |
| 503 | `agent_timeout`, `agent_unavailable` | As `kernel_retry` |

Since v1.0.0.

### POST /machine/kiln_os/memory_notice_seen

The one-time notice "Extended memory available" was seen: kept in
Moonraker's database (namespace `kiln_os`, key `memory_notice_seen`,
`true`; survives updates), so `notice_pending` stays false from now on.
The touch screen calls it when its bell shows the notice. The same notice
is a Moonraker announcement for Fluidd and Mainsail (see
[Announcement](#announcement-extended-memory-available)); this endpoint
dismisses it there too, and dismissing it there counts as seen. No
parameters; the reply is the `GET` object.

```sh
curl -X POST http://PRINTER/machine/kiln_os/memory_notice_seen
```

Errors: 503 `database_unavailable` when Moonraker's database is not
loaded.

Since v1.0.0.

### GET /machine/kiln_os/ifs_firmware

The IFS firmware switch (`docs/mcu-flashing.md`, "IFS firmware switch";
from PR #41 by Hunter Laux): which firmware the IFS runs, whether the
switch can be offered, and the last switch. No parameters. Never fails
while Moonraker runs, also while Klipper is stopped for a switch.

```sh
curl http://PRINTER/machine/kiln_os/ifs_firmware
```

```json
{"result": {
  "available": true,
  "enabled": true,
  "firmware": "stock",
  "state": "done",
  "target": "stock",
  "phase": null,
  "reason": null,
  "message": null,
  "version": "3.0.7",
  "klipper_version": "v0.13.0-806"
}}
```

| Field | Type | |
|---|---|---|
| `available` | boolean | Offer the switch: `enabled`, and this image has Klipper firmware for the IFS (`/usr/share/ad5x/mcu/ifs.hex`). The touch screen shows Settings > Devices > IFS firmware only then |
| `enabled` | boolean | The owner turned the switch on: `/data/ad5x/ifs-switch.enable` or `/data/ad5x/ifs-klipper.enable` exists (root's folder: no client can create it) |
| `firmware` | string | What the IFS runs: `klipper` (it answered as Klipper at Klipper's last start, or `printer.ifs.version` says Klipper), `stock` (`printer.ifs.version` is Flashforge's, such as `3.0.7`), else what the last finished switch put on; `unknown` while a switch runs or when nothing says |
| `state` | string | The last switch: `idle` (none on record), `running`, `done` or `failed` |
| `target` | string or null | What the last switch put on: `stock` or `klipper` |
| `phase` | string or null | While `running`: `stopping` (Klipper), `writing`, `replug` (the IFS's bootloader doesn't answer: unplug the IFS cable and plug it back in; the write carries on), `verifying`, `starting` (Klipper) |
| `reason` | string or null | When `failed`: `bad_image`, `no_stock_firmware` (no usable Flashforge `ifs.hex` on this printer), `no_bootloader`, `flash_failed`, `no_answer` (written, the firmware doesn't answer), `interrupted` (the printer restarted during the switch), `failed` |
| `message` | string or null | When `failed`: one line saying what went wrong |
| `version` | string or null | When `done`: what the IFS answered (`3.0.7`, `v0.13.0-806`) |
| `klipper_version` | string or null | The version of the Klipper firmware for the IFS in this image |

Fields may be added; ignore the ones you don't know.

### POST /machine/kiln_os/ifs_firmware

Switches the IFS to Flashforge's firmware or Klipper's. Parameter
`target`: `stock` or `klipper`. `klipper` only when `enabled` (the
owner's opt-in); `stock` for everyone. The root update agent checks
again, answers at once and switches in the background: Klipper stops,
the firmware is written and checked (Flashforge's `ifs.hex` from this
printer's own usershare backup, or Kiln's), Klipper starts again. That
takes 1 to 4 minutes; follow it with `GET` until `state` is no longer
`running`, then wait for Klipper. The reply is the `GET` object with
`state` `running`. There is no G-code command for it.

```sh
curl -X POST 'http://PRINTER/machine/kiln_os/ifs_firmware?target=klipper'
```

Errors:

| Status | Reason | When |
|---|---|---|
| 400 | `bad_parameter` | No `target`, or not `stock` or `klipper` |
| 409 | `not_enabled` | `klipper` without the owner's opt-in |
| 409 | `not_available` | `klipper`, and the image has no Klipper firmware for the IFS |
| 409 | `ifs_switching` | A switch runs |
| 409 | `printing`, `print_state_unknown` | A print is running or paused, or the agent couldn't tell |
| 409 | `printer_busy` | Klipper is running a command (`idle_timeout` `Printing`) |
| 500 | `agent_failed` | The agent rejected the request |
| 503 | `agent_timeout`, `agent_unavailable` | As `kernel_retry` |

While a switch runs, the agent refuses reboot, shutdown, service actions,
updates, `kernel_retry`, `boot_recovery` and `return_stock` with 409
`ifs_switching`.

Since v1.0.0 (API 1.8).

### GET /machine/kiln_os/webui

The web interface on port 80 (`docs/web-interface.md`): Fluidd (the
default) or Mainsail, one at a time. The printer's address
(`http://PRINTER/`) opens the chosen one; both use the same Moonraker,
cameras and touch screen view, and keep their settings apart. No
parameters. Never fails while Moonraker runs. It also brings the update
manager's entries in line with the choice (after `ad5x-webui` over SSH,
which asks for it itself).

```sh
curl http://PRINTER/machine/kiln_os/webui
```

```json
{"result": {
  "webui": "fluidd",
  "default": "fluidd",
  "served": "fluidd",
  "mismatch": false,
  "available": ["fluidd", "mainsail"],
  "versions": {"fluidd": "1.38.0", "mainsail": "2.19.0"},
  "plugin": null,
  "update_entries": ["fluidd"],
  "update_entries_pending": false,
  "moonraker_restart_needed": false
}}
```

| Field | Type | |
|---|---|---|
| `webui` | string | The choice: `fluidd` or `mainsail` (`/data/ad5x/webui`; `fluidd` when nothing valid is stored, or the chosen one isn't on this printer) |
| `default` | string | `fluidd` |
| `served` | string or null | What nginx's port 80 serves now (its root line, which Kiln keeps in line with what nginx runs: a failed reload puts the old one back); null when it is neither |
| `mismatch` | boolean | `served` is known and isn't `webui`, and no `plugin` serves both: a plugin put its own line back (mainsail-kiln's `DISABLE_PLUGIN` restores Fluidd's). Shut-out and update entries follow `served`. Choosing `webui` again (`POST`) puts them in line; so does the next start |
| `available` | list of strings | The web interfaces this printer has (in the image, or a copy in `/data/ad5x/web`). Offer the switch when it has two |
| `versions` | object | `release_info.json`'s version of each available one without a leading `v` (what would be served: the updated copy, else the image's); null when unreadable |
| `plugin` | string or null | `mainsail-kiln` while that community plugin serves both UIs (Mainsail and Fluidd on ports 80 and 81, swapped by its `WEB` macro): Kiln's switch is refused then |
| `update_entries` | list of strings | The web interfaces that have an update manager entry now: the served one (both while `plugin` serves both) |
| `update_entries_pending` | boolean | The entries are being brought in line in the background (right after a switch, or while an update holds the update manager): `update_entries` is the state before. The request never waits for it |
| `moonraker_restart_needed` | boolean | The update entries couldn't be brought in line while Moonraker runs (not expected; false while pending); Moonraker's next start sets them up. Restart it with `POST /machine/services/restart?service=moonraker` |

Only the chosen interface may use Moonraker: a websocket that identifies
(`server.connection.identify`) with `type` `web` and `client_name`
`fluidd` or `mainsail` but isn't the one `served` gets
`notify_gcode_response` `!! This printer now uses NAME: reload the page`
and is closed a second later (close code 1008), at every reconnect; at a
switch the open ones are closed the same way. Other clients (any other
name or type, or none) are never touched; neither is either interface
while `plugin` is set or while `served` is null. Each page nginx sends sets the cookie
`kiln_webui=NAME` for the service worker change-over
(`docs/web-interface.md`).

Since v1.0.1 (API 1.12).

### POST /machine/kiln_os/webui

Puts a web interface on port 80. Parameter `name`: `fluidd` or
`mainsail` (any case). The root update agent runs `ad5x-webui --no-sync
NAME`: it stores the choice, makes the UI's updatable copy in
`/data/ad5x/web/NAME` the first time (from the image, its text files
unpacked as Moonraker's own update writes them: about 10 MB for
Mainsail), points nginx at it (checked with `nginx -t`; the old setup back
when that or the reload fails) and reloads nginx. No reboot and no Moonraker restart;
allowed while printing (a print, Klipper and Moonraker aren't touched).
Pages of the old UI that are open lose their connection (see `GET`)
and show the old UI until they are reloaded: tell the user to reload.
The update manager's entries follow in the background, without
delaying the answer (`update_entries_pending`): the UI that is no longer
served loses its entry, the other gets its own back (its copy and its
updates stay). Choosing the stored one again re-applies it (useful when
`mismatch`). The reply is the `GET` object, plus:

| Field | Type | |
|---|---|---|
| `previous` | string | The choice before |
| `changed` | boolean | `webui` differs from `previous`, or `served` changed |
| `message` | string or null | The agent's text, for people (`Mainsail on port 80; reload the page in the browser`) |

Waits up to 30 s for the agent.

```sh
curl -X POST 'http://PRINTER/machine/kiln_os/webui?name=mainsail'
```

Errors:

| Status | Reason | When |
|---|---|---|
| 400 | `bad_parameter` | No `name`, or not `fluidd` or `mainsail` |
| 409 | `not_available` | This printer has no copy of that web interface |
| 409 | `plugin_manages_webui` | The mainsail-kiln plugin serves both (`plugin`) |
| 500 | `agent_failed` | `ad5x-webui` failed (the message has its answer, such as `nginx -t refused the new configuration; nothing changed`) |
| 503 | `agent_timeout`, `agent_unavailable` | As `kernel_retry` |

Since v1.0.1 (API 1.12).

### /printer/ad5x_setup/control

The setup wizard's steps (calibrations), the same actions as the G-code
command `SETUP_WIZARD_STEP`, but they get through while a long command
holds Klipper's G-code queue: this is the only way to abort a running PID
or mesh calibration. Follow progress in `printer.ad5x_setup`. Details of
each step: `docs/setup-wizard.md`.

| Parameter | Type | |
|---|---|---|
| `action` | string | `start` (default), `abort`, `adjust`, `accept`, `wizard` |
| `step` | string | For `start`: `selfcheck`, `pid`, `mesh`, `shaper`, `filament` (v1.0.0), `ifs`, `trash`, `zoffset`, `soak`, `summary`, `finish` |
| `delta` | number | For `adjust`: mm to move the Z offset (at most 0.5 per call, 1 mm in all from the start) |
| `heaters` | string | `pid`: `extruder`, `bed` or `both` (default) |
| `keep_bed` | 0/1 | `mesh`: leave the bed hot for the Z offset step |
| `channel` | int | `ifs`: tune one slot |
| `tube` | 0/1 | `ifs`: also test the tube pull-back |
| `material` | string | `zoffset`: patch temperatures for this material (default: the loaded slot's, else PLA) |
| `extruder`, `bed` | number | `zoffset`: temperatures, overriding `material` |
| `estimate` | 0/1 | `zoffset`: start from the load-cell estimate (needs `zoffset_estimate: True` in `[ad5x_setup]`) |
| `force` | 0/1 | `soak`: start on a warm bed instead of waiting for it to cool |
| `material_1`-`material_4` | string | `filament`: that slot's material (`PLA`, `PETG`, ...; "" or `?` clears it), as `IFS_SET_MATERIAL`. Since v1.0.0 |
| `head` | string | `filament`: the slot in the toolhead, `1`-`4` (with a strand left in the tube: that slot is pulled back); `0` empty (also: a strand pulled out by hand); `keep` filament the IFS doesn't feed, used as it is; `auto` (default) the one Kiln knows (loaded by Kiln or named; a slot only adopted at startup doesn't count), else found with `IFS_FIND_HEAD_SLOT` (which unloads it). `zoffset`: `keep` prints with the filament in the toolhead as it is, no find. Since v1.0.0 |

- `start` returns at once; the step runs in the background. Starting
  another step while one is `running` or `waiting_user` is refused,
  except `zoffset` again while its test patch waits (prints another patch).
- `abort` switches the heaters off at once (also during `M109`, `M190`
  and `PID_CALIBRATE`) and stops the IFS; the step ends after the move in
  progress. With nothing running it only switches the heaters off.
- `adjust` and `accept` work only while `state` is `waiting_user`
  (`adjust`: the Z offset patch; `accept`: Z offset and purge box steps,
  and the `clear_bed` prompt after the Z offset is saved: the test print
  is off the bed). `accept` also clears a `clear_bed` prompt left after a
  Z offset step that failed or was aborted.
- **Changed in v1.0.0 (from rc5):** one `accept` no longer ends the Z
  offset step. The first saves the offset; the step then waits with
  `prompt` `clear_bed` until a second `accept` (the test print is off the
  bed), at most `user_timeout` (15 min). A client that waited for `done`
  after one accept must send the second.
- `wizard` asks the touch screen to run the setup wizard again (as the
  `SETUP_WIZARD` macro).

```sh
curl -X POST http://PRINTER/printer/ad5x_setup/control \
  -H 'Content-Type: application/json' -d '{"action": "start", "step": "pid", "heaters": "extruder"}'
curl -X POST 'http://PRINTER/printer/ad5x_setup/control?action=adjust&delta=-0.02'
curl -X POST 'http://PRINTER/printer/ad5x_setup/control?action=abort'
```

```json
{"result": {"state": "running", "step": "pid", "message": "AD5X setup: pid started"}}
```

| Reply field | |
|---|---|
| `state`, `step` | As `printer.ad5x_setup` right after the action |
| `message` | What the action did |

Errors: always 400 (Moonraker's status for every Klipper error, no
`data`), with the reason at the start of the message and then the same
text as `SETUP_WIZARD_STEP` gives in the console:

| Reason | Message after it, for example |
|---|---|
| `bad_parameter` | `SETUP_WIZARD_STEP: STEP must be one of ...`, `SETUP_WIZARD_STEP: unknown ACTION '...'`, `SETUP_WIZARD_STEP: DELTA= must be between -0.5 and 0.5`, `SETUP_WIZARD_STEP: DELTA= must be a number`, `SETUP_WIZARD_STEP: Z offset would move more than 1 mm from where it started` |
| `printing` | `SETUP_WIZARD_STEP: no setup step during a print`, `SETUP_WIZARD_STEP: no setup wizard during a print` |
| `step_running` | `SETUP_WIZARD_STEP: step 'pid' is still running (ACTION=abort first)` |
| `not_waiting` | `SETUP_WIZARD_STEP: ACTION=adjust works only while the Z offset test patch is waiting for you` |
| `restart_needed` | `SETUP_WIZARD_STEP: extruder was left off by an aborted PID test: RESTART Klipper first` |
| `failed` | `Can't write ...` (the wizard request flag) |
| `internal_error` | `ad5x_setup: ...` (a bug) |

```json
{"error": {"code": 400, "message": "[step_running] SETUP_WIZARD_STEP: step 'pid' is still running (ACTION=abort first)"}}
```

Since v0.0.1; `heaters` since v0.0.10; `estimate`, `force` and the steps
`trash`, `soak`, `summary` by v0.0.17; reasons since v0.1.0-rc1.

### /printer/ad5x_soak/abort

Stops a running bed soak calibration (`BED_SOAK_CALIBRATE`, or the setup
wizard's `soak` step) within a second: heaters off, nothing saved. A G-code
command can't do this, because the calibration holds the G-code queue. No
parameters. With nothing running it does nothing.

```sh
curl -X POST http://PRINTER/printer/ad5x_soak/abort
```

```json
{"result": {"running": true}}
```

`running`: whether a calibration was running (and is now stopping). It
has no errors of its own.

Since v0.0.10.

## Changes to upstream Moonraker endpoints

### POST /server/files/upload

Upstream's upload, with two additions (Moonraker patches 0003 and 0004 in
`buildroot/package/moonraker/`).

**Sliced .3mf files print** (feature `3mf_upload`). A `.3mf` uploaded to
`gcodes` with sliced plates inside (OrcaSlicer "Use 3MF instead of G-code",
Bambu-style plate files) is unpacked: `Metadata/plate_<N>.gcode` becomes
`<name>.gcode` and the `.3mf` itself is not kept. With several sliced
plates, each becomes `<name>_plate<N>.gcode` and none is started, unless
the new form field `plate` picks one:

| Form field | |
|---|---|
| `plate` | Optional, a plate number: unpack and (with `print=true`) print that plate only |

A `.3mf` that can't be printed is refused, with a reason at the start of
the message (uploads are HTTP only, so there is no `data`):

| Status | Reason | When |
|---|---|---|
| 400 | `bad_parameter` | `plate` is not a number |
| 400 | `bad_3mf` | No sliced plate (a project file), a broken zip, an encrypted or damaged plate, a plate that isn't there, an implausible size |
| 507 | `no_space` | Not enough free space for the G-code |
| 500 | `unpack_failed` | Writing the G-code failed otherwise |

For example `[bad_3mf] x.3mf has no sliced plate (a project file): slice
it, then send it again, as G-code or as a sliced .gcode.3mf`. Reasons and
507 since v0.1.0-rc1 (before: 400 for all of them).

**Why a print didn't start** (feature `print_error`). With `print=true`,
upstream answers 201 with `print_started: false` and no reason when the
printer is busy or Klipper refuses. The reply now has `print_error`, the
same text goes to the console as `!! Upload <file>: print not started:
<reason>`, and the upload itself still succeeds (201), so don't send it
again.

```sh
curl -F file=@part.gcode.3mf -F print=true http://PRINTER/server/files/upload
```

```json
{"item": {"path": "part.gcode", "root": "gcodes", "modified": 1763030000.0,
          "size": 1834511, "permissions": "rw"},
 "print_started": false, "print_queued": false,
 "action": "create_file",
 "print_error": "a print is already running or paused"}
```

| `print_error` | When |
|---|---|
| `a print is already running or paused` | Busy |
| `the .3mf has several sliced plates, each unpacked to its own _plate<N>.gcode; start one of them` | Several plates, no `plate` |
| Klipper's message | Klipper refused the start |

`print_error` is absent when the print started, was queued (job queue),
or wasn't asked for. The reason of a refused upload (400) is also in the
HTTP reason phrase, not only in Moonraker's log.

Since v0.0.45.

### GET /server/files/list (`root=config`)

The flat list of the config root leaves out the files of the `plugins`
folder (the link to `/data/ad5x/plugins` that Kiln's `kiln_os` component
makes; Moonraker patch 0008). The list runs on Moonraker's event loop at
about 14 ms per file on the AD5X, and large plugins blocked Moonraker for
a minute at each call. To show plugin files, list the folder with
`GET /server/files/directory?path=config/plugins` (and its subfolders);
reading, uploading, moving and deleting there work as upstream, and
`notify_filelist_changed` still reports changes in it. Other roots and
folders are listed as upstream.

### `permissions` in file lists

`server.files.get_directory`, `server.files.list` and
`notify_filelist_changed` report `"r"` for a file Moonraker (user
`klipper`) can't write, or whose folder it can't write, and for a folder
it can't create files in (Moonraker patch 0010, issue #96). Upstream
reported `"rw"` for everything in a writable root. Only `"rw"` is
lowered; read-only roots, links, `.git` and reserved paths are as
upstream. Since v1.0.0.

### POST /printer/print/cancel during the print start

Upstream queues the cancel behind the running G-code command, which during
Kiln's `PRINT_START` is the whole start (several minutes). Kiln notes the
cancel when it arrives: the heating and soak waits end within a second,
the other steps at their next check, then `CANCEL_PRINT` runs as usual.
`printer.ad5x_soak.cancel` is true from the cancel until `CANCEL_PRINT`
has run. Same endpoint, same reply. Since v0.0.60.

### POST /machine/services/restart, start, stop (`provider: kiln_agent`)

Upstream's service endpoints (parameter `service`) and the update
manager's `managed_services` work through Kiln's `kiln_agent` provider
(`[machine] provider: kiln_agent`, Moonraker patch 0006): Moonraker writes
a `service` request ("ACTION NAME") for the root update agent, which runs
that service's init script. `/machine/system_info` lists the services in
`available_services` and `service_state` (`active`/`running` or
`inactive`/`dead`, from the init scripts' pid files).

| Service | Actions |
|---|---|
| `klipper`, `helixscreen`, `ad5x-camera` | `start`, `stop`, `restart` |
| `moonraker`, `nginx` | `restart` only; the reply comes first, the restart about 3 s later |

Errors as `kernel_retry` above: 409 `printing` or `print_state_unknown`
while a print may run, 500 `agent_failed` when the init script fails, 503
`agent_timeout` or `agent_unavailable`. A service or action that Kiln
doesn't offer (`stop` for `nginx`) answers 400 `bad_parameter`; Moonraker
itself refuses services it doesn't list (400, no reason). Waits up to 90 s
for the agent. Since v0.1.0-rc1 (before: `provider: none`, no service
actions).

### POST /machine/reboot, /machine/shutdown (`provider: kiln_agent`)

Upstream runs `sudo reboot` / `sudo poweroff` here. On Kiln the same
provider hands them to the root update agent instead (a `reboot` or
`shutdown` request, `S68ad5x-update-agent`), which checks first, answers,
and then reboots or powers off about 2 s later. The JSON-RPC methods
`machine.reboot` and `machine.shutdown` and the remote methods
`reboot_machine` and `shutdown_machine` (for other Moonraker components)
take the same path. No parameters; the reply is upstream's `"ok"`. Waits
up to 30 s for the agent. Fluidd's and the touch screen's Reboot and
Shutdown use it.

```sh
curl -X POST http://PRINTER/machine/reboot
```

Errors:

| Status | Reason | Message | When |
|---|---|---|---|
| 409 | `printing` | `A print is running` | Printing or paused |
| 409 | `print_state_unknown` | `The print state is unknown, try again`, `No answer from Moonraker` | The agent couldn't tell |
| 409 | `recovery_updating` | `The recovery OS is being written into slot A, try again in a few minutes` | A new recovery OS is being written (after a Kiln OS update): a reboot or power-off would cut it short |
| 409 | `starting_up` | `Start-up has not finished yet, try again in a minute` | Start-up hasn't finished and the printer started less than 10 minutes ago. After 10 minutes a start that never finished counts as hung, and the reboot goes ahead (the boot flag still points at the recovery OS, so the printer starts that) |
| 503 | `agent_timeout`, `agent_unavailable` | As `kernel_retry` | |

There is no `sudo` rule for the klipper user any more. Up to v1.0.0-rc2,
`/machine/reboot` ran `sudo reboot` with no checks, and
`/machine/shutdown` failed (sudo allowed only the reboot).

## Update manager entries

Kiln adds entries to upstream's update manager (`/machine/update/status`,
`/machine/update/refresh`, `/machine/update/upgrade`); Fluidd's Software
updates card uses them.

The web interface has upstream's own `web` entry, `fluidd` or
`mainsail`: only the one served on port 80 ([webui](#get-machinekiln_oswebui)
`update_entries`), for its copy in `/data/ad5x/web/<name>`. Fluidd's is
in `moonraker-updates.conf`, Mainsail's is added by Kiln with the same
settings (`type: web`, `channel: stable`, `repo: mainsail-crew/mainsail`);
a `[update_manager mainsail]` of your own in `moonraker.conf` (or a
plugin's) is used instead. Since v1.0.1.

Mainsail (v2.19.0) lists only entries of the types it knows (`git_repo`,
`zip`, `web`, `python`, `executable`): the `Kiln OS`, `klipper` and
`moonraker` entries below (`kiln_os`, `kiln_app`) don't show in its
update panel. Update Kiln OS from the touch screen or Fluidd then, or
with the endpoints below.

### "Kiln OS"

The OS itself. `name` and key are both `Kiln OS` (with the space).

```sh
curl http://PRINTER/machine/update/status
curl -X POST 'http://PRINTER/machine/update/upgrade?name=Kiln%20OS'
```

`version_info["Kiln OS"]`:

| Field | Type | |
|---|---|---|
| `name` | string | `Kiln OS` |
| `configured_type` | string | `kiln_os` |
| `version` | string | Running release (`/etc/kiln-version`) |
| `remote_version` | string | Newest release on the update server for the channel (`stable`: no drafts, no pre-releases; `test`: pre-releases too), `?` before the first check and after a channel change |
| `full_version_string` | string | Same as `version` |
| `remote_url` | string | The repository |
| `release_notes` | string | The newest release's notes (first 4000 characters) |
| `channel` | string | `stable` or `test` (the update channel; `stable` before v0.1.0-rc1) |
| `is_valid` | bool | Always true |
| `debug_enabled` | bool | Always false |
| `info_tags`, `anomalies` | list | Empty |
| `warnings` | list of strings | `Update check failed: ...` |
| `kernel` | object | As `GET /machine/kiln_os/kernel` (since v0.0.50) |

Upgrade downloads `kiln-os-<version>-update.zip`, checks it against the
release's `SHA256SUMS`, and the printer reboots into the recovery OS,
which installs it (3-6 minutes). Progress comes as upstream's
`notify_update_response` (`Downloading ... MiB`, `Downloading: N%`,
`Checking the download...`, `Staging the update for the recovery OS...`,
then `Kiln OS vX staged. The printer reboots now ...` with `complete:
true`). Errors from the upgrade: the agent's as for `kernel_retry` (409
`printing`, `print_state_unknown`, `starting_up`; 500 `agent_failed`; 503
`agent_timeout`, `agent_unavailable`), 409 `recovery_updating` while the
recovery OS is being written into slot A (at once; up to v1.0.0-rc2 the
agent waited up to 3 minutes for the write while Moonraker gave up after
2 and answered `agent_timeout`, though the update then went ahead), and 502 `download_failed` when the download fails, is
incomplete or doesn't match `SHA256SUMS`. Moonraker waits up to 180 s for
the agent. Moonraker's own refusals (another update running) have no
reason.

Since v0.0.1 (named `Kiln OS` since v0.0.2).

### "klipper" and "moonraker" (`kiln_app`)

Upstream's own `klipper` and `moonraker` entries, filled by Kiln: they
offer Kiln's tested daily packages of Klipper and Moonraker (GitHub
pre-releases `klipper-vX.Y.Z-N-gHASH`), the newest one this OS version
accepts. Upgrade installs it into `/data/ad5x/apps/<name>` and restarts
that service; a Kiln OS update brings newer ones with the image. Errors as
the `Kiln OS` entry's (without `starting_up`).

| Field | |
|---|---|
| `configured_type` | `kiln_app` |
| `version`, `remote_version` | Short form `v0.13.0-827` (git describe count as a pre-release), so semver compares them |
| `full_version_string` | `v0.13.0-827-g29d4ec2d6-ad5x (daily package)` or `(part of Kiln OS)` |
| `channel` | `dev` |
| others | As the `Kiln OS` entry, without `kernel` |

Since v0.0.1.

## Database namespace lane_data

Moonraker's database namespace `lane_data` holds the IFS slots in the
shape AFC uses, for OrcaSlicer's Moonraker printer agent (filament list
from what is loaded, `docs/orcaslicer.md`). Kiln writes it from
`printer.ifs_materials` and `printer.ifs.loaded_channels` whenever they
change, only the records whose content changed; it isn't written when
Klipper has no `ifs` object. Kiln changes only the fields in the table
below and keeps any other key a client stored in a record; what you write
into those fields is overwritten at the next change or check.

```sh
curl 'http://PRINTER/server/database/item?namespace=lane_data'
```

```json
{"result": {"namespace": "lane_data", "key": null, "value": {
  "lane1": {"lane": "0", "material": "PLA", "color": "#FF0000",
            "nozzle_temp": 220, "bed_temp": 0, "filament_id": "PKLNPLA",
            "spool_id": null, "scan_time": "2026-11-13T09:12:44Z"},
  "lane2": {"lane": "1", "material": "", "color": "", "nozzle_temp": 0,
            "bed_temp": 0, "spool_id": null, "scan_time": ""},
  "lane3": {...}, "lane4": {...}}}}
```

| Field | Type | |
|---|---|---|
| key `lane1`..`lane4` | | IFS slot 1-4 |
| `lane` | string | Slicer tool index, `"0"`-`"3"` (slot 1 = T0, the default tool map) |
| `material` | string | Material type, "" when the slot has no filament or no type set |
| `color` | string | `#RRGGBB`, "" with no material |
| `nozzle_temp` | int | The slot's nozzle temperature (its own or the material's default), 0 none |
| `bed_temp` | int | The slot's `IFS_SET_MATERIAL BED_TEMP=` (plugin API 1.12), else 0. Without one, a positive one HelixScreen stored stays until the slot's material changes or the slot empties. Since v1.0.1 |
| `filament_id` | string | The slot's `IFS_SET_MATERIAL FILAMENT_ID=`, exactly as sent (an id from OrcaSlicer's own filament library, e.g. `OFDSrzZ8` for Generic PLA; plugin API 1.12). Without one: the OrcaSlicer filament id of Kiln's profile for the type (kiln-orca): PLA `PKLNPLA`, SILK `PKLNSLK`, PLA-CF `PKLNPCF`, PETG `PKLNPET`, PETG-CF `PKLNPGC`, ABS `PKLNABS`, TPU `PKLNTPU` (type matched in any case); no key for any other type or an empty slot; HelixScreen's own string id (with `helix_filament_id_source` or `helix_catalog_id` in the record) is kept instead, also over an empty slot or a material change. Since v1.0.1 |
| `spool_id` | int or null | The slot's `IFS_SET_MATERIAL SPOOL_ID=` (plugin API 1.12). Without one, kept as stored (HelixScreen's linked Spoolman spool, also over an empty slot); null in a record Kiln creates |
| `vendor_name`, `name` | string | The slot's `IFS_SET_MATERIAL VENDOR=` and `NAME=` (plugin API 1.12). Without one, kept as stored (HelixScreen's); no key in a record Kiln creates |
| `scan_time` | string | UTC `YYYY-MM-DDTHH:MM:SSZ` of the slot's last change Kiln saw, or of the last HelixScreen write; "" in a record Kiln creates |

The slot's own `SPOOL_ID`, `VENDOR`, `NAME`, `FILAMENT_ID` and
`BED_TEMP` (all optional, `IFS_SET_MATERIAL`) win over what another
writer stored; one Kiln wrote and the slot no longer has (cleared, or
the slot's filament out) is taken out again, unless HelixScreen wrote
the record since (then the value counts as HelixScreen's). After a
Moonraker restart, a record without `writer` counts as Kiln's: its
spool details follow the slot as it is now. A change of spool details
alone leaves HelixScreen's `bed_temp`. Like the type and colour,
they are left out while the slot has no filament or no type. No `vendor`
or `spool_name` keys from Kiln (HelixScreen's own spellings), and never
`writer`. Since v0.0.5.
HelixScreen writes records under the same keys too (`"writer":
"helixscreen"` and more fields: `filament_type`, `vendor_name`, `name`,
`spool_id`, `helix_*`, its `filament_id` a string or null), each time the
whole record. Since v1.0.1 Kiln merges: it keeps HelixScreen's keys, and a
check 5 s after each slot change and every 60 s (a read; a write only for
a record that needs it) puts Kiln's fields back after a HelixScreen
write. Before, the last write of a record won.

With AFC (AFC-Klipper-Add-On, the afc-kiln plugin) the namespace is AFC's:
when `printer.objects.list` has `AFC` at Klipper ready (exact name, AFC's
`[AFC]` section), Kiln writes nothing, stops its check and deletes the
`lane1`..`lane4` records it wrote alone (no `writer`, none but the fields
above); a record HelixScreen signed or with AFC's own fields stays. AFC
writes one record per AFC lane (afc-kiln: `T0`..`T3`). Checked at every
Klipper ready, so installing or removing AFC takes effect at the next
Klipper restart. Since v1.0.1 (issue #101).

Kiln also writes Fluidd's own namespace `fluidd` once (key `macros`: macro
categories, internal macros hidden), only while Fluidd has no macro
settings yet, and the same hidden macros into Mainsail's namespace
`mainsail` (key `macros`: `mode` `simple`, `hiddenMacros`, no groups),
only while Mainsail has none (since v1.0.1).

## Warnings and notifications

### Moonraker warnings

| Warning ID | Text starts with | When | Since |
|---|---|---|---|
| `kiln_os_kernel` | `Running the stock kernel: Kiln's kernel failed to start ...` | The printer fell back to the stock kernel | v0.0.50 |
| `kiln_os_kernel` | `Running the 6.6 kernel: the mainline <release> kernel you turned on failed to start ...` | The opt-in 7.3 kernel fell back to 6.6 | v0.0.60 |
| (none) | `[kiln_os]: needs [update_manager]; Kiln OS updates off` | Configuration error | v0.0.1 |

Clients see the text in `/server/info` → `warnings` (a list of strings;
Moonraker doesn't send the ID). Fluidd and Kiln's touch screen show them.
The kernel warning is set when Moonraker starts and removed by a
successful `kernel_retry`.

### Announcement "Extended memory available"

On a printer with 512 MiB that starts in standard mode and hasn't seen
the notice (`notice_pending`), Kiln adds a Moonraker announcement
(`/server/announcements/list`, feed `kiln_os`, priority `normal`, title
`Extended memory available`, the notice text as its description). Fluidd
and Mainsail show it. Dismissing it there (`/server/announcements/dismiss`
without `wake_time`) marks the notice seen, as
`POST /machine/kiln_os/memory_notice_seen` does; a dismiss with a
`wake_time` (snooze) doesn't. Kiln removes the announcement once the
notice is seen or no longer applies (Extended memory switched on). Its
`entry_id` changes each time it is added: find it by feed and title.
Since v1.0.0.

### G-code output (`notify_gcode_response`)

Lines Kiln sends that a client may act on:

| Line | Meaning | Since |
|---|---|---|
| `// action:ad5x_setup_wizard` | Someone asked for the setup wizard (`SETUP_WIZARD`); the touch screen opens it | v0.0.1 |
| `!! Upload <file>: print not started: <reason>` | An upload's print didn't start (see `print_error`) | v0.0.45 |
| `// Extended memory: on\|off (this start: standard\|extended)`, `// Extended memory: not available (...)`, `// Needs a boot loader update to take effect: ...`, `!! KILN_MEMORY_MODE: [reason] ...` | `KILN_MEMORY_MODE`'s answer (Moonraker sends it, so only clients see it, not `klippy.log`) | v1.0.0 |
| `// Web interface on port 80: Fluidd\|Mainsail ...`, `// The mainsail-kiln plugin serves both ...`, `!! KILN_WEBUI: [reason] ...` | `KILN_WEBUI`'s answer (Moonraker sends it) | v1.0.1 |
| `!! This printer now uses Fluidd\|Mainsail: reload the page` | Sent only to a connection of the web interface that isn't chosen, just before it is closed | v1.0.1 |
| `// IFS: ...`, `// Bed heat soak: ...`, ... | Information for people; not an API | |

Kiln adds no websocket notification methods of its own; status changes
come through upstream's `notify_status_update` for the objects below.

## Klipper status objects

Subscribe or query them with upstream's `printer.objects.subscribe` /
`/printer/objects/query`:

```sh
curl 'http://PRINTER/printer/objects/query?ifs=channel,loaded_channels,activity&ifs_materials'
```

Types are JSON types. "Slot" and "channel" both mean an IFS lane, 1-4;
0 means none.

### ifs

The IFS (4-slot filament unit). Absent when a plugin drives the IFS
(`printer.ad5x_plugins.ifs_owner`). Since v0.0.1 unless noted.

| Field | Type | |
|---|---|---|
| `connected` | bool | The IFS answers (serial link open, or Klipper IFS firmware) |
| `mode` | string | `serial` (stock IFS firmware) or `mcu` (Kiln's Klipper IFS firmware). Since v0.0.44 |
| `version` | string | IFS firmware version |
| `busy` | bool | An IFS operation runs |
| `channel` | int | Slot loaded in the toolhead, 0 none |
| `loaded_source` | string | How Kiln knows `channel`: `kiln` (a load or swap of Kiln's own; also a channel saved before this field), `user` (named: `IFS_SET_CHANNEL CHANNEL=n`, `IFS_FIND_HEAD_SLOT SLOT=n`), `adopted` (only a guess at startup: no slot saved, the toolhead sensor saw filament and the IFS pointed at that slot, e.g. a lane loaded under zMod, issue #13); "" with `channel` 0. Saved (`ifs_loaded_source`), kept across restarts. An `adopted` slot isn't trusted: a swap or print start to it loads it again, its first unload must clear the toolhead sensor (else nothing is recorded as loaded and the error says why), `IFS_FIND_HEAD_SLOT` finds the slot instead of answering "known", and the setup wizard treats it as unknown. Since v1.0.0 |
| `state` | int or null | The IFS controller's raw state byte (5 = ready); diagnostic |
| `selected` | int or null | Slot the selector points at |
| `inserted` | list of 4 bool | A spool was inserted in that slot and not yet fed up (stock behaviour) |
| `silk` | list of 4 int | Raw per-slot filament sensor value; diagnostic, meaning differs by `mode` |
| `stall` | list of 4 int | Raw per-slot buffer/stall value; diagnostic |
| `colors` | list of 4 (string or null) | Slot colours `#RRGGBB` |
| `channel_count` | int | 4 |
| `active_channel` | int or null | Same as `selected` |
| `loaded_channels` | list of int | Slots with filament at the IFS |
| `pending_insert_channels` | list of int | Slots from `inserted` |
| `activity` | string | What the unit does: `ready`, `selecting`, `polling`, `homing`, `loading`, `unloading`, `clamped`, `unclamping`, `driver_error`, `unknown(<n>)`, or null |
| `activity_channel` | int or null | Slot of `activity`, 0 whole unit |
| `operation` | string | The running operation: `load`, `unload`, `swap`, `eject`, `prefeed`, `refill`, `tune`, `select`, `feed`, `retract`; "" idle. Since v0.0.44 |
| `phase` | string | Its step: `heating`, `cutting`, `unloading`, `homing` (the IFS selector), `selecting`, `feeding`, `purging`, `priming`; `homing_printer` (G28 before the operation, `HOME=1`; since v1.0.0); "" idle. Since v0.0.44 |
| `target_channel` | int | Slot the operation works on, 0 none. Since v0.0.44 |
| `error` | string or null | The last failure, null none |
| `error_channel` | int | Slot of that failure, 0 none or unknown. Since v0.0.44 |
| `auto_refill` | bool | Auto-refill on (`IFS_AUTO_REFILL`). Since v0.0.5 |
| `refill` | string | Last auto-refill message, "" none. Since v0.0.5 |
| `refill_match` | string | `exact`, `similar`, `any`. Since v0.0.11 |
| `refill_backups` | object | `"1"`-`"4"` → list of slots that would take over, nearest colour first. Since v0.0.11 |
| `refill_notice` | string | A print loaded a slot with no backup; "" otherwise. Since v0.0.11 |
| `map_mode` | string | `fixed` (T0-T3 → slots 1-4) or `loaded` (tools use the slots with filament). Since v0.0.23 |
| `tool_map` | object | `"0"`-`"3"` → slot for each slicer tool |
| `find_result` | string | The last `IFS_FIND_HEAD_SLOT`: `found`, `pick` (the extruder alone clears the sensor: name the slot), `tube` (a strand stayed in the tube above the sensor: `tube_blocked`), `none` (no slot cleared the sensor), `error`; "" none yet, or refused before anything moved. Each find starts it again. Since v1.0.0 |
| `head_found` | int | Its slot, 0 none. Since v1.0.0 |
| `tube_blocked` | bool | A strand of an unknown slot sits in the tube above the toolhead sensor (the find's `tube` result, a find that failed or was stopped after the strand had left the sensor, or an unload (`IFS_UNLOAD`, a swap's first half) that failed or was stopped after the strand had left the sensor: nothing is recorded as loaded then, and the error names the slot; saved, kept across restarts): loads, unloads (`IFS_UNLOAD`), `IFS_SET_CHANNEL CHANNEL=n`, tuning and pre-feeds are refused until `IFS_FIND_HEAD_SLOT SLOT=n` pulls lane n back out of the tube or `IFS_SET_CHANNEL CHANNEL=0` says it was pulled out by hand. Since v1.0.0 |
| `tune` | object | Swap tuning: `speed`, `load_dist` (`"1"`-`"4"` → mm), `unload_dist`, `tube_unload`, `flush` (since v0.0.44): number or null (null = the `[ifs]` default); `running` (bool), `progress` (0-1), `message` (string) while `IFS_TUNE` runs |

### ifs_materials

What is in each slot. Since v0.0.1.

| Field | Type | |
|---|---|---|
| `available` | bool | Always true |
| `channel_count` | int | 4 |
| `slots` | object | `"1"`-`"4"` → `{"type": string or null, "color": "#RRGGBB" or null, "temp": number or null, "spool_id": int or null, "vendor": string or null, "name": string or null, "filament_id": string or null, "bed_temp": int or null}`; `temp` is the slot's own temperature or the material's default; the last five are the spool's details as `IFS_SET_MATERIAL` set them (since v1.0.1, plugin API 1.12) |
| `loaded` | object or null | The loaded slot's entry, null none |
| `temperatures` | object | Material → handling temperature (`PLA` 220, `PETG` 250, ...) |

### ad5x_setup

The setup wizard steps (see `/printer/ad5x_setup/control`). Since v0.0.1.

| Field | Type | |
|---|---|---|
| `step` | string | Current or last step, "" none |
| `state` | string | `idle`, `running`, `waiting_user`, `done`, `failed`, `aborted` |
| `message` | string | One line for people |
| `progress` | number | 0-1, best effort |
| `results` | object | Step → short result text (`selfcheck`, `pid`, `mesh`, `shaper`, `ifs`, `trash`, `zoffset`, `estimate`, `soak`, `summary`, `finish`); kept across restarts |
| `checks` | list | Self-check items `{"name", "ok", "detail", "required"}` |
| `pending_save` | bool | Results waiting for the `finish` step |
| `zoffset` | number | The live Z offset during the `zoffset` step, else the saved print Z offset |
| `estimate` | bool | `ESTIMATE=1` is available on the Z offset step. Since v0.0.17 |
| `action` | string | What the step does now, a short key (`homing`, `heating`, `cleaning`, `probing`, `printing_patch`, `finding_slot`, `unloading`, `loading`, `tuning_ifs`, `waiting`, ...; `docs/setup-wizard.md`); "" when no step runs. Since v1.0.0 |
| `action_arg` | int | The slot (`loading`, `unloading`) or patch number (`printing_patch`) of `action`, 0 none. Since v1.0.0 |
| `step_started` | number | Unix time (s, the printer's clock) the current or last step started, 0 none. Since v1.0.0 |
| `prompt` | string or null | What the step asks of you: `clear_bed` (`waiting_user`: take the test print off the bed, then `accept`; also left after a Z offset step that failed or was aborted with a patch on the bed, `accept` clears it), `head_unknown` (`failed`: pull the filament out of the toolhead by hand, then start the step again), `pick_slot` (`failed`: Kiln can't find which slot is in the toolhead, or a strand of an unknown slot sits in the tube: name the slot, `filament` with `head=<n>`, or pull it out by hand and send `head=0`). Since v1.0.0 |
| `filament` | object or null | `present` (slots with filament at the IFS), `materials` (`"1"`-`"4"` → type or null), `head` (slot in the toolhead, 0 none or unknown), `head_source` (`loaded`, `user`, `found`, `unknown`, `kept`, `tube`, `empty`), `head_filament` (the toolhead sensor sees filament; null unknown); null without Kiln's IFS module. Since v1.0.0 |
| `zoffset_plan` | object or null | The Z offset step's test patch: `slot`, `material`, `nozzle`, `bed` (°C), `guess` (true: no material known, PLA's temperatures), `source` (`param`, `slot`, `guess`); set before anything heats (before a find of the toolhead's slot with `slot` 0, then again with the slot it found), null before the step ran. Since v1.0.0 |

### ad5x_soak

The bed heat soak. Since v0.0.7.

| Field | Type | |
|---|---|---|
| `enabled` | bool | The soak runs at each print start (`BED_SOAK_ENABLE`). Since v0.0.8 |
| `calibration` | object | Bed temperature (`"60"`) → `{"settle", "settle_corners"` (s), `"drift"`, `"warp"` (mm), `"points"`, `"from"` (start temperature), `"stable"` (bool), `"date"}` |
| `running` | bool | A calibration runs |
| `soak` | number | Seconds of soak this print start decided, 0 none |
| `last` | list | The running or last calibration's readings, `[seconds, z...]` per round |
| `cancel` | bool | A cancel arrived during the print start and `CANCEL_PRINT` hasn't run yet. Since v0.0.60 |

### ad5x_plugins

Plugins. Since v0.0.1.

| Field | Type | |
|---|---|---|
| `api_version` | string | The plugin API version (same as `api_version` in `/machine/kiln_os/info`) |
| `enabled` | list of strings | Plugins listed in `plugins.cfg` at this Klipper start (a skipped one is listed and named in `warnings`) |
| `available` | object | Name → `{"source": "shipped" or "user", "description", "version", "author", "url", "requires_os"` (strings), `"compatible"` (bool), `"owns_ifs"` (bool, since v0.0.49), `"root"` (bool: it has root scripts), `"root_installed"` (bool: root has its copy of them; both since v0.1.0-rc1)`}` |
| `ifs_owner` | string | The plugin that drives the IFS at this start, "" Kiln's own. Since v0.0.49 |
| `catalog` | object | Installable plugins: name → `{"title", "description", "url", "requires_os", "compatible", "installed"}`. Since v0.0.7 |
| `job` | object | Install/update/remove in progress: `{"name", "action", "state"` (`idle`, `running`, `done`, `failed`), `"message"}`; `action` is also `root install`, `root update` or `root uninstall` while a plugin's root script runs (since v0.1.0-rc1). Since v0.0.7 |
| `warnings` | list of strings | Plugins skipped at this start and why |

### Other objects

| Object | Fields | Since |
|---|---|---|
| `ad5x_config` | `notices` (list of strings: macro files an update replaced), `backups` (list of strings: `macros/*.bak-*` files) | v0.0.1 |
| `ad5x_log` | `mode` (`short` or `extended`), `until` (Unix time the extended mode ends, or null) | v0.0.53 |
| `ad5x_nozzle` | `size` (number, running nozzle mm), `saved` (number or null, `nozzle.cfg`), `local` (bool, `local.cfg` sets it), `sizes` (list of allowed sizes) | v0.0.10 |
| `ad5x_resume` | `available` (bool: a print a power cut ended can continue), `file` (string), `z` (number, mm), `time` (number, Unix time) | v0.0.5 |
| `ad5x_sound` | `speaker` (bool), `enabled` (bool), `volume` (0-100), `events` (event → file, "" off; events `startup`, `start`, `complete`, `error`, `cancelled`, `paused`, `refill`), `files` (list), `playing` (bool) | v0.0.7 |
| `ad5x_weight` | `connected` (bool), `weight` (number: last raw bed strain-gauge reading) | v0.0.1 |
| `ad5x_zestimate` | Empty until `Z_OFFSET_ESTIMATE` ran; then `estimate`, `press_in` (mm), `stiffness` (g/mm), `r2`, `points`, `trigger_force` (g or null), `saved` (mm or null), `drift` (g), `first_touch` | v0.0.17 |

Macro variables clients read (`printer["gcode_macro PRINT_START"]`,
`_PRIME_LINE`, `_AD5X_UNIT`, `_PURGE_BOX_POS`) are listed in
`docs/plugin-api.md`, "Printer objects and status fields".

## G-code commands

Send them with upstream's `/printer/gcode/script?script=...`
(`printer.gcode.script`). Commands starting with `_` are internal: they
are not API and may change in any release. Commands from plugins
(`START_PRINT` of zmod-compat, ...) are documented with the plugin
(`docs/zmod-compat.md`). Parameters in detail: `docs/plugin-api.md`.

### Print

| Command | Parameters | | Since |
|---|---|---|---|
| `PRINT_START` | `BED=` `EXTRUDER=` `TOOL=` (first slicer tool, -1 none) `LEVEL=0\|1` `ADAPTIVE=0\|1` `SOAK=s` | Home, heat, soak, purge, brush, mesh or Z check, first tool or prime line | v0.0.1 |
| `PRINT_END` | | Retract, lift, park, heaters, fans and motors off | v0.0.1 |
| `CANCEL_PRINT`, `PAUSE`, `RESUME` | upstream's | Wrapped: park, heaters; `PAUSE`/`RESUME` since v0.0.34 | v0.0.1 |
| `M106`, `M107` | `S` 0-255 | Part fan (`fan_generic fanM106`) | v0.0.1 |
| `M900` | `K` `[E=extruder]` | Pressure advance, Marlin style | v0.0.1 |
| `SET_GCODE_OFFSET` | upstream's | Wrapped: `Z`/`Z_ADJUST` are also saved as the print Z offset | v0.0.1 |
| `BED_MESH_CALIBRATE` | upstream's; `FORCE=1` | Wrapped: tares the strain gauges first; during a print, skipped after `PRINT_START`'s mesh (or another mesh of that print) unless `FORCE=1`, `PROFILE=` or `ADAPTIVE=0` (issue #73) | v0.0.1 |
| `SAVE_CONFIG` | upstream's | Wrapped: PID/shaper results go to `ad5x-tuning.cfg` | v0.0.14 |
| `HEATER_IDLE_TIMEOUT` | `[MINUTES=]` | Show or set when idle heaters go off | v0.0.34 |
| `TRASH_OFFSET` | `X=` `Y=` or `RESET=1` | Move the purge box spot | v0.0.17 |
| `BED_SOAK_CALIBRATE` | `BED=` `[POINTS=]` ... | Measure the bed's settling (abort: `/printer/ad5x_soak/abort`) | v0.0.7 |
| `BED_SOAK_ENABLE` | `[ENABLE=0\|1]` | Soak on/off for every print | v0.0.8 |
| `RESUME_INTERRUPTED`, `CLEAR_INTERRUPTED` | `CONFIRM=1` | Continue / forget a print a power cut ended; resuming is refused while `printer.ifs.tube_blocked` | v0.0.5 |
| `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `CLEAR_NOZZLE`, `AUTO_FULL_BED_LEVEL` | | Quick actions | v0.0.1 |
| `BED_LEVEL_SCREWS_TUNE`, `SCREWS_TILT_CALCULATE` | `BED_TEMP=` `EXTRUDER_TEMP=` `DIRECTION=CW\|CCW` / upstream's | Bed screw levelling (zMod's name): heat, home, probe at each screw, show the turns; `SCREWS_TILT_CALCULATE` alone tares over the first screw, makes one uncounted touch there, and doesn't heat (issue #69) | (v1.0.0) |
| `WEIGHT_TARE`, `LOAD_CELL_TARE` | | Zero the bed strain gauges | v0.0.1 |
| `Z_OFFSET_ESTIMATE` | `[X= Y=] [SAVE=1]` | Z offset from the load cells (`printer.ad5x_zestimate`) | v0.0.17 |
| `SET_NOZZLE_SIZE` | `SIZE=` `[RESTART=0]` | Nozzle size; Klipper restarts | v0.0.10 |
| `GET_FILAMENT_VALUE`, `GET_CUT_VALUE` | | Raw toolhead/cutter sensor values (stock names) | v0.0.1 |

### IFS

| Command | Parameters | | Since |
|---|---|---|---|
| `T0`-`T3` | | Load the slot the tool map names | v0.0.1 |
| `IFS_LOAD` | `SLOT=` `[TEMP=]` `[HOME=1]` | Load a slot (unloads the current one first). Not homed: refused ("home the printer first (G28)"); with `HOME=1` an idle printer homes first, never during a print or a pause (`HOME=1` since v1.0.0; the touch screen sends it) | v0.0.1 |
| `IFS_UNLOAD` | `[SLOT=]` `[TEMP=]` `[HOME=1]` | Cut and unload the nozzle; refused while `tube_blocked`. Failing after the strand left the toolhead sensor: nothing recorded as loaded, `tube_blocked` set. `HOME=1` as `IFS_LOAD` (`UNLOAD_FILAMENT` sends it) | v0.0.1 |
| `IFS_FIND_HEAD_SLOT` | `[TEMP=]` `[SLOT=]` `[HOME=1]` | Filament in the toolhead from a slot Kiln doesn't know (or only adopted at startup, `loaded_source` `adopted`: that slot tried first): find the slot (cut, the extruder alone, then short pulls of each slot) and unload it; `SLOT=` names it | (v1.0.0) |
| `IFS_SWAP` | `CHANNEL=` `[TEMP=] [FLUSH=] [ROUNDS=] [PURGE=0\|1] [HOME=1]` | Colour change with purge (`HOME=1` as `IFS_LOAD`). To the slot already loaded: nothing to do, unless it was only adopted at startup (`loaded_source` `adopted`): then it is loaded again (v1.0.0) | v0.0.1 |
| `IFS_EJECT` | `SLOT=` `[HOME=1]` | Pull a slot's filament out of the IFS (the loaded slot: unloads the nozzle first; `HOME=1` as `IFS_LOAD`) | v0.0.1 |
| `IFS_PREFEED` | `CHANNEL=` | Feed a new spool up to the IFS | v0.0.1 |
| `IFS_STOP` | | Stop the IFS | v0.0.1 |
| `IFS_STATUS`, `IFS_MATERIALS` | | Report | v0.0.1 |
| `IFS_SET_MATERIAL` | `SLOT=` `[TYPE=] [COLOR=] [TEMP=]` (absent = keep, empty = clear); since v1.0.1 (plugin API 1.12) also the spool's `[SPOOL_ID=] [VENDOR=] [NAME=] [FILAMENT_ID=] [BED_TEMP=]` (`printer.ifs_materials`, `lane_data`): a `TYPE=` other than the slot's type clears the spool's details except those given in the same command (the same `TYPE=`, `COLOR=` and `TEMP=` keep them); `SPOOL_ID` a whole number from 1 (no leading zeros), `BED_TEMP` 0-130, texts up to 64 characters without `"` `'` `\` `;` `%`, in double quotes when they hold spaces or `#` (`NAME="Silk Red"`; unquoted, a space gives "Malformed command" and `#` cuts the line). Releases before plugin API 1.12 ignore these next to `TYPE=`/`COLOR=`/`TEMP=`: check `printer.ad5x_plugins.api_version` | Slot material | v0.0.1 |
| `IFS_SET_COLOR` | `CHANNEL=` `COLOR=` | Slot colour | v0.0.1 |
| `IFS_SET_CHANNEL` | `CHANNEL=` (0 none) | Tell Kiln which slot is loaded; while `tube_blocked` only `CHANNEL=0` (the strand pulled out by hand), which lifts it | v0.0.1 |
| `IFS_MAP_TOOL` | `TOOL=` `SLOT=` or `RESET=1` | Tool map for this print | v0.0.1 |
| `IFS_MAP_MODE` | `[MODE=fixed\|loaded]` `[ZMOD=1]` | Tool map mode | v0.0.23 |
| `IFS_AUTO_REFILL` | `[ENABLE=0\|1] [MATCH=exact\|similar\|any]` | Auto-refill | v0.0.5 |
| `IFS_LED` | `[ENABLE=0\|1] [SLEEP=0\|1]` | The IFS's status light on Klipper firmware: `ENABLE` (kept), `SLEEP` (the screen sleeps: off while idle and no print runs; not kept); shows both without parameters (`docs/mcu-flashing.md`, "Status light") | v1.0.2 |
| `IFS_RESET_DRIVER` | | Recover after a fault | v0.0.1 |
| `IFS_TUNE`, `IFS_TUNE_SPEED`, `IFS_TUNE_LOAD`, `IFS_TUNE_UNLOAD`, `IFS_TUNE_RESET` | `[CHANNEL=]` ... | Swap tuning | v0.0.1 |
| `IFS_PURGE_TEST`, `IFS_PURGE_RESULT`, `IFS_SET_FLUSH` | | Purge tuning | v0.0.1 |

Service commands, not API (raw moves and board access, may change):
`IFS_SEND`, `IFS_SELECT`, `IFS_FEED`, `IFS_RETRACT`, `IFS_RELEASE`,
`IFS_RESET`, `IFS_SET_CURRENT`, `WEIGHT_READ`, `WEIGHT_SEND`.
`BED_SOAK_START` and `BED_SOAK_WAIT` are steps of `PRINT_START`, not for
clients.

### Setup, plugins, system

| Command | Parameters | | Since |
|---|---|---|---|
| `SETUP_WIZARD_STEP` | `STEP=` `[ACTION=start\|abort\|adjust\|accept\|wizard] [DELTA=] [WAIT=1]` + step options | As `/printer/ad5x_setup/control` | v0.0.1 |
| `SETUP_WIZARD` | | Run the wizard again on the touch screen | v0.0.1 |
| `ENABLE_PLUGIN`, `DISABLE_PLUGIN` | `NAME=` `[RESTART=0]`; `ENABLE_PLUGIN` `ROOT=1` (v0.1.0-rc1) for a plugin with root scripts | Klipper restarts | v0.0.1 |
| `LIST_PLUGINS` | | | v0.0.1 |
| `INSTALL_PLUGIN` | `NAME=` `[ENABLE=1]` `[ROOT=1]` (v0.1.0-rc1) | From the catalog (`printer.ad5x_plugins.job`) | v0.0.7 |
| `UPDATE_PLUGIN`, `REMOVE_PLUGIN` | `NAME=` | | v0.0.7 |
| `CONFIG_BACKUPS` | `[ACK=1]` | Macro files an update replaced | v0.0.1 |
| `LOG_MODE` | `[MODE=short\|extended] [HOURS=]` | How much `klippy.log` keeps | v0.0.53 |
| `M300`, `PLAY_MIDI`, `PLAY_SOUND`, `SOUND_STOP`, `SOUND_SETUP` | | Speaker | v0.0.7 |
| `KILN_MEMORY_MODE` | `[ENABLE=0\|1]` | Extended memory from the next start, as `POST /machine/kiln_os/memory`; without `ENABLE` the mode. A macro (macros/ `system.cfg`) calling Moonraker's remote method `kiln_memory_mode`; the answer comes in the console | v1.0.0 |
| `KILN_WEBUI` | `[NAME=fluidd\|mainsail]` | The web interface on port 80, as `POST /machine/kiln_os/webui`; without `NAME` which one. A macro (macros/ `system.cfg`) calling Moonraker's remote method `kiln_webui`; the answer comes in the console | v1.0.1 |

`PLUGINS_LIST`, `PLUGIN_ENABLE`, `PLUGIN_DISABLE`, `IFS_TUNE_RUN`,
`IFS_TUNE_CLEAR`, `IFS_INFO` and `CONFIG_BACKUPS_SHOW` are buttons for
Fluidd's macro panel that call the commands above; use the commands.
`ENABLE_PLUGIN ... ROOT=1` and `INSTALL_PLUGIN ... ROOT=1` (plugin API
1.6) are the owner's yes to a plugin's root scripts
(`docs/plugin-root-hooks.md`); a client that switches plugins passes
`ROOT=1` only after the owner agreed.

## Known quirks

Upstream behaviour that Kiln keeps:

- **Klipper endpoints** (`/printer/ad5x_*`) accept GET and POST alike (as
  every Klipper endpoint in Moonraker), answer 404 until Klipper has
  connected once since Moonraker started, and 503 while Klipper is
  disconnected. Their errors are always 400, without `data`: Moonraker
  answers every Klipper error that way, so the reason is only in the
  message (see [Errors](#errors)).
- **Moonraker's own errors** have no reason: a missing parameter on its
  side, an unknown endpoint, an update that is already running.
- **`lane_data` keys** follow AFC's shape: `lane` is a string, and `lane1`
  is tool `"0"`.
