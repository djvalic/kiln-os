# zmod-compat

Lets G-code and slicer profiles made for zMod print on this system. zMod's
macro names and parameters, mapped onto this system's own macros:

| zMod | Here |
|---|---|
| `START_PRINT EXTRUDER_TEMP= BED_TEMP=` (`FORCE_LEVELING`, `FORCE_KAMP`, `TOOL=`) | `PRINT_START` (which draws the prime line); `LINE_PURGE` after it only when that line is off (`variable_prime_line: 0`); a missing temperature: the one the file already set, else 245 / 80; one that is not a number (an unexpanded placeholder), a nozzle outside 170-350 C or a bed above 130 C stops the start with an error (bed 0 = off is accepted) |
| `END_PRINT` | `PRINT_END` (optional IFS unload first) |
| `SAVE_ZMOD_DATA USE_TRASH_ON_PRINT=0|1|2` | the purge mode (`use_trash_on_print`, read by the `nopoop` plugin); other zMod settings: a line says where they are here, nothing saved |
| `_GOTO_TRASH`, `_SBROS_TRASH` | into the purge box / wipe on its edge |
| `_DISABLE_SENSOR`, `_ENABLE_SENSOR` | toolhead runout sensor off / back on |
| `TIMELAPSE_TAKE_FRAME` | nothing (moonraker-timelapse replaces it) |
| `SET_ACTIVE_SPOOL`, `CLEAR_ACTIVE_SPOOL` | Spoolman, once set up |
| `SET_PAUSE_NEXT_LAYER`, `SET_PAUSE_AT_LAYER` | pause at a layer |
| `M600` | filament change: pause, Z +50 mm (the bed lowers), wait at the purge box; `RESUME` comes back with the bed still lowered (Y, then X), then raises the bed back over the print. The plugin's `PAUSE`/`RESUME` add only that; other pauses resume as without the plugin |
| `LINE_PURGE` | prime line; during a print skipped once `PRINT_START` has drawn its prime line, `LINE_PURGE FORCE=1` draws anyway |
| `LED_ON`, `LED_OFF`, `LED`, `M300` | chamber light, beep (none) |
| `NOZZLE_CONTROL WEIGHT=<g>` | the `nozzle-guard` plugin's limit and the guard on (`NOZZLE_GUARD ENABLE=1 THRESHOLD=<g>`); `WEIGHT=0` turns it off; no restart |
| `ZCONTROL_ON`, `ZCONTROL_PAUSE`, `ZCONTROL_AUTO`, `ZCONTROL_ABORT` / `ZCONTROL_OFF` / `ZCONTROL_STATUS` | `NOZZLE_GUARD ARM=1` / `ARM=0` / report; a hit always pauses (bed stays hot), Klipper is never stopped |
| `ZCONTROL_Z`, `SAVE_ZMOD_DATA ZCONTROL_Z=` | accepted, a line, no effect |

`TOOL=` (Bambufy's start G-code) must be a whole number or -1, as in
`PRINT_START`. Anything else loads no tool and the console shows an error:
an unexpanded `TOOL=[initial_tool]` (it used to load tool 0, issue #12), and
an empty `TOOL=`, which used to load tool 0 and now loads none. No `TOOL=`
loads none.

The nozzle commands need the `nozzle-guard` plugin (off by default); with
it off each shows one line and the file goes on printing.

Enabled by default. Full table and settings: `docs/zmod-compat.md`.
Pair with the `nopoop` plugin for zMod's prime-tower and slicer-purge
modes. Command names follow zMod (ghzserg/zmod); the macros are written
for this project.
