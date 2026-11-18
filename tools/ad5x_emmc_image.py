#!/usr/bin/env python3
"""Make the files to flash a whole AD5X eMMC over USB (USBCloner, or a
host that sees the eMMC as a disk), from release images only.

    ad5x_emmc_image.py --spl spl-mmc.img --uboot u-boot-emmc.img \\
        --kernel xImage --main rootfs.squashfs --recovery recovery.squashfs \\
        OUTDIR [--data-mib 64] [--stock-mib SOURCE] [--test-image]
    ad5x_emmc_image.py --from-update kiln-os-VERSION-update.zip OUTDIR
        [--stock-mib SOURCE] [--usershare SOURCE]... [--mac MAC|random]
        [--rescue SERVER[:PORT] [--keep-usershare] [--keep-data]]

--from-update takes all five from a release's update zip: the main OS, and
inside it Kiln's 6.6, the recovery OS, and in that the SPL and U-Boot.

The layout is stock's: p1-p7 keep their sectors, so Kiln's SPL (its built-in
partition table), the ota flag and the factory partition stay valid on every
board. What goes where:

    0x0     first MiB: Kiln's SPL at 0x4400 and Kiln's U-Boot at 0xA400 in
            this printer's own first MiB (--stock-mib: its boot.img, as
            ad5x-bootloader-install puts them in: the boot ROM's INGE
            block, the GPT and everything else stay stock's bytes).
            Without one: a generated first MiB (Kiln's SPL's INGE params,
            a protective MBR, a new GPT with stock's 8 entries), said
            loudly: afterwards ad5x-bootloader-install can't upgrade the
            boot loader and Return to Flashforge firmware can't put
            Flashforge's SPL back (both compare the disk with boot.img)
    p1      kernel     Kiln's 6.6 (uImage "Linux-6.6-ad5x")
    p2      rootfs     the recovery OS          (slot A, as Kiln OS 1.x)
    p3      kernel2    Kiln's 6.6
    p4      rootfs2    the main OS              (slot B)
    p5      ota        boot flag "ota:kernel2", U-Boot's areas empty
    p6      usershare  only with --usershare (this printer's own, checked) or
                       --mac (a new one with that Ethernet address); without
                       them no file: the factory data stays as it is
    p7      userdata   a small empty ext4 (/data), with this printer's
                       boot.img in ad5x/stock when --stock-mib gave one;
                       with a generated GPT the GPT's last partition ends
                       with the image

Kiln's SPL and 6.6 in the kernel slots are Kiln's own boot loader
(docs/own-boot-loader.md): ad5x_emmc_repair.py writes these files to a
printer still on Flashforge's SPL only with --install-boot-loader.

Every file is written at its own offset; without --usershare or --mac p6
has no file, so flashing all of them leaves the factory partition as it
was. --test-image also writes the whole image as one file for loop-device
and emulator tests: never flash that one whole (without p6 it zeroes p6).

--rescue SERVER[:PORT] adds the network rescue for a printer that only
USBCloner reaches: rescue-first-mib.bin (1 MiB, the one file USBCloner
writes: Kiln's SPL and U-Boot, and a record naming SERVER), and rescue/,
which SERVER serves over HTTP; Kiln's U-Boot then fetches, checks and
writes everything else (RESCUE.txt). It writes usershare and /data too,
unless --keep-usershare or --keep-data (which needs --stock-mib: the GPT
must be the eMMC's own).

Reads files only; never opens a device.
"""
import argparse
import binascii
import hashlib
import ipaddress
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import zipfile

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

This installs Kiln's own boot loader (Kiln's SPL and U-Boot,
docs/own-boot-loader.md) along with the system: the first MiB is
%(firstmib)s.

