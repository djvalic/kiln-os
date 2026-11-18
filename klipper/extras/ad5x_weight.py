# Support for the Flashforge AD5X bed weighing board (strain gauges)
#
# The board sits on its own host UART (/dev/ttyS7, 9600 baud) and drives the
# probe pin; this module only tares it and reads it. Written from the
# behaviour recorded in docs/bed-weighing-board.md. No vendor code is used.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import os
import termios

BAUDS = {9600: termios.B9600, 19200: termios.B19200, 57600: termios.B57600,
         115200: termios.B115200}

class WeightError(Exception):
    pass

class AD5XWeight:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.serial_port = config.get('serial', '/dev/ttyS7')
        self.baud = config.getint('baud', 9600)
        if self.baud not in BAUDS:
            raise config.error("ad5x_weight: unsupported baud %d" % self.baud)
        # Stock waits up to 1 s for each reply and sends a command up to 5
        # times. A reply is complete when it is longer than 12 bytes and
        # contains "ok".
        self.reply_timeout = config.getfloat('reply_timeout', 1., above=0.)
        self.send_attempts = config.getint('send_attempts', 5, minval=1)
        # Tare (H1) then read (H7) up to tare_attempts times, until the
        # reading is within +/- tare_tolerance (stock: 10 tries, |w| < 31).
        self.tare_attempts = config.getint('tare_attempts', 10, minval=1)
        self.tare_tolerance = config.getint('tare_tolerance', 31, minval=1)
        self.fd = self.fd_handle = None
        self.rx_buf = b""
        self.rx_event = None
        self.mutex = self.reactor.mutex()
        self.last_weight = None
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        self.printer.register_event_handler("klippy:disconnect",
                                            self._close)
        for cmd in ("WEIGHT_TARE", "WEIGHT_READ", "WEIGHT_SEND"):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        desc=getattr(self, "cmd_%s_help" % cmd))
    # Serial link
    def _handle_connect(self):
        try:
            self._open()
        except OSError as e:
            logging.warning("ad5x_weight: not available on %s: %s",
                            self.serial_port, e)
            self._close()
    def _open(self):
        fd = os.open(self.serial_port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            attrs = termios.tcgetattr(fd)
            attrs[0] = attrs[1] = attrs[3] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[4] = attrs[5] = BAUDS[self.baud]
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except termios.error:
            pass
        self.fd = fd
        self.fd_handle = self.reactor.register_fd(fd, self._handle_read)
    def _close(self):
        if self.fd_handle is not None:
            self.reactor.unregister_fd(self.fd_handle)
            self.fd_handle = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
    def _handle_read(self, eventtime):
        try:
            self.rx_buf += os.read(self.fd, 4096)
        except OSError:
            return
        if self.rx_event is not None:
            ev, self.rx_event = self.rx_event, None
            ev.complete(True)
    def _answered(self):
        return len(self.rx_buf) > 12 and b"ok" in self.rx_buf
    def _complete(self):
        # The whole line: the board sends "command H7 ok. 8596371 60 g
        # \r\n" in more than one piece at times, and "ok" alone came
        # before the reading on the printer (issue #69: "bad H7 reply:
        # 'command H7 ok. 8'"). A reply that never ends its line still
        # counts once no more bytes come (_request).
        i = self.rx_buf.find(b"ok")
        return (self._answered()
                and (b"\n" in self.rx_buf[i:] or b"\r" in self.rx_buf[i:]))
    def _request(self, cmd):
        """Send cmd and return the reply (caller holds the mutex)."""
        if self.fd is None:
            raise WeightError("weighing board not connected")
        for attempt in range(self.send_attempts):
            try:
                termios.tcflush(self.fd, termios.TCIFLUSH)
            except termios.error:
                pass
            self.rx_buf = b""
            logging.debug("ad5x_weight: -> %s", cmd)
            try:
                os.write(self.fd, (cmd + "\n").encode("ascii"))
            except OSError as e:
                # A G-code error, not a Klipper shutdown
                raise WeightError("can't write to %s: %s" % (
                    self.serial_port, e))
            # Wait while bytes keep arriving, at most reply_timeout between
            # reads, until the reply is complete.
            while not self._complete():
                n = len(self.rx_buf)
                end = self.reactor.monotonic() + self.reply_timeout
                while len(self.rx_buf) == n:
                    if self.reactor.monotonic() >= end:
                        break
                    self.rx_event = self.reactor.completion()
                    self.rx_event.wait(end)
                    self.rx_event = None
                if len(self.rx_buf) == n:
                    break
            if self._answered():
                reply = self.rx_buf.decode("ascii", "replace").strip()
                logging.debug("ad5x_weight: <- %s", reply)
                return reply
            logging.info("ad5x_weight: no reply to %s (attempt %d)",
                         cmd, attempt + 1)
        raise WeightError("no reply to %s" % (cmd,))
    def _read_weight(self):
        reply = self._request("H7")
        # The reading is the fifth space-separated field, as stock reads it.
        fields = reply.split()
        try:
            self.last_weight = int(fields[4])
        except (IndexError, ValueError):
            raise WeightError("bad H7 reply: %r" % (reply,))
        return self.last_weight
    def _tare(self):
        for attempt in range(self.tare_attempts):
            self._request("H1")
            w = self._read_weight()
            if abs(w) < self.tare_tolerance:
                logging.info("ad5x_weight: tared, reading %d", w)
                return w
            logging.info("ad5x_weight: tare attempt %d, reading %d",
                         attempt + 1, w)
        raise WeightError("Leveling sensor cannot be cleared (reading %s). "
                          "Check the bed is clear and the sensor."
                          % (self.last_weight,))
    def _run(self, func, *args):
        with self.mutex:
            try:
                return func(*args)
            except WeightError as e:
                raise self.gcode.error("ad5x_weight: %s" % (e,))
    def get_status(self, eventtime):
        return {'connected': self.fd is not None, 'weight': self.last_weight}
    # G-code commands
    cmd_WEIGHT_TARE_help = "Zero the bed strain gauges (before probing)"
    def cmd_WEIGHT_TARE(self, gcmd):
        self.printer.lookup_object('toolhead').wait_moves()
        w = self._run(self._tare)
        gcmd.respond_info("Bed weight tared, reading %d" % (w,))
    cmd_WEIGHT_READ_help = "Report the bed strain gauge reading"
    def cmd_WEIGHT_READ(self, gcmd):
        gcmd.respond_info("Bed weight reading %d" % (self._run(
            self._read_weight),))
    cmd_WEIGHT_SEND_help = "Send a raw command to the weighing board"
    def cmd_WEIGHT_SEND(self, gcmd):
        cmd = gcmd.get('CMD').strip()
        if not cmd.startswith("H"):
            raise gcmd.error("WEIGHT_SEND: CMD must start with H")
        gcmd.respond_info(self._run(self._request, cmd))

def load_config(config):
    return AD5XWeight(config)
