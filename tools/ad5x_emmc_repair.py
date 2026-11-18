#!/usr/bin/env python3
"""Check, back up and repair an AD5X's eMMC from a Linux PC.

The printer shows its eMMC to the PC as a USB disk: the boot ROM's USB mode,
then Kiln's U-Boot with "ad5x_usbboot.py run-uboot" (docs/emmc-repair.md).

    ad5x_emmc_repair.py find
    ad5x_emmc_repair.py check   [--disk DEV] [--image DIR] [--deep]
    ad5x_emmc_repair.py backup  [--disk DEV] [--userdata] DEST
    ad5x_emmc_repair.py restore [--disk DEV] (--image DIR | --backup DIR)
                                [--new-data] [--grow-data] [--parts NAME,...]
                                [--usershare] [--stock-mib SOURCE]
                                [--install-boot-loader [--unsupported-board]]
                                [--dry-run] [--yes]

find     the printer's eMMC among this PC's disks: a USB disk from Kiln's
         U-Boot (USB ID 1d6b:0104, maker "Kiln OS", U-Boot's ums product
         string). The other commands take that one when --disk is left out;
         --disk names a device (it must be the same kind of disk, or a loop
         device over an image file) or an image file (tests).
check    reads only: the first MiB (boot ROM parameters, SPL, U-Boot), both
         GPTs and stock's layout, both kernels (uImage CRCs), both root
         filesystems (SquashFS; with --image compared with the release's
         bytes), the boot flag, usershare (p6: ext4, /MAC) and userdata
         (p7: ext4 that fits its partition), and where this printer's stock
         first MiB (boot.img) is. Says what restore would do.
backup   the first MiB and p1-p6 (--userdata: p7 too) into
         DEST/ad5x-backup-<date>-<n>/, the recovery OS's ad5x-backup
         format (NAME.img, NAME.img.000... in 1 GiB pieces on FAT for 4 GiB
         and more, SHA256SUMS, MANIFEST.txt), each file read back.
restore  writes what is given, each piece read back:
         --image DIR   ad5x_emmc_image.py's files: the first MiB, p1-p5.
                       The first MiB is this printer's own (boot.img: from
                       --stock-mib, the disk itself while it has Flashforge's
                       SPL, /data/ad5x/stock, usershare's kiln-stock-backup/
                       or the image's stock-boot.img) with Kiln's SPL and
                       U-Boot put in as ad5x-bootloader-install does, so its
                       GPT stays stock's; without one, the disk's own first
                       MiB, else the image's generated one (said loudly)
         --backup DIR  an ad5x-backup: boot, kernel, rootfs, kernel2,
                       rootfs2, ota, as they are in it
         /data (p7) is kept unless --new-data: then the image's new, empty
         one (grown to its partition on the PC), or the backup's
         userdata.img. --grow-data stretches the GPT so userdata reaches the
         end of the eMMC: the disk then differs from boot.img, and
         ad5x-bootloader-install's upgrade and Return to Flashforge
         firmware's --flashforge-spl refuse it
         --usershare   also usershare, from the backup or the image
                       (ad5x_emmc_image.py --usershare/--mac); needs
                       debugfs; refused when the eMMC's own usershare is
                       usable and its /MAC differs
         --parts       only these (first-mib,p1,...,p7 or backup names)
         Boot loader rules (ad5x-restore's): Kiln's SPL and U-Boot go onto
         a disk that doesn't hold Kiln's SPL only with
         --install-boot-loader (Kiln's own boot loader, opt-in,
         docs/own-boot-loader.md; the board's stock SPL must be on the
         allowlist, else --unsupported-board; this printer's boot.img is
         saved to /data/ad5x/stock first). Under Kiln's SPL only Kiln's 6.6
         goes into a kernel slot, under Flashforge's SPL only Flashforge's
         5.10.
         Partitions first, the first MiB last (its SPL header sector last
         of all), then the backup GPT; when installing Kiln's boot loader
         the first MiB comes before the kernels. Pieces that already hold
         the same bytes are left alone. Asks before writing unless --yes;
         --dry-run says which pieces differ and writes nothing.

Writes need root and refuse a disk with anything of it mounted (a desktop
mounts the printer's ext4 partitions by itself: unmount them first); the
disk is opened exclusively.

Usershare (p6) holds this printer's factory data (MAC address, serial
number, calibration): no release has it, so it is never written except from
this printer's own backup or with --usershare.
"""
import argparse
import binascii
import datetime
import fcntl
import glob
import hashlib
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ad5x_emmc_image as img  # noqa: E402
spl = img.spl

SECTOR = 512
MIB = 1 << 20
CHUNK = 4 * MIB
FIRST_MIB = MIB
PARTS = img.PARTS                    # (number, name, first sector, sectors)
USERSHARE, USERDATA = 6, 7
SPL_LBA = img.SPL_OFF // SECTOR      # the SPL's header sector (34)
# Kiln's U-Boot's ums: idVendor, idProduct, manufacturer, and the product
# strings it may give: U-Boot's g_dnl default, or a name of its own
KILN_UMS = ("1d6b", "0104", "Kiln OS")
KILN_UMS_PRODUCTS = ("USB download gadget", "AD5X eMMC (Kiln U-Boot ums)")
SYSFS = os.environ.get("AD5X_SYSFS", "/sys")         # tests
MOUNTS = os.environ.get("AD5X_MOUNTS", "/proc/mounts")
BLKFLSBUF, BLKRRPART = 0x1261, 0x125f  # _IO(0x12, 97), _IO(0x12, 95)
if os.uname().machine.startswith("mips"):  # _IO's direction bits differ
    BLKFLSBUF, BLKRRPART = 0x20001261, 0x2000125f
EXT4_MAGIC = 0xEF53
FAT_PIECE = 1 << 30                  # ad5x-backup's pieces on FAT
FAT_MAX = 4 << 30                    # from this size on (FAT's file limit)
# image file names -> (restore name, eMMC byte offset)
IMAGE_FILES = {"00-first-mib.bin": ("first-mib", 0)}
for _n, _name, _start, _cnt in PARTS:
    IMAGE_FILES["p%d" % _n] = ("p%d" % _n, _start * SECTOR)
# ad5x-backup names (the GPT's) -> restore name
BACKUP_NAMES = {"boot": "first-mib"}
BACKUP_NAMES.update({name: "p%d" % n for n, name, _, _ in PARTS})
# lib/bootloader.sh's BL_ALLOWLIST: the boards Kiln's SPL and U-Boot are
# known to fit, (SPL fingerprint, DDR table fingerprint) of the stock SPL
# (test_ad5x_emmc_repair.py checks it against bootloader.sh)
ALLOWLIST = {("f7b9d763c1e83af8", "61b7ee909c0baa50"):
             "W634GU6QG-11; two boards known"}
DDR_NAME, DDR_LEN = b"W634GU6QG-11", 188


class RepairError(Exception):
    pass


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def ask(prompt):
    """A typed answer (tests replace it)."""
    return input(prompt).strip()


# ---- the disk ----

def usb_identity(dev):
    """(idVendor, idProduct, manufacturer, product) of the USB device
    behind a block device, or None."""
    name = os.path.basename(os.path.realpath(dev))
    p = os.path.realpath(os.path.join(SYSFS, "block", name, "device"))
    root = os.path.realpath(SYSFS)
    while p.startswith(root + "/"):
        if os.path.exists(os.path.join(p, "idVendor")):
            def rd(f):
                try:
                    with open(os.path.join(p, f)) as fh:
                        return fh.read().strip()
                except OSError:
                    return ""
            return (rd("idVendor"), rd("idProduct"), rd("manufacturer"),
                    rd("product"))
        p = os.path.dirname(p)
    return None


def is_kiln_ums(ident):
    return bool(ident) and tuple(ident[:3]) == KILN_UMS and \
        ident[3] in KILN_UMS_PRODUCTS


def kiln_disks():
    return sorted("/dev/" + os.path.basename(b)
                  for b in glob.glob(os.path.join(SYSFS, "block", "sd*"))
                  if is_kiln_ums(usb_identity("/dev/" + os.path.basename(b))))


def device_problem(path):
    """Why the block device @path isn't one this tool may open: None for the
    printer's eMMC from Kiln's U-Boot, and for a loop device over an image
    file (tests); a loop device over a block device is judged by that."""
    name = os.path.basename(os.path.realpath(path))
    if name.startswith("loop"):
        try:
            with open(os.path.join(SYSFS, "block", name, "loop",
                                   "backing_file")) as f:
                back = f.read().strip()
        except OSError:
            return "%s: a loop device with no backing file" % path
        try:
            st = os.stat(back)
        except OSError:
            return "%s: its backing file %s is gone" % (path, back)
        if stat.S_ISBLK(st.st_mode):
            why = device_problem(back)
            return why and "%s (over %s): %s" % (path, back, why)
        return None if stat.S_ISREG(st.st_mode) else \
            "%s: backed by %s, neither a file nor a disk" % (path, back)
    ident = usb_identity(path)
    if not is_kiln_ums(ident):
        return ("%s isn't an AD5X eMMC shown by Kiln's U-Boot (USB %s): "
                "refused" % (path, ident))
    return None


