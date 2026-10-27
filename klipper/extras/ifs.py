# Support for the Flashforge AD5X IFS (4-channel filament switcher)
#
# Written from docs/ifs-protocol.md and docs/ifs-swap-sequence.md, which
# describe the IFS controller's behavior. No vendor code is used.
# Status fields, the ifs_materials object, save variable ifs_loaded and the
# IFS_LOAD/IFS_UNLOAD/IFS_EJECT/IFS_MAP_TOOL/IFS_SET_MATERIAL/IFS_STOP/
# IFS_RESET_DRIVER/IFS_FEED/IFS_RETRACT names follow the interface of the
# HelixScreen author's standalone IFS module (github.com/prestonbrown/ff5m,
# feat/ad5x-support, GPLv3), so HelixScreen's IFS panel works; see
# docs/helixscreen-integration.md. Interface and its material temperature
# table (MATERIAL_TEMPS) only; no code copied.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import colorsys
import logging
import math
import os
import re
import termios

CHANNELS = (1, 2, 3, 4)

# IFS controller state byte (F13 "FFS_state"). The controller accepts
# F10/F11/F39 only in STATE_READY and returns to it when a move finishes.
# TODO(phase4): confirm on the wire that every move ends back in STATE_READY.
STATE_READY = 5
STATE_FAULT = 0x7f     # a move faulted (stall); F15 clears it
STATE_HOMING = 0x7e    # stuck here = the IFS can't home (stock error E0114)

# Reply phrases that mean the command was refused.
REFUSALS = ("not ready", "not exist", "no channel selected", "no chan",
            "error")

BAUDS = {9600: termios.B9600, 57600: termios.B57600,
         115200: termios.B115200, 230400: termios.B230400}

# Board activity, decoded from FFS_state for printer.ifs.activity (the names
# HelixScreen's AD5X backend reads in "module" mode). Channel moves report
# base + 11 * (channel - 1). 3, 7, 11, 12, 15 and 127 are the values the
# HelixScreen author's standalone IFS module saw on the wire (FX:
# github.com/prestonbrown/ff5m, branch feat/ad5x-support,
# .py/klipper/plugins/ifs_status.py, GPLv3); 1, 10, 14 and 0x7e are the
# values F24/F10/F11 and a failed home set (docs/ifs-protocol.md).
ACTIVITY_STRIDE = 11
WHOLE_BOARD_ACTIVITY = {1: "selecting", 3: "polling", STATE_READY: "ready",
                        STATE_HOMING: "homing", STATE_FAULT: "driver_error"}
CHANNEL_ACTIVITY = {7: "clamped", 10: "loading", 11: "loading",
                    12: "unclamping", 14: "unloading", 15: "unloading"}

# Nozzle temperature to move each material at (handling, not printing),
# as FX's ifs_materials.py uses. Override or add with temp_<type> in [ifs].
MATERIAL_TEMPS = {"PLA": 220., "PLA-CF": 220., "SILK": 230., "TPU": 230.,
                  "ABS": 250., "PETG": 250., "PETG-CF": 250.}

# Tool map keys: slicer tools T0..T3.
TOOLS = (0, 1, 2, 3)

# Auto-refill colour matching (IFS_AUTO_REFILL MATCH=)
REFILL_MATCHES = ("exact", "similar", "any")
# Tool map: "fixed" = T0-T3 -> slots 1-4; "loaded" = tools use the slots that
# have filament, in slot order (one loaded slot: every tool uses it)
MAP_MODES = ("fixed", "loaded")

# print_stats states that end a print (and the tool map with it). Not
# "paused": the print resumes with the same map.
PRINT_END_STATES = ("complete", "cancelled", "error", "standby")

# Seconds between tries while the IFS is not answering (at start, or after
# the link drops, e.g. a loose cable). The link comes back by itself.
RECONNECT_INTERVAL = 10.

# Swap tuning (IFS_TUNE, QuickSwap-like; ideas from ninjamida/quickswap-5x,
# MIT, no code used). Feed speeds tried, in mm/min; the sweep starts at
# load_speed and stops at tune_max_speed.
TUNE_SPEEDS = (300., 600., 900., 1200., 1500., 1800., 2100., 2400., 2700.,
               3000.)
# Pull-backs tried for the tube test (mm past the point where the toolhead
# sensor clears), from stock's 70 down.
TUNE_TUBE_STEPS = (70., 50., 35., 25.)
# Save variables holding the tuned values (variables.cfg).
TUNE_VARS = ("ifs_speed", "ifs_unload_dist", "ifs_tube_unload",
             "ifs_flush") + tuple(
    "ifs_load_dist_%d" % (c,) for c in CHANNELS)

class IfsError(Exception):
    pass

def decode_activity(state):
    """FFS_state -> (activity name, channel or 0); (None, None) if unknown."""
    if state is None:
        return None, None
    if state in WHOLE_BOARD_ACTIVITY:
        return WHOLE_BOARD_ACTIVITY[state], 0
    for base, name in CHANNEL_ACTIVITY.items():
        off = state - base
        if off >= 0 and off % ACTIVITY_STRIDE == 0 \
                and off // ACTIVITY_STRIDE < len(CHANNELS):
            return name, off // ACTIVITY_STRIDE + 1
    return "unknown(%d)" % (state,), 0

def mask_channels(mask):
    """Bitmask (bit 0 = channel 1) -> list of 1-based channels."""
    return [c for c in CHANNELS if (mask or 0) >> (c - 1) & 1]

