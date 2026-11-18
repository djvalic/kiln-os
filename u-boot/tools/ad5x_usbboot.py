#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Start Kiln's SPL from the Ingenic X2600 boot ROM over USB (AD5X, J28).

The bench's cold-start test (u-boot/USB-BOOT.md): the boot ROM's USB mode
loads stage 1 into the SRAM window and runs it; nothing is written to the
eMMC. The SPL then boots the flagged slot from the eMMC, read-only, as it
would from an eMMC start.

  ad5x_usbboot.py info
      GET_CPU_INFO, and the device's descriptors
  ad5x_usbboot.py run-spl spl-usb.bin
      GET_CPU_INFO, SET_DATA_ADDR 0x80001000, SET_DATA_LEN, the image on
      bulk OUT, FLUSH_CACHE, PROG_START1 0x80001800
  --dry-run   print the exact transfers instead (no USB, no pyusb needed)

Needs pyusb and libusb-1.0 for real use (not for --dry-run or the tests),
e.g. in a venv: python3 -m venv ~/.venv/usb && ~/.venv/usb/bin/pip install
pyusb; and access to the device (a udev rule for a108:eaef, or root).

The protocol, as the sources below agree:

* The device: VID:PID a108:eaef (the boot ROM; djvalic/kiln-os#68 saw it
  on an AD5X after the soft entry), one vendor-class interface, bulk
  endpoints 0x01 OUT and 0x81 IN, 512-byte packets at high speed (Rockbox
  utils/jztool/src/device_info.c, X1600 entry, seen on hardware).
* Vendor requests on EP0 to the device, recipient device:
    0x00 GET_CPU_INFO   IN  (bmRequestType 0xC0), wLength 5: an ID
                        string; the X2600 answers 'X2600', 5 bytes, no NUL
                        (seen on an AD5X, djvalic/kiln-os#68), as the X1600
                        and Cloner's X2600 configs (cpu_info_length=5)
    0x01 SET_DATA_ADDR  OUT (0x40), no data: wValue = address bits 31:16,
                        wIndex = bits 15:0; the address must be 4-aligned
    0x02 SET_DATA_LEN   OUT (0x40), the length split the same way
    0x03 FLUSH_CACHE    OUT (0x40), wValue = wIndex = 0
    0x04 PROG_START1    OUT (0x40), the entry point split as above: run
                        stage 1 (in SRAM; Ingenic's own stage 1 returns to
                        the ROM, Kiln's SPL doesn't: it boots the slot)
    0x05 PROG_START2    OUT (0x40), the same for stage 2 in DDR (unused)
  then the data of SET_DATA_ADDR/SET_DATA_LEN on bulk OUT 0x01.
  Sources: Ingenic's GPL device side, SDK u-boot common/spl/usb_boot.c
  handle_setup_packet() (address = (word1 & 0xffff0000) | (word2 &
  0xffff), i.e. wValue << 16 | wIndex; the request type is checked only
  for "vendor"; misaligned addresses are dropped) with
  include/usb_boot/usb_boot.h and include/cloner/cloner.h (request
  numbers); Ingenic's GPL host side, SDK u-boot common/usb_load.c
  (USB_TYPE_VENDOR | USB_RECIP_DEVICE | USB_DIR_OUT, STAGE_ADDR_MSB/LSB,
  stage 1: SET_DATA_ADDR, SET_DATA_LEN, bulk, FLUSH_CACHE, PROG_STAGE1);
  Rockbox utils/jztool/src/usb.c (Aidan MacDonald, GPL-2.0-or-later: the
  directions, GET_CPU_INFO as IN verified on an X1600, 1 s control and
  10 s bulk timeouts, EP 1); ballaswag/ingenic-usbboot usbboot.c (the
  same lineage, X2000: stage 1 loaded to 0xb2401000 with its 2 KiB
  parameter area first, started at 0xb2401800).
* X2600 stage 1: Ingenic Cloner 2.5.43's firmwares/x2600/config.cfg (a
  text config; nothing of Cloner is used here): ginfo=0x80001000,
  spl=0x80001800, d2i_len=0x7000 (written "%23d2i_len", Qt's escape of
  "#"); the SDK's include/configs/burner_x2600.h (CONFIG_SPL_GINFO_BASE
  0x80001000, size 0x800; CONFIG_SPL_TEXT_BASE 0x80001800). Cloner sends
  2 KiB of parameter records (BDIF/DDR/BOOT, xburst2/param_manage.c) and
  its stage 1 code behind them as one block to 0x80001000; Kiln sends its
  boot ROM image the same way: the 2 KiB header (as on the eMMC), the
  code from 0x80001800. Kiln's SPL reads nothing from the header but its
  USB tag (u-boot/tools/ad5x_spl_image.py usb-image).

