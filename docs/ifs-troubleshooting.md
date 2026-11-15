# IFS troubleshooting

The IFS (4-colour filament system) talks to the printer over a serial link.
If the link drops, for example from a loose cable or after a replug, the
printer keeps trying to reconnect on its own, every 10 seconds, so no restart
is needed for a brief drop.

The IFS is shown as **not available** (`printer.ifs.error` and the IFS panel
show the reason) until it answers again.

## If the IFS does not come back in line

1. Check the cable between the IFS and the printer. Make sure it is seated at
   both ends.
2. Wait about 30 seconds after reseating the cable. The printer retries on its
   own.
3. If it still does not come back, reboot the printer.
4. If it is still not connected after a reboot, check the error text in the
   IFS panel. It gives the port and the reason. Report it with the Klipper log
   (`klippy.log`).
