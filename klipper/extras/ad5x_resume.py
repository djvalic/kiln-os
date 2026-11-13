# Power-loss recovery: resume a print that a power cut (or a crash) ended
#
# While a print from the virtual SD card runs, its state is written every
# `interval` seconds (only when the file has moved on) to `state_file`,
# always between two G-code lines so that the file position, the G-code
# state and the toolhead's position belong together:
#   file and byte position, G-code position and offsets, coordinate modes,
#   speed and flow factors, feed rate, heater targets, part fan, pressure
#   advance, velocity limits, the bed mesh in use, the toolhead position
#   (bed mesh applied: the real Z), the IFS slot and tool map.
# A print that completes or is cancelled removes the file. One that ends
# any other way (power cut, shutdown, error) leaves it, and after the next
# start `printer.ad5x_resume.available` is true.
#
# RESUME_INTERRUPTED CONFIRM=1 continues it. The nozzle must still be over
# the print where it stopped (the Z axis holds its position without power;
# don't move the bed or the toolhead in between):
#   heat the bed; Z is set to where it stopped (no Z homing: that would
#   probe into the print), lifted, X and Y homed; the bed mesh, offsets,
#   limits, pressure advance and IFS state restored; the nozzle heated,
#   moved above the resume point and lowered; the file continues from the
#   saved position (moves of up to `interval` seconds are printed again).
# CLEAR_INTERRUPTED forgets it.
#
# [ad5x_resume]
# state_file: /home/klipper/printer_data/print_resume.json
# interval: 10          # seconds between saves while printing
# lift: 5               # mm Z lift before homing X and Y
# prime: 3              # mm extruded before continuing
#
# Written for Kiln OS (AD5X). This file may be distributed under the terms
# of the GNU GPLv3 license.
import json
import logging
import os
import time

FORMAT = 1