Cache flush before PROG_START1: Ingenic's usb_load.c flushes after the
upload; Rockbox's X1000 path and ballaswag's X2000 path don't (their
stage 1 sits in uncached or TCSM memory); Rockbox's X1600 path flushes
before the upload. The X2600's window is KSEG0 (cached), so this tool
follows Ingenic's order; --no-flush leaves FLUSH_CACHE out. Which one the
X2600 ROM needs is for hardware to show.

Nothing here writes to a disk or the printer's eMMC: only the boot ROM's
SRAM, over USB, and only on run-spl.
"""
import argparse
import hashlib
import struct
import sys

VID, PID = 0xA108, 0xEAEF

GET_CPU_INFO = 0x00
SET_DATA_ADDR = 0x01
SET_DATA_LEN = 0x02
FLUSH_CACHE = 0x03
PROG_START1 = 0x04
PROG_START2 = 0x05
REQ_NAMES = {GET_CPU_INFO: "GET_CPU_INFO", SET_DATA_ADDR: "SET_DATA_ADDR",
             SET_DATA_LEN: "SET_DATA_LEN", FLUSH_CACHE: "FLUSH_CACHE",
             PROG_START1: "PROG_START1", PROG_START2: "PROG_START2"}

# bmRequestType: vendor, recipient device, and the direction bit
RT_VENDOR_OUT = 0x40
RT_VENDOR_IN = 0xC0
EP_BULK_OUT = 0x01
EP_BULK_IN = 0x81

CPU_INFO_LEN = 5          # the X2600 answers 'X2600', 5 bytes, no NUL (alexshev86, #68)
CTRL_TIMEOUT_MS = 1000     # Rockbox jztool, ballaswag
BULK_TIMEOUT_MS = 10000

# X2600 stage 1 (see above) and Kiln's boot ROM image (ad5x_spl_image.py)
LOAD_ADDR = 0x80001000
HEADER_SIZE = 0x800
ENTRY_ADDR = LOAD_ADDR + HEADER_SIZE
STAGE1_MAX = 0x7000
BLOCK = 512
MAX_BLOCKS = 48
SPL_MAGIC = b"LPSM"
PARAMS_OFF = 0x100
PARAMS_ID = b"INGE"
USB_TAG_OFF = 0x7F0
USB_TAG = b"KILNUSB1"
# stage 1 only: the SPL sets up DDR and goes back to the boot ROM, which
# then takes U-Boot proper as stage 2 (run-uboot)
USB_TAG_STAGE2 = b"KILNUSB2"
UBOOT_ADDR = 0x80100000       # U-Boot proper's CONFIG_TEXT_BASE
STAGE1_RETURN_MS = 20000      # PROG_START1 until the SPL is back in the ROM
CHAINLOAD_MARKER = b"KILN-SPL-CHAINLOAD-TEST-ONLY"

EXIT_OK, EXIT_ERROR, EXIT_START_UNCONFIRMED = 0, 1, 3


class UsbBootError(Exception):
    pass


class StartUnconfirmed(UsbBootError):
    """PROG_START1 went out but its status stage didn't come back."""


def split(value):
    """A 32-bit address or length as the ROM takes it: (wValue, wIndex)."""
    if not 0 <= value <= 0xFFFFFFFF:
        raise UsbBootError("0x%x doesn't fit 32 bits" % value)
    return value >> 16, value & 0xFFFF


# ---- the image ----

