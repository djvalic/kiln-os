# Plugins: optional bundles of Klipper config (and Python extras, and a
# Moonraker part), switched on and off per printer
#
# A plugin is a directory <name>/ with plugin.json (metadata), plugin.cfg
# (Klipper config), README.md and optionally extras/*.py (Klipper modules)
# and moonraker.conf (Moonraker sections, e.g. its own [update_manager]).
# Shipped plugins come with the system image (shipped_dir, read-only,
# updated with the image); other people's and the user's own go in
# user_dir (never touched by system updates; a user plugin with a shipped
# plugin's name replaces it). Which plugins are on is kept only in the
# printer's own plugins.cfg (config dir), one [include] line each, which
# ad5x.cfg reads. The include paths are glob patterns ("plugi[n].cfg"): a
# plugin that disappears is skipped instead of stopping Klipper.
#
# ENABLE_PLUGIN NAME= / DISABLE_PLUGIN NAME= (zMod's command names) edit
# plugins.cfg and restart Klipper; LIST_PLUGINS shows them. A plugin is
# refused when its requires_os (plugin API version) doesn't fit this
# system's PLUGIN_API_VERSION, when a plugin it requires is off, or when a
# conflicting one is on.
#
# Extras: Klipper loads modules only from klippy/extras (read-only image).
# This module, loaded before the plugins' sections (ad5x.cfg declares it
# before including plugins.cfg), imports each enabled plugin's
# extras/<module>.py as extras.<module> and creates the objects for its
# config sections the way Klipper's load_object does. Only enabled,
# compatible plugins' code is loaded; a module name Klipper already has is
# refused. No Klipper change needed.
#
# Moonraker: run as a script (S62moonraker does, before Moonraker starts)
# it writes moonraker-plugins.conf, the [include] list of the enabled
# plugins' moonraker.conf files; Klipper rewrites it when plugins change.
# Developer root actions (docs/plugin-root-actions.md): a plugin lists the
# named actions it needs in plugin.json "root_actions". DEV_ROOT_REQUEST
# PLUGIN= ACTION= [ARGS=] writes one request file for root (in
# /data/ad5x/dev-root/requests); root writes the result (results/) and
# klipper reports it. Nothing is granted here: the owner turns actions on at
# the printer (ad5x-dev-root enable), and grants/ is read-only for klipper.
# DEV_ROOT_STATUS shows them. Off by default.
# Moonraker reads it at its next start. A plugin's python/ (libraries) and
# moonraker/components/ (Moonraker components) directories (plugin API
# 1.3): Klipper gets python/ on sys.path before the extras load;
# "ad5x_plugins.py env" prints both lists for S62moonraker, which passes
# them to Moonraker (our patch to its components package).
#
# Catalog (plugin API 1.4): the plugins in their own repositories this
# release offers (/usr/share/ad5x/plugin-catalog.json, tested by the
# builder). INSTALL_PLUGIN NAME= [ENABLE=1] clones one into user_dir,
# UPDATE_PLUGIN pulls it, REMOVE_PLUGIN disables and deletes it; git runs
# in the background (printer.ad5x_plugins.job). When a switch changes what
# Moonraker loads, the root update agent (S68ad5x-update-agent) restarts
# Moonraker. HelixScreen's Settings > Plugins uses these. See
# docs/plugins.md and docs/plugin-api.md.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time

# The plugin API this system offers (docs/plugin-api.md): major.minor.
# Minor: additions only. Major: something plugins may use changed or went.
# post-build.sh copies it to /usr/lib/os-release as AD5X_PLUGIN_API.
PLUGIN_API_VERSION = "1.4"

CONFIG_DIR = "/home/klipper/printer_data/config"
SHIPPED_DIR = "/usr/share/ad5x/plugins"
USER_DIR = "/data/ad5x/plugins"
CATALOG_FILE = "/usr/share/ad5x/plugin-catalog.json"
# Picked up by S68ad5x-update-agent (root), which restarts Moonraker
MOONRAKER_RESTART_FILE = "/data/ad5x/kiln-update/restart-moonraker"
GIT_TIMEOUT = 600.

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
MODULE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# [include <dir>/<name>/plugin.cfg], with or without the glob brackets
INCLUDE_RE = re.compile(
    r"^\s*\[include\s+(?P<path>\S*/(?P<name>[A-Za-z0-9_.-]+)/"
    r"plugi(?:n|\[n\])\.cfg)\s*\]\s*$")
# print_stats states during which plugins can't be switched (it restarts)
BUSY_STATES = ("printing", "paused")

# Developer root actions (docs/plugin-root-actions.md)
DEV_ROOT_DIR = "/data/ad5x/dev-root"
ROOT_ACTIONS_FILE = "/usr/share/ad5x/root-actions.conf"
ROOT_ACTION_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
PLUGIN_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
# One request argument: plain characters only, no shell or path characters
ROOT_TOKEN_RE = re.compile(r"[A-Za-z0-9._+=,:@%-]{1,128}")
ROOT_MAX_ACTIONS = 16
ROOT_MAX_ARGS = 16
ROOT_RATE_SECONDS = 10.
ROOT_RESULT_WAIT = 600.
# <plugin>.<n>.req / .res (n: a number, unique per request)
ROOT_FILE_RE = re.compile(r"([a-z0-9][a-z0-9_-]{0,47})\.([0-9]{1,20})\.(req|res)")

PLUGINS_HEADER = """\
# Plugins enabled on this printer (docs/plugins.md). Written by
# ENABLE_PLUGIN / DISABLE_PLUGIN; hand edits are kept. One [include] line
# per plugin; the [n] makes the path a pattern, so a plugin that is gone
# is skipped instead of stopping Klipper. System updates never change
# this file.
"""

