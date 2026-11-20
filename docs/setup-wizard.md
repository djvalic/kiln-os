# First-boot setup wizard (design + contract)

Goal: like the stock printer, a fresh install walks you through tuning on
the touch screen. It also runs again on demand ("Run setup wizard" in
HelixScreen settings, or the `SETUP_WIZARD` macro).

User decisions (2026-10-16): steps = self-check, PID, bed mesh, vibration
(input shaper), IFS tuning for quick swaps (QuickSwap-like), Z offset by a
first-layer test with live +/- on screen. Runs at first boot and on demand,
never forced after an update.

## Flow on the screen

HelixScreen's own wizard, with the preset collapsing the hardware pickers
(seeded settings: `preset: ad5x`, `wizard_completed: false` on a fresh
install). Our AD5X steps are added by a HelixScreen patch:

| # | Step | Source |
|---|------|--------|
| 1 | Touch calibration (skipped if already valid) | HelixScreen |
| 2 | Language | HelixScreen |
| 3 | Wi-Fi (optional) | HelixScreen |
| 4 | Connection (auto, local Moonraker) | HelixScreen |
| 5 | **Self-check** | AD5X step, `STEP=selfcheck` |
| 6 | **PID tune** (nozzle 220, bed 60) | AD5X step, `STEP=pid` |
| 7 | **Bed mesh** (bed at 60; cleans the nozzle on the bed edge first) | AD5X step, `STEP=mesh` |
| 8 | **Vibration compensation** | AD5X step, `STEP=shaper` |
| 9 | **Filament** (the material in each slot; which slot is in the toolhead, found by itself when Kiln doesn't know) | AD5X step, `STEP=filament` |
| 10 | **IFS tuning** (load filament in slots first) | AD5X step, `STEP=ifs` |
| 11 | **Purge box check** (is the nozzle over the trash bin? `TRASH_OFFSET X= Y=` moves it) | AD5X step, `STEP=trash` |
| 12 | **Z offset: first layer** (test patch; optional load cell estimate first, `ESTIMATE=1`, when `zoffset_estimate: 1`; then "remove the test print") | AD5X step, `STEP=zoffset` (+ live adjust) |
| 13 | **Bed soak calibration** (optional, about 15 min; starts from a cold bed) | AD5X step, `STEP=soak` |
| 14 | **Summary** (the results, before Save) | AD5X step, `STEP=summary` |
| 15 | **Save** (SAVE_CONFIG, Klipper restarts) | AD5X step, `STEP=finish` |
| 16 | Preferences | HelixScreen (telemetry stays off) |

Every AD5X step has Start, Skip and (while running) Abort. A failed step
shows the message and offers Retry / Skip.

## Klipper contract (`klipper/setup.cfg` + `klipper/extras/ad5x_setup.py`)

**Changed from the first draft (2026-10-16, Klipper side). The screen side
must follow:**

1. The G-code command is **`SETUP_WIZARD_STEP`**, not `AD5X_SETUP`.
   Klipper splits a command name at a digit followed by letters, so
   `AD5X_SETUP STEP=pid` arrives as command `AD5` ("Unknown command").
   ad5x.cfg already warns about this for macros, and a Klipper batch run
   showed it. Status object, config section and API endpoint keep the
   `ad5x_setup` name, which is fine there.
2. `ACTION=start` returns at once, and the step runs in the background.
   Follow `state`.
3. The same actions are a Klipper API endpoint, `ad5x_setup/control`.
   During a long calibration command it is the only way to abort.
4. The SETUP_WIZARD flag is
   `/data/ad5x/printer_data/comms/run-setup-wizard`. The klipper user
   can't create files in `/data/ad5x`; only `printer_data` belongs to it.
   S70helixscreen's `HELIX_WIZARD_FLAG_FILE` must point there.
5. PID and input-shaper results go to `ad5x-tuning.cfg`, because
   `SAVE_CONFIG` refuses them.

Status field names are unchanged. Check items have one extra key,
`required`.

Command: `SETUP_WIZARD_STEP STEP=<name> [ACTION=start|abort|adjust|accept]
[DELTA=<mm>] [WAIT=1] [step options]`

API endpoint (works at any time, even while the G-code lock is held):
Moonraker JSON-RPC `printer.ad5x_setup.control` or HTTP
`POST /printer/ad5x_setup/control`, with params `step`, `action`, `delta`
and the step options in lower case (`material`, `extruder`, `bed`,
`keep_bed`, `tube`, `channel`, `heaters`, `estimate`, `force`, `head`,
`material_1` ... `material_4`). Reply: `{"state", "step", "message"}`;
errors come back as a normal Klipper error (400 through Moonraker), the
message starting with a reason, e.g. `[step_running] SETUP_WIZARD_STEP:
step 'pid' is still running (ACTION=abort first)` (`docs/api.md`,
"Errors"; the G-code command's message has no reason). **The screen should send
abort this way, and preferably adjust and accept too.**

- `ACTION=start` (default) starts the step and returns at once. The step
  runs in the background (like a virtual_sdcard print) and takes
  Klipper's G-code lock only for each command it sends. Follow `state`
  in the status object. While a step is `running` or `waiting_user`,
  starting another is refused. `ACTION=start` with `STEP=zoffset` while
  the patch waits prints another patch beside it. `WAIT=1` runs the step
  inside the command (for the console and macros); then only the API
  endpoint can abort, adjust or accept.
- `ACTION=abort` switches the heaters off at once. From the API this
  works even in the middle of `PID_CALIBRATE`, `M109` or `M190`: the
  heater controls are held off, which also ends those waits. It also
  tells the IFS to stop. The step then ends after the command in
  progress. Klipper can't cut short homing, probing
  (`BED_MESH_CALIBRATE`) or `SHAPER_CALIBRATE`, so an abort there waits
  for that command to finish; the heaters are already off. After that:
  `TURN_OFF_HEATERS` and part fan off. The Z offset step also runs
  `_PARK_END` and `M84 X Y E` and puts the saved Z offset back. It does
  not use `CANCEL_PRINT`, since there is no virtual_sdcard print to
  cancel. Sent as G-code, abort waits until the command in progress
  releases the lock (between patch lines that is immediate).
- `ACTION=adjust DELTA=-0.02` (Z offset step, `waiting_user` only): queued
  and applied by the step between patch lines as
  `SET_GCODE_OFFSET Z_ADJUST=<d> MOVE=1`. At most `max_adjust` (0.5 mm)
  per call, and at most `max_total_adjust` (1 mm) away from the starting
  offset in all.
- `ACTION=accept` (Z offset and purge box steps, `waiting_user` only):
  keep the current offset (or box) and go on. After the Z offset is
  saved, the step waits once more with `prompt` `clear_bed`; the next
  accept (the test print is off the bed) finishes it.
- `ACTION=wizard` (no STEP): what `SETUP_WIZARD` does, see below.

Status object `ad5x_setup` (Moonraker `printer.objects.subscribe`):

| field | type | meaning |
|-------|------|---------|
| `step` | str | current/last step name, "" when none ran |
| `state` | str | `idle`, `running`, `waiting_user`, `done`, `failed`, `aborted` |
| `message` | str | one human line for the screen ("Heating: bed 45/60 C, nozzle 120/140 C") |
| `progress` | float | 0.0–1.0, best effort (PID: from the tuning cycles; IFS: from the IFS module) |
| `results` | dict | per step: short result strings, e.g. `{"pid": "nozzle Kp=… Ki=… Kd=…, bed Kp=…", "shaper": "X mzv 58.2 Hz, Y ei 47.0 Hz"}`; keys `selfcheck`, `pid`, `mesh`, `shaper`, `ifs`, `trash`, `soak`, `zoffset`, `estimate`, `summary`, `finish`. Kept in `variables.cfg` (`ad5x_setup`), so they survive restarts |
| `checks` | list | self-check items `[{"name": "...", "ok": true, "detail": "...", "required": true}]` |
| `pending_save` | bool | results waiting for `STEP=finish` |
| `zoffset` | float | live G-code Z offset during the Z offset step, else the saved print Z offset (`zoffset.z` in variables.cfg) |
| `estimate` | bool | `ESTIMATE=1` is available on the Z offset step (`zoffset_estimate`) |
| `action` | str | what the step does now, a short key (below); "" when no step runs |
| `action_arg` | int | the slot (`loading`, `unloading`) or patch number (`printing_patch`) of `action`; 0 none |
| `step_started` | float | Unix time (seconds, the printer's clock) the current or last step started; 0 none. Elapsed = now - `step_started` (the screen runs on the printer, same clock) |
| `prompt` | str or null | what the step asks of the user (below); null none |
| `filament` | dict or null | `present` (list of slots with filament at the IFS), `materials` (`"1"`-`"4"` → type or null, as `ifs_materials`), `head` (the slot in the toolhead, 0 none or unknown), `head_source`, `head_filament` (the toolhead sensor sees filament; null unknown). Live, also before the filament step runs. null without Kiln's IFS module (none, or a plugin drives it) |
| `zoffset_plan` | dict or null | the Z offset step's patch: `slot` (0 none), `material`, `nozzle`, `bed` (°C), `guess` (true: no material known for the slot, PLA's temperatures used), `source` (`param`: `MATERIAL=`; `slot`: the slot's material; `guess`). Set before anything heats: before a find of the toolhead's slot (it heats) with `slot` 0, then again with the slot found; null before the step ran |

`state` is `waiting_user` from the moment the test patch starts printing
until accept or abort. Adjust is accepted that whole time, not during the
`clear_bed` prompt.

`head_source`:

- `loaded`: filament in the toolhead, Kiln's IFS module knows the slot (a
  load of Kiln's own, `IFS_SET_CHANNEL`). A slot the startup check only
  adopted (`printer.ifs.loaded_source` `adopted`: no slot saved, the IFS
  pointing at a lane while the toolhead had filament) is a guess and
  reads `unknown`;
- `user`: the same, the slot given with `HEAD=<n>`;
- `found`: `IFS_FIND_HEAD_SLOT` found this slot in the toolhead and
  unloaded it; the Z offset step loads it again (then `loaded`);
- `unknown`: filament in the toolhead, slot not known (a fresh install
  over stock: the last print's slot);
- `kept`: filament in the toolhead the IFS doesn't feed, used as it is
  (`HEAD=KEEP`, or no slot has filament at the IFS);
- `tube`: a strand of an unknown slot sits in the tube above the toolhead
  sensor (`printer.ifs.tube_blocked`: the find's `tube` result, or a
  find or unload that failed or was aborted after the strand had left
  the sensor); loads and unloads are refused until its slot is named
  (`HEAD=<n>`) or it is pulled out (`HEAD=0`);
- `empty`: no filament in the toolhead.

`prompt`:

- `clear_bed`, state `waiting_user`: the Z offset is saved; the test
  print must come off the bed before the next step probes or prints
  there. Confirmed with `ACTION=accept`; after `user_timeout` (15 min)
  without an answer the step ends anyway, its message saying to remove
  the print (the heaters are off by then). Abort here ends the step as
  `done` (the offset stays). Also set,
  as a reminder, when a Z offset step fails or is aborted after a patch
  started printing; the next start clears it.
- `head_unknown`, state `failed`: the toolhead holds filament and no slot
  with filament cleared the toolhead sensor (`IFS_FIND_HEAD_SLOT`). Pull
  the filament out at the top of the toolhead by hand (cut the tip first
  if it isn't cut), then start the step again (Retry).
- `pick_slot`, state `failed`: Kiln can't find the slot in the toolhead on
  this printer (the extruder alone moves the strand past the toolhead
  sensor, so pulling a slot proves nothing; the strand is put back), or
  a strand of an unknown slot stayed in the tube above the sensor
  (`head_source` `tube`). The user names the slot (its colour): the
  filament step with `HEAD=<n>`; or pulls it out by hand and sends
  `HEAD=0`. Retry without naming asks again; nothing is fed into the
  tube meanwhile.
- `accept` also clears a `clear_bed` left after a failed or aborted Z
  offset step.
- A Z offset step takes two `accept`s now: the first keeps the offset,
  the second says the test print is off the bed.

`action` keys (a screen shows a general "working" text for a key it
doesn't know; new keys may come):

| key | when |
|---|---|
| `checking` | self-check: boards, IFS, accelerometer, gauges, sensor |
| `fan_test`, `heater_test` | self-check: a fan, the heaters |
| `homing` | `G28` (any step) |
| `heating` | a heat wait (mesh, estimate; PRINT_START's heating) |
| `pid_nozzle`, `pid_bed` | `PID_CALIBRATE` |
| `cleaning` | the nozzle scrub on the bed edge (mesh; PRINT_START) |
| `probing` | `BED_MESH_CALIBRATE` (mesh); PRINT_START's Z check |
| `shaper_x`, `shaper_y` | `SHAPER_CALIBRATE` |
| `setting_materials` | filament: `IFS_SET_MATERIAL` |
| `finding_slot` | `IFS_FIND_HEAD_SLOT` (filament, IFS, Z offset steps) |
| `unloading` | filament: `IFS_FIND_HEAD_SLOT SLOT=n` pulls a strand left in the tube back, `action_arg` = slot |
| `tuning_ifs` | `IFS_TUNE` (`message` has its progress) |
| `moving` | purge box check: to the box |
| `loading` | Z offset: `IFS_LOAD`, `action_arg` = slot |
| `estimating` | Z offset: `Z_OFFSET_ESTIMATE` |
| `preparing`, `purging` | Z offset: `PRINT_START` (its status line gives `homing`, `heating`, `purging`, `cleaning`, `probing`, `loading` while it runs) |
| `printing_patch` | Z offset: a test patch, `action_arg` = its number (1, 2, ...) |
| `waiting` | `waiting_user`: the user's turn |
| `saving` | Z offset: saving and `PRINT_END`; finish |
| `cooling`, `soak` | soak: bed cooling below 40 C, the calibration |

Live temperatures are not in this object: the screen reads
`extruder`/`heater_bed` (`temperature`, `target`) itself.

The steps:

- **selfcheck**:
  - MCUs connected (version per board).
  - IFS answers `IFS_STATUS` (required unless `require_ifs: False`).
  - `ACCELEROMETER_QUERY` answers.
  - `WEIGHT_TARE` works (bed strain gauges).
  - The toolhead filament sensor has a reading.
  - Part fan, then board fan, each for `check_time` (10 s), then off.
    There is no tachometer on the AD5X, so the result is "ran 10 s" and
    the check isn't required.
  - Homing (`G28`).
  - Nozzle and bed heat together for 10 s (nozzle target 120, bed 50, or
    higher if already warm), then switch off. The nozzle must rise 3 C
    and the bed 0.5 C, watched for up to 10 s more after switching off
    (the sensors lag).

  The step is `failed` if a required item fails. Heaters and fans are off
  in every case. `[pcb_fan_watch]` keeps the board fan on while motors or
  heaters are on, so it may start again after its test.
- **pid**: home and move the nozzle to the X/Y centre at Z10. With the
  part fan at `pid_fan_speed` (1.0, as when printing PLA), run
  `PID_CALIBRATE HEATER=extruder TARGET=220`. Then fan off and
  `PID_CALIBRATE HEATER=heater_bed TARGET=60`. Results are read from
  Klipper's pending SAVE_CONFIG values.
- **mesh** `[KEEP_BED=1]`: home, then heat the bed to 60 and the nozzle
  to 140 (stock's levelling temperatures; the wait can be aborted). Clean
  the nozzle as a print's Z check does: tare, probe at X60 Y-3, scrub
  along the front edge 0.3 then 0.1 mm above that (plastic on the tip
  makes the probe's samples exceed `samples_tolerance`). Run
  `BED_MESH_CALIBRATE PROFILE=default`, our wrapper: tare, mesh, then a
  centre probe that saves `ad5x_center_z`. The nozzle goes off. The bed
  goes off too unless `KEEP_BED=1`; send that when the Z offset step
  comes next.
- **shaper**: needs Python numpy, **which the image doesn't have yet**.
  Without it the step fails with a message saying so. Otherwise: home,
  `SHAPER_CALIBRATE AXIS=X`, then `AXIS=Y`; results from the pending
  SAVE_CONFIG values.
- **filament** `[MATERIAL_<n>=<type>] [HEAD=<n>|0|KEEP|AUTO]`: the screen
  shows `filament` (live, also before the step) and passes the user's
  choices:
  - `MATERIAL_1` ... `MATERIAL_4`: that slot's material, sent as
    `IFS_SET_MATERIAL SLOT=<n> TYPE=<type>` (the store `ifs_materials`
    and the IFS panel use; "" or `?` clears it). Letters, digits and
    `+_.-`, up to 16; anything else fails the step before anything is
    sent.
  - `HEAD=AUTO` (default): the toolhead empty → nothing (a find
    left open, e.g. pulled out by hand after `none`, is closed:
    `IFS_SET_CHANNEL CHANNEL=0`); filament and a
    slot Kiln knows (it loaded it, or the user named it) → that slot;
    filament from an unknown slot, or from a slot only adopted at
    startup (a guess: 2026-11-19 a stale `ifs_loaded = 1` from before a
    return to stock sent the IFS tuning after slot 1 while slot 2 was in
    the toolhead) → home,
    then `IFS_FIND_HEAD_SLOT` finds it and unloads it (`head_source`
    `found`; the Z offset step loads it again). No slot cleared the
    sensor: `failed`, prompt `head_unknown`. The find can't tell on this
    printer, or the strand stayed in the tube: `failed`, prompt
    `pick_slot`. No slot has filament at the IFS: no find, the filament
    is kept (`head_source` `kept`).
  - `HEAD=<n>`: slot n is in the toolhead (`IFS_SET_CHANNEL`, also when
    slot n was only adopted: the user's word replaces the guess); refused
    when the toolhead sensor sees no filament. With a strand left in the
    tube (`head_source` `tube`): it is slot n's, `IFS_FIND_HEAD_SLOT
    SLOT=<n>` pulls it back out of the tube. `HEAD=0`: empty, also after
    pulling a strand out by hand (`IFS_SET_CHANNEL CHANNEL=0`); refused
    when the sensor sees filament. `HEAD=KEEP`: filament the IFS doesn't
    feed (hand-fed): the Z offset step prints with it as it is, the IFS
    step fails asking to pull it out (`IFS_TUNE` needs the toolhead
    empty).
  - Result: `slots with filament: 1 PLA, 2 PETG, 4 ?; toolhead: slot 2
    (found, unloaded)`.
- **ifs** `[TUBE=1] [CHANNEL=n]`: home; filament in the toolhead from a
  slot Kiln doesn't know (or only adopted at startup) is found and
  unloaded first (`IFS_FIND_HEAD_SLOT`, as in the filament step); a slot
  Kiln loaded or the user named stays for `IFS_TUNE` to measure its
  unload. Then `IFS_TUNE` (see below).
  Progress and message come from the IFS module.
- **zoffset** `[MATERIAL=PLA] [EXTRUDER=] [BED=] [HEAD=KEEP]`:
  - The toolhead is read with the IFS module's sensor, the one
    `IFS_FIND_HEAD_SLOT` uses (the `adc_filament_sensor` only without
    it); no reading: printed with what is there.
  - The slot for the patch: the toolhead's when Kiln knows it (not one
    only adopted at startup). Filament from an unknown slot: found and
    unloaded (`IFS_FIND_HEAD_SLOT`), then
    loaded again the normal way (purged, its material known); not with
    `HEAD=KEEP` (or the filament step's), nor when no slot has filament
    at the IFS: then it prints with the filament as it is, the material
    from `MATERIAL=` or guessed. A strand left in the tube: `failed`,
    prompt `pick_slot`, nothing loads. The
    toolhead empty: loads the slot the filament step found, else the one
    the IFS step cut out, else T0's, else the first with filament;
    refused only when no slot has filament.
  - Temperatures come from `MATERIAL`; the default is that slot's
    material, else PLA (a guess). PLA 220/60, PETG 240/70, ABS/ASA
    250/90, TPU 230/50. `zoffset_plan` says which slot, material and
    temperatures it uses, and whether they are a guess, before anything
    heats (with a find first: `slot` 0 and the material from `MATERIAL=`
    or guessed, then again with the slot found).
  - Runs `PRINT_START BED= EXTRUDER= LEVEL=0`: home, heat, purge, brush,
    then the centre Z check only, with no new mesh and no prime line. The
    patch starts from the same first-layer reference as a print's centre.
  - Starts fresh every run at `patch_start_z` (0.1 mm, a little high),
    not at the saved offset: that may be stock's or zMod's, carried over
    at install and never printed with here, and too low scrapes the bed.
    It is saved for `PRINT_START` (so the prime line uses it too); lower
    it with - until the lines touch and flatten.
  - Prints a 30 x 30 mm single-layer patch at the bed centre, sent line
    by line, with a prime line in front. Layer height is nozzle/2 within
    0.2–0.3 mm, line width 1.125 x nozzle, speed 30 mm/s. Afterwards the
    nozzle goes up 10 mm and parks behind the patch.
  - Later patches go 40 mm left, right, front and back of the centre.
  - On accept: `SET_GCODE_OFFSET Z=<live offset>`, then `PRINT_END`.
    ad5x.cfg's wrapper saves `zoffset` into variables.cfg, minus any
    applied drift.
  - After `user_timeout` (15 min) with no answer, the offset is kept the
    same way.
  - Then the step waits with `prompt` `clear_bed` ("Remove the test
    print from the bed") until `ACTION=accept`, so the soak step's probe
    and the next print don't land on the patch (at most `user_timeout`,
    then the step ends, its message saying to remove the print). The
    offset is saved already; an abort here keeps it.
  - Klipper's own `PROBE_CALIBRATE` / `Z_OFFSET_APPLY_PROBE` work too:
    `SAVE_CONFIG` (wrapped by `[ad5x_setup]`) turns their `[probe]
    z_offset` into this saved offset (ad5x.cfg's -0.25 minus the new
    value), and moves PID / shaper results into `ad5x-tuning.cfg`.
  - The wrapper already saves every adjust as it happens, as it does for
    baby-steps from anywhere. Abort writes the starting value back (zero
    when no offset was saved).
- **finish**:
  - `PID_CALIBRATE` and `SHAPER_CALIBRATE` leave their values for
    SAVE_CONFIG in `[extruder]`, `[heater_bed]` and `[input_shaper]`.
    ad5x.cfg, an included file, sets those same options, and Klipper's
    SAVE_CONFIG refuses them ("conflicts with included value"). So finish
    merges them into `printer_data/config/ad5x-tuning.cfg` and drops them
    from the SAVE_CONFIG set.
  - Then it runs `SAVE_CONFIG` if anything else is pending (the bed
    mesh), else `RESTART` if the tuning file changed, else nothing
    ("nothing to save").
  - If `printer.cfg`, `unit.cfg` or `local.cfg` set one of the moved
    options, they still win; the `finish` result names them.
  - Before restarting, the state is saved with `restarting: True`. After
    the restart the status shows `step: finish`, `state: done` and all
    results.

`SETUP_WIZARD` macro (the printer's `macros/quick_actions.cfg`,
`docs/config-layout.md`): runs `SETUP_WIZARD_STEP ACTION=wizard`, which
does two things:

- Writes `/data/ad5x/printer_data/comms/run-setup-wizard`. That is the
  same file as `/home/klipper/printer_data/comms/run-setup-wizard`, set
  by the option `wizard_flag`. S70helixscreen/HelixScreen opens the
  wizard at its next start and deletes the file.
- Sends `// action:ad5x_setup_wizard` to the G-code output. Moonraker
  passes it on as `notify_gcode_response`, so a running screen can open
  the wizard at once.

Klipper can't restart HelixScreen itself (it runs as `klipper`).
Moonraker's `POST /machine/services/restart?service=helixscreen` can,
through the root update agent, except while a print runs.

## Klipper side: implementation notes

- Klipper has one G-code lock. A step runs in a reactor callback and
  sends each command with `run_script`, taking the lock per command, as
  `virtual_sdcard` does. Console, screen and Moonraker G-code get in
  between.
- Some commands hold the lock for a long time: `PID_CALIBRATE`, `M109`
  inside `PRINT_START`, `BED_MESH_CALIBRATE`, `SHAPER_CALIBRATE`,
  `IFS_TUNE`. While they run, only the API endpoint gets through.
- An abort from the API replaces each heater's control with one that
  holds the heater off and reports "settled". Temperature waits end at
  once. `PID_CALIBRATE` ends with "interrupted" (its own check) and puts
  its normal control back.
- Our own heat waits (mesh, self-check) are loops that check the abort
  flag.
- The Z offset patch is sent line by line. The toolhead's lookahead keeps
  about 2 s of moves queued, so a +/- shows on the bed about 2 s later,
  as with baby-stepping during a print.
- setup.cfg includes `ad5x-tuning.cfg` as
  `[include /home/klipper/printer_data/config/ad5x-tunin[g].cfg]`. The
  `[g]` makes it a pattern, so a missing file isn't an error.
- setup.cfg comes after ad5x.cfg's own sections (before the `macros/`
  files and plugins), so the tuned values replace ad5x.cfg's, and
  unit.cfg / local.cfg still override them.
- In Klipper's file output (batch) mode the accelerometer query is
  skipped and heat waits return at once.

## Running the steps by hand (Fluidd console)

```
SETUP_WIZARD_STEP STEP=selfcheck            ; ~1 min, watch the console
SETUP_WIZARD_STEP STEP=pid                  ; ~10-20 min (bed is slow)
SETUP_WIZARD_STEP STEP=pid HEATERS=extruder ; the nozzle only (after a nozzle change)
SETUP_WIZARD_STEP STEP=mesh KEEP_BED=1
SETUP_WIZARD_STEP STEP=shaper               ; needs numpy (not in the image)
SETUP_WIZARD_STEP STEP=filament MATERIAL_2=PETG   ; HEAD=AUTO finds the slot in the toolhead
SETUP_WIZARD_STEP STEP=ifs                  ; slots loaded in the IFS first
SETUP_WIZARD_STEP STEP=zoffset MATERIAL=PLA
SETUP_WIZARD_STEP STEP=zoffset ACTION=adjust DELTA=-0.02   ; while it prints
SETUP_WIZARD_STEP STEP=zoffset              ; print another patch
SETUP_WIZARD_STEP STEP=zoffset ACTION=accept
SETUP_WIZARD_STEP STEP=zoffset ACTION=accept   ; the test print is off the bed
SETUP_WIZARD_STEP STEP=finish               ; saves, Klipper restarts
SETUP_WIZARD_STEP ACTION=abort              ; any time (waits for the lock)
SETUP_WIZARD                                ; screen wizard again
```

Fluidd's console shows each command the step sends. The status object is
`printer.ad5x_setup`, e.g. in Fluidd's "Printer objects" debug view, or
from a shell: `curl 'http://<printer>/printer/objects/query?ad5x_setup'`.
To abort through the API from a shell:
`curl -X POST 'http://<printer>/printer/ad5x_setup/control?action=abort'`.
`WAIT=1` makes a step block the console until it ends.

IFS tuning alone:

- `IFS_TUNE [CHANNEL=n] [SPEED=0] [LOAD=0] [UNLOAD=0] [TUBE=1]`
- `IFS_TUNE_SPEED [CHANNEL=]`
- `IFS_TUNE_LOAD [CHANNEL=]`
- `IFS_TUNE_UNLOAD [CHANNEL=] [TUBE=1]`
- `IFS_TUNE_RESET`
- `IFS_FIND_HEAD_SLOT [TEMP=]`: filament in the toolhead from a slot
  Kiln doesn't know (below)

The tuned values are in `printer.ifs.tune` and in the `ifs_*` lines of
variables.cfg. They can be set by hand, e.g.
`SAVE_VARIABLE VARIABLE=ifs_speed VALUE=1500`; the module reads them when
Klipper starts.

## Tests (laptop)

- `tools/test_ad5x_setup.py <klippy dir>` runs the module on Klipper's
  real reactor and lock, with stand-in heaters and commands. It covers:
  - background start, and live PID progress;
  - API abort during `PID_CALIBRATE`, and that a G-code abort has to
    wait;
  - Z offset adjust from G-code and from the API, an extra patch, accept,
    the `clear_bed` prompt and abort;
  - the filament step (materials, `HEAD=`, the slot found), the IFS and
    Z offset steps with an unknown slot in the toolhead, the patch
    temperatures from the slot's material, the status fields;
  - `WAIT=1`;
  - finish: tuning file, SAVE_CONFIG vs RESTART, overrides, results after
    the restart;
  - `SETUP_WIZARD`.
- `tools/test_ifs.py <klippy dir>` adds tests for the tuning. They run on
  `fake_ifs.py --physics`, which models lane positions, the toolhead
  sensor, the merge point and a drive that slips above a set speed. Also
  covered: tuned swaps, `IFS_TUNE_RESET`, sensor-checked purge, early
  heating and `IFS_FIND_HEAD_SLOT` (on the lane model and in MCU mode).
- Both need greenlet and cffi, e.g. `uv run --no-project --with greenlet
  --with cffi python tools/test_ad5x_setup.py <copy of klippy>`. Use a
  copy of `firmware/builds/klipper-mainline/klippy`, because Klipper
  builds its C helper in that directory.
- Klipper batch run of the real config (2026-10-16):
  - ad5x.cfg and setup.cfg parse;
  - the tuning-file pattern include works, with the file missing and
    present;
  - `SETUP_WIZARD` and `STEP=finish WAIT=1` run.

  In batch mode any G-code error ends the run, so the other steps can't
  run there.

## Must be checked on the printer

- Self-check thresholds: nozzle +3 C and bed +0.5 C in 10 s (the bed runs
  at 40 % power, `max_power: 0.4`). `ACCELEROMETER_QUERY` and
  `WEIGHT_TARE` answer.
- PID with the part fan at 100 %: nozzle overshoot with the result.
- Abort in the middle of each step, from the screen: heaters go off at
  once. Note how long homing, probing and the shaper test take to stop.
- Z offset patch:
  - line width, height and placement (centre and ±40 mm);
  - first-layer quality against the offset;
  - baby-steps show up about 2 s later;
  - accept saves `zoffset` and the next print uses it.
- finish: the SAVE_CONFIG restart; `ad5x-tuning.cfg` is loaded (PID
  values in `printer.configfile.settings`); results show after
  reconnecting.
- numpy for the vibration step: add `python-numpy` to the image, or skip
  the step.
- IFS tuning: see below.

## IFS tuning (QuickSwap-like)

Ideas from QuickSwap for zMod (MIT, ninjamida/quickswap-5x), reimplemented
in `klipper/extras/ifs.py`, no code copied:

- **Speed**: per slot, feed/retract at rising speeds (300…3000 mm/min) and
  keep the fastest that reaches the toolhead sensor reliably (2 runs, with
  margin). Saved as `ifs_speed`.
- **Load distance**: measure IFS-to-toolhead-sensor distance per slot from
  feed time × speed, so the load can go fast for most of the way and slow
  only for the last part. Saved as `ifs_load_dist_<ch>`.
- **Unload distance**: shortest combined extruder+IFS retract after the cut
  that clears the toolhead sensor (plus margin), and how far back into the
  tube it must go so another slot can feed. Saved as `ifs_unload_dist`,
  `ifs_tube_unload`.
- **Sensor-checked purge**: purge in short steps until the head sensor
  confirms flow, then a fixed finish length (defaults 15 + 15 mm, scaled for
  the 0.6 nozzle).
- **Parallel swap**: heat while parking/cutting, start the IFS retract while
  the extruder retracts, etc.

Values go to `variables.cfg` (`save_variables`), are read by `ifs.py` at
start, and override the `ifs.cfg` defaults. `IFS_TUNE_RESET` drops them.

### As implemented (klipper/extras/ifs.py)

Everything is measured with the toolhead filament sensor, so it needs
`head_sensor`. Distance = time from the feed command to the sensor change
x speed. The sensor is polled every 0.05 s (`sensor_poll`), but its ADC
only updates about every 0.3 s: roughly ±5 mm at 1200 mm/min, ±15 mm at
3000.

- **`IFS_TUNE`** runs, in order:
  - the unload measurement, if a slot is loaded and `UNLOAD=1`;
  - the speed sweep on the first slot;
  - the load distance for each slot with filament (or `CHANNEL=`);
  - the tube test, only with `TUBE=1` and two slots.

  Every lane is released (`F39`) at the end. Refused during a print.
- **Unload** (`ifs_unload_dist`): a real unload of the loaded slot: lift,
  cut, then IFS and extruder pull until the sensor stops it, with a
  90 mm limit. Saved value = mm until the sensor cleared + 10, rounded
  up. Swaps then use it for `F11 L` and the extruder retract
  (`unload_gcode` gets `params.LENGTH/SPEED`). With nothing loaded,
  `IFS_TUNE_UNLOAD CHANNEL=n` first loads that slot the normal way (a
  full swap, with purge).
- **Park**: tuning leaves a lane where a swap's unload leaves it: pulled
  back until the sensor clears, then the tube pull-back.
- **Speed** (`ifs_speed`):
  - One settle run (load to the sensor, park).
  - Then 2 runs per speed (load to the sensor and park, both at the test
    speed), from `load_speed` (1200, stock) up through 1500, 1800, … to
    `tune_max_speed` (3000).
  - The sweep stops at the first fault, missed sensor or slip (a run
    20 % + 10 mm longer than at 1200). It keeps one step below the
    fastest speed that worked, as a margin.
  - Speeds below 1200 aren't tried: a slot that fails at stock speed is
    reported as a fault.
  - Swaps use the tuned speed for the fast part of loads and for the
    tube pull-back.
- **Load distance** (`ifs_load_dist_<n>`): measured from the parked
  position, after a settle run; the shorter of 2 runs. In a swap the load
  first feeds `dist - max(20, 15 %)` at `ifs_speed`, stopping at once if
  the sensor triggers early. The stock load at 1200 then goes on to the
  sensor. Only used when the tuned speed is above `load_speed`.
- **Tube pull-back** (`ifs_tube_unload`, opt-in with `TUBE=1`): park slot
  A with pull-backs of 70 (or the current value), 50, 35 and 25 mm, and
  feed slot B each time. If B faults or feeds slowly, A still blocks the
  merge. Saved value: the shortest that worked + 10, at most the current
  value. Risky, because two strands meet in the merge, so the wizard
  doesn't run it unless asked.
- **Sensor-checked purge** (`sensor_purge: True` in [ifs], off by
  default):
  - One purge round per swap.
  - After the push, the extruder feeds `purge_confirm` (15) mm in
    `purge_step` (5) mm steps, each checked against the sensor.
  - Then `purge_gcode` flushes `purge_finish` (15) mm (`params.FLUSH`).
  - Lengths are scaled by nozzle/0.4: 22.5 + 22.5 mm for the 0.6 nozzle.

  This purges much less than stock, so colour changes then rely on the
  slicer (prime tower or flush). It isn't tied to tuning: tuning doesn't
  change the purge.
- **Parallel**: idle swaps and unloads set the nozzle temperature at the
  start (`M104`) and wait for it (`M109`) only before the first extruder
  move (the cut, or the push). Heating then overlaps the lift, the
  selection and the IFS feed. The IFS pull and the extruder retract
  already ran together.
- Status: `printer.ifs.tune` = `{speed, load_dist: {"1": …}, unload_dist,
  tube_unload, running, progress, message}`. None means the default is
  in use.
- To check on the printer:
  - the measured distances against a ruler (the sensor timing);
  - that loads at 1500–3000 mm/min don't grind or skip;
  - how far the fast load overshoots the sensor at the tuned speed;
  - the unload with the shorter length;
  - whether the tube test is safe at all.

### The slot in the toolhead (`IFS_FIND_HEAD_SLOT`)

On a fresh install over stock, the last print's slot is usually still in
the toolhead, and Kiln doesn't know which slot that is ("loaded" at the
IFS, filament on the spool, is not "in the toolhead"). Unloading a guessed
slot pulled the wrong lane for a minute and failed ("filament still in
the toolhead"). `IFS_FIND_HEAD_SLOT [TEMP=] [SLOT=]`
(`klipper/extras/ifs.py`):

- Nothing moves when the toolhead sensor sees no filament, or when Kiln
  knows the slot (it says which). Needs the toolhead sensor with a
  reading, the printer homed, and no print. A slot only adopted at
  startup (`loaded_source` `adopted`) isn't known: the find runs, that
  slot tried first, and the guess is dropped (nothing loaded) before it
  starts, so a find that fails leaves the slot unknown, not the guess.
  The toolhead empty: an adopted slot is dropped too.
- Slots tried: those with filament at the IFS (a fresh status), the
  adopted slot first, else the one the IFS has selected. None: an error,
  nothing moves.
- Heat: as `IFS_UNLOAD`, only when the nozzle is idle: the hottest
  material of those slots, at least `[ifs] find_temp` (240) when one of
  them has no material. 240 suits PLA and PETG: the find moves only the
  strand above the cutter, so the nozzle only needs to be past
  `min_extrude_temp` and soft enough for the extruder's 5 mm back-off
  after the cut not to tear a PETG tip (PETG prints at 230-250, PLA's
  range tops out about there). The old target comes back afterwards, on
  every way out.
- Lift (`before_gcode`), wait for the heat; a stop during that wait (the
  wizard's abort holds the heater off, so the wait ends at once) ends it
  before the cut. Then the cut (`cut_gcode`).
- **Phase 1, the extruder alone**: the lane the IFS holds is released,
  then the extruder retracts the unload length (the tuned
  `ifs_unload_dist`, else `unload_length`, 60 mm) in 5 mm steps, the
  sensor read after each (`find_settle`, 0.4 s, for a fresh reading).
  The cut strand passes through the extruder gears (stock's unload
  retracts the extruder with the lane). Whether the sensor sits above
  the gears or between the gears and the cutter is not known, so:
  - The sensor clears: it sits below the gears, the extruder alone moves
    the strand past it, and no lane pull could tell which slot it is.
    The extruder feeds the strand back the same length; the sensor sees
    it again: `find_result` `pick`, the user names the slot. It doesn't
    come back (the strand left the gears right at the sensor): `tube`,
    the strand sits in the tube above the sensor, `tube_blocked` is set
    (saved) and every load, unload (`IFS_UNLOAD`: the screen's Unload
    sends the IFS's selected lane, a guess), `IFS_SET_CHANNEL CHANNEL=n`,
    tuning and pre-feed is refused until `IFS_FIND_HEAD_SLOT SLOT=n`
    pulls lane n back (the unload length plus the tube pull-back) or
    `IFS_SET_CHANNEL CHANNEL=0` says it was pulled out by hand. No lane
    has moved in either case.
  - The sensor still sees it: the cut end has left the gears (the unload
    length is longer than the cutter-to-gears path) and only its own
    lane can move it now.
- **Phase 2, lane by lane** (feeder only, no extruder): select a slot,
  pull it back the unload length, stopping when the sensor clears.
  - Still filament: not this slot. It is fed back the same length, so
    repeated finds (Retry) don't walk it out of the IFS; on Flashforge's
    firmware a stall there stops the find (the strand isn't where it
    was), Klipper's firmware has no stall detection.
  - Cleared: the slot is fed back up to the sensor (the unload length +
    10 mm at most; it must bring filament back, else the find stops with
    the tube blocked, below), then gets the normal unload (pull until
    clear, the tube pull-back) and is released; `printer.ifs.channel` is
    0 and the wizard remembers the slot (`filament.head_source` `found`).
- No slot clears the sensor: `none`, "pull the filament out of the
  toolhead by hand". Every slot is back where it was.
- A failure or stop after the strand left the sensor (phase 1's
  feed-back, the right slot's feed-back, its unload, a slot that
  doesn't bring filament back): the IFS is reset, and when the sensor
  then reads empty the strand sits in the tube above it: `tube_blocked`
  is set (saved) and `find_result` is `tube`, as above; the error names
  the slot when it was known (`IFS_FIND_HEAD_SLOT SLOT=<that slot>`
  pulls it back).
- Any failure but a stop, also a G-code error inside (a cold extrude):
  the last slot tried is released (after `IFS_STOP` the lane stays as
  the stop left it, as in `IFS_UNLOAD`). Every failure: the IFS reset
  (F15, or the motors off on Klipper firmware), `abort_gcode` puts the
  fan, runout sensor and G-code state back. `IFS_UNLOAD` and swaps got
  the same clean-up for G-code errors and the same stop check after
  their heat wait.
- From the start of a find until the toolhead's slot is known again (a
  load, an unload, `IFS_SET_CHANNEL`, a find that found it),
  `ifs_find_open` is saved: the startup check then adopts no lane (the
  IFS's selection is the last slot tried, not the loaded one).
- The startup check (issue #13: a lane loaded under zMod leaves no
  `ifs_loaded`): no slot saved, the toolhead sensor sees filament, the IFS
  has a lane with a spool selected: that lane is recorded as loaded, but
  as a guess (`loaded_source` `adopted`, saved as `ifs_loaded_source`,
  kept across restarts). The selection is only the last lane the IFS
  moved: on the owner's printer (2026-11-19) the old wizard's failed
  unload of slot 1 left lane 1 selected with slot 2 in the toolhead, the
  next start adopted slot 1, and that `ifs_loaded = 1` was still there
  after a return to stock and a new install. So an adopted slot is never
  built on: this find and the wizard's steps find the slot; `IFS_SWAP` to
  it (a print starting with that slot) loads it again; its first unload
  (a swap, `IFS_UNLOAD`, `UNLOAD_FILAMENT`) must clear the toolhead
  sensor, else nothing is recorded as loaded and the error says the slot
  was a guess (`IFS_FIND_HEAD_SLOT` finds it, `IFS_SET_CHANNEL CHANNEL=n`
  names it). A right guess still does what issue #13 needed: the swap
  or unload goes through and the slot is Kiln's from then on. Return
  to Flashforge firmware and the installer drop the saved slot record
  (`ifs_loaded`, `ifs_loaded_source`, `ifs_find_open`, `ifs_tube_blocked`)
  from `variables.cfg`: stock has run since.
- `IFS_STOP` (the wizard's abort) stops it between moves, also one
  that came while the slots were being queried.
- `find_result` starts empty at each find; a find that finds the
  toolhead empty also ends an open find (`ifs_find_open`), e.g. after
  "none" and pulling the strand out by hand. The filament step's
  `HEAD=AUTO` with the toolhead empty does the same
  (`IFS_SET_CHANNEL CHANNEL=0`).
- Both IFS modes (Flashforge's firmware on the serial link, Klipper
  firmware): the same moves, F10/F11 or feeder steps.
- `printer.ifs`: operation `unload`, `target_channel` the slot being
  tried; afterwards `find_result`, `head_found`, `tube_blocked`.
- `SLOT=n`: the user names the slot: recorded as loaded (the toolhead
  has filament), or with `tube_blocked`, lane n pulled back out of the
  tube.

Tests: `tools/fake_ifs.py --gears` models the extruder (a strand past the
gears moves with every extruder move; a lane can't pull it alone), and
`tools/test_ifs.py` runs the find with the sensor above the gears and
below them (pick, tube), Retry, repeated finds, a stop during the heat
wait or the slot query, a G-code error inside, a restart after a failed
find, the block holding against `IFS_UNLOAD`, `IFS_SET_CHANNEL
CHANNEL=n` and loads (with the lanes' merge modelled), and a stop or
failure after the strand left the sensor blocking the tube.

To check on the printer: which geometry it is (does phase 1 clear the
sensor?), that a wrong slot comes back to where it was, the time a find
takes with four slots.

## Settings seed

`/usr/share/ad5x/helixscreen-settings.json` is only copied when there is
no `/data/ad5x/helixscreen/config/settings.json`, i.e. on a fresh install,
and carries `wizard_completed: false` so the wizard runs once. Printers that
already have settings keep theirs and see no wizard after
an update.

## HelixScreen side (`buildroot/package/helixscreen/000*.patch`)

Patches on HelixScreen v1.1.0-rc.1 (63 files, `0001` to `0071`; the missing
numbers were dropped because upstream has them), applied by Buildroot after
extract (after the `GIT_INIT` hook has committed the pristine tree, so
upstream's own submodule patching is unaffected; they touch `src/`,
`include/`, `ui_xml/`, `tests/`, `translations/`, a few `assets/` files, and
for 0007 and 0057 the build files). The table below covers the setup wizard
and the first patches, `0001` to `0019`; the later ones are listed in
`docs/deviations-from-stock.md` (row "HelixScreen source"). Regenerate them
from a clean clone of the build dir's `import` commit with `git format-patch`.

| Patch | What |
|---|---|
| `0001-wizard-ad5x-setup-steps` | The seven AD5X steps, the `ad5x_setup` subscription, telemetry step skipped on AD5X |
| `0002-settings-run-setup-wizard` | Settings > Printer > **Run Setup Wizard** |
| `0003-application-wizard-rerun-flag-file` | `HELIX_WIZARD_FLAG_FILE` at start; `action:ad5x_setup_wizard` while running |
| `0004-ams-ad5x-ifs-ports-are-prep-sensors` | The IFS's port sensors shown as prep sensors |
| `0005-settings-plugins-panel` | Settings > Printer > **Plugins** (`docs/plugins.md`) |
| `0006-wizard-ad5x-time-zone-step` | **Time Zone**, the first AD5X step (below) |
| `0008-ad5x-nozzle-size` | **Nozzle Size**, the second AD5X step, and Settings > Printer > **Nozzle Size** (`SET_NOZZLE_SIZE`, `docs/print-start.md`) |
| `0009-ad5x-bed-soak-and-nozzle-checks` | Settings > Printer > **Bed Heat Soak** (on/off, calibrated times, Calibrate with progress and Stop; `docs/print-start.md`); after a Nozzle Size change in Settings, the offer to run the hotend PID, Z offset and Save only |
| `0007-sound-pwm-backend-and-printer-sounds` | HelixScreen's sounds on the speaker, Settings > Sound > **Printer Sounds** (`docs/sound.md`) |
| `0010-ad5x-auto-refill` | Settings > Printer > **Filament Auto-Refill** (on/off, colour match, the backups per slot, Filament slots); the **No backup spool** pop-up during a print when Klipper's `refill_notice` is set |
| `0011-ad5x-home-layout` | The AD5X home screen (preset seed `assets/config/panel_widgets/ad5x/home.json`, 800x480 grid only): nozzle, bed, fans and notifications along the top; the print status card (no temperature row of its own: config `show_temps`) on the left; IFS slots, Preheat/Cool Down (one track tall, no temperature column: preheat `show_temps`), the LED light and the live Z offset under it, Motion and an **Unload** button (`favorite_macro` `label`) on the right, Preheat/Cool Down and Unload greyed and inert while printing or paused (`lock_while_printing`); no printer picture, temperature graph or tips. A seed `revision` in the layout signature moves an unedited default to it on update; an edited layout stays |
| `0012-ad5x-wizard-purge-box-soak-summary` | The AD5X steps on the screen follow the Klipper order (mesh before the Z offset): the purge box check (`trash`, arrows move the box and the nozzle over it, Factory spot), the Z offset's **Estimate first** (shown with `zoffset_estimate: 1`), the optional bed soak and the summary before Save; Wi-Fi's **Add Hidden Network** in the wizard; Settings > **Purge Box** (the purge box check alone) |
| ~~`0013-ad5x-keyboard-underscore`~~ | Dropped with HelixScreen beta.18: upstream has the underscore |
| ~~`0014-ad5x-home-no-swipe-with-arrows`~~ | Dropped with beta.18: upstream fixed it (prestonbrown/helixscreen#1978) |
| `0015-ad5x-wizard-one-page-steps` | The Z offset step's buttons read Closer / Away (no hint line); the purge box is one row of arrows (Left, Right, Front, Back, Factory), so Accept and Abort fit on the page; shorter step text |
| ~~`0016-ad5x-network-menu-fixes`~~ | Dropped with beta.18: upstream reads the kernel's IP and leaves out hidden SSIDs itself |
| `0018-ad5x-preset-no-aux-fan` | The AD5X preset has no aux fan (`chamber_fan` is not on the printer): an empty `fans/aux` is no longer filled from the preset at every boot, which made the fan step come back each start |
| `0019-ad5x-buttons-no-drag-scroll` | Plain buttons do not pass a drag to the panel behind them (LVGL scroll chain off); list rows (`*_row`) keep drag-scroll. Set in `create_xml_hidden`, the home page walk and the home tile resize |

### Steps

One data-driven step class (`src/ui/ui_wizard_ad5x_setup.cpp`,
`WizardAd5xSetupStep`), one instance per row of a table (`StepId`, step
name, XML component, explanation). New `StepId`s `Ad5xSelfcheck` ...
`Ad5xFinish` sit between `FilamentSensor` and `InputShaper`, so the order
is: touch calibration (skipped when the seed's calibration is valid),
language, Wi-Fi, connection (auto, local Moonraker), [hardware pickers,
collapsed by the preset], **self-check, PID, bed mesh, vibration, filament,
IFS, purge box, Z offset, bed soak, summary, save** (`Ad5xFilament`, patch
0084, sits between `Ad5xShaper` and `Ad5xIfs`), [HelixScreen's own input
shaper step: skipped, the preset keeps it off], preferences, [summary: skipped in preset first-run], [telemetry:
skipped on AD5X]. The last visible step (preferences) has Finish.

The AD5X steps exist when the active printer's preset is `ad5x` or Klipper
lists an `ad5x_setup` object; on every other printer they are skipped and
the wizard is upstream's. Vibration compensation uses our step (`shaper`)
rather than HelixScreen's built-in one: the result then goes through
`pending_save` and the save step like the others, and the built-in step
stays skipped by the preset (it is shown only when
`initial_resonance_compensation_run` is false, which we never set).

Every action (start, abort, adjust, accept) goes to the API endpoint as
JSON-RPC `printer.ad5x_setup.control` with `step`, `action`, `delta` and
the step options, so abort and adjust also work while a long command holds
the G-code lock. If Moonraker answers "method not found", the screen falls
back to `SETUP_WIZARD_STEP STEP=… ACTION=…` as G-code. A refusal shows
without its `[reason] ` (patch 0070). Start returns at
once; the card follows `state`. Step options sent: the mesh step gets
`keep_bed: 1` when the Z offset step is part of the run (always, in both
the full wizard and the settings session). The Z offset step sends no
`material` (Klipper takes the loaded IFS slot's type, else PLA); the IFS
step sends neither `channel` nor `tube` (tube tuning is not offered). The
filament step sends `head` (`auto`, `1`-`4`, `0`, `keep`, from its
toolhead dropdown, or the slot named on the `pick_slot` panel) and
`material_<n>` only for a slot with filament whose material the user
changed (`?` for Unknown); the rest stays as it is. The step also reads
`printer.ifs` `tube_blocked`, `find_result`, `head_found` and `colors`
(queried with `ad5x_setup`, and from its updates).

Each step's screen (`ui_xml/wizard_ad5x_<step>.xml` for the title,
`wizard_ad5x_setup.xml` for the body):

- explanation of what the step does;
- filament (not while it runs): the four IFS slots from `filament`, a
  material dropdown for each slot with filament (Unknown, then the IFS's
  types PLA, PLA-CF, SILK, TPU, ABS, PETG, PETG-CF, plus the slot's own type
  when it is another one), "Empty" for the others, and **Filament in the
  toolhead**: Auto (find it), Slot 1-4, None (empty), Use the filament in
  the toolhead as it is (`keep`). The dropdowns follow `filament` live
  until the user changes them. Under it, one line on the toolhead now
  ("Toolhead: slot 2, PETG", "Toolhead: filament from an unknown slot",
  "kept as it is", "strand in the tube, slot unknown"); the IFS and Z
  offset pages show the same line before Start. With `tube_blocked` (or
  `head_source` `tube`) the filament page adds "A strand is still in the
  tube: name the slot first" (the toolhead dropdown's Slot n does that);
- **Start** (`action: start`);
- while `state` is `running` (and `waiting_user`): the current `action` in
  words (a phrase per key, e.g. "Heating", "Probing the bed", "Finding the
  slot in the toolhead", "Loading slot 2", "Printing test patch 2"; a key
  the screen doesn't know shows as it is), `message`, progress bar
  (`progress`), then the nozzle and bed temperature now/target (`extruder`,
  `heater_bed`) and the time since `step_started` (m:ss), updated every
  second. When the printer's clock is not set (`step_started` 0 or far from
  the screen's time) the screen counts from when it first saw the run.
  **Abort**; the footer's Next is disabled;
- Z offset, from the start: the patch's plan from `zoffset_plan` ("Slot 2,
  PETG, 240/70 °C"); with `guess` true it says "Material unknown: using
  PLA temperatures" (or that a type has no temperatures) and to Abort and
  set it in the Filament step if that is wrong;
- Z offset, `state` `waiting_user`: the current `zoffset`, buttons Closer 0.05,
  Closer 0.01, Away 0.01, Away 0.05 (`adjust` -0.05, -0.01, +0.01, +0.05), **New Patch** (`start` again: another
  patch beside the first), **Accept** and Abort;
- `prompt` `clear_bed` while waiting: only "Remove the test print from the
  bed" and **Done** (`accept`); the adjust buttons, the live view and Abort
  are hidden. After a failed or aborted Z offset with `clear_bed`: a
  reminder to clear the bed before Retry, with **Done** (`accept` clears
  it);
- `prompt` `head_unknown` (failed): the message and how to get the filament
  out by hand (cut it at the toolhead, pull it out at the top), then
  **Retry**;
- `prompt` `pick_slot` (failed): "Which slot is in the toolhead?", what to
  look at (the tubes), a button per slot with filament (all four when
  none is known) labelled "Slot 2 · PETG" with the spool's colour from
  `printer.ifs.colors`, and **I pulled it out by hand**. A slot runs the
  filament step with `head=<n>`, by hand with `head=0`. On the IFS or Z
  offset card that filament run shows on the card (live view, its
  message); once it is done the card offers its own Start again. Retry
  before naming starts the card's step again, which asks again;
- `HEAD=KEEP` and the IFS step: its failure message (pull the filament
  out) shows as it is, with Retry;
- a `prompt` key the screen doesn't know: its `message`, with **Done**
  (`accept`) while waiting, **Retry** when failed;
- `done`: the step's line from `results` (self-check: one line per entry of
  `checks`, `OK`, `FAIL`, or `WARN` for a failed item with `required:
  false`; save: every result including `finish`), **Run Again**, footer
  Next;
- `failed`/`aborted` (or the request was refused): the message, **Retry**,
  footer Skip;
- not started: footer **Skip** leaves the step out.

Leaving a running step with Back sends `abort` (not for the save step).
The save step arms HelixScreen's expected-restart handling when
`pending_save` is true or unknown (no disconnect modal, no recovery
dialog), shows "Saving... Klipper is restarting" while Klipper is down, and
after the reconnect shows `finish`/`done` with the results from the status
object (Klipper keeps them across the restart).

The status object is subscribed with the app's main subscription (whole
object) when `objects/list` has `ad5x_setup`; the step also queries it
when it opens, after every request and whenever Klipper becomes ready.

### Time zone (patch 0006)

The first AD5X step, before the self-check: a dropdown of HelixScreen's
time zones (the same list as Settings > Language & Time), set to the
current one; a choice is applied and saved at once (the screen's clock and
screensaver; the printer itself keeps UTC). It runs nothing on the printer
and always offers Next. It is in the first-start wizard and in every
"Run Setup Wizard" session.

### Nozzle size (patch 0008)

After the time zone: a dropdown of `printer.ad5x_nozzle.sizes`, set to the
current size (the factory 0.4). A different choice sends `SET_NOZZLE_SIZE`
on Next; the step waits until Klipper is back with the new size before the
self-check starts (Retry / Skip after 60 s). When `local.cfg` sets the
size, the dropdown is off and says so. Settings > Printer > Nozzle Size
changes it later (confirm: Klipper restarts).

### Running it again

- **Settings > Printer > Run Setup Wizard** (only where the steps exist):
  confirm, then the time zone, the nozzle size and the seven AD5X steps run as a targeted wizard session over
  the current screen. `wizard_completed`, the preset and the hardware
  selections are not touched; Back on the first step or Finish on the last
  returns to Settings.
- **`SETUP_WIZARD` while the screen runs**: HelixScreen watches
  `notify_gcode_response` for `action:ad5x_setup_wizard` and opens the same
  targeted session at once (unless a wizard is already open), deleting the
  flag file so the next start doesn't run it again.
- **Flag file**: S70 sets `HELIX_WIZARD_FLAG_FILE=/data/ad5x/printer_data/comms/run-setup-wizard`.
  If that file exists at start, the full wizard runs once and the file is
  deleted as soon as the wizard is up (a crash mid-wizard does not repeat
  it). Unlike `--wizard`, the preset, Moonraker host and hardware
  selections are kept, so the pickers stay collapsed and the connection
  step is skipped.

### Seed and first boot

The template `helixscreen-settings.json` has `wizard_completed: false`
at the root and under `printers.default`; everything else (preset `ad5x`,
`preset_provisional: false`, touch calibration, fans, sensor, host,
`telemetry_enabled: false`) is unchanged. `S70helixscreen` copies it only
when `/data/ad5x/helixscreen/config/settings.json` does not exist, so:

- fresh install: wizard once, preset authoritative (pickers collapsed),
  touch calibration skipped;
- existing install / update: the old settings.json stays, no wizard.

### Not verified

Compiled for the AD5X with Buildroot only; never run (no mock printer has
`ad5x_setup`, and nothing here has been on the screen). What to check on the
screen: `docs/helixscreen-integration.md`, section "Setup wizard".

## First run on hardware (the developer's printer, 2026-10-16)

Run from Settings > Printer > Run Setup Wizard, on update `202610161833-bb18ef9f`.

| Step | Result |
|---|---|
| selfcheck | 11/11 OK. Nozzle +15.1 C and bed +3.5 C in 10 s. Fans have no tach, so they only show "ran". |
| pid | Nozzle Kp 21.608 Ki 1.470 Kd 79.411; bed Kp 30.235 Ki 0.681 Kd 335.610. About 12 min in total. |
| mesh | 5x5, range 0.438 mm, contact about Z -3.6 to -4.1 (same as the earlier hot mesh). About 3.5 min. |
| shaper | X mzv 57.4 Hz, Y mzv 51.0 Hz. Klipper suggests max_accel <= ~3200 for mzv on Y. About 3 min. |
| ifs | Speed 2700 mm/min; 3000 passed, one step down kept as margin. Load from the park position 89/92/89/89 mm. Unload 31 mm: the head sensor cleared after about 21 mm, plus 10 mm. |
| zoffset | -0.36 mm (was -0.16). Four -0.05 taps, applied live while the patch printed. |
| finish | `ad5x-tuning.cfg` written and SAVE_CONFIG run for the mesh; after the restart everything was active. |

Found and fixed after the run:
- **The zoffset step refused** because the IFS step leaves the toolhead empty, and the filament had to be pushed in by hand. The step now loads the slot IFS_TUNE cut out, else T0's slot (`IFS_LOAD`).
- **IFS_TUNE kept the nozzle at 220 C** for the whole speed and load sweep. Heat now covers only the cut and unload.
- **The save step's button said "Start".** It now says "Save & Restart" (Klipper restarts; the printer does not reboot).
