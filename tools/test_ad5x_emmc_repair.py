#!/usr/bin/env python3
"""ad5x_emmc_repair.py on an eMMC image file (no printer): a fake release
made with ad5x_emmc_image.py, a "disk" larger than the release's image with
a usershare of its own, then check, damage, check, restore, check.

    python3 tools/test_ad5x_emmc_repair.py

Needs mksquashfs, mke2fs, debugfs and e2fsck (e2fsprogs, squashfs-tools).
"""
import binascii
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ad5x_emmc_image as img  # noqa: E402
import ad5x_emmc_repair as rep  # noqa: E402

SECTOR = 512
MIB = 1 << 20
MAC = "24:A1:0D:00:11:22"
fails = 0


def check(name, cond):
    global fails
    print("%s  %s" % ("ok  " if cond else "FAIL", name))
    if not cond:
        fails += 1


def uimage(name, data):
    h = bytearray(struct.pack(">IIIIIIIBBBB32s", img.UIMAGE_MAGIC, 0, 0,
                              len(data), 0x80010000, 0x80010000,
                              binascii.crc32(data) & 0xffffffff, 5, 5, 2, 0,
                              name))
    struct.pack_into(">I", h, 4, binascii.crc32(bytes(h)) & 0xffffffff)
    return bytes(h) + data


def run(*args):
    return rep.main([a for a in args])


def release(td):
    src = os.path.join(td, "src")
    os.makedirs(os.path.join(src, "root", "etc"))
    with open(os.path.join(src, "root", "etc", "os-release"), "w") as f:
        f.write("NAME=test\n")
    files = {
        "spl": img.spl.spl_image(b"U-Boot SPL 2026.10 test" + bytes(3000)),
        "uboot": uimage(b"Kiln U-Boot test",
                        b"KILN-RESCUE 1\n" + os.urandom(200000)),
        "kernel": uimage(b"Linux-6.6-ad5x", os.urandom(300000)),
    }
    for k, b in files.items():
        with open(os.path.join(src, k), "wb") as f:
            f.write(b)
    subprocess.run(["mksquashfs", os.path.join(src, "root"),
                    os.path.join(src, "rootfs.squashfs"), "-quiet",
                    "-noappend"], check=True, stdout=subprocess.DEVNULL)
    out = os.path.join(td, "image")
    img.main(["--spl", os.path.join(src, "spl"), "--uboot",
              os.path.join(src, "uboot"), "--kernel",
              os.path.join(src, "kernel"), "--main",
              os.path.join(src, "rootfs.squashfs"), "--recovery",
              os.path.join(src, "rootfs.squashfs"), "--data-mib", "32",
              "--test-image", out])
    return out


def usershare(td):
    """An ext4 for p6 with a /MAC, as the factory leaves it."""
    seed = os.path.join(td, "us")
    os.makedirs(seed)
    with open(os.path.join(seed, "MAC"), "w") as f:
        f.write(MAC + "\n")
    p = os.path.join(td, "usershare.img")
    with open(p, "wb") as f:
        f.truncate(img.PARTS[5][3] * SECTOR)
    subprocess.run(["mke2fs", "-q", "-F", "-t", "ext4", "-d", seed, p],
                   check=True)
    return p


def zero(disk, off, n):
    with open(disk, "r+b") as f:
        f.seek(off)
        f.write(bytes(n))


def read(disk, off, n):
    with open(disk, "rb") as f:
        f.seek(off)
        return f.read(n)


