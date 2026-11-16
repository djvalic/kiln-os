#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Check a candidate first MiB of the AD5X eMMC against stock dumps.

  check_first_mib.py CANDIDATE --unit DUMP (--spl SPL_IMAGE | --spl-sha256 HEX)
                     [--uboot U_BOOT_EMMC] [--also DUMP ...]

--unit is the first MiB read from the printer the candidate is for
(dd if=/dev/mmcblk0 bs=1M count=1, before anything was written). --also
are first MiBs of other units with the same stock SPL build; they don't
share the unit's GPT, so only the parts that are the same on every unit
are compared with them.

Passes (exit 0) only when the candidate differs from the unit's dump in
nothing but:
  * the SPL range 0x4400-0xA3FF (header, params copy and code), and
  * the params block's length field at 0x0004-0x0007;
and the candidate's SPL range is a well-formed boot ROM image:
  * "LPSM" at 0x4400, a block count of 1-48 at 0x4404, zeros up to 0x44FF;
  * at 0x4500 the unit's own params copy with only its length changed,
    the same length as at 0x0004, and length = block count * 512;
  * zeros from 0x4600 to the code at 0x4C00;
  * not the chainload-test build;
  * 0xFF after the loaded blocks up to 0xA400, as Ingenic's build pads
    the SPL (no stale stock code past what the boot ROM loads);
  * it is this build's SPL: with --spl, the same bytes as the build's
    spl-mmc.img (its params copy as the unit's, which first-mib keeps);
    with --spl-sha256, that image's SHA-256;
  * the board is the one Kiln's SPL was made for: the unit's stock SPL
    has the DDR3 table "W634GU6QG-11" with the same values as the
    candidate's (the 188 bytes from the name to remap[], sdram.c), and
    builds every value of the candidate's "KILNCLK" record (PLLs and
    CPCCR) as an immediate (lui, or lui + addiu/ori). Another board build
    (the Nov 2025 00437 one, say) is refused until its own dump has been
    looked at and Kiln's SPL made for it.