def parse_color(text):
    """'#RRGGBB', 'RRGGBB', '#RGB' or 'RGB' -> (r, g, b) 0..255, or None."""
    m = re.match(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", (text or "").strip())
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    v = int(digits, 16)
    return (v >> 16 & 0xff, v >> 8 & 0xff, v & 0xff)

def format_color(text):
    """Normalised '#RRGGBB', or None for an empty or invalid colour."""
    rgb = parse_color(text)
    return "#%02X%02X%02X" % rgb if rgb else None

def parse_material(text):
    """Material name (upper case) or None; raises ValueError if unusable.
    The stock UI writes '?' for an unset slot."""
    text = (text or "").strip()
    if text in ("", "?"):
        return None
    if not re.match(r"^[A-Za-z0-9+_.-]{1,16}$", text):
        raise ValueError(text)
    return text.upper()

def flush_volume(old, new):
    """Purge volume for a colour change, in the slicer's units (60..800).

    The published formula slicers use (Bambu Studio's flush volume
    calculator, also in OrcaSlicer), which the stock AD5X app uses too: hue
    and saturation distance in HSV, plus a brightness term that is larger
    when going from dark to light. old and new are (r, g, b) 0..255.
    """
    def hsv_xy(rgb):
        h, s, v = colorsys.rgb_to_hsv(*rgb)
        a = h * 2. * math.pi
        return v, v * s * math.cos(a), v * s * math.sin(a)
    def lum(rgb):
        return rgb[0] * .3 + rgb[1] * .59 + rgb[2] * .11
    src = [c / 255. for c in old]
    dst = [c / 255. for c in new]
    v1, x1, y1 = hsv_xy(src)
    v2, x2, y2 = hsv_xy(dst)
    hs_dist = math.hypot(x1 - x2, y1 - y2)
    l1, l2 = lum(src), lum(dst)
    if l2 >= l1:
        lumi_flush = (l2 - l1) ** .7 * 560.
    else:
        lumi_flush = (l1 - l2) * 80.
        hs_dist = min(.67 * v2 + .33 * v1, hs_dist)
    hs_flush = 230. * hs_dist
    # Third side of a triangle with a 120 degree angle between the two terms
    vol = math.sqrt(hs_flush ** 2 + lumi_flush ** 2
                    + hs_flush * lumi_flush)
    return 60 if vol < 60. else min(int(vol), 800)

def stock_color_quirk(rgb):
    """The colour the stock app actually feeds the formula: its call passes
    the bytes one place off (alpha=R, r=G, g=B, b=255), and a zero 'alpha'
    turns the colour white. Black to white comes out as 60 this way."""
    if rgb[0] == 0:
        return (255, 255, 255)
    return (rgb[1], rgb[2], 255)

def parse_fields(reply):
    """Parse 'key: value' pairs from a status reply into ints."""
    fields = {}
    for key, val in re.findall(r"([A-Za-z_]+):\s*([0-9A-Fa-f]+)", reply):
        base = 16 if key.endswith("GCONF") else 10
        try:
            fields[key] = int(val, base)
        except ValueError:
            pass
    return fields

def parse_counts(reply, key, count=None):
    """Parse 'key: a b ...' (one number per channel) from a reply."""
    count = len(CHANNELS) if count is None else count
    pat = key + r":\s*" + r"\s+".join([r"(-?\d+)"] * count)
    m = re.search(pat, reply)
    return [int(v) for v in m.groups()] if m else None

class IFS:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.name = config.get_name()
        # Link
        self.serial_port = config.get('serial', '/dev/ttyS4')
        self.baud = config.getint('baud', 115200)
        if self.baud not in BAUDS:
            raise config.error("ifs: unsupported baud %d" % (self.baud,))
        self.reply_timeout = config.getfloat('reply_timeout', 2., above=0.)
        self.poll_interval = config.getfloat('poll_interval', .5, above=0.)
        self.status_interval = config.getfloat('status_interval', 5.,
                                               minval=0.)
        # Moves (lengths and speeds in IFS units, see docs/ifs-protocol.md)
        self.load_length = config.getfloat('load_length', 1000., above=0.)
        self.load_speed = config.getfloat('load_speed', 1200., above=0.)
        self.unload_length = config.getfloat('unload_length', 60., above=0.)
        self.unload_speed = config.getfloat('unload_speed', 600., above=0.)
        self.backoff_length = config.getfloat('backoff_length', 50., above=0.)
        # After the unload clears the toolhead, stock pulls the strand back
        # further (F11 L70 S1200, "UnloadIFSSpace"). 0 turns it off.
        self.retract_length = config.getfloat('retract_length', 70., minval=0.)
        self.retract_speed = config.getfloat('retract_speed', 1200., above=0.)
        # Purge rounds per swap: each is push, release, purge_gcode, F23.
        # 0 = size from the two spool colours like stock: 2 rounds when the
        # flush volume is over purge_volume_threshold, else 1. Colours come
        # from IFS_SET_COLOR; with either colour unknown, 2 rounds. A load
        # into an empty toolhead gets 1, like stock.
        self.purge_rounds = config.getint('purge_rounds', 0, minval=0)
        self.purge_threshold = config.getint('purge_volume_threshold', 400,
                                             minval=0)
        # Reproduce the stock app's colour mix-up (see stock_color_quirk)
        self.stock_color_quirk = config.getboolean('stock_color_quirk', False)
        self.load_retries = config.getint('load_retries', 3, minval=0)
        # Toolhead filament sensor (an ADC registered with query_adc, value
        # 0..1). Stock reads filament as present when the value is at or
        # below 0.30 or at or above 0.72, empty in between. During a load the
        # module sends F112 (stop) as soon as it sees filament, as stock
        # does. Without it the load runs until the IFS finishes load_length.
        self.head_sensor = config.get('head_sensor', None)
        self.head_below = config.getfloat('head_sensor_present_below', .30,
                                          minval=0., maxval=1.)
        self.head_above = config.getfloat('head_sensor_present_above', .72,
                                          minval=0., maxval=1.)
        # First purge stage: the IFS and the extruder feed the same length
        # at the same speed (mm/min), so the new strand is pushed through
        # the hotend before the IFS releases it. 0 turns it off.
        self.push_length = config.getfloat('push_length', 90., minval=0.)
        self.push_speed = config.getfloat('push_speed', 300., above=0.)
        # Second purge stage: purge_gcode extrudes flush_length at
        # flush_speed (stock 90 mm at 300 mm/min). IFS_PURGE_TEST measures
        # the flush a colour change really needs (ifs_flush in
        # variables.cfg); with that, swaps purge one round of it.
        self.flush_length = config.getfloat('flush_length', 90., minval=0.)
        self.flush_speed = config.getfloat('flush_speed', 300., above=0.)
        # Pre-feed, as stock at power-on: each channel the IFS flags as
        # newly inserted is fed up to prefeed_length (stopped when the IFS
        # goes idle or the toolhead sensor sees it; then backed off
        # prefeed_backoff), acknowledged (F23) and released. Runs when
        # Klipper is ready and whenever the status poll sees a new spool,
        # never while printing. The loaded channel is only acknowledged.
        self.prefeed = config.getboolean('prefeed_on_insert', True)
        self.prefeed_length = config.getfloat('prefeed_length', 600.,
                                              above=0.)
        self.prefeed_speed = config.getfloat('prefeed_speed', 1200., above=0.)
        self.prefeed_backoff = config.getfloat('prefeed_backoff', 100.,
                                               minval=0.)
        # Eject (IFS_EJECT): pull a lane back out of the IFS for a spool
        # change. The IFS ends the move; TODO(phase4): measure the length.
        self.eject_length = config.getfloat('eject_length', 1000., above=0.)
        self.eject_speed = config.getfloat('eject_speed', 1200., above=0.)
        self.eject_timeout = config.getfloat('eject_timeout', 120., above=0.)
        # Heating for IFS_LOAD/IFS_UNLOAD/IFS_EJECT/IFS_SWAP when the nozzle
        # target is below [extruder] min_extrude_temp (idle, cold): the
        # slot material's temperature (MATERIAL_TEMPS, temp_<type>), else
        # default_temp. The old target is restored afterwards.
        self.default_temp = config.getfloat('default_temp', 220., above=0.)
        self.material_temps = dict(MATERIAL_TEMPS)
        for opt in config.get_prefix_options('temp_'):
            self.material_temps[opt[5:].upper()] = config.getfloat(
                opt, above=0.)
        # Swap tuning (IFS_TUNE). Tuned values live in variables.cfg and
        # replace the lengths/speeds above; without them nothing changes.
        # The head sensor is polled every sensor_poll seconds while a tuned
        # or measured feed runs (the ADC itself updates about every 0.3 s).
        self.sensor_poll = config.getfloat('sensor_poll', .05, above=0.)
        self.tune_max_speed = config.getfloat('tune_max_speed', 3000.,
                                              above=0.)
        # A tuned load feeds fast to this far short of the measured distance
        # (at least tune_load_margin mm, or 15 %), then at load_speed.
        self.tune_load_margin = config.getfloat('tune_load_margin', 20.,
                                                minval=0.)
        # Sensor-checked purge (not stock, off by default): one round; after
        # the push the extruder feeds purge_confirm mm in purge_step steps,
        # each checked against the head sensor, then purge_gcode flushes
        # purge_finish mm (params.FLUSH). Lengths scale with nozzle/0.4.
        self.sensor_purge = config.getboolean('sensor_purge', False)
        self.purge_step = config.getfloat('purge_step', 5., above=0.)
        self.purge_confirm = config.getfloat('purge_confirm', 15., minval=0.)
        self.purge_finish = config.getfloat('purge_finish', 15., minval=0.)
        # Swaps in a print whose slicer does the purge (zMod's
        # use_trash_on_print: 0 = prime tower, "nopoop"; 2 = the slicer's
        # own flush at the purge box; 1 = the printer purges, as stock).
        # purge_mode_variable names the save variable holding that mode
        # (the nopoop plugin sets it); unset, swaps always purge. Without a
        # purge a swap only primes: IFS and extruder feed prime_length past
        # the head sensor to fill the nozzle (zMod's 12 mm; QuickSwap's
        # insert_base_distance), then prime_gcode. IFS_SWAP PURGE=0|1 sets
        # it for one swap, in a print or not.
        self.purge_mode_variable = config.get('purge_mode_variable', None)
        # Auto-refill (not stock, off by default; Bambu's AMS "auto refill",
        # zMod's infinite spool): when the slot in use runs empty during a
        # print, the IFS still holds the old strand's tail, so the print
        # pauses, swaps to another slot with filament of the same material
        # and colour (refill_color_tolerance: RGB distance, 0-441) and
        # resumes. Slot types must be set (IFS_SET_MATERIAL or the screen).
        # The status poll runs every refill_poll s while printing, so the
        # tail is caught while the IFS still grips it. IFS_AUTO_REFILL
        # ENABLE=0|1 switches it (saved: ifs_auto_refill); MATCH= picks how
        # close the colour must be: exact (the same colour code), similar
        # (within refill_color_tolerance) or any (the material decides).
        self.auto_refill = config.getboolean('auto_refill', False)
        self.refill_color_tolerance = config.getfloat(
            'refill_color_tolerance', 40., minval=0.)
        self.refill_match = config.getchoice(
            'refill_match', {m: m for m in REFILL_MATCHES}, 'similar')
        self.refill_poll = config.getfloat('refill_poll', 1., above=0.)
        self.refill_busy = False
        self.refill_note = ""
        self.refill_warned = 0        # slot already reported as unmatched
        # Slots this print loaded without a backup, told once each
        self.refill_noticed = set()
        self.refill_notice = ""
        self.prime_length = config.getfloat('prime_length', 12., minval=0.)
        self.select_timeout = config.getfloat('select_timeout', 30., above=0.)
        self.load_timeout = config.getfloat('load_timeout', 60., above=0.)
        self.unload_timeout = config.getfloat('unload_timeout', 60., above=0.)
        self.release_timeout = config.getfloat('release_timeout', 30.,
                                               above=0.)
        # Machine-specific moves around a swap
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.gcode_macro = gcode_macro
        self.before_template = gcode_macro.load_template(
            config, 'before_gcode', '')
        self.cut_template = gcode_macro.load_template(config, 'cut_gcode', '')
        self.unload_template = gcode_macro.load_template(
            config, 'unload_gcode', '')
        self.purge_start_template = gcode_macro.load_template(
            config, 'purge_start_gcode', '')
        self.purge_template = gcode_macro.load_template(
            config, 'purge_gcode', '')
        self.prime_template = gcode_macro.load_template(
            config, 'prime_gcode', '')
        self.after_template = gcode_macro.load_template(
            config, 'after_gcode', '')
        self.abort_template = gcode_macro.load_template(
            config, 'abort_gcode', '')
        self.swap_open = None     # (old, new) between before_gcode and after_gcode
        # Runtime state
        self.fd = None
        self.fd_handle = None
        self.rx_buf = b""
        self.rx_lines = []
        self.rx_event = None
        self.mutex = self.reactor.mutex()
        self.status_timer = None
        self.retry_timer = None
        self.version = None
        self.channel = 0          # channel loaded to the toolhead, 0 = none
        # Per slot: material type, colour '#RRGGBB', temperature override
        self.materials = [{'type': None, 'color': None, 'temp': None}
                          for c in CHANNELS]
        self.tool_map = [c for c in CHANNELS]   # slicer tool n -> channel
        self.map_mode = "fixed"                 # see MAP_MODES
        self.last_status = {}
        self.silk = [0] * len(CHANNELS)
        self.stall = [0] * len(CHANNELS)
        self.busy = False
        self.error = None         # last failure, for printer.ifs.error
        self.stop_requested = False
        self.print_state = None
        # Swap heating: the target set by _heat, waited for (M109) just
        # before the first extruder move of the operation (_ensure_hot)
        self.heat_wait = None
        # Tuned values (None = use the [ifs] option) and tuning progress
        self.tuned = {'speed': None, 'unload_dist': None, 'tube_unload': None,
                      'flush': None,
                      'load_dist': [None for c in CHANNELS]}
        self.tune_progress = None     # 0..1 while IFS_TUNE runs
        self.first_swap_pending = False  # next swap in a print is its first
        self.tune_unloaded = 0        # lane the last IFS_TUNE cut out of the head
        self.tune_message = ""
        self.last_feed = 0.           # mm fed by the last measured feed
        # Events and commands
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        self.printer.register_event_handler("klippy:disconnect",
                                            self._handle_disconnect)
        self.printer.register_event_handler("klippy:ready",
                                            self._handle_ready)
        # Slot materials as their own status object (printer.ifs_materials),
        # the shape FX publishes and HelixScreen reads.
        self.printer.add_object('ifs_materials', IfsMaterials(self))
        for cmd in ("IFS_SEND", "IFS_STATUS", "IFS_SELECT", "IFS_FEED",
                    "IFS_RETRACT", "IFS_RELEASE", "IFS_RESET",
                    "IFS_RESET_DRIVER", "IFS_STOP", "IFS_SET_CURRENT",
                    "IFS_SWAP", "IFS_LOAD", "IFS_UNLOAD", "IFS_EJECT",
                    "IFS_MAP_TOOL", "IFS_SET_CHANNEL", "IFS_SET_COLOR",
                    "IFS_SET_MATERIAL", "IFS_MATERIALS", "IFS_PREFEED",
                    "IFS_TUNE", "IFS_TUNE_SPEED", "IFS_TUNE_LOAD",
                    "IFS_TUNE_UNLOAD", "IFS_TUNE_RESET", "IFS_SET_FLUSH",
                    "IFS_AUTO_REFILL", "IFS_MAP_MODE"):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        desc=getattr(self, "cmd_%s_help" % cmd))
    # Serial link
    def _handle_connect(self):
        self._load_variables()
        try:
            reply = self._connect_now()
            logging.info("ifs: connected on %s, %s", self.serial_port, reply)
        except (OSError, IfsError) as e:
            logging.warning("ifs: not available on %s: %s",
                            self.serial_port, e)
            self.error = "IFS not available on %s: %s" % (self.serial_port, e)
            self._close()
            self._schedule_reconnect()
            return
        self._start_status()
    def _connect_now(self):
        """Open the link and read the IFS version (F19). Raises OSError or
        IfsError; on success the link is up and self.version is set."""
        self._open()
        with self.mutex:
            reply = self._request("F19")
        self.version = reply.split("version:")[-1].strip(" .")
        return reply
    def _start_status(self):
        if self.status_interval and self.status_timer is None:
            self.status_timer = self.reactor.register_timer(
                self._status_event, self.reactor.NOW)
    def _schedule_reconnect(self):
        if self.retry_timer is None:
            self.retry_timer = self.reactor.register_timer(
                self._reconnect_event,
                self.reactor.monotonic() + RECONNECT_INTERVAL)
    def _reconnect_event(self, eventtime):
        try:
            reply = self._connect_now()
        except (OSError, IfsError) as e:
            self.error = "IFS not available on %s: %s" % (self.serial_port, e)
            self._close()
            return eventtime + RECONNECT_INTERVAL
        self.error = None
        self.retry_timer = None
        logging.info("ifs: reconnected on %s, %s", self.serial_port, reply)
        self._start_status()
        return self.reactor.NEVER
    def _drop_link(self, e):
        logging.warning("ifs: link lost on %s: %s", self.serial_port, e)
        self.error = "IFS link lost on %s: %s" % (self.serial_port, e)
        self._close()
        self._schedule_reconnect()
    def _load_variables(self):
        """Loaded channel and slot materials from save_variables.
        ifs_loaded (FX's name) replaced ifs_channel; ifs_materials replaced
        ifs_colors. The old variables are read when the new ones are absent."""
        sv = self.printer.lookup_object('save_variables', None)
        if sv is None:
            return
        v = sv.allVariables
        try:
            self.channel = int(v.get('ifs_loaded', v.get('ifs_channel', 0)))
        except (TypeError, ValueError):
            self.channel = 0
        if self.channel not in CHANNELS:
            self.channel = 0
        mats = v.get('ifs_materials')
        colors = v.get('ifs_colors')
        if isinstance(mats, (list, tuple)) and len(mats) == len(CHANNELS):
            for slot, m in zip(self.materials, mats):
                if not isinstance(m, dict):
                    continue
                try:
                    slot['type'] = parse_material(m.get('type'))
                except ValueError:
                    pass
                slot['color'] = format_color(m.get('color'))
                t = m.get('temp')
                slot['temp'] = float(t) if isinstance(t, (int, float)) \
                    and t > 0 else None
        elif isinstance(colors, (list, tuple)) and len(colors) == len(CHANNELS):
            for slot, c in zip(self.materials, colors):
                slot['color'] = format_color(c)
        # Tuned swap values (IFS_TUNE); missing or unusable = not tuned
        def num(name):
            val = v.get(name)
            if isinstance(val, (int, float)) and not isinstance(val, bool) \
                    and val > 0:
                return float(val)
            return None
        ar = v.get('ifs_auto_refill')
        if isinstance(ar, (bool, int)):
            self.auto_refill = bool(ar)
        rm = v.get('ifs_refill_match')
        if rm in REFILL_MATCHES:
            self.refill_match = rm
        mm = v.get('ifs_map_mode')
        if mm in MAP_MODES:
            self.map_mode = mm
        self.tuned = {
            'speed': num('ifs_speed'),
            'unload_dist': num('ifs_unload_dist'),
            'tube_unload': num('ifs_tube_unload'),
            'flush': num('ifs_flush'),
            'load_dist': [num('ifs_load_dist_%d' % (c,)) for c in CHANNELS]}
    def _save_variable(self, name, value):
        if self.printer.lookup_object('save_variables', None) is not None:
            self.gcode.run_script_from_command(
                "SAVE_VARIABLE VARIABLE=%s VALUE=\"%r\"" % (name, value))
    def _handle_disconnect(self):
        if self.retry_timer is not None:
            self.reactor.unregister_timer(self.retry_timer)
            self.retry_timer = None
        self._close()
    def _open(self):
        fd = os.open(self.serial_port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            attrs = termios.tcgetattr(fd)
            # Raw 8N1, no flow control
            attrs[0] = 0                                    # iflag
            attrs[1] = 0                                    # oflag
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag
            attrs[3] = 0                                    # lflag
            attrs[4] = attrs[5] = BAUDS[self.baud]
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            termios.tcflush(fd, termios.TCIOFLUSH)
        except termios.error:
            # A pty (fake IFS) accepts this; a real tty should too.
            pass
        self.fd = fd
        self.fd_handle = self.reactor.register_fd(fd, self._handle_read)
    def _close(self):
        if self.status_timer is not None:
            self.reactor.unregister_timer(self.status_timer)
            self.status_timer = None
        if self.fd_handle is not None:
            self.reactor.unregister_fd(self.fd_handle)
            self.fd_handle = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
    def _handle_read(self, eventtime):
        try:
            data = os.read(self.fd, 4096)
        except BlockingIOError:
            return
        except OSError as e:
            self._drop_link(e)
            return
        if not data:
            # Hang-up: a closed link reads as end-of-file, forever
            self._drop_link("end of file")
            return
        self.rx_buf += data
        *lines, self.rx_buf = self.rx_buf.split(b"\n")
        for line in lines:
            line = line.decode("ascii", "replace").strip()
            if line:
                self.rx_lines.append(line)
        if data and self.rx_event is not None:
            ev, self.rx_event = self.rx_event, None
            ev.complete(True)
    def _write(self, cmd):
        if self.fd is None:
            raise IfsError("IFS not connected")
        logging.debug("ifs: -> %s", cmd)
        try:
            os.write(self.fd, (cmd + "\r\n").encode("ascii"))
        except OSError as e:
            self._drop_link(e)
            raise IfsError("write failed: %s" % (e,))
    def _request(self, cmd):
        """Send one command and return its reply (caller holds the mutex).

        Replies start with 'F<n> ok'; multi-line ones (F21) arrive in one
        burst, so lines that follow within a short window are included.
        """
        prefix = cmd.split()[0] + " ok"
        self.rx_lines = []
        self.rx_buf = b""
        self._write(cmd)
        end = self.reactor.monotonic() + self.reply_timeout
        while True:
            # The IFS ends a reply without a line ending (F21 has \r\n only
            # between its lines): a reply is complete when the line goes
            # quiet, as the IFS firmware frames its own input.
            pending = self.rx_buf.decode("ascii", "replace").strip()
            lines = self.rx_lines + ([pending] if pending else [])
            for i, line in enumerate(lines):
                if line.startswith(prefix):
                    while True:
                        n = len(self.rx_buf) + len(self.rx_lines)
                        self.reactor.pause(self.reactor.monotonic() + .05)
                        if len(self.rx_buf) + len(self.rx_lines) == n:
                            break
                    pending = self.rx_buf.decode("ascii", "replace").strip()
                    lines = self.rx_lines + ([pending] if pending else [])
                    reply = " ".join(lines[i:])
                    self.rx_lines = []
                    self.rx_buf = b""
                    logging.debug("ifs: <- %s", reply)
                    return reply
            if self.reactor.monotonic() >= end:
                raise IfsError("no reply to %s" % (cmd,))
            self.rx_event = self.reactor.completion()
            self.rx_event.wait(end)
            self.rx_event = None
    def _command(self, cmd):
        reply = self._request(cmd)
        if any(r in reply.lower() for r in REFUSALS):
            raise IfsError("%s refused: %s" % (cmd, reply))
        return reply
    # Status
    def _query_status(self):
        st = parse_fields(self._request("F13"))
        if 'FFS_state' not in st:
            raise IfsError("bad F13 reply")
        self.last_status = st
        return st
    def _status_event(self, eventtime):
        if not self.busy and not self.mutex.test():
            with self.mutex:
                try:
                    self._query_status()
                    reply = self._request("F21")
                    self.silk = parse_counts(reply, "silk") or self.silk
                    self.stall = parse_counts(reply, "stall") or self.stall
                except IfsError as e:
                    logging.info("ifs: status poll failed: %s", e)
            self._prefeed_inserted(eventtime)
            self._check_refill(eventtime)
        if self.auto_refill and self._in_print():
            return eventtime + min(self.status_interval, self.refill_poll)
        return eventtime + self.status_interval
    def _handle_ready(self):
        if self.prefeed and self.fd is not None:
            self.reactor.register_callback(self._ready_prefeed)
        self.reactor.register_timer(self._watch_print, self.reactor.NOW)
    def _watch_print(self, eventtime):
        ps = self.printer.lookup_object('print_stats', None)
        if ps is not None:
            self._note_print_state(ps.get_status(eventtime).get('state'))
        return eventtime + 1.
    def _note_print_state(self, state):
        # The tool map belongs to one print (as FX): reset when it ends.
        ended = self.print_state == "printing" and state in PRINT_END_STATES
        if state == "printing" and self.print_state not in ("printing",
                                                            "paused"):
            # A new print (not a resume): its first tool load purges
            self.first_swap_pending = True
            self.refill_noticed = set()
            self.refill_notice = ""
            if self.map_mode == "loaded":
                self._map_loaded()
        self.print_state = state
        if ended and self.tool_map != list(CHANNELS):
            self.tool_map = list(CHANNELS)
            self.gcode.respond_info("IFS: print ended, tool map reset")
    def _ready_prefeed(self, eventtime):
        with self.mutex:
            try:
                self._query_status()
            except IfsError as e:
                logging.info("ifs: status at start failed: %s", e)
                return
        self._prefeed_inserted(eventtime)
    def _printing(self, eventtime):
        idle = self.printer.lookup_object('idle_timeout', None)
        return (idle is not None
                and idle.get_status(eventtime)['state'] == "Printing")
    def _prefeed_inserted(self, eventtime):
        """Pre-feed every channel flagged as newly inserted (stock does
        this at power-on)."""
        if (not self.prefeed or self.fd is None or self.busy
                or self.printer.is_shutdown() or self._printing(eventtime)):
            return
        inserted = self.last_status.get('ffs_channels_insert', 0)
        chans = [c for c in CHANNELS if inserted >> (c - 1) & 1]
        if not chans:
            return
        self.busy = True
        self.stop_requested = False
        try:
            with self.mutex:
                for chan in chans:
                    try:
                        if chan == self.channel:
                            # Loaded in the toolhead: feeding or backing it
                            # off would disturb the strand. Acknowledge only.
                            self._clear_inserted(chan)
                        else:
                            self._prefeed_channel(chan)
                    except IfsError as e:
                        logging.info("ifs: pre-feed channel %d failed: %s",
                                     chan, e)
                        self.gcode.respond_info(
                            "IFS: pre-feed channel %d failed: %s" % (chan, e))
                        try:
                            self._request("F15")
                        except IfsError:
                            pass
                        break
                self._query_status()
        finally:
            self.busy = False
    def _check_stop(self, what):
        if self.stop_requested:
            raise IfsError("%s stopped by IFS_STOP" % (what,))
    def _wait_ready(self, timeout, what):
        end = self.reactor.monotonic() + timeout
        while True:
            self._check_stop(what)
            st = self._query_status()
            if st['FFS_state'] == STATE_READY:
                return st
            now = self.reactor.monotonic()
            if now >= end:
                raise self._timeout_error(what, st)
            self.reactor.pause(now + self.poll_interval)
    def _timeout_error(self, what, st):
        if st['FFS_state'] == STATE_HOMING:
            return IfsError("%s: IFS homing error (E0114)" % (what,))
        return IfsError("%s timed out (state %d, stall %d)" % (
            what, st['FFS_state'], st.get('stall_state', 0)))
    def get_status(self, eventtime):
        # Cached values only: never touches the serial link or the toolhead.
        st = self.last_status
        inserted = st.get('ffs_channels_insert', 0)
        activity, activity_channel = decode_activity(st.get('FFS_state'))
        return {
            'connected': self.fd is not None,
            'version': self.version,
            'busy': self.busy,
            'channel': self.channel,
            'state': st.get('FFS_state'),
            'selected': st.get('chan'),
            'inserted': [bool(inserted >> (c - 1) & 1) for c in CHANNELS],
            'silk': list(self.silk),
            'stall': list(self.stall),
            'colors': self.colors,
            # FX "module" contract, read by HelixScreen
            'channel_count': len(CHANNELS),
            'active_channel': st.get('chan'),
            'loaded_channels': mask_channels(st.get('silk_state')),
            'pending_insert_channels': mask_channels(inserted),
            'activity': activity,
            'activity_channel': activity_channel,
            'error': self.error,
            'auto_refill': self.auto_refill,
            'map_mode': self.map_mode,
            'refill': self.refill_note,
            'refill_match': self.refill_match,
            'refill_backups': self._refill_backups(),
            'refill_notice': self.refill_notice,
            'tool_map': {str(t): self.tool_map[t] for t in TOOLS},
            # Swap tuning (not part of FX's contract): tuned values, None
            # where the [ifs] defaults apply; progress while IFS_TUNE runs
            'tune': {
                'speed': self.tuned['speed'],
                'load_dist': {str(c): self.tuned['load_dist'][c - 1]
                              for c in CHANNELS},
                'unload_dist': self.tuned['unload_dist'],
                'tube_unload': self.tuned['tube_unload'],
                'running': self.tune_progress is not None,
                'progress': self.tune_progress or 0.,
                'message': self.tune_message,
            },
        }
    @property
    def colors(self):
        return [m['color'] for m in self.materials]
    def _slot_temp(self, chan):
        m = self.materials[chan - 1]
        if m['temp']:
            return m['temp']
        return self.material_temps.get(m['type']) if m['type'] else None
    def _slot_status(self, chan):
        m = self.materials[chan - 1]
        return {'type': m['type'], 'color': m['color'],
                'temp': self._slot_temp(chan)}
    def materials_status(self):
        return {
            'available': True,
            'channel_count': len(CHANNELS),
            'slots': {str(c): self._slot_status(c) for c in CHANNELS},
            'loaded': self._slot_status(self.channel) if self.channel
                      else None,
            'temperatures': dict(self.material_temps),
        }
    def _save_materials(self):
        self._save_variable('ifs_materials', [dict(m) for m in self.materials])
    # Operations (caller holds the mutex)
    def _fmt(self, v):
        return "%g" % (v,)
    def _select(self, chan):
        self._command("F24 C%d" % (chan,))
        self._wait_ready(self.select_timeout, "select channel %d" % (chan,))
    def _head_has_filament(self):
        if self.head_sensor is None:
            return None
        qa = self.printer.lookup_object('query_adc', None)
        adc = qa.adc.get(self.head_sensor) if qa is not None else None
        if adc is None:
            raise IfsError("head_sensor '%s' is not a query_adc object" % (
                self.head_sensor,))
        value = adc.get_last_value()[1]
        return value <= self.head_below or value >= self.head_above
    def _wait_loaded(self, chan):
        """Wait for a load to reach the toolhead, then send F112 to stop
        the feed and return the IFS to ready."""
        what = "load channel %d" % (chan,)
        end = self.reactor.monotonic() + self.load_timeout
        while True:
            self._check_stop(what)
            st = self._query_status()
            head = self._head_has_filament()
            if head:
                break
            if st['FFS_state'] == STATE_FAULT:
                raise IfsError("%s faulted (stall %d)" % (
                    what, st.get('stall_state', 0)))
            if st['FFS_state'] == STATE_READY:
                if head is None:
                    break
                raise IfsError("%s: filament did not reach the toolhead"
                               % (what,))
            now = self.reactor.monotonic()
            if now >= end:
                raise self._timeout_error(what, st)
            self.reactor.pause(now + self.poll_interval)
        # Stop the feed. The IFS refuses only while a fault is latched.
        reply = self._request("F112")
        if "yes" not in reply:
            raise IfsError("F112 refused: %s" % (reply,))
        return self._wait_ready(self.select_timeout, what)
    def _load(self, chan, length, speed):
        if self._head_has_filament():
            # Not stock: loading into a toolhead that still holds filament
            # would end at once (the sensor already reads present) or jam.
            raise IfsError("load channel %d: the toolhead still has "
                           "filament in it" % (chan,))
        for attempt in range(self.load_retries + 1):
            try:
                if self._fast_load(chan):
                    return self.last_status
                self._command("F10 C%d L%s S%s" % (
                    chan, self._fmt(length), self._fmt(speed)))
                return self._wait_loaded(chan)
            except IfsError as e:
                if attempt >= self.load_retries:
                    raise
                # Stock recovery: reset, back the strand off, try again.
                logging.info("ifs: load retry after: %s", e)
                self._request("F15")
                self._command("F11 C%d L%s S%s" % (
                    chan, self._fmt(self.backoff_length),
                    self._fmt(self.unload_speed)))
                self._wait_ready(self.unload_timeout,
                                 "back off channel %d" % (chan,))
    def _fast_load(self, chan):
        """Tuned load, first part: feed at the tuned speed to a little short
        of the lane's measured distance to the toolhead sensor (stopping at
        once if the sensor sees filament earlier). True if the filament
        already reached the sensor; else the stock load does the rest."""
        dist = self.tuned['load_dist'][chan - 1]
        speed = self.tuned['speed'] or self.load_speed
        if not dist or self.head_sensor is None:
            return False
        length = dist - max(self.tune_load_margin, .15 * dist)
        if length <= 0. or speed <= self.load_speed:
            return False
        return self._feed_until_head(chan, length, speed,
                                     "fast load channel %d" % (chan,))
    def _feed_until_head(self, chan, length, speed, what):
        """F10 a lane and watch the head sensor closely: F112 as soon as it
        sees filament. True if it did, False if the IFS ended the move
        first. self.last_feed = mm fed (time x speed); errors raise."""
        start = self.reactor.monotonic()
        self.last_feed = 0.
        self._command("F10 C%d L%s S%s" % (
            chan, self._fmt(length), self._fmt(speed)))
        end = start + self.load_timeout
        next_query = start
        while True:
            self._check_stop(what)
            now = self.reactor.monotonic()
            self.last_feed = min(length, (now - start) * speed / 60.)
            if self._head_has_filament():
                reply = self._request("F112")
                if "yes" not in reply:
                    raise IfsError("F112 refused: %s" % (reply,))
                self._wait_ready(self.select_timeout, what)
                return True
            if now >= next_query:
                st = self._query_status()
                if st['FFS_state'] == STATE_FAULT:
                    raise IfsError("%s faulted (stall %d)" % (
                        what, st.get('stall_state', 0)))
                if st['FFS_state'] == STATE_READY and now > start:
                    self.last_feed = length
                    return False
                if now >= end:
                    raise self._timeout_error(what, st)
                next_query = now + self.poll_interval
            self.reactor.pause(now + self.sensor_poll)
    def _retract_until_clear(self, chan, length, speed, what):
        """F11 a lane until the head sensor clears (then F112). Returns the
        mm retracted (time x speed); raises if the sensor never clears."""
        start = self.reactor.monotonic()
        self._unload_start(chan, length, speed)
        end = start + self.unload_timeout
        next_query = start
        while True:
            self._check_stop(what)
            now = self.reactor.monotonic()
            if self._head_has_filament() is False:
                self._request("F112")
                self._wait_ready(self.unload_timeout, what)
                return min(length, (now - start) * speed / 60.)
            if now >= next_query:
                st = self._query_status()
                if st['FFS_state'] == STATE_FAULT:
                    raise IfsError("%s faulted (stall %d)" % (
                        what, st.get('stall_state', 0)))
                if st['FFS_state'] == STATE_READY and now > start:
                    if self._head_has_filament():
                        raise IfsError("%s: filament still in the toolhead"
                                       % (what,))
                    return length
                if now >= end:
                    raise self._timeout_error(what, st)
                next_query = now + self.poll_interval
            self.reactor.pause(now + self.sensor_poll)
    # Tuned values, or the [ifs] options
    def _unload_len(self):
        return self.tuned['unload_dist'] or self.unload_length
    def _tube_len(self):
        return self.tuned['tube_unload'] or self.retract_length
    def _tube_speed(self):
        return self.tuned['speed'] or self.retract_speed
    def _unload_start(self, chan, length, speed):
        self._command("F11 C%d L%s S%s" % (
            chan, self._fmt(length), self._fmt(speed)))
    def _release(self, chan):
        self._command("F39 C%d" % (chan,))
        self._wait_ready(self.release_timeout, "release channel %d" % (chan,))
    def _clear_inserted(self, chan):
        # Stock sends this after every purge: clears the channel's inserted
        # flag in the IFS. TODO(phase4): confirm why on the wire.
        self._command("F23 C%d" % (chan,))
    def _push(self, chan, length=None):
        # Extruder and IFS feed together; the extruder move is queued first
        # so both start within a lookahead flush of each other. length:
        # push_length, or prime_length for a swap without purge.
        toolhead = self.printer.lookup_object('toolhead')
        length = self.push_length if length is None else length
        self.gcode.run_script_from_command("M83\nG1 E%s F%s" % (
            self._fmt(length), self._fmt(self.push_speed)))
        self._command("F10 C%d L%s S%s" % (
            chan, self._fmt(length), self._fmt(self.push_speed)))
        toolhead.wait_moves()
        self._wait_ready(self.load_timeout, "purge push channel %d" % (chan,))
        self._request("F112")       # stock stops the feed after the push
    def _nozzle_scale(self):
        """Nozzle diameter / 0.4, for purge lengths (1 if unknown)."""
        cf = self.printer.lookup_object('configfile', None)
        try:
            settings = cf.get_status(self.reactor.monotonic())['settings']
            return float(settings['extruder']['nozzle_diameter']) / .4
        except (AttributeError, KeyError, TypeError, ValueError):
            return 1.
    def _sensor_purge(self, chan):
        """Sensor-checked purge (sensor_purge): with the IFS released, the
        extruder feeds purge_confirm mm in purge_step steps; before each
        step and at the end the head sensor must still see filament (a
        strand the extruder lost or that broke stops the swap here, not
        mid-print). Returns the finish length for purge_gcode."""
        toolhead = self.printer.lookup_object('toolhead')
        what = "purge channel %d" % (chan,)
        scale = self._nozzle_scale()
        total = self.purge_confirm * scale
        done = 0.
        while True:
            self._check_stop(what)
            if self._head_has_filament() is False:
                raise IfsError("%s: no filament at the toolhead sensor"
                               % (what,))
            if done >= total - 1e-6:
                break
            step = min(self.purge_step, total - done)
            self.gcode.run_script_from_command("M83\nG1 E%s F%s" % (
                self._fmt(round(step, 3)), self._fmt(self.push_speed)))
            toolhead.wait_moves()
            done += step
        return round(self.purge_finish * scale, 3)
    def _unload(self, chan, length=None):
        """Stock unload: select the old channel, pull it back while the
        extruder retracts (unload_gcode, params.LENGTH/SPEED), stop as soon
        as the toolhead is clear, then pull the strand further back (into
        the tube). Lengths are the tuned ones when IFS_TUNE saved them.
        Returns the mm pulled until the head sensor cleared, or None
        without a head sensor."""
        toolhead = self.printer.lookup_object('toolhead')
        what = "unload channel %d" % (chan,)
        length = length or self._unload_len()
        self._select(chan)
        self._run_template(self.unload_template, OLD=chan, NEW=0,
                           LENGTH=length, SPEED=self.unload_speed)
        cleared = None
        if self.head_sensor is not None:
            cleared = self._retract_until_clear(chan, length,
                                                self.unload_speed, what)
        else:
            self._unload_start(chan, length, self.unload_speed)
        toolhead.wait_moves()
        self._wait_ready(self.unload_timeout, what)
        tube = self._tube_len()
        if tube:
            self._unload_start(chan, tube, self._tube_speed())
            self._wait_ready(self.unload_timeout, what)
        return cleared
    def _prefeed_channel(self, chan):
        """Stock pre-feed of a new spool: F24, F10 L600 S1200, F112 when
        the IFS is done or the toolhead sensor sees filament (then F11
        L100 back off), F23, F39."""
        what = "pre-feed channel %d" % (chan,)
        logging.info("ifs: %s", what)
        # With another strand in the toolhead the sensor can't tell; then
        # only the IFS ends the feed.
        use_head = self._head_has_filament() is False
        self._select(chan)
        self._command("F10 C%d L%s S%s" % (
            chan, self._fmt(self.prefeed_length),
            self._fmt(self.prefeed_speed)))
        reached = False
        end = self.reactor.monotonic() + self.load_timeout
        while True:
            self._check_stop(what)
            st = self._query_status()
            if use_head and self._head_has_filament():
                reached = True
                break
            if st['FFS_state'] == STATE_FAULT:
                raise IfsError("%s faulted (stall %d)" % (
                    what, st.get('stall_state', 0)))
            if st['FFS_state'] == STATE_READY:
                break
            now = self.reactor.monotonic()
            if now >= end:
                raise self._timeout_error(what, st)
            self.reactor.pause(now + self.poll_interval)
        self._request("F112")
        self._wait_ready(self.select_timeout, what)
        if reached and self.prefeed_backoff:
            self._command("F11 C%d L%s S%s" % (
                chan, self._fmt(self.prefeed_backoff),
                self._fmt(self.prefeed_speed)))
            self._wait_ready(self.unload_timeout, what)
        self._clear_inserted(chan)
        self._release(chan)
    def _set_channel(self, chan):
        # ifs_loaded: the lane in the nozzle, 0 = none (FX's variable, read
        # by HelixScreen). Written once a load or unload has succeeded.
        self.channel = chan
        self._save_variable('ifs_loaded', chan)
        # For plugins (docs/plugin-api.md): the slot now in the nozzle
        self.printer.send_event("ifs:loaded", chan)
        self._refill_check_backup(chan)
    def _flush_volume(self, old, new):
        """Flush volume for a change from channel old to new, or None if
        either colour is unknown."""
        a = parse_color(self.colors[old - 1]) if old else None
        b = parse_color(self.colors[new - 1])
        if a is None or b is None:
            return None
        if self.stock_color_quirk:
            a, b = stock_color_quirk(a), stock_color_quirk(b)
        return flush_volume(a, b)
    def _purge_rounds(self, old, new):
        vol = self._flush_volume(old, new)
        if self.purge_rounds:
            return self.purge_rounds, vol
        if not old:
            # Nothing in the toolhead to flush out: stock compares the new
            # colour with itself here, the minimum, so 1 round.
            return 1, vol
        if vol is None:
            return 2, vol
        return (2 if vol > self.purge_threshold else 1), vol
    def _run_template(self, template, **params):
        context = self.gcode_macro.create_template_context()
        context['params'] = params
        template.run_gcode_from_command(context)
    def _abort_swap(self):
        """A swap failed after before_gcode ran: put back what it changed
        (abort_gcode). The Z lift stays: a blind move mid-print could hit the
        part. Errors here are logged, so the IFS error is what the user sees."""
        if self.swap_open is None:
            return
        old, new = self.swap_open
        self.swap_open = None
        try:
            self._run_template(self.abort_template, OLD=old, NEW=new)
        except Exception as e:
            logging.warning("ifs: abort_gcode failed: %s", e)
    def _run(self, func, *args, **kw):
        """Run an operation under the mutex, turning IFS errors into
        G-code errors after a best-effort controller reset. wait=False skips
        waiting for queued moves (for commands that don't move the toolhead
        and must work at any time: stop, reset)."""
        if kw.get('wait', True):
            toolhead = self.printer.lookup_object('toolhead')
            toolhead.wait_moves()
        self.busy = True
        self.stop_requested = False
        try:
            with self.mutex:
                try:
                    result = func(*args)
                except IfsError as e:
                    self.error = str(e)
                    try:
                        self._request("F15")
                    except IfsError:
                        pass
                    self._abort_swap()
                    raise self.gcode.error("IFS: %s" % (e,))
                self.error = None
                return result
        finally:
            self.busy = False
    def _require_homed(self):
        toolhead = self.printer.lookup_object('toolhead')
        status = toolhead.get_status(self.reactor.monotonic())
        if not all(a in status.get('homed_axes', '') for a in "xyz"):
            raise self.gcode.error("IFS: home the printer first (G28)")
    def _heat(self, gcmd, chans):
        """Make the nozzle hot enough to move filament. With TEMP= heat to
        that; otherwise only when the target is below min_extrude_temp
        (idle): to the hottest slot material of chans, else default_temp.
        Only sets the target (M104): the operation waits for it
        (_ensure_hot) just before its first extruder move, so the nozzle
        heats while the IFS selects and feeds (not stock: stock waits
        first). Returns the target to restore afterwards, or None."""
        extruder = self.printer.lookup_object('extruder', None)
        if extruder is None:
            return None
        heater = extruder.get_heater()
        target = heater.get_status(self.reactor.monotonic())['target']
        temp = gcmd.get_float('TEMP', None, minval=0., maxval=350.)
        if temp is None:
            if target >= heater.min_extrude_temp:
                return None
            temps = [self._slot_temp(c) for c in chans if c]
            temps = [t for t in temps if t]
            temp = max(temps) if temps else self.default_temp
        gcmd.respond_info("IFS: heating the nozzle to %.0f" % (temp,))
        self.gcode.run_script_from_command("M104 S%g" % (temp,))
        self.heat_wait = temp
        return target if target != temp else None
    def _ensure_hot(self):
        # Wait for the target _heat set, once, before an extruder move
        if self.heat_wait is not None:
            temp, self.heat_wait = self.heat_wait, None
            self.gcode.run_script_from_command("M109 S%g" % (temp,))
    def _restore_heat(self, target):
        self.heat_wait = None
        if target is not None:
            self.gcode.run_script_from_command("M104 S%g" % (target,))
    def _with_heat(self, gcmd, chans, func, *args):
        restore = self._heat(gcmd, chans)
        try:
            self._run(func, *args)
        finally:
            self._restore_heat(restore)
    def _get_channel(self, gcmd, name='CHANNEL'):
        return gcmd.get_int(name, minval=CHANNELS[0], maxval=CHANNELS[-1])
    # G-code commands
    cmd_IFS_SEND_help = "Send a raw command to the IFS and show the reply"
    def cmd_IFS_SEND(self, gcmd):
        cmd = gcmd.get('CMD').strip()
        if not re.match(r"^F\d+\b", cmd):
            raise gcmd.error("IFS_SEND: CMD must start with F<n>")
        gcmd.respond_info(self._run(self._request, cmd))
    cmd_IFS_STATUS_help = "Query and report IFS status"
    def cmd_IFS_STATUS(self, gcmd):
        # A query: no waiting for queued moves (screens poll this during a
        # print) and no controller reset on failure. While an operation
        # holds the link, report the last status instead (the background
        # poll holds it only for one exchange: wait for that).
        if self.busy or (self.mutex.test() and 'FFS_state' in self.last_status):
            st = self.last_status
            if 'FFS_state' not in st:
                raise gcmd.error("IFS: busy, no status yet")
        else:
            with self.mutex:
                try:
                    st = self._query_status()
                except IfsError as e:
                    raise gcmd.error("IFS: %s" % (e,))
        gcmd.respond_info("IFS %s: state %d (%s), selected %d, loaded %d, "
                          "filament in %s, inserted mask %d, stall %d" % (
                              self.version, st['FFS_state'],
                              decode_activity(st['FFS_state'])[0],
                              st.get('chan', 0), self.channel,
                              mask_channels(st.get('silk_state')),
                              st.get('ffs_channels_insert', 0),
                              st.get('stall_state', 0)))
    cmd_IFS_SELECT_help = "Point the IFS switch at a channel"
    def cmd_IFS_SELECT(self, gcmd):
        self._run(self._select, self._get_channel(gcmd))
    # Low-level moves (FX names: IFS_FEED / IFS_RETRACT)
    cmd_IFS_FEED_help = "Feed a channel toward the toolhead (raw IFS move)"
    def cmd_IFS_FEED(self, gcmd):
        chan = self._get_channel(gcmd)
        length = gcmd.get_float('LENGTH', self.load_length, above=0.)
        speed = gcmd.get_float('SPEED', self.load_speed, above=0.)
        self._run(self._load, chan, length, speed)
    cmd_IFS_RETRACT_help = "Retract a channel and wait for the IFS (raw move)"
    def cmd_IFS_RETRACT(self, gcmd):
        chan = self._get_channel(gcmd)
        length = gcmd.get_float('LENGTH', self.unload_length, above=0.)
        speed = gcmd.get_float('SPEED', self.unload_speed, above=0.)
        def retract():
            self._unload_start(chan, length, speed)
            self._wait_ready(self.unload_timeout, "retract channel %d" % chan)
        self._run(retract)
    cmd_IFS_RELEASE_help = "Release a channel's filament path"
    def cmd_IFS_RELEASE(self, gcmd):
        self._run(self._release, self._get_channel(gcmd))
    cmd_IFS_RESET_help = "Stop the IFS and return it to idle (F15)"
    def cmd_IFS_RESET(self, gcmd):
        self._run(self._request, "F15", wait=False)
    cmd_IFS_RESET_DRIVER_help = ("Recover the IFS after a fault (F15; same as "
                                 "IFS_RESET)")
    def cmd_IFS_RESET_DRIVER(self, gcmd):
        self._run(self._request, "F15", wait=False)
        gcmd.respond_info("IFS: driver reset")
    cmd_IFS_STOP_help = "Stop the IFS feeding (F112)"
    def cmd_IFS_STOP(self, gcmd):
        # Also ends a background pre-feed: its wait loop sees the flag.
        self.stop_requested = True
        if self.busy:
            gcmd.respond_info("IFS: stop requested")
            return
        reply = self._run(self._request, "F112", wait=False)
        gcmd.respond_info("IFS: stopped (%s)" % (reply,))
    cmd_IFS_SET_CURRENT_help = "Set IFS motor run current (0-31)"
    def cmd_IFS_SET_CURRENT(self, gcmd):
        motor = gcmd.get('MOTOR').lower()
        motors = {'feed': 1, 'switch': 2}
        if motor not in motors:
            raise gcmd.error("IFS_SET_CURRENT: MOTOR must be feed or switch")
        cur = gcmd.get_int('CURRENT', minval=0, maxval=31)
        gcmd.respond_info(self._run(self._command, "F42 T%d I%d" % (
            motors[motor], cur)))
    cmd_IFS_SET_CHANNEL_help = "Tell the module which channel is loaded"
    def cmd_IFS_SET_CHANNEL(self, gcmd):
        self._set_channel(gcmd.get_int('CHANNEL', minval=0,
                                       maxval=CHANNELS[-1]))
    # Slot materials
    cmd_IFS_SET_COLOR_help = "Set a channel's spool colour (#RRGGBB)"
    def cmd_IFS_SET_COLOR(self, gcmd):
        chan = self._get_channel(gcmd)
        color = gcmd.get('COLOR', '')
        if color and parse_color(color) is None:
            raise gcmd.error("IFS_SET_COLOR: COLOR must be #RRGGBB")
        self.materials[chan - 1]['color'] = format_color(color)
        self._save_materials()
    cmd_IFS_SET_MATERIAL_help = ("Set a slot's material: SLOT= TYPE= COLOR= "
                                 "(bare hex) TEMP=; absent = keep, "
                                 "empty = clear")
    def cmd_IFS_SET_MATERIAL(self, gcmd):
        slot = gcmd.get_int('SLOT', minval=CHANNELS[0], maxval=CHANNELS[-1])
        mtype = gcmd.get('TYPE', None)
        color = gcmd.get('COLOR', None)
        temp = gcmd.get('TEMP', None)
        if mtype is None and color is None and temp is None:
            raise gcmd.error("IFS_SET_MATERIAL needs TYPE=, COLOR= or TEMP=")
        m = dict(self.materials[slot - 1])
        if mtype is not None:
            try:
                m['type'] = parse_material(mtype)
            except ValueError:
                raise gcmd.error("IFS_SET_MATERIAL: bad TYPE '%s'" % (mtype,))
        if color is not None:
            if color.strip() and parse_color(color) is None:
                raise gcmd.error("IFS_SET_MATERIAL: COLOR must be RRGGBB "
                                 "or RGB hex")
            m['color'] = format_color(color)
        if temp is not None:
            try:
                t = float(temp) if temp.strip() else 0.
            except ValueError:
                raise gcmd.error("IFS_SET_MATERIAL: bad TEMP '%s'" % (temp,))
            if t and not 150. <= t <= 350.:
                raise gcmd.error("IFS_SET_MATERIAL: TEMP must be 150-350")
            m['temp'] = t or None
        self.materials[slot - 1] = m
        self._save_materials()
        st = self._slot_status(slot)
        gcmd.respond_info("IFS: slot %d: %s %s%s" % (
            slot, st['type'] or "(no type)", st['color'] or "(no colour)",
            " %.0fC" % st['temp'] if st['temp'] else ""))
    cmd_IFS_MATERIALS_help = "Report each slot's material"
    def cmd_IFS_MATERIALS(self, gcmd):
        lines = []
        for c in CHANNELS:
            st = self._slot_status(c)
            lines.append("slot %d: %s %s%s%s" % (
                c, st['type'] or "-", st['color'] or "-",
                " %.0fC" % st['temp'] if st['temp'] else "",
                " (loaded)" if c == self.channel else ""))
        gcmd.respond_info("\n".join(lines))
    # Auto-refill
    def _refill_candidates(self, chan, present):
        """The other slots with filament of chan's material and a matching
        colour (refill_match), the nearest colour first."""
        m = self.materials[chan - 1]
        if not m['type']:
            return []
        rgb = parse_color(m['color'])
        found = []
        for c in CHANNELS:
            if c == chan or c not in present:
                continue
            o = self.materials[c - 1]
            if o['type'] != m['type']:
                continue
            orgb = parse_color(o['color'])
            if self.refill_match == "any":
                d = 0.
            elif (rgb is None) != (orgb is None):
                continue
            else:
                d = 0. if rgb is None else math.sqrt(
                    sum((a - b) ** 2 for a, b in zip(rgb, orgb)))
                limit = (0. if self.refill_match == "exact"
                         else self.refill_color_tolerance)
                if d > limit:
                    continue
            found.append((d, c))
        return [c for d, c in sorted(found)]
    def _refill_target(self, chan, present):
        """Another slot with filament of the loaded slot's material and
        colour, the nearest colour first; None if there is none."""
        found = self._refill_candidates(chan, present)
        return found[0] if found else None
    def _refill_backups(self):
        """Per slot with filament: the slots that would take over if it
        ran out (printer.ifs.refill_backups, for the screen)."""
        present = mask_channels(self.last_status.get('silk_state'))
        return {str(c): self._refill_candidates(c, present) if c in present
                else [] for c in CHANNELS}
    def _refill_check_backup(self, chan):
        """A print loaded chan with auto-refill on and no backup for it:
        say so once per slot and print (printer.ifs.refill_notice). The
        print carries on; it pauses only if the slot really runs out."""
        if (not self.auto_refill or chan not in CHANNELS
                or chan in self.refill_noticed or not self._in_print()):
            return
        present = mask_channels(self.last_status.get('silk_state'))
        if self._refill_candidates(chan, present):
            return
        self.refill_noticed.add(chan)
        m = self.materials[chan - 1]
        what = " ".join(x for x in (m['type'], m['color']) if x)
        self.refill_notice = (
            "Auto-refill: slot %d%s has no backup spool. If it runs out, "
            "the print pauses for a reload." % (
                chan, " (%s)" % (what,) if what else ""))
        self.gcode.respond_info("IFS: " + self.refill_notice)
    def _check_refill(self, eventtime):
        """From the status poll: the loaded slot ran empty in a print."""
        chan = self.channel
        if (not self.auto_refill or not chan or self.refill_busy
                or self.busy or 'silk_state' not in self.last_status):
            return
        present = mask_channels(self.last_status['silk_state'])
        if chan in present:
            self.refill_warned = 0
            return
        ps = self.printer.lookup_object('print_stats', None)
        if ps is None or ps.get_status(eventtime).get('state') != "printing":
            return
        new = self._refill_target(chan, present)
        if new is None:
            if self.refill_warned != chan:
                self.refill_warned = chan
                self.refill_note = ("slot %d ran out, no other slot has the "
                                    "same filament" % (chan,))
                self.gcode.respond_info(
                    "IFS: slot %d ran out and no other slot has the same "
                    "material and colour: the print pauses when the "
                    "filament end reaches the toolhead" % (chan,))
            return
        self.refill_busy = True
        self.reactor.register_callback(
            lambda e, old=chan, new=new: self._do_refill(e, old, new))
    def _do_refill(self, eventtime, old, new):
        """Pause, swap old -> new, point the tools at the new slot, resume
        (as Klipper's runout handling: pause the file first)."""
        try:
            self.refill_note = "slot %d ran out: refilling from slot %d" % (
                old, new)
            self.gcode.respond_info("IFS: " + self.refill_note)
            pause_resume = self.printer.lookup_object('pause_resume', None)
            if pause_resume is not None:
                pause_resume.send_pause_command()
            script = ["PAUSE"]
            # A spool put in during the print wasn't pre-fed (never while
            # printing): pre-feed it now, paused, before loading it
            if self.last_status.get('ffs_channels_insert', 0) \
                    >> (new - 1) & 1:
                script.append("IFS_PREFEED CHANNEL=%d" % (new,))
            script.append("IFS_SWAP CHANNEL=%d" % (new,))
            for t in TOOLS:
                if self.tool_map[t] == old:
                    script.append("IFS_MAP_TOOL TOOL=%d SLOT=%d" % (t, new))
            script.append("RESUME")
            try:
                self.gcode.run_script("\n".join(script))
                self.refill_note = "slot %d ran out: continued with slot %d" % (
                    old, new)
            except Exception as e:
                logging.exception("ifs: auto-refill %d -> %d", old, new)
                self.refill_note = ("slot %d ran out: refill from slot %d "
                                    "failed: %s" % (old, new, e))
                self.gcode.respond_info("IFS: %s (print paused)"
                                        % (self.refill_note,))
        finally:
            self.refill_busy = False
    cmd_IFS_AUTO_REFILL_help = ("Auto-refill: a slot that runs out in a print "
                                "continues from a slot with the same filament:"
                                " [ENABLE=0|1] [MATCH=exact|similar|any]")
    def cmd_IFS_AUTO_REFILL(self, gcmd):
        enable = gcmd.get_int('ENABLE', None, minval=0, maxval=1)
        match = gcmd.get('MATCH', None)
        if match is not None:
            match = match.strip().lower()
            if match not in REFILL_MATCHES:
                raise gcmd.error("IFS_AUTO_REFILL: MATCH is one of %s"
                                 % (", ".join(REFILL_MATCHES),))
            self.refill_match = match
            self._save_variable('ifs_refill_match', match)
        if enable is not None:
            self.auto_refill = bool(enable)
            self._save_variable('ifs_auto_refill', self.auto_refill)
        backups = self._refill_backups()
        pairs = ["%s->%s" % (c, ",".join(str(b) for b in backups[c]))
                 for c in sorted(backups) if backups[c]]
        gcmd.respond_info("IFS: auto-refill %s, colour match %s%s; backups: "
                          "%s" % (
                              "on" if self.auto_refill else "off",
                              self.refill_match,
                              " (tolerance %.0f)" % self.refill_color_tolerance
                              if self.refill_match == "similar" else "",
                              " ".join(pairs) or "none"))
    # Tool map (per print, as FX)
    cmd_IFS_MAP_TOOL_help = ("Aim a slicer tool at a slot for this print: "
                             "TOOL= SLOT=, or RESET=1")
    def cmd_IFS_MAP_TOOL(self, gcmd):
        if gcmd.get_int('RESET', 0):
            self.tool_map = list(CHANNELS)
            gcmd.respond_info("IFS: tool map reset (T0-T3 -> slots 1-4)")
            return
        tool = gcmd.get_int('TOOL', minval=TOOLS[0], maxval=TOOLS[-1])
        slot = gcmd.get_int('SLOT', minval=CHANNELS[0], maxval=CHANNELS[-1])
        if 'silk_state' not in self.last_status:
            raise gcmd.error("IFS_MAP_TOOL: no IFS reading yet, can't check "
                             "slot %d for filament" % (slot,))
        if slot not in mask_channels(self.last_status['silk_state']):
            raise gcmd.error("IFS_MAP_TOOL: slot %d has no filament" % (slot,))
        self.tool_map[tool] = slot
        gcmd.respond_info("IFS: T%d -> slot %d" % (tool, slot))
    def _file_filaments(self):
        """(types, colours) per tool from the header or footer of the file
        printing now ('; filament_type' and '; filament_colour', as Orca and
        PrusaSlicer write them), so files made before this change work too.
        ([], []) when there is no file or it has no such lines."""
        vsd = self.printer.lookup_object('virtual_sdcard', None)
        path = vsd.file_path() if vsd is not None else None
        if not path:
            return [], []
        found = {}
        try:
            with open(path, 'r', errors='replace') as f:
                for line in f:
                    if not line.startswith(';'):
                        continue
                    key, sep, value = line[1:].partition('=')
                    key = key.strip()
                    if sep and key in ('filament_type', 'filament_colour'):
                        found[key] = [v.strip().strip('"')
                                      for v in value.split(';')]
        except OSError as e:
            logging.warning("ifs: cannot read %s for filament colours: %s",
                            path, e)
            return [], []
        return found.get('filament_type', []), found.get('filament_colour', [])
    def _match_slot(self, mtype, color, present):
        """The loaded slot for one tool's filament: a slot with the same
        material and the nearest colour; if no loaded slot has that material,
        the nearest colour of any loaded slot. None if nothing is loaded."""
        rgb = parse_color(color)
        def distance(chan):
            orgb = parse_color(self.materials[chan - 1]['color'])
            if rgb is None or orgb is None:
                return 441.     # unknown colour: no preference
            return math.sqrt(sum((a - b) ** 2 for a, b in zip(rgb, orgb)))
        same = [c for c in present
                if mtype and self.materials[c - 1]['type'] == mtype]
        pool = same or list(present)
        return min(pool, key=distance) if pool else None
    def _map_loaded(self):
        """Loaded-slot mode: each tool uses the loaded slot that matches its
        filament in the file (material, then nearest colour). Without file
        colours, tool t uses the (t mod n)th loaded slot in slot order. Returns
        the loaded slots; none loaded leaves the map as it is."""
        loaded = mask_channels(self.last_status.get('silk_state', 0))
        if not loaded:
            return loaded
        types, colours = self._file_filaments()
        new = []
        for t in TOOLS:
            fallback = loaded[t % len(loaded)]
            if t >= len(colours) and t >= len(types):
                new.append(fallback)
                continue
            try:
                mtype = parse_material(types[t]) if t < len(types) else None
            except ValueError:
                mtype = None
            color = colours[t] if t < len(colours) else None
            new.append(self._match_slot(mtype, color, loaded) or fallback)
        self.tool_map = new
        return loaded
    cmd_IFS_MAP_MODE_help = ("Tool map mode: fixed (T0-T3 -> slots 1-4) or "
                             "loaded (tools use the slots with filament)")
    def cmd_IFS_MAP_MODE(self, gcmd):
        mode = gcmd.get('MODE', None)
        if mode is not None:
            mode = mode.strip().lower()
            if mode not in MAP_MODES:
                raise gcmd.error("IFS_MAP_MODE: MODE is one of %s"
                                 % (", ".join(MAP_MODES),))
            self.map_mode = mode
            self._save_variable('ifs_map_mode', mode)
            if mode == "fixed":
                self.tool_map = list(CHANNELS)
            elif not self._map_loaded():
                gcmd.respond_info("IFS: no slot has filament; the map is "
                                  "applied at the next print")
        gcmd.respond_info("IFS: map mode %s; T0-T3 -> slots %s" % (
            self.map_mode, ",".join(str(c) for c in self.tool_map)))
    cmd_IFS_PREFEED_help = ("Feed a channel's new spool up to the IFS "
                            "(as stock does for a new spool)")
    def cmd_IFS_PREFEED(self, gcmd):
        chan = self._get_channel(gcmd)
        if chan == self.channel:
            raise gcmd.error("IFS_PREFEED: channel %d is loaded in the "
                             "toolhead" % (chan,))
        self._run(self._prefeed_channel, chan)
    # Full operations
    def _swap(self, old, new, flush=None, rounds=None, purge=True):
        toolhead = self.printer.lookup_object('toolhead')
        self._run_template(self.before_template, OLD=old, NEW=new)
        self.swap_open = (old, new)
        # Stock cuts only when the toolhead sensor shows filament. With
        # no sensor configured, trust the recorded channel.
        head = self._head_has_filament()
        if old and head is False:
            logging.info("ifs: toolhead empty, skipping cut of channel %d",
                         old)
            self._set_channel(0)
        elif old:
            # Cut at the toolhead (cut_gcode also moves to the purge
            # box), then unload the old strand there.
            self._ensure_hot()
            self._run_template(self.cut_template, OLD=old, NEW=new)
            toolhead.wait_moves()
            self._unload(old)
            self._set_channel(0)
        self._select(new)
        self._load(new, self.load_length, self.load_speed)
        if not purge:
            self._prime(old, new)
            self.swap_open = None
            return
        # Stock purge, in rounds: at the purge box, push the new strand
        # through the hotend (IFS and extruder together), release the
        # IFS, wipe and purge (purge_gcode), then F23.
        auto_rounds, vol = self._purge_rounds(old, new)
        # FLUSH=/ROUNDS= (IFS_PURGE_TEST), else the measured flush in one
        # round (it was measured for a hard change), else stock
        if flush is None and self.tuned['flush'] is not None:
            flush = self.tuned['flush']
            if rounds is None and not self.purge_rounds:
                rounds = 1
        if flush is None:
            flush = self.flush_length
        if rounds is None:
            rounds = auto_rounds
        if self.sensor_purge:
            rounds = 1
        logging.info("ifs: swap %d -> %d, flush volume %s, %d rounds of "
                     "%.0f mm", old, new, vol, rounds, flush)
        for rnd in range(1, rounds + 1):
            self._run_template(self.purge_start_template, OLD=old,
                               NEW=new, ROUND=rnd, ROUNDS=rounds)
            toolhead.wait_moves()
            self._ensure_hot()
            if self.push_length:
                self._push(new)
            self._release(new)
            self._set_channel(new)
            extra = {'FLUSH': flush, 'FLUSH_SPEED': self.flush_speed}
            if self.sensor_purge:
                extra['FLUSH'] = self._sensor_purge(new)
            self._run_template(self.purge_template, OLD=old, NEW=new,
                               ROUND=rnd, ROUNDS=rounds, **extra)
            toolhead.wait_moves()
            self._clear_inserted(new)
        self._run_template(self.after_template, OLD=old, NEW=new)
        self.swap_open = None
    def _prime(self, old, new):
        """Second half of a swap without purge (the slicer purges: prime
        tower or its own flush): at the purge box, feed the new strand
        prime_length into the nozzle (IFS and extruder together, as zMod's
        nopoop insert), release the IFS, prime_gcode, F23, after_gcode.
        Done at the box, not over the print (zMod primes over the print
        from layer 2 on), so the bead and any ooze stay off the part."""
        toolhead = self.printer.lookup_object('toolhead')
        logging.info("ifs: swap %d -> %d without purge, prime %.0f mm",
                     old, new, self.prime_length)
        self._run_template(self.purge_start_template, OLD=old, NEW=new,
                           ROUND=1, ROUNDS=1)
        toolhead.wait_moves()
        self._ensure_hot()
        if self.prime_length:
            self._push(new, self.prime_length)
        self._release(new)
        self._set_channel(new)
        self._run_template(self.prime_template, OLD=old, NEW=new)
        toolhead.wait_moves()
        self._clear_inserted(new)
        self._run_template(self.after_template, OLD=old, NEW=new)
    def _in_print(self):
        ps = self.printer.lookup_object('print_stats', None)
        return ps is not None and ps.get_status(
            self.reactor.monotonic()).get('state') == "printing"
    def _swap_purges(self, gcmd):
        """Whether a swap purges at the box: the first tool load of a print
        always does; else PURGE= if given; else, while a print runs and
        purge_mode_variable is set, its save variable (zMod
        use_trash_on_print: 0 and 2 = the slicer purges, anything else =
        purge); else purge."""
        purge = gcmd.get_int('PURGE', None, minval=0, maxval=1)
        if self.first_swap_pending and self._in_print():
            self.first_swap_pending = False
            if purge is None and self._purge_mode_says_slicer():
                # The slicer's prime tower on the bed does the purge, so the
                # first load only primes (no purge at the box). The colour
                # left in the nozzle goes into the bed purge instead.
                return False
            # Otherwise the first tool load purges in full at the box: the
            # prime tower doesn't exist yet, so the colour left in the nozzle
            # would go into the first layer (zMod purges it too).
            logging.info("ifs: first tool load of the print: purging")
            return True
        if purge is not None:
            return bool(purge)
        if not self.purge_mode_variable or not self._in_print():
            return True
        return not self._purge_mode_says_slicer()
    def _purge_mode_says_slicer(self):
        """purge_mode_variable's save variable is 0 or 2 (the slicer
        purges)."""
        if not self.purge_mode_variable:
            return False
        sv = self.printer.lookup_object('save_variables', None)
        mode = sv.allVariables.get(self.purge_mode_variable) \
            if sv is not None else None
        try:
            mode = int(mode)
        except (TypeError, ValueError):
            return False
        return mode in (0, 2)
    def _unload_toolhead(self, chan):
        """Nozzle contents back into the lane: the first half of a swap
        (cut, unload, pull back), then release the lane (as FX)."""
        toolhead = self.printer.lookup_object('toolhead')
        self._run_template(self.before_template, OLD=chan, NEW=0)
        if self._head_has_filament() is False:
            logging.info("ifs: toolhead empty, skipping cut of channel %d",
                         chan)
        else:
            self._ensure_hot()
            self._run_template(self.cut_template, OLD=chan, NEW=0)
            toolhead.wait_moves()
            self._unload(chan)
        self._set_channel(0)
        self._release(chan)
        self._run_template(self.after_template, OLD=chan, NEW=0)
    def _eject(self, chan):
        """Pull an idle lane out of the IFS (spool change), then release."""
        self._select(chan)
        self._unload_start(chan, self.eject_length, self.eject_speed)
        self._wait_ready(self.eject_timeout, "eject channel %d" % (chan,))
        self._release(chan)
    def _tool_change(self, gcmd, new):
        old = self.channel
        if new == old and not gcmd.get_int('FORCE', 0):
            if self._in_print():
                # The print's first tool is already in the nozzle (the
                # start purge cleared it): nothing left to purge
                self.first_swap_pending = False
            gcmd.respond_info("IFS: channel %d already loaded" % (new,))
            return
        flush = gcmd.get_float('FLUSH', None, minval=0.)
        rounds = gcmd.get_int('ROUNDS', None, minval=1, maxval=5)
        purge = self._swap_purges(gcmd)
        self._require_homed()
        self._with_heat(gcmd, (old, new), self._swap, old, new, flush, rounds,
                        purge)
    cmd_IFS_SWAP_help = ("Change to another IFS channel (cut, unload, load, "
                         "purge): CHANNEL= [TEMP=] [FLUSH=mm] [ROUNDS=] "
                         "[PURGE=0|1]")
    def cmd_IFS_SWAP(self, gcmd):
        self._tool_change(gcmd, self._get_channel(gcmd))
    cmd_IFS_LOAD_help = ("Load a slot into the nozzle, unloading the current "
                         "one first: SLOT= [TEMP=]")
    def cmd_IFS_LOAD(self, gcmd):
        self._tool_change(gcmd, self._get_channel(gcmd, 'SLOT'))
    cmd_IFS_UNLOAD_help = ("Take the filament out of the nozzle (cut, unload); "
                           "the lane stays threaded: [SLOT=] [TEMP=]")
    def cmd_IFS_UNLOAD(self, gcmd):
        slot = gcmd.get_int('SLOT', self.channel, minval=0,
                            maxval=CHANNELS[-1])
        if not slot:
            raise gcmd.error("IFS_UNLOAD: nothing loaded; give SLOT=")
        if self.channel and slot != self.channel:
            raise gcmd.error("IFS_UNLOAD: slot %d is not loaded (slot %d is)"
                             % (slot, self.channel))
        self._require_homed()
        self._with_heat(gcmd, (slot,), self._unload_toolhead, slot)
    cmd_IFS_EJECT_help = ("Pull a slot's filament out of the IFS (unloads "
                          "the nozzle first if it is the loaded one): SLOT=")
    def cmd_IFS_EJECT(self, gcmd):
        slot = self._get_channel(gcmd, 'SLOT')
        if slot == self.channel:
            self._require_homed()
            def unload_and_eject():
                self._unload_toolhead(slot)
                self._eject(slot)
            self._with_heat(gcmd, (slot,), unload_and_eject)
            return
        if not self.channel and self._head_has_filament():
            raise gcmd.error("IFS_EJECT: the toolhead holds filament from an "
                             "unknown slot; IFS_UNLOAD SLOT=n first")
        self._run(self._eject, slot)
    # Swap tuning (QuickSwap-like). Measures feed speed, each lane's
    # distance to the toolhead sensor and the unload length, from the head
    # sensor's timing (time x speed, so about +-5 mm at 1200 mm/min).
    # Results go to variables.cfg (TUNE_VARS) and replace the [ifs]
    # defaults in swaps. Caller holds the mutex (via _run).
    def _tune_note(self, progress, msg):
        self.tune_progress = max(0., min(1., progress))
        self.tune_message = msg
        logging.info("ifs: tune: %s", msg)
    def _save_tuned(self, key, var, value):
        if key == 'load_dist':
            self.tuned['load_dist'][int(var[-1]) - 1] = value
        else:
            self.tuned[key] = value
        self._save_variable(var, value)
    def _tune_park(self, chan, speed):
        """Pull a lane back from the toolhead sensor to where a swap's
        unload leaves it: until the sensor clears, then the tube
        pull-back."""
        what = "park channel %d" % (chan,)
        self._retract_until_clear(chan, self.load_length, speed, what)
        tube = self._tube_len()
        if tube:
            self._unload_start(chan, tube, speed)
            self._wait_ready(self.unload_timeout, what)
    def _tune_run(self, chan, speed):
        """Feed a lane from where it rests up to the head sensor, then park
        it again. Returns the distance fed (mm)."""
        what = "channel %d at %g mm/min" % (chan, speed)
        if not self._feed_until_head(chan, self.load_length, speed, what):
            raise IfsError("%s: filament did not reach the toolhead"
                           % (what,))
        dist = self.last_feed
        self._tune_park(chan, speed)
        return dist
    def _tune_recover(self, chan):
        """After a failed tuning feed: clear the fault and pull back what
        was fed (best effort)."""
        fed = self.last_feed
        try:
            self._request("F15")
            self._wait_ready(self.select_timeout, "recover channel %d"
                             % (chan,))
            if self._head_has_filament():
                self._tune_park(chan, self.load_speed)
            elif fed > 0.:
                self._unload_start(chan, fed, self.unload_speed)
                self._wait_ready(self.unload_timeout, "recover channel %d"
                                 % (chan,))
        except IfsError as e:
            logging.info("ifs: tune: recovery of channel %d: %s", chan, e)
    def _tune_speed(self, chan, prog):
        """Feed one lane at rising speeds from load_speed up, 2 runs each;
        stop at the first failure (fault, no sensor) or slip (the feed
        takes 20 % longer than at load_speed). Returns one step below the
        fastest speed that worked (margin)."""
        speeds = [v for v in TUNE_SPEEDS
                  if self.load_speed < v <= self.tune_max_speed]
        speeds.insert(0, self.load_speed)
        ref = best = None
        for i, speed in enumerate(speeds):
            self._tune_note(prog[0] + (prog[1] - prog[0]) * i / len(speeds),
                            "slot %d: feeding at %g mm/min" % (chan, speed))
            try:
                dists = [self._tune_run(chan, speed) for run in range(2)]
            except IfsError as e:
                if self.stop_requested:
                    raise
                logging.info("ifs: tune: %g mm/min failed: %s", speed, e)
                self._tune_recover(chan)
                break
            if ref is None:
                ref = min(dists)
            elif max(dists) > ref * 1.2 + 10.:
                logging.info("ifs: tune: %g mm/min slips (%s mm, %.1f at "
                             "%g)", speed, dists, ref, speeds[0])
                break
            best = i
        if best is None:
            raise IfsError("slot %d does not feed reliably at %g mm/min"
                           % (chan, speeds[0]))
        return speeds[max(0, best - 1)]
    def _tune_load(self, chan, speed, settle):
        """Distance from a lane's parked position (after a swap's unload)
        to the head sensor: the shorter of 2 runs. settle: one run first,
        to get the lane from wherever it rests to the parked position."""
        self._select(chan)
        if settle:
            self._tune_run(chan, speed)
        return min(self._tune_run(chan, speed) for run in range(2))
    def _tune_unload(self, chan):
        """A real unload of the loaded lane (cut, pull until the head
        sensor clears, tube pull-back), measured. Returns the mm it took
        to clear the sensor."""
        toolhead = self.printer.lookup_object('toolhead')
        self._run_template(self.before_template, OLD=chan, NEW=0)
        self._ensure_hot()
        self._run_template(self.cut_template, OLD=chan, NEW=0)
        toolhead.wait_moves()
        # Longer than needed: the sensor ends it
        cleared = self._unload(chan, length=1.5 * max(self.unload_length,
                                                      self._unload_len()))
        self._set_channel(0)
        self._release(chan)
        self._run_template(self.after_template, OLD=chan, NEW=0)
        return cleared
    def _tune_tube(self, chan, other, speed):
        """Shortest pull-back after the head sensor clears that still lets
        another lane feed past the point where the lanes merge: tried from
        the current pull-back down (TUNE_TUBE_STEPS); a blocked merge shows
        as a fault or a slow feed. Returns the shortest that worked plus
        10 mm, at most the current one."""
        base = self._tube_len()
        steps = [base] + [t for t in TUNE_TUBE_STEPS if t < base]
        expect = best = None
        last = base
        for t in steps:
            what = "tube test, slot %d pulled back %g mm" % (chan, t)
            self._tune_note(self.tune_progress or 0., what)
            self._select(chan)
            if not self._feed_until_head(chan, self.load_length, speed, what):
                raise IfsError("%s: filament did not reach the toolhead"
                               % (what,))
            self._retract_until_clear(chan, self.load_length, speed, what)
            self._unload_start(chan, t, speed)
            self._wait_ready(self.unload_timeout, what)
            last = t
            self._select(other)
            try:
                if not self._feed_until_head(other, self.load_length, speed,
                                             what):
                    raise IfsError("slot %d did not reach the toolhead"
                                   % (other,))
                if expect is None:
                    expect = self.last_feed
                elif self.last_feed > expect * 1.2 + 10.:
                    raise IfsError("slot %d fed slowly (blocked?)" % (other,))
            except IfsError as e:
                if self.stop_requested:
                    raise
                logging.info("ifs: tune: %s: %s", what, e)
                self._tune_recover(other)
                break
            self._tune_park(other, speed)
            best = t
        # Back to a pull-back that works for the lane tested
        if best is not None and last < best:
            self._select(chan)
            self._unload_start(chan, best - last, speed)
            self._wait_ready(self.unload_timeout, "park channel %d" % (chan,))
        if best is None:
            raise IfsError("slot %d blocks slot %d even pulled back %g mm"
                           % (chan, other, base))
        return min(best + 10., base)
    def _tune_all(self, chans, do_speed, do_load, do_unload, do_tube):
        """IFS_TUNE: measured unload of the loaded lane (do_unload), then
        with the toolhead empty: speed on the first lane, load distance of
        each, tube test with the first two (do_tube). Lanes are released
        at the end, as after a pre-feed."""
        try:
            self._tune_note(0., "starting")
            if do_unload and self.channel \
                    and self._head_has_filament() is not False:
                self._tune_note(.02, "measuring the unload of slot %d"
                                % (self.channel,))
                cleared = self._tune_unload(self.channel)
                if cleared is not None:
                    self._save_tuned('unload_dist', 'ifs_unload_dist',
                                     float(math.ceil(cleared + 10.)))
            if self._head_has_filament():
                raise IfsError("the toolhead holds filament; unload it first "
                               "(IFS_UNLOAD)")
            speed = self.tuned['speed'] or self.load_speed
            first = chans[0]
            if do_speed:
                self._tune_note(.1, "slot %d: settling" % (first,))
                self._select(first)
                self._tune_run(first, self.load_speed)
                speed = self._tune_speed(first, (.1, .5))
                self._save_tuned('speed', 'ifs_speed', speed)
            if do_load:
                for i, chan in enumerate(chans):
                    self._tune_note(.5 + .35 * i / len(chans),
                                    "slot %d: measuring the load distance"
                                    % (chan,))
                    dist = self._tune_load(chan, speed, settle=not (
                        do_speed and chan == first))
                    self._save_tuned('load_dist', 'ifs_load_dist_%d' % (chan,),
                                     round(dist, 1))
            if do_tube and len(chans) >= 2:
                self._tune_note(.85, "tube test with slots %d and %d"
                                % (chans[0], chans[1]))
                self._save_tuned('tube_unload', 'ifs_tube_unload',
                                 self._tune_tube(chans[0], chans[1], speed))
            for chan in chans:
                self._release(chan)
            self._tune_note(1., "done: " + self._tune_summary())
        finally:
            self.tune_progress = None
    def _tune_summary(self):
        t = self.tuned
        dists = ["%d: %.0f mm" % (c, t['load_dist'][c - 1]) for c in CHANNELS
                 if t['load_dist'][c - 1]]
        return ("speed %s; load %s; unload %s; tube pull-back %s; "
                "flush %s" % (
            "%.0f mm/min" % t['speed'] if t['speed'] else "default",
            ", ".join(dists) or "default",
            "%.0f mm" % t['unload_dist'] if t['unload_dist'] else "default",
            "%.0f mm" % t['tube_unload'] if t['tube_unload'] else "default",
            "%.0f mm" % t['flush'] if t['flush'] else "default"))
    def _tune_channels(self, gcmd):
        """CHANNEL=, else every slot with filament in the IFS (fresh F13)."""
        if self.fd is None:
            raise gcmd.error("IFS: not connected")
        if self.head_sensor is None:
            raise gcmd.error("IFS tuning needs the toolhead sensor "
                             "(head_sensor in [ifs])")
        ps = self.printer.lookup_object('print_stats', None)
        if ps is not None and ps.get_status(self.reactor.monotonic()).get(
                'state') in ("printing", "paused"):
            raise gcmd.error("IFS tuning: not during a print")
        st = self._run(self._query_status, wait=False)
        loaded = mask_channels(st.get('silk_state'))
        chan = gcmd.get_int('CHANNEL', 0, minval=0, maxval=CHANNELS[-1])
        if chan:
            if chan not in loaded:
                raise gcmd.error("IFS tuning: slot %d has no filament"
                                 % (chan,))
            return [chan]
        if not loaded:
            raise gcmd.error("IFS tuning: no filament in any slot")
        return loaded
    def _tune_cmd(self, gcmd, do_speed, do_load, do_unload, do_tube):
        chans = self._tune_channels(gcmd)
        if do_tube and len(chans) < 2:
            if gcmd.get_int('TUBE', 0):
                raise gcmd.error("IFS tuning: the tube test needs two slots "
                                 "with filament")
            do_tube = False
        unload = do_unload and self.channel \
            and self._head_has_filament() is not False
        if unload:
            # A real unload: cut and extruder move, so homed and hot. Only
            # for that part: feeding to the head sensor needs no heat.
            self._require_homed()
            self.tune_unloaded = self.channel
            self._with_heat(gcmd, (self.channel,), self._tune_all, chans,
                            False, False, True, False)
        self._run(self._tune_all, chans, do_speed, do_load, False, do_tube)
        gcmd.respond_info("IFS tuning saved: " + self._tune_summary())
    cmd_IFS_TUNE_help = ("Tune swaps (QuickSwap-like): unload length, feed "
                         "speed, each slot's load distance; saved in "
                         "variables.cfg. [CHANNEL=] [SPEED=1] [LOAD=1] "
                         "[UNLOAD=1] [TUBE=0] [TEMP=]")
    def cmd_IFS_TUNE(self, gcmd):
        self._tune_cmd(gcmd, gcmd.get_int('SPEED', 1), gcmd.get_int('LOAD', 1),
                       gcmd.get_int('UNLOAD', 1), gcmd.get_int('TUBE', 0))
    cmd_IFS_TUNE_SPEED_help = ("Find the fastest reliable IFS feed speed on "
                               "a slot: [CHANNEL=]")
    def cmd_IFS_TUNE_SPEED(self, gcmd):
        self._tune_cmd(gcmd, True, False, False, False)
    cmd_IFS_TUNE_LOAD_help = ("Measure each slot's distance to the toolhead "
                              "sensor: [CHANNEL=]")
    def cmd_IFS_TUNE_LOAD(self, gcmd):
        self._tune_cmd(gcmd, False, True, False, False)
    cmd_IFS_TUNE_UNLOAD_help = ("Measure the unload length (cuts and unloads "
                                "the loaded slot; with CHANNEL= and nothing "
                                "loaded, loads it first); TUBE=1 also tests "
                                "the tube pull-back with two slots")
    def cmd_IFS_TUNE_UNLOAD(self, gcmd):
        chan = gcmd.get_int('CHANNEL', 0, minval=0, maxval=CHANNELS[-1])
        tube = gcmd.get_int('TUBE', 0)
        if not self.channel or self._head_has_filament() is False:
            if not chan:
                raise gcmd.error("IFS_TUNE_UNLOAD: nothing loaded; give "
                                 "CHANNEL= to load a slot first")
            # Load it the normal way (purges), then measure its unload
            self._tool_change(gcmd, chan)
        if tube:
            self._tune_cmd(gcmd, False, False, True, True)
        else:
            self._tune_cmd(gcmd, False, False, True, False)
    cmd_IFS_SET_FLUSH_help = ("Save the flush length a colour change needs "
                              "(from IFS_PURGE_TEST): LENGTH=mm, or RESET=1")
    def cmd_IFS_SET_FLUSH(self, gcmd):
        if gcmd.get_int('RESET', 0):
            self._save_tuned('flush', 'ifs_flush', None)
            gcmd.respond_info("IFS: flush back to %.0f mm (flush_length), "
                              "rounds from the colours" % (self.flush_length,))
            return
        length = gcmd.get_float('LENGTH', minval=1., maxval=400.)
        self._save_tuned('flush', 'ifs_flush', round(length, 1))
        gcmd.respond_info("IFS: swaps purge one round: push %.0f mm, then "
                          "flush %.1f mm at %.0f mm/min" % (
                              self.push_length, length, self.flush_speed))
    cmd_IFS_TUNE_RESET_help = ("Forget the IFS_TUNE values (back to the "
                               "[ifs] defaults)")
    def cmd_IFS_TUNE_RESET(self, gcmd):
        for key in ('speed', 'unload_dist', 'tube_unload', 'flush'):
            self.tuned[key] = None
        self.tuned['load_dist'] = [None for c in CHANNELS]
        for var in TUNE_VARS:
            self._save_variable(var, None)
        gcmd.respond_info("IFS: tuning reset, swaps use the [ifs] values")

class IfsMaterials:
    """printer.ifs_materials: per-slot type, colour and temperature."""
    def __init__(self, ifs):
        self.ifs = ifs
    def get_status(self, eventtime):
        return self.ifs.materials_status()

def load_config(config):
    return IFS(config)
