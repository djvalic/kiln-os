# Repairing the eMMC over USB

The AD5X keeps everything on its eMMC: the boot loader, both system slots,
the boot flag, the factory data and `/data`. When the printer doesn't start
and the fallbacks don't help (another slot, safe mode, the recovery OS), a
Linux PC can repair the eMMC directly. The printer's boot ROM starts Kiln's
U-Boot over a USB cable, U-Boot shows the eMMC to the PC as a USB disk, and
`tools/ad5x_emmc_repair.py` checks it, backs it up and writes back what is
damaged.

This is bench work on the printer's mainboard. It is provided as is; you do
it at your own risk.

## What can be repaired

| Damaged | Repaired from | Notes |
|---|---|---|
| Boot loader (first MiB: SPL, U-Boot, GPT) | a release, or your backup | |
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
  - e2fsprogs (`debugfs`, `e2fsck`);
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
"Kiln OS"), so it can't pick one of the PC's own disks by mistake.

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
- `/data` (ext4 that fits its partition, `e2fsck -n`).

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
partition: 57 GiB on a 58 GiB eMMC). Keep the backup even when the printer
is damaged: it holds this printer's usershare.

## 5. Restore

See what would change first. Nothing is written with `--dry-run`:

```
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/ --keep-data --dry-run
```

Then choose one of these:

```
# a release, keeping /data: the boot loader, both kernels, both system
# slots and the boot flag; /data gets the rest of the eMMC in the new GPT
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/ --keep-data

# a release with a new, empty /data (when /data is damaged too), grown
# to the end of the eMMC on the PC (resize2fs)
sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/

# your backup (the first MiB, p1-p5; /data when the backup has it)
sudo python3 tools/ad5x_emmc_repair.py restore --backup ad5x-backup-.../

# your backup's usershare too
sudo python3 tools/ad5x_emmc_repair.py restore --backup ad5x-backup-.../ --usershare
```

Every restore follows the same rules:
- **What it writes:** pieces that already hold the same bytes are left alone. Each written piece is read back.
- **Order:** partitions first, the first MiB last, then the backup GPT. A restore cut short leaves the old boot loader and partition table.
- **Choosing pieces:** `--parts first-mib,p4` writes only the pieces named.
- **Confirmation:** it asks before writing; `--yes` skips the question.
- **Usershare:** it is written only from a backup and only with `--usershare`, and refused when the backup's `/MAC` differs from the eMMC's.
- **`/data`:** if `/data` on the eMMC has grown larger than userdata in an older backup's partition table, userdata is extended to the end of the eMMC instead of being cut short.

`--keep-data` keeps `/data` as it is. If `check` reports errors there,
repair it from the PC before starting the printer, with the disk `find`
named (partition 7, after the backup):

```
sudo e2fsck -p /dev/sda7       # -y for what -p won't fix on its own
```

In safe mode Kiln OS also runs `e2fsck -p` on `/data` before mounting it.

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

1. **Make the files**, on any PC with Python 3 and e2fsprogs, giving the
   address of the PC that will serve them:

   ```
   python3 tools/ad5x_emmc_image.py --from-update kiln-os-VERSION-update.zip \
       --usershare ad5x-backup-.../ --usershare old-whole-emmc.img \
       --mac 24:A1:0D:12:34:56 \
       --rescue 192.168.1.10:8000 rescue-set/
   ```

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
2. **Serve them** from that PC:

   ```
   python3 -m http.server 8000 --directory rescue-set/
   ```
3. **USBCloner** writes `rescue-set/rescue-first-mib.bin` at offset 0
   with the settings in `rescue-set/RESCUE.txt`: one policy, ops MMC0,
   force erase None, readback on.
4. **Power off and on.** Kiln's U-Boot finds the rescue record in the
   first MiB's last sector and then:
   - turns the watchdog off;
   - gets an address;
   - fetches `rescue/rescue.scr` and checks it against the SHA-256 in the record.

   The script then takes each 32 MiB piece in turn: it fetches it (three
   tries), checks its SHA-256, writes it, and checks what reads back. The
   normal first MiB comes last and clears the record. The printer resets
   and Kiln OS starts from slot B.

   If anything fails, U-Boot resets after 10 s and starts the rescue
   again. To follow it on the serving PC, run `tools/ad5x_netconsole.py` there (see Netconsole below). The server log also shows each piece as it is fetched.
5. **Afterwards** `/data` is small (64 MiB). To give it the rest of the eMMC, run `restore --image rescue-set/ --keep-data` over USB.

Not tried yet on hardware: the rescue run itself (simulated by
`tools/test_ad5x_rescue.py`), and USBCloner on an X2600E (256 MiB) printer.

## Netconsole: U-Boot's console without a serial cable

Kiln's U-Boot can send its console over the network, and take keys back:
- you see what it does at every start (the boot rules, which kernel);
- you can stop it with Ctrl-C and use the U-Boot prompt from a PC.

Switch it on from Kiln OS, as root, then restart the printer:

```
echo 192.168.1.10 > /data/ad5x/netconsole   # this PC's IP
```

On the PC:

```
python3 tools/ad5x_netconsole.py            # or: nc -u -l -p 6666
```

What happens at each start:
- U-Boot gets an address by DHCP. That takes milliseconds, at most 10 s; without one, the start goes on as usual.
- The console then goes to UDP port 6666 on the PC.
- Ctrl-C within the first 2 seconds gives the U-Boot prompt, with the watchdog off; `reset` starts normally again.

Other settings:
- An empty file sends to the whole network instead. Where the PC is on Wi-Fi, part of the output gets lost that way (access points pass broadcasts slowly), so give the PC's IP when you can.
- At the U-Boot prompt, `setenv ad5x_nc 192.168.1.10; saveenv` does the same as the file.
- `rm /data/ad5x/netconsole` switches it off.

The network rescue (above) always sends its console to the PC that serves
it: start `ad5x_netconsole.py` there to follow it.

## Other ways in

- **Ethernet in U-Boot:** at Kiln's U-Boot prompt, a file can come over the network instead (`dhcp`, `wget`, `hash -v sha256`; `u-boot/README.md`, U-Boot proper).

## Tested

On printer 2 (X2600E, 58 GiB eMMC), over USB from a Linux PC:
- `find`, `check`, `backup` and both `restore --dry-run` paths;
- the whole A/B image written and read back;
- the printer started from it.

`tools/test_ad5x_emmc_repair.py` runs every command on an eMMC image file, with damage to:
- the SPL header;
- the GPT;
- a kernel;
- a system slot;
- usershare;
- an old backup's partition table.

A full restore with a new `/data` was also run against a loop device, which exercises the `resize2fs` step.

Not yet done on hardware: repairing a deliberately broken printer from the
boot ROM's automatic USB mode.
