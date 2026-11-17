#!/usr/bin/env python3
"""The AD5X's usershare partition (p6): find a usable copy, or make one.

    ad5x_usershare.py check SOURCE...
    ad5x_usershare.py make --mac XX:XX:XX:XX:XX:XX|random OUT

Usershare is the factory's ext4 (1 GiB): this printer's Ethernet address
(/MAC), stock's printer settings (/config), Wi-Fi networks stock saved
(/wifi) and Flashforge's programs. Kiln OS reads only /MAC and
/wifi/wpa_supplicant.conf from it.

check   each SOURCE, which may be:
        - a usershare image (usershare.img from ad5x-backup or
          ad5x_emmc_repair.py backup, or a dd of p6)
        - an ad5x-backup directory (its usershare.img, checked against
          SHA256SUMS)
        - a whole-eMMC dump (a dd of /dev/mmcblk0, a USBCloner read from 0):
          p6 is cut out of it
        Good when the ext4 checks clean (e2fsck -n) and /MAC is a usable
        address. Prints the MAC; exit 0 when one of them is good.
make    a new usershare for Kiln OS: an empty ext4 as the factory makes it,
        with /MAC (the address given: the printer's own if you know it,
        from its label, router or an old log; "random" picks a locally
        administered one) and empty /config and /wifi. Flashforge's
        firmware doesn't run from it (its programs aren't there): return
        to stock then needs Flashforge's full firmware package.
"""
import argparse
import hashlib
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

SECTOR = 512
USERSHARE_LBA = 0x6d000
USERSHARE_SECTORS = 0x200000
USERSHARE_BYTES = USERSHARE_SECTORS * SECTOR          # 1 GiB
EXT4_MAGIC = b"\x53\xef"
# the factory's ext4 (dumpe2fs of a stock usershare): 4 KiB blocks, 256-byte
# inodes, 65536 inodes, no label, these features
FEATURES = ("none,has_journal,ext_attr,resize_inode,dir_index,filetype,"
            "extent,64bit,flex_bg,sparse_super,large_file,huge_file,"
            "dir_nlink,extra_isize,metadata_csum")
NOTE = """This usershare (p6) was made by Kiln OS's ad5x_usershare.py, not at
the factory: the printer's own was lost. It has the Ethernet address
chosen when it was made (/MAC) and nothing of Flashforge's. Flashforge's
firmware doesn't run from it.
"""


class UsershareError(Exception):
    pass


def parse_mac(text):
    """'24:a1:0d:b8:5a:58' (or with - or no separators) -> '24:A1:0D:B8:5A:58',
    or UsershareError for anything that can't be a printer's address."""
    t = text.strip()
    if t.lower() == "random":
        b = [random.SystemRandom().randrange(256) for _ in range(6)]
        b[0] = (b[0] & 0xfc) | 0x02      # unicast, locally administered
        return ":".join("%02X" % x for x in b)
    h = re.sub(r"[:\-.]", "", t)
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", h):
        raise UsershareError("%r isn't a MAC address (6 bytes in hex)" % text)
    b = bytes.fromhex(h)
    if b[0] & 1:
        raise UsershareError("%s is a multicast address (lowest bit of the "
                             "first byte set): not usable for one printer" %
                             text)
    if b == bytes(6):
        raise UsershareError("00:00:00:00:00:00 isn't usable")
    return ":".join("%02X" % x for x in b)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def need(tool):
    if not shutil.which(tool):
        raise UsershareError("%s not found (e2fsprogs)" % tool)


def check_image(path):
    """(MAC, None) for a good usershare image file, or (None, why)."""
    need("e2fsck")
    need("debugfs")
    with open(path, "rb") as f:
        f.seek(1024 + 56)
        if f.read(2) != EXT4_MAGIC:
            return None, "no ext4"
    if os.path.getsize(path) > USERSHARE_BYTES:
        return None, "larger than usershare (%d bytes)" % os.path.getsize(path)
    r = run(["e2fsck", "-n", "-f", path])
    if r.returncode not in (0,):
        last = [l for l in r.stdout.splitlines() if l.strip()][-1:]
        return None, "e2fsck -n: %s (exit %d)" % (" ".join(last),
                                                  r.returncode)
    r = run(["debugfs", "-c", "-R", "cat /MAC", path])
    line = r.stdout.splitlines()[0].strip() if r.stdout else ""
    try:
        return parse_mac(line), None
    except UsershareError:
        return None, "no usable /MAC (%r)" % line[:40]


