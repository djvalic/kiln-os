#!/usr/bin/env python3
"""Wrap a kernel in a legacy U-Boot image header, as the AD5X SPL expects.

The SPL (docs/boot-slots.md) checks only the magic 0x27051956, reads
ih_size + 64 bytes to ih_load - 64 and jumps to ih_ep when ih_os is Linux.
It does NOT decompress, so the payload must be a self-extracting vmlinuz
(or a raw vmlinux.bin). Header and data CRCs are filled in anyway.

  mkuimage.py [--load ADDR] [--entry ADDR] [--name NAME] IN OUT
  mkuimage.py --show FILE
"""
import argparse
import struct
import sys
import time
import zlib

MAGIC = 0x27051956
IH_OS_LINUX, IH_ARCH_MIPS, IH_TYPE_KERNEL, IH_COMP_NONE = 5, 5, 2, 0
HDR = struct.Struct(">7I4B32s")  # 64 bytes


def build(data, load, entry, name):
    fields = [MAGIC, 0, int(time.time()), len(data), load, entry,
              zlib.crc32(data) & 0xFFFFFFFF,
              IH_OS_LINUX, IH_ARCH_MIPS, IH_TYPE_KERNEL, IH_COMP_NONE,
              name.encode()[:31].ljust(32, b"\0")]
    hdr = HDR.pack(*fields)
    fields[1] = zlib.crc32(hdr) & 0xFFFFFFFF
    return HDR.pack(*fields) + data


def show(path):
    blob = open(path, "rb").read()
    f = HDR.unpack(blob[:64])
    hcrc = zlib.crc32(HDR.pack(*f[:1], 0, *f[2:])) & 0xFFFFFFFF
    dcrc = zlib.crc32(blob[64:64 + f[3]]) & 0xFFFFFFFF
    print(f"magic   {f[0]:#010x} {'ok' if f[0] == MAGIC else 'BAD'}")
    print(f"name    {f[11].rstrip(b'\0').decode(errors='replace')}")
    print(f"size    {f[3]} (+64 = {f[3] + 64}, kernel slot 8388608)")
    print(f"load    {f[4]:#010x}  entry {f[5]:#010x}")
    print(f"os/arch/type/comp {f[7]}/{f[8]}/{f[9]}/{f[10]}")
    print(f"hcrc    {'ok' if hcrc == f[1] else 'BAD'}  dcrc {'ok' if dcrc == f[6] else 'BAD'}")
    ok = f[0] == MAGIC and f[7] == IH_OS_LINUX and f[3] + 64 <= 8 << 20
    print("SPL-compatible:", "yes" if ok else "NO")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", default="0x80f00000")
    ap.add_argument("--entry")
    ap.add_argument("--name", default="Linux")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    if a.show:
        return show(a.files[0])
    src, dst = a.files
    load = int(a.load, 0)
    entry = int(a.entry, 0) if a.entry else load
    data = open(src, "rb").read()
    if data[:4] == b"\x7fELF":
        # The SPL and chainload jump to the first byte: an ELF header there
        # is executed as code (vmlinuz instead of vmlinuz.bin)
        sys.exit("%s is an ELF file; give the raw image (objcopy -O binary)" % src)
    open(dst, "wb").write(build(data, load, entry, a.name))
    return show(dst)


if __name__ == "__main__":
    sys.exit(main())