def check_image(img, tag=None):
    """Kiln's boot ROM image (spl-usb.bin or spl-mmc.img): a list of
    notes; UsbBootError when it can't be sent."""
    n = len(img)
    if n < HEADER_SIZE + 4 or n % BLOCK:
        raise UsbBootError("%d bytes: not a boot ROM image (a 2 KiB header "
                           "and code, in 512-byte blocks)" % n)
    if img[0:4] != SPL_MAGIC or img[PARAMS_OFF:PARAMS_OFF + 4] != PARAMS_ID:
        raise UsbBootError("no LPSM header with an INGE params copy: not "
                           "Kiln's spl-usb.bin / spl-mmc.img")
    count = struct.unpack_from("<I", img, 4)[0]
    length = struct.unpack_from("<I", img, PARAMS_OFF + 4)[0]
    if count * BLOCK != n or count > MAX_BLOCKS:
        raise UsbBootError("the header's block count %d doesn't match the "
                           "%d bytes (at most %d blocks)" %
                           (count, n, MAX_BLOCKS))
    if length != n:
        raise UsbBootError("the params length 0x%x isn't the image's 0x%x" %
                           (length, n))
    if CHAINLOAD_MARKER in img:
        raise UsbBootError("the chainload-test SPL can't start from the "
                           "boot ROM")
    if n > STAGE1_MAX:
        raise UsbBootError("%d bytes, the boot ROM takes at most %d" %
                           (n, STAGE1_MAX))
    notes = []
    want = tag or USB_TAG
    tag = img[USB_TAG_OFF:USB_TAG_OFF + len(want)]
    if want == USB_TAG_STAGE2 and tag != want:
        # without it the SPL boots the eMMC instead of going back to the
        # boot ROM, and the stage 2 that follows has nobody to take it
        raise UsbBootError("no KILNUSB2 tag at 0x%x: run-uboot needs "
                           "spl-usb2.bin (ad5x_spl_image.py usb-image "
                           "--stage2), not %s" %
                           (USB_TAG_OFF, "spl-usb.bin" if tag == USB_TAG
                            else "spl-mmc.img"))
    if tag != want:
        notes.append("no USB tag (this is spl-mmc.img, not spl-usb.bin): "
                     "the SPL will count the scratch pad's tries and skip "
                     "its DDR test, as on an eMMC start (and may stop at once "
                     "after its own USB mode request: patch 0028)")
    return notes


# ---- transports: pyusb, or printing the transfers ----

def describe_ctrl(rt, req, value, index, length, timeout, note=""):
    return ("%-13s ctrl %-3s bmRequestType=0x%02x bRequest=0x%02x "
            "wValue=0x%04x wIndex=0x%04x wLength=%d timeout=%dms%s" %
            (REQ_NAMES.get(req, "0x%02x" % req),
             "IN" if rt & 0x80 else "OUT", rt, req, value, index, length,
             timeout, note))


def describe_bulk(ep, data, timeout):
    return ("%-13s bulk OUT ep=0x%02x length=%d sha256=%s timeout=%dms" %
            ("data", ep, len(data), hashlib.sha256(data).hexdigest(),
             timeout))


class UsbTransport:
    """Transfers through a pyusb device (or anything with its
    ctrl_transfer() and write())."""

    def __init__(self, dev, log=None):
        self.dev = dev
        self.log = log

    def _usb_error(self, what, e):
        return UsbBootError("%s: %s" % (what, e))

    def ctrl_out(self, req, value, index, timeout, note=""):
        if self.log:
            self.log(describe_ctrl(RT_VENDOR_OUT, req, value, index, 0,
                                   timeout, note))
        try:
            self.dev.ctrl_transfer(RT_VENDOR_OUT, req, value, index, None,
                                   timeout)
        except Exception as e:  # usb.core.USBError, by duck type
            raise self._usb_error(REQ_NAMES.get(req, hex(req)), e)

    def ctrl_in(self, req, value, index, length, timeout, note=""):
        if self.log:
            self.log(describe_ctrl(RT_VENDOR_IN, req, value, index, length,
                                   timeout, note))
        try:
            data = self.dev.ctrl_transfer(RT_VENDOR_IN, req, value, index,
                                          length, timeout)
        except Exception as e:
            raise self._usb_error(REQ_NAMES.get(req, hex(req)), e)
        return bytes(data)

    def bulk_out(self, ep, data, timeout):
        if self.log:
            self.log(describe_bulk(ep, data, timeout))
        try:
            n = self.dev.write(ep, data, timeout)
        except Exception as e:
            raise self._usb_error("bulk OUT 0x%02x" % ep, e)
        if n != len(data):
            raise UsbBootError("bulk OUT 0x%02x: %d of %d bytes went out" %
                               (ep, n, len(data)))


