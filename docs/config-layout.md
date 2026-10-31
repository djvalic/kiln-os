# Klipper config layout: factory and user files

Rule: the read-only image holds only a plain factory default (what is
true of every AD5X, and the stock firmware's own behaviour); every choice
this system makes beyond stock is a file in the printer's config
directory, which the user can edit in Fluidd.

- **Factory (read-only)**: `/usr/share/ad5x/config/` (`ad5x.cfg`,
  `ifs.cfg`, `setup.cfg`) and the shipped plugins in
  `/usr/share/ad5x/plugins/`. Replaced by every system update. With
  nothing else the printer behaves as stock.
- **User (read-write)**: `/home/klipper/printer_data/config`
  (= `/data/ad5x/printer_data/config`), shown in Fluidd under
  Configuration. Two kinds:
  - the printer's own settings (`printer.cfg`, `unit.cfg`, `local.cfg`,
    `plugins.cfg`, `ad5x-tuning.cfg`, `variables.cfg`, `moonraker.conf`):
    written once (or by Klipper commands), **never** changed by updates;
  - `macros/*.cfg`: this system's editable defaults (its print start,
    prime line, quick actions, ...). Copied from the image's templates at
    first boot; **an update that changes a template replaces the file**
    (an edited one is kept as a backup first, see below).

So: small tweaks you want to keep go in `local.cfg` (read last, never
touched). Editing a `macros/` file works too, but the next update that
changes that file replaces it (your version is kept next to it as
`<name>.cfg.bak-<date>` and you get a notice).

## Include order

```
printer.cfg                          user, never replaced
  /usr/share/ad5x/config/ad5x.cfg    factory: hardware, stock macros
    ifs.cfg                          factory: IFS link, stock swap templates, T0-T3
    setup.cfg                        factory: [ad5x_setup] (setup wizard module)
      ad5x-tuning.cfg                user (wizard results; optional)
    [ad5x_config]                    factory: update notices, CONFIG_BACKUPS
    macros/*.cfg                     user: editable defaults, in name order (optional)
    [ad5x_plugins]
    plugins.cfg                      user: enabled plugins, in file order (optional)
  unit.cfg                           user: per-printer calibration
  local.cfg                          user: overrides, read last
  SAVE_CONFIG block
```

The `macros/` and plugins includes sit at the end of `ad5x.cfg` (the
image), so an existing `printer.cfg` picks them up without being changed.
Both are glob patterns: no `macros/` directory or no `plugins.cfg` is no
error. Klipper sorts the files a glob matches by name.

Klipper merges sections of the same name across files: a later file's
option replaces the earlier value of that option, other options stay.
For a `[gcode_macro]` that means a later `gcode:` replaces the whole
macro body and later `variable_*` lines replace single variables. A
multi-line option such as an `[ifs]` template (`prime_gcode:`,
`purge_gcode:`, ...) is replaced as a whole too, never merged line by
line (checked with Klipper's config reader: `prime_gcode` A1/A2/A3 in one
file, B1 in a later one gives just B1; the other `[ifs]` options stay).

So, for example, the stock `PRINT_START` in `ad5x.cfg` is replaced by
the one in `macros/print_start.cfg`; `local.cfg` can then still change
one of its variables:

```
[gcode_macro PRINT_START]
variable_mesh_every_print: 0
```

A section that exists only in a `macros/` file (e.g. `_PRIME_LINE`) needs
that file: a `local.cfg` with only `variable_*` lines for it and no
`macros/prime_line.cfg` stops Klipper ("gcode must be specified").

## Files

