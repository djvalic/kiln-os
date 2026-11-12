# Bed heat soak: how long the bed needs after reaching its temperature
# before Z is measured, from a calibration with the load-cell probe
#
# The plate's surface keeps warming (and growing) for minutes after the
# bed sensor reads the target, so a Z check made at once is a little off.
#
# BED_SOAK_CALIBRATE BED=80 [POINTS=5|1] [NOZZLE=140] [NOZZLE_SOAK=300]
#     [INTERVAL=60] [STABLE=0.02] [WINDOW=240] [MAX=1500] [FORCE=1]
#   From a cold bed: home, nozzle to NOZZLE, held there NOZZLE_SOAK seconds
#   before the bed heats (the hotend keeps growing for minutes after its
#   sensor reads the target; without the wait that shows up as bed
#   movement: the 60 C and 80 C runs of 2026-10-20 disagreed 5x), bed to
#   BED, then probe every INTERVAL seconds, at the
#   centre and (POINTS=5) 30 mm in from each corner: the heater warms the
#   middle first, so the centre domes and the corners lag. The load cells
#   scatter about 0.03 mm between touches (measured, 60 C run 2026-10-20),
#   so each point's readings are averaged over 3 rounds before judging.
#   Ends when every point's average has stayed within STABLE mm for WINDOW
#   seconds (or after MAX). Saves, per bed temperature (save variable
#   ad5x_bed_soak): settle (the centre's time from the bed reaching BED
#   until its average stayed within STABLE of its final level: PRINT_START
#   checks Z there), settle_corners (the slowest corner's), drift (the
#   centre's total change), warp (how much the corners moved relative to
#   the centre: the shape change), from (the starting temperature), date.
#   Heaters off at the end. On the AD5X at 60 C: the centre moved 0.16 mm
#   and was settled after 5 min, one corner crept for about 13.
# BED_SOAK_START BED= FROM= [SECONDS=] [PER_DEGREE=3] [MAX=300] [MODE=]
#   PRINT_START, when the bed has reached BED (FROM: its temperature when
#   the print started). The soak: SECONDS if given; none when FROM was
#   within 5 C of BED; else the calibrated settle time of the nearest
#   calibrated temperature, scaled by how far the bed rose: a hotter target
#   at least that time (more for a bigger rise, up to twice), a cooler or
#   equal one at most that time (less for a smaller rise); else
#   PER_DEGREE seconds per degree risen; at most MAX. MODE=probe:
#   instead of a time, probe until two readings 60 s apart agree within
#   0.005 mm (POINTS=1: the centre, 5: also the corners), at most that time.
#   Two readings can't tell how much is still to come: on a bed settling
#   like a measured one this stops with about 0.01 mm left, and the load
#   cells' own scatter limits it; the calibration is the better guide.
# API ad5x_soak/abort (Moonraker: JSON-RPC printer.ad5x_soak.abort, HTTP
#   POST /printer/ad5x_soak/abort; HelixScreen's Stop): ends a running
#   calibration within a second, heaters off, nothing saved. A G-code
#   command couldn't: the calibration holds the G-code queue.
# BED_SOAK_ENABLE [ENABLE=0|1]
#   The soak on or off for every print (saved: ad5x_bed_soak_on; a
#   calibration stays saved either way); without ENABLE says which it is.
#   PRINT_START SOAK= in a file still sets that print's soak.
# BED_SOAK_WAIT
#   Waits for what is left of the soak (the purge and brushing since
#   BED_SOAK_START count), with a countdown on the screen.
# _PRINT_START_HEAT HEATER=heater_bed|extruder [MINIMUM=]
#   PRINT_START's heating waits: TEMPERATURE_WAIT MINIMUM= (with MINIMUM)
#   or M109's wait for the heater to settle (without), set the target first.
# Cancel during the print start: a cancel (Moonraker printer.print.cancel,
#   Klipper endpoint pause_resume/cancel: Fluidd, Mainsail, HelixScreen)
#   queues CANCEL_PRINT behind the running G-code command, which during
#   the print start is the whole PRINT_START (several minutes). The
#   endpoint is wrapped so the cancel is noted when it arrives
#   (printer.ad5x_soak.cancel, until CANCEL_PRINT has run); the soak and
#   heating waits above end within a second, _PRINT_START_CHECK (ad5x.cfg)
#   at the step boundaries, with an error that ends PRINT_START. The
#   waiting CANCEL_PRINT then runs as on any cancel (print_stats
#   "cancelled", heaters off, park). A probe move, the mesh or an IFS swap
#   isn't cut: the start ends after it.
# printer.ad5x_soak: calibration ({"80": {settle, drift, from, date}}),
#   running, soak (seconds of the current print's soak), last (readings of
#   the last calibration: [[seconds, z centre, z corners...], ...]).
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import time

