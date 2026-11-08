# AD5X setup wizard steps (first boot and on demand)
#
# SETUP_WIZARD_STEP STEP=<selfcheck|pid|mesh|shaper|ifs|zoffset|finish>
# [ACTION=start|abort|adjust|accept] and the printer.ad5x_setup status
# object, the contract HelixScreen's AD5X wizard steps use
# (docs/setup-wizard.md). Not "AD5X_SETUP": Klipper reads a command name
# with a digit followed by letters as "AD5" plus parameters. Each step
# runs in the background (as virtual_sdcard does), taking the G-code lock
# only for each command it sends, so ACTION=abort/adjust/accept get
# through between them. The same
# actions are also a Klipper API endpoint, ad5x_setup/control (Moonraker:
# printer.ad5x_setup.control), which works even while a long command
# (PID_CALIBRATE, BED_MESH_CALIBRATE) holds the lock.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import math
import os
import re

# Order on the screen. The mesh step comes before the Z offset step: the
# mesh's nozzle scrub doesn't yet work after a Z offset step (the offset
# is still applied there). The purge box check sits before the Z offset
# (the test patch purges at the box); the soak calibration takes ~15 min,
# so it comes after the IFS tuning and before the summary.
STEPS = ("selfcheck", "pid", "mesh", "shaper", "ifs", "trash", "zoffset",
         "soak", "summary", "finish")

# Z offset test patch temperatures per material (nozzle, bed); MATERIAL=
# picks one, default the loaded IFS slot's type, else PLA.
PATCH_TEMPS = {"PLA": (220., 60.), "PLA-CF": (220., 60.), "SILK": (230., 60.),
               "PETG": (240., 70.), "PETG-CF": (250., 70.),
               "ABS": (250., 90.), "ASA": (250., 90.), "TPU": (230., 50.)}

# Sections the calibrations write that ad5x.cfg (an include) also sets:
# Klipper's SAVE_CONFIG refuses those ("conflicts with included value"),
# so finish writes them to tuning_file, which setup.cfg includes after
# ad5x.cfg.
TUNING_SECTIONS = ("extruder", "heater_bed", "input_shaper")

# print_stats states during which no step starts: they home, heat, probe,
# and finish restarts Klipper
BUSY_STATES = ("printing", "paused")

# Where successive test patches go (offsets from patch_center, mm)
PATCH_SPOTS = ((0., 0.), (-40., 0.), (40., 0.), (0., -40.), (0., 40.))

class SetupAborted(Exception):
    pass

class HeaterOff:
    """Heater control swapped in on abort: holds the heater off and reports
    it settled, so a temperature wait in progress (M109, M190, the PID test
    of PID_CALIBRATE) ends at once with the heater off."""
    def __init__(self, heater):
        self.heater = heater
    def temperature_update(self, read_time, temp, target_temp):
        self.heater.alter_target(0.)
        self.heater.set_pwm(read_time, 0.)
    def check_busy(self, eventtime, smoothed_temp, target_temp):
        return False

