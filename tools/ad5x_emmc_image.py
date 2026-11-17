#!/usr/bin/env python3
"""Make the files to flash a whole AD5X eMMC over USB (USBCloner, or a
host that sees the eMMC as a disk), from release images only.

    ad5x_emmc_image.py --spl spl-mmc.img --uboot u-boot-emmc.img \\
        --kernel xImage --main rootfs.squashfs --recovery recovery.squashfs \\
        OUTDIR [--data-mib 64] [--test-image]

The layout is stock's: p1-p7 keep their sectors, so Kiln's SPL (its built-in
partition table), the ota flag and the factory partition stay valid on every
board. What goes where:

    0x0     first MiB: the boot ROM's INGE params (Kiln's SPL's), the
            protective MBR, a new GPT (8 entries at LBA 2, as stock), Kiln's
            SPL at 0x4400, Kiln's U-Boot at 0xA400
    p1      kernel     Kiln's 6.6 (uImage "Linux-6.6-ad5x")
    p2      rootfs     the recovery OS          (slot A, as Kiln OS 1.x)
    p3      kernel2    Kiln's 6.6
    p4      rootfs2    the main OS              (slot B)
    p5      ota        boot flag "ota:kernel2", U-Boot's areas empty
    p6      usershare  only with --usershare (this printer's own, checked) or
                       --mac (a new one with that Ethernet address); without
                       them no file: the factory data stays as it is
    p7      userdata   a small empty ext4 (/data); the GPT's last partition
                       ends with the image, on any eMMC size

Every file is written at its own offset; without --usershare or --mac p6
has no file, so flashing all of them leaves the factory partition as it
was. --test-image also writes the whole image as one file for loop-device
and emulator tests: never flash that one whole (without p6 it zeroes p6).

--rescue SERVER[:PORT] adds the network rescue for a printer that only
USBCloner reaches: rescue-first-mib.bin (1 MiB, the one file USBCloner
writes: Kiln's SPL and U-Boot, and a record naming SERVER), and rescue/,
which SERVER serves over HTTP; Kiln's U-Boot then fetches, checks and
writes everything else (RESCUE.txt).

Reads files only; never opens a device.
"""
import argparse
import binascii
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "u-boot", "tools"))
import ad5x_spl_image as spl  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ad5x_usershare as ushare  # noqa: E402

SECTOR = 512
MIB = 1 << 20
# stock's layout (every AD5X examined; Kiln's SPL: mach/x2600.h)
PARTS = [  # number, name, first sector, sectors (0: to the end of the image)
    (1, "kernel", 0x800, 0x4000),
    (2, "rootfs", 0x4800, 0x32000),
    (3, "kernel2", 0x36800, 0x4000),
    (4, "rootfs2", 0x3a800, 0x32000),
    (5, "ota", 0x6c800, 0x800),
    (6, "usershare", 0x6d000, 0x200000),
    (7, "userdata", 0x26d000, 0),
]
GPT_ENTRIES = 8
GPT_ENTRY_SIZE = 128
BASIC_DATA = uuid.UUID("ebd0a0a2-b9e5-4433-87c0-68b6b72699c7")
SPL_OFF = 0x4400
UBOOT_OFF = 0xA400
FLAG = b"ota:kernel2"
KERNEL_NAME = b"Linux-6.6-ad5x"
UIMAGE_MAGIC = 0x27051956
SQUASHFS_MAGIC = b"hsqs"
# what an ext4 the 6.6 and 7.3 kernels mount needs; newer e2fsprogs
# defaults (orphan_file) are left out
MKE2FS_FEATURES = "^orphan_file"


