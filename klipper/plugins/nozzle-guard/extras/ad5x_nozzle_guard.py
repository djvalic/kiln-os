# Nozzle-hit guard: pause the print when the bed feels a push
#
# Watches the bed weighing board through ad5x_weight's background reading
# (plugin API 1.10): when the force above the slowly drifting baseline is
# over the limit for several readings in a row while a print runs, the
# print pauses (as a filament runout does) and the reason is shown. Armed
# by PRINT_START once its homing, Z check, mesh and purge are done
# (NOZZLE_GUARD ARM=1); not watching during homing or probing, an IFS
# colour change, or a pause. Idea from zMod's NOZZLE_CONTROL; written from
# its behaviour, no zMod code.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import collections
import logging

SENSITIVITY = {'low': 600., 'medium': 300., 'high': 150.}
VAR_ENABLED = "nozzle_guard_enabled"
VAR_THRESHOLD = "nozzle_guard_threshold"


class NozzleGuard:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.default_threshold = config.getfloat('threshold', 300., above=20.)
        self.samples = config.getint('samples', 3, minval=1, maxval=20)
        self.rate = config.getfloat('rate', 5., minval=1., maxval=10.)
        # Readings ignored after homing, an IFS change or a resume while the
        # baseline settles again
        self.settle_time = config.getfloat('settle_time', 2., minval=0.)
        self.default_enabled = config.getboolean('enabled', True)
        self.weight = self.pause_resume = self.print_stats = None
        self.ifs = self.save_vars = None
        self.enabled = self.default_enabled
        self.threshold = self.default_threshold
        self.armed = False
        self.homing = 0
        self.suspended = None
        self.settle_until = 0.
        self.count = 0
        self.print_peak = 0.
        self.trips = 0
        self.last_trip = None
        self.history = collections.deque(maxlen=30)
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        self.printer.register_event_handler("ad5x_weight:sample",
                                            self._handle_sample)
        for ev in ("homing:homing_move_begin", "homing:home_rails_begin"):
            self.printer.register_event_handler(ev, self._homing_begin)
        for ev in ("homing:homing_move_end", "homing:home_rails_end"):
            self.printer.register_event_handler(ev, self._homing_end)
        self.gcode.register_command("NOZZLE_GUARD", self.cmd_NOZZLE_GUARD,
                                    desc=self.cmd_NOZZLE_GUARD_help)
    def _handle_connect(self):
        self.weight = self.printer.lookup_object('ad5x_weight', None)
        if self.weight is None or not hasattr(self.weight, 'monitor_start'):
            raise self.printer.config_error(
                "nozzle-guard needs [ad5x_weight] with background reading "
                "(Kiln OS plugin API 1.10)")
        self.pause_resume = self.printer.lookup_object('pause_resume', None)
        self.print_stats = self.printer.lookup_object('print_stats', None)
        self.ifs = self.printer.lookup_object('ifs', None)
        self.save_vars = self.printer.lookup_object('save_variables', None)
        if self.save_vars is not None:
            v = self.save_vars.allVariables
            self.enabled = bool(v.get(VAR_ENABLED, self.default_enabled))
            try:
                self.threshold = max(20., float(
                    v.get(VAR_THRESHOLD, self.default_threshold)))
            except (TypeError, ValueError):
                self.threshold = self.default_threshold
    # Homing and probing press on the bed on purpose
    def _homing_begin(self, *args):
        self.homing += 1
    def _homing_end(self, *args):
        self.homing = max(0, self.homing - 1)
        self.settle_until = self.reactor.monotonic() + self.settle_time
    # State
    def _print_state(self):
        if self.print_stats is None:
            return "standby"
        return self.print_stats.get_status(
            self.reactor.monotonic())['state']
    def _suspend_reason(self, now):
        if self.homing:
            return "homing"
        if self.pause_resume is not None and self.pause_resume.is_paused:
            return "paused"
        if self.ifs is not None and getattr(self.ifs, 'busy', False):
            return "colour change"
        if now < self.settle_until:
            return "settling"
        return None
    def _arm(self):
        self.armed = True
        self.count = 0
        self.print_peak = 0.
        self.suspended = None
        self.settle_until = self.reactor.monotonic() + self.settle_time
        self.weight.monitor_start(self.rate)
        self.weight.monitor_rebase()
        logging.info("nozzle-guard: armed, limit %.0f g, %d readings",
                     self.threshold, self.samples)
    def _disarm(self, why):
        if self.armed:
            logging.info("nozzle-guard: off (%s), largest push this print "
                         "%.0f g", why, self.print_peak)
        self.armed = False
        self.count = 0
        self.suspended = None
        if self.weight is not None:
            self.weight.monitor_stop()
    # Readings
    def _handle_sample(self, eventtime, raw, force):
        if not self.armed:
            return
        state = self._print_state()
        if state not in ("printing", "paused"):
            self._disarm("print " + state)
            return
        now = self.reactor.monotonic()
        reason = self._suspend_reason(now)
        if reason is not None:
            if reason != "settling" and self.suspended != reason:
                # The bed may have been touched or the plate changed: start
                # the baseline again once watching resumes
                self.weight.monitor_rebase()
            if reason != "settling":
                self.settle_until = now + self.settle_time
            self.suspended = reason
            self.count = 0
            return
        self.suspended = None
        self.history.append((round(now, 2), raw, round(force, 1)))
        self.print_peak = max(self.print_peak, abs(force))
        if abs(force) < self.threshold:
            self.count = 0
            return
        self.count += 1
        if self.count >= self.samples and self.enabled:
            self._trip(now, force)
    def _trip(self, now, force):
        self.count = 0
        self.trips += 1
        z = None
        try:
            z = self.printer.lookup_object('toolhead').get_position()[2]
        except Exception:
            pass
        self.last_trip = {'time': now, 'force': round(force, 1),
                          'threshold': self.threshold,
                          'z': None if z is None else round(z, 2)}
        logging.warning("nozzle-guard: push of %.0f g (limit %.0f g) at Z=%s;"
                        " last readings (time, raw, g): %s", force,
                        self.threshold, self.last_trip['z'],
                        list(self.history))
        msg = ("Nozzle hit detected: the bed felt %.0f g (limit %.0f g)%s. "
               "Print paused: check the print and the nozzle, then resume "
               "or cancel." % (abs(force), self.threshold,
                               "" if z is None else " at Z %.2f" % z))
        self.reactor.register_callback(lambda e: self._pause(msg))
    def _pause(self, msg):
        self.gcode.respond_raw("!! " + msg)
        if self.pause_resume is not None and not self.pause_resume.is_paused:
            self.pause_resume.send_pause_command()
            try:
                self.gcode.run_script("PAUSE")
            except Exception:
                logging.exception("nozzle-guard: PAUSE failed")
    def get_status(self, eventtime):
        return {'enabled': self.enabled, 'armed': self.armed,
                'watching': self.armed and self.suspended is None,
                'suspended': self.suspended or "",
                'threshold': self.threshold, 'samples': self.samples,
                'sensitivity': next((k for k, v in SENSITIVITY.items()
                                     if v == self.threshold), "custom"),
                'print_peak': round(self.print_peak, 1),
                'trips': self.trips, 'last_trip': self.last_trip}
    # G-code
    def _save(self, name, value):
        if self.save_vars is None:
            return
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=%r" % (name, value))
    cmd_NOZZLE_GUARD_help = ("Nozzle-hit guard: ENABLE=0|1, SENSITIVITY="
                             "low|medium|high or THRESHOLD=g (saved), "
                             "ARM=1|0 (PRINT_START), no option: report")
    def cmd_NOZZLE_GUARD(self, gcmd):
        enable = gcmd.get_int('ENABLE', None, minval=0, maxval=1)
        if enable is not None:
            self.enabled = bool(enable)
            self._save(VAR_ENABLED, int(enable))
        sens = gcmd.get('SENSITIVITY', None)
        thr = gcmd.get_float('THRESHOLD', None, minval=20.)
        if sens is not None:
            if sens.lower() not in SENSITIVITY:
                raise gcmd.error("NOZZLE_GUARD: SENSITIVITY is low, medium "
                                 "or high")
            thr = SENSITIVITY[sens.lower()]
        if thr is not None:
            self.threshold = thr
            self._save(VAR_THRESHOLD, thr)
        arm = gcmd.get_int('ARM', None, minval=0, maxval=1)
        if arm:
            if self.enabled and self._print_state() == "printing":
                self._arm()
            elif not self.enabled:
                gcmd.respond_info("Nozzle-hit guard is off "
                                  "(NOZZLE_GUARD ENABLE=1)")
                return
        elif arm is not None:
            self._disarm("ARM=0")
        st = self.get_status(self.reactor.monotonic())
        gcmd.respond_info(
            "Nozzle-hit guard %s, limit %.0f g (%s), %d readings in a row; "
            "%s; largest push this print %.0f g, %d hits" % (
                "on" if st['enabled'] else "off", st['threshold'],
                st['sensitivity'], st['samples'],
                ("watching" if st['watching'] else "armed, not watching: "
                 + st['suspended']) if st['armed'] else "not armed",
                st['print_peak'], st['trips']))


def load_config(config):
    return NozzleGuard(config)