MOONRAKER_HEADER = """\
# Moonraker parts of the enabled plugins (docs/plugins.md). Generated from
# plugins.cfg when Moonraker starts and when plugins change; don't edit.
# Moonraker reads it after moonraker.conf (S62moonraker).
"""

def parse_version(text):
    """'1.2' -> (1, 2); None if not major.minor numbers."""
    m = re.match(r"^\s*(\d+)\.(\d+)\s*$", str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None

def api_compatible(required, offered=PLUGIN_API_VERSION):
    """Same major version, offered minor at least the required one.
    No requirement given: compatible."""
    if required in (None, ""):
        return True
    req, have = parse_version(required), parse_version(offered)
    return bool(req and have and req[0] == have[0] and req[1] <= have[1])

def read_metadata(plugin_dir, name):
    """plugin.json as a dict with every field present; 'error' set when
    the file is unusable (the plugin can't be enabled then)."""
    meta = {'name': name, 'description': "", 'version': "", 'author': "",
            'url': "", 'requires_os': "", 'requires': [], 'conflicts': [],
            'root_actions': [], 'error': None}
    path = os.path.join(plugin_dir, 'plugin.json')
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except FileNotFoundError:
        meta['error'] = "no plugin.json"
        return meta
    except (OSError, ValueError) as e:
        meta['error'] = "plugin.json: %s" % (e,)
        return meta
    for key in ('description', 'version', 'author', 'url', 'requires_os'):
        if data.get(key) is not None:
            meta[key] = str(data[key])
    for key in ('requires', 'conflicts'):
        val = data.get(key) or []
        if isinstance(val, str):
            val = [v.strip() for v in val.split(",")]
        meta[key] = [str(v).strip().lower() for v in val if str(v).strip()]
    meta['root_actions'] = read_root_actions(data, name)
    if data.get('name') not in (None, name):
        meta['error'] = "plugin.json name '%s' differs from the directory" % (
            data.get('name'),)
    elif meta['requires_os'] and parse_version(meta['requires_os']) is None:
        meta['error'] = "requires_os '%s' is not major.minor" % (
            meta['requires_os'],)
    return meta

def read_root_actions(data, name):
    """plugin.json root_actions as a list of plain names. A bad list (not a
    list, too long, or an entry that isn't a plain name) is logged and
    ignored as a whole; the plugin still installs. Duplicates are dropped."""
    raw = data.get('root_actions')
    if raw is None:
        return []
    bad = None
    if not isinstance(raw, list):
        bad = "root_actions is not a list"
    elif len(raw) > ROOT_MAX_ACTIONS:
        bad = "more than %d root_actions" % (ROOT_MAX_ACTIONS,)
    else:
        for entry in raw:
            if not isinstance(entry, str) or \
                    not ROOT_ACTION_RE.fullmatch(entry):
                bad = "root_actions entry %s is not a plain name" % (
                    repr(entry)[:40],)
                break
    if bad is not None:
        logging.warning("ad5x_plugins: plugin %s: %s; its root actions are "
                        "ignored", name, bad)
        return []
    out = []
    for entry in raw:
        if entry not in out:
            out.append(entry)
    return out

def request_args(raw):
    """ARGS= text -> the request's argument tokens (single spaces between
    them). ValueError for anything that isn't a plain token."""
    raw = (raw or "").strip(" ")
    if raw == "":
        return []
    tokens = raw.split(" ")
    if len(tokens) > ROOT_MAX_ARGS:
        raise ValueError("too many arguments (at most %d)" % (ROOT_MAX_ARGS,))
    for tok in tokens:
        if not ROOT_TOKEN_RE.fullmatch(tok):
            raise ValueError("argument %s is not a plain value (letters, "
                             "digits and . _ + = , : @ %% -)"
                             % (repr(tok)[:40],))
    return tokens

def read_grants(path):
    """Actions the owner granted, from the lines "action NAME" (root's
    grant format). A missing file grants nothing: set(). None when the
    file is there but klipper can't read it (root keeps grants private);
    the caller then lets root decide."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return set()
    except OSError:
        return None
    out = set()
    for line in lines:
        m = re.fullmatch(r"action ([A-Za-z0-9_-]{1,64})", line)
        if m is not None:
            out.add(m.group(1))
    return out

def read_action_list(path):
    """(names, print_safe) from the image's root action list (root's
    block format: "action NAME", then its lines, "print_safe yes|no"
    default no). names is None when the list can't be read; then no
    action is print_safe."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return None, set()
    names, safe, current = set(), set(), None
    for line in lines:
        words = line.split()
        if not words or words[0].startswith('#'):
            continue
        if words[0] == 'action' and len(words) >= 2:
            current = words[1]
            names.add(current)
        elif words[0] == 'print_safe' and current is not None and \
                len(words) >= 2 and words[1] == 'yes':
            safe.add(current)
    return names, safe

def root_actions_note(name, actions):
    return ("Plugin %s asks for root actions: %s. They are off until the "
            "owner turns them on at the printer (ad5x-dev-root enable); "
            "Kiln OS does not grant them." % (name, ", ".join(actions)))

def scan(shipped_dir=SHIPPED_DIR, user_dir=USER_DIR):
    """name -> info for every directory holding a plugin.cfg; user plugins
    replace shipped ones of the same name."""
    found = {}
    for source, base in (("shipped", shipped_dir), ("user", user_dir)):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            d = os.path.join(base, name)
            if not NAME_RE.match(name) or not os.path.isfile(
                    os.path.join(d, 'plugin.cfg')):
                continue
            info = read_metadata(d, name)
            info.update({
                'dir': d, 'source': source,
                'compatible': api_compatible(info['requires_os']),
                'extras': os.path.isdir(os.path.join(d, 'extras')),
                'moonraker': os.path.isfile(os.path.join(d,
                                                         'moonraker.conf')),
                'python': os.path.isdir(os.path.join(d, 'python')),
                'components': os.path.isdir(os.path.join(
                    d, 'moonraker', 'components'))})
            found[name] = info
    return found

