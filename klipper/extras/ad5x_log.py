# Log modes: how much of Klipper's once-a-second Stats line goes to klippy.log
#
# LOG_MODE [MODE=short|extended] [HOURS=n]
#   short (the default): the Stats line once a minute while the printer is
#   active (and the first one after an idle spell); every line of the last
#   two minutes stays in RAM and is written ahead of any shutdown, after an
#   MCU error while connecting, and the latest one at a restart or exit.
#   extended: every Stats line, as upstream Klipper. HOURS: back to short
#   after that many hours (also across restarts). Saved (save_variables
#   ad5x_log_mode, ad5x_log_until). Without MODE: says which mode is on.
#   Root scripts read the mode from printer_data/comms/log-mode
#   ("short" or "extended [until, Unix time]").
# printer.ad5x_log: mode, until (Unix time or None)
#
# Klipper's statistics module keeps collecting: its callbacks run every
# second as before (the heaters' watchdog, the MCU clock calibration, the
# mcu/system_stats status depend on that); only the logging changes.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import collections
import logging
import os
import time

MODES = ("short", "extended")
VAR_MODE = "ad5x_log_mode"
VAR_UNTIL = "ad5x_log_until"
SHORT_EVERY = 60.
MAX_HOURS = 24. * 31
RECHECK = 600.      # the clock may jump (no RTC; NTP sets it after boot)
MODE_FILE = "/home/klipper/printer_data/comms/log-mode"

# Module level: kept across RESTART and FIRMWARE_RESTART (the module stays
# imported), so an MCU error while reconnecting can still show the Stats of
# the session before. Entries: [eventtime, text, written]
RING = collections.deque(maxlen=120)


def dump_ring(reason, since=None):
    """Write the Stats lines of the ring not in the log yet (from eventtime
    since on, if given), oldest first, as one record.

    Lines newer than the last one already in the log are written as
    upstream's "Stats ..." lines, so the log's Stats stay in time order:
    Klipper's scripts/logextract.py reads them ahead of a shutdown and
    assumes that. Older ones are written as "held Stats ...", which it
    leaves alone."""
    last = max([e[0] for e in RING if e[2]] or [-1e99])
    todo = [e for e in RING if not e[2]
            and (since is None or e[0] >= since)]
    if not todo:
        return 0
    for e in todo:
        e[2] = True
    logging.info("ad5x_log: %d Stats lines held back (%s):\n%s", len(todo),
                 reason, "\n".join([
                     "%sStats %.1f: %s" % ("" if e[0] > last else "held ",
                                            e[0], e[1]) for e in todo]))
    return len(todo)


