#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Boot ROM image of the AD5X SPL, and a first MiB with it.

The X2600 boot ROM (eMMC on MSC0) reads two things from the user area:

* LBA 0 (the protective-MBR sector), bytes 0x000-0x0FF: the "INGE" params
  block, which Ingenic's spl_params_fixer writes (SDK u-boot,
  tools/ingenic-tools/spl_params_fixer_x2600.c, called with offset 0):

    0x00  u32  id          "INGE"
    0x04  u32  length      SPL image length, rounded up to 512 bytes
    0x08  u32  pll_freq    624000000: the APLL rate the descriptors set up
    0x0C  u32  cpccr       0x95073310: CPCCR after the descriptors (SCLK_A
                           from the APLL, CPU /1, L2 /2, AHB0 /4, AHB2 /4,
                           PCLK /8)
    0x10  16 B nand_timing set_rw 3, wait_rw 14, hold_rw 6, set_cs 20,
                           wait_cs 6, trr 12, tedo 15, trhw 30 (unused on
                           eMMC, written anyway)
    0x20  14 x 16 B cpm_desc: register writes the ROM does before it loads
                           the SPL, each {u16 set_addr, u16 poll_addr (CPM
                           offsets), u32 value, u32 poll_h_mask (bits to
                           wait set), u32 poll_l_mask (bits to wait clear)},
                           ended by set_addr = poll_addr = 0xFFFF:
                             CPAPCR  0x034051c1  APLL 624 MHz, wait ON|LOCK
                             CPCCR   0x55773310  dividers, wait CPCSR 2:0 clear
                             CPCCR   0x95073310  sources, wait CPCSR 31:28 set
                             DDRCDR  0x60000001  wait busy clear
                             MSC0CDR 0x20108003  39 MHz, wait busy clear
                             SFCCDR  0x20000007  wait busy clear
                             end

