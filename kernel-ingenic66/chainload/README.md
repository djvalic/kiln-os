# chainload: test-boot a kernel from RAM, no cables

Boots the 6.6 test kernel (`../build.sh` output) from the running stock
5.10 kernel without writing the eMMC or the boot flag. If the test kernel
hangs, a power cycle boots the installed system as before. The stock kernel
has no kexec, so this is a minimal one: a module that stages the image and
argv in RAM, shuts devices down (`kernel_restart_prepare`, address from
`/proc/kallsyms`), and enters a small trampoline that copies the image to
0x80f00000, flushes L1/L2 and jumps there with argc/argv like the stock SPL.

**Status: works.** First run 2026-10-17: the 6.6 kernel was up on SSH
34 s after the jump; `reboot` from it returns to the installed system. On
6.6: both cores, RAM, eMMC, ttyS0/2/3/4/5/7, Ethernet, both USB buses
(cameras, hub, Wi-Fi adapter), touch (tsc2007) and keys worked. Not yet:
Klipper/Moonraker (no `FILE_LOCKING` in the SDK defconfig, fixed), the
screen (panel driver didn't bind; boot log was lost in a 16 KiB buffer,
now 128 KiB), Wi-Fi (rtw88 firmware not in the rootfs).

First attempt crashed the stock kernel while staging: the header tree had
16 KiB pages, stock has 4 KiB (`setup.sh` now matches). It came back on
its own (stock `panic=10`).

Second run (file locking, 128 KiB log): **Klipper ready on 6.6**, both
MCUs connected, the IFS answering over RS-485 through `patches/0002`
(`IFS 3.0.7: state 5 (ready)`, filament in all four slots), no
retransmits. The screen: DPU and LVDS PHY came up (31.1 MHz), then the
4.6 MB framebuffer allocation failed; CMA (32 MiB) added for the next run.

Third run (CMA): `/dev/fb0` 800x480x32 with 3 frames in CMA, kernel console
readable through the screen stream; the panel lit with a stable, synced
picture but horizontal noise. HelixScreen had no draw buffer: the rotator
support pads lines to 3584 bytes and LVGL reads that as 35 bpp.
`patches/0003` drops the padding.

Fourth run: **HelixScreen shows normally on the panel** (stride 3200,
ARGB8888). Touch still needs a calibration for the mainline tsc2007 range
(0-4095, stored calibration is from stock's driver).

## Build

```
kernel-ingenic66/chainload/setup.sh      # linux-5.10.186 with stock's module ABI
make -C kernel-ingenic66/chainload       # chainload.ko
```

## Module ABI check (against Flashforge's own modules for this kernel)

| | stock modules (all 21) | chainload.ko |
|---|---|---|
| vermagic | `5.10.186+ SMP preempt mod_unload MIPS32_R5 32BIT` | same |
| `.gnu.linkonce.this_module` | 0x180, init 0xe0, exit 0x16c | same (needs `DEBUG_SPINLOCK`, which stock has) |
| `__versions` | none | none |
| imports | | all 21 exported by the stock kernel (checked in the stock image: a ksymtab pointer to each name string) |

The module touches no config-dependent kernel structs (file size comes from
reading to end of file, not `struct inode`).

## Memory

Both kernels are zboot images loaded at physical 0x00f00000. The zboot
clears its bss on entry and uses a heap and stack there before the new
kernel reads its argv:

| | image | bss, heap and stack to | kernel decompressed to |
|---|---|---|---|
| 6.6 | to 0x01498000 | about 0x014b2450 | 0x00010000-0x00d31900 |
| 7.3.3 | to 0x014da3a0 | 0x019dc3b0 (1 MiB `.appended_dtb` gap, 4 MiB heap) | 0x00100000-0x00e3be70 |

Staged pages, page list, argv and trampoline are all above physical
0x02000000 (`SAFE_MIN`) and below 0x0ec00000. That is above an 8 MiB image
with mainline's bss (0x01c02010), so neither the copy nor the zboot
overwrites what the next step still needs. Until 2026-11-12 the limit was
0x01600000, below the end of 7.3's bss: an argv page placed there would have
been cleared and 7.3 would hang before its console (never seen).
`kernel-mainline/build.sh` fails a build whose zboot ends above `SAFE_MIN`.

## Test on the printer

```
mkdir -p /data/ad5x/chainload        # chainload.ko, chainload.sh, xImage
chainload.sh stage                   # harmless: loads, stages, prints
chainload.sh unstage                 # or: chainload.sh go (no return)
```

`go` stops services, unbinds USB, downs and unloads the network drivers
(they do DMA into RAM), offlines cpu1, syncs and remounts `/data` read-only,
then jumps. SSH drops. Watch the LCD (boot messages via fbcon) and wait for
SSH from the 6.6 kernel. Command line: stock's, plus `console=tty0` and
`root=PARTLABEL=rootfs2` (same system; `slot.sh` then sees no slot, so the
boot flag is never written).

Recovery: power cycle. Stock's watchdog is loaded disabled, so a hang is
not reset automatically.

## Risks

- A reboot notifier or device shutdown in stock's out-of-tree drivers might
  reset the board: the test simply ends in a normal boot.
- Cache flush assumes Config1/Config2 describe L1 and L2 (index ops).
- cpu1 is offlined by stock; the 6.6 SMP code resets and restarts it.
- The 6.6 system writes `/data` (ext4, journaled) like any boot.

## At boot (S00ad5x-kernel)

The stock kernel starts ours at every boot (S00ad5x-kernel); ours
starts the display itself. Until 2026-10-17 a cold start of our display
driver left the LVDS panel in its no-signal self-test, and S00 first
brought the display up with stock's driver. The cause was in Ingenic's
6.6 driver (fbcon panned before probe had configured the DPU and started
the read DMA into it); fixed by kernel-ingenic66/patches/0004-0007, see
patches-experimental/README.md.