def disk_nodes(path):
    """The disk's node and its partitions' nodes (/dev/NAME)."""
    name = os.path.basename(os.path.realpath(path))
    nodes = {"/dev/" + name}
    for p in glob.glob(os.path.join(SYSFS, "block", name, name + "*")):
        nodes.add("/dev/" + os.path.basename(p))
    return nodes


def in_use(path):
    """[(node, where, read-write)] for each mount of the disk or one of its
    partitions (/proc/mounts), and each holder (device-mapper, md)."""
    nodes = disk_nodes(path)
    out = []
    try:
        with open(MOUNTS) as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        w = line.split()
        if len(w) < 4 or not w[0].startswith("/"):
            continue
        dev = os.path.realpath(w[0])
        if dev in nodes or w[0] in nodes:
            out.append((dev, w[1].replace("\\040", " "),
                        "rw" in w[3].split(",")))
    name = os.path.basename(os.path.realpath(path))
    for n in sorted(nodes):
        b = os.path.basename(n)
        for d in (os.path.join(SYSFS, "block", b),
                  os.path.join(SYSFS, "block", name, b)):
            for h in glob.glob(os.path.join(d, "holders", "*")):
                out.append((n, "held by " + os.path.basename(h), True))
    return out


class Disk:
    def __init__(self, path, write=False):
        self.path = path
        st = os.stat(path)
        self.block = stat.S_ISBLK(st.st_mode)
        if not self.block and not stat.S_ISREG(st.st_mode):
            raise RepairError("%s is neither a disk nor an image file" % path)
        if self.block:
            why = device_problem(path)
            if why:
                raise RepairError(why)
            if write and os.geteuid() != 0:
                raise RepairError("writing %s needs root (sudo): nothing "
                                  "written" % path)
        flags = os.O_RDONLY
        if write:
            # exclusive: no mount or other program may hold the disk
            flags = os.O_RDWR | (os.O_EXCL if self.block else 0)
        try:
            self.fd = os.open(path, flags)
        except OSError as e:
            raise RepairError("%s: %s%s" % (path, e.strerror,
                              " (in use: mounted, or another program has "
                              "it)" if e.errno == 16 else ""))
        self.size = os.lseek(self.fd, 0, os.SEEK_END)
        self.sectors = self.size // SECTOR

    def read(self, off, n):
        out = bytearray()
        while len(out) < n:
            b = os.pread(self.fd, min(CHUNK, n - len(out)), off + len(out))
            if not b:
                raise RepairError("%s: short read at %d" % (self.path,
                                                           off + len(out)))
            out += b
        return bytes(out)

    def chunks(self, off, n):
        done = 0
        while done < n:
            b = self.read(off + done, min(CHUNK, n - done))
            done += len(b)
            yield b

    def sha256(self, off, n):
        h = hashlib.sha256()
        for b in self.chunks(off, n):
            h.update(b)
        return h.hexdigest()

    def write(self, off, data):
        view = memoryview(data)
        done = 0
        while done < len(view):
            done += os.pwrite(self.fd, view[done:done + CHUNK], off + done)
        os.fsync(self.fd)

    def drop_cache(self):
        """So a read-back reads the eMMC, not this PC's page cache."""
        os.fsync(self.fd)
        if self.block:
            fcntl.ioctl(self.fd, BLKFLSBUF, 0)
        os.posix_fadvise(self.fd, 0, 0, os.POSIX_FADV_DONTNEED)

    def partition_node(self, n):
        """/dev/sdXN when the kernel made one (it read a good GPT)."""
        if not self.block:
            return None
        base = os.path.realpath(self.path)
        p = "%s%s%d" % (base, "p" if base[-1].isdigit() else "", n)
        return p if os.path.exists(p) else None

    def ext4_target(self, off):
        """The ext4 at byte @off for e2fsprogs: "DISK?offset=N"."""
        return "%s?offset=%d" % (self.path, off)


def open_disk(arg, write=False):
    if arg:
        path = arg
    else:
        found = kiln_disks()
        if not found:
            raise RepairError("no AD5X eMMC on this PC: start the printer "
                              "over USB (docs/emmc-repair.md), or name it "
                              "with --disk")
        if len(found) > 1:
            raise RepairError("more than one AD5X eMMC (%s): choose with "
                              "--disk" % ", ".join(found))
        path = found[0]
    if os.path.exists(path) and stat.S_ISBLK(os.stat(path).st_mode):
        why = device_problem(path)
        if why:
            raise RepairError(why)
        used = in_use(path)
        bad = [u for u in used if write or u[2]]
        if bad:
            raise RepairError(
                "%s is in use: %s. Unmount it first (a desktop mounts the "
                "printer's ext4 partitions by itself; udisksctl unmount -b "
                "NODE): %s" % (path, ", ".join("%s on %s" % u[:2] for u in
                                               bad),
                               "nothing written" if write else
                               "a read of a mounted file system isn't "
                               "consistent"))
        for u in used:
            print("note: %s is mounted read-only on %s" % u[:2])
    return Disk(path, write)


# ---- what is on it ----

def crc32(b):
    return binascii.crc32(b) & 0xffffffff


def parse_gpt(disk, lba):
    """The GPT header at @lba and its entries: dict, or a string saying
    what is wrong."""
    if lba <= 0 or lba >= disk.sectors:
        return "LBA %d is outside the disk" % lba
    h = disk.read(lba * SECTOR, SECTOR)
    (sig, _, hsz, hcrc, _, cur, alt, first, last, guid, elba, n, esz,
     ecrc) = struct.unpack_from("<8sIIIIQQQQ16sQIII", h)
    if sig != b"EFI PART":
        return "no GPT header"
    if hsz < 92 or hsz > SECTOR:
        return "header size %d" % hsz
    hb = bytearray(h[:hsz])
    struct.pack_into("<I", hb, 16, 0)
    if crc32(bytes(hb)) != hcrc:
        return "header CRC wrong"
    if cur != lba or not 0 < n <= 128 or esz != 128 or \
            elba + (n * esz + SECTOR - 1) // SECTOR > disk.sectors:
        return "header fields don't fit"
    ents = disk.read(elba * SECTOR, n * esz)
    if crc32(ents) != ecrc:
        return "entries CRC wrong"
    parts = {}
    for i in range(n):
        e = ents[i * esz:(i + 1) * esz]
        if e[:16] == bytes(16):
            continue
        s, end = struct.unpack_from("<QQ", e, 32)
        parts[i + 1] = (e[56:128].decode("utf-16le", "replace").split("\0")[0],
                        s, end)
    return dict(raw=h[:hsz], alt=alt, first=first, last=last, guid=guid,
                elba=elba, n=n, esz=esz, ents=ents, parts=parts)


layout_problems = img.layout_problems


def disk_gpt(disk):
    """The disk's GPT: the primary, else the backup at the last sector;
    None when neither is good."""
    for lba in (1, disk.sectors - 1):
        g = parse_gpt(disk, lba)
        if not isinstance(g, str):
            return g
    return None


def part_extent(g, n):
    """(byte offset, bytes) of partition @n: from the GPT, or stock's."""
    if g and n in g["parts"]:
        _, s, e = g["parts"][n]
        return s * SECTOR, (e - s + 1) * SECTOR
    _, _, s, cnt = PARTS[n - 1]
    if not cnt:
        return None
    return s * SECTOR, cnt * SECTOR


def uimage_info(b):
    """'name, N bytes' of a good uImage, or a string with what is wrong
    (prefixed 'BAD: ')."""
    try:
        name = img.check_uimage(b, "kernel")
    except img.ImageError as e:
        return "BAD: " + str(e).split(": ", 1)[1]
    size = struct.unpack(">I", b[12:16])[0]
    return "%s, %d bytes" % (name.decode(errors="replace"), size)


def ext4_bytes(disk, off):
    """The size of the ext4 at @off, or None without one."""
    sb = disk.read(off + 1024, 1024)
    if struct.unpack_from("<H", sb, 56)[0] != EXT4_MAGIC:
        return None
    blocks = struct.unpack_from("<I", sb, 4)[0] | \
        (struct.unpack_from("<I", sb, 0x150)[0] << 32
         if struct.unpack_from("<I", sb, 0x60)[0] & 0x80 else 0)
    return blocks * (1024 << struct.unpack_from("<I", sb, 24)[0])