VARIABLE = "ad5x_bed_soak"
ON_VARIABLE = "ad5x_bed_soak_on"
CENTRE = (107.5, 107.5)
# Centre first, then 30 mm in from each corner (bed 0-215 x 0-215)
POINTS5 = (CENTRE, (30., 30.), (185., 30.), (185., 185.), (30., 185.))
HOT = 5.        # C: a bed this close to the target at the start needs none


def smooth(readings):
    """Each reading averaged with its neighbours (3 rounds): the load
    cells scatter more than the settling we look for."""
    out = []
    for i, (t, z) in enumerate(readings):
        near = [r[1] for r in readings[max(0, i - 1):i + 2]]
        out.append((t, sum(near) / len(near)))
    return out


def settle_time(readings, stable):
    """Seconds from the first reading until the smoothed Z stayed within
    stable of its final level (the mean of the last 4 readings)."""
    if not readings:
        return 0.
    sm = smooth(readings)
    tail = [z for t, z in readings[-4:]]
    final = sum(tail) / len(tail)
    settle = sm[-1][0]
    for t, z in reversed(sm):
        if abs(z - final) > stable:
            break
        settle = t
    return settle


def is_stable(readings, stable, window):
    """Smoothed Z within stable over the last window seconds (and that
    long run, and at least 4 readings in it)."""
    if not readings or readings[-1][0] - readings[0][0] < window:
        return False
    end = readings[-1][0]
    zs = [z for t, z in smooth(readings) if t >= end - window]
    return len(zs) >= 4 and max(zs) - min(zs) <= stable


def soak_seconds(bed, start, calibration, per_degree, max_s):
    """Soak for a print heating the bed from start to bed (see header)."""
    rise = bed - start
    if rise <= HOT:
        return 0., "bed already hot"
    near = None
    for key, cal in (calibration or {}).items():
        try:
            t = float(key)
        except ValueError:
            continue
        if near is None or abs(t - bed) < abs(near[0] - bed):
            near = (t, cal)
    if near is not None:
        t, cal = near
        settle = float(cal.get('settle', 0.))
        cal_rise = max(t - float(cal.get('from', 20.)), 1.)
        if bed > t:
            # Hotter: scaled up by the bigger rise, never less than measured
            s = settle * min(max(rise / cal_rise, 1.), 2.)
        else:
            # Not hotter: at most the measured time, less for a smaller rise
            s = settle * min(rise / cal_rise, 1.)
        return min(s, max_s), "calibrated at %d C" % (t,)
    return min(rise * per_degree, max_s), "%.0f s per degree" % (per_degree,)


