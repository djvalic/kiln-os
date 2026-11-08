#!/usr/bin/env python3
"""Print the version Flashforge's firmware on the IFS reports.

usage: ifs_f19.py [--port /dev/ttyS4] [--timeout 1]

Sends the F19 query (115200 baud) and prints the "version:" value of the
reply ("F19 ok. four color. version: 3.0.7" -> 3.0.7). Exit codes: 0
printed, 1 nothing answered (or no version in the reply), 3 port error.
Installed as /usr/bin/ad5x-ifs-f19; ad5x-mcu uses it. Klipper firmware on
the IFS does not answer it.
"""
import argparse
import os
import select
import sys
import termios
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyS4")
    ap.add_argument("--timeout", type=float, default=1.0)
    a = ap.parse_args()
    try:
        fd = os.open(a.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        t = termios.tcgetattr(fd)
        t[0] = t[1] = t[3] = 0
        t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        t[4] = t[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, t)
        termios.tcflush(fd, termios.TCIOFLUSH)
        # A newline first ends whatever came before (a Klipper identify
        # from "ad5x-mcu-version" has none): Flashforge's firmware ignores
        # the F19 glued to it otherwise
        os.write(fd, b"\r\nF19\r\n")
    except OSError as e:
        print("ad5x-ifs-f19: %s: %s" % (a.port, e), file=sys.stderr)
        return 3
    r = b""
    end = time.time() + a.timeout
    while time.time() < end and b"version:" not in r:
        if select.select([fd], [], [], 0.1)[0]:
            try:
                r += os.read(fd, 256)
            except OSError:
                break
    time.sleep(0.1)     # the rest of the line
    try:
        r += os.read(fd, 256)
    except OSError:
        pass
    os.close(fd)
    s = r.decode("ascii", "replace")
    if "version:" not in s:
        return 1
    v = s.split("version:")[-1].strip(" .\r\n\t")
    if not v:
        return 1
    print(v)
    return 0


sys.exit(main())