def ext4_info(disk, off, part_bytes):
    """(ok, text) for the ext4 superblock at @off."""
    sb = disk.read(off + 1024, 1024)
    if struct.unpack_from("<H", sb, 56)[0] != EXT4_MAGIC:
        return False, "no ext4 superblock"
    blocks = struct.unpack_from("<I", sb, 4)[0] | \
        (struct.unpack_from("<I", sb, 0x150)[0] << 32
         if struct.unpack_from("<I", sb, 0x60)[0] & 0x80 else 0)
    bsize = 1024 << struct.unpack_from("<I", sb, 24)[0]
    label = sb[120:136].split(b"\0")[0].decode(errors="replace")
    fs = blocks * bsize
    if fs > part_bytes:
        return False, ("ext4 '%s' of %d bytes is larger than its partition "
                       "(%d): the kernel won't mount it" % (label, fs,
                                                            part_bytes))
    return True, "ext4 '%s', %.1f GiB" % (label, fs / 2**30)


def debugfs_cat(target, path):
    if not shutil.which("debugfs"):
        return None
    r = subprocess.run(["debugfs", "-c", "-R", "cat " + path, target],
                       capture_output=True)
    if r.returncode or not r.stdout:
        return None
    return r.stdout.decode(errors="replace").splitlines()[0].strip()


def debugfs_file(target, path):
    """The bytes of @path in the ext4 @target, or None."""
    if not shutil.which("debugfs"):
        return None
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "f")
        subprocess.run(["debugfs", "-c", "-R", "dump %s %s" % (path, out),
                        target], capture_output=True)
        if not os.path.exists(out):
            return None
        with open(out, "rb") as f:
            return f.read()


def mac_or_none(text):
    return text if text and re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}",
                                         text) else None


def part_file(disk, g, n, path):
    """@path in the ext4 of partition @n of the disk, or None."""
    ext = part_extent(g, n)
    if not ext or not ext4_info(disk, *ext)[0]:
        return None
    return debugfs_file(disk.ext4_target(ext[0]), path)


def usershare_mac(disk, g):
    """usershare's /MAC on the disk (debugfs at the partition's offset: no
    partition node needed), or None."""
    ext = part_extent(g, USERSHARE)
    if not ext4_info(disk, *ext)[0]:
        return None
    return mac_or_none(debugfs_cat(disk.ext4_target(ext[0]), "/MAC"))


def e2fsck(node, deep):
    if not node or not shutil.which("e2fsck"):
        return None
    r = subprocess.run(["e2fsck", "-n"] + (["-f"] if deep else []) + [node],
                       capture_output=True, text=True)
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    return r.returncode, lines[-1:]


# ---- the first MiB: this printer's stock one, Kiln's boot loader ----

def fingerprint(mib):
    """(SPL, DDR) fingerprint of a first MiB's stock SPL, as
    lib/bootloader.sh's bl_fp_spl and the DDR line print them: the first 16
    hex digits of the sha256 of 0x4400-0xA3FF with 0x4480-0x4483 read as
    zeros (USBCloner's stamp), and of the 188 bytes from the DDR table's
    name W634GU6QG-11 (None when the SPL has no such table)."""
    r = bytearray(mib[img.SPL_OFF:img.UBOOT_OFF])
    r[0x80:0x84] = bytes(4)
    fp = sha256_bytes(bytes(r))[:16]
    o = bytes(mib[img.SPL_OFF:img.UBOOT_OFF]).find(DDR_NAME)
    ddr = None
    if 0 <= o <= len(r) - DDR_LEN:
        ddr = sha256_bytes(bytes(mib[img.SPL_OFF + o:img.SPL_OFF + o +
                                     DDR_LEN]))[:16]
    return fp, ddr


def same_printer(cand, disk):
    """Why the stock first MiB @cand isn't this disk's (another printer's,
    or the GPT changed since), or None. Its GPT (header and entries) must
    be the disk's primary; with no good primary the disk's backup GPT where
    @cand has it must have the same disk GUID and entries."""
    cg = img.first_gpt(cand)
    end = cg["elba"] * SECTOR + cg["n"] * cg["esz"]
    dg = parse_gpt(disk, 1)
    if not isinstance(dg, str):
        if disk.read(SECTOR, end - SECTOR) != cand[SECTOR:end]:
            return "its GPT isn't the disk's (another printer's, or the GPT " \
                "changed since it was saved)"
        return None
    if cg["alt"] < disk.sectors:
        bg = parse_gpt(disk, cg["alt"])
        if not isinstance(bg, str):
            if bg["guid"] != cg["guid"] or bg["ents"] != cg["ents"]:
                return "the disk's backup GPT has another disk GUID or " \
                    "entries (another printer's)"
            return None
    print("note: the disk has no readable GPT to compare %s with" % "it")
    return None


def stock_sources(disk, g, stock_arg=None, backup=None, image=None):
    """[(description, bytes or why-not)]: where this printer's stock first
    MiB (boot.img) may be, in this order: --stock-mib, the backup's
    boot.img, the disk's own first MiB (while it holds Flashforge's SPL),
    /data/ad5x/stock/boot.img, usershare's kiln-stock-backup/boot.img, the
    image's stock-boot.img."""
    out = []
    if stock_arg:
        try:
            b, d = img.load_stock_mib(stock_arg)
            out.append(("--stock-mib " + d, b))
        except (img.ImageError, OSError) as e:
            raise RepairError("--stock-mib: %s" % e)
    if backup:
        p = os.path.join(backup, "boot.img")
        if os.path.exists(p) or os.path.exists(p + ".000"):
            out.append(("the backup's boot.img", file_bytes(p)))
    cur = disk.read(0, FIRST_MIB)
    if img.spl_loader(cur) == "flashforge":
        out.append(("the disk's own first MiB (Flashforge's SPL)", cur))
    for n, d, where in ((USERDATA, "/ad5x/stock", "/data/ad5x/stock/boot.img"),
                        (USERSHARE, "/kiln-stock-backup",
                         "usershare's kiln-stock-backup/boot.img")):
        b = part_file(disk, g, n, d + "/boot.img")
        if b is None:
            continue
        s = part_file(disk, g, n, d + "/boot.img.sha256")
        want = s.split()[0].decode(errors="replace") if s and s.split() \
            else None
        if want != sha256_bytes(b):
            out.append((where, "its boot.img.sha256 is missing or differs"))
        else:
            out.append((where, b))
    if image:
        p = os.path.join(image, "stock-boot.img")
        sums = read_sums(image)
        if os.path.exists(p) and "stock-boot.img" in sums:
            b = file_bytes(p)
            out.append(("the image's stock-boot.img",
                        b if sha256_bytes(b) == sums["stock-boot.img"] else
                        "doesn't match SHA256SUMS"))
    return out


def find_stock(disk, g, quiet=False, **kw):
    """(bytes, description) of this printer's stock first MiB, or (None,
    None); says what each source was and why one wasn't used."""
    for desc, b in stock_sources(disk, g, **kw):
        why = b if isinstance(b, str) else img.stock_mib_problem(b) or \
            same_printer(b, disk)
        if why:
            if not quiet:
                print("stock first MiB: %s: not used: %s" % (desc, why))
            continue
        return b, desc
    return None, None


def first_mib_for(a, disk, g, release_first):
    """The first MiB to write for --image: (bytes, kind, description, stock
    first MiB or None). kind: "stock" (this printer's boot.img with the
    release's SPL and U-Boot in it), "disk" (the disk's own first MiB, no
    boot.img found), "generated" (the image's own)."""
    try:
        spl_img, uboot = img.boot_images(release_first)
    except img.ImageError as e:
        raise RepairError("%s/00-first-mib.bin: %s" % (a.image, e))
    stock, desc = find_stock(disk, g, stock_arg=a.stock_mib, image=a.image)
    if stock is not None:
        return (img.compose_first_mib(stock, spl_img, uboot), "stock",
                "this printer's own first MiB (%s) with the release's SPL "
                "and U-Boot" % desc, stock)
    cur = disk.read(0, FIRST_MIB)
    cg = img.first_gpt(cur)
    if img.spl_loader(cur) == "kiln" and not isinstance(cg, str) and \
            not img.layout_problems(cg) and cur[:4] == spl.PARAMS_ID:
        try:
            out = img.compose_first_mib(cur, spl_img, uboot)
            print(LOUD % ("No stock first MiB (boot.img) of this printer "
                          "found: the disk's own first MiB is kept (its GPT "
                          "and boot ROM block), Kiln's SPL and U-Boot "
                          "replaced. ad5x-bootloader-install's upgrade and "
                          "Return to Flashforge firmware's --flashforge-spl "
                          "need boot.img: give --stock-mib if you have it."))
            return out, "disk", "the disk's own first MiB with the release's " \
                "SPL and U-Boot (no boot.img found)", None
        except img.ImageError:
            pass
    print(LOUD % ("No stock first MiB (boot.img) of this printer found: the "
                  "image's GENERATED first MiB is written (a new GPT, new "
                  "GUIDs, userdata to the end of the eMMC). Afterwards "
                  "ad5x-bootloader-install can't upgrade Kiln's boot loader "
                  "and Return to Flashforge firmware can't put Flashforge's "
                  "SPL back. Give --stock-mib (this printer's boot.img) if "
                  "you have it."))
    return release_first, "generated", "the image's generated first MiB", None