def extract(source, td):
    """A usershare image file from @source (see check); its path."""
    if os.path.isdir(source):
        img = os.path.join(source, "usershare.img")
        if not os.path.exists(img):
            raise UsershareError("%s: no usershare.img" % source)
        sums = os.path.join(source, "SHA256SUMS")
        if os.path.exists(sums):
            want = [l.split()[0] for l in open(sums)
                    if l.split()[-1:] == ["usershare.img"]]
            h = hashlib.sha256()
            with open(img, "rb") as f:
                for b in iter(lambda: f.read(1 << 22), b""):
                    h.update(b)
            if want and want[0] != h.hexdigest():
                raise UsershareError("%s: usershare.img doesn't match "
                                     "SHA256SUMS" % source)
        return img
    size = os.path.getsize(source)
    if size <= USERSHARE_BYTES:
        return source
    if size < (USERSHARE_LBA + USERSHARE_SECTORS) * SECTOR:
        raise UsershareError("%s: %d bytes: neither usershare nor a whole "
                             "eMMC" % (source, size))
    out = os.path.join(td, "usershare-from-dump.img")
    with open(source, "rb") as s, open(out, "wb") as d:
        s.seek(USERSHARE_LBA * SECTOR)
        left = USERSHARE_BYTES
        while left:
            b = s.read(min(1 << 22, left))
            if not b:
                break
            d.write(b)
            left -= len(b)
    return out


def find(sources):
    """The first good usershare among @sources: (bytes, MAC, source), or
    (None, None, None); prints what it found in each."""
    with tempfile.TemporaryDirectory() as td:
        for s in sources:
            try:
                img = extract(s, td)
                mac, why = check_image(img)
            except (UsershareError, OSError) as e:
                mac, why = None, str(e)
            if mac:
                print("usershare: %s: good, /MAC %s" % (s, mac))
                with open(img, "rb") as f:
                    data = f.read()
                return data.ljust(USERSHARE_BYTES, b"\0"), mac, s
            print("usershare: %s: not usable: %s" % (s, why))
    return None, None, None


def make(mac):
    """A new usershare (bytes, USERSHARE_BYTES) with /MAC = @mac."""
    need("mke2fs")
    need("debugfs")
    mac = parse_mac(mac)
    with tempfile.TemporaryDirectory() as td:
        seed = os.path.join(td, "seed")
        for d in ("config", "wifi"):
            os.makedirs(os.path.join(seed, d))
        with open(os.path.join(seed, "MAC"), "w") as f:
            f.write(mac + "\n")
        with open(os.path.join(seed, "KILN-GENERATED.txt"), "w") as f:
            f.write(NOTE)
        os.chmod(os.path.join(seed, "MAC"), 0o755)      # as the factory's
        img = os.path.join(td, "usershare.img")
        with open(img, "wb") as f:
            f.truncate(USERSHARE_BYTES)
        r = run(["mke2fs", "-q", "-F", "-t", "ext4", "-b", "4096", "-I", "256",
                 "-N", "65536", "-O", FEATURES, "-E", "root_owner=0:0",
                 "-d", seed, img])
        if r.returncode:
            raise UsershareError("mke2fs: %s" % r.stderr.strip())
        # mke2fs -d keeps this PC's owner: root's, as the factory's
        for p in ("/MAC", "/KILN-GENERATED.txt", "/config", "/wifi"):
            for field in ("uid", "gid"):
                run(["debugfs", "-w", "-R", "sif %s %s 0" % (p, field), img],
                    check=True)
        got, why = check_image(img)
        if got != mac:
            raise UsershareError("the new usershare doesn't check: %s" % why)
        with open(img, "rb") as f:
            return f.read(), mac


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("sources", nargs="+")
    m = sub.add_parser("make")
    m.add_argument("--mac", required=True)
    m.add_argument("out")
    a = p.parse_args(argv)
    try:
        if a.cmd == "check":
            return 0 if find(a.sources)[0] else 1
        data, mac = make(a.mac)
        with open(a.out, "wb") as f:
            f.write(data)
        print("usershare: %s made, /MAC %s" % (a.out, mac))
        return 0
    except (UsershareError, OSError, subprocess.CalledProcessError) as e:
        print("ad5x_usershare: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