class LogMode:
    def __init__(self, config):
        self.printer = printer = config.get_printer()
        self.reactor = printer.get_reactor()
        self.gcode = printer.lookup_object('gcode')
        self.mode_file = config.get('mode_file', MODE_FILE)
        self.every = config.getfloat('short_interval', SHORT_EVERY, minval=1.)
        self.mode = "short"
        self.until = None
        # Not "self.stats": statistics calls .stats of every printer object
        self.statistics = None
        self.last_written = -1e9
        self.was_active = False
        # Ring lines from before this start (a RESTART keeps the module)
        # don't go into this session's shutdown dump: its MCU sequence
        # numbers start again
        self.session_start = self.reactor.monotonic()
        self.expire_timer = self.reactor.register_timer(self._expire)
        printer.register_event_handler("klippy:connect", self._handle_connect)
        printer.register_event_handler("klippy:notify_mcu_error",
                                       self._handle_mcu_error)
        printer.register_event_handler("klippy:disconnect",
                                       self._handle_disconnect)
        # Ahead of "Transition to shutdown state": Klipper's
        # scripts/logextract.py reads the Stats lines before that line
        self._invoke_shutdown = printer.invoke_shutdown
        printer.invoke_shutdown = self._shutdown_first
        self.gcode.register_command('LOG_MODE', self.cmd_LOG_MODE,
                                    desc=self.cmd_LOG_MODE_help)

    # Taking over the Stats timer
    def _handle_connect(self):
        self._load_mode()
        stats = self.printer.lookup_object('statistics', None)
        if (stats is None or not hasattr(stats, 'stats_timer')
                or not hasattr(stats, 'stats_cb')):
            logging.warning("ad5x_log: Klipper's statistics module changed;"
                            " Stats are logged as upstream does")
            return
        # statistics' klippy:ready handler fills stats_cb and starts
        # stats_timer (not in batch mode): then it starts this one. The new
        # timer first, so the callbacks never go without one.
        old = stats.stats_timer
        timer = self.reactor.register_timer(self._generate_stats,
                                            old.waketime)
        stats.stats_timer = timer
        self.reactor.unregister_timer(old)
        self.statistics = stats

    def _generate_stats(self, eventtime):
        # As statistics.PrinterStats.generate_stats; the ring and the
        # once-a-minute rule are the only change
        with self.reactor.assert_no_pause():
            stats = [cb(eventtime) for cb in self.statistics.stats_cb]
        active = max([s[0] for s in stats])
        text = ' '.join([s[1] for s in stats if s[1]])
        entry = [eventtime, text, False]
        RING.append(entry)
        if active and (self.mode == "extended" or not self.was_active
                       or eventtime >= self.last_written + self.every):
            entry[2] = True
            self.last_written = eventtime
            logging.info("Stats %.1f: %s", eventtime, text)
        self.was_active = active
        return eventtime + 1.

    # Where the held back lines go to the log
    def _shutdown_first(self, *args, **kwargs):
        if not self.printer.is_shutdown():
            try:
                dump_ring("shutdown", since=self.session_start)
            except Exception:
                logging.exception("ad5x_log: Stats dump")
        return self._invoke_shutdown(*args, **kwargs)

    def _handle_mcu_error(self, msg, details):
        dump_ring(msg)

    def _handle_disconnect(self):
        # A restart or exit: the latest line only (a shutdown wrote the
        # ring already)
        if RING and not RING[-1][2]:
            e = RING[-1]
            e[2] = True
            logging.info("Stats %.1f: %s", e[0], e[1])

    # The mode
    def _load_mode(self):
        sv = self.printer.lookup_object('save_variables', None)
        v = sv.allVariables if sv is not None else {}
        mode, until = v.get(VAR_MODE), v.get(VAR_UNTIL)
        if mode not in MODES:
            mode = "short"
        if (mode != "extended" or isinstance(until, bool)
                or not isinstance(until, (int, float))):
            until = None
        elif not time.time() < until <= time.time() + MAX_HOURS * 3600.:
            # Over, or not a time LOG_MODE could have saved (NaN, 1e300)
            mode, until = "short", None
        self._set(mode, until)

    def _set(self, mode, until):
        self.mode, self.until = mode, until
        self._write_mode_file()
        waketime = self.reactor.NEVER
        if until is not None:
            waketime = self.reactor.monotonic() + max(
                0., min(until - time.time(), RECHECK))
        self.reactor.update_timer(self.expire_timer, waketime)

    def _expire(self, eventtime):
        if self.until is None:
            return self.reactor.NEVER
        left = self.until - time.time()
        if left > 0.:
            return eventtime + min(left, RECHECK)
        # Not saved: the saved until is past, the next start reads short
        logging.info("ad5x_log: extended logging time is over; short again")
        self._set("short", None)
        return self.reactor.NEVER

    def _write_mode_file(self):
        text = self.mode
        if self.until is not None:
            text += " %d" % (self.until,)
        text += "\n"
        path = self.mode_file
        if not os.path.isdir(os.path.dirname(path)):
            return
        try:
            with open(path) as f:
                if f.read() == text:
                    return
        except Exception:
            # Missing, or not text: written again below
            pass
        try:
            with open(path + ".tmp", "w") as f:
                f.write(text)
            os.rename(path + ".tmp", path)
        except OSError:
            logging.warning("ad5x_log: unable to write %s", path)

    def _save(self, name, value):
        if self.printer.lookup_object('save_variables', None) is not None:
            self.gcode.run_script_from_command(
                "SAVE_VARIABLE VARIABLE=%s VALUE=\"%r\"" % (name, value))

    def _describe(self):
        if self.until is None:
            return "Log mode: %s" % (self.mode,)
        return "Log mode: %s until %s" % (
            self.mode, time.strftime("%Y-%m-%d %H:%M",
                                     time.localtime(self.until)))

    cmd_LOG_MODE_help = "How much klippy.log keeps: MODE=short|extended"

    def cmd_LOG_MODE(self, gcmd):
        mode = gcmd.get('MODE', None)
        if mode is None:
            gcmd.respond_info(self._describe())
            return
        mode = mode.lower()
        if mode not in MODES:
            raise gcmd.error("LOG_MODE: MODE is short or extended")
        hours = gcmd.get_float('HOURS', 0., minval=0., maxval=MAX_HOURS)
        until = None
        if mode == "extended" and hours:
            until = round(time.time() + hours * 3600.)
        # Saved first: from a G-code command, which may wait for the write
        self._save(VAR_MODE, mode)
        self._save(VAR_UNTIL, until)
        self._set(mode, until)
        if mode == "extended":
            self.last_written = -1e9
        gcmd.respond_info(self._describe())

    def get_status(self, eventtime):
        return {'mode': self.mode, 'until': self.until}


def load_config(config):
    return LogMode(config)