RESCUE_FIRST = "rescue-first-mib.bin"
RESCUE_LBA = MIB // SECTOR - 1          # the first MiB's last sector
RESCUE_CHUNK = 32 * MIB                 # what U-Boot holds in RAM at once
RESCUE_NOTE = """Network rescue: USBCloner writes the first MiB, Kiln's U-Boot the rest
=========================================================================

1. Serve this folder from the PC at %(server)s (any OS with Python 3):

     python3 -m http.server %(port)s --directory "%(out)s"

   (rescue/ must be reachable at http://%(server)s:%(port)s/rescue/; allow
   the port in the PC's firewall.) The printer's Ethernet port on the same
   network%(net)s.

2. USBCloner writes %(first)s (1 MiB): Kiln's SPL and U-Boot, the
   GPT, and the rescue record in its last sector. The settings that
   restored an AD5X's first MiB before (alexshev86, #68; USBCloner 2.5.36.1
   and 2.5.50 on Windows):

     Board config  configs/x2600/x2600_mmc0_ddr3_linux.cfg
     POLICY        exactly one entry enabled, the others disabled:
                     type FILE (type=0), ops MMC0 (ops="6,2,0"),
                     offset 0x0, attribute %(first)s
     MMC           Force erase: None (force_erase=0)
     DEBUG         Readback and CRC/Transfer check on
     other         force_reset=0, cpu_info_length=5

   Power off; cable on J28 (D+, D-, GND; 5 V open); start USBCloner;
   power on (a damaged SPL sends the boot ROM to USB mode by itself,
   otherwise K4 or the boot-select strap); Start; wait for it to finish.

3. Power off and on fully (K4 or the strap open again). Kiln's SPL starts
   Kiln's U-Boot, which finds the record and, with the watchdog off:
   gets an address%(dhcp)s, fetches rescue/rescue.scr and checks it
   against the sha256 in the record, then fetches each piece (%(pieces)d
   pieces, %(mib)d MiB over the network), checks its sha256, writes it and
   checks what reads back. The normal first MiB comes last and clears the
   record; then U-Boot resets and Kiln OS starts from slot B. A failure:
   a reset after 10 s, and the rescue starts again. The serial console
   (DEBUG header) shows the progress; the PC's server log shows each
   piece fetched.

usershare (p6): %(usershare)s

Afterwards /data is small (%(data)d MiB): give it the rest of the eMMC with
ad5x_emmc_repair.py restore --image ... --keep-data, or from the printer.
USBCloner leaves 84 00 84 00 at 0x4480 until the rescue writes the normal
first MiB.

Not tried yet: USBCloner on an X2600E (256 MiB) printer, whose DDR differs
from the X2600H's.
"""


def uimage_script(text):
    """A U-Boot legacy script image ("source"): header + length table +
    the script."""
    body = struct.pack(">II", len(text), 0) + text
    h = bytearray(struct.pack(">IIIIIIIBBBB32s", UIMAGE_MAGIC, 0, 0,
                              len(body), 0, 0, binascii.crc32(body) &
                              0xffffffff, 5, 5, 6, 0, b"Kiln eMMC rescue"))
    struct.pack_into(">I", h, 4, binascii.crc32(bytes(h)) & 0xffffffff)
    return bytes(h) + body