class DryRunTransport:
    """Prints each transfer; nothing is sent."""

    def __init__(self, out):
        self.out = out

    def ctrl_out(self, req, value, index, timeout, note=""):
        self.out(describe_ctrl(RT_VENDOR_OUT, req, value, index, 0, timeout,
                               note))

    def ctrl_in(self, req, value, index, length, timeout, note=""):
        self.out(describe_ctrl(RT_VENDOR_IN, req, value, index, length,
                               timeout, note))
        return b""

    def bulk_out(self, ep, data, timeout):
        self.out(describe_bulk(ep, data, timeout))


# ---- the requests ----

def get_cpu_info(t, length=CPU_INFO_LEN, timeout=CTRL_TIMEOUT_MS):
    return t.ctrl_in(GET_CPU_INFO, 0, 0, length, timeout)


def send(t, addr, data, timeout=CTRL_TIMEOUT_MS,
         bulk_timeout=BULK_TIMEOUT_MS):
    """SET_DATA_ADDR, SET_DATA_LEN, then the data on bulk OUT 0x01."""
    if addr & 3:
        raise UsbBootError("0x%08x: the boot ROM drops an address that "
                           "isn't 4-byte aligned" % addr)
    v, i = split(addr)
    t.ctrl_out(SET_DATA_ADDR, v, i, timeout, " (address 0x%08x)" % addr)
    v, i = split(len(data))
    t.ctrl_out(SET_DATA_LEN, v, i, timeout, " (%d bytes)" % len(data))
    t.bulk_out(EP_BULK_OUT, data, bulk_timeout)


def flush_cache(t, timeout=CTRL_TIMEOUT_MS):
    t.ctrl_out(FLUSH_CACHE, 0, 0, timeout)


def prog_start1(t, entry, timeout=CTRL_TIMEOUT_MS):
    v, i = split(entry)
    try:
        t.ctrl_out(PROG_START1, v, i, timeout, " (entry 0x%08x)" % entry)
    except UsbBootError as e:
        raise StartUnconfirmed(
            "%s. The data went out; the boot ROM may have jumped before "
            "the status stage: watch the serial console" % e)


def prog_start2(t, entry, timeout=CTRL_TIMEOUT_MS):
    v, i = split(entry)
    try:
        t.ctrl_out(PROG_START2, v, i, timeout, " (entry 0x%08x)" % entry)
    except UsbBootError as e:
        raise StartUnconfirmed(
            "%s. U-Boot went out; the boot ROM may have jumped before the "
            "status stage: watch the serial console" % e)


def run_uboot(t, spl_img, uboot, timeout=CTRL_TIMEOUT_MS,
              bulk_timeout=BULK_TIMEOUT_MS, cpu_info_len=CPU_INFO_LEN,
              out=print, sleep=None):
    """Stage 1 (the SPL tagged KILNUSB2: DDR, then back to the ROM), then
    U-Boot proper into DDR as stage 2."""
    import time
    sleep = sleep or time.sleep
    for note in check_image(spl_img, USB_TAG_STAGE2):
        out("note: " + note)
    info = get_cpu_info(t, cpu_info_len, timeout)
    if info:
        out("boot ROM: %s" % format_cpu_info(info))
    send(t, LOAD_ADDR, spl_img, timeout, bulk_timeout)
    flush_cache(t, timeout)
    # the status stage comes back once the SPL returns to the ROM (DDR set
    # up and tested: a few seconds)
    v, i = split(ENTRY_ADDR)
    t.ctrl_out(PROG_START1, v, i, STAGE1_RETURN_MS,
               " (entry 0x%08x; stage 1 returns)" % ENTRY_ADDR)
    out("stage 1 done: DDR is up, the boot ROM is back")
    sleep(0.2)
    send(t, UBOOT_ADDR, uboot, timeout, bulk_timeout)
    flush_cache(t, timeout)
    prog_start2(t, UBOOT_ADDR, timeout)
    return info


def run_spl(t, img, flush=True, timeout=CTRL_TIMEOUT_MS,
            bulk_timeout=BULK_TIMEOUT_MS, cpu_info_len=CPU_INFO_LEN,
            out=print):
    """The whole stage-1 start. Returns the CPU info bytes."""
    for note in check_image(img):
        out("note: " + note)
    info = get_cpu_info(t, cpu_info_len, timeout)
    if info:
        out("boot ROM: %s" % format_cpu_info(info))
    send(t, LOAD_ADDR, img, timeout, bulk_timeout)
    if flush:
        flush_cache(t, timeout)
    prog_start1(t, ENTRY_ADDR, timeout)
    return info


def format_cpu_info(b):
    text = b.split(b"\0", 1)[0].decode("ascii", "replace")
    return "%r (%d bytes: %s)" % (text, len(b), b.hex())


