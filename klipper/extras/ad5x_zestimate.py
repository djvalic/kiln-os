# Z offset estimate from the bed load cells (Z_OFFSET_ESTIMATE)
#
# The AD5X probe is the bed's strain gauges: the weighing board raises the
# probe pin once the nozzle presses hard enough, so the probe fires some
# way past first contact. ad5x.cfg's [probe] z_offset (-0.25) assumes how
# far; the saved print Z offset makes up the rest. The board also reports
# the force in grams, so this measures it:
#   1. PROBE at a point (tared first, as the Z check does): trigger height.
#   2. Up above contact, tare, then down in small steps, standing still at
#      each to read the force, until max_force or the trigger height (no
#      harder than probing presses).
#   3. Fit a line to the force once it clearly rises; where it reaches 0 g
#      is first contact. press-in = contact - trigger.
#   4. Klipper takes the bed surface to be trigger - z_offset; the nozzle
#      really touches at contact, so the print Z offset that puts a layer
#      at its nominal height is  press-in + z_offset.
# Reports only (SAVE=1 saves it as the print Z offset). Every step is
# logged to klippy.log ("ad5x_zestimate:").
#
# Heights: the probe result is in toolhead (machine) coordinates, before the
# bed mesh and the G-code Z offset. Every move after the probe is made in
# the same coordinates (toolhead.manual_move), not with G1: with a mesh
# loaded (a print's adaptive mesh stays loaded after it ends) or an offset
# set, G1 Z<trigger + x> lands somewhere else, measured 3 mm below the
# trigger on a real printer (2026-11-25), pressing the nozzle into the bed.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging


def fit_contact(points, min_force):
    """points: [(z, grams)], z going down. Least-squares line through the
    points at or above min_force; returns (contact_z, grams_per_mm, r2,
    n) where the line reaches 0 g, or None with too few points."""
    pts = [(z, f) for z, f in points if f >= min_force]
    n = len(pts)
    if n < 3:
        return None
    mz = sum(z for z, _ in pts) / n
    mf = sum(f for _, f in pts) / n
    szz = sum((z - mz) ** 2 for z, _ in pts)
    szf = sum((z - mz) * (f - mf) for z, f in pts)
    if szz <= 0. or szf >= 0.:
        return None              # force must rise as Z goes down
    slope = szf / szz            # grams per mm (negative)
    contact = mz - mf / slope
    sff = sum((f - mf) ** 2 for _, f in pts)
    r2 = (szf * szf) / (szz * sff) if sff > 0. else 0.
    return contact, -slope, r2, n


