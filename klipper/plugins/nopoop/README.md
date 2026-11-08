# nopoop

zMod's purge modes for colour changes during a print. Slicer profiles for
zMod's nopoop / slicer-controlled purge set the mode in their start
G-code:

    SAVE_VARIABLE VARIABLE=use_trash_on_print VALUE=0

(`SAVE_ZMOD_DATA USE_TRASH_ON_PRINT=0`, zMod's way, does the same with the
`zmod-compat` plugin.)

- `0`: the prime tower takes the purge ("nopoop").
- `2`: the slicer flushes at the purge box itself (`_GOTO_TRASH`,
  `G1 E...`, `_SBROS_TRASH`).
- `1` or not set: the printer purges at the box, as without this plugin.

With `0` or `2` a tool change still cuts, unloads and loads the new
filament, then fills the nozzle (`prime_length`, 12 mm, in `[ifs]`) at
the purge box and wipes, without purge rounds. Swaps outside a print
always purge. Tune `prime_length` in `local.cfg` (`[ifs]`): thin first
tower lines, raise it; blobs on the tower, lower it.

With `0`, from layer 2 on, a change doesn't go to the box, as on zMod: it
cuts, goes back to the prime tower (where the print stopped, at print
Z), unloads, loads and fills the nozzle there, flattens the bead with a
small square move and goes on (`prime_at_print: True`, set by this
plugin). It only does that when the file reports its layers
(`SET_PRINT_STATS_INFO`), labels its objects, and the head is at least
5 mm away from every object; otherwise that change uses the box. To keep
every change at the box, put this in `local.cfg`:

    [ifs]
    prime_at_print: False

With `0` or `2`, `PRINT_START` doesn't purge at the box at the start: the
prime line flushes the nozzle (`docs/print-start.md`). Set the variable
before `PRINT_START` in the start G-code.

Enabled by default (nothing changes until a file sets the variable).
Mode numbers and idea: zMod, ninjamida's nopoop and QuickSwap.