With --uboot (u-boot-emmc.img; the candidate is first-mib-uboot.img), it
may also differ in U-Boot proper's whole sectors from 0xA400, which must
hold exactly that image (the rest of its last sector the unit's bytes),
end before 1 MiB (the first partition) and be a uImage Kiln's SPL starts:
magic, header and data CRCs, MIPS, OS U-Boot, load address and entry
point as spl_load_uimage() checks them.
With --also, the candidate must also equal each of those dumps outside the
SPL range, the length field, the GPT (0x200-0x43FF) and the U-Boot range.

Reads files only; never opens a device.
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ad5x_spl_image as img  # noqa: E402

MIB = 1 << 20
GPT = (0x200, 0x4400)
SPL = (img.SPL_EMMC_OFF, img.SPL_AREA_END)
LEN0 = (0x4, 0x8)
HDR_COUNT = (img.SPL_EMMC_OFF + 4, img.SPL_EMMC_OFF + 8)
PARAMS = img.SPL_EMMC_OFF + img.PARAMS_OFF
CODE = img.SPL_EMMC_OFF + img.HEADER_SIZE
# sdram.c: struct x2600_ddr_params from the name to remap[]
DDR_NAME = b"W634GU6QG-11\0"
DDR_TABLE_LEN = 188
# sdram.c: x2600_clk, the values the clock setup writes
CLK_TAG = b"KILNCLK\0"
CLK_FIELDS = ("CPCCR (safe dividers)", "CPCCR (dividers)", "CPCCR (sources)",
              "APLL", "MPLL", "EPLL")


def mips_immediates(code):
    """The 32-bit constants MIPS code builds: lui followed (within 8
    instructions, the register not written in between) by addiu or ori on
    the same register, else lui alone. Data words read as code add a few
    more; that only makes the set larger."""
    words = struct.unpack("<%dI" % (len(code) // 4), code[:len(code) // 4 * 4])
    out = set()
    for i, w in enumerate(words):
        if w >> 26 != 0x0F or (w >> 21) & 31:
            continue                                    # not lui
        rt, hi = (w >> 16) & 31, (w & 0xFFFF) << 16
        alone = True
        for x in words[i + 1:i + 9]:
            op, rs, xt, imm = x >> 26, (x >> 21) & 31, (x >> 16) & 31, \
                x & 0xFFFF
            if rs == rt and op == 0x09:                 # addiu
                out.add((hi + imm - (0x10000 if imm & 0x8000 else 0)) &
                        0xFFFFFFFF)
                alone = False
            elif rs == rt and op == 0x0D:               # ori
                out.add(hi | imm)
                alone = False
            # written: rd of SPECIAL, rt of the other I-types but stores
            # and branches
            dest = (x >> 11) & 31 if op == 0 else \
                None if op in (0x01, 0x04, 0x05, 0x06, 0x07) or \
                0x28 <= op <= 0x2F else xt
            if dest == rt:
                break
        if alone:
            out.add(hi)
    return out


def board_values(cand, unit, loaded_end):
    """Problems with the candidate's DDR table and clock record against
    the unit's stock SPL (Kiln's SPL is made for that board build)."""
    errs = []
    _, ucount, _ = img.decode(unit, img.SPL_EMMC_OFF)
    stock = unit[CODE:min(img.SPL_EMMC_OFF + ucount * img.BLOCK, SPL[1])]
    ours = cand[CODE:loaded_end]

    n_stock, n_ours = stock.count(DDR_NAME), ours.count(DDR_NAME)
    if n_stock != 1:
        errs.append("the unit's stock SPL has %s DDR table %s (another "
                    "board build? make Kiln's SPL from its own dump first)"
                    % ("no" if not n_stock else "more than one",
                       DDR_NAME[:-1].decode()))
    if n_ours != 1:
        errs.append("the candidate's SPL has %s DDR table %s" %
                    ("no" if not n_ours else "more than one",
                     DDR_NAME[:-1].decode()))
    if n_stock == 1 and n_ours == 1:
        i, j = stock.index(DDR_NAME), ours.index(DDR_NAME)
        a, b = stock[i:i + DDR_TABLE_LEN], ours[j:j + DDR_TABLE_LEN]
        if a != b:
            k = next((k for k in range(min(len(a), len(b)))
                      if a[k] != b[k]), min(len(a), len(b)))
            errs.append("DDR table %s differs from the unit's stock SPL's "
                        "at byte %d of %d (another board build?)" %
                        (DDR_NAME[:-1].decode(), k, DDR_TABLE_LEN))

    n = ours.count(CLK_TAG)
    if n != 1:
        errs.append("the candidate's SPL has %s KILNCLK clock record" %
                    ("no" if not n else "more than one"))
        return errs
    k = ours.index(CLK_TAG) + len(CLK_TAG)
    vals = struct.unpack_from("<%dI" % len(CLK_FIELDS), ours, k)
    imm = mips_immediates(stock)
    for name, v in zip(CLK_FIELDS, vals):
        if v not in imm:
            errs.append("the unit's stock SPL doesn't set %s 0x%08x as "
                        "Kiln's SPL does (another board build?)" % (name, v))
    return errs


def spl_from_build(cand, spl_img=None, spl_sha256=None):
    """Problems tying the candidate's SPL range to the build's
    spl-mmc.img (its bytes, or its SHA-256)."""
    _, count, _ = img.decode(cand, img.SPL_EMMC_OFF)
    n = count * img.BLOCK
    if not 1 <= count <= img.MAX_BLOCKS:
        return []                       # reported by the image check
    got = bytearray(cand[img.SPL_EMMC_OFF:img.SPL_EMMC_OFF + n])
    # first-mib keeps the unit's params copy; the image has the defaults
    got[img.PARAMS_OFF:img.PARAMS_OFF + img.PARAMS_SIZE] = \
        img.params_block(n)
    if spl_img is not None:
        if len(spl_img) != n:
            return ["the SPL is %d bytes, the build's spl-mmc.img %d: not "
                    "this build's SPL" % (n, len(spl_img))]
        if bytes(got) != spl_img:
            return ["the SPL differs from the build's spl-mmc.img: not "
                    "this build's SPL"]
    if spl_sha256 is not None and \
            hashlib.sha256(bytes(got)).hexdigest() != spl_sha256.lower():
        return ["the SPL's SHA-256 isn't %s: not that build's SPL" %
                spl_sha256]
    return []


def diff_ranges(a, b, skip):
    """Ranges (start, end) where a and b differ, outside the @skip ranges."""
    mask = bytearray(len(a))
    for s, e in skip:
        mask[s:e] = b"\x01" * (e - s)
    out, start = [], None
    for blk in range(0, len(a), 512):
        if a[blk:blk + 512] == b[blk:blk + 512]:
            if start is not None:
                out.append((start, blk))
                start = None
            continue
        for i in range(blk, min(blk + 512, len(a))):
            same = a[i] == b[i] or mask[i]
            if not same and start is None:
                start = i
            elif same and start is not None:
                out.append((start, i))
                start = None
    if start is not None:
        out.append((start, len(a)))
    return out


def fmt(ranges, limit=8):
    s = ", ".join("0x%05x-0x%05x" % (a, b - 1) for a, b in ranges[:limit])
    if len(ranges) > limit:
        s += ", ... (%d ranges)" % len(ranges)
    return s


def check(cand, unit, also=(), spl_img=None, spl_sha256=None,
          uboot_img=None):
    """A list of problems; empty when the candidate passes. Without
    @spl_img and @spl_sha256 the candidate isn't tied to a build (the
    command line requires one of them). With @uboot_img the candidate
    carries it at 0xA400."""
    errs = []
    skip = [SPL, LEN0]
    if uboot_img is not None:
        ub = img.uboot_range(uboot_img)
        if ub[1] > img.UBOOT_AREA_END:
            return ["U-Boot image: %d bytes, more than 0xA400 to 1 MiB" %
                    len(uboot_img)]
        skip.append(ub)
    if len(cand) != MIB:
        return ["candidate is %d bytes, not 1 MiB" % len(cand)]
    if len(unit) != MIB:
        return ["unit dump is %d bytes, not 1 MiB" % len(unit)]
    if unit[0:4] != img.PARAMS_ID or \
            unit[img.SPL_EMMC_OFF:img.SPL_EMMC_OFF + 4] != img.SPL_MAGIC:
        return ["the unit dump doesn't look like a stock first MiB"]

    # 1. against the unit: only the SPL range, the length field (and
    # U-Boot proper's sectors)
    d = diff_ranges(cand, unit, skip)
    if d:
        where = []
        for a, b in d:
            if a < GPT[1] and b > GPT[0]:
                where.append("GPT")
            elif a < 0x200:
                where.append("MBR sector")
            elif uboot_img is not None:
                where.append("outside the SPL and U-Boot")
            else:
                where.append("outside the SPL")
        errs.append("differs from the unit's dump at %s (%s)" %
                    (fmt(d), ", ".join(sorted(set(where)))))

    # 2. the SPL image itself
    base = img.SPL_EMMC_OFF
    magic, count, params = img.decode(cand, base)
    length0 = struct.unpack_from("<I", cand, 4)[0]
    if magic != img.SPL_MAGIC:
        errs.append("no LPSM magic at 0x4400")
    if not 1 <= count <= img.MAX_BLOCKS:
        errs.append("block count %d at 0x4404 (1-%d allowed)" %
                    (count, img.MAX_BLOCKS))
    if any(cand[base + 8:PARAMS]):
        errs.append("header bytes 0x4408-0x44ff not zero")
    unit_params = bytearray(unit[PARAMS:PARAMS + img.PARAMS_SIZE])
    unit_params[4:8] = params[4:8]
    if bytes(unit_params) != params:
        errs.append("params copy at 0x4500 differs from the unit's in more "
                    "than its length")
    plen = struct.unpack_from("<I", params, 4)[0]
    if plen != length0:
        errs.append("params length 0x%x at 0x4504 but 0x%x at 0x0004" %
                    (plen, length0))
    if plen != count * img.BLOCK:
        errs.append("params length 0x%x but block count %d (0x%x bytes)" %
                    (plen, count, count * img.BLOCK))
    if any(cand[PARAMS + img.PARAMS_SIZE:base + img.HEADER_SIZE]):
        errs.append("header bytes 0x4600-0x4bff not zero")
    loaded_end = base + count * img.BLOCK
    if img.CHAINLOAD_MARKER in cand[base:loaded_end]:
        errs.append("the chainload-test SPL (it can't start from the boot "
                    "ROM)")
    tail = cand[loaded_end:SPL[1]]
    if loaded_end <= SPL[1] and tail != b"\xff" * len(tail):
        errs.append("bytes after the loaded SPL (0x%x-0x%x) not the 0xFF "
                    "fill the SDK pads with" % (loaded_end, SPL[1] - 1))
    errs += spl_from_build(cand, spl_img, spl_sha256)
    errs += board_values(cand, unit, min(loaded_end, SPL[1]))

    # 2b. U-Boot proper at 0xA400
    if uboot_img is not None:
        a, b = ub
        n = len(uboot_img)
        if cand[a:a + n] != uboot_img:
            errs.append("0x%x-0x%x isn't the build's u-boot-emmc.img" %
                        (a, a + n - 1))
        if cand[a + n:b] != unit[a + n:b]:
            errs.append("the rest of U-Boot's last sector (0x%x-0x%x) isn't "
                        "the unit's" % (a + n, b - 1))
        p = img.uimage_problems(cand[a:img.UBOOT_AREA_END], img.IH_OS_U_BOOT,
                                img.UBOOT_AREA_END - a)
        if p:
            errs.append("U-Boot at 0xA400: Kiln's SPL would not start it: "
                        "%s" % "; ".join(p))
    # 3. against other units: everything but the SPL range, length, GPT
    for name, other in also:
        if len(other) != MIB:
            errs.append("%s is not 1 MiB" % name)
            continue
        d = diff_ranges(cand, other, skip + [GPT])
        if d:
            errs.append("differs from %s outside the SPL and the GPT at %s"
                        % (name, fmt(d)))
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("candidate")
    ap.add_argument("--unit", required=True,
                    help="this printer's own first MiB")
    ap.add_argument("--also", action="append", default=[],
                    help="another unit's first MiB (same SPL build)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--spl", help="the build's spl-mmc.img")
    g.add_argument("--spl-sha256", help="SHA-256 of the build's spl-mmc.img")
    ap.add_argument("--uboot", help="the build's u-boot-emmc.img, at 0xA400 "
                    "in the candidate")
    a = ap.parse_args(argv)
    cand = img.read(a.candidate)
    unit = img.read(a.unit)
    also = [(p, img.read(p)) for p in a.also]
    ub = img.read(a.uboot) if a.uboot else None
    errs = check(cand, unit, also,
                 spl_img=img.read(a.spl) if a.spl else None,
                 spl_sha256=a.spl_sha256, uboot_img=ub)
    _, count, _ = img.decode(cand, img.SPL_EMMC_OFF)
    if errs:
        for e in errs:
            print("check_first_mib: FAIL: " + e)
        return 1
    print("check_first_mib: ok: only the SPL (%d blocks, %d bytes loaded)%s "
          "and the length fields differ from %s%s; the SPL is the build's "
          "(%s); DDR table %s and clocks as in the unit's stock SPL%s" %
          (count, count * img.BLOCK,
           ", U-Boot proper at 0xA400 (%d sectors)" %
           ((len(ub) + 511) // 512) if ub is not None else "", a.unit,
           "; outside the GPT also the same as %d other dump(s)" % len(also)
           if also else "", "spl-mmc.img" if a.spl else "SHA-256",
           DDR_NAME[:-1].decode(),
           "; U-Boot is the build's u-boot-emmc.img, a uImage Kiln's SPL "
           "starts, ending at 0x%x" % img.uboot_range(ub)[1]
           if ub is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
