# The printer's editable macros (macros/*.cfg in the config directory):
# update notices and the backups of edited files
#
# The macros/ files are copied from the image's templates
# (/usr/share/ad5x/defaults/macros) by the boot script ad5x-config-templates
# (S05ad5x-data). When an update brings a changed template, that script
# replaces the printer's file; an edited one is first kept as
# <name>.cfg.bak-<date> and a line is added to config-updates.txt in the
# config directory (docs/config-layout.md). This module tells the user:
# at Klipper start the notice lines go to the console (and a short message
# to the screen) while that file exists; CONFIG_BACKUPS lists the notices
# and the backup files, CONFIG_BACKUPS ACK=1 removes the notice (backups
# stay until deleted in Fluidd).
#
# One mesh and one prime line per print (issue #73). PRINT_START meshes
# the print area and draws the prime line; a slicer start G-code written
# for KAMP calls BED_MESH_CALIBRATE and LINE_PURGE (or VORON_PURGE) again
# after it. At Klipper start this module wraps these commands, whoever
# defines them (Kiln's macros, zmod-compat's, or KAMP's from local.cfg,
# which replace Kiln's sections: same name, read later). While a print
# runs, a call after that step (gcode_macro _KILN_START_DONE, ad5x.cfg:
# PRINT_START's mesh and prime line note it, and so does any of these
# commands that ran during the print) is skipped with a console line
# saying why and how to change it. FORCE=1 runs it anyway;
# BED_MESH_CALIBRATE with PROFILE= or ADAPTIVE=0 (a mesh asked for by
# name, or the whole bed) always runs; outside a print nothing is
# skipped. Loading a new file (virtual_sdcard:reset_file) forgets the
# marks. Also at start: a warning (Fluidd's and Mainsail's
# Klipper warnings, and the console) when another config replaced Kiln's
# BED_MESH_CALIBRATE, or brings a LINE_PURGE while Kiln's prime line is
# on, naming the file that set its gcode.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import glob
import logging
import os
import re

CONFIG_DIR = "/home/klipper/printer_data/config"
NOTICE_FILE = "config-updates.txt"
BACKUP_RE = re.compile(r"^(?P<name>.+\.cfg)\.bak-(?P<stamp>[0-9-]+)$")
# Config file lines as Klipper's reader sees them (configparser)
SECTION_RE = re.compile(r"\[(?P<header>.+)\]")
OPTION_RE = re.compile(r"(?P<key>[^:=\s][^:=]*?)\s*[:=]")
# The macro that marks the print start's steps, and its variable for each
# guarded command
MARKS = "gcode_macro _KILN_START_DONE"
STEP = {'BED_MESH_CALIBRATE': 'mesh', 'LINE_PURGE': 'line',
        'VORON_PURGE': 'line'}
SOMEWHERE = "another config (for example KAMP's %s)"
# Comments as Klipper's reader cuts them: '#' anywhere, ';' at the line
# start or after a space (configparser's comment and inline prefixes)
COMMENT_RE = re.compile(r"#.*|(?:^|(?<=\s));.*")


def skipped_message(cmd, mesh_owner=None):
    """The console line for a skipped cmd; mesh_owner: the file whose
    BED_MESH_CALIBRATE replaced Kiln's, if one did."""
    if cmd == 'BED_MESH_CALIBRATE':
        msg = ("BED_MESH_CALIBRATE skipped: PRINT_START already meshed the"
               " bed for this print (Kiln OS, issue #73). ")
        if mesh_owner:
            msg += (
                "This BED_MESH_CALIBRATE comes from %s: remove that include"
                " (Kiln's PRINT_START meshes the print area itself) rather"
                " than setting variable_mesh_every_print: 0, as with it no"
                " full mesh saves the centre Z, so the stock Z check"
                " compares against an old one or stops with \"no saved"
                " centre Z\". " % (mesh_owner,))
        else:
            msg += ("To have the slicer's mesh instead, set"
                    " variable_mesh_every_print: 0 under"
                    " [gcode_macro PRINT_START] in local.cfg, or remove"
                    " BED_MESH_CALIBRATE from the slicer's start G-code."
                    " With KAMP's Adaptive_Meshing.cfg included, remove that"
                    " include instead: with its BED_MESH_CALIBRATE no full"
                    " mesh saves the centre Z, and the stock Z check stops"
                    " with \"no saved centre Z\" (or uses an old one). ")
        return msg + "BED_MESH_CALIBRATE FORCE=1 meshes anyway."
    return ("%s skipped: this print already has its purge line (PRINT_START's"
            " prime line, or a purge line run earlier in the print; Kiln OS,"
            " issue #73). To have this purge line instead of the prime line,"
            " set variable_prime_line: 0 under [gcode_macro _PRIME_LINE] in"
            " local.cfg, or remove %s from the slicer's start G-code."
            " %s FORCE=1 draws it anyway." % (cmd, cmd, cmd))