LOUD = ("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        "!! %s\n"
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")


def gpt_fit_problem(first, disk):
    """Why the GPT in @first (a first MiB to write) doesn't fit this disk:
    from an eMMC of another size. None when its backup GPT is at the last
    sector, or where this disk's own GPT has it (stock's layout on 58 GiB
    eMMCs doesn't reach the end)."""
    g = img.first_gpt(first)
    if isinstance(g, str):
        return "it has no usable GPT (%s)" % g
    alt = g["alt"]
    if alt >= disk.sectors or g["last"] >= alt or \
            any(e >= alt for _, _, e in g["parts"].values()):
        return ("its GPT is for a larger eMMC (backup GPT at LBA %d; this "
                "one has %d sectors)" % (alt, disk.sectors))
    if alt == disk.sectors - 1:
        return None
    p = parse_gpt(disk, 1)
    if not isinstance(p, str) and p["alt"] == alt:
        return None
    b = parse_gpt(disk, alt)
    if not isinstance(b, str) and b["alt"] == 1:
        return None
    return ("its backup GPT is at LBA %d, not at this eMMC's end (LBA %d) "
            "nor where this eMMC's own GPT has it: from an eMMC of another "
            "size" % (alt, disk.sectors - 1))


# ---- release images ----

def image_pieces(d):
    """ad5x_emmc_image.py's output: [(name, offset, path, sha256)]."""
    sums = read_sums(d)
    out = []
    for f, sha in sums.items():
        key = f if f in IMAGE_FILES else f.split("-")[0]
        if key not in IMAGE_FILES:
            continue
        name, off = IMAGE_FILES[key]
        out.append((name, off, os.path.join(d, f), sha))
    if not any(p[0] == "first-mib" for p in out):
        raise RepairError("%s: no 00-first-mib.bin in SHA256SUMS" % d)
    return sorted(out, key=lambda p: p[1])


def read_sums(d):
    try:
        with open(os.path.join(d, "SHA256SUMS")) as f:
            lines = f.read().split("\n")
    except OSError as e:
        raise RepairError("%s: no SHA256SUMS (%s)" % (d, e.strerror))
    sums = {}
    for line in lines:
        if line.strip():
            sha, f = line.split(None, 1)
            sums[f.strip().lstrip("*")] = sha
    return sums


def file_sha(path):
    h = hashlib.sha256()
    for part in pieces_of(path):
        with open(part, "rb") as f:
            for b in iter(lambda: f.read(CHUNK), b""):
                h.update(b)
    return h.hexdigest()


def pieces_of(path):
    """NAME.img, or NAME.img.000, .001... as ad5x-backup splits on FAT."""
    if os.path.exists(path):
        return [path]
    parts = sorted(glob.glob(path + ".[0-9][0-9][0-9]"))
    if not parts:
        raise RepairError("%s: missing" % path)
    return parts


def file_bytes(path):
    out = bytearray()
    for p in pieces_of(path):
        with open(p, "rb") as f:
            out += f.read()
    return bytes(out)


# ---- commands ----

def cmd_find(a):
    found = kiln_disks()
    if not found:
        print("no AD5X eMMC on this PC (USB 1d6b:0104 from Kiln OS); "
              "start the printer over USB: docs/emmc-repair.md")
        return 1
    for d in found:
        n = os.path.basename(d)
        size = int(open(os.path.join(SYSFS, "block", n, "size")).read()) * \
            SECTOR
        used = in_use(d)
        print("%s  %.1f GiB  AD5X eMMC over USB (Kiln's U-Boot)%s" %
              (d, size / 2**30, "; mounted: " + ", ".join(
                  "%s on %s" % u[:2] for u in used) if used else ""))
    return 0


class Report:
    def __init__(self):
        self.bad = []

    def line(self, ok, what, text):
        mark = {True: "ok ", False: "BAD", None: "-- "}[ok]
        print("%s  %-16s %s" % (mark, what, text))
        if ok is False:
            self.bad.append(what)


def cmd_check(a):
    disk = open_disk(a.disk)
    r = Report()
    print("%s: %.1f GiB" % (disk.path, disk.size / 2**30))
    rel = {}
    if a.image:
        for name, off, path, sha in image_pieces(a.image):
            rel[name] = (off, path, sha)

    # GPT
    g = parse_gpt(disk, 1)
    if isinstance(g, str):
        r.line(False, "GPT (primary)", g)
        b = parse_gpt(disk, disk.sectors - 1)
        r.line(not isinstance(b, str), "GPT (backup)",
               b if isinstance(b, str) else "good, at the last sector")
        g = None if isinstance(b, str) else b
    else:
        lp = layout_problems(g)
        r.line(not lp, "GPT (primary)", "; ".join(lp) or
               "good, stock's layout, p7 %.1f GiB" %
               ((g["parts"][7][2] - g["parts"][7][1] + 1) * SECTOR / 2**30))
        b = parse_gpt(disk, g["alt"])
        if isinstance(b, str):
            r.line(False, "GPT (backup)", "at LBA %d: %s" % (g["alt"], b))
        else:
            r.line(b["ents"] == g["ents"], "GPT (backup)",
                   "good" if b["ents"] == g["ents"] else
                   "entries differ from the primary's")
        if g["alt"] != disk.sectors - 1:
            r.line(None, "GPT (backup)", "not at the end of the disk (LBA %d "
                   "of %d): userdata could be larger (restore --grow-data; "
                   "the disk then differs from boot.img)" %
                   (g["alt"], disk.sectors))

    # first MiB
    mib = disk.read(0, FIRST_MIB)
    r.line(mib[0:4] == spl.PARAMS_ID, "boot ROM params",
           "INGE at 0" if mib[0:4] == spl.PARAMS_ID else
           "no INGE at 0: the boot ROM won't start from the eMMC")
    magic, count, _ = spl.decode(mib[spl.SPL_EMMC_OFF:], 0)
    kind = {"kiln": "Kiln's", "flashforge": "Flashforge's"}.get(
        img.spl_loader(mib), "unknown")
    ok = magic == spl.SPL_MAGIC and 0 < count <= spl.MAX_BLOCKS
    r.line(ok, "SPL", "%s, %d blocks" % (kind, count) if ok else
           "no SPL header at 0x4400: the boot ROM falls to USB mode")
    ub = mib[spl.UBOOT_EMMC_OFF:]
    if struct.unpack(">I", ub[:4])[0] == img.UIMAGE_MAGIC:
        info = uimage_info(ub)
        r.line(not info.startswith("BAD"), "U-Boot", info)
    else:
        r.line(None, "U-Boot", "no uImage at 0xA400 (Flashforge's raw one, "
               "or none: Kiln's SPL then starts the slot's kernel itself)")
    if "first-mib" in rel:
        want = file_bytes(rel["first-mib"][1])
        try:
            s_img, u_img = img.boot_images(want)
            same = mib[img.SPL_OFF:img.SPL_OFF + 256] == s_img[:256] and \
                mib[img.SPL_OFF + 512:img.SPL_OFF + len(s_img)] == \
                s_img[512:] and \
                mib[img.UBOOT_OFF:img.UBOOT_OFF + len(u_img)] == u_img
        except img.ImageError:
            same = False
        r.line(same, "boot loader", "the release's" if same else
               "differs from the release's SPL/U-Boot")
    stock, desc = find_stock(disk, g, quiet=True,
                             image=a.image if a.image else None)
    if stock is not None:
        r.line(None, "stock first MiB", "%s: restore builds Kiln's boot "
               "loader into it" % desc)
    else:
        r.line(None, "stock first MiB", "none found (boot.img): restore "
               "keeps the disk's own first MiB or writes a generated one; "
               "--stock-mib gives it")

    # kernels, roots, flag
    for n in (1, 3):
        off, size = part_extent(g, n)
        info = uimage_info(disk.read(off, min(size, 8 * MIB)))
        r.line(not info.startswith("BAD"), "p%d %s" % (n, PARTS[n - 1][1]),
               info)
    for n in (2, 4):
        off, size = part_extent(g, n)
        sb = disk.read(off, 96)
        if sb[:4] != img.SQUASHFS_MAGIC:
            r.line(False, "p%d %s" % (n, PARTS[n - 1][1]),
                   "no SquashFS superblock")
            continue
        used = struct.unpack_from("<Q", sb, 40)[0]
        text = "SquashFS, %.1f MiB" % (used / MIB)
        ok = used <= size
        if ok and "p%d" % n in rel:
            _, path, sha = rel["p%d" % n]
            same = disk.sha256(off, os.path.getsize(path)) == sha
            text += ", the release's bytes" if same else \
                ", NOT the release's bytes"
            ok = same
        r.line(ok, "p%d %s" % (n, PARTS[n - 1][1]), text)
    off, _ = part_extent(g, 5)
    flag = disk.read(off, 16).split(b"\0")[0].split(b"\n")[0]
    r.line(flag in (b"ota:kernel", b"ota:kernel2"), "p5 ota",
           "boot flag %r" % flag.decode(errors="replace"))

    # usershare, userdata
    off, size = part_extent(g, USERSHARE)
    ok, text = ext4_info(disk, off, size)
    if ok:
        mac = usershare_mac(disk, g)
        text += ", /MAC %s" % mac if mac else ", /MAC not read (debugfs)"
        if part_file(disk, g, USERSHARE, "/KILN-GENERATED.txt") is not None:
            text += ", generated by ad5x_usershare.py (not the factory's)"
        fs = e2fsck(disk.partition_node(USERSHARE), a.deep)
        if fs:
            ok = fs[0] == 0
            text += "; e2fsck -n: %s" % (" ".join(fs[1]) or fs[0])
    r.line(ok, "p6 usershare", text)
    ext = part_extent(g, USERDATA)
    if ext:
        ok, text = ext4_info(disk, *ext)
        fs = e2fsck(disk.partition_node(USERDATA), a.deep) if ok else None
        if fs:
            ok = fs[0] == 0
            text += "; e2fsck -n: %s" % (" ".join(fs[1]) or fs[0])
        r.line(ok, "p7 userdata", text)
    else:
        r.line(False, "p7 userdata", "no GPT to find it")

    print()
    if not r.bad:
        print("check: nothing found wrong")
        return 0
    print("check: wrong: %s" % ", ".join(r.bad))
    if "p6 usershare" in r.bad:
        print("  usershare: only this printer's own backup has it "
              "(restore --backup DIR --usershare); docs/emmc-repair.md")
    print("  restore --image DIR (a release's ad5x_emmc_image.py files) "
          "rewrites the rest and keeps /data; --new-data for a new one")
    return 2


def fs_type(path):
    """The file system type of the mount holding @path (/proc/mounts)."""
    best, typ = "", None
    p = os.path.realpath(path)
    try:
        with open(MOUNTS) as f:
            for line in f:
                w = line.split()
                if len(w) >= 3:
                    m = w[1].replace("\\040", " ")
                    if (p == m or p.startswith(m.rstrip("/") + "/")) and \
                            len(m) > len(best):
                        best, typ = m, w[2]
    except OSError:
        pass
    return typ


def slot_holds(path):
    """What a backup's rootfs image is, as recovery.sh's rc_slot_holds:
    "recovery RELEASE", "ad5x RELEASE", "stock", "empty", "unknown"."""
    with open(pieces_of(path)[0], "rb") as f:
        if f.read(4) != img.SQUASHFS_MAGIC:
            return "empty"
    if not shutil.which("unsquashfs"):
        return "unknown (no unsquashfs)"
    if len(pieces_of(path)) > 1:
        return "unknown (in pieces)"

    def cat(p):
        r = subprocess.run(["unsquashfs", "-cat", path, p],
                           capture_output=True)
        return r.stdout.decode(errors="replace").strip() if \
            r.returncode == 0 else None
    rel = cat("etc/ad5x-release")
    if cat("etc/ad5x-recovery") is not None:
        return "recovery %s" % (rel or "")
    if rel is not None:
        return "ad5x %s" % rel
    if cat("etc/ota_bin/ota_local_method.sh") is not None:
        return "stock"
    return "unknown"


def cmd_backup(a):
    disk = open_disk(a.disk)
    g = parse_gpt(disk, 1)
    if isinstance(g, str):
        print("backup: primary GPT %s: stock's layout used" % g)
        g = None
    items = [("boot", 0, FIRST_MIB)]
    for n, name, _, _ in PARTS:
        if n == USERDATA and not a.userdata:
            continue
        ext = part_extent(g, n)
        if not ext:
            raise RepairError("no extent for %s without a GPT" % name)
        items.append((name, ) + ext)
    total = sum(i[2] for i in items)
    free = shutil.disk_usage(a.dest).free
    if total + 64 * MIB > free:
        raise RepairError("%d MiB to copy, %d MiB free in %s" %
                          (total // MIB, free // MIB, a.dest))
    fat = fs_type(a.dest) in ("vfat", "msdos")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    i = 1
    while os.path.exists(os.path.join(a.dest, "ad5x-backup-%s-%d" % (stamp, i))):
        i += 1
    out = os.path.join(a.dest, "ad5x-backup-%s-%d" % (stamp, i))
    os.makedirs(out)
    sums, rows = [], []
    for name, off, size in items:
        h = hashlib.sha256()
        split = fat and size >= FAT_MAX
        files = []
        k = 0
        f = None
        done = 0
        for b in disk.chunks(off, size):
            h.update(b)
            while b:
                if f is None:
                    fn = "%s.img.%03d" % (name, k) if split else name + ".img"
                    files.append(fn)
                    f = open(os.path.join(out, fn), "wb")
                room = FAT_PIECE - done % FAT_PIECE if split else len(b)
                f.write(b[:room])
                done += min(room, len(b))
                b = b[room:]
                if split and done % FAT_PIECE == 0:
                    f.flush()
                    os.fsync(f.fileno())
                    f.close()
                    f, k = None, k + 1
        if f is not None:
            f.flush()
            os.fsync(f.fileno())
            f.close()
        sha = h.hexdigest()
        if file_sha(os.path.join(out, name + ".img")) != sha:
            raise RepairError("%s: the file doesn't read back as read" %
                              os.path.join(out, name + ".img"))
        sums.append("%s  %s.img" % (sha, name))
        rows.append("%s %s %d %d %s %s" % (name, disk.path, off // SECTOR,
                                           size, sha, " ".join(files)))
        print("backup: %-9s %12d bytes  %s%s" % (name, size, sha[:16],
                                                 " (%d pieces, FAT)" %
                                                 len(files) if split else ""))
    with open(os.path.join(out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    # MANIFEST.txt as ad5x-backup writes it: ad5x-return-stock takes a
    # backup as a stock source by its "running root: ..., slot X" line
    # (here the slot the boot flag names: nothing runs during a backup)
    off5, _ = part_extent(g, 5)
    flag = disk.read(off5, 16).split(b"\0")[0].split(b"\n")[0].decode(
        errors="replace")
    slot = "B" if flag == "ota:kernel2" else "A"
    mac = usershare_mac(disk, g)
    with open(os.path.join(out, "MANIFEST.txt"), "w") as f:
        f.write("AD5X eMMC backup (ad5x_emmc_repair.py, over USB), %s\n" %
                datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"))
        f.write("made by: ad5x_emmc_repair.py on a PC\n")
        f.write("running root: none (read over USB; the boot flag's slot), "
                "slot %s\n" % slot)
        f.write("boot flag: %s\n" % flag)
        f.write("disk: %s, %d bytes\n" % (disk.path, disk.size))
        f.write("slot A holds: %s\n" % slot_holds(os.path.join(out,
                                                               "rootfs.img")))
        f.write("slot B holds: %s\n" % slot_holds(os.path.join(out,
                                                               "rootfs2.img")))
        f.write("usershare /MAC: %s\n" % (mac or "not read"))
        f.write("# name device start_sector bytes sha256 files\n")
        f.write("\n".join(rows) + "\n")
    print("backup: OK %s" % out)
    return 0


def new_gpt_for(first, disk_sectors):
    """@first (a first MiB) with its GPT stretched to this disk: userdata
    to the end, the backup GPT in the last sectors. Returns (first MiB,
    backup entries + header, backup entries LBA, p7's sectors)."""
    first = bytearray(first)
    h = bytearray(first[SECTOR:2 * SECTOR])
    hsz = struct.unpack_from("<I", h, 12)[0]
    elba = struct.unpack_from("<Q", h, 72)[0]
    n, esz = struct.unpack_from("<II", h, 80)
    es = (n * esz + SECTOR - 1) // SECTOR
    ents = bytearray(first[elba * SECTOR:elba * SECTOR + n * esz])
    alt = disk_sectors - 1
    last = alt - es - 1
    o = (USERDATA - 1) * esz
    dstart = struct.unpack_from("<Q", ents, o + 32)[0]
    dend = dstart + (last - dstart + 1) // 8 * 8 - 1
    struct.pack_into("<Q", ents, o + 40, dend)
    ecrc = crc32(bytes(ents))

    def header(cur, other, el):
        b = bytearray(h[:hsz])
        struct.pack_into("<QQ", b, 24, cur, other)
        struct.pack_into("<Q", b, 48, last)
        struct.pack_into("<Q", b, 72, el)
        struct.pack_into("<I", b, 88, ecrc)
        struct.pack_into("<I", b, 16, 0)
        struct.pack_into("<I", b, 16, crc32(bytes(b)))
        return bytes(b).ljust(SECTOR, b"\0")

    first[SECTOR:2 * SECTOR] = header(1, alt, elba)
    first[elba * SECTOR:elba * SECTOR + len(ents)] = ents
    struct.pack_into("<I", first, 0x1ca, min(disk_sectors - 1, 0xffffffff))
    tail = bytes(ents).ljust(es * SECTOR, b"\0") + header(alt, 1, alt - es)
    return bytes(first), tail, alt - es, dend - dstart + 1


def p7_sectors_in(first):
    """Userdata's sectors in the GPT of @first (a first MiB), or None."""
    h = first[SECTOR:2 * SECTOR]
    if h[:8] != b"EFI PART":
        return None
    elba, n, esz = struct.unpack_from("<QII", h, 72)
    o = elba * SECTOR + (USERDATA - 1) * esz
    if o + esz > len(first):
        return None
    s, e = struct.unpack_from("<QQ", first, o + 32)
    return e - s + 1 if e >= s else None


def backup_gpt_from_primary(first, disk_sectors):
    """The backup GPT (entries + header) that goes with the primary in
    @first, at the LBA the primary names. None when the primary is bad."""
    h = first[SECTOR:2 * SECTOR]
    if h[:8] != b"EFI PART":
        return None
    hsz = struct.unpack_from("<I", h, 12)[0]
    _, _, _, _, _, cur, alt, _, _, _, elba, n, esz, ecrc = \
        struct.unpack_from("<8sIIIIQQQQ16sQIII", h)
    if cur != 1 or not 0 < alt < disk_sectors:
        return None
    es = (n * esz + SECTOR - 1) // SECTOR
    ents = first[elba * SECTOR:elba * SECTOR + n * esz]
    if crc32(ents) != ecrc:
        return None
    b = bytearray(h[:hsz])
    struct.pack_into("<QQ", b, 24, alt, 1)
    struct.pack_into("<Q", b, 72, alt - es)
    struct.pack_into("<I", b, 16, 0)
    struct.pack_into("<I", b, 16, crc32(bytes(b)))
    return (alt - es) * SECTOR, ents.ljust(es * SECTOR, b"\0") + \
        bytes(b).ljust(SECTOR, b"\0")


class Piece:
    """One write: name (first-mib, p1..p7), eMMC offset, the bytes (or a
    file until loaded), their sha256."""

    def __init__(self, name, off, src, sha):
        self.name, self.off, self.src, self.sha = name, off, src, sha
        self.data = None

    def load(self):
        if self.data is None:
            self.data = file_bytes(self.src)
            if sha256_bytes(self.data) != self.sha:
                raise RepairError("%s: not the bytes SHA256SUMS lists" %
                                  self.src)
        return self.data

    def set(self, data):
        self.data, self.sha = data, sha256_bytes(data)


def plan_restore(a, disk):
    """[Piece] in offset order (partitions), the first MiB among them."""
    want = None
    if a.parts:
        want = {BACKUP_NAMES.get(n, n) for n in a.parts.split(",")}
    plan = []
    if a.image:
        for name, off, path, sha in image_pieces(a.image):
            if name == "p%d" % USERSHARE and not a.usershare:
                continue
            plan.append(Piece(name, off, path, sha))
    else:
        sums = read_sums(a.backup)
        has = {f[:-4]: sha for f, sha in sums.items() if f.endswith(".img")}
        g = disk_gpt(disk)
        for bname, rname in BACKUP_NAMES.items():
            if bname not in has:
                continue
            if bname == "usershare" and not a.usershare:
                continue
            path = os.path.join(a.backup, bname + ".img")
            if rname == "first-mib":
                off = 0
            else:
                n = int(rname[1:])
                off = PARTS[n - 1][2] * SECTOR
                ext = part_extent(g, n)
                size = sum(os.path.getsize(p) for p in pieces_of(path))
                if ext and size > ext[1]:
                    raise RepairError("%s.img (%d bytes) is larger than %s "
                                      "on this eMMC (%d)" % (bname, size,
                                                             rname, ext[1]))
            plan.append(Piece(rname, off, path, has[bname]))
    if want is not None:
        unknown = want - {p.name for p in plan}
        if unknown:
            raise RepairError("--parts: nothing to write for %s" %
                              ", ".join(sorted(unknown)))
        plan = [p for p in plan if p.name in want]
    p7 = [p for p in plan if p.name == "p%d" % USERDATA]
    if p7 and not a.new_data:
        if want is not None and "p7" in want:
            raise RepairError("--parts p7 (userdata): /data is replaced only "
                              "with --new-data")
        plan.remove(p7[0])
    elif a.new_data and not p7:
        raise RepairError("--new-data: %s has no userdata to write" %
                          (a.image or a.backup))
    if a.usershare and not any(p.name == "p%d" % USERSHARE for p in plan):
        raise RepairError("--usershare: %s has no usershare" %
                          (a.image or a.backup))
    return sorted(plan, key=lambda p: p.off)


def check_usershare(disk, g, piece):
    """The MAC guard: refused when the eMMC's own usershare is usable and
    has another /MAC, or when that can't be told (no debugfs)."""
    if not shutil.which("debugfs"):
        raise RepairError("--usershare needs debugfs (e2fsprogs): without it "
                          "the eMMC's own /MAC can't be compared, and another "
                          "printer's usershare could replace this one's")
    data = piece.load()
    with tempfile.TemporaryDirectory() as td:
        t = os.path.join(td, "u.img")
        with open(t, "wb") as f:
            f.write(data)
        theirs = mac_or_none(debugfs_cat(t, "/MAC"))
        generated = debugfs_cat(t, "/KILN-GENERATED.txt") is not None
    if not theirs:
        raise RepairError("the usershare to write has no readable /MAC: "
                          "refused")
    ok, text = ext4_info(disk, *part_extent(g, USERSHARE))
    mine = usershare_mac(disk, g) if ok else None
    if mine and mine.lower() != theirs.lower():
        raise RepairError("the eMMC has a usable usershare with /MAC %s; "
                          "the one to write has %s: refused (it would "
                          "replace this printer's factory data)" %
                          (mine, theirs))
    if ok and not mine:
        print(LOUD % ("The eMMC's usershare has an ext4 (%s) but its /MAC "
                      "can't be read (damaged?): it is replaced by one with "
                      "/MAC %s. Make sure that is this printer's address." %
                      (text, theirs)))
    elif not ok:
        print("restore: the eMMC's usershare: %s; replaced" % text)
    if generated:
        print("restore: the usershare to write was made by ad5x_usershare.py "
              "(KILN-GENERATED.txt): Flashforge's firmware can't run from it")
    print("restore: usershare (/MAC %s)" % theirs)


def disk_loader(cur, disk):
    """(loader, note): whose SPL the disk holds; when its SPL can't be read
    (damaged), the one its kernel slots are for: Kiln's 6.6 in both (only
    Kiln's SPL starts it; under Flashforge's SPL Kiln OS keeps Flashforge's
    5.10 there), or Flashforge's 5.10 in both."""
    l = img.spl_loader(cur)
    if l != "unknown":
        return l, None
    ks = {img.kernel_kind(disk.read(PARTS[n - 1][2] * SECTOR, 8 * MIB))
          for n in (1, 3)}
    if ks == {"kiln"}:
        return "kiln", "the disk's SPL can't be read; both kernel slots hold " \
            "Kiln's 6.6, which only Kiln's SPL starts: taken as Kiln's"
    if ks == {"stock"}:
        return "flashforge", "the disk's SPL can't be read; both kernel " \
            "slots hold Flashforge's 5.10: taken as Flashforge's"
    return "unknown", None


def confirm_unsupported():
    """A typed confirmation, --yes or not (as ad5x-bootloader-install's
    --unsupported-board)."""
    if ask("type 'unsupported' to go on: ") != "unsupported":
        raise RepairError("not confirmed: nothing written")


def boot_rules(a, disk, plan, cur, stock):
    """ad5x-restore's rules for the first MiB and the kernel slots, and the
    opt-in for Kiln's own boot loader. Returns the stock first MiB to save
    to /data/ad5x/stock first (installing from Flashforge's SPL), or None."""
    cur_l, note = disk_loader(cur, disk)
    if note:
        print("restore: %s" % note)
    real_ff = img.spl_loader(cur) == "flashforge"
    fm = next((p for p in plan if p.name == "first-mib"), None)
    final = img.spl_loader(fm.data) if fm else cur_l
    say = {"kiln": "Kiln's SPL", "flashforge": "Flashforge's SPL",
           "unknown": "no SPL it knows"}
    save = None
    if fm and final == "kiln" and cur_l != "kiln":
        if not a.install_boot_loader:
            raise RepairError(
                "the disk holds %s: writing this first MiB installs Kiln's "
                "own boot loader (Kiln's SPL and U-Boot, opt-in and "
                "experimental, docs/own-boot-loader.md). Give "
                "--install-boot-loader for that, or leave the first MiB and "
                "the kernels out (--parts p2,p4,p5: the system only, under "
                "the boot loader that is there). Nothing written" %
                say[cur_l])
        base = cur if real_ff else stock
        if base is not None:
            fp = fingerprint(base)
            if fp in ALLOWLIST:
                print("restore: this board's stock SPL is on the allowlist "
                      "(%s %s: %s)" % (fp[0], fp[1], ALLOWLIST[fp]))
            elif not a.unsupported_board:
                raise RepairError(
                    "this board's stock SPL (fingerprint spl %s, ddr %s) is "
                    "not on the allowlist of boards Kiln's boot loader is "
                    "known to fit (lib/bootloader.sh; an X2600E (256 MiB) or "
                    "the 2025 SPL 00437 isn't on it). --unsupported-board "
                    "goes on anyway, at your own risk; please post the "
                    "fingerprint in djvalic/kiln-os#68. Nothing written" %
                    (fp[0], fp[1] or "none"))
            else:
                print(LOUD % ("--unsupported-board: spl %s, ddr %s is not on "
                              "the allowlist." % (fp[0], fp[1] or "none")))
                confirm_unsupported()
        else:
            print(LOUD % ("No stock first MiB of this printer to check the "
                          "board against the allowlist: Kiln's boot loader "
                          "goes on a board it may not fit."))
            if not a.unsupported_board:
                raise RepairError("no stock first MiB (boot.img) to check this "
                                  "board against the allowlist: "
                                  "--unsupported-board to go on anyway. "
                                  "Nothing written")
            confirm_unsupported()
        # step 0: this printer's boot.img on /data first
        save = cur if real_ff else stock
    elif a.install_boot_loader and not (fm and final == "kiln"):
        print("restore: --install-boot-loader: nothing to install (the "
              "first MiB isn't written, or isn't Kiln's)")
    # the slots as they end up, under the boot loader that ends up there
    kinds = {}
    for n in (1, 3):
        p = next((p for p in plan if p.name == "p%d" % n), None)
        kinds[n] = (img.kernel_kind(p.load()), True) if p else \
            (img.kernel_kind(disk.read(PARTS[n - 1][2] * SECTOR, 8 * MIB)),
             False)
    for n, (k, writing) in kinds.items():
        if not writing:
            continue
        if final == "kiln" and k != "kiln":
            raise RepairError(
                "p%d: the image is not Kiln's 6.6 (%s): under Kiln's boot "
                "loader no other kernel goes into a slot. Nothing written" %
                (n, k))
        if final == "flashforge" and k != "stock":
            raise RepairError(
                "p%d: Kiln's 6.6 (%s) into a slot needs Kiln's boot loader in "
                "the first MiB; the disk keeps %s. Give "
                "--install-boot-loader with the first MiB, or leave the "
                "kernels out (--parts p2,p4,p5). Nothing written" %
                (n, k, say["flashforge"]))
    if fm and final == "flashforge" and cur_l != "flashforge":
        for n, (k, _) in kinds.items():
            if k != "stock":
                raise RepairError(
                    "first-mib: Flashforge's boot loader goes back only over "
                    "Flashforge's 5.10 in both slots, and p%d holds %s: "
                    "restore kernel and kernel2 from a stock backup in the "
                    "same run (--parts first-mib,p1,p3). Nothing written" %
                    (n, k))
    return save


def write_checked(disk, name, off, data, sha):
    if disk.sha256(off, len(data)) == sha:
        print("restore: %-9s already the same, left alone" % name)
        return
    disk.write(off, data)
    disk.drop_cache()
    if disk.sha256(off, len(data)) != sha:
        raise RepairError("%s at 0x%x: doesn't read back as written; stop "
                          "here and run check" % (name, off))
    print("restore: %-9s %12d bytes at 0x%09x, read back: OK" %
          (name, len(data), off))


def write_first_mib(disk, data, sha):
    """The first MiB, its SPL's header sector (34) zeroed first and written
    last, as lib/bootloader.sh's bl_put_spl: the boot ROM checks only that
    header, so a cut at any moment leaves the old SPL whole, or no header
    (the boot ROM's USB mode: this repair again), or the new first MiB."""
    if disk.sha256(0, FIRST_MIB) == sha:
        print("restore: first-mib already the same, left alone")
        return
    h = SPL_LBA * SECTOR
    for off, b in ((h, bytes(SECTOR)), (0, data[:h]),
                   (h + SECTOR, data[h + SECTOR:]), (h, data[h:h + SECTOR])):
        disk.write(off, b)
        disk.drop_cache()
        if disk.read(off, len(b)) != b:
            raise RepairError("first-mib at 0x%x: doesn't read back as "
                              "written; don't switch the printer off, run "
                              "restore again" % off)
    if disk.sha256(0, FIRST_MIB) != sha:
        raise RepairError("first-mib: doesn't read back as written")
    print("restore: first-mib %12d bytes at 0x000000000, SPL header last, "
          "read back: OK" % FIRST_MIB)


def grow_userdata(disk):
    """The release's small /data to the whole of userdata: the kernel
    re-reads the GPT, then e2fsck and resize2fs on /dev/sdX7."""
    if not disk.block:
        print("restore: an image file: /data left at the release's size")
        return
    os.fsync(disk.fd)
    try:
        fcntl.ioctl(disk.fd, BLKRRPART, 0)
    except OSError as e:
        print("restore: the kernel didn't re-read the GPT (%s): /data left at "
              "the release's size; resize2fs on partition 7 grows it" %
              e.strerror)
        return
    node = None
    for _ in range(50):
        node = disk.partition_node(USERDATA)
        if node:
            break
        subprocess.run(["sleep", "0.1"])
    if not node or not shutil.which("resize2fs"):
        print("restore: /data not grown (no %s or no resize2fs): Kiln OS "
              "keeps the release's size" % (node or "partition 7"))
        return
    subprocess.run(["sleep", "1"])
    if any(u[0] == os.path.realpath(node) for u in in_use(disk.path)):
        print("restore: %s was mounted by this PC meanwhile: /data not grown "
              "(unmount it, then e2fsck -f and resize2fs %s)" % (node, node))
        return
    # e2fsck and resize2fs open the partition exclusively: not while this
    # tool holds the whole disk so
    os.close(disk.fd)
    disk.fd = None
    subprocess.run(["e2fsck", "-fy", node], capture_output=True)
    r = subprocess.run(["resize2fs", node], capture_output=True, text=True)
    print("restore: /data grown to its partition" if r.returncode == 0
          else "restore: resize2fs %s failed: %s" % (node, r.stderr.strip()))


def cmd_restore(a):
    disk = open_disk(a.disk, write=not a.dry_run)
    plan = plan_restore(a, disk)
    g = disk_gpt(disk)
    if g is not None:
        lp = [x for x in layout_problems(g) if not x.startswith("p7 ")]
        if lp:
            raise RepairError("%s has a partition table that isn't an AD5X "
                              "eMMC's (%s): refused, nothing written" %
                              (disk.path, "; ".join(lp)))
    cur = disk.read(0, FIRST_MIB)
    fm = next((p for p in plan if p.name == "first-mib"), None)
    if a.grow_data and not fm:
        raise RepairError("--grow-data changes the GPT: the first MiB must be "
                          "written too")
    # /data/ad5x/stock/boot.img, read before /data is replaced
    stock = None
    if a.image and fm:
        data, kind, what, stock = first_mib_for(a, disk, g, fm.load())
        fm.set(data)
    elif fm:
        kind, what = "backup", "the backup's first MiB, as it is"
        fm.load()
        stock = find_stock(disk, g, quiet=True, backup=a.backup)[0]
    else:
        stock = find_stock(disk, g, quiet=True, stock_arg=a.stock_mib,
                           backup=a.backup, image=a.image)[0]
    for p in plan:
        p.load()
    tail = None
    if fm:
        stretch = kind == "generated" or a.grow_data
        if kind == "backup" and not stretch and not a.new_data:
            # a backup's GPT from before userdata grew: the ext4 on the
            # eMMC then doesn't fit the backup's p7
            n7 = p7_sectors_in(fm.data)
            have = ext4_bytes(disk, PARTS[USERDATA - 1][2] * SECTOR)
            if n7 and have is not None and have > n7 * SECTOR:
                print("restore: /data on the eMMC is larger than userdata in"
                      " the backup's GPT: userdata to the end of the eMMC")
                stretch = True
        if stretch:
            data, gtail, tail_lba, p7_sectors = new_gpt_for(fm.data,
                                                            disk.sectors)
            if a.grow_data and kind != "generated":
                print(LOUD % ("--grow-data: the GPT is stretched to the end "
                              "of the eMMC. The disk then differs from "
                              "boot.img: ad5x-bootloader-install's upgrade "
                              "and Return to Flashforge firmware's "
                              "--flashforge-spl refuse it."))
            fm.set(data)
            tail = (tail_lba * SECTOR, gtail)
        else:
            why = gpt_fit_problem(fm.data, disk)
            if why:
                raise RepairError("first-mib: %s. --grow-data fits its GPT to "
                                  "this eMMC. Nothing written" % why)
            p7_sectors = p7_sectors_in(fm.data)
            tail = backup_gpt_from_primary(fm.data, disk.sectors)
        if not a.new_data:
            ok, text = ext4_info(disk, PARTS[USERDATA - 1][2] * SECTOR,
                                 (p7_sectors or 0) * SECTOR)
            if not ok:
                raise RepairError("/data kept: userdata in the new GPT: %s "
                                  "(--new-data for a new, empty /data). "
                                  "Nothing written" % text)
    us = next((p for p in plan if p.name == "p%d" % USERSHARE), None)
    if us:
        check_usershare(disk, g, us)
    save = boot_rules(a, disk, plan, cur, stock)
    p7 = next((p for p in plan if p.name == "p%d" % USERDATA), None)
    old_l = img.spl_loader(cur)
    new_l = img.spl_loader(fm.data) if fm else old_l
    # the first MiB: last, or before the kernels when Kiln's boot loader
    # is installed (Kiln's SPL starts Flashforge's 5.10 as well as its
    # 6.6; Flashforge's SPL has never started Kiln's 6.6)
    order = [p for p in plan if p is not fm]
    if fm:
        if save is not None:
            # this printer's boot.img on /data before Kiln's SPL: the new
            # /data first when it is replaced, else saved to the old one
            first = [p7] if p7 else []
            order = first + [fm] + [p for p in order if p is not p7]
        else:
            order.append(fm)

    print("restore: %s, %.1f GiB" % (disk.path, disk.size / 2**30))
    if fm:
        print("  first MiB: %s" % what)
    if save is not None and not p7:
        print("  /data/ad5x/stock/boot.img <- the disk's first MiB "
              "(Flashforge's SPL), first")
    for p in order:
        print("  %-9s %12d bytes at 0x%09x" % (p.name, len(p.data), p.off))
    if p7 and stock is not None:
        print("  /data/ad5x/stock/boot.img into the new /data")
    if tail:
        print("  %-9s %12d bytes at 0x%09x" % ("GPT copy", len(tail[1]),
                                             tail[0]))
    if not us:
        print("  usershare (p6) is not written")
    print("  /data (p7): %s" % ("replaced" if p7 else "kept"))
    if a.dry_run:
        pieces = [(p.name, p.off, p.data, p.sha) for p in order] + \
            ([("GPT copy", tail[0], tail[1], sha256_bytes(tail[1]))]
             if tail else [])
        for name, off, data, sha in pieces:
            same = disk.sha256(off, len(data)) == sha
            print("restore: %-9s %s" % (name, "the same already" if same
                                        else "would be written"))
        print("restore: dry run, nothing written")
        return 0
    if not a.yes:
        if ask("write these? type yes: ") != "yes":
            print("restore: nothing written")
            return 1
    if save is not None and not p7:
        save_boot_img(disk, g, save)
    for p in order:
        if p is fm:
            write_first_mib(disk, p.data, p.sha)
            if tail:
                write_checked(disk, "GPT copy", tail[0], tail[1],
                              sha256_bytes(tail[1]))
        else:
            write_checked(disk, p.name, p.off, p.data, p.sha)
            if p is p7 and stock is not None:
                try:
                    img.put_boot_img(disk.ext4_target(p.off), stock)
                    print("restore: boot.img in the new /data/ad5x/stock")
                except img.ImageError as e:
                    if save is not None:
                        raise RepairError("%s: Kiln's SPL not written" % e)
                    print("restore: WARNING: boot.img not put into the new "
                          "/data: %s" % e)
    if p7 and a.image:
        grow_userdata(disk)
    if fm and old_l != new_l:
        print("restore: the boot loader changed (%s -> %s)" % (old_l, new_l))
    if fm and not p7:
        print("restore: /data was kept: in the recovery OS run "
              "ad5x-bootloader-install --status and ad5x-return-stock --status"
              " (their records may describe the first MiB from before)")
    print("restore: OK; run check, then start the printer (power cycle)")
    return 0


def save_boot_img(disk, g, stock):
    """Step 0 of installing Kiln's boot loader (ad5x-bootloader-install's):
    this printer's first MiB (Flashforge's SPL) to /data/ad5x/stock before
    anything is written, unless the same is there already."""
    have = part_file(disk, g, USERDATA, "/ad5x/stock/boot.img")
    if have == stock:
        print("restore: /data/ad5x/stock/boot.img is the disk's first MiB "
              "already")
        return
    if have is not None and img.stock_mib_problem(have) is None:
        raise RepairError("/data/ad5x/stock/boot.img differs from the disk's "
                          "first MiB (another printer's?): move it away first."
                          " Nothing written")
    ext = part_extent(g, USERDATA)
    if not ext or not ext4_info(disk, *ext)[0]:
        raise RepairError("no /data (p7 ext4) to save boot.img in: give "
                          "--new-data (the new /data gets it). Nothing "
                          "written")
    try:
        img.put_boot_img(disk.ext4_target(ext[0]), stock)
    except img.ImageError as e:
        raise RepairError("saving boot.img to /data/ad5x/stock: %s. Nothing "
                          "else written" % e)
    print("restore: /data/ad5x/stock/boot.img <- the disk's first MiB, read "
          "back: OK")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("find")
    c = sub.add_parser("check")
    c.add_argument("--disk")
    c.add_argument("--image", help="a release's ad5x_emmc_image.py files")
    c.add_argument("--deep", action="store_true", help="e2fsck -f")
    b = sub.add_parser("backup")
    b.add_argument("--disk")
    b.add_argument("--userdata", action="store_true")
    b.add_argument("dest")
    r = sub.add_parser("restore")
    r.add_argument("--disk")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("--image")
    src.add_argument("--backup")
    data = r.add_mutually_exclusive_group()
    data.add_argument("--keep-data", action="store_true",
                      help="keep /data (the default)")
    data.add_argument("--new-data", action="store_true",
                      help="replace /data: the image's new, empty one, or "
                      "the backup's userdata.img")
    r.add_argument("--grow-data", action="store_true",
                   help="stretch the GPT: userdata to the end of the eMMC "
                   "(the disk then differs from boot.img)")
    r.add_argument("--parts")
    r.add_argument("--usershare", action="store_true")
    r.add_argument("--stock-mib", metavar="SOURCE",
                   help="this printer's stock first MiB (boot.img, a folder "
                   "with one, or a whole-eMMC dump) for --image")
    r.add_argument("--install-boot-loader", action="store_true",
                   help="allow installing Kiln's own boot loader on a disk "
                   "that doesn't hold Kiln's SPL")
    r.add_argument("--unsupported-board", action="store_true",
                   help="with --install-boot-loader: a board whose stock SPL "
                   "isn't on the allowlist")
    r.add_argument("--yes", action="store_true")
    r.add_argument("--dry-run", action="store_true",
                   help="say which pieces differ; write nothing")
    a = p.parse_args(argv)
    if a.cmd == "restore" and a.stock_mib and not a.image:
        p.error("--stock-mib goes with --image")
    if a.cmd == "restore" and a.unsupported_board and \
            not a.install_boot_loader:
        p.error("--unsupported-board goes with --install-boot-loader")
    try:
        return {"find": cmd_find, "check": cmd_check, "backup": cmd_backup,
                "restore": cmd_restore}[a.cmd](a)
    except (RepairError, img.ImageError, OSError) as e:
        print("ad5x_emmc_repair: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