class AD5XSetup:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        # PID step (nozzle with the part fan as when printing)
        self.pid_nozzle = config.getfloat('pid_nozzle_temp', 220., above=0.)
        self.pid_bed = config.getfloat('pid_bed_temp', 60., above=0.)
        self.pid_fan = config.getfloat('pid_fan_speed', 1., minval=0.,
                                       maxval=1.)
        # Self-check: each live output runs check_time seconds, then off
        # (house rule: about 10 s). A heater passes when it rose by the
        # given amount, measured up to check_watch seconds after switching
        # off (the sensor lags).
        self.check_time = config.getfloat('check_time', 10., above=0.)
        self.check_watch = config.getfloat('check_watch', 10., minval=0.)
        self.check_nozzle_temp = config.getfloat('check_nozzle_temp', 120.,
                                                 above=0.)
        self.check_bed_temp = config.getfloat('check_bed_temp', 50., above=0.)
        self.nozzle_rise = config.getfloat('check_nozzle_rise', 3., above=0.)
        self.bed_rise = config.getfloat('check_bed_rise', .5, above=0.)
        self.fans = [f.strip() for f in config.get(
            'check_fans', 'fanM106, pcb_fan').split(',') if f.strip()]
        self.filament_sensor = config.get('filament_sensor', 'toolhead')
        self.require_ifs = config.getboolean('require_ifs', True)
        # Mesh: stock's levelling temperatures (AUTO_FULL_BED_LEVEL)
        self.mesh_bed = config.getfloat('mesh_bed_temp', 60., above=0.)
        self.mesh_nozzle = config.getfloat('mesh_nozzle_temp', 140., minval=0.)
        self.heat_timeout = config.getfloat('heat_timeout', 900., above=0.)
        # Z offset test patch
        self.patch_center = config.getfloatlist('patch_center', (107.5, 107.5),
                                                count=2)
        self.patch_size = config.getfloat('patch_size', 30., above=5.)
        self.patch_speed = config.getfloat('patch_speed', 1800., above=0.)
        # Every run starts fresh at this offset, a little high, and is
        # lowered from there: the saved offset may be one never printed
        # with here (stock's or zMod's, carried over at install), and too
        # low scrapes the bed
        self.patch_start_z = config.getfloat('patch_start_z', .1)
        # ESTIMATE=1 on the Z offset step (Z_OFFSET_ESTIMATE, the load cells):
        # off until it has been checked against tuned offsets on printers
        self.estimate_enabled = config.getboolean('zoffset_estimate', False)
        self.max_adjust = config.getfloat('max_adjust', .5, above=0.)
        self.max_total_adjust = config.getfloat('max_total_adjust', 1.,
                                                above=0.)
        self.user_timeout = config.getfloat('user_timeout', 900., above=0.)
        # Files
        self.tuning_file = config.get(
            'tuning_file', '/home/klipper/printer_data/config/ad5x-tuning.cfg')
        self.wizard_flag = config.get(
            'wizard_flag', '/home/klipper/printer_data/comms/run-setup-wizard')
        # Status
        self.step = ""
        self.state = "idle"
        self.message = ""
        self.progress = 0.
        self.progress_fn = None     # live progress while a command runs
        self.results = {}
        self.checks = []
        self.pending_save = False
        # Runtime
        self.inline = False         # step runs inside the G-code command
        self.abort_requested = False
        self.stubbed = []           # (heater, control) replaced on abort
        self.z_deltas = []
        self.z_accept = False
        self.z_reprint = False
        self.z_start = 0.
        self.z_saved = None
        self.gcode.register_command('SETUP_WIZARD_STEP',
                                    self.cmd_SETUP_WIZARD_STEP,
                                    desc=self.cmd_SETUP_WIZARD_STEP_help)
        # SAVE_CONFIG keeps what it can't write itself: Klipper's own goes
        # on with whatever is left
        self.save_config = self.gcode.register_command('SAVE_CONFIG', None)
        self.gcode.register_command('SAVE_CONFIG', self.cmd_SAVE_CONFIG,
                                    desc=self.cmd_SAVE_CONFIG_help)
        webhooks = self.printer.lookup_object('webhooks')
        webhooks.register_endpoint("ad5x_setup/control", self._handle_control)
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
    # Status object (cached values only)
    def get_status(self, eventtime):
        progress = self.progress
        if self.progress_fn is not None:
            try:
                progress = self.progress_fn()
            except Exception:
                logging.exception("ad5x_setup: progress")
        return {
            'step': self.step,
            'state': self.state,
            'message': self.message,
            'progress': round(max(0., min(1., progress)), 3),
            'results': dict(self.results),
            'checks': [dict(c) for c in self.checks],
            'pending_save': self.pending_save,
            'zoffset': round(self._zoffset(), 4),
            'estimate': self.estimate_enabled,
        }
    def _zoffset(self):
        """The live G-code Z offset during the zoffset step, else the
        saved print Z offset (variables.cfg zoffset)."""
        if self.step == "zoffset" and self.state in ("running",
                                                     "waiting_user"):
            gm = self.printer.lookup_object('gcode_move', None)
            if gm is not None:
                return gm.get_status()['homing_origin'].z
        return self._saved_zoffset() or 0.
    def _variables(self):
        sv = self.printer.lookup_object('save_variables', None)
        return sv.allVariables if sv is not None else {}
    def _saved_zoffset(self):
        z = self._variables().get('zoffset')
        if isinstance(z, dict) and isinstance(z.get('z'), (int, float)):
            return float(z['z'])
        return None
    def _set(self, message=None, progress=None):
        if message is not None:
            self.message = message
            logging.info("ad5x_setup: %s: %s", self.step, message)
        if progress is not None:
            self.progress = progress
    def _result(self, key, text):
        # New dict: Moonraker only sees changed objects
        results = dict(self.results)
        results[key] = text
        self.results = results
    def _handle_ready(self):
        # Results of earlier steps survive restarts (variables.cfg), so the
        # summary after finish's SAVE_CONFIG restart still has them.
        saved = self._variables().get('ad5x_setup')
        if not isinstance(saved, dict):
            return
        res = saved.get('results')
        if isinstance(res, dict):
            self.results = {str(k): str(v) for k, v in res.items()}
        if saved.get('restarting'):
            self.step = "finish"
            self.state = "done"
            self.message = saved.get('message') or "Saved"
            self.progress = 1.
            self.reactor.register_callback(lambda e: self._persist(False))
    def _persist(self, restarting):
        """Save the results (and whether finish is restarting Klipper)."""
        if self.printer.lookup_object('save_variables', None) is None:
            return
        data = {'results': dict(self.results), 'restarting': restarting,
                'message': self.message}
        # The value goes through SAVE_VARIABLE's quoting: no quotes in it
        text = repr(data).replace('"', "'")
        script = 'SAVE_VARIABLE VARIABLE=ad5x_setup VALUE="%s"' % (text,)
        try:
            if self.inline:
                self.gcode.run_script_from_command(script)
            else:
                self.gcode.run_script(script)
        except self.printer.command_error as e:
            logging.warning("ad5x_setup: can't save results: %s", e)
    # Commands and the API endpoint
    cmd_SETUP_WIZARD_STEP_help = (
        "Setup wizard step: STEP=selfcheck|pid|trash|zoffset|mesh|shaper|"
        "ifs|soak|summary|finish [ACTION=start|abort|adjust|accept] "
        "[DELTA=] [WAIT=1] [ESTIMATE=1]; "
        "ACTION=wizard asks the screen to run the wizard again")
    def cmd_SETUP_WIZARD_STEP(self, gcmd):
        action = gcmd.get('ACTION', 'start').lower()
        step = gcmd.get('STEP', '').lower()
        params = {k: v for k, v in gcmd.get_command_parameters().items()
                  if k not in ('STEP', 'ACTION', 'DELTA', 'WAIT')}
        delta = gcmd.get_float('DELTA', None)
        wait = gcmd.get_int('WAIT', 0)
        if action == 'start' and wait:
            # Runs here, inside this command (console/macros/tests): the
            # G-code lock stays taken, so only the API endpoint can abort,
            # adjust or accept.
            self._start(step, params, inline=True)
            return
        gcmd.respond_info(self._dispatch(step, action, params, delta))
    def _handle_control(self, web_request):
        try:
            action = str(web_request.get('action', 'start')).lower()
            step = str(web_request.get('step', '')).lower()
            delta = web_request.get('delta', None)
            if delta is not None:
                delta = float(delta)
            params = {}
            for key in ('material', 'extruder', 'bed', 'keep_bed', 'tube',
                        'channel', 'heaters', 'estimate', 'force'):
                if web_request.get(key, None) is not None:
                    params[key.upper()] = str(web_request.get(key))
            msg = self._dispatch(step, action, params, delta)
        except self.printer.command_error:
            raise
        except Exception as e:
            # Anything else would shut Klipper down (webhooks)
            logging.exception("ad5x_setup: control request")
            raise self.printer.command_error("ad5x_setup: %s" % (e,))
        web_request.send({'state': self.state, 'step': self.step,
                          'message': msg})
    def _dispatch(self, step, action, params, delta):
        error = self.printer.command_error
        if action == 'start':
            self._start(step, params, inline=False)
            return "AD5X setup: %s started" % (step,)
        if action == 'abort':
            return self._abort()
        if action == 'wizard':
            if self._printing():
                raise error("SETUP_WIZARD_STEP: no setup wizard during a "
                            "print")
            return self._request_wizard()
        if action in ('adjust', 'accept'):
            if self.state != "waiting_user" or self.step not in (
                    ("zoffset", "trash") if action == 'accept'
                    else ("zoffset",)):
                raise error("SETUP_WIZARD_STEP: ACTION=%s works only while "
                            "the %s is waiting for you" % (
                                action, "Z offset test patch" if action
                                == 'adjust' else "step"))
            if action == 'accept':
                self.z_accept = True
                return "AD5X setup: %s accepted" % (self.step,)
            if delta is None or abs(delta) > self.max_adjust:
                raise error("SETUP_WIZARD_STEP: DELTA= must be between -%g "
                            "and %g" % (self.max_adjust, self.max_adjust))
            total = self._zoffset() + sum(self.z_deltas) + delta - self.z_start
            if abs(total) > self.max_total_adjust + 1e-9:
                raise error("SETUP_WIZARD_STEP: Z offset would move more "
                            "than %g mm from where it started"
                            % (self.max_total_adjust,))
            self.z_deltas = self.z_deltas + [delta]
            return "AD5X setup: Z offset %+.3f" % (delta,)
        raise error("SETUP_WIZARD_STEP: unknown ACTION '%s'" % (action,))
    def _printing(self):
        ps = self.printer.lookup_object('print_stats', None)
        return ps is not None and ps.get_status(
            self.reactor.monotonic()).get('state') in BUSY_STATES
    def _start(self, step, params, inline):
        error = self.printer.command_error
        if step not in STEPS:
            raise error("SETUP_WIZARD_STEP: STEP must be one of %s" % (
                ", ".join(STEPS),))
        if getattr(self, 'held_off', None):
            raise error("SETUP_WIZARD_STEP: %s was left off by an aborted PID "
                        "test: RESTART Klipper first" % (
                            ", ".join(self.held_off),))
        if self.state in ("running", "waiting_user"):
            if (step == "zoffset" and self.step == "zoffset"
                    and self.state == "waiting_user"):
                self.z_reprint = True     # another patch beside the last
                return
            raise error("SETUP_WIZARD_STEP: step '%s' is still running "
                        "(ACTION=abort first)" % (self.step,))
        if self._printing():
            raise error("SETUP_WIZARD_STEP: no setup step during a print")
        self.step = step
        self.state = "running"
        self.abort_requested = False
        self.progress = 0.
        self.progress_fn = None
        self._set("Starting", 0.)
        if inline:
            self._run_step(step, params, True)
            if self.state == "failed":
                raise error(self.message)
            return
        self.reactor.register_callback(
            lambda e: self._run_step(step, params, False))
    def _run_step(self, step, params, inline):
        self.inline = inline
        try:
            getattr(self, "_step_" + step)(params)
            if self.state in ("running", "waiting_user"):
                self.state = "done"
                self.progress = 1.
            if step != "finish":
                self._persist(False)
        except SetupAborted:
            self.state = "aborted"
            self._set("Aborted")
        except self.printer.command_error as e:
            if self.abort_requested:
                self.state = "aborted"
                self._set("Aborted")
            else:
                self.state = "failed"
                self._set(str(e))
        except Exception as e:
            logging.exception("ad5x_setup: step %s", step)
            self.state = "failed"
            self._set("Internal error: %s" % (e,))
        finally:
            self.progress_fn = None
            try:
                if self.state in ("aborted", "failed"):
                    self._make_safe(step)
            finally:
                self._restore_heaters()
                self.abort_requested = False
                self.inline = False
    # Abort
    def _abort(self):
        if self.state not in ("running", "waiting_user"):
            pheaters = self.printer.lookup_object('heaters', None)
            if pheaters is not None:
                pheaters.turn_off_all_heaters()
            return "AD5X setup: nothing running (heaters off)"
        self.abort_requested = True
        self._set("Aborting: heaters off, stopping after the current move")
        # The soak waits for the bed to reach its target; the heaters are off
        # now, so only its own abort flag ends that wait
        soak = self.printer.lookup_object('ad5x_soak', None)
        if soak is not None and getattr(soak, 'running', False):
            soak.abort = True
        # Heaters off now, without the G-code lock, ending any heater wait
        pheaters = self.printer.lookup_object('heaters', None)
        if pheaters is not None:
            for heater in pheaters.heaters.values():
                if not isinstance(heater.control, HeaterOff):
                    self.stubbed.append(
                        (heater, heater.set_control(HeaterOff(heater))))
        ifs = self.printer.lookup_object('ifs', None)
        if ifs is not None:
            ifs.stop_requested = True     # as IFS_STOP: ends a tuning feed
        return "AD5X setup: aborting %s" % (self.step,)
    def _restore_heaters(self):
        # Back to the normal heater control (target 0). A heater whose
        # control already changed (PID_CALIBRATE restores its own) is left.
        for heater, control in self.stubbed:
            if not isinstance(heater.control, HeaterOff):
                continue
            if hasattr(control, 'peaks'):
                # PID_CALIBRATE's test control: its command never returned.
                # Leave the heater held off; a restart brings it back.
                logging.warning("ad5x_setup: %s left off after abort",
                                heater.get_name())
                self.held_off = getattr(self, 'held_off', []) + [
                    heater.get_name()]
                continue
            heater.set_control(control)
        self.stubbed = []
    def _make_safe(self, step):
        """After a failed or aborted step: heaters and part fan off; the Z
        offset step also parks and restores the saved Z offset."""
        script = ["TURN_OFF_HEATERS", "M106 S0"]
        if step == "zoffset":
            script += ["_PARK_END", "M84 X Y E"]
            if self.z_saved is not None:
                script.append('SAVE_VARIABLE VARIABLE=zoffset VALUE="%r"'
                              % (self.z_saved,))
        for line in script:
            try:
                self._gcode_raw(line)
            except self.printer.command_error as e:
                logging.warning("ad5x_setup: cleanup '%s': %s", line, e)
    # Helpers
    def _gcode_raw(self, script):
        if self.inline:
            self.gcode.run_script_from_command(script)
        else:
            self.gcode.run_script(script)
    def _check(self):
        if self.abort_requested:
            raise SetupAborted()
        if self.printer.is_shutdown():
            raise self.printer.command_error("Klipper shut down")
    def _gcode(self, script):
        self._check()
        self._gcode_raw(script)
        self._check()
    def _pause(self, seconds):
        self.reactor.pause(self.reactor.monotonic() + seconds)
        self._check()
    def _batch(self):
        # Klipper's file output mode (tests): no temperatures to wait for
        return self.printer.get_start_args().get('debugoutput') is not None
    def _heater(self, name):
        pheaters = self.printer.lookup_object('heaters')
        try:
            return pheaters.lookup_heater(name)
        except self.printer.config_error as e:
            raise self.printer.command_error(str(e))
    def _temp(self, heater):
        return heater.get_status(self.reactor.monotonic())['temperature']
    def _homed(self):
        toolhead = self.printer.lookup_object('toolhead')
        status = toolhead.get_status(self.reactor.monotonic())
        return all(a in status['homed_axes'] for a in "xyz")
    def _home(self):
        if not self._homed():
            self._set("Homing")
            self._gcode("G28")
    def _settings(self, section):
        cf = self.printer.lookup_object('configfile')
        return cf.get_status(self.reactor.monotonic())['settings'].get(
            section, {})
    def _autosave(self, section):
        """Options a calibration left for SAVE_CONFIG in [section]."""
        fc = self.printer.lookup_object('configfile').autosave.fileconfig
        if fc is None or not fc.has_section(section):
            return {}
        return dict(fc.items(section))
    def _heat_and_wait(self, targets, prog):
        """Set heater targets {name: temp} and wait until each is within
        1 C of it (abortable, unlike M109/M190)."""
        heaters = {n: self._heater(n) for n in targets}
        for name, temp in targets.items():
            self._gcode("SET_HEATER_TEMPERATURE HEATER=%s TARGET=%g"
                        % (name, temp))
        start = {n: self._temp(h) for n, h in heaters.items()}
        end = self.reactor.monotonic() + self.heat_timeout
        while not self._batch():
            temps = {n: self._temp(h) for n, h in heaters.items()}
            left = [n for n in targets if temps[n] < targets[n] - 1.]
            if not left:
                break
            done = min(max(0., (temps[n] - start[n])
                           / max(1., targets[n] - start[n])) for n in left)
            self._set("Heating: " + ", ".join(
                "%s %.0f/%.0f C" % ("bed" if n == "heater_bed" else "nozzle",
                                    temps[n], targets[n]) for n in targets),
                prog[0] + (prog[1] - prog[0]) * done)
            if self.reactor.monotonic() > end:
                raise self.printer.command_error(
                    "Heating timed out (%s)" % (", ".join(left),))
            self._pause(1.)
    def _pid_progress(self, name, a, b):
        heater = self._heater(name)
        peaks = getattr(heater.control, 'peaks', None)
        if peaks is None:
            return a
        return a + (b - a) * min(len(peaks), 12) / 12.
    # Steps
    def _step_selfcheck(self, params):
        self.checks = []
        total = 7. + len(self.fans)
        def add(name, ok, detail, required=True):
            self.checks = self.checks + [{'name': name, 'ok': bool(ok),
                                          'detail': detail,
                                          'required': required}]
            self.progress = len(self.checks) / total
        def try_gcode(name, script, detail, required=True):
            try:
                self._gcode(script)
                add(name, True, detail, required)
            except self.printer.command_error as e:
                if self.abort_requested:
                    raise SetupAborted()
                add(name, False, str(e), required)
        # Boards. Klipper only gets ready with every MCU connected.
        now = self.reactor.monotonic()
        for name, mcu in self.printer.lookup_objects('mcu'):
            add("MCU %s" % (name.split()[-1],), True,
                mcu.get_status(now).get('mcu_version', 'connected'))
        # IFS
        self._set("Checking the IFS")
        ifs = self.printer.lookup_object('ifs', None)
        if ifs is None:
            add("IFS", False, "not configured", self.require_ifs)
        elif not ifs.get_status(now)['connected']:
            add("IFS", False, ifs.error or "not connected", self.require_ifs)
        else:
            try_gcode("IFS", "IFS_STATUS", "answers, version %s" % (
                ifs.version,), self.require_ifs)
        self._set("Checking the accelerometer")
        if self._batch():
            # No sensor data in file output mode (the query would crash)
            add("Accelerometer", True, "not checked (file output mode)")
        else:
            try_gcode("Accelerometer", "ACCELEROMETER_QUERY", "answers")
        if self.printer.lookup_object('ad5x_weight', None) is not None:
            self._set("Checking the bed strain gauges")
            try_gcode("Bed strain gauges", "WEIGHT_TARE", "tared")
        sensor = self.printer.lookup_object(
            'adc_filament_sensor %s' % (self.filament_sensor,), None)
        if sensor is None:
            add("Toolhead filament sensor", False, "not configured")
        elif sensor.value is None:
            add("Toolhead filament sensor", False, "no reading")
        else:
            present = sensor.get_status(now)['filament_detected']
            add("Toolhead filament sensor", True, "%s (%.2f)" % (
                "filament" if present else "empty", sensor.value))
        # Fans, one at a time, check_time each
        for fan in self.fans:
            obj_name = fan if ' ' in fan else 'fan_generic %s' % (fan,)
            obj = self.printer.lookup_object(obj_name, None)
            label = {"fanM106": "Part fan", "pcb_fan": "Board fan"}.get(
                fan, fan)
            if obj is None:
                add(label, False, "not configured")
                continue
            self._set("%s should spin now (%.0f s)" % (label,
                                                       self.check_time))
            rpm = None
            try:
                self._gcode("SET_FAN_SPEED FAN=%s SPEED=1" % (fan,))
                self._pause(self.check_time)
                rpm = obj.get_status(self.reactor.monotonic()).get('rpm')
            finally:
                self._gcode_raw("SET_FAN_SPEED FAN=%s SPEED=0" % (fan,))
            if rpm is None:
                add(label, True, "ran %.0f s (no speed sensor)"
                    % (self.check_time,), False)
            else:
                add(label, rpm > 0, "%.0f rpm" % (rpm,))
        # Homing
        self._set("Homing")
        try_gcode("Homing", "G28", "X, Y and Z home")
        # Heaters, together: check_time on, then off; rise measured until
        # check_watch after switching off
        ext, bed = self._heater('extruder'), self._heater('heater_bed')
        t_ext, t_bed = self._temp(ext), self._temp(bed)
        tgt_ext = min(max(self.check_nozzle_temp, t_ext + 40.), 200.)
        tgt_bed = min(max(self.check_bed_temp, t_bed + 15.), 90.)
        max_ext, max_bed = t_ext, t_bed
        start = self.reactor.monotonic()
        try:
            self._gcode("SET_HEATER_TEMPERATURE HEATER=extruder TARGET=%g\n"
                        "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=%g"
                        % (tgt_ext, tgt_bed))
            while self.reactor.monotonic() - start < self.check_time:
                max_ext = max(max_ext, self._temp(ext))
                max_bed = max(max_bed, self._temp(bed))
                self._set("Heater test: nozzle %.1f C, bed %.1f C" % (
                    self._temp(ext), self._temp(bed)))
                self._pause(.5)
        finally:
            self._gcode_raw("SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0\n"
                            "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0")
        off = self.reactor.monotonic()
        while self.reactor.monotonic() - off < self.check_watch and (
                max_ext - t_ext < self.nozzle_rise
                or max_bed - t_bed < self.bed_rise):
            max_ext = max(max_ext, self._temp(ext))
            max_bed = max(max_bed, self._temp(bed))
            self._set("Heaters off; nozzle %.1f C, bed %.1f C" % (
                self._temp(ext), self._temp(bed)))
            self._pause(.5)
        if self._batch():
            # Klipper's test mode has no temperatures (tools/test_wizard.sh)
            add("Nozzle heater", True, "not tested (Klipper test mode)")
            add("Bed heater", True, "not tested (Klipper test mode)")
        else:
            add("Nozzle heater", max_ext - t_ext >= self.nozzle_rise,
                "+%.1f C in %.0f s" % (max_ext - t_ext, self.check_time))
            add("Bed heater", max_bed - t_bed >= self.bed_rise,
                "+%.1f C in %.0f s" % (max_bed - t_bed, self.check_time))
        failed = [c['name'] for c in self.checks
                  if not c['ok'] and c['required']]
        ok = len([c for c in self.checks if c['ok']])
        self._result("selfcheck", "%d of %d checks OK" % (
            ok, len(self.checks)))
        if failed:
            raise self.printer.command_error(
                "Self-check failed: %s" % (", ".join(failed),))
        self._set("All checks passed", 1.)
    def _step_pid(self, params):
        # HEATERS=extruder after a nozzle change (the bed didn't change),
        # bed, or both (default)
        which = str(params.get('HEATERS', 'both') or 'both').lower()
        heaters = [h for h in (
            ("extruder", "nozzle", self.pid_nozzle),
            ("heater_bed", "bed", self.pid_bed))
            if which == 'both' or h[1] == which or h[0] == which]
        if not heaters:
            raise self.printer.command_error(
                "HEATERS is extruder, bed or both")
        self._home()
        cx, cy = self.patch_center
        self._gcode("G90\nG1 X%.1f Y%.1f Z10 F6000" % (cx, cy))
        if self._batch():
            # Klipper's test mode: no temperatures, PID_CALIBRATE can't run
            self._result("pid", "not tuned (Klipper test mode)")
            self._set("PID: not tuned in Klipper test mode", 1.)
            return
        results = []
        n = len(heaters)
        for i, (name, label, target) in enumerate(heaters):
            prog = (i / float(n), (i + 1) / float(n))
            self._set("PID tuning the %s at %.0f C (takes a few minutes)"
                      % (label, target), prog[0])
            fan = self.pid_fan if name == "extruder" else 0.
            self._gcode("M106 S%d" % (round(fan * 255),))
            self.progress_fn = (lambda n=name, p=prog:
                                self._pid_progress(n, p[0], p[1]))
            try:
                self._gcode("PID_CALIBRATE HEATER=%s TARGET=%g" % (
                    name, target))
            finally:
                self.progress_fn = None
                self._gcode_raw("M106 S0")
            vals = self._autosave(name)
            if 'pid_kp' not in vals:
                raise self.printer.command_error(
                    "PID_CALIBRATE gave no result for %s" % (name,))
            results.append("%s Kp=%s Ki=%s Kd=%s" % (
                label, vals['pid_kp'], vals['pid_ki'], vals['pid_kd']))
        self._result("pid", ", ".join(results))
        self.pending_save = True
        self._set("PID values ready to save", 1.)
    def _step_mesh(self, params):
        keep_bed = int(params.get('KEEP_BED', 0) or 0)
        self._home()
        cx, cy = self.patch_center
        self._gcode("G90\nG1 X%.1f Y%.1f Z10 F6000" % (cx, cy))
        try:
            self._heat_and_wait({'heater_bed': self.mesh_bed,
                                 'extruder': self.mesh_nozzle}, (0., .3))
            # As a print's Z check: tare, probe the front edge, scrub the
            # nozzle along it, then the mesh. Plastic left on the tip
            # squashes a little more at every touch, and the probe's
            # samples then exceed samples_tolerance.
            self._set("Cleaning the nozzle on the bed edge", .32)
            # The Z offset from the step before is still applied: clear it for
            # the tap and the scrub, as PRINT_START does (the scrub's height
            # is in the offset's frame)
            self._gcode("G90\n_SET_GCODE_OFFSET Z=0\nG1 Z5 F800\nG1 X60 Y-3 F30000\n"
                        "WEIGHT_TARE\nPROBE")
            self._scrub()
            self._set("Probing the bed", .35)
            self._gcode("BED_MESH_CALIBRATE PROFILE=default")
        except Exception:
            self._gcode_raw("SET_HEATER_TEMPERATURE HEATER=heater_bed "
                            "TARGET=0")
            raise
        finally:
            self._gcode_raw("SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0")
        if not keep_bed:
            self._gcode("SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0")
        bm = self.printer.lookup_object('bed_mesh').get_status(
            self.reactor.monotonic())
        points = [z for row in bm.get('probed_matrix') or [] for z in row]
        rows = bm.get('probed_matrix') or [[]]
        if points:
            self._result("mesh", "%dx%d points, range %.3f mm" % (
                len(rows[0]), len(rows), max(points) - min(points)))
        else:
            self._result("mesh", "done")
        self.pending_save = True
        self._set("Bed mesh ready to save", 1.)
    def _scrub(self):
        """_CHECK_Z_SCRUB's moves: along the bed's front edge just above
        where the probe (at X60 Y-3) fired, part fan on."""
        probe = self.printer.lookup_object('probe', None)
        if probe is None:
            return
        lp = probe.get_status(self.reactor.monotonic()).get(
            'last_probe_position')
        if lp is None:
            return
        z = lp.z + float(self._settings('probe').get('z_offset', 0.))
        logging.info("ad5x_setup: scrub: probe at %.3f, z_offset %.3f, "
                     "height %.3f", lp.z, float(
                         self._settings('probe').get('z_offset', 0.)), z)
        self._gcode("G90\nM106 S255\nG1 Z%.3f F1000\nG1 X130 F1200\n"
                    "G1 X150 F1200\nG1 Z%.3f F1000\nM106 S0\nG1 Z5 F6000"
                    % (z + .3, z + .1))
    def _step_shaper(self, params):
        try:
            import numpy  # noqa: F401  (SHAPER_CALIBRATE needs it)
        except ImportError:
            raise self.printer.command_error(
                "Vibration calibration needs numpy, which this system image "
                "doesn't have")
        self._home()
        for i, axis in enumerate("XY"):
            self._set("Measuring vibrations on %s (the printer buzzes)"
                      % (axis,), .05 + .45 * i)
            self._gcode("SHAPER_CALIBRATE AXIS=%s" % (axis,))
        vals = self._autosave('input_shaper')
        res = ["%s %s %.1f Hz" % (axis.upper(), vals['shaper_type_' + axis],
                                  float(vals['shaper_freq_' + axis]))
               for axis in "xy" if 'shaper_type_' + axis in vals]
        self._result("shaper", ", ".join(res) or "done")
        self.pending_save = True
        self._set("Input shaper ready to save", 1.)
    def _step_ifs(self, params):
        ifs = self.printer.lookup_object('ifs', None)
        if ifs is None:
            raise self.printer.command_error("No IFS configured")
        args = "".join(" %s=%s" % (k, params[k]) for k in ("TUBE", "CHANNEL")
                       if params.get(k))
        self._home()
        # Filament left in the toolhead (from an earlier run): unload it first.
        # IFS_TUNE only does that when it knows the slot; after a restart it
        # doesn't, so the step does it here.
        if ifs._head_has_filament():
            chan = int(params.get('CHANNEL', 0) or 0) or self._reload_channel()
            if not chan:
                raise self.printer.command_error(
                    "The toolhead holds filament from an unknown slot: pull it "
                    "out by hand (cut the tip first), then Retry")
            self._set("Unloading slot %d from the toolhead" % (chan,), .02)
            self._gcode("IFS_UNLOAD SLOT=%d" % (chan,))
        self._set("Tuning the IFS (QuickSwap-like)", 0.)
        def progress():
            if ifs.tune_message:
                self.message = "IFS: " + ifs.tune_message
            return ifs.tune_progress or 0.
        self.progress_fn = progress
        try:
            self._gcode("IFS_TUNE" + args)
        finally:
            self.progress_fn = None
        self._result("ifs", ifs._tune_summary())
        self._set("IFS tuned", 1.)
    def _step_zoffset(self, params):
        mat = (params.get('MATERIAL') or self._loaded_material() or "PLA")
        nozzle, bed = PATCH_TEMPS.get(mat.upper(), PATCH_TEMPS["PLA"])
        nozzle = float(params.get('EXTRUDER') or nozzle)
        bed = float(params.get('BED') or bed)
        zo = self._variables().get('zoffset')
        # No saved value: abort puts zero back, not the patch's start offset
        self.z_saved = dict(zo) if isinstance(zo, dict) else {'z': 0.}
        self.z_deltas = []
        self.z_accept = self.z_reprint = False
        sensor = self.printer.lookup_object(
            'adc_filament_sensor %s' % (self.filament_sensor,), None)
        if sensor is not None and sensor.value is not None and not \
                sensor.get_status(self.reactor.monotonic())[
                    'filament_detected']:
            chan = self._reload_channel()
            if not chan:
                raise self.printer.command_error(
                    "No filament in the toolhead: load a slot first")
            # The IFS step leaves the head empty: load the slot it cut out
            self._set("Loading slot %d" % (chan,), .02)
            self._gcode("IFS_LOAD SLOT=%d" % (chan,))
        # PRINT_START applies the saved offset (and its prime line prints
        # with it): save the fresh start for it; abort puts z_saved back
        start_z = self.patch_start_z
        if params.get('ESTIMATE') and str(params['ESTIMATE']).strip() not in (
                '', '0'):
            start_z = self._estimate_start(nozzle)
        self._gcode('SAVE_VARIABLE VARIABLE=zoffset VALUE="%r"'
                    % ({'z': round(start_z, 4)},))
        self._set("Preparing like a print: home, heat to %.0f/%.0f C, "
                  "clean the nozzle, check Z" % (nozzle, bed), .05)
        # LEVEL=0: the centre Z check only. A mesh here probed the whole bed
        # (adaptive without exclude_object labels), which the test patch doesn't need.
        self._gcode("PRINT_START BED=%g EXTRUDER=%g LEVEL=0" % (bed, nozzle))
        self.z_start = self._zoffset()
        index = 0
        while True:
            self.state = "waiting_user"
            self._set("Test patch %d: press Closer until the lines touch and "
                      "flatten. Gaps or lifted edges: Closer. Squashed, "
                      "torn lines: Away" % (index + 1,), .5)
            for line in self._patch_gcode(index):
                self._apply_z_deltas()
                self._gcode(line)
            self._set("Check the patch: adjust and print another, or accept",
                      .9)
            end = self.reactor.monotonic() + self.user_timeout
            while not (self.z_accept or self.z_reprint):
                self._apply_z_deltas()
                if self.reactor.monotonic() > end:
                    self._set("No answer for %.0f min: keeping the offset"
                              % (self.user_timeout / 60.,))
                    break
                self._pause(.1)
            self._apply_z_deltas()
            if not self.z_reprint:
                break
            self.z_reprint = False
            index += 1
        # Keep it: SET_GCODE_OFFSET (ad5x.cfg's wrapper) saves zoffset
        self.state = "running"
        self._gcode("SET_GCODE_OFFSET Z=%.4f" % (self._zoffset(),))
        self._gcode("PRINT_END")
        saved = self._saved_zoffset()
        self._result("zoffset", "Z offset %.3f mm" % (
            saved if saved is not None else self._zoffset(),))
        self._set("Z offset saved", 1.)
    def _reload_channel(self):
        """Slot to load for the patch: the one IFS_TUNE unloaded, else
        T0's, if the IFS has filament there."""
        ifs = self.printer.lookup_object('ifs', None)
        if ifs is None:
            return 0
        st = ifs.get_status(self.reactor.monotonic())
        loaded = st.get('loaded_channels') or []
        for chan in (getattr(ifs, 'tune_unloaded', 0),
                     st.get('tool_map', {}).get('0', 0)):
            if chan and chan in loaded:
                return chan
        return loaded[0] if loaded else 0
    def _loaded_material(self):
        ifs = self.printer.lookup_object('ifs', None)
        if ifs is None or not ifs.channel:
            return None
        return ifs.materials[ifs.channel - 1].get('type')
    def _apply_z_deltas(self):
        while self.z_deltas:
            delta, self.z_deltas = self.z_deltas[0], self.z_deltas[1:]
            self._gcode("SET_GCODE_OFFSET Z_ADJUST=%.4f MOVE=1" % (delta,))
            self._set("Z offset %.3f mm" % (self._zoffset(),))
    def _patch_gcode(self, index):
        """One layer, patch_size square, lines along X, beside the last
        patch; a prime line in front of it. Ends lifted, parked behind."""
        ext = self._settings('extruder')
        nozzle = float(ext.get('nozzle_diameter', .4))
        fil = float(ext.get('filament_diameter', 1.75))
        h = round(min(.3, max(.2, nozzle * .5)), 2)
        w = round(nozzle * 1.125, 3)
        # Extruded line cross-section (rectangle with round ends)
        e_mm = ((w - h) * h + math.pi * (h / 2.) ** 2) / (
            math.pi * (fil / 2.) ** 2)
        dx, dy = PATCH_SPOTS[index % len(PATCH_SPOTS)]
        cx, cy = self.patch_center[0] + dx, self.patch_center[1] + dy
        size, f = self.patch_size, self.patch_speed
        x0, x1, y0 = cx - size / 2., cx + size / 2., cy - size / 2.
        lines = ["G90", "M83", "G1 Z5 F1200",
                 "G1 X%.2f Y%.2f F12000" % (x0, y0 - 5.),
                 "G1 Z%.2f F600" % (h,), "G1 E3 F300",
                 "G1 X%.2f E%.4f F%.0f" % (x1, size * e_mm * 1.5, f / 2.),
                 "G1 Y%.2f F%.0f" % (y0, f)]
        for i in range(int(size / w) + 1):
            if i:
                lines.append("G1 Y%.3f E%.5f F%.0f" % (
                    y0 + i * w, w * e_mm, f))
            lines.append("G1 X%.2f E%.5f F%.0f" % (
                x0 if i % 2 == 0 else x1, size * e_mm, f))
        lines += ["G1 E-1 F1800", "G1 Z%.2f F600" % (h + 10.),
                  "G1 X%.2f Y%.2f F12000" % (self.patch_center[0], 215.)]
        return lines
    def _estimate_start(self, nozzle):
        """Z offset from the load cells (Z_OFFSET_ESTIMATE, ad5x_zestimate):
        only when zoffset_estimate is on. The nozzle is hot first, as the
        estimate expects; the test patch then checks the result."""
        if not self.estimate_enabled:
            raise self.printer.command_error(
                "The Z offset estimate is off (zoffset_estimate: 1 in "
                "local.cfg, [ad5x_setup], once checked on this printer)")
        est = self.printer.lookup_object('ad5x_zestimate', None)
        if est is None:
            raise self.printer.command_error(
                "The Z offset estimate isn't in this image")
        self._set("Heating the nozzle for the estimate", .02)
        self._heat_and_wait({'extruder': nozzle}, (0., .05))
        self._set("Estimating the Z offset from the bed load cells", .06)
        self._gcode("Z_OFFSET_ESTIMATE")
        val = est.get_status(self.reactor.monotonic()).get('estimate')
        if val is None:
            raise self.printer.command_error(
                "The estimate gave no result: use the test patch")
        self._result("estimate", "%.3f mm" % (val,))
        self._gcode("G1 Z10 F3000")
        self._gcode_raw("SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0")
        return float(val)
    def _step_trash(self, params):
        """The purge box (trash bin): move there and check the nozzle is over
        it. TRASH_OFFSET X= Y= moves it (typed in the console for now);
        accept when it's right."""
        self._home()
        self.z_accept = False
        self._gcode("_TRASH_CHECK")
        self.state = "waiting_user"
        self._set("Is the nozzle over the purge box? If not, TRASH_OFFSET "
                  "X= Y=; then accept", .9)
        end = self.reactor.monotonic() + self.user_timeout
        while not self.z_accept:
            if self.reactor.monotonic() > end:
                self._set("No answer: keeping the purge box where it is")
                break
            self._pause(.1)
        self.state = "running"
        self._gcode("G1 Z10 F3000")
        self._result("trash", "box at X%.1f Y%.1f" % (
            52.5 + self._trash_offset()[0], 229. + self._trash_offset()[1]))
        self._set("Purge box checked", 1.)
    def _trash_offset(self):
        """(x, y) of the purge box from its factory spot: variables.cfg
        trash_offset (TRASH_OFFSET), else unit.cfg."""
        t = self._variables().get('trash_offset')
        if isinstance(t, dict) and 'x' in t and 'y' in t:
            return float(t['x']), float(t['y'])
        unit = self.printer.lookup_object('gcode_macro _AD5X_UNIT', None)
        if unit is None:
            return 0., 0.
        return float(unit.variables.get('x_offset', 0.)), float(
            unit.variables.get('y_offset', 0.))
    def _step_soak(self, params):
        """Bed heat soak calibration (BED_SOAK_CALIBRATE at 60 C, about 15
        minutes). Optional; starts from a cold bed, as the command requires.
        The Z offset step heats the bed, so a warm bed is cooled first (the
        heater off), not refused."""
        bed = self._heater('heater_bed')
        if self._temp(bed) > 40. and not int(params.get('FORCE', 0) or 0):
            self._gcode_raw("SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0")
            end = self.reactor.monotonic() + self.heat_timeout
            while self._temp(bed) > 40.:
                self._set("Waiting for the bed to cool below 40 C (now %.0f C)"
                          % (self._temp(bed),), 0.)
                if self.reactor.monotonic() > end:
                    raise self.printer.command_error(
                        "The bed did not cool below 40 C in time")
                self._pause(1.)
        self._set("Bed soak calibration at 60 C (about 15 minutes)", .05)
        self._gcode("BED_SOAK_CALIBRATE BED=60")
        self._gcode_raw("SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0")
        self._result("soak", "calibrated at 60 C")
        self._set("Bed soak calibrated", 1.)
    def _step_summary(self, params):
        """Nothing to run: the results so far, for review before Save."""
        done = [k for k in self.results if k != "summary"]
        self._result("summary", "%d step(s) done" % (len(done),))
        self._set("Review the results, then Save", 1.)
    def _step_finish(self, params):
        cf = self.printer.lookup_object('configfile')
        moved = {s: self._autosave(s) for s in TUNING_SECTIONS}
        moved = {s: v for s, v in moved.items() if v}
        if moved:
            self._set("Writing %s" % (os.path.basename(self.tuning_file),), .3)
            self._write_tuning(moved)
            for section in moved:
                cf.remove_section(section)
            warn = self._overridden(moved)
        else:
            warn = []
        fc = cf.autosave.fileconfig
        to_save = fc is not None and bool(fc.sections())
        if not moved and not to_save:
            self.pending_save = False
            self._result("finish", "nothing to save")
            self._set("Nothing to save", 1.)
            return
        note = "Saved; Klipper restarts"
        if warn:
            note += ". Not in effect, overridden by: " + "; ".join(warn)
        self._result("finish", note)
        self.pending_save = False
        self.state = "done"
        self._set(note, 1.)
        self._persist(True)
        # Both restart Klipper; the screen reconnects (state comes back
        # from variables.cfg: step finish, done)
        self._gcode("SAVE_CONFIG" if to_save else "RESTART")
    cmd_SAVE_CONFIG_help = ("Save calibration results; ad5x.cfg's values go "
                            "to the tuning file, a probe z_offset to the "
                            "saved Z offset")
    def cmd_SAVE_CONFIG(self, gcmd):
        """Klipper's SAVE_CONFIG refuses options an included file sets
        ("conflicts with included value"): ad5x.cfg's PID, input shaper
        and [probe] z_offset. PID_CALIBRATE / SHAPER_CALIBRATE results go
        to tuning_file (as the wizard's finish step does). A probe
        z_offset from PROBE_CALIBRATE or Z_OFFSET_APPLY_PROBE becomes the
        print Z offset (variables.cfg zoffset), which this system uses
        instead (probe z_offset stays ad5x.cfg's): the same first layer,
        offset = old z_offset - new z_offset."""
        cf = self.printer.lookup_object('configfile')
        probe = self._autosave('probe')
        if 'z_offset' in probe:
            old = float(self._settings('probe').get('z_offset', 0.))
            z = round(old - float(probe.pop('z_offset')), 4)
            cf.remove_section('probe')
            for opt, val in probe.items():
                cf.set('probe', opt, val)
            self.gcode.run_script_from_command(
                'SAVE_VARIABLE VARIABLE=zoffset VALUE="%r"\n'
                '_SET_GCODE_OFFSET Z=%.4f' % ({'z': z}, z))
            gcmd.respond_info("Z offset %.3f mm saved (the print Z offset; "
                              "[probe] z_offset stays %.3f)" % (z, old))
        moved = {s: self._autosave(s) for s in TUNING_SECTIONS}
        moved = {s: v for s, v in moved.items() if v}
        if moved:
            self._write_tuning(moved)
            for section in moved:
                cf.remove_section(section)
            msg = "%s saved to %s" % (", ".join(sorted(moved)),
                                      os.path.basename(self.tuning_file))
            warn = self._overridden(moved)
            if warn:
                msg += "; not in effect, overridden by: " + "; ".join(warn)
            gcmd.respond_info(msg)
        fc = cf.autosave.fileconfig
        if fc is not None and fc.sections():
            self.save_config(gcmd)
        elif moved:
            self.gcode.run_script_from_command("RESTART")
    def _write_tuning(self, moved):
        """Merge moved {section: {option: value}} into tuning_file."""
        sections = {}
        order = []
        try:
            with open(self.tuning_file) as f:
                section = None
                for line in f:
                    line = line.split('#', 1)[0].strip()
                    m = re.match(r"^\[([^]]+)\]$", line)
                    if m:
                        section = m.group(1).strip()
                        if section not in sections:
                            sections[section] = {}
                            order.append(section)
                    elif section and re.match(r"^[^:=]+[:=]", line):
                        key, val = re.split(r"[:=]", line, 1)
                        sections[section][key.strip()] = val.strip()
        except OSError:
            pass
        for section, opts in moved.items():
            if section not in sections:
                sections[section] = {}
                order.append(section)
            sections[section].update(opts)
        out = ["# Calibration results of the AD5X setup wizard",
               "# (SETUP_WIZARD_STEP STEP=finish). Included after the system",
               "# defaults (ad5x.cfg)",
               "# and before unit.cfg/local.cfg, which still win. Rewritten by",
               "# the next wizard run; delete a section to go back to the",
               "# defaults.", ""]
        for section in order:
            out.append("[%s]" % (section,))
            out += ["%s: %s" % kv for kv in sorted(sections[section].items())]
            out.append("")
        tmp = self.tuning_file + ".tmp"
        try:
            with open(tmp, "w") as f:
                f.write("\n".join(out))
            os.rename(tmp, self.tuning_file)
        except OSError as e:
            raise self.printer.command_error("Can't write %s: %s" % (
                self.tuning_file, e))
    def _overridden(self, moved):
        """Options in the printer's own config files (printer.cfg,
        unit.cfg, local.cfg) that would hide a moved value."""
        cfgdir = os.path.dirname(self.printer.get_start_args()['config_file'])
        found = []
        for name in ("printer.cfg", "unit.cfg", "local.cfg"):
            section = None
            try:
                with open(os.path.join(cfgdir, name)) as f:
                    lines = f.read().split("#*# <-")[0].splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.split('#', 1)[0].rstrip()
                m = re.match(r"^\[([^]]+)\]$", line.strip())
                if m:
                    section = m.group(1).strip()
                    continue
                m = re.match(r"^([A-Za-z0-9_]+)\s*[:=]", line)
                if m and section in moved \
                        and m.group(1).lower() in moved[section]:
                    found.append("%s [%s] %s" % (name, section,
                                                 m.group(1).lower()))
        return found
    def _request_wizard(self):
        """SETUP_WIZARD: leave the flag for the screen (S70helixscreen
        reads it at its next start) and tell a running screen."""
        try:
            with open(self.wizard_flag, "w") as f:
                f.write("requested by SETUP_WIZARD\n")
        except OSError as e:
            raise self.printer.command_error("Can't write %s: %s" % (
                self.wizard_flag, e))
        self.gcode.respond_info("action:ad5x_setup_wizard", log=False)
        return ("Setup wizard requested: the screen opens it now if it "
                "listens, else at its next start")

def load_config(config):
    return AD5XSetup(config)
