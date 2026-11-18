# Repairing the eMMC over USB

The AD5X keeps everything on its eMMC: the boot loader, both system slots,
the boot flag, the factory data and `/data`. When the printer doesn't start
and the fallbacks don't help (the other slot, the recovery OS), a Linux PC
can repair the eMMC directly. The printer's boot ROM starts Kiln's
U-Boot over a USB cable, U-Boot shows the eMMC to the PC as a USB disk, and
`tools/ad5x_emmc_repair.py` checks it, backs it up and writes back what is
damaged.

This is bench work on the printer's mainboard. It is provided as is; you do
it at your own risk.

## What can be repaired

| Damaged | Repaired from | Notes |
|---|---|---|
| Boot loader (first MiB: SPL, U-Boot, GPT) | a release, or your backup | from a release: Kiln's SPL and U-Boot put into this printer's own first MiB (`boot.img`), see "The first MiB" below |
| Kernels (p1, p3) or system slots (p2, p4) | a release, or your backup | |
| Boot flag and U-Boot's records (p5, `ota`) | a release, or your backup | from a release: the flag on slot B, U-Boot's records and settings empty |
| `/data` (p7) | kept, or a new empty one | a new one loses settings, configs, G-code files and logs |
| Factory data (p6, `usershare`) | **only this printer's own backup** | no release has it |

Usershare holds what Flashforge wrote at the factory: the Ethernet
address (`/MAC`), the serial number, calibration data and stock's own
programs. Kiln OS reads the Ethernet address and stock's saved Wi-Fi
networks from it, and keeps its copy of the stock system there for the
way back to Flashforge firmware. **Back it up now, while the printer
works**: from Kiln OS's recovery OS (`ad5x-backup`, onto a USB stick), or
over USB as below (`backup`). Without a copy, a damaged usershare stays
damaged; Kiln OS still starts, with a random Ethernet address.

A failing eMMC chip can't be repaired this way. If `restore` reports that a
piece doesn't read back as written, the chip may be at the end of its life.

## What you need

- **A USB cable on J28**, the mainboard's 5-pin OTG header (JST PH):
  - D+, D- and GND to a USB-A plug;
  - 5 V left open, since the printer has its own supply;
  - newer boards ship without the connector fitted.

  Pinout and wiring are in `u-boot/USB-BOOT.md`, "What it needs".
- **A Linux PC** with:
  - Python 3 with pyusb (`python3 -m venv ~/.venv/usb && ~/.venv/usb/bin/pip install pyusb`);
  - e2fsprogs (`mke2fs`, `debugfs`, `e2fsck`, `resize2fs`);
  - root for the disk commands;
  - the udev rule from `USB-BOOT.md`, so the boot ROM's device (`a108:eaef`) can be used without root.
- **The release's rescue kit**, `kiln-os-VERSION-rescue.zip`. It holds this guide, the PC tools, and `boot/spl-usb2.bin` and `boot/u-boot.bin`, which start Kiln's U-Boot over USB. Run the commands below from the unpacked kit. From a repository checkout, the same tools are in `tools/` and `u-boot/tools/`, and `u-boot/build.sh` makes the two boot files.
- **The release's update zip**, `kiln-os-VERSION-update.zip`, to write a system. `ad5x_emmc_image.py` takes everything from it: the main OS, and the Kiln kernel, recovery OS, SPL and U-Boot it carries, each checked against the release's sha256s.

  ```
  python3 tools/ad5x_emmc_image.py --from-update kiln-os-VERSION-update.zip emmc-files/
  ```

  You need squashfs-tools (`unsquashfs`) for this. Use the release whose kit you have, or a newer one: the network rescue (below) needs a U-Boot that has it, and the tool refuses one that doesn't.
- **Optional:** the serial console on the DEBUG header (`serial-console.md`), to watch what the printer does.

## 1. Into the boot ROM's USB mode

Use whichever of these works for the printer's state:

- **Kiln OS still starts:** soft entry, no opening needed besides J28. As root on the printer:
  ```
  devmem 0x100000cc 32 0x42575302; reboot
  ```
  At Kiln's U-Boot prompt: `mw.l b00000cc 42575302; reset`.
