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
    p6      usershare  NEVER WRITTEN: the printer's factory data (MAC address,
                       serial number, calibration)
    p7      userdata   a small empty ext4 (/data); the GPT's last partition
                       ends with the image, on any eMMC size

Every file is written at its own offset; p6 has no file, so flashing all of
them leaves the factory partition as it was. --test-image also writes the
whole image as one file for loop-device and emulator tests: never flash that
one whole (it would zero p6).

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


def gpt(total_sectors):
    """Primary (LBA 1, entries at LBA 2) and backup GPT (entries before the
    last sector), as stock: 8 entries, basic data type, no attributes."""
    last = total_sectors - 1
    n_ent_sectors = GPT_ENTRIES * GPT_ENTRY_SIZE // SECTOR
    first_usable = 34                       # as stock: SPL at LBA 34
    last_usable = last - n_ent_sectors - 1
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

    # p7: an empty ext4 of --data-mib
    with tempfile.TemporaryDirectory() as td:
        dimg = os.path.join(td, "userdata.img")
        with open(dimg, "wb") as f:
            f.truncate(a.data_mib * MIB)
        subprocess.run(["mke2fs", "-q", "-F", "-t", "ext4", "-O",
                        MKE2FS_FEATURES, "-L", "userdata", "-E",
                        "root_owner=0:0", dimg], check=True)
        data = read(dimg)
    # the backup GPT sits in the last sectors of userdata's range
    tail = ents + backup
    data = data[:len(data) - len(tail)] + tail if a.data_mib else data

    ota = bytearray(PARTS[4][3] * SECTOR)
    ota[0:len(FLAG)] = FLAG

    files = [  # name, eMMC byte offset, bytes
        ("00-first-mib.bin", 0, bytes(first)),
        ("p1-kernel.img", PARTS[0][2] * SECTOR, kernel),
        ("p2-rootfs-recovery.img", PARTS[1][2] * SECTOR, rec),
        ("p3-kernel2.img", PARTS[2][2] * SECTOR, kernel),
        ("p4-rootfs2-main.img", PARTS[3][2] * SECTOR, main),
        ("p5-ota.img", PARTS[4][2] * SECTOR, bytes(ota)),
        ("p7-userdata.img", data_start * SECTOR, data),
    ]
    os.makedirs(a.out, exist_ok=True)
    sums, policy = [], []
    for i, (name, off, b) in enumerate(files):
        with open(os.path.join(a.out, name), "wb") as f:
            f.write(b)
        sums.append("%s  %s" % (sha256(b), name))
        policy.append("[policy%d]\nenabled=1\nattribute=%s\nlabel=*\n"
                      "offset=0x%x\nops=\"6,2,0\"\ntype=0\n" % (i, name, off))
    with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    with open(os.path.join(a.out, "usbcloner-policies.txt"), "w") as f:
        f.write("# USBCloner policies: one file per range, each at its eMMC "
                "offset (type 0 = file,\n# ops \"6,2,0\" = MMC0). No entry "
                "for p6 (usershare, 0x%x-0x%x): the\n# printer's factory "
                "data must stay. Keep force_erase=0.\n\n" %
                (PARTS[5][2] * SECTOR,
                 (PARTS[5][2] + PARTS[5][3]) * SECTOR - 1) +
                "\n".join(policy))
    if a.test_image:
        t = os.path.join(a.out, "TEST-ONLY-whole-emmc-do-not-flash.img")
        with open(t, "wb") as f:
            f.truncate(total * SECTOR)
            for _, off, b in files:
                f.seek(off)
                f.write(b)
    print("eMMC image files in %s: %d sectors (%.1f MiB) up to the end of "
          "userdata (%d MiB); p6 never written" %
          (a.out, total, total * SECTOR / MIB, a.data_mib))
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
    p.add_argument("--test-image", action="store_true",
                   help="also the whole image as one file (tests only)")
    p.add_argument("out")
    a = p.parse_args(argv)
    try:
        build(a)
    except (ImageError, OSError, subprocess.CalledProcessError) as e:
        print("ad5x_emmc_image: ERROR: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