class BedSoak:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.calibration = {}
        self.running = False
        self.last = []
        self.soak = 0.
        self.until = 0.
        self.mode = "time"
        self.points = 1
        self.enabled = True
        self.abort = False
        self.cancel = False     # a cancel waits for the print start to end
        self.printer.register_event_handler("klippy:connect", self._connect)
        webhooks = self.printer.lookup_object('webhooks', None)
        if webhooks is not None:
            webhooks.register_endpoint("ad5x_soak/abort", self._handle_abort)
        for cmd, desc in (
                ("BED_SOAK_CALIBRATE", "Measure how long the bed's Z keeps "
                 "moving after heating: BED= (from a cold bed)"),
                ("BED_SOAK_START", "PRINT_START: decide the bed soak: BED= "
                 "FROM= [SECONDS=]"),
                ("BED_SOAK_ENABLE", "Bed heat soak on or off for every "
                 "print: ENABLE=0|1"),
                ("BED_SOAK_WAIT", "PRINT_START: wait for the rest of the "
                 "bed soak"),
                ("_PRINT_START_HEAT", "PRINT_START: wait for a heater, a "
                 "cancel ends it: HEATER= [MINIMUM=]")):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        desc=desc)

    def _connect(self):
        self._load()
        self._hook_cancel()

    def _load(self):
        sv = self.printer.lookup_object('save_variables', None)
        v = sv.allVariables.get(VARIABLE) if sv is not None else None
        if isinstance(v, dict):
            self.calibration = {str(k): c for k, c in v.items()
                                if isinstance(c, dict)}
        on = sv.allVariables.get(ON_VARIABLE) if sv is not None else None
        if on in (0, 1) and not isinstance(on, float):
            self.enabled = bool(on)

    def _save(self):
        if self.printer.lookup_object('save_variables', None) is None:
            return
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=\"%r\"" % (VARIABLE,
                                                        self.calibration))

    def _status(self, msg):
        self.gcode.run_script_from_command('_PRINT_STATUS MSG="%s"' % (msg,))

    def _hook_cancel(self):
        # Note a cancel when it arrives, before it waits for the G-code
        # queue (webhooks has no public way to wrap an endpoint)
        endpoints = getattr(self.printer.lookup_object('webhooks'),
                            '_endpoints', None)
        orig = (endpoints or {}).get("pause_resume/cancel")
        if orig is None:
            logging.info("ad5x_soak: no pause_resume/cancel endpoint; a "
                         "cancel waits for the print start to end")
            return

        def cancel(web_request):
            self.cancel = True
            try:
                orig(web_request)
            finally:
                self.cancel = False
        endpoints["pause_resume/cancel"] = cancel

    def _check_cancel(self):
        if self.cancel:
            raise self.gcode.error("Print start cancelled")

    def _handle_abort(self, web_request):
        if self.running:
            self.abort = True
        web_request.send({'running': self.running})

    def _sleep(self, seconds, start=False):
        end = self.reactor.monotonic() + seconds
        while not self.printer.is_shutdown():
            if self.abort:
                raise self.gcode.error("Bed soak calibration stopped")
            if start:
                self._check_cancel()
            now = self.reactor.monotonic()
            if now >= end:
                return
            self.reactor.pause(min(end, now + 1.))
        raise self.gcode.error("Shutdown during the bed soak")

    def _temp(self, name):
        heater = self.printer.lookup_object(name)
        return heater.get_status(self.reactor.monotonic())['temperature']

    def _probe_at(self, xy):
        self.gcode.run_script_from_command(
            "G90\nG1 Z5 F800\nG1 X%.1f Y%.1f F30000\nWEIGHT_TARE\nPROBE\n"
            "G1 Z5 F800" % xy)
        probe = self.printer.lookup_object('probe')
        st = probe.get_status(self.reactor.monotonic())
        return st['last_probe_position'][2]

    def _probe_points(self, n):
        return [self._probe_at(xy) for xy in (POINTS5 if n == 5
                                              else POINTS5[:1])]

    # Calibration
    def cmd_BED_SOAK_CALIBRATE(self, gcmd):
        bed = gcmd.get_float('BED', minval=40., maxval=110.)
        npts = gcmd.get_int('POINTS', 5)
        if npts not in (1, 5):
            raise gcmd.error("POINTS is 1 or 5")
        nozzle = gcmd.get_float('NOZZLE', 140., minval=0., maxval=200.)
        nozzle_soak = gcmd.get_float('NOZZLE_SOAK', 300., minval=0.)
        interval = gcmd.get_float('INTERVAL', 60. if npts == 5 else 30.,
                                  minval=10.)
        stable = gcmd.get_float('STABLE', .02, above=0.)
        window = gcmd.get_float('WINDOW', 240., minval=interval)
        max_s = gcmd.get_float('MAX', 1500., minval=window)
        start = self._temp('heater_bed')
        if start > 40. and not gcmd.get_int('FORCE', 0):
            raise gcmd.error("The bed is at %.0f C: start from a cold bed "
                             "(below 40 C) for real numbers, or FORCE=1"
                             % (start,))
        self.running = True
        self.abort = False
        self.last = []
        readings = [[] for _ in range(npts)]
        try:
            gcmd.respond_info("Bed soak calibration at %.0f C (from %.0f C):"
                              " nozzle %.0f C, probing %s every %.0f s until"
                              " Z stays within %.3f mm for %.0f s"
                              % (bed, start, nozzle, "the centre and corners"
                                 if npts == 5 else "the centre", interval,
                                 stable, window))
            self.gcode.run_script_from_command("G28")
            self._status("Bed soak test: heating nozzle")
            self.gcode.run_script_from_command(
                "G90\nG1 X%.1f Y%.1f Z10 F30000\nM109 S%.0f" % (CENTRE + (nozzle,)))
            end = self.reactor.monotonic() + nozzle_soak
            while self.reactor.monotonic() < end:
                left = end - self.reactor.monotonic()
                self._status("Bed soak test: nozzle settling %d:%02d"
                             % (left // 60, left % 60))
                self._sleep(min(left, 5.))
            self.gcode.run_script_from_command("M140 S%.0f" % (bed,))
            heat_end = self.reactor.monotonic() + 900.
            while self._temp('heater_bed') < bed - 1.:
                if self.reactor.monotonic() > heat_end:
                    raise self.gcode.error(
                        "Bed did not reach %.0f C in 15 min: check the bed"
                        % (bed,))
                self._status("Bed soak test: bed %.0f / %.0f C"
                             % (self._temp('heater_bed'), bed))
                self._sleep(5.)
            t0 = self.reactor.monotonic()
            while True:
                t = self.reactor.monotonic() - t0
                zs = self._probe_points(npts)
                for r, z in zip(readings, zs):
                    r.append((round(t, 1), round(z, 4)))
                self.last.append([round(t, 1)] + [round(z, 4) for z in zs])
                d = [z - r[0][1] for z, r in zip(zs, readings)]
                gcmd.respond_info("%4d s: centre %+.4f%s (since the bed was "
                                  "hot)" % (t, d[0], "" if npts == 1 else
                                            ", corners " + " ".join(
                                                "%+.4f" % x for x in d[1:])))
                self._status("Bed soak test: %d s, centre %+.3f" % (t, d[0]))
                if all(is_stable(r, stable, window) for r in readings) \
                        or t >= max_s:
                    break
                self._sleep(max(0., t0 + t + interval
                                - self.reactor.monotonic()))
        finally:
            self.running = False
            self.abort = False
            self.gcode.run_script_from_command("M140 S0\nM104 S0")
            self._status("")
        if not readings[0]:
            return
        settle = settle_time(readings[0], stable)
        corners = max([settle_time(r, stable) for r in readings[1:]] or [0.])
        last4 = [sum(z for t, z in r[-4:]) / len(r[-4:]) for r in readings]
        change = [f - r[0][1] for f, r in zip(last4, readings)]
        warp = max([abs(c - change[0]) for c in change[1:]] or [0.])
        done = all(is_stable(r, stable, window) for r in readings)
        self.calibration["%d" % (round(bed),)] = {
            'settle': round(settle), 'settle_corners': round(corners),
            'drift': round(change[0], 4),
            'warp': round(warp, 4), 'points': npts, 'from': round(start),
            'stable': done, 'date': time.strftime("%Y-%m-%d")}
        self._save()
        gcmd.respond_info(
            "Bed soak at %.0f C: the centre moved %+.3f mm and stayed within "
            "%.3f mm after %d s%s%s. PRINT_START now soaks %d s after the bed"
            " is hot (the purge and brushing count)."
            % (bed, change[0], stable, settle,
               "" if npts == 1 else "; the corners moved up to %.3f mm more "
               "or less than the centre, the slowest settled after %d s"
               % (warp, corners),
               "" if done else " (not all settled within MAX)", settle))

    # Print start
    def cmd_BED_SOAK_START(self, gcmd):
        bed = gcmd.get_float('BED')
        start = gcmd.get_float('FROM', 0.)
        self.mode = gcmd.get('MODE', 'time').lower()
        if self.mode not in ('time', 'probe'):
            raise gcmd.error("MODE is time or probe")
        self.points = gcmd.get_int('POINTS', 1)
        if self.points not in (1, 5):
            raise gcmd.error("POINTS is 1 or 5")
        if gcmd.get('SECONDS', '') != '':
            soak, why = gcmd.get_float('SECONDS', minval=0.), "SOAK="
        elif not self.enabled:
            soak, why = 0., "off"
        else:
            soak, why = soak_seconds(
                bed, start, self.calibration,
                gcmd.get_float('PER_DEGREE', 3., minval=0.),
                gcmd.get_float('MAX', 600., minval=0.))
        self.soak = soak
        self.until = self.reactor.monotonic() + soak
        if soak > 0:
            gcmd.respond_info("Bed heat soak: %s%d s (%s)" % (
                "up to " if self.mode == 'probe' else "", soak, why))

    def cmd_BED_SOAK_ENABLE(self, gcmd):
        if gcmd.get('ENABLE', None) is not None:
            self.enabled = gcmd.get_int('ENABLE', minval=0, maxval=1) == 1
            if self.printer.lookup_object('save_variables', None) is not None:
                self.gcode.run_script_from_command(
                    "SAVE_VARIABLE VARIABLE=%s VALUE=%d"
                    % (ON_VARIABLE, self.enabled))
        cal = ", ".join("%s C: %s s" % (t, c.get('settle'))
                        for t, c in sorted(self.calibration.items()))
        gcmd.respond_info("Bed heat soak is %s%s" % (
            "on" if self.enabled else "off (PRINT_START SOAK= still works)",
            "; calibrated: " + cal if cal else "; not calibrated (3 s per "
            "degree the bed rises)"))

    def cmd_BED_SOAK_WAIT(self, gcmd):
        if self.soak <= 0:
            return
        try:
            if self.mode == 'probe':
                self._probe_until_stable(gcmd)
                return
            while True:
                left = self.until - self.reactor.monotonic()
                if left < 1.:
                    break
                # "Heat soak", not "Bed heat soak": HelixScreen's print start
                # steps read "bed ... heat" as heating the bed, a step it has
                # passed by now, and the screen stayed on the step before
                self._status("Heat soak %d:%02d" % (left // 60, left % 60))
                self._sleep(min(left, 5.), start=True)
        finally:
            self.soak = 0.

    def _probe_until_stable(self, gcmd, stable=.005, interval=60.):
        self._check_cancel()
        prev = self._probe_points(self.points)
        while self.reactor.monotonic() < self.until:
            self._status("Heat soak: waiting for Z to settle")
            self._sleep(interval, start=True)
            zs = self._probe_points(self.points)
            moved = max(abs(a - b) for a, b in zip(zs, prev))
            if moved <= stable:
                gcmd.respond_info("Bed heat soak: Z settled (at most %.3f mm"
                                  " in %d s)" % (moved, interval))
                break
            prev = zs

    def cmd__PRINT_START_HEAT(self, gcmd):
        # As TEMPERATURE_WAIT (heaters.py) / M109's wait, checking for a
        # cancel each second; the toolhead is still here
        try:
            heater = self.printer.lookup_object('heaters').lookup_heater(
                gcmd.get('HEATER'))
        except self.printer.config_error as e:
            raise gcmd.error(str(e))    # not a shutdown for a wrong name
        minimum = gcmd.get_float('MINIMUM', None)
        if self.printer.get_start_args().get('debugoutput') is not None:
            return      # batch mode (tools/test_image.sh), as heaters.py
        toolhead = self.printer.lookup_object('toolhead')
        eventtime = self.reactor.monotonic()
        while not self.printer.is_shutdown():
            self._check_cancel()
            temp, target = heater.get_temp(eventtime)
            if minimum is not None:
                if temp >= minimum:
                    return
            elif target <= 0. or not heater.check_busy(eventtime):
                return
            toolhead.get_last_move_time()
            self.reactor.pause(eventtime + 1.)
            eventtime = self.reactor.monotonic()
        raise gcmd.error("Shutdown while heating")

    def get_status(self, eventtime):
        return {'enabled': self.enabled,
                'calibration': self.calibration, 'running': self.running,
                'soak': self.soak, 'last': self.last,
                'cancel': self.cancel}


def load_config(config):
    return BedSoak(config)