def main():
    with tempfile.TemporaryDirectory() as td:
        image = release(td)
        # the "eMMC": the release's whole image, its own usershare, 96 MiB
        # more at the end than the release's userdata
        disk = os.path.join(td, "emmc.img")
        whole = os.path.join(image, "TEST-ONLY-whole-emmc-do-not-flash.img")
        size = os.path.getsize(whole) + 96 * MIB
        with open(whole, "rb") as s, open(disk, "wb") as d:
            d.truncate(size)
            while True:
                b = s.read(MIB)
                if not b:
                    break
                d.write(b)
        us = open(usershare(td), "rb").read()
        p6 = img.PARTS[5][2] * SECTOR
        with open(disk, "r+b") as f:
            f.seek(p6)
            f.write(us)

        check("check: a fresh image is good",
              run("check", "--disk", disk, "--image", image) == 0)
        g = rep.parse_gpt(rep.Disk(disk), 1)
        check("usershare /MAC read", rep.usershare_mac(rep.Disk(disk), g) == MAC)

        bdir = os.path.join(td, "backups")
        os.makedirs(bdir)
        check("backup", run("backup", "--disk", disk, bdir) == 0)
        b = os.path.join(bdir, os.listdir(bdir)[0])
        check("backup has boot..usershare", sorted(os.listdir(b)) == sorted(
            ["SHA256SUMS", "MANIFEST.txt", "boot.img", "kernel.img",
             "rootfs.img", "kernel2.img", "rootfs2.img", "ota.img",
             "usershare.img"]))

        # damage: the SPL header, the primary GPT, slot B's kernel header and
        # root superblock
        zero(disk, 0x4400, 512)
        zero(disk, 512, 512)
        zero(disk, img.PARTS[2][2] * SECTOR, 64)
        zero(disk, img.PARTS[3][2] * SECTOR, 4096)
        check("check: damage found", run("check", "--disk", disk) == 2)

        before = read(disk, 0, 2 * MIB)
        check("restore --dry-run", run("restore", "--disk", disk, "--image",
                                       image, "--dry-run") == 0)
        check("dry run wrote nothing", read(disk, 0, 2 * MIB) == before)
        check("restore --image", run("restore", "--disk", disk, "--image",
                                     image, "--yes") == 0)
        check("check: good after restore",
              run("check", "--disk", disk, "--image", image) == 0)
        check("usershare untouched", read(disk, p6, len(us)) == us)

        # keep /data: a file in userdata, then restore with --keep-data on
        # a GPT damaged again; userdata gets the rest of the disk
        zero(disk, 512, 512)
        check("restore --image --keep-data", run(
            "restore", "--disk", disk, "--image", image, "--keep-data",
            "--yes") == 0)
        d = rep.Disk(disk)
        g = rep.parse_gpt(d, 1)
        check("GPT: backup at the last sector", g["alt"] == d.sectors - 1)
        check("GPT: backup good", not isinstance(rep.parse_gpt(d, g["alt"]),
                                                 str))
        p7 = g["parts"][7]
        check("GPT: userdata to the end", p7[2] >= g["last"] - 7)
        check("check: good with --keep-data", run("check", "--disk", disk) == 0)

        # a backup's first MiB from before /data grew: userdata keeps the
        # whole disk when the ext4 on it is larger than the backup's p7
        d = rep.Disk(disk)
        n7 = rep.p7_sectors_in(read(os.path.join(b, "boot.img"), 0, MIB))
        bigger = (d.sectors - img.PARTS[6][2] - 40) // 8 * 8
        subprocess.run(["e2fsck", "-fy", "-E", "offset=%d" % (img.PARTS[6][2] *
                        SECTOR), disk], capture_output=True)
        p7img = os.path.join(td, "p7.img")
        subprocess.run(["dd", "if=" + disk, "of=" + p7img, "bs=512",
                        "skip=%d" % img.PARTS[6][2], "count=%d" % bigger,
                        "status=none"], check=True)
        subprocess.run(["resize2fs", "-f", p7img], capture_output=True,
                       check=True)
        with open(p7img, "rb") as s_, open(disk, "r+b") as d_:
            d_.seek(img.PARTS[6][2] * SECTOR)
            d_.write(s_.read())
        check("test setup: /data larger than the backup's p7",
              not rep.ext4_info(d, img.PARTS[6][2] * SECTOR,
                                n7 * SECTOR)[0])
        check("restore --backup over a grown /data", run(
            "restore", "--disk", disk, "--backup", b, "--parts", "first-mib",
            "--yes") == 0)
        check("check: /data mountable after it",
              run("check", "--disk", disk) == 0)

        # usershare from the backup: only with --usershare
        zero(disk, p6 + 1024, 1024)
        check("check: usershare damage found", run("check", "--disk", disk) == 2)
        run("restore", "--disk", disk, "--backup", b, "--yes")
        check("restore --backup alone leaves usershare",
              read(disk, p6 + 1024, 1024) == bytes(1024))
        check("restore --backup --usershare", run(
            "restore", "--disk", disk, "--backup", b, "--usershare",
            "--yes") == 0)
        check("usershare back", read(disk, p6, len(us)) == us)
        check("check: good at the end", run("check", "--disk", disk) == 0)

        check("a device that isn't a disk is refused",
              run("check", "--disk", "/dev/null") == 1)
    print("failures: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