- **The SPL on the eMMC is damaged:** the boot ROM finds no valid SPL and goes to USB mode by itself at power-on (alexshev86's test, #68).
- **Otherwise:** force it with the boot-select strap at power-on. Then power-cycle.
  - On the boards with K4: close K4.
  - On a newer board (FFP0302 V3.0.1), K4 didn't work. Grounding R91 during power-on did, on one unit; that needs checking on more boards (#68).
  - Open the strap again afterwards.

The PC then sees the boot ROM:

```
lsusb | grep a108          # ID a108:eaef Ingenic ... USB BOOT DEVICE
```

## 2. The eMMC as a USB disk

```
python3 u-boot/tools/ad5x_usbboot.py run-uboot boot/spl-usb2.bin boot/u-boot.bin
python3 tools/ad5x_emmc_repair.py find
# /dev/sda  58.2 GiB  AD5X eMMC over USB (Kiln's U-Boot)
```

The SPL sets up the RAM; Kiln's U-Boot then starts from the PC, offers the
eMMC (`UMS disk 0`) and writes nothing to it. `ad5x_emmc_repair.py` takes
only a disk that comes from Kiln's U-Boot (USB ID `1d6b:0104`, maker
"Kiln OS", U-Boot's ums product string), so it can't pick one of the PC's
own disks by mistake; with two such disks it asks for `--disk`.

**Unmount what the PC mounted.** A desktop mounts the printer's ext4
partitions (usershare, `userdata`) as soon as the disk appears. The tool
refuses a disk with anything of it mounted (`find` lists the mounts), and
opens it exclusively for writes:

```
udisksctl unmount -b /dev/sda6; udisksctl unmount -b /dev/sda7
```

The disk commands (`check`, `backup`, `restore`) need root.

Reads run at about 14 MB/s. About once per 1 to 2 GB a read fails its
CRC; U-Boot reads that piece again, and every write is read back.

## 3. Check

```
sudo python3 tools/ad5x_emmc_repair.py check --image emmc-files/
```

It reads only. One line for each of these:
- the boot ROM parameters, SPL and U-Boot;
- both GPTs;
- both kernels (uImage CRCs);
- both system slots (with `--image`, compared with the release's bytes);
- the boot flag;
- usershare (ext4, `/MAC`, `e2fsck -n`);
- `/data` (ext4 that fits its partition, `e2fsck -n`);
- where this printer's stock first MiB (`boot.img`) is, if anywhere.

`--deep` runs `e2fsck -f`. A healthy printer:

```
ok   GPT (primary)    good, stock's layout, p7 57.0 GiB
ok   SPL              Kiln's, 30 blocks
ok   p4 rootfs2       SquashFS, 90.8 MiB, the release's bytes
ok   p6 usershare     ext4 '', 1.0 GiB, /MAC 24:A1:0D:B8:5A:58; e2fsck -n: /dev/sda6: clean, ...
...
check: nothing found wrong
```

## 4. Back up first

```
sudo python3 tools/ad5x_emmc_repair.py backup /path/with/space
```

This copies the first MiB and p1–p6 (1.3 GB, about 90 s) into
`ad5x-backup-<date>-<n>/`, in the recovery OS's `ad5x-backup` format, and
reads each file back. `--userdata` also copies `/data` (the whole
partition: 57 GiB on a 58 GiB eMMC); on a FAT stick it is split into
1 GiB pieces (`userdata.img.000`, ...), as `ad5x-backup` does. Keep the
backup even when the printer is damaged: it holds this printer's usershare,
and its `boot.img` (the first MiB) when the printer still had Flashforge's
boot loader.

`MANIFEST.txt` has `ad5x-backup`'s format. A backup of a printer still on
stock can be given to Return to Flashforge firmware
(`ad5x-return-stock --source DIR`): it takes the slot the boot flag names.

## 5. Restore

See what would change first. Nothing is written with `--dry-run`:

```
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/ --dry-run
```

Then choose one of these:

```
# a release, keeping /data: the boot loader, both kernels, both system
# slots and the boot flag
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/

# the same, on a printer that still has Flashforge's boot loader: the
# release brings Kiln's own (see "The boot loader" below)
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/ --install-boot-loader

# only the system, under the boot loader and kernels that are there
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/ --parts p2,p4,p5

# a release with a new, empty /data (when /data is damaged too)
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/ --new-data

# your backup (the first MiB, p1-p5 as they are in it)
sudo python3 tools/ad5x_emmc_repair.py restore --backup ad5x-backup-.../

# your backup's usershare too
sudo python3 tools/ad5x_emmc_repair.py restore --backup ad5x-backup-.../ --usershare
```

Every restore follows the same rules:
- **What it writes:** pieces that already hold the same bytes are left alone. Each written piece is read back.
- **Order:** partitions first, the first MiB last (its SPL header sector last of all, so a cut leaves either a whole SPL or none, and the boot ROM goes to USB mode by itself), then the backup GPT.
- **Choosing pieces:** `--parts first-mib,p4` writes only the pieces named.
- **Confirmation:** it asks before writing; `--yes` skips the question.
- **Usershare:** it is written only with `--usershare`, and refused when the eMMC's own usershare is usable and has another `/MAC`. It needs `debugfs` to compare them.
- **`/data` is kept** unless you give `--new-data`: then the release's new, empty one (grown to its partition with `resize2fs`), or the backup's `userdata.img`. A new `/data` loses settings, configs, G-code files and logs; `boot.img` (below) is put back into it.
- **Another eMMC size:** a first MiB whose partition table is for an eMMC of another size (a backup of another printer, say) is refused.

### The first MiB

The boot loader installer and Return to Flashforge firmware both compare
the eMMC with this printer's first MiB as it was on stock: `boot.img`,
which Kiln OS saves to `/data/ad5x/stock` (and a copy in usershare's
`kiln-stock-backup/`). So `restore --image` doesn't write the release's
first MiB as it is: it puts Kiln's SPL and U-Boot into `boot.img`, the
same bytes `ad5x-bootloader-install` writes, and keeps its partition
table. It takes `boot.img` from, in this order:
- `--stock-mib FILE` (a `boot.img`, a folder with one, or a whole-eMMC dump);
- the eMMC itself, while it still has Flashforge's SPL;
- `/data/ad5x/stock/boot.img`, then usershare's `kiln-stock-backup/boot.img`;
- the image folder's `stock-boot.img` (`ad5x_emmc_image.py --stock-mib`).

Each is used only when its partition table is the eMMC's. Without one, the
eMMC's own first MiB is kept (its partition table and boot ROM block) with
the release's SPL and U-Boot in it; when that is unreadable too, the
release's generated first MiB is written, with a new partition table. Both
are said loudly: afterwards `ad5x-bootloader-install` can't upgrade the
boot loader and Return to Flashforge firmware can't put Flashforge's SPL
back, because there is no `boot.img` to compare with.

`--grow-data` stretches the partition table so userdata reaches the end of
the eMMC (stock's doesn't on 58 GiB eMMCs). It is opt-in for the same
reason: the eMMC then differs from `boot.img`, and the installer's upgrade
and `--flashforge-spl` refuse it.

### The boot loader

The release's first MiB and kernels are Kiln's own boot loader (Kiln's SPL
and U-Boot, Kiln's 6.6 in both kernel slots, `own-boot-loader.md`). The
rules are the recovery OS's (`ad5x-restore`):
- **Flashforge's SPL on the eMMC** (most printers): the first MiB and the kernels are refused unless you give `--install-boot-loader`. That is the same opt-in as the installer's, with its checks: this board's stock SPL must be on the allowlist of boards Kiln's boot loader is known to fit (`--unsupported-board` goes on anyway after a typed confirmation; an X2600E or the 2025 SPL isn't on it), and `boot.img` is saved to `/data/ad5x/stock` before anything else is written. The first MiB then goes before the kernels: Kiln's SPL starts Flashforge's 5.10 as well as Kiln's 6.6.
- **An SPL it can't read:** the kernel slots say which boot loader the printer had (Kiln's 6.6 in both: Kiln's; Flashforge's 5.10 in both: Flashforge's). With neither, `--install-boot-loader` is needed.
- **Under Kiln's SPL** only Kiln's 6.6 goes into a kernel slot; **under Flashforge's SPL** only Flashforge's 5.10.
- **Flashforge's first MiB back** (from a backup) only with Flashforge's 5.10 in both slots: `--parts first-mib,kernel,kernel2` from the same backup.

After a restore that kept `/data`, check the records in the recovery OS:
`ad5x-bootloader-install --status` and `ad5x-return-stock --status`. They
may describe the first MiB from before.

### /data

If `check` reports errors in `/data`, repair it from the PC before
starting the printer, with the disk `find` named (partition 7, after the
backup):

```
sudo e2fsck -p /dev/sda7       # -y for what -p won't fix on its own
```

## 6. Start the printer

Run `check` again, then:
1. Stop ums with Ctrl-C on the serial console, or unplug J28.
2. Open K4 or the strap if you closed it.
3. Power-cycle.

After a restore from a release, Kiln OS starts from slot B.

## With USBCloner: the first MiB, then the rest over Ethernet

When only Ingenic's USBCloner reaches the printer (on Windows, say), it
writes one small file: the first MiB with Kiln's SPL and U-Boot. This is
the same one-entry, 1 MiB write that restored a printer's boot loader
before (#68). Kiln's U-Boot then fetches the rest of the eMMC from a PC
on the printer's network, checks every piece and writes it. No serial
console is needed.

This writes Kiln's own boot loader (`own-boot-loader.md`) along with the
system.

1. **Make the files**, on any PC with Python 3 and e2fsprogs, giving the
   address of the PC that will serve them:

   ```
   python3 tools/ad5x_emmc_image.py --from-update kiln-os-VERSION-update.zip \
       --usershare ad5x-backup-.../ --usershare old-whole-emmc.img \
       --mac 24:A1:0D:12:34:56 \
       --rescue 192.168.1.10:8000 rescue-set/
   ```

   The server is the PC's IPv4 address (U-Boot resolves no names).

   The first MiB is built from this printer's `boot.img` when you have it:
   `--stock-mib boot.img`, or an `ad5x-backup` folder with one given as
   `--usershare`. The new `/data` then carries it in `ad5x/stock`, so the
   boot loader installer and Return to Flashforge firmware keep working.
   Without it the first MiB is a generated one (said loudly; see "The
   first MiB" above).

   The rescue writes usershare and a new `/data` too, unless:
   - `--keep-usershare` leaves the eMMC's usershare as it is (no `--usershare` or `--mac` then);
   - `--keep-data` leaves `/data` as it is; it needs `--stock-mib`, since the partition table written must be the eMMC's own.

   For usershare (p6), every `--usershare` you give is tried in turn:
   - an `ad5x-backup` folder, a `usershare.img`, or a whole-eMMC dump;
   - the first one that checks clean (`e2fsck -n`, a usable `/MAC`) is used.

   When none is usable (or none is given), a new usershare is made with
   the address given in `--mac`:
   - Use the printer's own address if you can find it: an old router lease, a log, a label.
   - `--mac random` picks a locally administered one.
   - The new usershare holds `/MAC` and empty `/config` and `/wifi`, in the factory's ext4 format. Flashforge's firmware can't run from it.

   `tools/ad5x_usershare.py check SOURCE...` shows what each source holds before you build.

   `--rescue-ip 192.168.1.50/255.255.255.0` gives the printer a fixed address
   instead of DHCP.
2. **Serve them** from that PC, on that address only:

   ```
   python3 -m http.server 8000 --bind 192.168.1.10 --directory rescue-set/
   ```

   While it runs, anyone on that network can fetch the set: usershare
   (with the saved Wi-Fi passwords and stock's root password hash) and
   `boot.img` among it. Use a network you trust, and **stop the server
   (Ctrl-C) and delete `rescue-set/` when the rescue is done**.
3. **USBCloner** writes `rescue-set/rescue-first-mib.bin` at offset 0
   with the settings in `rescue-set/RESCUE.txt`: one policy, ops MMC0,
   force erase None, readback on.
4. **Power off and on.** Kiln's U-Boot finds the rescue record in the
   first MiB's last sector and then:
   - sets the watchdog to 900 s for each step (a hang is a reset, and a try);
   - gets an address;
   - fetches `rescue/rescue.scr` and checks it against the SHA-256 in the record.

   The script then takes each 32 MiB piece in turn: it fetches it (three
   tries), checks its SHA-256, writes it, and checks what reads back. The
   normal first MiB comes last and clears the record. The printer resets
   and Kiln OS starts from slot B.

   If anything fails, or the server isn't there, U-Boot resets after 10 s
   and starts the rescue again: three times in all, each start counted in
   the record first. Then it starts as without it; the record stays
   (`ad5x_rescue` at the U-Boot prompt shows it) until a rescue finishes,
   `ad5x_rescue clear`, or a new first MiB. A rescue that hangs is reset by
   the watchdog. To follow it on the serving PC, run
   `tools/ad5x_netconsole.py` there (see Netconsole below). The server log
   also shows each piece as it is fetched.
5. **Afterwards** a new `/data` is small (64 MiB) in its partition. Over
   USB, `restore --image rescue-set/ --new-data` gives a new one the whole
   partition; it is empty either way.

Tried on hardware once: printer 2 (X2600E), with the first MiB written over
ums instead of USBCloner (591 s from the reset to Kiln OS started). Not
tried yet: USBCloner itself, an X2600H, a failure part-way, and the loop
with no server.

## Netconsole: U-Boot's console without a serial cable

Kiln's U-Boot can send its console over the network: you see what it does
at every start (the boot rules, which kernel). Switch it on from Kiln OS,
as root, then restart the printer:

```
echo 192.168.1.10 > /data/ad5x/netconsole   # this PC's IP
```

On the PC:

```
python3 tools/ad5x_netconsole.py            # or: nc -u -l -p 6666
```

What happens at each start:
- U-Boot brings the Ethernet link up and gets an address by DHCP. DHCP gives up after 10 s; without an address, the start goes on as usual. On my printer the start took 1 to 12 s longer than without netconsole (three starts), most of it waiting for the link.
- The console then goes to UDP port 6666 on the PC, output only.

Keys from the network (the stop key and the U-Boot prompt) need a second
file, and come only from that one PC's address:

```
touch /data/ad5x/netconsole-input
```

Then Ctrl-C in `ad5x_netconsole.py` within the first 2 seconds gives the
U-Boot prompt, with the watchdog off; a prompt reached that way resets
the printer after 300 s idle, so a start stopped from the network goes on
by itself. `reset` starts normally at once.

Other settings:
- An empty file sends to the whole network instead, output only (keys never come from a broadcast address). Where the PC is on Wi-Fi, part of the output gets lost that way (access points pass broadcasts slowly), so give the PC's IP when you can.
- Nothing of it is kept in U-Boot's environment: a `saveenv` at the prompt changes no later start.
- `rm /data/ad5x/netconsole /data/ad5x/netconsole-input` switches it off.

The network rescue (above) always sends its console to the PC that serves
it, output only: start `ad5x_netconsole.py` there to follow it.

## Other ways in

- **Ethernet in U-Boot:** at Kiln's U-Boot prompt, a file can come over the network instead (`dhcp`, `wget`, `hash -v sha256`; `u-boot/README.md`, U-Boot proper).

## Tested

On printer 2 (X2600E, 58 GiB eMMC), over USB from a Linux PC:
- `find`, `check`, `backup` and both `restore --dry-run` paths;
- a whole image written and read back;
- the printer started from it.

`tools/test_ad5x_emmc_repair.py` runs every command on an eMMC image file, with damage to:
- the SPL header;
- the GPT;
- a kernel;
- a system slot;
- usershare;
- an old backup's partition table.

It also covers a printer on Flashforge's SPL (the boot loader rules,
`boot.img` saved first, the first MiB checked with `lib/bootloader.sh`,
the installer's upgrade check and Return to Flashforge firmware's), and the
refusals: another kind of disk, two printers, a mounted partition, another
printer's `/MAC`, no `debugfs`, an eMMC of another size.
`tools/test_ad5x_rescue.py` replays the rescue script against an image
file. The builder runs both.

A full restore with a new `/data` was also run against a loop device (before
the fixes ported with it), which exercises the `resize2fs` step.

Not yet done on hardware: repairing a deliberately broken printer from the
boot ROM's automatic USB mode.
