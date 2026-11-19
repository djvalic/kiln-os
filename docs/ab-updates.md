# A/B updates (prototype, for 2.0)

> Opt-in and experimental. It changes how the printer starts and replaces
> the recovery OS. Use it at your own risk, with a serial console and a
> backup of the eMMC (`ad5x-backup` in the recovery OS) at hand.

In 1.x's layout slot A holds the recovery OS and slot B the main OS, and an
update goes through the recovery OS into slot B. In the A/B layout both
slots hold the main OS: an update is written into the slot that isn't
running while the printer runs, and U-Boot goes back to the slot before if
the new one doesn't finish starting.

This follows the usual SWUpdate setup on U-Boot (#83): SWUpdate installs,
U-Boot's own boot count guards the update.

## What it needs

- Kiln's boot loader from this release (`u-boot/` patch 0051), installed
  with `ad5x-bootloader-install`. It says on the command line that it knows
  A/B: `ad5x.ab=-` in 1.x's layout, `ad5x.ab=a` or `ad5x.ab=b` in A/B.
  Printers on Flashforge's boot loader, or an older Kiln U-Boot, stay on
  1.x's layout.
- A main OS from this release in slot B.

## How an update goes

1. `ad5x-update FILE` (or the update agent) sees `ad5x.ab=a|b` and packs a
   `.swu` from the update's `rootfs.squashfs`, streamed from the `.zip`
   (`ab-pack.py`): `/data` needs room for the update and the `.swu`.
2. SWUpdate writes it into the other slot's root partition, checking its
   sha256 as it streams. `ad5x-ab.sh` reads it back, checks it is Kiln's
   main OS and puts its 6.6 into the slot's kernel partition (header last).
3. Only then does SWUpdate set U-Boot's environment, in one write:
   `kiln_slot` (the new slot), `upgrade_available=1`, `bootcount=0`. It
   also keeps its own markers there: `recovery_status` while it installs,
   `ustate=1` after.
4. At the next start U-Boot starts the new slot and counts the start in
   `bootcount`. Once start-up has finished, `S99ad5x-booted` sets
   `upgrade_available`, `bootcount` and `ustate` back to 0 (`fw_setenv -s`,
   one write), and the new slot is kept.
5. If the new slot doesn't finish starting `bootlimit` (2) times, U-Boot
   runs `altbootcmd` (`ad5x_boot alt`): back to the slot before, with
   `ustate=3` (failed) and fresh state and records in `ota` (they counted
   the other slot's starts). The slot before says so at start-up and keeps
   `ustate=3` until the next update.

U-Boot also goes back when an install was cut off after it changed
`kiln_slot` (`recovery_status` still set with an update pending), and
doesn't fall back to a slot whose install is unfinished or failed
(`recovery_status` set without one). Within a slot the 1.x rules still
pick the kernel (7.3, then 6.6). Where 1.x would start the recovery OS
(no kernel left), A/B starts the other slot instead.

## Converting a printer

From the main OS in slot B, with the boot loader above:

```
ad5x-update --ab --reboot kiln-os-update.zip
```

This writes the main OS into slot A over the recovery OS and starts it.
If it doesn't finish starting twice, U-Boot goes back to slot B. From then
on the printer is A/B: the recovery OS jobs (`S99ad5x-install-recovery`,
`S99ad5x-update-recovery`) stay off, and later updates alternate slots.

There is no way back to 1.x's layout from the printer yet: putting the
recovery OS back into slot A means `ad5x-update --install-recovery`, which
this layout refuses, or a reimage (`tools/ad5x_emmc_image.py`, the rescue
kit).

## Tested

On printer 2 (X2600E, A31M8C), 2026-11-19, with this branch's U-Boot and
main OS:

- 1.x's layout under the new U-Boot: starts as before, `ad5x.ab=-`.
- Converting with `ad5x-update --ab`: slot A written, started with the
  boot count running, confirmed; the recovery OS jobs stay off.
- A/B updates A -> B and B -> A, each confirmed and read back as 0.
- A U-Boot update while an update was pending: `kiln_slot` and the count
  kept.
- A slot that never finishes starting (its `S99ad5x-booted` stubbed out):
  started twice, then `altbootcmd` back to the other slot, `ustate=3`,
  fresh state and records, no kernel recorded as failed.
- An install cut off after `kiln_slot` changed (`recovery_status`
  `in_progress` with `upgrade_available=1`): back to the other slot.
- A good install after both clears `ustate` and `recovery_status`; a cold
  start from the plug starts the confirmed slot.

## Looking at the state

```
fw_printenv kiln_slot upgrade_available bootcount bootlimit ustate recovery_status
cat /proc/cmdline        # ad5x.ab=a|b
```

At the U-Boot prompt: `printenv kiln_slot bootcount`, and `ad5x_boot -n`
shows what the next start takes and why.

## Not in this yet

- Safe mode and the network rescue as the last steps (#76 has a
  prototype of safe mode).
- All of the RAM for the kernel, and growing `/data` (#76).
- Signed updates: SWUpdate checks each image's sha256; signing is off, as
  in the recovery OS.