class Ad5xResume:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.state_file = os.path.expanduser(config.get(
            'state_file', '/home/klipper/printer_data/print_resume.json'))
        self.interval = config.getfloat('interval', 10., minval=1.)
        self.lift = config.getfloat('lift', 5., minval=0.)
        self.prime = config.getfloat('prime', 3., minval=0.)
        self.saved = None          # state of an interrupted print
        self.last_pos = None       # file position of the last save
        self.last_state = None     # print_stats state seen last
        self.resuming = False
        self.timer = None
        self.printer.register_event_handler("klippy:ready", self._ready)
        for cmd, desc in (
                ("RESUME_INTERRUPTED", "Continue the print a power cut "
                 "ended: CONFIRM=1 (the nozzle must still be where it "
                 "stopped)"),
                ("CLEAR_INTERRUPTED", "Forget the interrupted print")):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        desc=desc)

    # --- state file ---------------------------------------------------------
    def _load(self):
        try:
            with open(self.state_file) as f:
                st = json.load(f)
            if st.get('format') == FORMAT and st.get('file'):
                return st
        except (OSError, ValueError):
            pass
        return None

    def _write(self, st):
        tmp = self.state_file + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(st, f)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp, self.state_file)
        except OSError as e:
            logging.info("ad5x_resume: can't save %s: %s",
                         self.state_file, e)

    def _remove(self):
        self.saved = None
        try:
            os.unlink(self.state_file)
        except OSError:
            pass

    # --- recording ----------------------------------------------------------
    def _ready(self):
        self.saved = self._load()
        if self.saved is not None:
            self.gcode.respond_info(
                "Interrupted print: %s at Z %.2f (%s). RESUME_INTERRUPTED "
                "CONFIRM=1 continues it, CLEAR_INTERRUPTED forgets it." % (
                    os.path.basename(self.saved['file']),
                    self.saved['gcode_position'][2],
                    time.strftime("%Y-%m-%d %H:%M",
                                  time.localtime(self.saved['time']))))
        self.timer = self.reactor.register_timer(self._tick,
                                                 self.reactor.NOW)

    def _tick(self, eventtime):
        try:
            self._check(eventtime)
        except Exception:
            logging.exception("ad5x_resume")
        return eventtime + (1. if self.last_state == "printing"
                            else self.interval)

    def _check(self, eventtime):
        ps = self.printer.lookup_object('print_stats')
        state = ps.get_status(eventtime)['state']
        prev, self.last_state = self.last_state, state
        if state in ("complete", "cancelled") and prev != state:
            self._remove()
            self.last_pos = None
            return
        if state != "printing":
            return
        vsd = self.printer.lookup_object('virtual_sdcard')
        if vsd.is_cmd_from_sd() or not vsd.is_active():
            return      # inside a line (a macro, a wait): try again soon
        pos = vsd.get_status(eventtime)['file_position']
        if pos == self.last_pos:
            return
        if (self.last_pos is not None and self.saved_at is not None
                and eventtime - self.saved_at < self.interval):
            return
        st = self.snapshot(eventtime)
        if st is None:
            return
        self._write(st)
        self.saved = None       # this print's file replaces an older one
        self.last_pos = pos
        self.saved_at = eventtime
    saved_at = None

    def snapshot(self, eventtime):
        lookup = self.printer.lookup_object
        vsd = lookup('virtual_sdcard')
        path = vsd.file_path()
        if not path:
            return None
        gm = lookup('gcode_move').get_status(eventtime)
        toolhead = lookup('toolhead')
        th = toolhead.get_status(eventtime)
        heaters = {}
        for name in ('extruder', 'heater_bed'):
            obj = lookup(name, None)
            if obj is not None:
                heaters[name] = obj.get_status(eventtime)['target']
        ext = lookup('extruder', None)
        pa = None
        if ext is not None:
            es = ext.get_status(eventtime)
            pa = [es.get('pressure_advance'), es.get('smooth_time')]
        fan = lookup('fan_generic fanM106', None) or lookup('fan', None)
        mesh = None
        bm = lookup('bed_mesh', None)
        if bm is not None and bm.get_mesh() is not None:
            zm = bm.get_mesh()
            mesh = {'name': bm.get_status(eventtime).get('profile_name') or
                    "resume", 'params': zm.get_mesh_params(),
                    'points': zm.get_probed_matrix()}
        ifs = lookup('ifs', None)
        ifs_st = None
        if ifs is not None:
            s = ifs.get_status(eventtime)
            ifs_st = {'channel': ifs.channel,
                      'tool_map': [s['tool_map'][str(t)] for t in range(4)]}
        return {
            'format': FORMAT,
            'time': time.time(),
            'file': path,
            'position': vsd.get_status(eventtime)['file_position'],
            'gcode_position': list(gm['gcode_position']),
            'homing_origin': list(gm['homing_origin']),
            'absolute_coordinates': gm['absolute_coordinates'],
            'absolute_extrude': gm['absolute_extrude'],
            'speed_factor': gm['speed_factor'],
            'extrude_factor': gm['extrude_factor'],
            'speed': gm['speed'],
            'toolhead_position': list(toolhead.get_position()[:3]),
            'axis_maximum': list(th['axis_maximum'])[:3],
            'velocity': [th['max_velocity'], th['max_accel'],
                         th['square_corner_velocity'],
                         th.get('minimum_cruise_ratio')],
            'heaters': heaters,
            'pressure_advance': pa,
            'fan': fan.get_status(eventtime)['speed'] if fan else 0.,
            'mesh': mesh,
            'ifs': ifs_st,
        }

    def get_status(self, eventtime):
        s = self.saved
        return {
            'available': s is not None,
            'file': os.path.basename(s['file']) if s else "",
            'z': s['gcode_position'][2] if s else 0.,
            'time': s['time'] if s else 0.,
        }

    # --- resuming -----------------------------------------------------------
    def resume_script(self, st, sd_path):
        """The G-code that continues saved state st (a list of lines)."""
        f = lambda v: "%.4f" % (v,)
        tx, ty, tz = st['toolhead_position']
        gx, gy, gz, ge = st['gcode_position']
        ox, oy, oz = st['homing_origin'][:3]
        maxz = st['axis_maximum'][2]
        lift = max(0., min(self.lift, maxz - tz - 1.))
        bed = st['heaters'].get('heater_bed', 0.)
        nozzle = st['heaters'].get('extruder', 0.)
        out = []
        if bed:
            out.append("M190 S%s" % f(bed))
        # Z where the print stopped (bed mesh included), X/Y as they were
        out.append("SET_KINEMATIC_POSITION X=%s Y=%s Z=%s" % (
            f(tx), f(ty), f(tz)))
        out += ["G90", "G1 Z%s F600" % f(tz + lift)]
        # Back off a pressed Y endstop here (_HOME_ZXY would set Z to 0)
        out += ["QUERY_ENDSTOPS", "_AD5X_RESUME_Y_BACKOFF", "G28 X", "G28 Y"]
        mesh = st.get('mesh')
        if mesh:
            out.append("_AD5X_RESUME_MESH")
        else:
            out.append("BED_MESH_CLEAR")
        out.append("SET_GCODE_OFFSET X=%s Y=%s Z=%s" % (f(ox), f(oy), f(oz)))
        v = st['velocity']
        lim = "SET_VELOCITY_LIMIT VELOCITY=%s ACCEL=%s " \
              "SQUARE_CORNER_VELOCITY=%s" % (f(v[0]), f(v[1]), f(v[2]))
        if v[3] is not None:
            lim += " MINIMUM_CRUISE_RATIO=%s" % (f(v[3]),)
        out.append(lim)
        pa = st.get('pressure_advance')
        if pa and pa[0] is not None:
            out.append("SET_PRESSURE_ADVANCE ADVANCE=%s SMOOTH_TIME=%s" % (
                f(pa[0]), f(pa[1])))
        ifs = st.get('ifs')
        # Saved with Kiln's IFS module, resumed with it off (a plugin that
        # drives the IFS was enabled since): no IFS_SET_CHANNEL to send
        if ifs and self.printer.lookup_object('ifs', None) is not None:
            out.append("IFS_SET_CHANNEL CHANNEL=%d" % (ifs['channel'],))
        if nozzle:
            out.append("M109 S%s" % f(nozzle))
        # Above the resume point, prime, then down onto it
        out += ["G90", "G1 X%s Y%s F6000" % (f(gx), f(gy)),
                "M83", "G1 E%s F300" % f(self.prime),
                "G1 Z%s F600" % f(gz)]
        if st['absolute_extrude']:
            out += ["M82", "G92 E%s" % f(ge)]
        else:
            out.append("M83")
        if not st['absolute_coordinates']:
            out.append("G91")
        out += ["M220 S%s" % f(st['speed_factor'] * 100.),
                "M221 S%s" % f(st['extrude_factor'] * 100.),
                "M106 S%d" % round(st['fan'] * 255.),
                "G1 F%s" % f(st['speed'] * 60.)]
        rel = os.path.relpath(st['file'], sd_path)
        # (M23 only finds files at the top of the gcodes folder)
        out += ["_AD5X_RESUME_SELECT FILE=\"%s\"" % (rel,),
                "M26 S%d" % (st['position'],), "M24"]
        return out

    def cmd_RESUME_INTERRUPTED(self, gcmd):
        st = self.saved or self._load()
        if st is None:
            raise gcmd.error("RESUME_INTERRUPTED: no interrupted print")
        ps = self.printer.lookup_object('print_stats')
        if ps.get_status(self.reactor.monotonic())['state'] in (
                "printing", "paused"):
            raise gcmd.error("RESUME_INTERRUPTED: a print is running")
        if not os.path.isfile(st['file']) or \
                os.path.getsize(st['file']) < st['position']:
            raise gcmd.error("RESUME_INTERRUPTED: %s is gone or changed"
                             % (st['file'],))
        if not gcmd.get_int('CONFIRM', 0):
            gcmd.respond_info(
                "RESUME_INTERRUPTED: %s at Z %.2f, byte %d. The bed must not "
                "have moved and the nozzle must still be over the print. "
                "RESUME_INTERRUPTED CONFIRM=1 to continue." % (
                    os.path.basename(st['file']), st['gcode_position'][2],
                    st['position']))
            return
        vsd = self.printer.lookup_object('virtual_sdcard')
        self.pending = st
        script = self.resume_script(st, vsd.sdcard_dirname)
        logging.info("ad5x_resume: %s", "\n".join(script))
        gcmd.respond_info("Resuming %s from Z %.2f" % (
            os.path.basename(st['file']), st['gcode_position'][2]))
        self.gcode.run_script_from_command("\n".join(script))
    pending = None

    def restore_mesh(self):
        """_AD5X_RESUME_MESH: the bed mesh of the interrupted print (an
        adaptive mesh isn't a saved profile)."""
        st = self.pending
        mesh = st and st.get('mesh')
        if not mesh:
            return
        from . import bed_mesh
        zm = bed_mesh.ZMesh(mesh['params'], mesh['name'])
        zm.build_mesh(mesh['points'])
        self.printer.lookup_object('bed_mesh').set_mesh(zm)

    def cmd_CLEAR_INTERRUPTED(self, gcmd):
        self._remove()
        gcmd.respond_info("Interrupted print forgotten")


def load_config(config):
    obj = Ad5xResume(config)
    gcode = obj.gcode

    def mesh(gcmd):
        obj.restore_mesh()

    def backoff(gcmd):
        q = obj.printer.lookup_object('query_endstops', None)
        last = q.get_status(0.)['last_query'] if q else {}
        if last.get('stepper_y'):
            gcode.run_script_from_command("G91\nG1 Y-20 F600\nG90")
    def select(gcmd):
        vsd = obj.printer.lookup_object('virtual_sdcard')
        vsd._reset_file()
        vsd._load_file(gcmd, gcmd.get('FILE'), check_subdirs=True)
    gcode.register_command("_AD5X_RESUME_SELECT", select)
    gcode.register_command("_AD5X_RESUME_MESH", mesh)
    gcode.register_command("_AD5X_RESUME_Y_BACKOFF", backoff)
    return obj
