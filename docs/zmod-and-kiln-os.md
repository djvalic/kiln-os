# zMod and Kiln OS

Both projects give the Flashforge Adventurer 5X (AD5X) an open Klipper
setup. They take different routes:

- **zMod extends the stock firmware.**
- **Kiln OS replaces it.**

This page explains what that means in practice, and how much Kiln OS owes
to zMod.

> Neither project is affiliated with or endorsed by Flashforge. Both change
> the printer's software. Use either at your own risk.

## What Kiln OS owes to zMod

Kiln OS would look very different, and would have taken much longer,
without [zMod](https://github.com/ghzserg/zmod) by ghzserg. Before Kiln OS
existed, zMod had already shown that these printers could run a modern
Klipper with Fluidd or Mainsail, adaptive meshing, nopoop purging and a
plugin ecosystem. It had also worked out how the AD5X behaves day to day,
and gathered a community that knew how to use all of it.

Kiln OS builds on that work in many places:

- **The G-code people already have.** Slicer profiles made for zMod (and
  Bambufy's, which build on it) are what most AD5X owners print with. Kiln
  OS keeps zMod's macro names and behaviour so those files print unchanged:
  `START_PRINT`, `END_PRINT`, `_GOTO_TRASH`, `_SBROS_TRASH`,
  `SAVE_ZMOD_DATA`, the `use_trash_on_print` purge modes,
  `BED_LEVEL_SCREWS_TUNE`, `PLAY_MIDI` and more. zMod's behaviour is the
  reference for these macros; Kiln OS wrote its own versions of them
  ([zmod-compat.md](zmod-compat.md)).
- **Ideas and models.**
  - **Plugin root scripts:** they follow zMod's model (`install.sh`,
    `update.sh`, `uninstall.sh` run as root).
  - **The touch screen in the browser:** this follows zMod's screen view
    in Fluidd.
  - **Prime at the print from layer 2:** this nopoop behaviour follows
    zMod.
  - **KAMP:** zMod's handling of adaptive meshing and line purging guided
    how Kiln's print start does both.
- **Knowledge it published.** Kiln OS's recovery tools unpack Flashforge's
  update packages with the password the zMod project published.
- **A way in.** Many owners, and Kiln OS's own developers, first got root
  access to an AD5X through zMod. Kiln OS can be installed over SSH from a
  printer running zMod, but it doesn't need zMod or root: it also installs
  from stock firmware with a USB stick ([install.md](install.md)).
- **Moving over.** On a printer that ran zMod, Kiln OS reads zMod's plugin
  settings on its first start and turns on the matching plugins. zMod's
  files are left where they are.
- **The HelixScreen work.** HelixScreen's AD5X support grew up talking to
  zMod's IFS macros, and Kiln OS's HelixScreen patches still handle a
  printer that was set up under zMod.

Kiln OS's README credits zMod for exactly this. The point here is that
"credits" understates it: zMod defined what an open AD5X is expected to
do, and Kiln OS set out to keep that.

## The core difference

| | zMod | Kiln OS |
|---|---|---|
| Approach | Installed on top of the stock firmware, in a chroot started from stock's own start-up | Replaces the stock firmware with its own Linux system |
| Flashforge's software | Keeps running: the stock screen, the Flashforge app and Orca FF keep working | Not run. The few drivers and files it needs are copied from your own printer at install time |
| Klipper | Klipper v0.13 is optional; you can stay on the stock Klipper and board firmware | Klipper v0.13 is required, on the host and on both motion boards. Installing reflashes the mainboard and the eboard |
| IFS | Stock IFS firmware | Stock IFS firmware. Klipper firmware for the IFS is in development and opt-in |
| Kernel | The stock kernel | Its own Linux 6.6; mainline Linux 7.3 is opt-in |
| Touch screen | The stock screen, or GuppyScreen, HelixScreen or Rivet | HelixScreen, with Kiln patches |
| Updates | zMod updates itself on the running stock system | Each update replaces the whole system image, installed through a recovery OS, with a fallback if a start fails |
| Going back to stock | Remove zMod | A guided return to stock firmware |
| Printers | AD5M, AD5M Pro, AD5X, Creator 5, Creator 5 Pro | AD5X only |
| Maturity | Long-established, widely used, a large wiki in Russian and English, a help bot | Young: v1.0 is still in release candidates, with a small group of testers |

## Where zMod is the better fit

- **You want to keep the stock experience.** zMod leaves the stock screen,
  the Flashforge app and the stock features in place and adds to them. You
  choose how much of it to use.
- **You have more than an AD5X.** One project covers the AD5M, AD5M Pro,
  AD5X and Creator 5 series.
- **You want its ecosystem.** That includes remote access through
  zmod.link, Telegram and other notifications, nozzle collision detection
  with the load cells, power-loss recovery, input shaping and belt
  analysis, and many plugins.
- **You want something proven.** zMod has years of use behind it, broad
  documentation and an active community.
- **You want to keep the board firmware.** Klipper v0.13 is optional in
  zMod, so the motion boards can stay as Flashforge shipped them.
- **You want an easy way back.** Removing zMod returns the printer to its
  stock firmware, which was never replaced.

## Where Kiln OS differs

- **The whole system is open source.** No Flashforge user space runs, and
  the motion boards run Klipper v0.13 built from source. The IFS keeps
  Flashforge's firmware; Klipper firmware for it is in development and
  opt-in.
- **No stock screen to work around.** Flashforge's screen software
  doesn't run, so features don't have to stay compatible with it or
  share the printer with it. The screen, Klipper and the hardware setup
  can change together.
- **Recovery is built in.** Kiln OS has:
  - a recovery OS in a second slot;
  - starts that try once, then fall back if the new system doesn't come
    up;
  - backups and USB rescue;
  - with Kiln's optional boot loader, a network rescue that can reimage
    the eMMC.
- **Both motion boards are reflashed.** Kiln OS needs Klipper v0.13 on
  them and writes them with its own tools at install: the mainboard through the chip's ROM bootloader, the
  eboard through Flashforge's bootloader, which it never overwrites. A
  failed flash can be retried over serial.
- **Updates are whole images.** Each release is built and tested as one
  system, then installed from Fluidd.
- **Kernel work.** Kiln OS carries its own 6.6 kernel with built-in drivers
  (display, speaker, Wi-Fi, touch, the IFS's RS-485 port), and an opt-in
  mainline Linux 7.3 kernel.
- **Narrower and newer.** Kiln OS only targets the AD5X, and has far fewer
  users than zMod so far. Some zMod features have no Kiln OS counterpart
  yet ([zmod-compat.md](zmod-compat.md) lists them).

## Printing zMod G-code on Kiln OS

Files sliced with zMod's or Bambufy's AD5X profiles are meant to print
unchanged. Kiln OS maps zMod's commands to its own macros, and
[zmod-compat.md](zmod-compat.md) lists each one. A few behaviours differ on purpose,
for example:

- **Prime-only mode:** Kiln OS primes over the print from layer 2 only
  when the head is clear of the labelled objects. Otherwise it primes at
  the purge box.
- **Copying zMod's `KAMP/` folder doesn't work:** it depends on zMod-only
  macros, and Kiln OS's print start does the meshing and the prime line
  itself.

## Which one to choose

Choose **zMod** to extend the stock firmware, to keep Flashforge's screen
and app, to leave the board firmware alone, to run more than one
Flashforge model, or to use the most proven option.

Choose **Kiln OS** if you want an AD5X system that is open source from the
kernel up, with whole-image updates, a recovery OS and Klipper v0.13 on
both motion boards. It's young, so expect to be an early user.

Trying both is straightforward: Kiln OS installs from a printer running
zMod (over SSH) or from stock firmware (with a USB stick, no zMod or root
needed), and a printer that ran zMod moves over with its zMod plugin
choices.

## Links

- zMod: <https://github.com/ghzserg/zmod>, wiki <https://wiki.zmod.link/>
- Kiln OS: <https://github.com/djvalic/kiln-os>, zMod compatibility in
  [zmod-compat.md](zmod-compat.md), differences from stock in
  [deviations-from-stock.md](deviations-from-stock.md)
