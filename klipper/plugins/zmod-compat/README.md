# zmod-compat

Lets G-code and slicer profiles made for zMod print on this system. zMod's
macro names and parameters, mapped onto this system's own macros:

| zMod | Here |
|---|---|
| `START_PRINT EXTRUDER_TEMP= BED_TEMP=` (`FORCE_LEVELING`, `FORCE_KAMP`, `TOOL=`) | `PRINT_START`, then `LINE_PURGE`; a missing temperature: the one the file already set, else 245 / 80 |
| `END_PRINT` | `PRINT_END` (optional IFS unload first) |
| `_GOTO_TRASH`, `_SBROS_TRASH` | into the purge box / wipe on its edge |
| `_DISABLE_SENSOR`, `_ENABLE_SENSOR` | toolhead runout sensor off / back on |
| `TIMELAPSE_TAKE_FRAME` | nothing (moonraker-timelapse replaces it) |
| `SET_ACTIVE_SPOOL`, `CLEAR_ACTIVE_SPOOL` | Spoolman, once set up |
| `SET_PAUSE_NEXT_LAYER`, `SET_PAUSE_AT_LAYER`, `M600` | pause at a layer, filament change |
| `LINE_PURGE`, `LED_ON`, `LED_OFF`, `LED`, `M300` | prime line, chamber light, beep (none) |

`TOOL=` (Bambufy's start G-code) must be a whole number or -1, as in
`PRINT_START`. Anything else loads no tool and the console shows an error:
an unexpanded `TOOL=[initial_tool]` (it used to load tool 0, issue #12), and
an empty `TOOL=`, which used to load tool 0 and now loads none. No `TOOL=`
loads none.

Enabled by default. Full table and settings: `docs/zmod-compat.md`.
Pair with the `nopoop` plugin for zMod's prime-tower and slicer-purge
modes. Command names follow zMod (ghzserg/zmod); the macros are written
for this project.