def read_enabled(plugins_file):
    """(enabled names in file order, lines); a missing file is empty
    (lines None)."""
    try:
        with open(plugins_file) as f:
            lines = f.read().splitlines()
    except OSError:
        return [], None
    names = []
    for line in lines:
        m = INCLUDE_RE.match(line)
        if m is not None and m.group('name') not in names:
            names.append(m.group('name'))
    return names, lines

def moonraker_text(names, found):
    lines = [MOONRAKER_HEADER.rstrip("\n")]
    updates = False
    for name in names:
        info = found.get(name)
        if info is None or not info['moonraker'] or not info['compatible'] \
                or info['error']:
            continue
        path = os.path.join(info['dir'], 'moonraker.conf')
        try:
            with open(path) as f:
                updates |= "[update_manager" in f.read()
        except OSError:
            continue
        lines.append("[include %s]" % (path,))
    if updates:
        # Plugins kept up to date by Moonraker: this system has no package
        # manager for Moonraker's system updates.
        lines += ["[update_manager]", "enable_system_updates: False"]
    return "\n".join(lines) + "\n"

def plugin_paths(names, found):
    """(python dirs, Moonraker component dirs) of the enabled, compatible
    plugins, in plugins.cfg order."""
    python, components = [], []
    for name in names:
        info = found.get(name)
        if info is None or not info['compatible'] or info['error']:
            continue
        if info['python']:
            python.append(os.path.join(info['dir'], 'python'))
        if info['components']:
            components.append(os.path.join(info['dir'], 'moonraker',
                                           'components'))
    return python, components

def env_text(names, found):
    """Shell assignments for S62moonraker (plugin directory names are
    checked against NAME_RE, so they need no quoting beyond this)."""
    python, components = plugin_paths(names, found)
    return "AD5X_PLUGIN_PYTHON='%s'\nAD5X_MOONRAKER_COMPONENTS='%s'\n" % (
        ":".join(python), ":".join(components))

