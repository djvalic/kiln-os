# nozzle-guard

Pauses the print when the nozzle hits the print or the bed. The bed
weighing board is read 5 times a second during a print; a push over the
limit (300 g by default) for 3 readings in a row pauses the print, with
the reason on the screen. The bed stays hot.

Shipped with Kiln OS, off by default. Turn it on in Settings > Safety &
Alerts on the touch screen, or `ENABLE_PLUGIN NAME=nozzle-guard`.

- `NOZZLE_GUARD ENABLE=0|1`: on/off without a restart
- `NOZZLE_GUARD SENSITIVITY=low|medium|high` (600 / 300 / 150 g) or
  `THRESHOLD=<g>`: saved in variables.cfg
- `NOZZLE_GUARD`: the state and the largest push of this print

Armed by `PRINT_START` after its homing, probing and purge; not watching
while homing or probing, during an IFS colour change or while paused.
Details: docs/nozzle-guard.md in the Kiln OS repository. Idea from zMod's
NOZZLE_CONTROL; zmod-compat maps its commands here.
