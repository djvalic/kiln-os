#!/usr/bin/env python3
"""Pack an A/B .swu for SWUpdate (lib/ab.sh) without an unpacked copy.

    ab-pack.py SOURCE OUT.swu MKDESC SCRIPT

SOURCE is an update .zip (rootfs.squashfs, SHA256SUMS, optional
version.txt) or a rootfs.squashfs. rootfs.squashfs is read twice, straight
from SOURCE: once for its size and sha256 (checked against SHA256SUMS in a
.zip), once into OUT.swu, a newc cpio with sw-description (from MKDESC,
mk-ab-sw-description.sh), SCRIPT (ad5x-ab.sh) and rootfs.squashfs, in that
order as SWUpdate wants. /data then needs room for SOURCE and OUT.swu only.
Prints the version; exits 1 with a message on any problem."""
import hashlib
import os
import subprocess
import sys
import zipfile

CHUNK = 1 << 20


def die(msg):
    sys.stderr.write("ab-pack: %s\n" % msg)
    sys.exit(1)


class Source:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            magic = f.read(4)
        self.zip = None
        self.version = ""
        if magic == b"hsqs":
            return
        if magic != b"PK\x03\x04":
            die("%s is neither a squashfs nor a .zip" % path)
        self.zip = zipfile.ZipFile(path)
        names = self.zip.namelist()
        if "rootfs.squashfs" not in names or "SHA256SUMS" not in names:
            die("the .zip lacks rootfs.squashfs or SHA256SUMS")
        self.want = None
        for line in self.zip.read("SHA256SUMS").decode().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == "rootfs.squashfs":
                self.want = parts[0].lower()
        if not self.want:
            die("SHA256SUMS doesn't list rootfs.squashfs")
        if "version.txt" in names:
            for line in self.zip.read("version.txt").decode().splitlines():
                if "version " in line:
                    self.version = line.split("version ", 1)[1].strip()
                    break

    def open(self):
        if self.zip:
            return self.zip.open("rootfs.squashfs")
        return open(self.path, "rb")


def measure(src):
    h, n, head = hashlib.sha256(), 0, b""
    with src.open() as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            if n == 0:
                head = b[:4]
            h.update(b)
            n += len(b)
    if head != b"hsqs":
        die("rootfs.squashfs is not a squashfs image")
    sha = h.hexdigest()
    if src.zip and sha != src.want:
        die("rootfs.squashfs doesn't match the package's SHA256SUMS")
    return n, sha


def cpio_header(name, size, ino):
    nb = name.encode() + b"\0"
    fields = [ino, 0o100644, 0, 0, 1, 0, size, 0, 0, 0, 0, len(nb), 0]
    h = b"070701" + b"".join(b"%08X" % v for v in fields) + nb
    return h + b"\0" * (-len(h) % 4)


def main():
    if len(sys.argv) != 5:
        die("usage: ab-pack.py SOURCE OUT.swu MKDESC SCRIPT")
    source, out, mkdesc, script = sys.argv[1:]
    src = Source(source)
    size, sha = measure(src)
    version = src.version or "sqfs-" + sha[:8]
    desc = subprocess.run(["sh", mkdesc, version, str(size), sha, script],
                          check=True, capture_output=True).stdout
    with open(script, "rb") as f:
        scr = f.read()
    tmp = out + ".part"
    with open(tmp, "wb") as o:
        for ino, (name, data) in enumerate((("sw-description", desc),
                                            ("ad5x-ab.sh", scr)), 1):
            o.write(cpio_header(name, len(data), ino))
            o.write(data + b"\0" * (-len(data) % 4))
        o.write(cpio_header("rootfs.squashfs", size, 3))
        h, n = hashlib.sha256(), 0
        with src.open() as f:
            while True:
                b = f.read(CHUNK)
                if not b:
                    break
                h.update(b)
                n += len(b)
                o.write(b)
        if n != size or h.hexdigest() != sha:
            die("rootfs.squashfs changed while it was packed")
        o.write(b"\0" * (-size % 4))
        o.write(cpio_header("TRAILER!!!", 0, 0))
        o.flush()
        os.fsync(o.fileno())
    os.rename(tmp, out)
    print(version)


if __name__ == "__main__":
    main()
