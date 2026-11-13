#!/usr/bin/env python3
# Copyright (C) 2026 Hunter Laux <hunterlaux@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
tools/flash_iap.py - Open-source firmware flasher for Flashforge IAP MCUs.

Flashes microcontroller firmware using the Flashforge In-Application Programming
(IAP) serial bootloader protocol. Used for both the toolhead board (eboard on
/dev/ttyS5) and the Intelligent Filament System (IFS MCU on /dev/ttyS4) on the
Flashforge Adventurer 5X. Replaces the closed-source vendor binaries
(IAPCommand, IFSCommand, ifsF37).

Protocol:
  - Bootloader Entry:
    - eboard: bootloader runs automatically at power-on; prints "Ready" and waits.
    - IFS: bootloader is entered either by power-cycling or sending "F37\\r\\n"
      at 115200 8N1 (which erases the bootloader's valid-app flag page at
      0x0800D000 and resets into the bootloader).
  - Synchronization (115200 8E1):
    - Host sends 'C' (0x43) once per second.
    - Bootloader replies with ACK (0x06) when ready to receive frames, or 0x07
      ("Update :HD", meaning no update written).
  - Frame Transmission (1030 bytes per frame):
    - Byte 0: 0x01 (SOH)
    - Byte 1: Sequence number (0-indexed uint8)
    - Byte 2..3: Unpadded byte count in this 1 KB block (uint16 little-endian;
      0x0400 = 1024 for full blocks, or remaining byte count on the final block)
    - Byte 4..1027: 1024 bytes firmware data (padded with 0xFF)
    - Byte 1028..1029: CRC-16-CCITT (poly 0x1021, init 0x0000, uint16 little-endian)
      computed over all 1024 data bytes (including 0xFF padding)
    - Bootloader returns ACK (0x06) on success, or NAK (0x15) on CRC error.
      Only a NAK'd frame is sent again. With no answer the write stops
      before EOT: the bootloader stays (on the IFS the flag page stays
      erased) but waits for the next frame and ignores 'C' until it is
      powered off; after a power-cycle it takes a new write
      (docs/mcu-flashing.md, "Interrupted eboard flash").
  - End of Transmission:
    - Host sends EOT (0x04); bootloader acknowledges with ACK (0x06).
    - eboard: host sends 'A' (0x41) to start the application; bootloader
      acknowledges with ACK (0x06).
    - IFS: host sends nothing after EOT; the bootloader starts the application
      itself. Stock IFSCommand sends no 'A' (recorded under qemu 2026-11-04),
      and an 'A' after EOT left the IFS with an erased application.
