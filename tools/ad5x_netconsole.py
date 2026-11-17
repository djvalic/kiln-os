#!/usr/bin/env python3
"""U-Boot's console over the network (netconsole), on any PC with Python 3.

    python3 tools/ad5x_netconsole.py [--printer IP] [--port 6666]

Prints what Kiln's U-Boot sends to UDP port 6666 (from every printer on the
LAN, or only --printer) and sends what you type back to it, a line at a
time. Ctrl-C sends Ctrl-C (the stop key: the U-Boot prompt within the first
2 seconds of a start); Ctrl-D or Ctrl-Break ends this program.

On the printer: /data/ad5x/netconsole switches it on for every start (empty:
the whole LAN; or this PC's IP on its first line):

    touch /data/ad5x/netconsole        # Kiln OS, as root
    setenv ad5x_nc on; saveenv          # or at the U-Boot prompt

The network rescue (ad5x_emmc_image.py --rescue) always sends its console
to the PC that serves it.
"""
import argparse
import select
import signal
import socket
import sys
import threading


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--printer", help="only this printer's IP")
    p.add_argument("--port", type=int, default=6666)
    a = p.parse_args(argv)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.bind(("", a.port))
    except OSError as e:
        print("ad5x_netconsole: UDP port %d: %s" % (a.port, e.strerror),
              file=sys.stderr)
        return 1
    peer = [(a.printer, a.port)] if a.printer else [None]
    print("ad5x_netconsole: listening on UDP %d%s; Ctrl-C sends Ctrl-C, "
          "Ctrl-D ends" % (a.port, " for " + a.printer if a.printer else ""),
          file=sys.stderr)

    def send(b):
        if peer[0]:
            s.sendto(b, peer[0])
        else:
            print("\nad5x_netconsole: no printer heard yet", file=sys.stderr)

    def on_sigint(*_):
        send(b"\x03")
    signal.signal(signal.SIGINT, on_sigint)

    def typing():
        for line in sys.stdin:
            send(line.replace("\r\n", "\n").replace("\n", "\r").encode())
        s.close()

    threading.Thread(target=typing, daemon=True).start()
    while True:
        try:
            r, _, _ = select.select([s], [], [], 0.5)
        except (OSError, ValueError):
            return 0
        if not r:
            continue
        try:
            data, src = s.recvfrom(2048)
        except OSError:
            return 0
        if a.printer and src[0] != a.printer:
            continue
        if not peer[0]:
            peer[0] = (src[0], a.port)
            print("ad5x_netconsole: printer at %s" % src[0], file=sys.stderr)
        sys.stdout.write(data.decode(errors="replace"))
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
