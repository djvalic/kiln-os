#!/usr/bin/env python3
"""Print the Klipper firmware version a board runs (its identify data).

usage: mcu_version.py [--port /dev/ttyS2] [--baud 230400] [--timeout 3]

Asks the board for its data dictionary with Klipper's "identify" command,
the way klippy does when it connects, and prints the dictionary's
"version" (e.g. v0.13.0-803-g4cd711119; Flashforge's firmware reports
"?-20241125_172251-ubuntu"). Exit codes: 0 printed, 1 no answer (the board
is in its bootloader, off, or speaks another protocol), 3 port error.
Installed as /usr/bin/ad5x-mcu-version; ad5x-mcu uses it at boot. Nothing
is written to the board. Written from Klipper's protocol documentation
(docs/Protocol.md in Klipper); needs no Klipper code.
"""
import argparse
import json
import os
import select
import sys
import termios
import time
import tty
import zlib

BAUDS = {115200: termios.B115200, 230400: termios.B230400,
         250000: getattr(termios, "B250000", termios.B230400)}
SYNC = 0x7e
MSG_ID_IDENTIFY_RESPONSE = 0     # fixed ids in every Klipper firmware
MSG_ID_IDENTIFY = 1
CHUNK = 40
RESEND = 0.02                    # seconds between identify requests


def crc16_ccitt(buf):
    crc = 0xffff
    for data in buf:
        data ^= crc & 0xff
        data ^= (data & 0x0f) << 4
        crc = ((data << 8) | (crc >> 8)) ^ (data >> 4) ^ (data << 3)
    return bytes([(crc >> 8) & 0xff, crc & 0xff])


def encode_int(v):
    out = bytearray()
    if v >= 0xc000000 or v < -0x4000000:
        out.append((v >> 28) & 0x7f | 0x80)
    if v >= 0x180000 or v < -0x80000:
        out.append((v >> 21) & 0x7f | 0x80)
    if v >= 0x3000 or v < -0x1000:
        out.append((v >> 14) & 0x7f | 0x80)
    if v >= 0x60 or v < -0x20:
        out.append((v >> 7) & 0x7f | 0x80)
    out.append(v & 0x7f)
    return bytes(out)


def decode_int(s, pos):
    c = s[pos]
    pos += 1
    v = c & 0x7f
    if (c & 0x60) == 0x60:
        v |= -0x20
    while c & 0x80:
        c = s[pos]
        pos += 1
        v = (v << 7) | (c & 0x7f)
    return v, pos


def block(seq, payload):
    head = bytes([len(payload) + 5, 0x10 | (seq & 0x0f)]) + payload
    return head + crc16_ccitt(head) + bytes([SYNC])


def open_port(port, baud):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    attrs[4] = attrs[5] = BAUDS[baud]
    attrs[2] |= termios.CLOCAL | termios.CREAD
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


class Link:
    def __init__(self, fd):
        self.fd = fd
        self.buf = bytearray()

    def blocks(self, until):
        """Yield the valid message blocks received before time UNTIL."""
        while True:
            # Split off complete blocks
            while self.buf:
                n = self.buf[0]
                if n < 5 or n > 64:
                    del self.buf[0]         # resync on the next byte
                    continue
                if len(self.buf) < n:
                    break
                blk = bytes(self.buf[:n])
                if blk[-1] == SYNC and blk[1] & 0xf0 == 0x10 and \
                        crc16_ccitt(blk[:-3]) == blk[-3:-1]:
                    del self.buf[:n]
                    yield blk
                else:
                    del self.buf[0]
            left = until - time.monotonic()
            if left <= 0:
                return
            r, _, _ = select.select([self.fd], [], [], left)
            if r:
                try:
                    self.buf += os.read(self.fd, 256)
                except BlockingIOError:
                    pass


def identify(fd, timeout):
    link = Link(fd)
    os.write(fd, bytes([SYNC]) * 4)     # end any half-sent block on the board
    seq = 0
    data = bytearray()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        os.write(fd, block(seq, encode_int(MSG_ID_IDENTIFY)
                           + encode_int(len(data)) + encode_int(CHUNK)))
        got = False
        # Ask again soon: a half-duplex (RS-485) board sends only when it
        # gets a block, and a configured one fills its transmit buffer with
        # reports between two asks; at 0.3 s the reply never had room
        # (the AD5X IFS with Happy Hare's sensors)
        for blk in link.blocks(min(end, time.monotonic() + RESEND)):
            payload = blk[2:-3]
            if not payload:
                # An ack or nak: the board tells us the sequence it expects
                seq = blk[1] & 0x0f
                continue
            pos = 0
            msgid, pos = decode_int(payload, pos)
            if msgid != MSG_ID_IDENTIFY_RESPONSE:
                continue
            offset, pos = decode_int(payload, pos)
            n = payload[pos]
            chunk = payload[pos + 1:pos + 1 + n]
            seq = blk[1] & 0x0f
            if offset != len(data):
                continue
            data += chunk
            got = True
            if n < CHUNK:
                return json.loads(zlib.decompress(bytes(data)))
            break
        if got:
            end = time.monotonic() + timeout    # the board answers: keep going
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", default="/dev/ttyS2")
    ap.add_argument("--baud", type=int, default=230400, choices=sorted(BAUDS))
    ap.add_argument("--timeout", type=float, default=3.0)
    args = ap.parse_args()
    try:
        fd = open_port(args.port, args.baud)
    except OSError as e:
        print("mcu_version: %s: %s" % (args.port, e), file=sys.stderr)
        return 3
    try:
        d = identify(fd, args.timeout)
    except (ValueError, zlib.error, IndexError) as e:
        print("mcu_version: bad identify data: %s" % e, file=sys.stderr)
        d = None
    finally:
        os.close(fd)
    if not d:
        print("mcu_version: no answer on %s" % args.port, file=sys.stderr)
        return 1
    print(d.get("version", "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