def rescue_files(out, files, first, server, port, mac, ip):
    """rescue/: the pieces in chunks of RESCUE_CHUNK, rescue.scr, and the
    first MiB with the record. Returns (pieces, bytes fetched)."""
    d = os.path.join(out, "rescue")
    os.makedirs(d, exist_ok=True)
    lines = ["echo ad5x rescue: writing the eMMC"]
    pieces, fetched = 0, 0
    order = [f for f in files if f[1] != 0] + [f for f in files if f[1] == 0]
    for name, off, b in order:
        base = name.split(".")[0]
        for i in range(0, len(b), RESCUE_CHUNK):
            c = b[i:i + RESCUE_CHUNK]
            c = c + bytes(-len(c) % SECTOR)
            blk, cnt = (off + i) // SECTOR, len(c) // SECTOR
            if c.count(0) == len(c):
                f = "-"
            else:
                f = "/rescue/%s.%03d" % (base, i // RESCUE_CHUNK)
                with open(os.path.join(out, f[1:]), "wb") as fh:
                    fh.write(c)
                fetched += len(c)
            pieces += 1
            lines.append("echo ad5x rescue: %s %d/%d; setenv f %s; "
                         "setenv sz 0x%x; setenv blk 0x%x; setenv cnt 0x%x; "
                         "setenv sum %s; run kr_piece" %
                         (base, i // RESCUE_CHUNK + 1,
                          -(-len(b) // RESCUE_CHUNK), f, len(c), blk, cnt,
                          sha256(c)))
    lines += ["echo ad5x rescue: done, the eMMC is written; reset", "reset"]
    scr = uimage_script(("\n".join(lines) + "\n").encode())
    with open(os.path.join(d, "rescue.scr"), "wb") as fh:
        fh.write(scr)
    rec = "KILN-RESCUE 1\nserver=%s\nport=%d\nsha256=%s\n" % (
        server, port, sha256(scr))
    if mac:
        rec += "mac=%s\n" % mac
    if ip:
        a, m = (ip.split("/") + ["255.255.255.0"])[:2]
        rec += "ip=%s\nnetmask=%s\n" % (a, m)
    rec = rec.encode()
    if len(rec) > SECTOR - 1:
        raise ImageError("rescue record too long")
    if any(first[RESCUE_LBA * SECTOR:]):
        raise ImageError("U-Boot reaches the first MiB's last sector: no "
                         "room for the rescue record")
    rf = bytearray(first)
    rf[RESCUE_LBA * SECTOR:RESCUE_LBA * SECTOR + len(rec)] = rec
    with open(os.path.join(out, RESCUE_FIRST), "wb") as fh:
        fh.write(bytes(rf))
    return pieces, fetched


class ImageError(Exception):
    pass


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def read(p):
    with open(p, "rb") as f:
        return f.read()


def check_uimage(b, what):
    if len(b) < 64 or struct.unpack(">I", b[:4])[0] != UIMAGE_MAGIC:
        raise ImageError("%s: not a uImage" % what)
    hdr = bytearray(b[:64])
    hcrc = struct.unpack(">I", hdr[4:8])[0]
    hdr[4:8] = bytes(4)
    if binascii.crc32(bytes(hdr)) & 0xffffffff != hcrc:
        raise ImageError("%s: uImage header CRC wrong" % what)
    size, dcrc = struct.unpack(">I", b[12:16])[0], struct.unpack(">I", b[24:28])[0]
    if len(b) < 64 + size or \
            binascii.crc32(b[64:64 + size]) & 0xffffffff != dcrc:
        raise ImageError("%s: uImage data short or its CRC wrong" % what)
    return b[32:64].split(b"\0")[0]


def last_usable_lba(total_sectors):
    """The last LBA a partition may use: the backup GPT's entries and
    header take the sectors after it."""
    return total_sectors - 1 - GPT_ENTRIES * GPT_ENTRY_SIZE // SECTOR - 1


def gpt(total_sectors):
    """Primary (LBA 1, entries at LBA 2) and backup GPT (entries before the
    last sector), as stock: 8 entries, basic data type, no attributes."""
    last = total_sectors - 1
    n_ent_sectors = GPT_ENTRIES * GPT_ENTRY_SIZE // SECTOR
    first_usable = 34                       # as stock: SPL at LBA 34
    last_usable = last_usable_lba(total_sectors)
    ents = bytearray(GPT_ENTRIES * GPT_ENTRY_SIZE)
    for num, name, start, count in PARTS:
        end = (last_usable if count == 0 else start + count - 1)
        if end < start:
            raise ImageError("%s doesn't fit" % name)
        e = BASIC_DATA.bytes_le + uuid.uuid4().bytes_le + \
            struct.pack("<QQQ", start, end, 0) + \
            name.encode("utf-16le").ljust(72, b"\0")
        ents[(num - 1) * GPT_ENTRY_SIZE:num * GPT_ENTRY_SIZE] = e
    ecrc = binascii.crc32(bytes(ents)) & 0xffffffff
    disk = uuid.uuid4().bytes_le

    def header(cur, alt, elba):
        h = bytearray(struct.pack("<8sIIIIQQQQ16sQIII", b"EFI PART", 0x10000,
                                  92, 0, 0, cur, alt, first_usable,
                                  last_usable, disk, elba, GPT_ENTRIES,
                                  GPT_ENTRY_SIZE, ecrc))
        struct.pack_into("<I", h, 16, binascii.crc32(bytes(h)) & 0xffffffff)
        return bytes(h).ljust(SECTOR, b"\0")

    primary = header(1, last, 2)
    backup = header(last, 1, last - n_ent_sectors)
    return primary, bytes(ents), backup


def protective_mbr_entry(total_sectors):
    n = min(total_sectors - 1, 0xffffffff)
    return struct.pack("<B3sB3sII", 0, b"\x00\x02\x00", 0xee, b"\xff\xff\xff",
                       1, n) + bytes(48) + b"\x55\xaa"


def build(a):
    spl_img = read(a.spl)
    uboot = read(a.uboot)
    kernel = read(a.kernel)
    main = read(a.main)
    rec = read(a.recovery)

    # the SPL image as the boot ROM loads it, from the build's own check
    magic, count, _ = spl.decode(spl_img, 0)
    if magic != spl.SPL_MAGIC or spl_img[spl.PARAMS_OFF:spl.PARAMS_OFF + 4] \
            != spl.PARAMS_ID:
        raise ImageError("--spl: not spl-mmc.img (no LPSM header/INGE params)")
    if spl_img[spl.USB_TAG_OFF:spl.USB_TAG_OFF + len(spl.USB_TAG)] == spl.USB_TAG:
        raise ImageError("--spl: this is spl-usb.bin; use spl-mmc.img")
    if SPL_OFF + len(spl_img) > UBOOT_OFF:
        raise ImageError("--spl: %d bytes don't fit before 0xA400" %
                         len(spl_img))
    if check_uimage(uboot, "--uboot") is None or \
            UBOOT_OFF + len(uboot) > MIB:
        raise ImageError("--uboot: doesn't fit before 1 MiB")
    if not check_uimage(kernel, "--kernel").startswith(KERNEL_NAME):
        raise ImageError("--kernel: not Kiln's 6.6 (uImage name %s...)" %
                         KERNEL_NAME.decode())
    for b, what, part in ((main, "--main", 4), (rec, "--recovery", 2)):
        if b[:4] != SQUASHFS_MAGIC:
            raise ImageError("%s: not a SquashFS" % what)
        if len(b) > PARTS[part - 1][3] * SECTOR:
            raise ImageError("%s: %d bytes don't fit p%d" % (what, len(b),
                                                             part))
    if len(kernel) > PARTS[0][3] * SECTOR:
        raise ImageError("--kernel doesn't fit a kernel slot")

    data_start = PARTS[6][2]
    total = data_start + a.data_mib * MIB // SECTOR
    primary, ents, backup = gpt(total)

    # first MiB
    first = bytearray(MIB)
    first[0:spl.PARAMS_SIZE] = spl_img[spl.PARAMS_OFF:spl.PARAMS_OFF +
                                       spl.PARAMS_SIZE]
    first[0x1be:0x200] = protective_mbr_entry(total)
    first[0x200:0x400] = primary
    first[0x400:0x400 + len(ents)] = ents
    first[SPL_OFF:SPL_OFF + len(spl_img)] = spl_img
    # 0xFF after the SPL up to U-Boot, as Ingenic's build pads it
    first[SPL_OFF + len(spl_img):UBOOT_OFF] = b"\xff" * (UBOOT_OFF - SPL_OFF - len(spl_img))
    first[UBOOT_OFF:UBOOT_OFF + len(uboot)] = uboot

    # p7: an empty ext4 of userdata's size in the GPT (--data-mib less the
    # backup GPT at its end), whole 4 KiB blocks: the kernel refuses an
    # ext4 larger than its partition
    p7_sectors = last_usable_lba(total) - data_start + 1
    fs_bytes = p7_sectors * SECTOR // 4096 * 4096
    with tempfile.TemporaryDirectory() as td:
        dimg = os.path.join(td, "userdata.img")
        with open(dimg, "wb") as f:
            f.truncate(fs_bytes)
        subprocess.run(["mke2fs", "-q", "-F", "-t", "ext4", "-O",
                        MKE2FS_FEATURES, "-L", "userdata", "-E",
                        "root_owner=0:0", dimg], check=True)
        data = read(dimg)
    # the backup GPT sits in the last sectors of userdata's range
    tail = ents + backup
    data = data.ljust(a.data_mib * MIB - len(tail), b"\0") + tail

    ota = bytearray(PARTS[4][3] * SECTOR)
    ota[0:len(FLAG)] = FLAG

    # usershare: this printer's own when one of --usershare is good, else
    # a new one with the address from --mac
    us = None
    if a.usershare:
        us, mac, src = ushare.find(a.usershare)
        if us is not None:
            us_what = "this printer's, from %s (/MAC %s)" % (src, mac)
    if us is None and a.mac:
        us, mac = ushare.make(a.mac)
        us_what = "made new, /MAC %s" % mac
        print("usershare: none of the printer's own usable%s: a new one with "
              "/MAC %s" % (" (above)" if a.usershare else "", mac))
    if us is None and a.usershare:
        raise ImageError("no usable usershare among --usershare: give --mac "
                         "to make a new one")
    if a.rescue and us is None:
        raise ImageError("--rescue writes the whole eMMC, usershare too: give "
                         "--usershare (this printer's) or --mac")

    files = [  # name, eMMC byte offset, bytes
        ("00-first-mib.bin", 0, bytes(first)),
        ("p1-kernel.img", PARTS[0][2] * SECTOR, kernel),
        ("p2-rootfs-recovery.img", PARTS[1][2] * SECTOR, rec),
        ("p3-kernel2.img", PARTS[2][2] * SECTOR, kernel),
        ("p4-rootfs2-main.img", PARTS[3][2] * SECTOR, main),
        ("p5-ota.img", PARTS[4][2] * SECTOR, bytes(ota)),
        ("p7-userdata.img", data_start * SECTOR, data),
    ]
    if us is not None:
        files.insert(6, ("p6-usershare.img", PARTS[5][2] * SECTOR, us))
    os.makedirs(a.out, exist_ok=True)
    sums = []
    for name, off, b in files:
        with open(os.path.join(a.out, name), "wb") as f:
            f.write(b)
        sums.append("%s  %s" % (sha256(b), name))
    if a.test_image:
        with open(os.path.join(a.out, "TEST-ONLY-whole-emmc-do-not-flash.img"),
                  "wb") as f:
            f.truncate(total * SECTOR)
            for _, off, b in files:
                f.seek(off)
                f.write(b)
    if a.rescue:
        server, _, port = a.rescue.partition(":")
        port = int(port or 8000)
        pieces, fetched = rescue_files(a.out, files, first, server, port,
                                       mac if us is not None else None,
                                       a.rescue_ip)
        rf = read(os.path.join(a.out, RESCUE_FIRST))
        sums.append("%s  %s" % (sha256(rf), RESCUE_FIRST))
        with open(os.path.join(a.out, "RESCUE.txt"), "w") as f:
            f.write(RESCUE_NOTE % dict(
                server=server, port=port, out=os.path.abspath(a.out),
                first=RESCUE_FIRST, pieces=pieces, mib=fetched // MIB,
                usershare=us_what, data=a.data_mib,
                net=" (a static address, %s)" % a.rescue_ip if a.rescue_ip
                else ", with a DHCP server",
                dhcp="" if a.rescue_ip else " by DHCP"))
    with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    print("eMMC image files in %s: %d sectors (%.1f MiB) up to the end of "
          "userdata (%d MiB); usershare (p6): %s" %
          (a.out, total, total * SECTOR / MIB, a.data_mib,
           us_what if us is not None else "no file, never written"))
    if a.rescue:
        print("rescue: USBCloner writes %s; serve %s from %s; steps in "
              "RESCUE.txt" % (RESCUE_FIRST, a.out, a.rescue))
    for s in sums:
        print("  " + s)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--spl", required=True, help="spl-mmc.img (u-boot/build.sh)")
    p.add_argument("--uboot", required=True, help="u-boot-emmc.img")
    p.add_argument("--kernel", required=True,
                   help="Kiln's 6.6 uImage (/usr/lib/ad5x/kernel66/xImage)")
    p.add_argument("--main", required=True, help="the main OS rootfs.squashfs")
    p.add_argument("--recovery", required=True, help="recovery.squashfs")
    p.add_argument("--data-mib", type=int, default=64,
                   help="userdata's size in the image (MiB, default 64)")
    p.add_argument("--usershare", action="append", metavar="SOURCE",
                   help="this printer's usershare: usershare.img, an "
                   "ad5x-backup directory or a whole-eMMC dump (repeat to "
                   "try several; the first good one is used)")
    p.add_argument("--mac", help="when no --usershare is usable (or none is "
                   "given): a new usershare with this Ethernet address "
                   "(XX:XX:XX:XX:XX:XX, or 'random')")
    p.add_argument("--rescue", metavar="SERVER[:PORT]",
                   help="also the network rescue: %s for USBCloner (Kiln's "
                   "SPL and U-Boot, and a record naming SERVER), and rescue/ "
                   "for SERVER to serve over HTTP (port 8000 by default); "
                   "steps in RESCUE.txt. Needs --usershare or --mac" %
                   RESCUE_FIRST)
    p.add_argument("--rescue-ip", metavar="IP[/NETMASK]",
                   help="the printer's address during the rescue (default: "
                   "DHCP)")
    p.add_argument("--test-image", action="store_true",
                   help="also the whole image as one file (tests only)")
    p.add_argument("out")
    a = p.parse_args(argv)
    try:
        build(a)
    except (ImageError, ushare.UsershareError, OSError,
            subprocess.CalledProcessError) as e:
        print("ad5x_emmc_image: ERROR: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