# ---- pyusb ----

def import_usb():
    try:
        import usb.core
        import usb.util
    except ImportError:
        raise UsbBootError(
            "pyusb isn't installed (needed for everything but --dry-run): "
            "python3 -m venv ~/.venv/usb && ~/.venv/usb/bin/pip install "
            "pyusb, then run this with ~/.venv/usb/bin/python3; libusb-1.0 "
            "must be installed too")
    return usb


def open_device(bus=None, address=None):
    usb = import_usb()
    try:
        devs = list(usb.core.find(find_all=True, idVendor=VID,
                                  idProduct=PID))
    except usb.core.NoBackendError:
        raise UsbBootError("pyusb found no libusb backend: install "
                           "libusb-1.0")
    if bus is not None:
        devs = [d for d in devs if d.bus == bus]
    if address is not None:
        devs = [d for d in devs if d.address == address]
    if not devs:
        raise UsbBootError(
            "no %04x:%04x device: is the printer in USB boot mode "
            "(tools/bench/ad5x-usbboot-mode, or K4 closed at power-on), "
            "the laptop on J28 (D+/D-/GND), and does lsusb list it?" %
            (VID, PID))
    if len(devs) > 1:
        raise UsbBootError("%d boot ROM devices: pick one with --bus and "
                           "--address (%s)" % (len(devs), ", ".join(
                               "bus %d address %d" % (d.bus, d.address)
                               for d in devs)))
    dev = devs[0]
    try:
        try:
            cfg = dev.get_active_configuration()
        except usb.core.USBError:
            cfg = None
        if cfg is None:
            dev.set_configuration()
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass
        usb.util.claim_interface(dev, 0)
    except usb.core.USBError as e:
        if getattr(e, "errno", None) == 13:
            raise UsbBootError(
                "no permission for bus %d address %d: a udev rule "
                "(SUBSYSTEM==\"usb\", ATTR{idVendor}==\"a108\", "
                "ATTR{idProduct}==\"eaef\", MODE=\"0660\", TAG+=\"uaccess\") "
                "or run as root" % (dev.bus, dev.address))
        raise UsbBootError("can't open the device: %s" % e)
    return dev


def close_device(dev):
    try:
        import usb.util
        usb.util.dispose_resources(dev)
    except Exception:
        pass


def describe_device(dev):
    """Bus, speed, strings and endpoints, as far as they can be read."""
    speeds = {1: "low", 2: "full", 3: "high", 4: "super"}
    speed = speeds.get(getattr(dev, "speed", None))
    if speed is None:
        # pyusb on Windows leaves dev.speed empty for this device; 512-byte
        # bulk packets only exist at high speed (or faster)
        try:
            intf = dev.get_active_configuration()[(0, 0)]
            if any(ep.wMaxPacketSize >= 512 for ep in intf):
                speed = "high (from the 512-byte packets)"
        except Exception:
            pass
    lines = ["device %04x:%04x on bus %s address %s, %s speed" %
             (dev.idVendor, dev.idProduct, getattr(dev, "bus", "?"),
              getattr(dev, "address", "?"), speed or "unknown")]
    for attr in ("manufacturer", "product", "serial_number"):
        try:
            v = getattr(dev, attr)
        except Exception:
            v = None
        if v:
            lines.append("  %s: %s" % (attr.replace("_", " "), v))
    try:
        intf = dev.get_active_configuration()[(0, 0)]
        lines.append("  interface 0: class 0x%02x, %d endpoints" %
                     (intf.bInterfaceClass, intf.bNumEndpoints))
        for ep in intf:
            lines.append("    endpoint 0x%02x, attributes 0x%02x, max "
                         "packet %d" % (ep.bEndpointAddress, ep.bmAttributes,
                                        ep.wMaxPacketSize))
    except Exception as e:
        lines.append("  (no configuration descriptor: %s)" % e)
    return "\n".join(lines)


def check_endpoints(dev):
    """The bulk OUT endpoint must be there, when the descriptors say."""
    try:
        intf = dev.get_active_configuration()[(0, 0)]
        eps = [ep.bEndpointAddress for ep in intf]
    except Exception:
        return
    if EP_BULK_OUT not in eps:
        raise UsbBootError("the device has no bulk OUT endpoint 0x%02x "
                           "(endpoints: %s): not the boot ROM?" %
                           (EP_BULK_OUT, ", ".join("0x%02x" % e
                                                   for e in eps)))