def read_catalog(path):
    """name -> {title, description, url, requires_os} of the catalog's
    valid entries (https git URLs; file:// for tests); a missing file is
    empty."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    entries = data.get('plugins') if isinstance(data, dict) else None
    for p in entries if isinstance(entries, list) else []:
        if not isinstance(p, dict):
            continue
        name, url = p.get('name'), p.get('url')
        if not isinstance(name, str) or not NAME_RE.match(name) or \
                not isinstance(url, str) or \
                not url.startswith(('https://', 'file://')):
            continue
        out[name] = {'title': str(p.get('title') or name),
                     'description': str(p.get('description') or ''),
                     'url': url,
                     'requires_os': str(p.get('requires_os') or '')}
    return out

def touches_moonraker(info):
    """A plugin whose switch changes what Moonraker loads."""
    return bool(info) and (info['moonraker'] or info['python']
                           or info['components'])

def write_if_changed(path, text):
    """Write text atomically unless the file already holds it. True if
    written."""
    try:
        with open(path) as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return True

class DevRoot:
    """DEV_ROOT_REQUEST / DEV_ROOT_STATUS: a plugin's request for a named
    root action (docs/plugin-root-actions.md). Klipper checks what it can,
    writes one request file and reports root's result. Granting is root's
    job (the owner's ad5x-dev-root enable); Klipper only reads the grants,
    and where root keeps a grant unreadable it lets root decide."""
    def __init__(self, owner, config):
        self.owner = owner
        self.printer = owner.printer
        self.gcode = owner.gcode
        base = config.get('dev_root_dir', DEV_ROOT_DIR)
        self.requests_dir = os.path.join(base, 'requests')
        self.results_dir = os.path.join(base, 'results')
        self.grants_dir = os.path.join(base, 'grants')
        self.actions_file = config.get('root_actions_file', ROOT_ACTIONS_FILE)
        self.last_sent = {}   # plugin -> time of its last request written
        self.pending = {}     # request id -> (request line, time sent)
        self.recent = []      # last results reported (DEV_ROOT_STATUS)
        self.kept = set()     # result files that could not be removed
        self.last_n = 0
        self.polling = False

    def _now(self):
        return self.printer.get_reactor().monotonic()

    def _printing(self):
        ps = self.printer.lookup_object('print_stats', None)
        return ps is not None and ps.get_status(self._now()).get(
            'state') in BUSY_STATES

    def _grants(self, plugin):
        return read_grants(os.path.join(self.grants_dir, plugin + '.grant'))

    def _write(self, gcmd, plugin, line):
        """One request file: written under a dot-name (root does not read
        those) and renamed, so root never reads half a line. Returns the
        request id."""
        n = max(int(time.time() * 1000), self.last_n + 1)
        while os.path.exists(os.path.join(self.requests_dir,
                                          "%s.%d.req" % (plugin, n))):
            n += 1
        self.last_n = n
        base = "%s.%d.req" % (plugin, n)
        path = os.path.join(self.requests_dir, base)
        tmp = os.path.join(self.requests_dir, "." + base + ".tmp")
        try:
            with open(tmp, "w") as f:
                f.write(line + "\n")
            os.rename(tmp, path)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise gcmd.error("Can't write the root request in %s: %s"
                             % (self.requests_dir, e))
        return "%s.%d" % (plugin, n)

    def request(self, gcmd):
        plugin = gcmd.get('PLUGIN').strip().lower()
        action = gcmd.get('ACTION').strip()
        if not PLUGIN_NAME_RE.fullmatch(plugin):
            raise gcmd.error("PLUGIN must be a plugin name (a-z, 0-9, - _)")
        if not ROOT_ACTION_RE.fullmatch(action):
            raise gcmd.error("ACTION must be a plain name (letters, digits, "
                             "- _)")
        try:
            args = request_args(gcmd.get('ARGS', ''))
        except ValueError as e:
            raise gcmd.error("Refused: %s" % (e,))
        self.owner.found = scan(self.owner.shipped_dir, self.owner.user_dir)
        info = self.owner.found.get(plugin)
        if info is None or info['error']:
            raise gcmd.error("Plugin %s is not installed, or its plugin.json "
                             "is bad" % (plugin,))
        if action not in info['root_actions']:
            raise gcmd.error("Plugin %s did not declare root action %s "
                             "(root_actions: %s)" % (
                                 plugin, action,
                                 ", ".join(info['root_actions']) or "none"))
        names, safe = read_action_list(self.actions_file)
        if names is not None and action not in names:
            raise gcmd.error("Root action %s is not in this image's list"
                             % (action,))
        if self._printing() and action not in safe:
            raise gcmd.error("Root action %s can't run during a print"
                             % (action,))
        granted = self._grants(plugin)
        if granted is not None and action not in granted:
            raise gcmd.error("Root action %s is not granted to %s. The owner "
                             "turns it on at the printer: ad5x-dev-root "
                             "enable" % (action, plugin))
        now = self._now()
        last = self.last_sent.get(plugin)
        if last is not None and now - last < ROOT_RATE_SECONDS:
            raise gcmd.error("Plugin %s sent a root request %.0f s ago; one "
                             "per %.0f s" % (plugin, now - last,
                                             ROOT_RATE_SECONDS))
        line = " ".join([plugin, action] + args)
        rid = self._write(gcmd, plugin, line)
        self.last_sent[plugin] = now
        self.pending[rid] = (line, now)
        note = "" if granted is not None else (
            " (the grant is not readable from Klipper; root checks it)")
        gcmd.respond_info("Root request %s sent: %s%s (the result follows)"
                          % (rid, line, note))
        self.start_poll()

    def start_poll(self):
        if not self.polling:
            self.polling = True
            reactor = self.printer.get_reactor()
            reactor.register_timer(self._poll, reactor.monotonic() + .5)

    def _poll(self, eventtime):
        try:
            names = sorted(os.listdir(self.results_dir))
        except OSError:
            names = []
        for fn in names:
            m = ROOT_FILE_RE.fullmatch(fn)
            if m is None or m.group(3) != 'res' or fn in self.kept:
                continue
            self._report("%s.%s" % (m.group(1), m.group(2)),
                         os.path.join(self.results_dir, fn))
        for rid, (line, sent) in list(self.pending.items()):
            if eventtime - sent > ROOT_RESULT_WAIT:
                del self.pending[rid]
                self._say("Root request %s (%s): no result after %.0f s; is "
                          "the root agent running?"
                          % (rid, line, ROOT_RESULT_WAIT))
        if self.pending:
            return eventtime + .5
        self.polling = False
        return self.printer.get_reactor().NEVER

    def _report(self, rid, path):
        """Root writes "<ok or refused: reason> at <time>" on one line."""
        try:
            with open(path) as f:
                first = f.readline(512).strip()
        except OSError as e:
            first = "refused: result unreadable (%s)" % (e,)
        text = re.sub(r" at \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", "", first)
        if text != "ok" and not text.startswith("refused: "):
            text = "unexpected result %s" % (repr(text)[:80],)
        line = self.pending.pop(rid, ("unknown request",))[0]
        self._say("Root request %s (%s): %s" % (rid, line, text))
        self.recent = (self.recent + ["%s: %s" % (rid, text)])[-5:]
        try:
            os.remove(path)
        except OSError as e:
            # root's results dir is not writable by klipper: keep it in
            # memory so it is not reported again this start
            self.kept.add(os.path.basename(path))
            logging.info("ad5x_plugins: can't remove %s: %s", path, e)

    def _say(self, msg):
        logging.info("ad5x_plugins: %s", msg)
        self.gcode.respond_info(msg)

    def status(self, gcmd):
        self.owner.found = scan(self.owner.shipped_dir, self.owner.user_dir)
        lines = ["Developer root actions (off until the owner grants them: "
                 "ad5x-dev-root enable)"]
        declared = [(n, i) for n, i in sorted(self.owner.found.items())
                    if i['root_actions']]
        if not declared:
            lines.append("No plugin declares root actions.")
        names, safe = read_action_list(self.actions_file)
        for name, info in declared:
            granted = self._grants(name)
            for action in info['root_actions']:
                if granted is None:
                    state = "grant not readable here"
                else:
                    state = "granted" if action in granted else "not granted"
                notes = []
                if names is not None and action not in names:
                    notes.append("not in this image's list")
                if action in safe:
                    notes.append("print_safe")
                lines.append("%s: %s %s%s" % (
                    name, action, state,
                    "".join(", " + n for n in notes)))
        try:
            waiting = sorted(f for f in os.listdir(self.requests_dir)
                             if ROOT_FILE_RE.fullmatch(f))
        except OSError:
            waiting = []
        lines.append("Requests waiting for root: %s"
                     % (", ".join(waiting) or "none"))
        lines.append("Sent here, no result yet: %s"
                     % (", ".join(sorted(self.pending)) or "none"))
        lines.append("Recent results: %s"
                     % ("; ".join(self.recent) or "none"))
        gcmd.respond_info("\n".join(lines))

class AD5XPlugins:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.plugins_file = config.get(
            'plugins_file', os.path.join(CONFIG_DIR, 'plugins.cfg'))
        self.moonraker_file = config.get(
            'moonraker_file', os.path.join(CONFIG_DIR,
                                           'moonraker-plugins.conf'))
        self.shipped_dir = config.get('shipped_dir', SHIPPED_DIR)
        self.user_dir = config.get('user_dir', USER_DIR)
        self.catalog_file = config.get('catalog_file', CATALOG_FILE)
        self.restart_file = config.get('moonraker_restart_file',
                                       MOONRAKER_RESTART_FILE)
        self.catalog = read_catalog(self.catalog_file)
        # The last install/update/remove result survives the Klipper restart
        # that enabling a plugin makes (the screen shows it after)
        self.job_file = os.path.join(self.user_dir, '.last-job.json')
        self.job = {'name': '', 'action': '', 'state': 'idle',
                    'message': ''}
        try:
            with open(self.job_file) as f:
                saved = json.load(f)
            if isinstance(saved, dict) and saved.get('state') in (
                    'done', 'failed'):
                self.job.update({k: str(saved.get(k, '')) for k in
                                 ('name', 'action', 'state', 'message')})
        except (OSError, ValueError):
            pass
        self.proc = None
        self.found = scan(self.shipped_dir, self.user_dir)
        # Enabled at this start (plugins.cfg as Klipper read it)
        self.loaded = read_enabled(self.plugins_file)[0]
        self.warnings = []
        self.modules = {}
        self._load_extras(config)
        self.dev_root = DevRoot(self, config)
        self.printer.register_event_handler("klippy:ready",
                                            self._handle_ready)
        # Also while Klipper isn't ready: a plugin whose config stops
        # Klipper can be disabled from the console (when the error comes
        # after this section, as a plugin's own sections do)
        for cmd in ("ENABLE_PLUGIN", "DISABLE_PLUGIN", "LIST_PLUGINS"):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        when_not_ready=True,
                                        desc=getattr(self, "cmd_%s_help" % cmd))
        for cmd in ("INSTALL_PLUGIN", "UPDATE_PLUGIN", "REMOVE_PLUGIN"):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        desc=getattr(self, "cmd_%s_help" % cmd))
        for cmd in ("DEV_ROOT_REQUEST", "DEV_ROOT_STATUS"):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        desc=getattr(self, "cmd_%s_help" % cmd))
    # Startup
    def _warn(self, msg):
        logging.warning("ad5x_plugins: %s", msg)
        self.warnings.append(msg)
        pconfig = self.printer.lookup_object('configfile', None)
        if pconfig is not None and hasattr(pconfig, 'runtime_warning'):
            pconfig.runtime_warning(msg)
    def _usable(self, name):
        """Enabled plugin whose code may run: present, valid, compatible."""
        info = self.found.get(name)
        if info is None:
            self._warn("Plugin %s is enabled but missing (no plugin.cfg in "
                       "%s or %s); skipped" % (name, self.shipped_dir,
                                               self.user_dir))
            return None
        if info['error']:
            self._warn("Plugin %s: %s; its extras are not loaded"
                       % (name, info['error']))
            return None
        if not info['compatible']:
            self._warn("Plugin %s needs plugin API %s, this system has %s; "
                       "its extras are not loaded (DISABLE_PLUGIN NAME=%s)"
                       % (name, info['requires_os'], PLUGIN_API_VERSION,
                          name))
            return None
        return info
    def _load_extras(self, config):
        core = os.path.dirname(os.path.abspath(__file__))
        # Libraries the plugins bring (python/), after Klipper's own
        for d in plugin_paths(self.loaded, self.found)[0]:
            if d not in sys.path:
                sys.path.append(d)
        wanted = {}
        for name in self.loaded:
            info = self._usable(name)
            if info is None or not info['extras']:
                continue
            ext = os.path.join(info['dir'], 'extras')
            for fn in sorted(os.listdir(ext)):
                mod = fn[:-3]
                if not fn.endswith('.py') or not MODULE_RE.match(mod):
                    continue
                if os.path.exists(os.path.join(core, fn)) or os.path.isdir(
                        os.path.join(core, mod)):
                    raise config.error(
                        "Plugin %s: extras/%s has the name of a Klipper "
                        "module; rename it" % (name, fn))
                if mod in wanted:
                    raise config.error(
                        "Plugins %s and %s both have extras/%s"
                        % (wanted[mod][0], name, fn))
                wanted[mod] = (name, os.path.join(ext, fn))
        for mod, (name, path) in sorted(wanted.items()):
            full = 'extras.' + mod
            spec = importlib.util.spec_from_file_location(full, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[full] = module
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                del sys.modules[full]
                logging.exception("ad5x_plugins: loading %s", path)
                raise config.error("Plugin %s: extras/%s.py failed to load: "
                                   "%s" % (name, mod, e))
            self.modules[mod] = module
            logging.info("ad5x_plugins: loaded %s from plugin %s", mod, name)
        # Objects for the plugin modules' config sections, as load_object
        # would make them (it only looks in klippy/extras)
        for section in config.get_prefix_sections(''):
            sname = section.get_name()
            parts = sname.split()
            module = self.modules.get(parts[0])
            if module is None or self.printer.lookup_object(
                    sname, None) is not None:
                continue
            init = getattr(module, 'load_config_prefix' if len(parts) > 1
                           else 'load_config', None)
            if init is None:
                raise config.error("Unable to load module '%s'" % (sname,))
            self.printer.add_object(sname, init(config.getsection(sname)))
    def _handle_ready(self):
        # Keep the Moonraker list in step (a system update may have added
        # or dropped a plugin's moonraker.conf). Moonraker reads it at its
        # next start.
        self._write_moonraker(self.loaded)
        # Results of root requests left from before this start
        self.dev_root.start_poll()
    def _write_moonraker(self, names):
        try:
            return write_if_changed(self.moonraker_file,
                                    moonraker_text(names, self.found))
        except OSError as e:
            logging.info("ad5x_plugins: can't write %s: %s",
                         self.moonraker_file, e)
            return False
    # plugins.cfg
    def _write_enabled(self, enable=(), disable=()):
        """Add include lines for enable, drop the lines of disable (and
        duplicate lines of any plugin); other lines are kept as they are."""
        lines = read_enabled(self.plugins_file)[1]
        if lines is None:
            lines = PLUGINS_HEADER.splitlines()
        out, seen = [], set()
        for line in lines:
            m = INCLUDE_RE.match(line)
            if m is not None:
                name = m.group('name')
                if name in disable or name in seen:
                    continue
                seen.add(name)
            out.append(line)
        for name in enable:
            if name not in seen:
                out.append("[include %s/plugi[n].cfg]"
                           % (self.found[name]['dir'],))
        write_if_changed(self.plugins_file, "\n".join(out) + "\n")
        return read_enabled(self.plugins_file)[0]
    # Commands
    def _check_idle(self, gcmd):
        ps = self.printer.lookup_object('print_stats', None)
        if ps is not None and ps.get_status(
                self.printer.get_reactor().monotonic()).get(
                    'state') in BUSY_STATES:
            raise gcmd.error("Plugins can't be switched during a print "
                             "(Klipper restarts)")
    def _apply(self, gcmd, enable=(), disable=()):
        try:
            names = self._write_enabled(enable, disable)
        except OSError as e:
            raise gcmd.error("Can't write %s: %s" % (self.plugins_file, e))
        changed = self._write_moonraker(names)
        if changed or any(touches_moonraker(self.found.get(n))
                          for n in list(enable) + list(disable)):
            self._restart_moonraker(gcmd)
        if gcmd.get_int('RESTART', 1):
            gcmd.respond_info("Restarting Klipper")
            self.gcode.run_script_from_command("RESTART")
        else:
            gcmd.respond_info("Takes effect at the next RESTART")
    def _restart_moonraker(self, gcmd=None):
        """Ask the root update agent to restart Moonraker (it reads the
        plugins' Moonraker parts at its start)."""
        try:
            with open(self.restart_file, "w") as f:
                f.write("plugins\n")
            msg = "Moonraker restarts for the plugin's Moonraker part"
        except OSError as e:
            logging.info("ad5x_plugins: %s: %s", self.restart_file, e)
            msg = "The Moonraker part changes when Moonraker restarts (reboot)"
        if gcmd is not None:
            gcmd.respond_info(msg)
        else:
            self.gcode.respond_info(msg)
    # Catalog plugins: git in the background
    def _catalog_entry(self, gcmd):
        name = gcmd.get('NAME').strip().lower()
        self.catalog = read_catalog(self.catalog_file)
        if name not in self.catalog:
            raise gcmd.error("'%s' is not in the plugin catalog. Offered: %s"
                             % (name, ", ".join(sorted(self.catalog))
                                or "none"))
        return name, self.catalog[name]
    def _start_job(self, gcmd, name, action, argv, done):
        if self.job['state'] == 'running':
            raise gcmd.error("Busy: %s %s" % (self.job['action'],
                                              self.job['name']))
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
        env.setdefault('HOME', '/home/klipper')
        try:
            self.proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env=env)
        except OSError as e:
            raise gcmd.error("Can't run git: %s" % (e,))
        self.job = {'name': name, 'action': action, 'state': 'running',
                    'message': "%s %s..." % (action, name)}
        self.job_done = done
        reactor = self.printer.get_reactor()
        self.job_end = reactor.monotonic() + GIT_TIMEOUT
        reactor.register_timer(self._poll_job, reactor.monotonic() + .5)
        gcmd.respond_info(self.job['message'])
    def _poll_job(self, eventtime):
        rc = self.proc.poll()
        if rc is None:
            if eventtime < self.job_end:
                return eventtime + .5
            self.proc.kill()
            rc = self.proc.wait()
            out = "timed out"
        else:
            out = self.proc.stdout.read().decode('utf-8', 'replace')
        self.proc.stdout.close()
        self.proc = None
        try:
            msg = self.job_done(rc, out.strip())
            state = 'done'
        except Exception as e:
            msg, state = str(e), 'failed'
        self.job.update({'state': state, 'message': msg})
        self._save_job()
        self.gcode.respond_info("%s %s: %s" % (self.job['action'],
                                               self.job['name'], msg))
        return self.printer.get_reactor().NEVER
    def _save_job(self):
        try:
            write_if_changed(self.job_file, json.dumps(self.job))
        except OSError as e:
            logging.info("ad5x_plugins: %s: %s", self.job_file, e)
    def _restart_after(self, info, msg):
        """Restart what a changed enabled plugin needs; returns msg."""
        msg += "; restarting Klipper"
        self.job.update({'state': 'done', 'message': msg})
        self._save_job()
        if touches_moonraker(info):
            self._restart_moonraker()
        self.gcode.run_script("RESTART")
        return msg
    cmd_INSTALL_PLUGIN_help = ("Install a plugin from the catalog: NAME= "
                               "[ENABLE=1]")
    def cmd_INSTALL_PLUGIN(self, gcmd):
        name, entry = self._catalog_entry(gcmd)
        enable = gcmd.get_int('ENABLE', 0)
        dest = os.path.join(self.user_dir, name)
        if os.path.exists(dest):
            raise gcmd.error("Plugin %s is installed already "
                             "(UPDATE_PLUGIN / REMOVE_PLUGIN)" % (name,))
        if not api_compatible(entry['requires_os']):
            raise gcmd.error("Plugin %s needs plugin API %s; this system "
                             "has %s" % (name, entry['requires_os'],
                                         PLUGIN_API_VERSION))
        if enable:
            self._check_idle(gcmd)
        tmp = os.path.join(self.user_dir, ".install-" + name)
        shutil.rmtree(tmp, ignore_errors=True)
        def done(rc, out):
            if rc != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                raise Exception("git clone failed: %s" % (out[-300:],))
            meta = read_metadata(tmp, name)
            if meta['error']:
                shutil.rmtree(tmp, ignore_errors=True)
                raise Exception("not a valid plugin: %s" % (meta['error'],))
            os.rename(tmp, dest)
            self.found = scan(self.shipped_dir, self.user_dir)
            if enable:
                # Saved first: enabling restarts Klipper
                self.job.update({'state': 'done',
                                 'message': "installed and enabled"})
                self._save_job()
                self.gcode.run_script("ENABLE_PLUGIN NAME=%s" % (name,))
                return "installed and enabled"
            msg = "installed (ENABLE_PLUGIN NAME=%s)" % (name,)
            actions = self.found[name]['root_actions'] if name in \
                self.found else []
            if actions:
                msg += ". " + root_actions_note(name, actions)
            return msg
        try:
            os.makedirs(self.user_dir, exist_ok=True)
        except OSError as e:
            raise gcmd.error("Can't create %s: %s" % (self.user_dir, e))
        self._start_job(gcmd, name, "install",
                        ["git", "clone", "-q", entry['url'], tmp], done)
    cmd_UPDATE_PLUGIN_help = "Update an installed plugin (git pull): NAME="
    def cmd_UPDATE_PLUGIN(self, gcmd):
        name = gcmd.get('NAME').strip().lower()
        d = os.path.join(self.user_dir, name)
        if not os.path.isdir(os.path.join(d, '.git')):
            raise gcmd.error("Plugin %s isn't a git install in %s"
                             % (name, self.user_dir))
        on = name in read_enabled(self.plugins_file)[0]
        if on:
            self._check_idle(gcmd)
        def head():
            try:
                return subprocess.check_output(
                    ["git", "-C", d, "rev-parse", "--short", "HEAD"],
                    stderr=subprocess.DEVNULL).decode().strip()
            except (OSError, subprocess.CalledProcessError):
                return "?"
        before = head()
        def done(rc, out):
            if rc != 0:
                raise Exception("git pull failed: %s" % (out[-300:],))
            after = head()
            self.found = scan(self.shipped_dir, self.user_dir)
            if after == before:
                return "up to date (%s)" % (after,)
            msg = "updated %s -> %s" % (before, after)
            if on:
                return self._restart_after(self.found.get(name), msg)
            return msg
        self._start_job(gcmd, name, "update",
                        ["git", "-C", d, "pull", "-q", "--ff-only"], done)
    cmd_REMOVE_PLUGIN_help = "Disable and delete an installed plugin: NAME="
    def cmd_REMOVE_PLUGIN(self, gcmd):
        self.found = scan(self.shipped_dir, self.user_dir)
        name = gcmd.get('NAME').strip().lower()
        info = self.found.get(name)
        d = os.path.join(self.user_dir, name)
        if info is None or info['source'] != 'user' or not os.path.isdir(d):
            raise gcmd.error("Plugin %s isn't installed in %s (shipped "
                             "plugins can only be disabled)"
                             % (name, self.user_dir))
        if self.job['state'] == 'running' and self.job['name'] == name:
            raise gcmd.error("Busy: %s %s" % (self.job['action'], name))
        enabled = read_enabled(self.plugins_file)[0]
        on = name in enabled
        users = [n for n in enabled if n != name
                 and name in self.found.get(n, {}).get('requires', ())]
        if users:
            raise gcmd.error("Plugin %s is needed by %s: disable that first"
                             % (name, ", ".join(users)))
        if on:
            self._check_idle(gcmd)
            names = self._write_enabled(disable=[name])
        shutil.rmtree(d)
        self.found = scan(self.shipped_dir, self.user_dir)
        self.job = {'name': name, 'action': 'remove', 'state': 'done',
                    'message': 'removed'}
        self._save_job()
        gcmd.respond_info("Plugin %s removed" % (name,))
        if on:
            if self._write_moonraker(names) or touches_moonraker(info):
                self._restart_moonraker(gcmd)
            gcmd.respond_info("Restarting Klipper")
            self.gcode.run_script_from_command("RESTART")
    cmd_ENABLE_PLUGIN_help = ("Enable a plugin and restart Klipper: NAME= "
                              "[RESTART=0]")
    def cmd_ENABLE_PLUGIN(self, gcmd):
        self.found = scan(self.shipped_dir, self.user_dir)
        name = gcmd.get('NAME').strip().lower()
        info = self.found.get(name)
        if info is None:
            raise gcmd.error("Unknown plugin '%s'. Available: %s" % (
                name, ", ".join(sorted(self.found)) or "none"))
        enabled = read_enabled(self.plugins_file)[0]
        if name in enabled:
            gcmd.respond_info("Plugin %s is already enabled" % (name,))
            return
        if info['error']:
            raise gcmd.error("Plugin %s: %s" % (name, info['error']))
        if not info['compatible']:
            raise gcmd.error("Plugin %s needs plugin API %s; this system "
                             "has %s" % (name, info['requires_os'],
                                         PLUGIN_API_VERSION))
        missing = [r for r in info['requires'] if r not in enabled]
        if missing:
            raise gcmd.error("Plugin %s needs %s: enable it first" % (
                name, ", ".join(missing)))
        clash = [c for c in enabled if c in info['conflicts'] or name in
                 self.found.get(c, {}).get('conflicts', ())]
        if clash:
            raise gcmd.error("Plugin %s can't be on together with %s: "
                             "disable it first" % (name, ", ".join(clash)))
        self._check_idle(gcmd)
        gcmd.respond_info("Plugin %s %s enabled (%s)" % (
            name, info['version'], info['source']))
        if info['root_actions']:
            gcmd.respond_info(root_actions_note(name, info['root_actions']))
        self._apply(gcmd, enable=[name])
    cmd_DISABLE_PLUGIN_help = ("Disable a plugin and restart Klipper: NAME= "
                               "[RESTART=0]")
    def cmd_DISABLE_PLUGIN(self, gcmd):
        self.found = scan(self.shipped_dir, self.user_dir)
        name = gcmd.get('NAME').strip().lower()
        enabled = read_enabled(self.plugins_file)[0]
        if name not in enabled:
            if name not in self.found:
                raise gcmd.error("Unknown plugin '%s'" % (name,))
            gcmd.respond_info("Plugin %s is not enabled" % (name,))
            return
        users = [n for n in enabled if n != name
                 and name in self.found.get(n, {}).get('requires', ())]
        if users:
            raise gcmd.error("Plugin %s is needed by %s: disable that first"
                             % (name, ", ".join(users)))
        self._check_idle(gcmd)
        gcmd.respond_info("Plugin %s disabled" % (name,))
        self._apply(gcmd, disable=[name])
    cmd_DEV_ROOT_REQUEST_help = ("Ask root for a named action a plugin "
                                 "declares: PLUGIN= ACTION= [ARGS=\"a b\"]")
    def cmd_DEV_ROOT_REQUEST(self, gcmd):
        self.dev_root.request(gcmd)
    cmd_DEV_ROOT_STATUS_help = ("Show the plugins' root actions, which are "
                                "granted, and pending requests")
    def cmd_DEV_ROOT_STATUS(self, gcmd):
        self.dev_root.status(gcmd)
    cmd_LIST_PLUGINS_help = "List the plugins (shipped and own) and which are on"
    def cmd_LIST_PLUGINS(self, gcmd):
        self.found = scan(self.shipped_dir, self.user_dir)
        enabled = read_enabled(self.plugins_file)[0]
        lines = ["Plugin API %s" % (PLUGIN_API_VERSION,)]
        for name in sorted(set(self.found) | set(enabled)):
            info = self.found.get(name)
            on = name in enabled
            if info is None:
                lines.append("[on]  %s: missing, skipped" % (name,))
                continue
            notes = []
            if info['error']:
                notes.append(info['error'])
            elif not info['compatible']:
                notes.append("needs plugin API %s" % (info['requires_os'],))
            if info['requires']:
                notes.append("requires " + ", ".join(info['requires']))
            if info['conflicts']:
                notes.append("conflicts with " + ", ".join(info['conflicts']))
            if on != (name in self.loaded):
                notes.append("until RESTART")
            lines.append("%s %s %s (%s%s): %s%s" % (
                "[on] " if on else "[off]", name, info['version'] or "-",
                info['source'], ", " + info['author'] if info['author']
                else "", info['description'] or "-",
                " [%s]" % ("; ".join(notes),) if notes else ""))
        lines.append("ENABLE_PLUGIN NAME=<name> / DISABLE_PLUGIN NAME=<name>")
        gcmd.respond_info("\n".join(lines))
    def get_status(self, eventtime):
        return {
            'api_version': PLUGIN_API_VERSION,
            'enabled': list(self.loaded),
            'available': {
                n: {k: i[k] for k in ('source', 'description', 'version',
                                      'author', 'url', 'requires_os',
                                      'compatible')}
                for n, i in self.found.items()},
            'catalog': {
                n: dict(e, compatible=api_compatible(e['requires_os']),
                        installed=n in self.found
                        and self.found[n]['source'] == 'user')
                for n, e in self.catalog.items()},
            'job': dict(self.job),
            'warnings': list(self.warnings)}

def load_config(config):
    return AD5XPlugins(config)

def main(argv):
    """S62moonraker, before Moonraker starts: write the Moonraker include
    list, or print the plugins' library and component directories.
    usage: ad5x_plugins.py moonraker [PLUGINS_CFG [OUT]]
           ad5x_plugins.py env [PLUGINS_CFG]"""
    if len(argv) < 2 or argv[1] not in ("moonraker", "env"):
        sys.stderr.write("usage: ad5x_plugins.py moonraker [PLUGINS_CFG "
                         "[OUT]] | env [PLUGINS_CFG]\n")
        return 2
    plugins_file = argv[2] if len(argv) > 2 else os.path.join(
        CONFIG_DIR, 'plugins.cfg')
    if argv[1] == "env":
        names = read_enabled(plugins_file)[0]
        sys.stdout.write(env_text(names, scan(SHIPPED_DIR, USER_DIR)))
        return 0
    out = argv[3] if len(argv) > 3 else os.path.join(
        CONFIG_DIR, 'moonraker-plugins.conf')
    names = read_enabled(plugins_file)[0]
    found = scan(SHIPPED_DIR, USER_DIR)
    write_if_changed(out, moonraker_text(names, found))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
