# bambufy-compat

G-code from Bambufy's slicer profiles (Bambufy is a zMod plugin) calls two
macros beyond zMod's:

- `_NOPOOP` before `T<n>` when the prime tower purges: that tool change
  only fills the nozzle (as the `nopoop` plugin's mode 0, for one change).
- `_M106 FAN_MAX_SPEED=` sets the part fan during its flushes (percent x
  `factor`, 0.5 as Bambufy).

Needs `zmod-compat` (START_PRINT, END_PRINT, _GOTO_TRASH, _SBROS_TRASH).
Works together with `nopoop`. Its `T0`-`T3` drive Kiln's IFS module: not
for use with a plugin that drives the IFS itself (`owns_ifs`,
`docs/plugin-api.md`); enabled after one, they replace its `T0`-`T3` and
stop with a message at the first tool change. Bambufy's own colour
mapping dialogs, port sensors and `POOP` are not part of it. Tool changes without
`_NOPOOP` (Bambufy's "poop mode", prime tower off) also get this
system's purge at the box on top of the slicer's flush; to skip it, add
`SAVE_VARIABLE VARIABLE=use_trash_on_print VALUE=2` to the profile's
start G-code (needs `nopoop`).