1. Serve this folder from the PC at %(server)s (any OS with Python 3),
   on that address only:

     python3 -m http.server %(port)s --bind %(server)s --directory "%(out)s"

   (rescue/ must be reachable at http://%(server)s:%(port)s/rescue/; allow
   the port in the PC's firewall.) The printer's Ethernet port on the same
   network%(net)s. Anyone on that network can fetch what is served while
   the server runs, %(private)s: use a network you trust, and stop the
   server (Ctrl-C) and delete this folder when the rescue is done.

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
   Kiln's U-Boot, which finds the record and, with the watchdog at 900 s a step:
   gets an address%(dhcp)s, fetches rescue/rescue.scr and checks it
   against the sha256 in the record, then fetches each piece (%(pieces)d
   pieces, %(mib)d MiB over the network), checks its sha256, writes it and
   checks what reads back. The normal first MiB comes last and clears the
   record; then U-Boot resets and Kiln OS starts from slot B. A failure,
   or no server: a reset after 10 s, and the rescue starts again, three
   times in all (U-Boot counts each start in the record). Then U-Boot
   starts as without it; the record stays until a rescue finishes,
   "ad5x_rescue clear" at the U-Boot prompt, or a new first MiB.
   The serial console (DEBUG header) or ad5x_netconsole.py on the serving
   PC shows the progress; the PC's server log shows each piece fetched.

usershare (p6): %(usershare)s
/data (p7): %(data)s

USBCloner leaves 84 00 84 00 at 0x4480 until the rescue writes the normal
first MiB.

Not tried yet: USBCloner on an X2600E (256 MiB) printer, whose DDR differs
from the X2600H's.
"""


def rescue_address(server, port, ip):
    """The record's values as Kiln's U-Boot checks them (bootlogic.c,
    ad5x_rescue_parse; a record that doesn't check is ignored): the server
    a unicast IPv4 address, the port 1-65535, the printer's ip and netmask
    IPv4 addresses."""
    try:
        a = ipaddress.IPv4Address(server)
    except ValueError:
        raise ImageError("--rescue %s: the server must be the PC's IPv4 "
                         "address (no name: U-Boot resolves none)" % server)
    if a.packed[0] == 0 or a.packed[0] >= 224:
        raise ImageError("--rescue %s: not a unicast address" % server)
    if not 1 <= port <= 65535:
        raise ImageError("--rescue: port %d isn't 1-65535" % port)
    if ip:
        for x in (ip.split("/") + ["255.255.255.0"])[:2]:
            try:
                ipaddress.IPv4Address(x)
            except ValueError:
                raise ImageError("--rescue-ip %s: %s isn't an IPv4 address"
                                 % (ip, x))


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
    if len(rec) > SECTOR - 1 - len(b"tries=999\n"):
        raise ImageError("rescue record too long (U-Boot adds its tries= "
                         "line)")
    if any(first[RESCUE_LBA * SECTOR:]):
        raise ImageError("the first MiB's last sector isn't empty (U-Boot "
                         "reaches it, or this printer's first MiB has bytes "
                         "there): no room for the rescue record")
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


# ---- the first MiB: whose SPL, this printer's stock one, Kiln's in it ----

FF_SPL_BANNER = b"U-Boot SPL 2013.07"


def spl_loader(mib):
    """Whose SPL the first MiB @mib holds (0x4400-0xA3FF), as
    lib/bootloader.sh's bl_loader: "kiln" (its KILNCLK record),
    "flashforge" (U-Boot SPL 2013.07), else "unknown"."""
    for t in re.split(rb"[^ -~]+", bytes(mib[SPL_OFF:UBOOT_OFF])):
        if b"KILNCLK" in t:
            return "kiln"
        if t.startswith(FF_SPL_BANNER):
            return "flashforge"
    return "unknown"


def spl_banner(mib):
    for t in re.split(rb"[^ -~]+", bytes(mib[SPL_OFF:UBOOT_OFF])):
        if b"U-Boot SPL" in t:
            return t[t.index(b"U-Boot SPL"):].decode(errors="replace")
    return ""


def kernel_kind(b):
    """A kernel slot's uImage, as recovery.sh's rc_kernel_kind: kiln
    (Linux-6.6-ad5x), stock (Linux-5.10), none or other."""
    try:
        name = check_uimage(b, "kernel")
    except ImageError:
        return "none" if b[:4] != struct.pack(">I", UIMAGE_MAGIC) else "other"
    if name.startswith(KERNEL_NAME):
        return "kiln"
    if name.startswith(b"Linux-5.10"):
        return "stock"
    return "other"


def first_gpt(first):
    """The primary GPT inside a first MiB (header at 0x200, entries in the
    first MiB): dict (raw, alt, last, guid, elba, n, esz, ents, parts), or
    a string saying what is wrong."""
    h = bytes(first[SECTOR:2 * SECTOR])
    if h[:8] != b"EFI PART":
        return "no GPT header at 0x200"
    (_, _, hsz, hcrc, _, cur, alt, _, last, guid, elba, n, esz,
     ecrc) = struct.unpack_from("<8sIIIIQQQQ16sQIII", h)
    if not 92 <= hsz <= SECTOR or cur != 1:
        return "GPT header fields wrong"
    hb = bytearray(h[:hsz])
    struct.pack_into("<I", hb, 16, 0)
    if binascii.crc32(bytes(hb)) & 0xffffffff != hcrc:
        return "GPT header CRC wrong"
    if esz != GPT_ENTRY_SIZE or not 0 < n <= 128 or \
            elba * SECTOR + n * esz > len(first):
        return "GPT entries not in the first MiB"
    ents = bytes(first[elba * SECTOR:elba * SECTOR + n * esz])
    if binascii.crc32(ents) & 0xffffffff != ecrc:
        return "GPT entries CRC wrong"
    parts = {}
    for i in range(n):
        e = ents[i * esz:(i + 1) * esz]
        if e[:16] == bytes(16):
            continue
        st, end = struct.unpack_from("<QQ", e, 32)
        parts[i + 1] = (e[56:128].decode("utf-16le", "replace").split("\0")[0],
                        st, end)
    return dict(raw=h[:hsz], alt=alt, last=last, guid=guid, elba=elba, n=n,
                esz=esz, ents=ents, parts=parts)


def layout_problems(g):
    """What in GPT @g (first_gpt's or ad5x_emmc_repair.parse_gpt's dict)
    differs from stock's layout: p1-p6 where stock has them, p7 from its
    start within the usable sectors."""
    out = []
    for n, name, start, cnt in PARTS:
        if n not in g["parts"]:
            out.append("p%d missing" % n)
            continue
        gname, s, e = g["parts"][n]
        if gname != name or s != start:
            out.append("p%d is %s at %d, not %s at %d" % (n, gname, s, name,
                                                          start))
        elif cnt and e != start + cnt - 1:
            out.append("p%d ends at %d, not %d" % (n, e, start + cnt - 1))
    if 7 in g["parts"] and g["parts"][7][2] > g["last"]:
        out.append("p7 runs past the last usable sector")
    return out


def stock_mib_problem(b):
    """Why @b isn't a stock first MiB (a boot.img: Flashforge's SPL and raw
    U-Boot, the INGE block, a GPT of stock's layout), as
    ad5x-bootloader-install's boot_img_why checks it; None when it is."""
    if len(b) != MIB:
        return "%d bytes, not 1 MiB" % len(b)
    if b[:4] != spl.PARAMS_ID or b[SECTOR:SECTOR + 8] != b"EFI PART" or \
            b[SPL_OFF:SPL_OFF + 4] != spl.SPL_MAGIC:
        return "no INGE block, GPT or LPSM in it"
    if spl_loader(b) != "flashforge":
        return "not Flashforge's SPL (no U-Boot SPL 2013.07 banner)"
    if b[UBOOT_OFF:UBOOT_OFF + 4] == struct.pack(">I", UIMAGE_MAGIC):
        return "a uImage at 0xA400: not Flashforge's raw U-Boot"
    g = first_gpt(b)
    if isinstance(g, str):
        return g
    lp = layout_problems(g)
    if lp:
        return "GPT not stock's layout: " + "; ".join(lp)
    return None


def sha_listed(d, name):
    """The sha256 listed for @name next to it: NAME.sha256 or SHA256SUMS in
    folder @d; None when neither lists it."""
    for f, pick in ((name + ".sha256", None), ("SHA256SUMS", name)):
        try:
            with open(os.path.join(d, f)) as fh:
                for line in fh:
                    w = line.split()
                    if w and (pick is None or w[1:] in ([pick], ["*" + pick])):
                        return w[0]
        except OSError:
            pass
    return None


def load_stock_mib(source):
    """This printer's stock first MiB from @source: a boot.img (with its
    .sha256 or a SHA256SUMS next to it, checked when there), a folder with
    one (an ad5x-backup, a copy of /data/ad5x/stock, kiln-stock-backup/),
    or a whole-eMMC dump (its first MiB). (bytes, description); ImageError
    when it isn't one."""
    path = source
    if os.path.isdir(source):
        path = os.path.join(source, "boot.img")
        if not os.path.isfile(path):
            raise ImageError("%s: no boot.img in it" % source)
    with open(path, "rb") as f:
        b = f.read(MIB)
        whole = os.path.getsize(path) > MIB
    if not whole:
        want = sha_listed(os.path.dirname(os.path.abspath(path)),
                          os.path.basename(path))
        if want and want != sha256(b):
            raise ImageError("%s doesn't match its sha256 (%s)" % (path, want))
    why = stock_mib_problem(b)
    if why:
        raise ImageError("%s: not this printer's stock first MiB: %s" %
                         (path, why))
    return b, "%s (%s)" % (path, spl_banner(b))


def boot_images(first):
    """(SPL image, U-Boot uImage) of Kiln's boot loader in a first MiB made
    by this tool (00-first-mib.bin): the SPL's blocks from 0x4400, the
    uImage from 0xA400."""
    magic, count, _ = spl.decode(first[SPL_OFF:], 0)
    if magic != spl.SPL_MAGIC or not 0 < count <= spl.MAX_BLOCKS or \
            spl_loader(first) != "kiln":
        raise ImageError("no Kiln SPL at 0x4400")
    s = bytes(first[SPL_OFF:SPL_OFF + count * SECTOR])
    check_uimage(first[UBOOT_OFF:], "U-Boot at 0xA400")
    size = struct.unpack(">I", first[UBOOT_OFF + 12:UBOOT_OFF + 16])[0]
    return s, bytes(first[UBOOT_OFF:UBOOT_OFF + 64 + size])


def compose_first_mib(base, spl_img, uboot):
    """@base (this printer's first MiB: boot.img, or the disk's own) with
    Kiln's SPL and U-Boot put in as ad5x-bootloader-install's bl_compose
    and ad5x_spl_image.py's first-mib and uboot-mib put them: the SPL range
    0xFF, the SPL image over it, the unit's params copy at 0x4500 and the
    length at 0x4 the image's; U-Boot at 0xA400, the rest of its last sector
    and up to 1 MiB @base's. Nothing else changes."""
    b = bytearray(base)
    if b[UBOOT_OFF:UBOOT_OFF + 4] == struct.pack(">I", UIMAGE_MAGIC):
        b[UBOOT_OFF:UBOOT_OFF + 4] = bytes(4)   # the disk's own Kiln U-Boot
    try:
        return spl.uboot_mib(spl.first_mib(bytes(b), spl_img), uboot)
    except spl.ImageError as e:
        raise ImageError(str(e))


def boot_seed(stock):
    """The files ad5x/stock/boot.img* as the main OS saves them
    (S99ad5x-booted: boot.img, boot.img.sha256, boot.img.info)."""
    return {"boot.img": stock,
            "boot.img.sha256": ("%s  boot.img\n" % sha256(stock)).encode(),
            "boot.img.info": ("Flashforge's boot loader: %s\n" %
                              spl_banner(stock)).encode()}


def put_boot_img(target, stock):
    """this printer's boot.img into /ad5x/stock of the ext4 @target (a
    file, or "DEV?offset=N"), with debugfs as root's files; checked by
    reading it back. ImageError when it can't."""
    if not shutil.which("debugfs"):
        raise ImageError("debugfs not found (e2fsprogs)")
    with tempfile.TemporaryDirectory() as td:
        cmds = ["mkdir /ad5x", "mkdir /ad5x/stock"]
        for name, b in boot_seed(stock).items():
            with open(os.path.join(td, name), "wb") as f:
                f.write(b)
            cmds += ["rm /ad5x/stock/" + name,
                     "write %s /ad5x/stock/%s" % (os.path.join(td, name), name)]
        with open(os.path.join(td, "cmds"), "w") as f:
            f.write("\n".join(cmds) + "\n")
        subprocess.run(["debugfs", "-w", "-f", os.path.join(td, "cmds"),
                        target], capture_output=True)
        got = os.path.join(td, "got")
        subprocess.run(["debugfs", "-c", "-R", "dump /ad5x/stock/boot.img " +
                        got, target], capture_output=True)
        if not os.path.exists(got) or read(got) != stock:
            raise ImageError("boot.img didn't read back from the new /data")


# where a release's main OS keeps what the eMMC needs (the recovery OS
# inside it keeps the boot loader)
MAIN_KERNEL = "usr/lib/ad5x/kernel66/xImage"
MAIN_RECOVERY = "usr/share/ad5x/recovery/rootfs.squashfs"
MAIN_RECOVERY_SHA = "usr/share/ad5x/recovery/rootfs.sha256"
REC_BOOT = "usr/share/ad5x/bootloader/"


def squash_cat(image, path):
    r = subprocess.run(["unsquashfs", "-cat", image, path],
                       capture_output=True)
    if r.returncode or not r.stdout:
        raise ImageError("%s: no %s in it (unsquashfs: %s)" % (
            image, path, r.stderr.decode(errors="replace").strip()[-200:]))
    return r.stdout


def from_update(a, td):
    """--from-update: the main OS (an update zip's rootfs.squashfs, checked
    against the zip's SHA256SUMS, or a rootfs.squashfs) and what it
    carries: Kiln's 6.6, the recovery OS, and the recovery OS's SPL and
    U-Boot (checked against its SHA256SUMS). Fills what isn't given."""
    if not shutil.which("unsquashfs"):
        raise ImageError("--from-update needs unsquashfs (squashfs-tools)")
    src = a.from_update
    main = os.path.join(td, "main.squashfs")
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            if "rootfs.squashfs" not in names:
                raise ImageError("%s: no rootfs.squashfs: not an update zip" %
                                 src)
            with z.open("rootfs.squashfs") as f, open(main, "wb") as o:
                shutil.copyfileobj(f, o)
            if "SHA256SUMS" in names:
                sums = z.read("SHA256SUMS").decode().split("\n")
                want = [l.split()[0] for l in sums
                        if l.split()[1:] == ["rootfs.squashfs"]]
                if want and want[0] != sha256(read(main)):
                    raise ImageError("%s: rootfs.squashfs doesn't match its "
                                     "SHA256SUMS" % src)
    else:
        shutil.copyfile(src, main)
    rec = os.path.join(td, "recovery.squashfs")
    with open(rec, "wb") as f:
        f.write(squash_cat(main, MAIN_RECOVERY))
    want = squash_cat(main, MAIN_RECOVERY_SHA).split()[0].decode()
    if sha256(read(rec)) != want:
        raise ImageError("the recovery OS in %s doesn't match its sha256" % src)
    kern = os.path.join(td, "xImage")
    with open(kern, "wb") as f:
        f.write(squash_cat(main, MAIN_KERNEL))
    bsums = squash_cat(rec, REC_BOOT + "SHA256SUMS").decode().split("\n")
    for name, attr in (("spl-mmc.img", "spl"), ("u-boot-emmc.img", "uboot")):
        out = os.path.join(td, name)
        b = squash_cat(rec, REC_BOOT + name)
        want = [l.split()[0] for l in bsums if l.split()[1:] == [name]]
        if not want or want[0] != sha256(b):
            raise ImageError("%s in the recovery OS doesn't match its "
                             "SHA256SUMS" % name)
        with open(out, "wb") as f:
            f.write(b)
        if not getattr(a, attr):
            setattr(a, attr, out)
    for attr, path in (("main", main), ("recovery", rec), ("kernel", kern)):
        if not getattr(a, attr):
            setattr(a, attr, path)


def find_stock(a):
    """This printer's stock first MiB: --stock-mib, else the first of the
    --usershare sources that has one (an ad5x-backup folder's boot.img, a
    whole-eMMC dump's first MiB). (bytes, description) or (None, None)."""
    if a.stock_mib:
        return load_stock_mib(a.stock_mib)
    for src in a.usershare or []:
        try:
            if os.path.isdir(src) and os.path.isfile(os.path.join(src,
                                                                  "boot.img")):
                return load_stock_mib(src)
            if os.path.isfile(src) and os.path.getsize(src) > MIB * 2:
                return load_stock_mib(src)
        except (ImageError, OSError) as e:
            print("stock first MiB: %s: not used: %s" % (src, e))
    return None, None


def mkfs_data(size, stock=None):
    """An empty ext4 of @size bytes (whole 4 KiB blocks) for userdata, with
    this printer's boot.img in ad5x/stock when @stock is given."""
    with tempfile.TemporaryDirectory() as td:
        dimg = os.path.join(td, "userdata.img")
        with open(dimg, "wb") as f:
            f.truncate(size // 4096 * 4096)
        subprocess.run(["mke2fs", "-q", "-F", "-t", "ext4", "-O",
                        MKE2FS_FEATURES, "-L", "userdata", "-E",
                        "root_owner=0:0", dimg], check=True)
        if stock is not None:
            put_boot_img(dimg, stock)
        return read(dimg)


GENERATED_WARNING = """
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!! No stock first MiB of this printer (--stock-mib: its boot.img, from an
!! ad5x-backup or /data/ad5x/stock): 00-first-mib.bin has a GENERATED
!! boot ROM block and GPT. On the printer afterwards
!! ad5x-bootloader-install can't upgrade Kiln's boot loader and Return to
!! Flashforge firmware can't put Flashforge's SPL back: both need the disk
!! to be this printer's boot.img outside Kiln's ranges. Use it only when
!! that boot.img is lost. ad5x_emmc_repair.py restore builds the first
!! MiB from the printer's own one when it finds it on the eMMC.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""


def build(a):
    if a.from_update:
        with tempfile.TemporaryDirectory() as td:
            from_update(a, td)
            a.from_update = None
            return build(a)
    for attr in ("spl", "uboot", "kernel", "main", "recovery"):
        if not getattr(a, attr):
            raise ImageError("--%s (or --from-update) is needed" % attr)
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
    if a.rescue and b"KILN-RESCUE 1" not in uboot:
        raise ImageError("this U-Boot (%s) has no network rescue: it came "
                         "before Kiln's U-Boot patch 0045; use a newer release"
                         % check_uimage(uboot, "--uboot").decode(
                             errors="replace"))
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
    if a.rescue:
        server, _, port = a.rescue.partition(":")
        try:
            port = int(port or 8000)
        except ValueError:
            raise ImageError("--rescue %s: the port isn't a number" % a.rescue)
        rescue_address(server, port, a.rescue_ip)
    if not a.rescue and (a.keep_usershare or a.keep_data):
        raise ImageError("--keep-usershare and --keep-data go with --rescue "
                         "(ad5x_emmc_repair.py restore keeps both by itself)")

    stock, stock_what = find_stock(a)
    if a.rescue and a.keep_data and stock is None:
        raise ImageError("--rescue --keep-data needs this printer's stock "
                         "first MiB (--stock-mib): the GPT written must be "
                         "the eMMC's own, or the /data kept won't fit it")
    data_start = PARTS[6][2]
    if stock is not None:
        # this printer's first MiB with Kiln's SPL and U-Boot in it; its
        # GPT (and so userdata's size) stay stock's
        first = compose_first_mib(stock, spl_img, uboot)
        g = first_gpt(stock)
        total = g["alt"] + 1
        p7_bytes = (g["parts"][7][2] - data_start + 1) * SECTOR
        if a.data_mib * MIB > p7_bytes:
            raise ImageError("--data-mib %d: userdata in this printer's GPT "
                             "has %d MiB" % (a.data_mib, p7_bytes // MIB))
        data = mkfs_data(a.data_mib * MIB, stock)
        first_what = "this printer's own (%s), Kiln's SPL and U-Boot in it" \
            % stock_what
    else:
        total = data_start + a.data_mib * MIB // SECTOR
        primary, ents, backup = gpt(total)
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
        first = bytes(first)
        # p7: an empty ext4 of userdata's size in the GPT (--data-mib less
        # the backup GPT at its end), whole 4 KiB blocks: the kernel
        # refuses an ext4 larger than its partition
        p7_sectors = last_usable_lba(total) - data_start + 1
        data = mkfs_data(p7_sectors * SECTOR)
        # the backup GPT sits in the last sectors of userdata's range
        tail = ents + backup
        data = data.ljust(a.data_mib * MIB - len(tail), b"\0") + tail
        first_what = "GENERATED (no stock first MiB of this printer)"
        print(GENERATED_WARNING, file=sys.stderr)

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
    if a.rescue and us is None and not a.keep_usershare:
        raise ImageError("--rescue writes the whole eMMC, usershare too: give "
                         "--usershare (this printer's) or --mac, or "
                         "--keep-usershare to leave the eMMC's as it is")
    if a.rescue and a.keep_usershare and us is not None:
        raise ImageError("--keep-usershare and --usershare/--mac: choose one")

    files = [  # name, eMMC byte offset, bytes
        ("00-first-mib.bin", 0, first),
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
    if stock is not None:
        # for ad5x_emmc_repair.py restore: the first MiB it builds Kiln's
        # into (this printer's own; Flashforge's bytes: never share it)
        with open(os.path.join(a.out, "stock-boot.img"), "wb") as f:
            f.write(stock)
        sums.append("%s  stock-boot.img" % sha256(stock))
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
        sent = [f for f in files
                if not (a.keep_data and f[0].startswith("p7-"))]
        pieces, fetched = rescue_files(a.out, sent, first, server, port,
                                       mac if us is not None else None,
                                       a.rescue_ip)
        rf = read(os.path.join(a.out, RESCUE_FIRST))
        sums.append("%s  %s" % (sha256(rf), RESCUE_FIRST))
        private = ["the system"]
        if us is not None:
            private = ["usershare (the saved Wi-Fi passwords, the stock root "
                       "password's hash, the serial number)"]
        if stock is not None:
            private.append("this printer's boot.img")
        with open(os.path.join(a.out, "RESCUE.txt"), "w") as f:
            f.write(RESCUE_NOTE % dict(
                server=server, port=port, out=os.path.abspath(a.out),
                first=RESCUE_FIRST, pieces=pieces, mib=fetched // MIB,
                usershare=us_what if us is not None else
                "kept as it is on the eMMC (--keep-usershare)",
                data="kept as it is on the eMMC (--keep-data)" if a.keep_data
                else "a new, empty one of %d MiB%s" % (
                    a.data_mib, ", with this printer's boot.img in "
                    "ad5x/stock" if stock is not None else ""),
                firstmib=first_what, private=" and ".join(private),
                net=" (a static address, %s)" % a.rescue_ip if a.rescue_ip
                else ", with a DHCP server",
                dhcp="" if a.rescue_ip else " by DHCP"))
    with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    print("eMMC image files in %s: first MiB %s; usershare (p6): %s; "
          "userdata %d MiB" %
          (a.out, first_what, us_what if us is not None else
           "no file, never written", a.data_mib))
    if a.rescue:
        print("rescue: USBCloner writes %s; serve %s from %s only; steps in "
              "RESCUE.txt; delete the folder afterwards" %
              (RESCUE_FIRST, a.out, a.rescue))
    for s in sums:
        print("  " + s)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--spl", help="spl-mmc.img (u-boot/build.sh)")
    p.add_argument("--uboot", help="u-boot-emmc.img")
    p.add_argument("--kernel",
                   help="Kiln's 6.6 uImage (/usr/lib/ad5x/kernel66/xImage)")
    p.add_argument("--main", help="the main OS rootfs.squashfs")
    p.add_argument("--recovery", help="recovery.squashfs")
    p.add_argument("--data-mib", type=int, default=64,
                   help="userdata's size in the image (MiB, default 64)")
    p.add_argument("--from-update", metavar="ZIP",
                   help="a release's kiln-os-VERSION-update.zip (or its "
                   "rootfs.squashfs): the main OS, and the 6.6 kernel, the "
                   "recovery OS, the SPL and U-Boot it carries, for "
                   "whichever of --spl --uboot --kernel --main --recovery "
                   "isn't given")
    p.add_argument("--stock-mib", metavar="SOURCE",
                   help="this printer's stock first MiB: its boot.img (from "
                   "/data/ad5x/stock, an ad5x-backup, kiln-stock-backup/), a "
                   "folder with one, or a whole-eMMC dump; Kiln's SPL and "
                   "U-Boot go into it. Taken from an ad5x-backup folder "
                   "given as --usershare too")
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
                   "steps in RESCUE.txt. Needs --usershare, --mac or "
                   "--keep-usershare" % RESCUE_FIRST)
    p.add_argument("--rescue-ip", metavar="IP[/NETMASK]",
                   help="the printer's address during the rescue (default: "
                   "DHCP)")
    p.add_argument("--keep-usershare", action="store_true",
                   help="--rescue: leave usershare (p6) on the eMMC as it is")
    p.add_argument("--keep-data", action="store_true",
                   help="--rescue: leave /data (p7) on the eMMC as it is "
                   "(needs --stock-mib)")
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