* eMMC byte 0x4400 (LBA 34), the SPL image: a 2 KiB header, then the code.
  The ROM loads it to 0x80001000 and jumps to 0x80001800.

    0x000 u32  "MSPL" (bytes "LPSM")
    0x004 u32  block count: 512-byte blocks the ROM loads, the image length
               rounded up, capped at 48 (24 KiB, SPL_SIZE in the SDK's
               tools/ingenic-tools/mmc_params.c, which writes it)
    0x100 256 B a second copy of the params block (spl_params_fixer with
               offset 256), length included
    0x200-0x7FF zero (the SDK's room for its secure-boot header)

  The stock first MiB (Sep 2024 SPL build 00190): count 0x23, both length
  fields 0x4600, so the ROM loads 0x4600 bytes from 0x4400 and only 0x3E00
  bytes of code. This tool sets all three from the SPL that is written.

  ad5x_spl_image.py image SPL_BIN OUT [--nm NM_OUTPUT]
      header + SPL_BIN (U-Boot's spl/u-boot-spl.bin, code from 0x80001800)
      -> OUT; with --nm (``nm spl/u-boot-spl``) also checks the memory map
  ad5x_spl_image.py first-mib DUMP SPL_IMAGE OUT
      DUMP (a unit's first MiB, read-only) with SPL_IMAGE at 0x4400 and the
      length fields set -> OUT, a file; check it with check_first_mib.py
  ad5x_spl_image.py write-plan DUMP SPL_IMAGE PLAN.json
      what an installer may write for that candidate, and nothing else
  ad5x_spl_image.py apply-plan PLAN.json IN OUT
      the plan applied to the file IN (a first MiB) -> OUT, as an installer
      would apply it to the device
  ad5x_spl_image.py usb-image [--stage2] SPL_IMAGE OUT
      SPL_IMAGE (spl-mmc.img) with the USB tag "KILNUSB1" ("KILNUSB2" with
      --stage2: spl-usb2.bin, for run-uboot) at header offset
      0x7f0 -> OUT (spl-usb.bin), what u-boot/tools/ad5x_usbboot.py sends
      the boot ROM over USB: the same bytes at the same addresses as an
      eMMC start loads, the SPL's code unchanged (u-boot/USB-BOOT.md)
  ad5x_spl_image.py uboot-mib FIRST_MIB U_BOOT_EMMC OUT
      FIRST_MIB (first-mib.img: the unit's first MiB with Kiln's SPL) with
      U_BOOT_EMMC (u-boot-emmc.img) at 0xA400 -> OUT (first-mib-uboot.img):
      only the image's whole sectors change, the rest of its last sector
      keeps FIRST_MIB's bytes; refused unless Kiln's SPL would load it
      (uimage_problems) and it ends before 1 MiB (the first partition)
  ad5x_spl_image.py show FILE
      decode the header and params of a first MiB or an SPL image

The write plan: a first MiB made from a dump carries that dump's GPT and
everything else, which may be stale by the time it is written (the dump
is old, the unit was repartitioned). So nothing should write the
candidate as a whole. The plan lists only the bytes that change, the INGE
length field 0x0004-0x0007 and the SPL range 0x4400-0xA3FF, with the
data and its SHA-256, and what the INGE block and the SPL range must hold
before (SHA-256 of 0x0000-0x00FF and 0x4400-0xA3FF in the dump). An
installer re-reads the device, refuses when the "verify" ranges differ
from the plan, writes exactly the "write" ranges and reads them back.
apply-plan does the same to a file; a plan that writes anywhere else is
refused.

U-Boot proper at 0xA400 (phase 7) gets no plan of its own: the bench
tool (tools/bench/ad5x-uboot-flash) compares the device's first MiB with
first-mib.img and first-mib-uboot.img byte for byte and writes only the
U-Boot range's sectors (u-boot/README.md, "U-Boot proper at 0xA400").

Nothing here writes to a device: inputs and outputs are files.
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib

BLOCK = 512
HEADER_SIZE = 0x800
PARAMS_OFF = 0x100         # in the SPL image header
PARAMS_SIZE = 256
SPL_EMMC_OFF = 0x4400      # the SPL image in the eMMC user area
SPL_AREA_END = 0xA400      # where U-Boot proper starts
MAX_BLOCKS = 48            # 24 KiB: the boot ROM's SPL window
LOAD_ADDR = 0x80001000
CODE_ADDR = LOAD_ADDR + HEADER_SIZE
SRAM_END = 0x80007000
SPL_MAGIC = b"LPSM"        # .word 0x4d53504c, little endian
PARAMS_ID = b"INGE"
CHAINLOAD_MARKER = b"KILN-SPL-CHAINLOAD-TEST-ONLY"
STACK_RESERVE = 0x800      # x2600/u-boot-spl.lds AD5X_SPL_STACK_SIZE
# spl-usb.bin: the tag the SPL looks for at 0x800017f0 (patch 0025); the
# eMMC image has zeros there
USB_TAG_OFF = 0x7F0
USB_TAG = b"KILNUSB1"
# spl-usb2.bin: DDR only, then back to the ROM for U-Boot proper as stage 2
# (patch 0034, ad5x_usbboot.py run-uboot)
USB_TAG_STAGE2 = b"KILNUSB2"
# what the X2600 boot ROM's USB mode takes for stage 1 from 0x80001000
# (Ingenic Cloner's firmwares/x2600/config.cfg: d2i_len=0x7000)
USB_STAGE1_MAX = 0x7000

# CPM register offsets
CPM_CPCCR, CPM_CPAPCR, CPM_DDRCDR = 0x00, 0x10, 0x2C
CPM_MSC0CDR, CPM_SFCCDR, CPM_CPCSR = 0x68, 0x74, 0xD4

PLL_FREQ = 624000000
CPCCR = 0x95073310
NAND_TIMING = bytes([3, 14, 6, 20, 6, 12, 15, 0, 0, 0, 0, 0, 0, 30, 0, 0])
DESCRIPTORS = [
    # set_addr, poll_addr, value, poll_h_mask, poll_l_mask
    (CPM_CPAPCR, CPM_CPAPCR, 0x034051C1, 0x0000000C, 0),
    (CPM_CPCCR, CPM_CPCSR, 0x55773310, 0, 0x00000007),
    (CPM_CPCCR, CPM_CPCSR, 0x95073310, 0xF0000000, 0),
    (CPM_DDRCDR, CPM_DDRCDR, 0x60000001, 0, 0x10000000),
    (CPM_MSC0CDR, CPM_MSC0CDR, 0x20108003, 0, 0x10000000),
    (CPM_SFCCDR, CPM_SFCCDR, 0x20000007, 0, 0x10000000),
    (0xFFFF, 0xFFFF, 0, 0, 0),
]


# U-Boot proper at eMMC 0xA400, a U-Boot uImage, up to the first
# partition (p1 at LBA 2048 on every known unit)
UBOOT_EMMC_OFF = SPL_AREA_END
UBOOT_AREA_END = 1 << 20
# the first MiB's last sector (LBA 2047) is the network rescue record's
# (patch 0045, ad5x_emmc_image.py --rescue): U-Boot proper ends before it,
# as the SPL's AD5X_UBOOT_MAX and build.sh's UBOOT_EMMC_MAX say
RESCUE_LBA = UBOOT_AREA_END // 512 - 1
RESCUE_MAGIC = b"KILN-RESCUE 1\n"
UBOOT_MAX_END = RESCUE_LBA * 512
UIMAGE_MAGIC = 0x27051956
UIMAGE_HEADER = 64
IH_OS_LINUX, IH_OS_U_BOOT, IH_ARCH_MIPS = 5, 17, 5
# spl.c, spl_load_uimage(): the blocks it loads (header from load - 64)
# lie between the SRAM window and ramoops
SPL_LOAD_LOW = 0x80008000
SPL_LOAD_END = 0x8EB00000
UBOOT_LOAD = 0x80100000     # build.sh's mkimage -a/-e
UBOOT_NAME = b"Kiln U-Boot "


class ImageError(Exception):
    pass


def round_up(n, a=BLOCK):
    return (n + a - 1) // a * a


def params_block(length):
    """The 256-byte INGE params block for an SPL image of @length bytes."""
    p = bytearray(PARAMS_SIZE)
    struct.pack_into("<4sIII", p, 0, PARAMS_ID, round_up(length), PLL_FREQ,
                     CPCCR)
    p[0x10:0x20] = NAND_TIMING
    for i, (sa, pa, v, hm, lm) in enumerate(DESCRIPTORS):
        struct.pack_into("<HHIII", p, 0x20 + 16 * i, sa, pa, v, hm, lm)
    return bytes(p)


def blocks_for(length):
    """The header's block count: what the boot ROM loads."""
    n = round_up(length) // BLOCK
    if n > MAX_BLOCKS:
        raise ImageError("SPL image is %d bytes: the boot ROM loads at most "
                         "%d (%d blocks)" % (length, MAX_BLOCKS * BLOCK,
                                             MAX_BLOCKS))
    return n


def spl_image(spl_bin):
    """Header + code, padded to whole blocks."""
    if CHAINLOAD_MARKER in spl_bin:
        raise ImageError("this is the chainload-test SPL "
                         "(CONFIG_AD5X_SPL_CHAINLOAD): it can't start from "
                         "the boot ROM")
    length = HEADER_SIZE + len(spl_bin)
    count = blocks_for(length)
    h = bytearray(HEADER_SIZE)
    h[0:4] = SPL_MAGIC
    struct.pack_into("<I", h, 4, count)
    h[PARAMS_OFF:PARAMS_OFF + PARAMS_SIZE] = params_block(length)
    img = bytes(h) + spl_bin
    return img + bytes(round_up(len(img)) - len(img))


def usb_image(spl_img, tag=USB_TAG):
    """spl-mmc.img -> spl-usb.bin (or spl-usb2.bin with USB_TAG_STAGE2):
    the USB tag in the header's zero room."""
    magic, count, p = decode(spl_img)
    if magic != SPL_MAGIC or p[0:4] != PARAMS_ID:
        raise ImageError("not an SPL image (header missing)")
    if CHAINLOAD_MARKER in spl_img:
        raise ImageError("chainload-test SPL: refused")
    if len(spl_img) != count * BLOCK or count > MAX_BLOCKS:
        raise ImageError("SPL image length %d doesn't match its block count "
                         "%d" % (len(spl_img), count))
    if len(spl_img) > USB_STAGE1_MAX:
        raise ImageError("%d bytes: the boot ROM takes at most %d over USB" %
                         (len(spl_img), USB_STAGE1_MAX))
    room = spl_img[USB_TAG_OFF:USB_TAG_OFF + len(tag)]
    if room != bytes(len(tag)):
        raise ImageError("header offset 0x%x isn't zero (%s)" %
                         (USB_TAG_OFF, room.hex()))
    out = bytearray(spl_img)
    out[USB_TAG_OFF:USB_TAG_OFF + len(tag)] = tag
    return bytes(out)


def parse_nm(text):
    syms = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            try:
                syms[parts[2]] = int(parts[0], 16)
            except ValueError:
                pass
    return syms


def check_layout(syms, bin_len, count):
    """The SPL's memory map against the boot ROM's window and load size.
    Returns a list of problems (empty: fine) and a description."""
    need = ("__text_start", "__image_copy_end", "__bss_start", "__bss_end")
    missing = [s for s in need if s not in syms]
    if missing:
        return ["nm output lacks " + ", ".join(missing)], ""
    text, copy_end = syms["__text_start"], syms["__image_copy_end"]
    bss, bss_end = syms["__bss_start"], syms["__bss_end"]
    stack_bottom = SRAM_END - STACK_RESERVE
    loaded_end = LOAD_ADDR + count * BLOCK
    errs = []
    if text != CODE_ADDR:
        errs.append("code starts at 0x%08x, not 0x%08x" % (text, CODE_ADDR))
    if copy_end - text > bin_len:
        errs.append("the image ends at 0x%08x but the binary is only %d "
                    "bytes" % (copy_end, bin_len))
    if copy_end > loaded_end:
        errs.append("code/data end at 0x%08x, the boot ROM loads only up to "
                    "0x%08x" % (copy_end, loaded_end))
    if bss < copy_end:
        errs.append("BSS (0x%08x) overlaps the image" % bss)
    if bss_end > stack_bottom:
        errs.append("BSS ends at 0x%08x, into the stack reserve from "
                    "0x%08x" % (bss_end, stack_bottom))
    if bss_end > SRAM_END or loaded_end > SRAM_END:
        errs.append("outside the SRAM window (0x%08x)" % SRAM_END)
    desc = ("  0x%08x-0x%08x  header (loaded, unused after the jump)\n"
            "  0x%08x-0x%08x  code, rodata, data (%d bytes)\n"
            "  0x%08x-0x%08x  loaded by the boot ROM (%d blocks)\n"
            "  0x%08x-0x%08x  BSS (%d bytes)\n"
            "  0x%08x-0x%08x  stack reserve (top 0x%08x)\n"
            "  free in the window: %d bytes" %
            (LOAD_ADDR, CODE_ADDR, text, copy_end, copy_end - text,
             LOAD_ADDR, loaded_end, count, bss, bss_end, bss_end - bss,
             stack_bottom, SRAM_END, SRAM_END,
             stack_bottom - max(bss_end, loaded_end)))
    return errs, desc


def decode(data, base=0):
    """Header fields of an SPL image at @base of @data."""
    magic = data[base:base + 4]
    count = struct.unpack_from("<I", data, base + 4)[0]
    p = data[base + PARAMS_OFF:base + PARAMS_OFF + PARAMS_SIZE]
    return magic, count, p


def rescue_record(mib):
    """@mib (a first MiB) holds a network rescue record in LBA 2047."""
    o = RESCUE_LBA * 512
    return mib[o:o + len(RESCUE_MAGIC)] == RESCUE_MAGIC


def first_mib(dump, spl_img):
    """@dump with @spl_img at 0x4400 and the INGE length at 0x0004."""
    if len(dump) != 1 << 20:
        raise ImageError("the dump is %d bytes, not 1 MiB" % len(dump))
    if rescue_record(dump):
        # Kiln's U-Boot would run it at every start
        raise ImageError("the dump holds a network rescue record in LBA "
                         "%d: not a stock first MiB" % RESCUE_LBA)
    if dump[0:4] != PARAMS_ID or dump[SPL_EMMC_OFF:SPL_EMMC_OFF + 4] != \
            SPL_MAGIC:
        raise ImageError("the dump has no INGE block at 0 or no SPL at "
                         "0x4400")
    magic, count, p = decode(spl_img)
    if magic != SPL_MAGIC or p[0:4] != PARAMS_ID:
        raise ImageError("not an SPL image (header missing)")
    if CHAINLOAD_MARKER in spl_img:
        raise ImageError("chainload-test SPL: refused")
    if spl_img[USB_TAG_OFF:USB_TAG_OFF + len(USB_TAG)] in (USB_TAG,
                                                           USB_TAG_STAGE2):
        # on the eMMC every start would count as a fresh one (no tries)
        raise ImageError("this is spl-usb.bin or spl-usb2.bin, for the boot "
                         "ROM's USB mode only: use spl-mmc.img")
    if len(spl_img) != count * BLOCK or count > MAX_BLOCKS:
        raise ImageError("SPL image length %d doesn't match its block count "
                         "%d" % (len(spl_img), count))
    out = bytearray(dump)
    # the SPL range as Ingenic's build pads it (SPL_PAD_TO, 24 KiB): the
    # image, then 0xFF up to U-Boot proper at 0xA400; the stock SPL's code
    # doesn't linger past ours
    out[SPL_EMMC_OFF:SPL_AREA_END] = b"\xff" * (SPL_AREA_END - SPL_EMMC_OFF)
    out[SPL_EMMC_OFF:SPL_EMMC_OFF + len(spl_img)] = spl_img
    # the params block at 0 keeps the unit's own values; only the length
    out[4:8] = spl_img[PARAMS_OFF + 4:PARAMS_OFF + 8]
    # and the image's own params copy keeps the unit's values too
    unit_params = bytearray(dump[SPL_EMMC_OFF + PARAMS_OFF:
                                 SPL_EMMC_OFF + PARAMS_OFF + PARAMS_SIZE])
    unit_params[4:8] = spl_img[PARAMS_OFF + 4:PARAMS_OFF + 8]
    out[SPL_EMMC_OFF + PARAMS_OFF:SPL_EMMC_OFF + PARAMS_OFF + PARAMS_SIZE] \
        = unit_params
    return bytes(out)


def uimage_problems(data, os_, max_len):
    """Why Kiln's SPL's spl_load_uimage() (spl.c) would not start the
    uImage at the start of @data, read from a range of @max_len bytes:
    the same checks in the same terms (test_spl_uimage.py runs the C code
    itself). [] when it would."""
    if len(data) < UIMAGE_HEADER:
        return ["shorter than a uImage header"]
    (magic, hcrc, _, size, load, ep, dcrc, ih_os, arch, _,
     _) = struct.unpack_from(">IIIIIIIBBBB", data, 0)
    if magic != UIMAGE_MAGIC:
        return ["no uImage magic"]
    errs = []
    h = bytearray(data[:UIMAGE_HEADER])
    h[4:8] = bytes(4)
    if zlib.crc32(bytes(h)) != hcrc:
        errs.append("header CRC wrong")
    if arch != IH_ARCH_MIPS:
        errs.append("architecture %d, not MIPS" % arch)
    if ih_os != os_:
        errs.append("OS %d, not %d" % (ih_os, os_))
    if size > max_len - UIMAGE_HEADER:
        errs.append("%d bytes: more than the %d the range holds" %
                    (size, max_len - UIMAGE_HEADER))
    if load & 3 or load < SPL_LOAD_LOW + UIMAGE_HEADER or \
            load > SPL_LOAD_END - BLOCK or size > SPL_LOAD_END - BLOCK - load:
        errs.append("load address 0x%x (size %d) outside 0x%x-0x%x" %
                    (load, size, SPL_LOAD_LOW, SPL_LOAD_END))
    if ep < load or ep - load >= size:
        errs.append("entry point 0x%x outside the image" % ep)
    if errs:
        return errs
    if len(data) < UIMAGE_HEADER + size:
        return ["cut short: %d of %d bytes" % (len(data), UIMAGE_HEADER + size)]
    if zlib.crc32(data[UIMAGE_HEADER:UIMAGE_HEADER + size]) != dcrc:
        return ["data CRC wrong"]
    return []


def uboot_range(uboot_img):
    """The bytes U-Boot proper's whole sectors take from 0xA400."""
    return UBOOT_EMMC_OFF, UBOOT_EMMC_OFF + round_up(len(uboot_img))


def uboot_mib(mib, uboot_img):
    """@mib (first-mib.img) with @uboot_img (u-boot-emmc.img) at 0xA400."""
    if len(mib) != 1 << 20:
        raise ImageError("the first MiB is %d bytes, not 1 MiB" % len(mib))
    errs = uimage_problems(uboot_img, IH_OS_U_BOOT,
                           UBOOT_MAX_END - UBOOT_EMMC_OFF)
    if errs:
        raise ImageError("U-Boot image: Kiln's SPL would refuse it: %s" %
                         "; ".join(errs))
    size, load, ep = struct.unpack_from(">III", uboot_img, 12)
    if len(uboot_img) != UIMAGE_HEADER + size:
        raise ImageError("U-Boot image: %d bytes, its header says %d" %
                         (len(uboot_img), UIMAGE_HEADER + size))
    if load != UBOOT_LOAD or ep != UBOOT_LOAD or \
            not uboot_img[32:64].startswith(UBOOT_NAME):
        raise ImageError("U-Boot image: not Kiln's (load 0x%x, entry 0x%x, "
                         "name %r)" % (load, ep, uboot_img[32:64]))
    if rescue_record(mib):
        raise ImageError("the first MiB holds a network rescue record in "
                         "LBA %d" % RESCUE_LBA)
    if mib[UBOOT_EMMC_OFF:UBOOT_EMMC_OFF + 4] == \
            struct.pack(">I", UIMAGE_MAGIC):
        raise ImageError("the first MiB holds a uImage at 0xA400 already: "
                         "make this from first-mib.img")
    out = bytearray(mib)
    out[UBOOT_EMMC_OFF:UBOOT_EMMC_OFF + len(uboot_img)] = uboot_img
    return bytes(out)


PLAN_FORMAT = "kiln-first-mib-plan 1"
# the only bytes a plan may write: the INGE length, the SPL range
PLAN_WRITE = ((0x4, 0x8), (SPL_EMMC_OFF, SPL_AREA_END))
# what must still be as in the dump: the INGE block, the SPL range
PLAN_VERIFY = ((0x0, PARAMS_SIZE), (SPL_EMMC_OFF, SPL_AREA_END))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_plan(dump, spl_img):
    """The plan to put @spl_img on the unit @dump was read from."""
    cand = first_mib(dump, spl_img)
    return {
        "format": PLAN_FORMAT,
        "device": "eMMC user area (mmcblk0), byte offsets",
        "verify": [{"offset": a, "length": b - a, "sha256": sha256(dump[a:b])}
                   for a, b in PLAN_VERIFY],
        "write": [{"offset": a, "length": b - a, "sha256": sha256(cand[a:b]),
                   "data": cand[a:b].hex()} for a, b in PLAN_WRITE],
    }


def apply_plan(plan, data):
    """@data (a first MiB, or more) with @plan applied; ImageError when the
    plan is malformed, writes elsewhere, or @data isn't what it expects."""
    if not isinstance(plan, dict) or plan.get("format") != PLAN_FORMAT:
        raise ImageError("not a %s" % PLAN_FORMAT)
    try:
        verify = [(int(v["offset"]), int(v["length"]), str(v["sha256"]))
                  for v in plan["verify"]]
        write = [(int(w["offset"]), int(w["length"]), str(w["sha256"]),
                  bytes.fromhex(w["data"])) for w in plan["write"]]
    except (KeyError, TypeError, ValueError) as e:
        raise ImageError("malformed plan (%s)" % e)
    if [(o, o + n) for o, n, _ in verify] != list(PLAN_VERIFY):
        raise ImageError("the plan's verify ranges aren't 0x0-0xff and "
                         "0x4400-0xa3ff")
    if [(o, o + n) for o, n, _, _ in write] != list(PLAN_WRITE):
        raise ImageError("the plan writes outside 0x4-0x7 and "
                         "0x4400-0xa3ff: refused")
    if len(data) < SPL_AREA_END:
        raise ImageError("only %d bytes to apply the plan to" % len(data))
    for o, n, h in verify:
        if sha256(data[o:o + n]) != h:
            raise ImageError("0x%x-0x%x isn't what the plan was made from: "
                             "re-read the device and make a new plan" %
                             (o, o + n - 1))
    out = bytearray(data)
    for o, n, h, d in write:
        if len(d) != n or sha256(d) != h:
            raise ImageError("the plan's data for 0x%x has the wrong length "
                             "or SHA-256" % o)
        out[o:o + n] = d
    return bytes(out)


def show(data):
    base = SPL_EMMC_OFF if len(data) == 1 << 20 else 0
    lines = []
    if base:
        p0 = data[0:PARAMS_SIZE]
        lines.append("LBA 0 params: id %r length 0x%x" %
                     (p0[0:4], struct.unpack_from("<I", p0, 4)[0]))
    magic, count, p = decode(data, base)
    lines.append("SPL header at 0x%x: magic %r, %d blocks (%d bytes loaded, "
                 "%d of code)" % (base, magic, count, count * BLOCK,
                                  count * BLOCK - HEADER_SIZE))
    pid, length, freq, cpccr = struct.unpack_from("<4sIII", p, 0)
    lines.append("params copy: id %r length 0x%x pll_freq %d cpccr 0x%08x" %
                 (pid, length, freq, cpccr))
    for i in range(14):
        sa, pa, v, hm, lm = struct.unpack_from("<HHIII", p, 0x20 + 16 * i)
        if sa == 0xFFFF and pa == 0xFFFF:
            break
        lines.append("  desc %d: set 0x%04x poll 0x%04x value 0x%08x "
                     "high 0x%08x low 0x%08x" % (i, sa, pa, v, hm, lm))
    return "\n".join(lines)


def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("image")
    a.add_argument("spl_bin")
    a.add_argument("out")
    a.add_argument("--nm", help="nm output of spl/u-boot-spl")
    b = sub.add_parser("first-mib")
    b.add_argument("dump")
    b.add_argument("spl_image")
    b.add_argument("out")
    c = sub.add_parser("show")
    c.add_argument("file")
    w = sub.add_parser("write-plan")
    w.add_argument("dump")
    w.add_argument("spl_image")
    w.add_argument("out")
    u = sub.add_parser("usb-image")
    u.add_argument("--stage2", action="store_true",
                   help="tag KILNUSB2 (spl-usb2.bin): DDR, then back to the "
                   "boot ROM for U-Boot proper as stage 2")
    u.add_argument("spl_image")
    u.add_argument("out")
    x = sub.add_parser("apply-plan")
    x.add_argument("plan")
    x.add_argument("input")
    x.add_argument("out")
    v = sub.add_parser("uboot-mib")
    v.add_argument("first_mib")
    v.add_argument("uboot_image")
    v.add_argument("out")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "image":
            spl_bin = read(args.spl_bin)
            img = spl_image(spl_bin)
            count = len(img) // BLOCK
            print("SPL image: %d bytes of code, %d with the header: %d "
                  "blocks of %d the boot ROM can load (%d bytes spare)" %
                  (len(spl_bin), HEADER_SIZE + len(spl_bin), count,
                   MAX_BLOCKS, (MAX_BLOCKS - count) * BLOCK))
            if args.nm:
                errs, desc = check_layout(parse_nm(read(args.nm).decode()),
                                          len(spl_bin), count)
                print("SPL memory map:\n" + desc)
                if errs:
                    raise ImageError("; ".join(errs))
            write(args.out, img)
        elif args.cmd == "first-mib":
            out = first_mib(read(args.dump), read(args.spl_image))
            write(args.out, out)
            print("first MiB with the new SPL: %s" % args.out)
        elif args.cmd == "write-plan":
            plan = write_plan(read(args.dump), read(args.spl_image))
            write(args.out, (json.dumps(plan, indent=1) + "\n").encode())
            print("write plan: %s (writes 0x4-0x7 and 0x4400-0xa3ff only)" %
                  args.out)
        elif args.cmd == "usb-image":
            img = usb_image(read(args.spl_image),
                            USB_TAG_STAGE2 if args.stage2 else USB_TAG)
            write(args.out, img)
            print("USB image: %s, %d bytes to 0x%08x, entry 0x%08x (%d of "
                  "the %d bytes the boot ROM takes over USB)" %
                  (args.out, len(img), LOAD_ADDR, CODE_ADDR, len(img),
                   USB_STAGE1_MAX))
        elif args.cmd == "apply-plan":
            try:
                plan = json.loads(read(args.plan))
            except ValueError as e:
                raise ImageError("%s: %s" % (args.plan, e))
            write(args.out, apply_plan(plan, read(args.input)))
            print("plan applied: %s" % args.out)
        elif args.cmd == "uboot-mib":
            ub = read(args.uboot_image)
            write(args.out, uboot_mib(read(args.first_mib), ub))
            a, b = uboot_range(ub)
            print("first MiB with Kiln's SPL and U-Boot proper: %s (U-Boot "
                  "%d bytes, sectors %d-%d, 0x%x-0x%x)" %
                  (args.out, len(ub), a // BLOCK, b // BLOCK - 1, a, b - 1))
        else:
            print(show(read(args.file)))
    except (ImageError, OSError) as e:
        print("ad5x_spl_image: ERROR: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
