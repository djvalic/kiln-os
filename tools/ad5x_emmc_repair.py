#!/usr/bin/env python3
"""Check, back up and repair an AD5X's eMMC from a Linux PC.

The printer shows its eMMC to the PC as a USB disk: the boot ROM's USB mode,
then Kiln's U-Boot with "ad5x_usbboot.py run-uboot" (docs/emmc-repair.md).

    ad5x_emmc_repair.py find
    ad5x_emmc_repair.py check   [--disk DEV] [--image DIR] [--deep]
    ad5x_emmc_repair.py backup  [--disk DEV] [--userdata] DEST
    ad5x_emmc_repair.py restore [--disk DEV] (--image DIR | --backup DIR)
                                [--keep-data] [--parts NAME,...]
                                [--usershare] [--dry-run] [--yes]

find     the printer's eMMC among this PC's disks: a USB disk from Kiln's
         U-Boot (USB ID 1d6b:0104, maker "Kiln OS"). The other commands
         take that one when --disk is left out; --disk names a device
         (it must be the same kind of disk) or an image file (tests).
check    reads only: the first MiB (boot ROM parameters, SPL, U-Boot), both
         GPTs and stock's layout, both kernels (uImage CRCs), both root
         filesystems (SquashFS; with --image compared with the release's
         bytes), the boot flag, usershare (p6: ext4, /MAC) and userdata
         (p7: ext4 that fits its partition). Says what restore would do.
backup   the first MiB and p1-p6 (--userdata: p7 too) into
         DEST/ad5x-backup-<date>-<n>/, the recovery OS's ad5x-backup
         format (NAME.img, SHA256SUMS, MANIFEST.txt), each file read back.
restore  writes what is given, each piece read back:
         --image DIR   ad5x_emmc_image.py's files: the first MiB, p1-p5 and
                       a new, empty /data (p7), grown to the end of the
                       eMMC; --keep-data leaves p7 as it is. Either way
                       userdata gets the rest of the eMMC in the new GPT
         --backup DIR  an ad5x-backup: boot, kernel, rootfs, kernel2,
                       rootfs2, ota; userdata when it has one
         --usershare   also usershare, from the backup or the image
                       (ad5x_emmc_image.py --usershare/--mac): refused when
                       the eMMC's own usershare is usable and its /MAC
                       differs
         --parts       only these (first-mib,p1,...,p7 or backup names)
         Partitions first, the first MiB last, then the backup GPT from
         the primary. Pieces that already hold the same bytes are left
         alone. Asks before writing unless --yes; --dry-run says which
         pieces differ and writes nothing.

Usershare (p6) holds this printer's factory data (MAC address, serial
number, calibration): no release has it, so it is never written except from
this printer's own backup.
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
KILN_UMS = ("1d6b", "0104", "Kiln OS")
BLKFLSBUF, BLKRRPART = 0x1261, 0x125f  # _IO(0x12, 97), _IO(0x12, 95)
if os.uname().machine.startswith("mips"):  # _IO's direction bits differ
    BLKFLSBUF, BLKRRPART = 0x20001261, 0x2000125f
EXT4_MAGIC = 0xEF53
# image file names -> (restore name, eMMC byte offset)
IMAGE_FILES = {"00-first-mib.bin": ("first-mib", 0)}
for _n, _name, _start, _cnt in PARTS:
    IMAGE_FILES["p%d" % _n] = ("p%d" % _n, _start * SECTOR)
# ad5x-backup names (the GPT's) -> restore name
BACKUP_NAMES = {"boot": "first-mib"}
BACKUP_NAMES.update({name: "p%d" % n for n, name, _, _ in PARTS})


class RepairError(Exception):
    pass


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


# ---- the disk ----

def usb_identity(dev):
    """(idVendor, idProduct, manufacturer) of the USB device behind a
    block device, or None."""
    name = os.path.basename(os.path.realpath(dev))
    p = os.path.realpath("/sys/block/%s/device" % name)
    while p not in ("/", "/sys"):
        if os.path.exists(os.path.join(p, "idVendor")):
            def rd(f):
                try:
                    with open(os.path.join(p, f)) as fh:
                        return fh.read().strip()
                except OSError:
                    return ""
            return rd("idVendor"), rd("idProduct"), rd("manufacturer")
        p = os.path.dirname(p)
    return None


def kiln_disks():
    return sorted("/dev/" + os.path.basename(b) for b in glob.glob("/sys/block/sd*")
                  if usb_identity("/dev/" + os.path.basename(b)) == KILN_UMS)


class Disk:
    def __init__(self, path, write=False):
        self.path = path
        st = os.stat(path)
        self.block = stat.S_ISBLK(st.st_mode)
        if not self.block and not stat.S_ISREG(st.st_mode):
            raise RepairError("%s is neither a disk nor an image file" % path)
        # a loop device (tests) is a file; any other disk must be the
        # printer's, from Kiln's U-Boot
        loop = os.path.basename(os.path.realpath(path)).startswith("loop")
        if self.block and not loop and usb_identity(path) != KILN_UMS:
            raise RepairError("%s isn't an AD5X eMMC shown by Kiln's U-Boot "
                              "(USB %s): refused" % (path, usb_identity(path)))
        self.fd = os.open(path, os.O_RDWR if write else os.O_RDONLY)
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


def open_disk(arg, write=False):
    if arg:
        return Disk(arg, write)
    found = kiln_disks()
    if not found:
        raise RepairError("no AD5X eMMC on this PC: start the printer over USB "
                          "(docs/emmc-repair.md), or name it with --disk")
    if len(found) > 1:
        raise RepairError("more than one AD5X eMMC (%s): choose with --disk" %
                          ", ".join(found))
    return Disk(found[0], write)


# ---- what is on it ----

def crc32(b):
    return binascii.crc32(b) & 0xffffffff


def parse_gpt(disk, lba):
    """The GPT header at @lba and its entries: dict, or a string saying
    what is wrong."""
    if lba <= 0 or lba >= disk.sectors:
        return "LBA %d is outside the disk" % lba
    h = disk.read(lba * SECTOR, SECTOR)
    (sig, _, hsz, hcrc, _, cur, alt, first, last, _, elba, n, esz,
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
    return dict(raw=h[:hsz], alt=alt, first=first, last=last, elba=elba,
                n=n, esz=esz, ents=ents, parts=parts)


def layout_problems(g):
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
    if USERDATA in g["parts"] and g["parts"][USERDATA][2] > g["last"]:
        out.append("p7 runs past the last usable sector")
    return out


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


def mac_or_none(text):
    return text if text and re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}",
                                         text) else None


def usershare_mac(disk, g):
    node = disk.partition_node(USERSHARE)
    if node:
        return mac_or_none(debugfs_cat(node, "/MAC"))
    if disk.block:
        return None
    ext = part_extent(g, USERSHARE)	# an image file: through a copy
    with tempfile.NamedTemporaryFile() as t:
        t.write(disk.read(*ext))
        t.flush()
        return mac_or_none(debugfs_cat(t.name, "/MAC"))


def e2fsck(node, deep):
    if not node or not shutil.which("e2fsck"):
        return None
    r = subprocess.run(["e2fsck", "-n"] + (["-f"] if deep else []) + [node],
                       capture_output=True, text=True)
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    return r.returncode, lines[-1:]


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
    return b"".join(open(p, "rb").read() for p in pieces_of(path))


# ---- commands ----

def cmd_find(a):
    found = kiln_disks()
    if not found:
        print("no AD5X eMMC on this PC (USB 1d6b:0104 from Kiln OS); "
              "start the printer over USB: docs/emmc-repair.md")
        return 1
    for d in found:
        n = os.path.basename(d)
        size = int(open("/sys/block/%s/size" % n).read()) * SECTOR
        print("%s  %.1f GiB  AD5X eMMC over USB (Kiln's U-Boot)" %
              (d, size / 2**30))
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
                   "of %d): userdata could be larger" % (g["alt"],
                                                         disk.sectors))

    # first MiB
    mib = disk.read(0, FIRST_MIB)
    r.line(mib[0:4] == spl.PARAMS_ID, "boot ROM params",
           "INGE at 0" if mib[0:4] == spl.PARAMS_ID else
           "no INGE at 0: the boot ROM won't start from the eMMC")
    magic, count, _ = spl.decode(mib[spl.SPL_EMMC_OFF:], 0)
    region = mib[spl.SPL_EMMC_OFF:spl.SPL_AREA_END]
    kind = ("Kiln's" if b"U-Boot SPL 2026" in region else
            "stock" if b"U-Boot SPL 2013" in region else "unknown")
    ok = magic == spl.SPL_MAGIC and 0 < count <= spl.MAX_BLOCKS
    r.line(ok, "SPL", "%s, %d blocks" % (kind, count) if ok else
           "no SPL header at 0x4400: the boot ROM falls to USB mode")
    ub = mib[spl.UBOOT_EMMC_OFF:]
    if struct.unpack(">I", ub[:4])[0] == img.UIMAGE_MAGIC:
        info = uimage_info(ub)
        r.line(not info.startswith("BAD"), "U-Boot", info)
    else:
        r.line(None, "U-Boot", "no uImage at 0xA400 (stock's, or none: "
               "Kiln's SPL then starts the slot's kernel itself)")
    if "first-mib" in rel:
        want = file_bytes(rel["first-mib"][1])
        same = want[spl.SPL_EMMC_OFF:] == mib[spl.SPL_EMMC_OFF:len(want)]
        r.line(same, "boot loader", "the release's" if same else
               "differs from the release's SPL/U-Boot")

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
          "rewrites the rest; --keep-data keeps /data")
    return 2


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
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    i = 1
    while os.path.exists(os.path.join(a.dest, "ad5x-backup-%s-%d" % (stamp, i))):
        i += 1
    out = os.path.join(a.dest, "ad5x-backup-%s-%d" % (stamp, i))
    os.makedirs(out)
    sums = []
    for name, off, size in items:
        h = hashlib.sha256()
        path = os.path.join(out, name + ".img")
        with open(path, "wb") as f:
            for b in disk.chunks(off, size):
                h.update(b)
                f.write(b)
            f.flush()
            os.fsync(f.fileno())
        sha = h.hexdigest()
        if file_sha(path) != sha:
            raise RepairError("%s: the file doesn't read back as read" % path)
        sums.append("%s  %s.img" % (sha, name))
        print("backup: %-9s %12d bytes  %s" % (name, size, sha[:16]))
    with open(os.path.join(out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    mac = usershare_mac(disk, g)
    with open(os.path.join(out, "MANIFEST.txt"), "w") as f:
        f.write("AD5X eMMC backup (ad5x_emmc_repair.py, over USB), %s\n" %
                datetime.datetime.now().isoformat(timespec="seconds"))
        f.write("disk: %s, %d bytes\n" % (disk.path, disk.size))
        f.write("usershare /MAC: %s\n" % (mac or "not read"))
        for name, off, size in items:
            f.write("%s: start sector %d, %d bytes\n" % (name, off // SECTOR,
                                                         size))
    print("backup: OK %s" % out)
    return 0


def new_gpt_for(first, disk_sectors):
    """@first (a release's first MiB) with its GPT stretched to this disk:
    userdata to the end, the backup GPT in the last sectors, as
    ad5x-grow-data leaves it. Returns (first MiB, backup entries + header,
    backup entries LBA, p7's sectors)."""
    first = bytearray(first)
    h = bytearray(first[SECTOR:2 * SECTOR])
    hsz = struct.unpack_from("<I", h, 12)[0]
    n, esz = struct.unpack_from("<II", h, 80)
    es = (n * esz + SECTOR - 1) // SECTOR
    ents = bytearray(first[2 * SECTOR:2 * SECTOR + n * esz])
    alt = disk_sectors - 1
    last = alt - es - 1
    o = (USERDATA - 1) * esz
    dstart = struct.unpack_from("<Q", ents, o + 32)[0]
    dend = dstart + (last - dstart + 1) // 8 * 8 - 1
    struct.pack_into("<Q", ents, o + 40, dend)
    ecrc = crc32(bytes(ents))

    def header(cur, other, elba):
        b = bytearray(h[:hsz])
        struct.pack_into("<QQ", b, 24, cur, other)
        struct.pack_into("<Q", b, 48, last)
        struct.pack_into("<Q", b, 72, elba)
        struct.pack_into("<I", b, 88, ecrc)
        struct.pack_into("<I", b, 16, 0)
        struct.pack_into("<I", b, 16, crc32(bytes(b)))
        return bytes(b).ljust(SECTOR, b"\0")

    first[SECTOR:2 * SECTOR] = header(1, alt, 2)
    first[2 * SECTOR:2 * SECTOR + len(ents)] = ents
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


def plan_restore(a, disk):
    """[(name, offset, bytes-or-path, sha256)] in writing order."""
    want = set(a.parts.split(",")) if a.parts else None
    plan = []
    if a.image:
        for name, off, path, sha in image_pieces(a.image):
            if name == "p%d" % USERDATA and a.keep_data:
                continue
            if name == "p%d" % USERSHARE and not a.usershare:
                continue
            plan.append([name, off, path, sha])
    else:
        sums = read_sums(a.backup)
        has = {f[:-4]: sha for f, sha in sums.items() if f.endswith(".img")}
        g = parse_gpt(disk, 1)
        g = None if isinstance(g, str) else g
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
            plan.append([rname, off, path, has[bname]])
    us = [p for p in plan if p[0] == "p%d" % USERSHARE]
    if us:
        g = parse_gpt(disk, 1)
        mine = usershare_mac(disk, None if isinstance(g, str) else g)
        with tempfile.TemporaryDirectory() as td:
            t = os.path.join(td, "u.img")
            with open(t, "wb") as f:
                f.write(file_bytes(us[0][2]))
            theirs = mac_or_none(debugfs_cat(t, "/MAC"))
        if mine and theirs and mine.lower() != theirs.lower():
            raise RepairError("the eMMC has a usable usershare with /MAC %s; "
                              "the one to write has %s: refused (it would "
                              "replace this printer's factory data)" %
                              (mine, theirs))
        print("restore: usershare from %s (/MAC %s)" %
              (a.image or a.backup, theirs or "not read"))
    if want is not None:
        unknown = want - {p[0] for p in plan}
        if unknown:
            raise RepairError("--parts: nothing to write for %s" %
                              ", ".join(sorted(unknown)))
        plan = [p for p in plan if p[0] in want]
    # partitions first, the first MiB last (a write cut short leaves the
    # old boot loader and GPT)
    plan.sort(key=lambda p: (p[0] == "first-mib", p[1]))
    return plan


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
    subprocess.run(["e2fsck", "-fy", node], capture_output=True)
    r = subprocess.run(["resize2fs", node], capture_output=True, text=True)
    print("restore: /data grown to the end of the eMMC" if r.returncode == 0
          else "restore: resize2fs %s failed: %s" % (node, r.stderr.strip()))


def cmd_restore(a):
    disk = open_disk(a.disk, write=not a.dry_run)
    plan = plan_restore(a, disk)
    tail = None
    for p in plan:
        data = file_bytes(p[2])
        if sha256_bytes(data) != p[3]:
            raise RepairError("%s: not the bytes SHA256SUMS lists" % p[2])
        stretch = bool(a.image)
        if p[0] == "first-mib" and a.backup and \
                not any(q[0] == "p%d" % USERDATA for q in plan):
            # the backup's GPT may predate ad5x-grow-data: userdata's
            # ext4 on the eMMC then doesn't fit the backup's p7
            n7 = p7_sectors_in(data)
            fits = n7 and ext4_info(disk, PARTS[USERDATA - 1][2] * SECTOR,
                                    n7 * SECTOR)[0]
            if not fits:
                print("restore: /data on the eMMC is larger than userdata in"
                      " the backup's GPT: userdata to the end of the eMMC")
                stretch = True
        if p[0] == "first-mib" and stretch:
            data, gtail, tail_lba, p7_sectors = new_gpt_for(data,
                                                            disk.sectors)
            ok, text = ext4_info(disk, PARTS[USERDATA - 1][2] * SECTOR,
                                 p7_sectors * SECTOR)
            if a.keep_data and not ok:
                raise RepairError("--keep-data: userdata: %s" % text)
            p[3] = sha256_bytes(data)
            tail = (tail_lba * SECTOR, gtail)
        p[2] = data
    if tail is None and any(p[0] == "first-mib" for p in plan):
        first = next(p[2] for p in plan if p[0] == "first-mib")
        tail = backup_gpt_from_primary(first, disk.sectors)
    print("restore: %s, %.1f GiB" % (disk.path, disk.size / 2**30))
    for name, off, data, _ in plan:
        print("  %-9s %12d bytes at 0x%09x" % (name, len(data), off))
    if tail:
        print("  %-9s %12d bytes at 0x%09x" % ("GPT copy", len(tail[1]),
                                             tail[0]))
    if not any(p[0] == "p%d" % USERSHARE for p in plan):
        print("  usershare (p6) is not written")
    if a.dry_run:
        pieces = plan + ([["GPT copy", tail[0], tail[1],
                           sha256_bytes(tail[1])]] if tail else [])
        for name, off, data, sha in pieces:
            same = disk.sha256(off, len(data)) == sha
            print("restore: %-9s %s" % (name, "the same already" if same
                                        else "would be written"))
        print("restore: dry run, nothing written")
        return 0
    if not a.yes:
        if input("write these? type yes: ").strip() != "yes":
            print("restore: nothing written")
            return 1
    for name, off, data, sha in plan:
        write_checked(disk, name, off, data, sha)
    if tail:
        write_checked(disk, "GPT copy", tail[0], tail[1],
                      sha256_bytes(tail[1]))
    if a.image and any(p[0] == "p%d" % USERDATA for p in plan):
        grow_userdata(disk)
    print("restore: OK; run check, then start the printer (power cycle)")
    return 0


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
    r.add_argument("--keep-data", action="store_true")
    r.add_argument("--parts")
    r.add_argument("--usershare", action="store_true")
    r.add_argument("--yes", action="store_true")
    r.add_argument("--dry-run", action="store_true",
                   help="say which pieces differ; write nothing")
    a = p.parse_args(argv)
    if a.cmd == "restore" and a.keep_data and not a.image:
        p.error("--keep-data goes with --image")
    try:
        return {"find": cmd_find, "check": cmd_check, "backup": cmd_backup,
                "restore": cmd_restore}[a.cmd](a)
    except (RepairError, img.ImageError, OSError) as e:
        print("ad5x_emmc_repair: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