class AD5XZEstimate:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.x, self.y = config.getfloatlist('position', (107.5, 107.5),
                                             count=2)
        # Measured hot, first contact is 0.2-0.25 mm above the trigger, but
        # plastic on the tip reaches up to 0.7 mm: start well above that
        self.start = config.getfloat('start_above', 1.2, above=0.)
        self.step = config.getfloat('step', .02, above=0.)
        # Grams at the board's 56 counts per gram (issue #94: these were
        # 400 / 30 at a wrong 43 counts per gram, the same forces)
        self.max_force = config.getfloat('max_force', 300., above=0.)
        self.min_force = config.getfloat('min_force', 23., above=0.)
        # 0: no lower than where the probe fired, so never pressing harder
        # than probing does
        self.below = config.getfloat('max_below_trigger', 0., minval=0.)
        self.samples = config.getint('samples', 3, minval=1)
        # None: [ad5x_weight]'s counts_per_gram (56)
        self.counts_per_gram = config.getfloat('counts_per_gram', None,
                                               above=0.)
        # fit only from this share of the highest force up
        self.fit_from = config.getfloat('fit_from', .25, minval=0.,
                                        maxval=.9)
        self.settle = config.getfloat('settle', .3, minval=0.)
        # After the probe's press the reading creeps back for a while:
        # wait before taring
        self.tare_wait = config.getfloat('tare_wait', 3., minval=0.)
        self.last = {}
        self.gcode.register_command(
            'Z_OFFSET_ESTIMATE', self.cmd_Z_OFFSET_ESTIMATE,
            desc=self.cmd_Z_OFFSET_ESTIMATE_help)

    def _run(self, script):
        self.gcode.run_script_from_command(script)

    def _move(self, x=None, y=None, z=None, speed=5.):
        """Move in toolhead coordinates (as the probe reports them), past
        the bed mesh and the G-code offset; speed in mm/s."""
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.manual_move([x, y, z], speed)
        toolhead.wait_moves()

    def _trigger(self):
        """Toolhead Z where the probe last fired (last_probe_position is
        the bed's height: the trigger minus the probe's z_offset)."""
        probe = self.printer.lookup_object('probe')
        lp = probe.get_status(self.reactor.monotonic())['last_probe_position']
        return lp.z + self.z_offset

    def _raw(self, weight):
        """Mean raw count over samples reads. H7's reply is "command H7
        ok. <raw> <grams> g": grams come in 20 g steps, the raw count is
        about 56 per gram ([ad5x_weight] counts_per_gram)."""
        vals = []
        for _ in range(self.samples):
            reply = weight._run(weight._request, "H7")
            try:
                vals.append(int(reply.split()[3]))
            except (IndexError, ValueError):
                raise self.printer.command_error(
                    "Z_OFFSET_ESTIMATE: bad H7 reply %r" % (reply,))
        return sum(vals) / float(len(vals))

    def _clean(self):
        """As the print's Z check: tare, probe at the bed's front edge,
        then scrub the nozzle along it (soft plastic on the tip squashes a
        little more at every touch)."""
        self._run("G1 X60 Y-3 F30000\nWEIGHT_TARE\nPROBE")
        z = self._trigger()
        self._move(z=z + .3, speed=1000 / 60.)
        self._move(x=130., speed=20.)
        self._move(x=150., speed=20.)
        self._move(z=z + .1, speed=1000 / 60.)
        self._move(x=170., speed=20.)
        self._move(z=z + 5., speed=10.)

    def get_status(self, eventtime):
        return dict(self.last)

    cmd_Z_OFFSET_ESTIMATE_help = (
        "Estimate the print Z offset from the bed load cells "
        "[X= Y=] [MAX_FORCE=] [STEP=] [SAVE=1]")

    def cmd_Z_OFFSET_ESTIMATE(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        weight = self.printer.lookup_object('ad5x_weight', None)
        probe = self.printer.lookup_object('probe', None)
        if weight is None or probe is None:
            raise gcmd.error("Z_OFFSET_ESTIMATE needs [ad5x_weight] "
                             "and [probe]")
        ps = self.printer.lookup_object('print_stats', None)
        if ps is not None and ps.get_status(None)['state'] in (
                'printing', 'paused'):
            raise gcmd.error("Not during a print")
        now = self.reactor.monotonic()
        if 'xyz' not in toolhead.get_status(now)['homed_axes']:
            raise gcmd.error("Home first (G28)")
        x = gcmd.get_float('X', self.x)
        y = gcmd.get_float('Y', self.y)
        step = gcmd.get_float('STEP', self.step, above=.004, maxval=.05)
        max_force = gcmd.get_float('MAX_FORCE', self.max_force, above=50.,
                                   maxval=1000.)
        cf = self.printer.lookup_object('configfile')
        self.z_offset = float(
            cf.get_status(now)['settings']['probe']['z_offset'])
        self._run("G90\nG1 Z5 F800")
        if gcmd.get_int('CLEAN', 1):
            self._clean()
        # 1. Probe: tared first, as the Z check does
        self._move(x=x, y=y, speed=200.)
        self._run("WEIGHT_TARE\nPROBE")
        trigger = self._trigger()          # toolhead Z where it fired
        # 2. Above contact, tare, then step down (all in toolhead Z)
        top = trigger + self.start
        self._move(z=top, speed=5.)
        self.reactor.pause(self.reactor.monotonic() + self.tare_wait)
        weight._run(weight._tare)
        cpg = self.counts_per_gram or getattr(weight, 'counts_per_gram', 56.)
        base = self._raw(weight)
        base_time = self.reactor.monotonic()
        points = []
        z = top
        bottom = trigger - self.below
        stop = "the lowest point"
        try:
            while z >= bottom - 1e-6:
                self._move(z=z, speed=2.)
                self.reactor.pause(self.reactor.monotonic() + self.settle)
                f = (self._raw(weight) - base) / cpg
                points.append((round(z - trigger, 4), round(f, 1)))
                logging.info("ad5x_zestimate: z %+.3f (above trigger) "
                             "%.1f g", z - trigger, f)
                if f >= max_force:
                    stop = "%.0f g" % (max_force,)
                    break
                z -= step
        finally:
            self._move(z=top, speed=10.)
        # The sensor's zero, clear of the bed again: how far it drifted
        self.reactor.pause(self.reactor.monotonic() + .5)
        drift = (self._raw(weight) - base) / cpg
        drift_time = self.reactor.monotonic() - base_time
        self._move(z=trigger + 5., speed=10.)
        # 3. Fit
        if points and points[0][1] >= self.min_force:
            raise gcmd.error("Z_OFFSET_ESTIMATE: already touching %.1f mm "
                             "above the trigger (%.0f g): start_above higher"
                             % (self.start, points[0][1]))
        # The steep part: the nozzle pressing on the bed (a soft start
        # before it is plastic on the tip, or the sensor drifting)
        peak = max(f for _, f in points) if points else 0.
        fit = fit_contact(points, max(self.min_force, peak * self.fit_from))
        soft = next((z for z, f in points if f >= self.min_force / 2.), None)
        if fit is None:
            raise gcmd.error(
                "Z_OFFSET_ESTIMATE: no clear contact (%d points, last %.0f "
                "g, stopped at %s); see klippy.log" % (
                    len(points), points[-1][1] if points else 0, stop))
        contact, stiffness, r2, n = fit
        press_in = contact                  # relative to the trigger
        estimate = round(press_in + self.z_offset, 3)
        trig_force = None
        for (z1, f1), (z2, f2) in zip(points, points[1:]):
            if z1 >= 0. >= z2 and z1 != z2:
                trig_force = f1 + (f2 - f1) * z1 / (z1 - z2)
        sv = self.printer.lookup_object('save_variables', None)
        saved = None
        if sv is not None:
            zo = sv.allVariables.get('zoffset')
            if isinstance(zo, dict):
                saved = zo.get('z')
        self.last = {'estimate': estimate, 'press_in': round(press_in, 4),
                     'stiffness': round(stiffness, 1), 'r2': round(r2, 4),
                     'points': n, 'trigger_force': None if trig_force is None
                     else round(trig_force, 1), 'saved': saved,
                     'drift': round(drift, 1),
                     'first_touch': soft}
        msg = ("Z offset estimate %.3f mm (saved: %s). First contact %.3f mm "
               "above where the probe fires (ad5x.cfg assumes %.3f); bed "
               "%.0f g/mm, fit of %d points r2 %.3f%s; stopped at %s." % (
                   estimate, "%.3f" % saved if saved is not None else "none",
                   press_in, -self.z_offset, stiffness, n, r2,
                   "" if trig_force is None else
                   ", probe fires at about %.0f g" % (trig_force,), stop))
        msg += (" Sensor zero drifted %+.0f g in %.0f s; first force at "
                "%s mm above the trigger." % (
                    drift, drift_time, "none" if soft is None
                    else "%.2f" % soft))
        logging.info("ad5x_zestimate: %s points %s", msg, points)
        if r2 < .95:
            msg += " The fit is poor (r2 below 0.95): don't trust it."
        if gcmd.get_int('SAVE', 0):
            if r2 < .95:
                raise gcmd.error(msg + " Not saved.")
            self._run("SET_GCODE_OFFSET Z=%.4f" % (estimate,))
            msg += " Saved as the print Z offset."
        gcmd.respond_info(msg)


def load_config(config):
    return AD5XZEstimate(config)