"""

import argparse
import os
import select
import struct
import sys
import termios
import time

CMD_SOH = b"\x01"
CMD_EOT = b"\x04"
CMD_ACK = b"\x06"
CMD_START = b"A"
CMD_HD = b"\x07"
CMD_NAK = b"\x15"
CMD_POLL_CRC = b"\x43"  # 'C'

FRAME_DATA_SIZE = 1024
FRAME_TOTAL_SIZE = 1030  # SOH(1) + seq(1) + len(2) + data(1024) + crc(2)
# How long a frame's ACK or NAK may take. A frame is sent again only after a
# NAK: the bootloader writes every frame it accepts, so a frame resent after
# a late or lost ACK is written twice. That left the IFS with a broken
# application that still passes the bootloader's checks (2026-10-29, SWD
# only). Without an answer the write stops before EOT instead: power-cycle,
# then flash again.
FRAME_REPLY_S = 5.0
FRAME_NAK_RETRIES = 10


def crc16_ccitt(data: bytes, crc: int = 0) -> int:
    """Calculates CRC-16-CCITT / XMODEM (poly 0x1021, init 0x0000)."""
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def parse_intel_hex(hex_path: str) -> bytes:
    """Parses an Intel HEX file into a contiguous byte image from min_addr to max_addr.

    Any gaps between records within [min_addr, max_addr] are filled with 0xFF.
    """
    ext_addr = 0
    data_dict = {}

    with open(hex_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            byte_count = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            record_type = int(line[7:9], 16)
            data_bytes = bytes.fromhex(line[9:9 + byte_count * 2])

            if record_type == 0x00:  # Data record
                full_addr = ext_addr + addr
                for offset, b in enumerate(data_bytes):
                    data_dict[full_addr + offset] = b
            elif record_type == 0x01:  # EOF
                break
            elif record_type == 0x02:  # Extended Segment Address
                ext_addr = int(line[9:13], 16) << 4
            elif record_type == 0x04:  # Extended Linear Address
                ext_addr = int(line[9:13], 16) << 16

    if not data_dict:
        raise ValueError(f"No valid data records found in {hex_path}")

    min_addr = min(data_dict.keys())
    max_addr = max(data_dict.keys())
    total_size = (max_addr - min_addr) + 1

    buf = bytearray(b"\xFF" * total_size)
    for addr, byte_val in data_dict.items():
        buf[addr - min_addr] = byte_val

    return bytes(buf)


def load_firmware(path: str) -> bytes:
    """Loads unpadded firmware image from .hex or .bin."""
    if path.lower().endswith(".hex"):
        return parse_intel_hex(path)

    with open(path, "rb") as f:
        raw = f.read()
    if not raw:
        raise ValueError(f"Firmware file {path} is empty")
    return raw


def build_iap_frame(seq: int, chunk: bytes) -> bytes:
    """Builds a 1030-byte Flashforge IAP frame from a <= 1024-byte chunk.

    Header bytes [2..3] hold the unpadded chunk length (matching IAPCommand's
    end_addr - start_addr), while the 1024-byte payload is padded with 0xFF and
    CRC-16 is computed over all 1024 bytes.
    """
    if not (0 < len(chunk) <= FRAME_DATA_SIZE):
        raise ValueError(f"Invalid chunk length {len(chunk)}")
    valid_len = len(chunk)
    padded = chunk.ljust(FRAME_DATA_SIZE, b"\xFF")
    crc = crc16_ccitt(padded)
    frame = (
        CMD_SOH +
        bytes([seq & 0xFF]) +
        struct.pack("<H", valid_len) +
        padded +
        struct.pack("<H", crc)
    )
    assert len(frame) == FRAME_TOTAL_SIZE
    return frame


class SerialPort:
    """Raw POSIX serial port wrapper using standard termios."""

    def __init__(self, port: str, baudrate: int = 115200, even_parity: bool = True):
        self.port = port
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.configure(baudrate, even_parity=even_parity)

    def configure(self, baudrate: int, even_parity: bool = True):
        baud_map = {
            9600: termios.B9600,
            19200: termios.B19200,
            38400: termios.B38400,
            57600: termios.B57600,
            115200: termios.B115200,
            230400: termios.B230400,
        }
        b = baud_map.get(baudrate, termios.B115200)
        attr = termios.tcgetattr(self.fd)
        attr[0] = 0  # iflag: raw (INPCK clear, matching IAPCommand)
        attr[1] = 0  # oflag: raw
        cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
        if even_parity:
            cflag |= termios.PARENB
        attr[2] = cflag
        attr[3] = 0  # lflag: raw, no echo
        attr[4] = b  # ispeed
        attr[5] = b  # ospeed
        attr[6][termios.VMIN] = 0
        attr[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attr)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def write(self, data: bytes):
        # The port is non-blocking: a short write would send half a frame
        # and desync the bootloader, so wait for room and send the rest.
        view = memoryview(data)
        while view:
            try:
                n = os.write(self.fd, view)
            except BlockingIOError:
                select.select([], [self.fd], [], 1.0)
                continue
            view = view[n:]

    def read_exact(self, count: int, timeout_s: float = 1.0) -> bytes:
        deadline = time.monotonic() + timeout_s
        buf = bytearray()
        while len(buf) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            r, _, _ = select.select([self.fd], [], [], max(0.01, remaining))
            if r:
                try:
                    chunk = os.read(self.fd, count - len(buf))
                except BlockingIOError:
                    continue
                if chunk:
                    buf.extend(chunk)
        return bytes(buf)

    def flush(self):
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def wait_frame_reply(ser, timeout_s: float) -> bytes:
    """The first ACK or NAK within timeout_s; other bytes are skipped.

    Returns the last other byte seen (or b"") when neither came."""
    deadline = time.monotonic() + timeout_s
    other = b""
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return other
        b = ser.read_exact(1, timeout_s=left)
        if b in (CMD_ACK, CMD_NAK):
            return b
        if b:
            other = b


def flash_iap(port_name: str, firmware_path: str, baudrate: int = 115200,
              trigger_f37: bool = False, wait_seconds: int = 20,
              dry_run: bool = False, start_app: bool = True) -> bool:
    """Flashes firmware into MCU via Flashforge IAP protocol."""
    if trigger_f37 and port_name != "/dev/ttyS4":
        print("Error: F37 is only for the IFS on /dev/ttyS4; the eboard has no F37 entry.",
              file=sys.stderr)
        return False
    if dry_run and trigger_f37:
        print("Error: --dry-run on the IFS needs --no-f37: F37 erases the IFS "
              "bootloader flag page (0x0800D000) and requires a full flash write "
              "to boot the application again.", file=sys.stderr)
        return False

    print(f"Loading firmware: {firmware_path}...")
    image = load_firmware(firmware_path)
    total_frames = (len(image) + FRAME_DATA_SIZE - 1) // FRAME_DATA_SIZE

    print(f"Opening serial port {port_name} at {baudrate} baud...")
    ser = SerialPort(port_name, baudrate, even_parity=not trigger_f37)

    try:
        if trigger_f37:
            print("Sending 'F37' bootloader entry command (8N1)...")
            ser.flush()
            ser.write(b"F37\r\n")
            time.sleep(1.0)
            ser.configure(baudrate, even_parity=True)

        print(f"Connecting to bootloader on {port_name} (polling 'C')...", end="", flush=True)
        connected = False
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            ser.flush()
            ser.write(CMD_POLL_CRC)
            print(".", end="", flush=True)
            resp = ser.read_exact(1, timeout_s=1.0)
            if resp == CMD_ACK:
                connected = True
                print(" Connected!")
                break
            elif resp == CMD_HD:
                print("\nUpdate :HD ")
                return False

        if not connected:
            print(f"\nCan not connect to board within {wait_seconds}s.")
            return False

        if dry_run:
            print("Dry-run: bootloader handshake verified. Exiting without writing.")
            return True

        print(f"Writing {len(image)} bytes ({total_frames} frames)...")

        for frame_idx in range(total_frames):
            chunk = image[frame_idx * FRAME_DATA_SIZE : (frame_idx + 1) * FRAME_DATA_SIZE]
            frame = build_iap_frame(frame_idx, chunk)

            success = False
            for attempt in range(FRAME_NAK_RETRIES):
                ser.flush()
                ser.write(frame)
                resp = wait_frame_reply(ser, FRAME_REPLY_S)
                if resp == CMD_ACK:
                    success = True
                    break
                if resp != CMD_NAK:
                    # The frame may have been written: sending it again would
                    # write it twice. Stop before EOT, so the bootloader keeps
                    # waiting for a new write.
                    print(f"\n[Frame {frame_idx}] no ACK or NAK within {FRAME_REPLY_S:g} s "
                          f"(got {resp!r}); stopping without EOT. The bootloader is still "
                          "there but ignores 'C' until it is powered off: switch the "
                          "printer off and on (the IFS: or unplug and replug its cable), "
                          "then flash again.")
                    return False
                print(f"\n[Frame {frame_idx}] NAK received, sending it again...")
                time.sleep(0.05)

            if not success:
                print(f"\nFailed to transmit frame {frame_idx}: {FRAME_NAK_RETRIES} NAKs.")
                return False

            pct = (frame_idx + 1) * 100 // total_frames
            print(f"\rTransmitted frame {frame_idx + 1}/{total_frames} ({pct}%)", end="", flush=True)

        print("\nAll frames transmitted. Sending EOT...")
        for _ in range(3):
            ser.flush()
            ser.write(CMD_EOT)
            resp = ser.read_exact(1, timeout_s=3.0)
            if resp == CMD_ACK:
                break
        else:
            print(f"Warning: EOT response was {resp!r} (expected ACK).")
            return False
        print("STM32Write: success.")

        if not start_app:
            # IFS: the bootloader starts the application itself (as with stock
            # IFSCommand); the caller checks that it then answers.
            print("No start command sent (the board starts its application itself).")
            return True

        # After EOT the bootloader waits for 'A' to start the application
        # (on hardware, without it the eboard stays in the bootloader until a
        # power cycle). Verified on the printer 2026-11-02.
        ser.flush()
        ser.write(CMD_START)
        resp = ser.read_exact(1, timeout_s=3.0)
        if resp == CMD_ACK:
            print("Application started.")
            return True

        print(f"Warning: start response was {resp!r} (expected ACK); power-cycle the board.")
        return False

    finally:
        ser.close()


def main():
    prog = os.path.basename(sys.argv[0])
    default_port = "/dev/ttyS4" if "ifs" in prog else "/dev/ttyS5"
    default_f37 = True if "ifs" in prog else False

    parser = argparse.ArgumentParser(
        description="Flashforge IAP MCU Firmware Flasher (eboard / IFS)"
    )
    parser.add_argument("firmware", help="Path to firmware (.hex or .bin)")
    parser.add_argument("pos_port", nargs="?", default=None,
                        help=f"Serial port (positional, default: {default_port})")
    parser.add_argument("pos_baud", nargs="?", type=int, default=None,
                        help="Baud rate (positional, default: 115200)")
    parser.add_argument("-p", "--port", dest="opt_port", default=None,
                        help=f"Serial port (default: {default_port})")
    parser.add_argument("-b", "--baud", dest="opt_baud", type=int, default=None,
                        help="Baud rate (default: 115200)")
    parser.add_argument("--f37", dest="f37", action="store_true", default=None,
                        help="Send F37 bootloader entry command before sync")
    parser.add_argument("--no-f37", dest="no_f37", action="store_true",
                        help="Do not send F37 bootloader entry command")
    parser.add_argument("-w", "--wait", type=int, default=20,
                        help="Connection timeout in seconds (default: 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Handshake with bootloader and exit without flashing")
    parser.add_argument("--start", dest="start", action="store_true", default=None,
                        help="Send 'A' after EOT to start the application (eboard default)")
    parser.add_argument("--no-start", dest="start", action="store_false",
                        help="Send nothing after EOT (IFS default, as stock IFSCommand)")

    args = parser.parse_args()

    port = args.opt_port or args.pos_port or default_port
    baud = args.opt_baud or args.pos_baud or 115200

    if args.no_f37:
        trigger_f37 = False
    elif args.f37 is not None:
        trigger_f37 = args.f37
    else:
        trigger_f37 = default_f37 or ("/dev/ttyS4" in port)

    is_ifs = "ifs" in prog or "/dev/ttyS4" in port
    start_app = (not is_ifs) if args.start is None else args.start

    success = flash_iap(
        port_name=port,
        firmware_path=args.firmware,
        baudrate=baud,
        trigger_f37=trigger_f37,
        wait_seconds=args.wait,
        dry_run=args.dry_run,
        start_app=start_app
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