# ---- command line ----

def read_file(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise UsbBootError("%s: %s" % (path, e.strerror or e))


def main(argv=None, out=print, err=None, opener=open_device,
         closer=close_device):
    err = err or (lambda s: print(s, file=sys.stderr))
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog="u-boot/USB-BOOT.md has the bench procedure.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the transfers, send nothing")
    ap.add_argument("--timeout", type=int, default=CTRL_TIMEOUT_MS,
                    metavar="MS", help="control transfers (default %(default)s)")
    ap.add_argument("--bulk-timeout", type=int, default=BULK_TIMEOUT_MS,
                    metavar="MS", help="the bulk transfer (default %(default)s)")
    ap.add_argument("--cpu-info-length", type=int, default=CPU_INFO_LEN,
                    metavar="N", help="wLength of GET_CPU_INFO "
                    "(default %(default)s)")
    ap.add_argument("--bus", type=int, help="the device's USB bus")
    ap.add_argument("--address", type=int, help="its address on the bus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="GET_CPU_INFO and the descriptors")
    r = sub.add_parser("run-spl", help="load the SPL to 0x%08x and start it "
                       "at 0x%08x" % (LOAD_ADDR, ENTRY_ADDR))
    r.add_argument("image", help="spl-usb.bin (u-boot/build.sh output)")
    r.add_argument("--no-flush", action="store_true",
                   help="no FLUSH_CACHE before PROG_START1")
    u = sub.add_parser("run-uboot", help="the SPL as stage 1 (DDR only, "
                       "tagged KILNUSB2), then U-Boot proper to 0x%08x as "
                       "stage 2: Kiln's U-Boot then offers the eMMC as a "
                       "USB disk (ums)" % UBOOT_ADDR)
    u.add_argument("image", help="spl-usb2.bin: spl-mmc.img tagged KILNUSB2")
    u.add_argument("uboot", help="u-boot.bin (raw, linked at 0x%08x)" %
                   UBOOT_ADDR)
    args = ap.parse_args(argv)
    for name in ("timeout", "bulk_timeout", "cpu_info_length"):
        if getattr(args, name) <= 0:
            err("ad5x_usbboot: ERROR: --%s must be positive" %
                name.replace("_", "-"))
            return EXIT_ERROR

    dev = None
    try:
        img = read_file(args.image) if args.cmd in ("run-spl",
                                                    "run-uboot") else None
        if img is not None:
            check_image(img, USB_TAG_STAGE2 if args.cmd == "run-uboot"
                        else None)
        if args.dry_run:
            out("dry run: nothing is sent; the transfers, in order:")
            t = DryRunTransport(out)
        else:
            dev = opener(args.bus, args.address)
            if args.cmd == "info":
                out(describe_device(dev))
            else:
                check_endpoints(dev)
            t = UsbTransport(dev)
        if args.cmd == "info":
            info = get_cpu_info(t, args.cpu_info_length, args.timeout)
            if not args.dry_run:
                out("GET_CPU_INFO: %s" % format_cpu_info(info))
        elif args.cmd == "run-uboot":
            run_uboot(t, img, read_file(args.uboot), timeout=args.timeout,
                      bulk_timeout=args.bulk_timeout,
                      cpu_info_len=args.cpu_info_length, out=out,
                      sleep=(lambda s: None) if args.dry_run else None)
            if not args.dry_run:
                out("U-Boot proper started; it offers the eMMC over USB "
                    "(watch for a new USB disk on this host)")
        else:
            run_spl(t, img, flush=not args.no_flush, timeout=args.timeout,
                    bulk_timeout=args.bulk_timeout,
                    cpu_info_len=args.cpu_info_length, out=out)
            if not args.dry_run:
                out("started: %d bytes at 0x%08x, entry 0x%08x. On the "
                    "console: \"SPL: boot ROM\", \"SPL: started over USB\", "
                    "the DDR test, then the slot's kernel from the eMMC" %
                    (len(img), LOAD_ADDR, ENTRY_ADDR))
    except StartUnconfirmed as e:
        err("ad5x_usbboot: WARNING: %s" % e)
        return EXIT_START_UNCONFIRMED
    except UsbBootError as e:
        err("ad5x_usbboot: ERROR: %s" % e)
        return EXIT_ERROR
    finally:
        if dev is not None:
            closer(dev)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
