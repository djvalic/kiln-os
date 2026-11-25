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
        # Background reading (plugin API 1.10, docs/bed-weighing-board.md):
        # WEIGHT_MONITOR START reads the raw count (the fourth field) a few
        # times a second and reports the force in grams above a slow
        # baseline, which follows drift (bed heat, the print's own weight)
        # but not a push. One attempt per reading with a short timeout; a
        # reading is skipped while a tare or another command has the board.
        self.counts_per_gram = config.getfloat('counts_per_gram', 56.,
                                               above=0.)
        self.monitor_rate = config.getfloat('monitor_rate', 5., minval=.5,
                                            maxval=10.)
        self.monitor_timeout = config.getfloat('monitor_timeout', .3,
                                               above=0.)
        self.baseline_tc = config.getfloat('baseline_tc', 30., above=0.)
        self.baseline_band = config.getfloat('baseline_band', 100., above=0.)
        self.mon_timer = None
        self.mon_rate = self.monitor_rate
        self.mon_raw = self.mon_baseline = self.mon_force = None
        self.mon_peak = 0.
        self.mon_errors = self.mon_samples = 0
        self.mon_last_time = None
        self.fd = self.fd_handle = None
        self.rx_buf = b""
        self.rx_event = None
        self.mutex = self.reactor.mutex()
        self.last_weight = None
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        self.printer.register_event_handler("klippy:disconnect",
                                            self._close)
        self.printer.register_event_handler("klippy:shutdown",
                                            self.monitor_stop)
        for cmd in ("WEIGHT_TARE", "WEIGHT_READ", "WEIGHT_SEND",
                    "WEIGHT_MONITOR"):
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
        self.monitor_stop()
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
    def _request(self, cmd, attempts=None, timeout=None):
        """Send cmd and return the reply (caller holds the mutex)."""
        if self.fd is None:
            raise WeightError("weighing board not connected")
        if attempts is None:
            attempts = self.send_attempts
        if timeout is None:
            timeout = self.reply_timeout
        for attempt in range(attempts):
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
                end = self.reactor.monotonic() + timeout
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
    # Background reading
    def monitor_start(self, rate=None):
        """Start (or re-rate) the background reading; for plugins: public
        since API 1.10, with monitor_stop() and the event
        "ad5x_weight:sample" (eventtime, raw, force)."""
        self.mon_rate = rate or self.monitor_rate
        if self.mon_timer is None:
            self.mon_raw = self.mon_baseline = self.mon_force = None
            self.mon_last_time = None
            self.mon_peak = 0.
            self.mon_timer = self.reactor.register_timer(
                self._monitor_event, self.reactor.NOW)
    def monitor_stop(self, *args):
        if self.mon_timer is not None:
            self.reactor.unregister_timer(self.mon_timer)
            self.mon_timer = None
    def monitor_reset_peak(self):
        self.mon_peak = 0.
    def monitor_rebase(self):
        # Start the baseline again from the next reading (after the bed
        # was touched, a pause, a tool change)
        self.mon_baseline = None
        self.mon_last_time = None
    def _monitor_read(self):
        reply = self._request("H7", attempts=1, timeout=self.monitor_timeout)
        fields = reply.split()
        try:
            i = fields.index("ok.")
            return int(fields[i + 1]), int(fields[i + 2])
        except (ValueError, IndexError):
            raise WeightError("bad H7 reply: %r" % (reply,))
    def _monitor_event(self, eventtime):
        start = self.reactor.monotonic()
        if self.fd is not None and not self.mutex.test():
            try:
                with self.mutex:
                    raw, grams = self._monitor_read()
            except WeightError as e:
                self.mon_errors += 1
                logging.debug("ad5x_weight: monitor: %s", e)
            else:
                if self.mon_timer is None:
                    return self.reactor.NEVER   # stopped while reading
                now = self.reactor.monotonic()
                self._monitor_sample(now, raw, grams)
        if self.mon_timer is None:
            return self.reactor.NEVER
        return max(start + 1. / self.mon_rate,
                   self.reactor.monotonic() + .02)
    def _monitor_sample(self, now, raw, grams):
        self.mon_samples += 1
        self.last_weight = grams
        if self.mon_baseline is None:
            self.mon_baseline = float(raw)
        force = (raw - self.mon_baseline) / self.counts_per_gram
        if abs(force) < self.baseline_band and self.mon_last_time is not None:
            # Follow slow drift only: a push past the band leaves the
            # baseline where it was
            a = min(1., (now - self.mon_last_time) / self.baseline_tc)
            self.mon_baseline += a * (raw - self.mon_baseline)
        self.mon_last_time = now
        self.mon_raw, self.mon_force = raw, force
        self.mon_peak = max(self.mon_peak, abs(force))
        self.printer.send_event("ad5x_weight:sample", now, raw, force)
    def get_status(self, eventtime):
        rnd = lambda v: None if v is None else round(v, 1)
        return {'connected': self.fd is not None, 'weight': self.last_weight,
                'monitor': self.mon_timer is not None,
                'rate': self.mon_rate if self.mon_timer is not None else 0.,
                'raw': self.mon_raw, 'baseline': rnd(self.mon_baseline),
                'force': rnd(self.mon_force), 'peak': rnd(self.mon_peak),
                'samples': self.mon_samples, 'errors': self.mon_errors,
                'counts_per_gram': self.counts_per_gram}
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
    cmd_WEIGHT_MONITOR_help = ("Background bed force reading: START=1 [RATE=hz]"
                               ", START=0, RESET_PEAK=1, REBASE=1; no "
                               "option: report")
    def cmd_WEIGHT_MONITOR(self, gcmd):
        start = gcmd.get_int('START', None)
        if start:
            self.monitor_start(gcmd.get_float('RATE', self.monitor_rate,
                                              minval=.5, maxval=10.))
        elif start is not None:
            self.monitor_stop()
        if gcmd.get_int('RESET_PEAK', 0):
            self.monitor_reset_peak()
        if gcmd.get_int('REBASE', 0):
            self.monitor_rebase()
        st = self.get_status(self.reactor.monotonic())
        gcmd.respond_info(
            "Bed force monitor %s: force %s g, peak %s g, %d readings, "
            "%d errors" % ("on (%.1f/s)" % st['rate'] if st['monitor']
                           else "off", st['force'], st['peak'],
                           st['samples'], st['errors']))
    cmd_WEIGHT_SEND_help = "Send a raw command to the weighing board"
    def cmd_WEIGHT_SEND(self, gcmd):
        cmd = gcmd.get('CMD').strip()
        if not cmd.startswith("H"):
            raise gcmd.error("WEIGHT_SEND: CMD must start with H")
        gcmd.respond_info(self._run(self._request, cmd))

def load_config(config):
    return AD5XWeight(config)