| File | Where | R/W | What's in it | Why there |
|---|---|---|---|---|
| `ad5x.cfg` | image `/usr/share/ad5x/config` | RO | MCUs, pins, kinematics, steppers, TMC, homing (stock Z-X-Y order), extruder and bed heaters/sensors and their safety limits (bed `smooth_time: 3.0`, `max_power 0.4`), hotend power pin, probe and strain-gauge tare (`[ad5x_weight]`, `LOAD_CELL_TARE`), bed mesh limits, accelerometer and input shaper, part/board fans with stock's `M106`/`M107`, board-fan watchdog, chamber light, toolhead sensors and runout (`GET_FILAMENT_VALUE`, `GET_CUT_VALUE`), `M900`, `[virtual_sdcard]`, `[pause_resume]` with pass-through `PAUSE`/`RESUME` macros, `[exclude_object]`, `[gcode_arcs]`, `[firmware_retraction]` (0.7 mm / 35 mm/s); stock print macros: `PRINT_START` as the stock app (no mesh unless `LEVEL=1`, first tool always loaded fresh, no prime line), the stock Z check (`_CHECK_Z*`), Z offset saving and applying (`SET_GCODE_OFFSET`, `_APPLY_Z_OFFSET`, `_SEED_ZOFFSET`), `BED_MESH_CALIBRATE` with tare and saved centre, `PRINT_END`, `CANCEL_PRINT`, purge box moves (`_PURGE_BOX`, `_PURGE_WIPE`, `_NOZZLE_BRUSH`), status line `_PRINT_STATUS`; `[ad5x_config]`, `[ad5x_plugins]` | Physically true of every AD5X, or what stock does. Firmware retraction and arcs are capabilities that change nothing unless a file uses `G10`/`G11`/`G2`; the board-fan watchdog protects the electronics; the bed waits only for heating up (`TEMPERATURE_WAIT MINIMUM`), as the stock app |
| `ifs.cfg` | image | RO | `[save_variables]`, `[ifs]` link and lengths/speeds/timeouts (stock values), stock swap templates (`before_gcode`, `cut_gcode`, `unload_gcode`, `purge_start_gcode`, `purge_gcode`, `after_gcode`, from the capture of the stock app), `T0`-`T3`, purge tuning commands `IFS_PURGE_TEST`/`IFS_PURGE_RESULT` | The IFS hardware and the stock swap; tuning commands do nothing until run |
| `setup.cfg` | image | RO | `[ad5x_setup]` (setup wizard module options), include of `ad5x-tuning.cfg` | Module options only |
| shipped plugins | image `/usr/share/ad5x/plugins` | RO | `zmod-compat`, `nopoop`, `bambufy-compat`, `recommend` | Opt-in switches: off = stock; which are on is in `plugins.cfg` |
| `printer.cfg` | config dir | RW, never replaced | Includes `ad5x.cfg`, `unit.cfg`, `local.cfg`; SAVE_CONFIG block (bed mesh) | The printer's own |
| `unit.cfg` | config dir | RW, never replaced | `[gcode_macro _AD5X_UNIT]`: stock per-unit calibration (Z offset seed, cutter and purge box offsets) | Per printer, from stock's settings at first boot |
| `nozzle.cfg` | config dir | RW, never replaced; written by `SET_NOZZLE_SIZE` | `[extruder] nozzle_diameter` (the setup wizard's Nozzle Size step, Settings on the touch screen); absent = the factory 0.4 | Included at the end of `ad5x.cfg`: after the factory `[extruder]`, before `unit.cfg` and `local.cfg` |
| `local.cfg` | config dir | RW, never replaced | The user's lasting overrides (user's printer: `nozzle_diameter: 0.6`, `[ifs] flush_speed: 480`) | Read last: wins over everything |
| `plugins.cfg` | config dir | RW, never replaced | Enabled plugins (`ENABLE_PLUGIN`/`DISABLE_PLUGIN`) | The user's choice |
| `ad5x-tuning.cfg` | config dir | RW, written by the wizard | PID and input shaper results | Per printer |
| `variables.cfg` | config dir | RW, Klipper | Saved state: `zoffset`, `ad5x_center_z`, `ifs_loaded`, slot materials, tuning | Per printer |
| `macros/print_start.cfg` | config dir | RW, refreshed by updates | `PRINT_START` (this system's: mesh of the print area every print `variable_mesh_every_print: 1`, `variable_adaptive_mesh: 1`, `variable_retract: 3`, status line per step, prime line or first tool), `_PRINT_START_TOOL` (first tool already loaded: one purge at the box instead of cut and reload) | Choices beyond stock |
| `macros/prime_line.cfg` | config dir | RW, refreshed | `_PRIME_LINE` (un-retract, prime, slow wide line in front of the objects, wipe; variables `prime_line`, `length`, `height`, `width`, `flow`, `speed`, `unretract`, `prime`, `prime_speed`, `gap`, `margin`, `wipe`, `retract`) | Not stock (zMod's `LINE_PURGE`) |
| `macros/quick_actions.cfg` | config dir | RW, refreshed | `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `CLEAR_NOZZLE`, `AUTO_FULL_BED_LEVEL` (HelixScreen's AD5X buttons, zMod names), `_HEAT_FOR_FILAMENT`, `SETUP_WIZARD` | Conveniences, not stock |
| `macros/ifs_templates.cfg` | config dir | RW, refreshed | `[ifs] prime_gcode` (wipe after a prime-only swap: nopoop modes, `_NOPOOP`, `IFS_SWAP PURGE=0`) | Swap behaviour beyond stock |
| `macros/*.cfg.bak-<date>` | config dir | RW | Your edited version of a file an update replaced | Not read by Klipper (doesn't match `*.cfg`) |
| `config-updates.txt` | config dir | RW | One line per replaced edited file: which file, where the backup is | Notice; `CONFIG_BACKUPS ACK=1` deletes it |
| `.ad5x-templates.json` | config dir | written at boot | sha256 of the template each `macros/` file was copied from | Tells an unedited file from an edited one |
| `moonraker.conf` | config dir | RW, never replaced | Moonraker | The printer's own |

Kept where they are: the first tool load of a print purging in full at
the box in trash mode (`ifs.py`, code), nopoop modes (plugin), firmware retraction values and
bed `smooth_time` (factory), the bed `TEMPERATURE_WAIT MINIMUM` heating
(both `PRINT_START`s).

## Updates of `macros/`

`S05ad5x-data` runs `ad5x-config-templates` at every boot. The image's
templates are `/usr/share/ad5x/defaults/macros/*.cfg` (repo
`klipper/macros/`); `.ad5x-templates.json` records the sha256 of the
template each file was copied from. For each template:

| Situation | What happens |
|---|---|
| File missing, never installed (first boot, or a new template) | Copied |
| File missing, installed before (you deleted it) | Left deleted: that part goes back to factory/stock. To get it again, delete its line in `.ad5x-templates.json` (or the whole file) and reboot |
| Template unchanged since the copy | Nothing, edited or not |
| Template changed, file unedited | Replaced, no notice |
| Template changed, file edited | Your file is copied to `<name>.cfg.bak-<YYYYmmdd-HHMMSS>` (`-1`, `-2` added if that exists), then replaced; a line goes to `config-updates.txt` |
| File already equal to the new template | Only recorded |
| File present but not recorded (manifest lost) | Recorded as is, not touched; the next template change backs it up |
| Template dropped from the image | File and record kept |

Only `macros/*.cfg` are templates; the other files in the config
directory are never replaced. The date in a backup name is the printer's
clock at boot (it may be wrong before the network time is set; the
`-n` suffix keeps names unique).

Telling the user: at Klipper start, while `config-updates.txt` exists, its
lines go to the console (Fluidd, HelixScreen's console) and the screen
shows "Macros updated: see CONFIG_BACKUPS" (`M117`). `CONFIG_BACKUPS`
lists the notices and every `macros/*.bak-*` file; `CONFIG_BACKUPS
ACK=1` deletes the notice (backups stay). Status:
`printer.ad5x_config.notices`, `printer.ad5x_config.backups`.

Merging after an update: open the `.bak` file and the new file in
Fluidd (Configuration, `macros/`), copy your changes across (or, better,
put the variables you changed into `local.cfg`, where no update touches
them), `RESTART`, then delete the `.bak` file and `CONFIG_BACKUPS ACK=1`.

## Moving an existing printer to this layout

Nothing to do by hand. On the user's printer (files: `printer.cfg`
including `ad5x.cfg`, `unit.cfg`, `local.cfg`; `local.cfg` with
`nozzle_diameter: 0.6` and `[ifs] flush_speed: 480`; `ad5x-tuning.cfg`;
`plugins.cfg` with `zmod-compat` and `nopoop`; `variables.cfg` with
`zoffset` 0.085; `moonraker.conf`), the first boot of the new image:

1. `S05ad5x-data`: `printer.cfg` already includes `ad5x.cfg`, so it is
   not converted; the first-boot copies exist, nothing is copied.
2. `ad5x-config-templates` creates `macros/` with `print_start.cfg`,
   `prime_line.cfg`, `quick_actions.cfg`, `ifs_templates.cfg` and
   `.ad5x-templates.json`. No backups, no notice (nothing existed).
3. Klipper reads the new, smaller factory `ad5x.cfg`, then
   `ad5x-tuning.cfg`, then `macros/*.cfg` (which bring back everything
   that left the image: `PRINT_START` with its variables,
   `_PRINT_START_TOOL`, `_PRIME_LINE`, `LOAD_FILAMENT`,
   `UNLOAD_FILAMENT`, `CLEAR_NOZZLE`, `AUTO_FULL_BED_LEVEL`,
   `SETUP_WIZARD`, `[ifs] prime_gcode`), then `zmod-compat` and `nopoop`,
   then `unit.cfg`, then `local.cfg` (still last: the 0.6 nozzle and the
   flush speed win as before).
4. Unchanged: HelixScreen's buttons, `SETUP_WIZARD_STEP`, zMod files'
   `START_PRINT` -> `PRINT_START`, `END_PRINT`, swaps and their
   templates, `PRINT_END`, `CANCEL_PRINT`, `M106`/`M107`, `T0`-`T3`,
   the saved Z offset, the bed mesh in `printer.cfg`.
5. Changed on purpose: every print now meshes the print area first
   (below), the prime line primes more and sticks, and the screen shows
   each start step.

## Mesh every print and the Z offset

`PRINT_START` now probes a mesh of the print area every print
(`variable_mesh_every_print: 1`; zMod did the same with
`print_leveling: 1` and KAMP) instead of the stock check (probe the
centre, compare with the centre saved with an old full mesh, apply
nothing). `LEVEL=0` in a file, or `mesh_every_print: 0` in `local.cfg`,
goes back to the stock check; zMod files' `FORCE_LEVELING=1` makes a full
mesh, `FORCE_KAMP=1` the print area.

The Z offset: after the mesh `_APPLY_Z_OFFSET` sets the saved `zoffset`
(nothing added). The mesh and the probe use the same reference, so the
saved offset keeps its meaning: the nozzle-to-bed gap at the probe's
zero. What changes is that the mesh is now fresh, so bed movement since
the last full mesh no longer shows up in the first layer. With the old
mesh plus the "not applied" centre check that movement had to be tuned
away by hand: the user's offset went -0.36 -> -0.02 -> +0.085 over three
prints. The current 0.085 partly compensates the old mesh's error, so
**one small Z re-tune may be needed after this change** (baby-step in the
first print, or the setup wizard's Z offset step, which now also meshes
first). An adaptive mesh isn't saved as a profile (Klipper's rule), so the
full `default` mesh and its saved centre stay as they were; the saved
centre is only written by a full mesh into `default`.