def config_origins(path, section, visited=None):
    """The files, in the order Klipper reads them from path (includes
    followed as Klipper does: relative to the including file, patterns
    sorted), whose [section] sets a gcode option. The last one is the
    gcode Klipper uses."""
    if visited is None:
        visited = set()
    path = os.path.abspath(path)
    if path in visited:
        return []
    visited.add(path)
    try:
        with open(path) as f:
            lines = f.read().split('\n')
    except OSError:
        return []
    want = ' '.join(section.split()).lower()
    found, cur = [], None
    for line in lines:
        line = COMMENT_RE.sub('', line)
        mo = SECTION_RE.match(line)
        if mo:
            header = mo.group('header').strip()
            if header.startswith('include '):
                spec = os.path.join(os.path.dirname(path),
                                    header[8:].strip())
                for name in sorted(glob.glob(spec)):
                    found += config_origins(name, section, visited)
                cur = None
            else:
                cur = ' '.join(header.split()).lower()
            continue
        mo = OPTION_RE.match(line)
        if cur == want and mo and mo.group('key').strip().lower() == 'gcode':
            found.append(path)
    visited.discard(path)
    return found


class AD5XConfig:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.config_dir = config.get('config_dir', CONFIG_DIR)
        self.notice_path = os.path.join(self.config_dir, NOTICE_FILE)
        self.macros_dir = os.path.join(self.config_dir, 'macros')
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('CONFIG_BACKUPS', self.cmd_CONFIG_BACKUPS,
                                    desc=self.cmd_CONFIG_BACKUPS_help)
        self.status = {'notices': [], 'backups': []}
        # The file whose BED_MESH_CALIBRATE replaced Kiln's (Klipper start)
        self.mesh_owner = None
        self.printer.register_event_handler("klippy:ready", self._ready)
        self.printer.register_event_handler("klippy:ready",
                                            self._ready_guards)
        # A file loaded for printing (Moonraker's SDCARD_PRINT_FILE, M23,
        # SDCARD_RESET_FILE): a new print, nothing of its start done yet
        self.printer.register_event_handler("virtual_sdcard:reset_file",
                                            self.forget_marks)
    def _refresh(self):
        self.status = {'notices': self._notices(),
                       'backups': self._backups()}
        return self.status
    def _notices(self):
        try:
            with open(self.notice_path) as f:
                return [l.rstrip('\n') for l in f if l.strip()]
        except OSError:
            return []
    def _backups(self):
        try:
            names = os.listdir(self.macros_dir)
        except OSError:
            return []
        return sorted('macros/' + n for n in names if BACKUP_RE.match(n))
    def _ready(self):
        notices = self._refresh()['notices']
        if not notices:
            return
        for line in notices:
            logging.info("ad5x_config: %s", line)
        reactor = self.printer.get_reactor()
        reactor.register_callback(lambda et: self._announce(notices))
    def _announce(self, notices):
        lines = ["Macros updated by a system update:"] + notices + [
            "Merge your changes from the .bak file (Fluidd, Configuration),"
            " lasting ones into local.cfg. CONFIG_BACKUPS ACK=1 hides this."]
        self.gcode.respond_info("\n".join(lines))
        try:
            self.gcode.run_script("M117 Macros updated: see CONFIG_BACKUPS")
        except Exception:
            logging.exception("ad5x_config: M117")
    # One mesh and one prime line per print (issue #73)
    def _ready_guards(self):
        # Never stop Klipper over this: log and go on without it
        try:
            self._install_guards()
        except Exception:
            logging.exception("ad5x_config: start step guards")
        try:
            warnings = self.override_warnings()
        except Exception:
            logging.exception("ad5x_config: config override check")
            return
        if not warnings:
            return
        pconfig = self.printer.lookup_object('configfile', None)
        for msg in warnings:
            logging.warning("ad5x_config: %s", msg)
            if pconfig is not None and hasattr(pconfig, 'runtime_warning'):
                pconfig.runtime_warning(msg)
        reactor = self.printer.get_reactor()
        reactor.register_callback(
            lambda et: self.gcode.respond_raw(
                "\n".join("!! " + m for m in warnings)))
    def _install_guards(self):
        """Wrap the commands registered now (klippy:ready: after every
        gcode_macro rename_existing), whoever defines them."""
        for cmd in ("BED_MESH_CALIBRATE", "LINE_PURGE", "VORON_PURGE"):
            prev = self.gcode.register_command(cmd, None)
            if prev is None:
                continue
            self.gcode.register_command(cmd, self._guarded(cmd, prev))
    def _guarded(self, cmd, prev):
        def handler(gcmd):
            # An error in the check itself must not stop the print (an
            # exception here is a Klipper shutdown): run the command then
            try:
                reason = self.skip_reason(cmd, gcmd.get_command_parameters())
            except Exception:
                logging.exception("ad5x_config: %s guard", cmd)
                reason = None
            if reason:
                gcmd.respond_info(reason)
                return
            prev(gcmd)
            # Ran during a print: noted, whoever defines it (KAMP's
            # LINE_PURGE from START_PRINT sets no mark of its own). The
            # start's own mesh comes after _CHECK_Z cleared the marks.
            try:
                self.note_done(cmd)
            except Exception:
                logging.exception("ad5x_config: %s mark", cmd)
        return handler
    def _set_marks(self, values):
        """Set _KILN_START_DONE variables as SET_GCODE_VARIABLE does (a
        new dict, so status readers see the change)."""
        marks = self.printer.lookup_object(MARKS, None)
        if marks is None:
            return
        v = dict(marks.variables)
        v.update(values)
        marks.variables = v
    def note_done(self, cmd):
        stats = self.printer.lookup_object('print_stats', None)
        if stats is None:
            return
        st = stats.get_status(self.printer.get_reactor().monotonic())
        if st.get('state') == 'printing':
            self._set_marks({STEP[cmd]: float(st.get('total_duration', 0.))})
    def forget_marks(self):
        try:
            self._set_marks({'mesh': -1., 'line': -1.})
        except Exception:
            logging.exception("ad5x_config: forget start marks")
    def skip_reason(self, cmd, params):
        """Why cmd (with params) is skipped now, or None to run it."""
        params = {k.upper(): str(v).strip() for k, v in params.items()}
        if params.get('FORCE', '').lower() in ('1', 'true', 'yes'):
            return None
        if cmd == 'BED_MESH_CALIBRATE' and (
                'PROFILE' in params or params.get('ADAPTIVE') == '0'):
            return None
        marks = self.printer.lookup_object(MARKS, None)
        stats = self.printer.lookup_object('print_stats', None)
        if marks is None or stats is None:
            return None
        st = stats.get_status(self.printer.get_reactor().monotonic())
        if st.get('state') != 'printing':
            return None
        try:
            mark = float(marks.variables.get(STEP[cmd], -1.))
            now = float(st.get('total_duration', 0.))
        except (TypeError, ValueError):
            return None
        # -1: not this print. Later than now: a mark from an earlier print
        # (this one restarted total_duration at 0); loading the file
        # already forgot it, this is the second check.
        if mark < 0. or now < mark:
            return None
        return skipped_message(cmd, self.mesh_owner)
    def override_warnings(self):
        """Warnings for configs that replaced Kiln's BED_MESH_CALIBRATE,
        or bring a LINE_PURGE while Kiln's prime line is on."""
        pconfig = self.printer.lookup_object('configfile', None)
        if pconfig is None:
            return []
        reactor = self.printer.get_reactor()
        settings = pconfig.get_status(reactor.monotonic()).get('settings', {})
        out = []
        # Kiln's (ad5x.cfg) tares and calls the renamed Klipper command
        sec = settings.get('gcode_macro bed_mesh_calibrate')
        gcode = str(sec.get('gcode')) if sec is not None else ''
        if sec is not None and not ('WEIGHT_TARE' in gcode and
                                    '_BED_MESH_CALIBRATE_BASE' in gcode):
            where = self._origin('gcode_macro bed_mesh_calibrate',
                                 'Adaptive_Meshing.cfg')
            self.mesh_owner = where
            out.append(
                "BED_MESH_CALIBRATE is replaced by %s (issue #73). Kiln OS"
                " already meshes the print area at every PRINT_START; with"
                " this macro that mesh (and every other one: console,"
                " screen, setup wizard) runs without Kiln's strain gauge"
                " tare before probing, and a full mesh no longer saves the"
                " centre Z that the stock Z check needs (so don't turn"
                " mesh_every_print off while it is included). A"
                " BED_MESH_CALIBRATE from the slicer after PRINT_START's"
                " mesh is skipped during the print. Remove that include (or"
                " the section) to get Kiln's macro back." % (where,))
        sec = settings.get('gcode_macro line_purge')
        prime = self.printer.lookup_object('gcode_macro _PRIME_LINE', None)
        prime_on = prime is not None and prime.variables.get('prime_line')
        if sec is not None and prime_on \
                and '_PRIME_LINE' not in str(sec.get('gcode')):
            where = self._origin('gcode_macro line_purge', 'Line_Purge.cfg')
            # The prime line notes itself (macros/prime_line.cfg since
            # issue #73); an older edited copy doesn't
            pgcode = str(settings.get('gcode_macro _prime_line', {})
                         .get('gcode'))
            if '_KILN_START_DONE' in pgcode:
                then = ("PRINT_START already draws a prime line, and a"
                        " LINE_PURGE after it in the same print is skipped")
            else:
                then = ("PRINT_START already draws a prime line, and a"
                        " LINE_PURGE after it draws a second one: your"
                        " macros/prime_line.cfg is older than the one that"
                        " notes its line (merge it from the system's,"
                        " CONFIG_BACKUPS)")
            out.append(
                "LINE_PURGE comes from %s, while Kiln's prime line is on"
                " (issue #73). %s. To use that purge line instead, set"
                " variable_prime_line: 0 under [gcode_macro _PRIME_LINE] in"
                " local.cfg." % (where, then))
        return out
    def _origin(self, section, kamp_file):
        """The file whose gcode Klipper uses for section, as the config
        directory shows it; else a general description."""
        try:
            main = self.printer.get_start_args().get('config_file')
        except Exception:
            main = None
        files = config_origins(main, section) if main else []
        if not files:
            return SOMEWHERE % (kamp_file,)
        # Relative to the config directory (a link: /home/klipper/... is
        # /data/ad5x/... on the printer)
        path = os.path.realpath(files[-1])
        base = os.path.realpath(self.config_dir) + os.sep
        return path[len(base):] if path.startswith(base) else files[-1]
    cmd_CONFIG_BACKUPS_help = ("List macros/ files an update replaced and "
                               "the backups of edited ones; ACK=1 clears "
                               "the notice")
    def cmd_CONFIG_BACKUPS(self, gcmd):
        ack = gcmd.get_int('ACK', 0)
        notices = self._notices()
        backups = self._backups()
        lines = []
        if notices:
            lines.append("Update notices (%s):" % (NOTICE_FILE,))
            lines.extend("  " + l for l in notices)
        else:
            lines.append("No update notices.")
        if backups:
            lines.append("Backups of edited macros files (delete them in "
                         "Fluidd when merged):")
            lines.extend("  " + b for b in backups)
        else:
            lines.append("No backups in macros/.")
        if ack and notices:
            try:
                os.remove(self.notice_path)
                lines.append("Notice cleared (backups kept).")
            except OSError as e:
                raise gcmd.error("CONFIG_BACKUPS: can't remove %s: %s"
                                 % (self.notice_path, e))
        self._refresh()
        gcmd.respond_info("\n".join(lines))
    def get_status(self, eventtime):
        return dict(self.status)


def load_config(config):
    return AD5XConfig(config)
