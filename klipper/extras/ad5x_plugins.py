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
# Skipped plugins: Klipper doesn't read plugins.cfg itself but
# plugins-active.cfg next to it (ad5x.cfg includes it): plugins.cfg with
# the include line of each enabled plugin that can't run commented out
# (missing, bad plugin.json or plugin.cfg, requires_os doesn't fit, a
# plugin it requires not loaded, a conflict with one listed before it, a
# plugin that drives the IFS while the IFS isn't on Klipper firmware, a
# second plugin that drives the IFS).
# So a skipped plugin's config, extras and Moonraker part all stay out,
# with one warning each. Written before each config read (every start,
# RESTART, FIRMWARE_RESTART: host Klipper patch 0009 calls
# before_config_read, so hand edits of plugins.cfg take effect then), when
# plugins change, and by S61klipper before Klipper starts ("ad5x_plugins.py
# klipper", for a Klipper without patch 0009). plugins.cfg is never
# changed for this. With an older ad5x.cfg that still includes plugins.cfg
# itself (a newer daily Klipper package on an older OS) the list isn't
# written and a skipped plugin's config is still read, as before.
#
# Extras: Klipper loads modules only from klippy/extras (read-only image).
# This module, loaded before the plugins' sections (ad5x.cfg declares it
# before including plugins.cfg), imports each enabled plugin's
# extras/<module>.py as extras.<module> and creates the objects for its
# config sections the way Klipper's load_object does. Only enabled,
# compatible plugins' code is loaded; a module name Klipper already has is
# refused. No Klipper change needed. Plugin API 1.5: a plugin's extras/ may
# hold packages (extras/<name>/__init__.py; the plugin's extras/ joins the
# extras package path, so its modules import each other as Klipper's do),
# and printer.load_object() also finds plugin modules.
# Plugin API 1.7: module names may have capitals (AFC_lane), and
# plugin.json "module_dirs" lists more folders of Klipper modules inside
# the plugin (a checkout of another project, e.g. AFC-Klipper-Add-On/extras).
# They join the extras package path too, but their modules are imported
# the way Klipper imports its own extras: only when a config section or
# printer.load_object() names one, or another module imports it. A missing
# folder, or one that a link leads out of the plugin folder, is a warning
# and is not read. A module name Klipper has, in any case (Heaters), is
# refused, and so are two modules whose names differ only in case.
#
# Name collisions between running plugins: an extras module two plugins
# have stops Klipper (above). A Moonraker component or python/ library two
# plugins have is the first one's (plugins.cfg order), a Klipper section
# two plugins define is merged (the later one's options win): no error, so
# Klipper shows one warning each (collisions), except for a section of a
# plugin the later one requires.
#
# Reserved names (plugin API 1.6): kiln_ and ad5x_ are kept for Kiln OS and
# its official plugins (shipped, or in the catalog from Kiln's own
# repositories). Any other plugin with an extras module, Moonraker
# component, plugin.cfg section or macro starting with one of them can't be
# enabled and is skipped, like a plugin with a bad plugin.json
# (reserved_names; tools/check_plugin.py reports the same).
#
# IFS owner (plugin API 1.5): a plugin with "owns_ifs": true in plugin.json
# drives the IFS itself (e.g. Happy Hare) instead of Kiln's [ifs] module.
# It needs the IFS on Klipper firmware (S61klipper writes IFS_KLIPPER_FLAG
# when the IFS answers as Klipper; without it the owner is skipped, so
# Kiln's [ifs] runs the IFS as if the plugin were off; plan, with the
# same flag in S61klipper, Klipper and S62moonraker), and its plugin.cfg
# sets [ifs] enable:
# False and brings its own [mcu ifs] and pins. Kiln's IFS pins
# (generic-flashforge-ifs.cfg, linked into IFS_MCU_DIR, which ifs.cfg
# includes) are then left out: sync_ifs_mcu keeps the link in step with
# plugins.cfg, at boot (S61klipper: "ad5x_plugins.py ifs-mcu") and
# whenever plugins change. One owner at a time: ENABLE_PLUGIN refuses a
# second one, and a second one enabled by hand is skipped like a conflict
# (plan: the first in plugins.cfg drives the IFS, one warning).
#
# Moonraker: run as a script (S62moonraker does, before Moonraker starts)
# it writes moonraker-plugins.conf, the [include] list of the enabled
# plugins' moonraker.conf files; Klipper rewrites it when plugins change.
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
# Pinned entries (plugin API 1.11): a catalog entry may name a commit (40
# hex digits). INSTALL_PLUGIN then checks out exactly that commit (fetching
# it if the default branch doesn't have it) and UPDATE_PLUGIN fetches and
# moves to the catalog's commit, never to whatever the author pushed last;
# a new commit comes with a new catalog (a Kiln OS update). Community
# plugins (not from Kiln's own repositories) are always pinned: the build
# refuses a catalog without it (tools/test_plugin_catalog.py). Entries also
# carry author and community (docs/plugins.md "Community plugins").
# Submodules (plugin API 1.7, issue #69): a plugin with a .gitmodules gets
# its submodules after the clone or pull (git submodule update --init
# --recursive, in the same background job), https only: .gitmodules is
# checked first and git refuses every other transport (submodule_errors,
# SUBMODULE_PROTOCOLS). A failure leaves nothing installed, or puts the
# previous version back (UPDATE_PLUGIN). REMOVE_PLUGIN deletes them with
# the plugin's folder (their git data is in its .git/modules).
#
# Root scripts (plugin API 1.6, zMod's model; docs/plugin-root-hooks.md): a
# plugin may ship root/install.sh, root/update.sh and root/uninstall.sh.
# Klipper runs as klipper, so it asks the root update agent
# (S68ad5x-update-agent, lib/plugin-root.sh): it packs the plugin's root/
# folder into AGENT_DIR/plugin-<name>.tar, writes AGENT_DIR/plugin-request
# (action, name, sha256) and waits for AGENT_DIR/plugin-status (a timer, at
# most ROOT_WAIT; printer.ad5x_plugins.job meanwhile). Root runs the
# script from its own copy, PLUGINS_ROOT_DIR/<name>, never from the
# plugin's folder.
#   ENABLE_PLUGIN       a plugin with root scripts needs ROOT=1 (they run as
#                       root); install.sh runs first, and only when it says
#                       ok is plugins.cfg written and Klipper restarted
#   klippy:ready        an enabled plugin whose root/ differs from root's
#                       copy (its .sha256), after UPDATE_PLUGIN or
#                       Moonraker's update manager: update.sh runs by itself
#                       when root/ is what git checked out (or the plugin is
#                       shipped); a root/ changed any other way (uploaded in
#                       Fluidd's file manager, copied by hand) only gets a
#                       warning: ENABLE_PLUGIN NAME= ROOT=1 runs update.sh
#   DISABLE_PLUGIN,     uninstall.sh (root's copy) runs, then the plugin is
#   REMOVE_PLUGIN       switched off or removed, whatever it answered
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import configparser
import errno
import hashlib
import importlib
import io
import json
import logging
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile

# The plugin API this system offers (docs/plugin-api.md): major.minor.
# Minor: additions only. Major: something plugins may use changed or went.
# post-build.sh copies it to /usr/lib/os-release as AD5X_PLUGIN_API.
PLUGIN_API_VERSION = "1.12"

CONFIG_DIR = "/home/klipper/printer_data/config"
SHIPPED_DIR = "/usr/share/ad5x/plugins"
USER_DIR = "/data/ad5x/plugins"
# INSTALL_PLUGIN clones here first, then moves the finished plugin into
# USER_DIR in one rename. Not inside USER_DIR: Moonraker watches it (as
# config/plugins) and warned about the half-cloned folders it saw vanish
# ("Error adding inotify watch"). Same file system as USER_DIR (/data), and
# not one of Moonraker's roots.
STAGING_DIR = "/home/klipper/printer_data/plugin-staging"
# Seconds between checks of USER_DIR for plugins added or removed by hand
DIR_CHECK = 2.

def dir_mtime(path):
    """The directory's change time, None when it isn't there."""
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None
CATALOG_FILE = "/usr/share/ad5x/plugin-catalog.json"
# Picked up by S68ad5x-update-agent (root), which restarts Moonraker
MOONRAKER_RESTART_FILE = "/data/ad5x/kiln-update/restart-moonraker"
GIT_TIMEOUT = 600.
# Submodules (issue #69): INSTALL_PLUGIN and UPDATE_PLUGIN fetch a
# plugin's git submodules, over these transports only (GIT_ALLOW_PROTOCOL:
# git itself refuses file, ssh, git, http and ext:: for the submodules and
# theirs, whose .gitmodules can't be checked before they are fetched).
# The tests add "file"; nothing on the printer changes it.
SUBMODULE_PROTOCOLS = "https"
# Local git steps (sync, status, going back after a failed update)
GIT_LOCAL_TIMEOUT = 60.
# IFS owner: Kiln's IFS pins are linked into IFS_MCU_DIR (ifs.cfg includes
# it) while the IFS answers as Klipper (IFS_KLIPPER_FLAG, written by
# S61klipper) and no enabled plugin owns the IFS
IFS_MCU_DIR = "/run/ad5x/ifs-mcu"
IFS_KLIPPER_FLAG = "/run/ad5x/ifs-klipper"
# Why an IFS owner is skipped while the IFS doesn't answer as Klipper
IFS_NOT_KLIPPER = ("drives the IFS, which needs the IFS on Klipper "
                   "firmware, and the IFS didn't answer as Klipper at this "
                   "boot: Kiln's IFS module runs it instead. To use the "
                   "plugin: /data/ad5x/ifs-klipper.enable, then reboot "
                   "(docs/mcu-flashing.md)")
GENERIC_IFS_CFG = "/usr/share/ad5x/config/generic-flashforge-ifs.cfg"
# The image's ad5x.cfg: whether it includes plugins-active.cfg (older
# ones include plugins.cfg itself)
FACTORY_CFG = "/usr/share/ad5x/config/ad5x.cfg"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
# Klipper module names (extras/, module_dirs): capitals allowed since
# plugin API 1.7 (AFC's AFC_lane, ...)
MODULE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# plugin.json module_dirs (plugin API 1.7): at most this many folders;
# each path part letters, digits, '_', '-' and '.', not starting with '.';
# not in the folders the plugin layout gives a meaning (the first part)
MODULE_DIRS_MAX = 8
MODULE_DIR_PART_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
MODULE_DIRS_KEPT = ('extras', 'python', 'moonraker', 'root')
# plugin.json keys read_metadata reads; others are ignored here and
# reported by tools/check_plugin.py
PLUGIN_JSON_KEYS = ('name', 'description', 'version', 'author', 'url',
                    'requires_os', 'requires', 'conflicts', 'owns_ifs',
                    'module_dirs')
# Name prefixes kept for Kiln OS and its official plugins (plugin API 1.6,
# docs/plugin-api.md "Names"): Klipper modules, Moonraker components,
# plugin.cfg sections and macros of any other plugin starting with them
# make it unusable (reserved_names; tools/check_plugin.py reports them).
# Official: shipped in the image, or in the catalog from one of Kiln's own
# repositories (OFFICIAL_URL_PREFIXES)
RESERVED_PREFIXES = ('ad5x_', 'kiln_')
RESERVED_MODULE_PREFIXES = RESERVED_PREFIXES
OFFICIAL_URL_PREFIXES = ('https://github.com/djvalic/kiln-',)
# A pinned catalog commit (plugin API 1.11): a full SHA-1
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
# git config key INSTALL_PLUGIN sets in a pinned install
PIN_GIT_KEY = "kiln.pinned"
# [include <dir>/<name>/plugin.cfg], with or without the glob brackets
INCLUDE_RE = re.compile(
    r"^\s*\[include\s+(?P<path>\S*/(?P<name>[A-Za-z0-9_.-]+)/"
    r"plugi(?:n|\[n\])\.cfg)\s*\]\s*$")
# print_stats states during which plugins can't be switched (it restarts)
BUSY_STATES = ("printing", "paused")

# Root scripts (docs/plugin-root-hooks.md): the scripts a plugin's root/
# folder may hold, root's copies of those folders, the root update agent's
# folder (requests, answers) and the most root takes
ROOT_HOOKS = ('install.sh', 'update.sh', 'uninstall.sh')
PLUGINS_ROOT_DIR = "/data/ad5x/plugins-root"
AGENT_DIR = "/data/ad5x/kiln-update"
ROOT_TAR_MAX = 8 << 20
# How long Klipper waits for root's answer: root gives a script 300 s, and
# the agent may be busy with something else for a moment first
ROOT_WAIT = 360.

# Plugin extras dirs on the extras package path and the plugin modules
# loaded, at this start (a RESTART runs in the same process)
_PLUGIN_EXTRAS_DIRS = []
_PLUGIN_MODULES = set()

PLUGINS_HEADER = """\
# Plugins enabled on this printer (docs/plugins.md). Written by
# ENABLE_PLUGIN / DISABLE_PLUGIN; hand edits are kept. One [include] line
# per plugin; the [n] makes the path a pattern, so a plugin that is gone
# is skipped instead of stopping Klipper. System updates never change
# this file.
"""

# What Klipper reads (ad5x.cfg includes it), next to plugins.cfg so that
# relative includes there mean the same
ACTIVE_NAME = "plugins-active.cfg"
ACTIVE_HEADER = """\
# The plugins Klipper loads (docs/plugins.md): plugins.cfg with the
# enabled plugins that can't run left out, and why. Written from
# plugins.cfg when Klipper starts and when plugins change; don't edit it,
# edit plugins.cfg.
"""
# plugins.cfg, shipped and user dir and the factory config of the last
# start in this process; before_config_read uses them (else the defaults)
_ACTIVE_SOURCE = {}

MOONRAKER_HEADER = """\
# Moonraker parts of the enabled plugins (docs/plugins.md). Generated from
# plugins.cfg when Moonraker starts and when plugins change; don't edit.
# Moonraker reads it after moonraker.conf (S62moonraker).
"""

# Most a plugin file or plugins.cfg can hold (read_regular)
READ_LIMIT = 1 << 20

def read_regular(path, limit=READ_LIMIT):
    """The text of a regular file, at most limit bytes. Opened without
    blocking and checked on the open file: plugins.cfg and the plugins'
    files are klipper's, and root reads them at boot (S61klipper,
    S62moonraker), so a FIFO there must not stop the boot. OSError when
    missing, unreadable or not a regular file; ValueError when not UTF-8."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("not a regular file")
        chunks, size = [], 0
        while size < limit:
            chunk = os.read(fd, min(1 << 16, limit - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8")

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
            'owns_ifs': False, 'module_dirs': [], 'error': None}
    path = os.path.join(plugin_dir, 'plugin.json')
    try:
        data = json.loads(read_regular(path))
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
    meta['owns_ifs'] = data.get('owns_ifs') is True
    dirs, dirs_error = parse_module_dirs(data.get('module_dirs'))
    meta['module_dirs'] = dirs
    if data.get('name') not in (None, name):
        meta['error'] = "plugin.json name '%s' differs from the directory" % (
            data.get('name'),)
    elif meta['requires_os'] and parse_version(meta['requires_os']) is None:
        meta['error'] = "requires_os '%s' is not major.minor" % (
            meta['requires_os'],)
    elif dirs_error:
        meta['error'] = "plugin.json: module_dirs: %s" % (dirs_error,)
    return meta

def parse_module_dirs(val):
    """(folders, error) for plugin.json module_dirs: a list of folders
    inside the plugin, relative to it, '/' separated ("AFC/extras"). Each
    part matches MODULE_DIR_PART_RE (so no "..", no hidden folders, no
    spaces); no absolute paths; not extras/, python/, moonraker/ or root/
    or a folder in them (MODULE_DIRS_KEPT); at most MODULE_DIRS_MAX.
    ([], None) when the key is absent."""
    if val is None:
        return [], None
    if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
        return [], "must be a list of folder names"
    if len(val) > MODULE_DIRS_MAX:
        return [], "at most %d folders" % (MODULE_DIRS_MAX,)
    out = []
    for v in val:
        parts = [p for p in v.split('/') if p not in ('', '.')]
        if v.startswith('/') or not parts or not all(
                MODULE_DIR_PART_RE.match(p) for p in parts):
            return [], "'%s' is not a folder inside the plugin" % (v,)
        if parts[0] in MODULE_DIRS_KEPT:
            return [], "'%s': %s/ has its own use in a plugin" % (
                v, parts[0])
        rel = '/'.join(parts)
        if rel not in out:
            out.append(rel)
    return out, None

def inside(path, base):
    """Whether path, with links followed, is base or inside it."""
    real, top = os.path.realpath(path), os.path.realpath(base)
    return real == top or real.startswith(top.rstrip(os.sep) + os.sep)

def module_dirs(plugin_dir):
    """The plugin's extra module folders (plugin.json module_dirs) as
    absolute paths, whether they exist or not; [] when plugin.json has none
    or can't be read."""
    meta = read_metadata(plugin_dir, os.path.basename(plugin_dir))
    return [os.path.join(plugin_dir, *d.split('/'))
            for d in meta['module_dirs']]

def unknown_keys(data):
    """plugin.json keys this plugin manager doesn't read, sorted."""
    return sorted(k for k in data if k not in PLUGIN_JSON_KEYS)

def cfg_error(path):
    """Why Klipper's config parser would stop on a plugin.cfg (comments
    cut at '#' and parsed as Klipper does), or None. Includes inside it
    aren't followed."""
    try:
        text = read_regular(path)
    except (OSError, ValueError) as e:
        return "plugin.cfg: %s" % (e,)
    text = "\n".join(line.split('#', 1)[0] for line in text.split('\n'))
    parser = configparser.RawConfigParser(
        strict=False, inline_comment_prefixes=(';', '#'))
    try:
        parser.read_string(text, path)
    except configparser.Error as e:
        return "plugin.cfg doesn't parse: %s" % (
            " ".join(str(e).split())[:200],)
    return None

def extras_modules(ext_dir):
    """(module name, file name) for each module (<name>.py) and package
    (<name>/__init__.py) in a plugin's extras/, by file name. The loader
    takes only names that match MODULE_RE."""
    out = []
    for fn in sorted(os.listdir(ext_dir)):
        if fn.endswith('.py') and os.path.isfile(os.path.join(ext_dir, fn)):
            out.append((fn[:-3], fn))
        elif os.path.isfile(os.path.join(ext_dir, fn, '__init__.py')):
            out.append((fn, fn))
    return out

def is_official(name, source, catalog):
    """Kiln OS's own plugin: shipped with the image, or a catalog entry
    (read_catalog) from one of Kiln's own repositories."""
    if source == 'shipped':
        return True
    entry = catalog.get(name)
    return bool(entry) and entry['url'].startswith(OFFICIAL_URL_PREFIXES)

def reserved_names(plugin_dir):
    """Where a plugin uses a name kept for Kiln OS (RESERVED_PREFIXES), as
    the loader reads it: extras/ modules and packages, Moonraker
    components, plugin.cfg sections ([kiln_x], [ad5x_x name]) and macros
    ([gcode_macro KILN_X], any case, leading _ ignored). A list of
    "extras/kiln_x.py", "moonraker/components/kiln_x.py",
    "plugin.cfg [kiln_x]"; [] when there is none."""
    out = []
    for ext in [os.path.join(plugin_dir, 'extras')] + module_dirs(plugin_dir):
        if os.path.isdir(ext):
            rel = os.path.relpath(ext, plugin_dir).replace(os.sep, '/')
            out += ["%s/%s" % (rel, fn) for mod, fn in extras_modules(ext)
                    if MODULE_RE.match(mod)
                    and mod.lower().startswith(RESERVED_PREFIXES)]
    comps = os.path.join(plugin_dir, 'moonraker', 'components')
    for mod in _module_names(comps):
        if mod.lower().startswith(RESERVED_PREFIXES):
            fn = mod + '.py' if os.path.isfile(
                os.path.join(comps, mod + '.py')) else mod
            out.append("moonraker/components/%s" % (fn,))
    for sec in _cfg_sections(os.path.join(plugin_dir, 'plugin.cfg')):
        words = sec.split()
        name = words[0].lower()
        if name == 'gcode_macro' and len(words) > 1:
            name = words[1].lower().lstrip('_')
        if name.startswith(RESERVED_PREFIXES):
            out.append("plugin.cfg [%s]" % (sec,))
    return out

def reserved_error(names):
    """The plugin's error for reserved_names(), None when there are none."""
    if not names:
        return None
    return ("uses names kept for Kiln OS and its official plugins (%s): %s; "
            "start them with the plugin's name" % (
                ", ".join(RESERVED_PREFIXES), ", ".join(names)))

def is_core_module(mod, core_dir):
    """Whether Klipper's extras (core_dir) already have this module, in
    any case (plugin API 1.7: a plugin's Heaters would be taken for
    Klipper's heaters)."""
    try:
        names = os.listdir(core_dir)
    except OSError:
        return False
    low = mod.lower()
    for fn in names:
        if fn.lower() == low + '.py' or (fn.lower() == low and os.path.isdir(
                os.path.join(core_dir, fn))):
            return True
    return False

def scan(shipped_dir=SHIPPED_DIR, user_dir=USER_DIR,
         roots_dir=PLUGINS_ROOT_DIR, catalog_file=CATALOG_FILE):
    """name -> info for every directory holding a plugin.cfg; user plugins
    replace shipped ones of the same name. 'root': the plugin has root
    scripts; 'root_installed': root has its copy of them (roots_dir).
    'official': shipped, or from Kiln's own repositories (catalog_file);
    any other plugin with names kept for Kiln OS gets an 'error'."""
    found = {}
    catalog = read_catalog(catalog_file)
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
            if not info['error']:
                info['error'] = cfg_error(os.path.join(d, 'plugin.cfg'))
            official = is_official(name, source, catalog)
            if not info['error'] and not official:
                info['error'] = reserved_error(reserved_names(d))
            info.update({
                'dir': d, 'source': source, 'official': official,
                'compatible': api_compatible(info['requires_os']),
                'extras': os.path.isdir(os.path.join(d, 'extras')),
                'module_dirs': [os.path.join(d, *m.split('/'))
                                for m in info['module_dirs']],
                'moonraker': os.path.isfile(os.path.join(d,
                                                         'moonraker.conf')),
                'python': os.path.isdir(os.path.join(d, 'python')),
                'components': os.path.isdir(os.path.join(
                    d, 'moonraker', 'components')),
                'root': has_root(d),
                'root_installed': os.path.isdir(os.path.join(roots_dir,
                                                             name)),
                # plugin API 1.11: installed pinned from the catalog
                'pinned': source == 'user' and is_pinned(d)})
            found[name] = info
    return found

def read_enabled(plugins_file):
    """(enabled names in file order, lines); a missing file is empty
    (lines None). Anything but a readable regular file counts as missing,
    with a warning."""
    try:
        lines = read_regular(plugins_file).splitlines()
    except FileNotFoundError:
        return [], None
    except (OSError, ValueError) as e:
        logging.warning("ad5x_plugins: %s unusable, no plugins enabled: %s",
                        plugins_file, e)
        return [], None
    names = []
    for line in lines:
        m = INCLUDE_RE.match(line)
        if m is not None and m.group('name') not in names:
            names.append(m.group('name'))
    return names, lines

def ifs_klipper(flag=None):
    """Whether the IFS answered as Klipper at this boot (flag, default
    IFS_KLIPPER_FLAG as it is when called: S61klipper's script mode)."""
    return os.path.exists(IFS_KLIPPER_FLAG if flag is None else flag)

def plan(names, found, dirs=None, ifs_flag=None):
    """(the enabled plugins that run, in plugins.cfg order; name -> why
    each other enabled plugin is skipped). Skipped: missing, a bad
    plugin.json or plugin.cfg, requires_os that doesn't fit, a required
    plugin that isn't loaded (also when it is skipped itself), a conflict
    with a plugin listed before it, owns_ifs while the IFS doesn't answer
    as Klipper (ifs_flag missing, ifs_klipper) or when a plugin listed
    before it drives the IFS already (only one can)."""
    skipped = {}
    on_klipper = None
    for name in names:
        info = found.get(name)
        if info is None:
            skipped[name] = "enabled but missing (no plugin.cfg in %s)" % (
                " or ".join(dirs or ("the plugin folders",)),)
        elif info['error']:
            skipped[name] = info['error']
        elif not info['compatible']:
            skipped[name] = "needs plugin API %s, this system has %s" % (
                info['requires_os'], PLUGIN_API_VERSION)
        elif info['owns_ifs']:
            if on_klipper is None:
                on_klipper = ifs_klipper(ifs_flag)
            if not on_klipper:
                skipped[name] = IFS_NOT_KLIPPER
    while True:
        active = [n for n in names if n not in skipped]
        for i, name in enumerate(active):
            info = found[name]
            missing = [r for r in info['requires'] if r not in active]
            clash = [c for c in active[:i] if c in info['conflicts']
                     or name in found[c]['conflicts']]
            owner = [c for c in active[:i]
                     if info['owns_ifs'] and found[c]['owns_ifs']]
            if missing:
                skipped[name] = "needs plugin %s, which is not loaded" % (
                    ", ".join(missing),)
                break
            if clash:
                skipped[name] = ("conflicts with %s, listed before it in "
                                 "plugins.cfg" % (", ".join(clash),))
                break
            if owner:
                skipped[name] = ("drives the IFS, and so does %s, listed "
                                 "before it in plugins.cfg; only one plugin "
                                 "can" % (owner[0],))
                break
        else:
            return active, skipped

def active_path(plugins_file):
    return os.path.join(os.path.dirname(plugins_file), ACTIVE_NAME)

def active_text(lines, skipped):
    """plugins-active.cfg: plugins.cfg's lines, a skipped plugin's include
    line commented out with the reason."""
    out = ACTIVE_HEADER.splitlines()
    for line in lines or []:
        m = INCLUDE_RE.match(line)
        if m is not None and m.group('name') in skipped:
            out.append("# skipped (%s): %s" % (
                " ".join(skipped[m.group('name')].split()), line.strip()))
        else:
            out.append(line)
    return "\n".join(out) + "\n"

def effective_lines(text):
    """The lines Klipper acts on (no comments, no blank lines)."""
    return [l.strip() for l in (text or "").splitlines()
            if l.strip() and not l.lstrip().startswith(('#', ';'))]

def write_active(plugins_file, shipped_dir=SHIPPED_DIR, user_dir=USER_DIR,
                 found=None, catalog_file=CATALOG_FILE, ifs_flag=None):
    """Write plugins-active.cfg from plugins.cfg as it is now. Returns
    (active names, skipped, the file's text before (None when it wasn't
    there), its text now). OSError when it can't be written."""
    if found is None:
        found = scan(shipped_dir, user_dir, catalog_file=catalog_file)
    names, lines = read_enabled(plugins_file)
    active, skipped = plan(names, found, (shipped_dir, user_dir), ifs_flag)
    path = active_path(plugins_file)
    try:
        before = read_regular(path)
    except (OSError, ValueError):
        before = None
    text = active_text(lines, skipped)
    write_if_changed(path, text)
    return active, skipped, before, text

def uses_active(factory_cfg=FACTORY_CFG):
    """Whether the factory config includes plugins-active.cfg. True when
    it can't be read (not this image's layout: tests, a plain Klipper)."""
    try:
        return "plugins-activ" in read_regular(factory_cfg)
    except (OSError, ValueError):
        return True

def before_config_read(printer=None):
    """Host Klipper patch 0009 calls this before Klipper reads its config
    (every start, RESTART, FIRMWARE_RESTART): plugins-active.cfg from
    plugins.cfg as it is now, so a hand edit applies at the restart, also
    when the last start stopped before [ad5x_plugins]. The paths of the
    last start in this process, else the defaults (the first start)."""
    src = dict(plugins_file=os.path.join(CONFIG_DIR, 'plugins.cfg'),
               shipped_dir=SHIPPED_DIR, user_dir=USER_DIR,
               factory_cfg=FACTORY_CFG, catalog_file=CATALOG_FILE,
               ifs_flag=None)
    src.update(_ACTIVE_SOURCE)
    if not uses_active(src.pop('factory_cfg')):
        return
    try:
        write_active(**src)
    except OSError as e:
        logging.info("ad5x_plugins: can't write %s: %s",
                     active_path(src['plugins_file']), e)

def _module_names(d):
    """Top-level importable names in a directory: name.py files and
    package directories."""
    try:
        entries = sorted(os.listdir(d))
    except OSError:
        return []
    out = []
    for fn in entries:
        if fn.endswith('.py') and MODULE_RE.match(fn[:-3]):
            out.append(fn[:-3])
        elif MODULE_RE.match(fn) and os.path.isfile(
                os.path.join(d, fn, '__init__.py')):
            out.append(fn)
    return out

def _cfg_sections(path):
    """Section names of a plugin.cfg as Klipper reads them (exact: a
    different spelling is another section), [] when unreadable."""
    try:
        text = read_regular(path)
    except (OSError, ValueError):
        return []
    text = "\n".join(line.split('#', 1)[0] for line in text.split('\n'))
    parser = configparser.RawConfigParser(
        strict=False, inline_comment_prefixes=(';', '#'))
    try:
        parser.read_string(text, path)
    except configparser.Error:
        return []
    return [s for s in parser.sections() if not s.startswith('include ')]

def collisions(names, found, ifs_flag=None):
    """Messages for names two running plugins (plan, plugins.cfg order)
    both bring, where one silently loses: a Moonraker component or a
    python/ library (the first plugin's is used), a Klipper config section
    (the later plugin's options replace the earlier one's; not reported
    when the later plugin requires the earlier one, which then is meant)."""
    msgs = []
    owners = {'component': {}, 'library': {}, 'section': {}}
    for name in plan(names, found, ifs_flag=ifs_flag)[0]:
        info = found[name]
        d = info['dir']
        kinds = (
            ('component', _module_names(os.path.join(
                d, 'moonraker', 'components')) if info['components'] else []),
            ('library', _module_names(os.path.join(d, 'python'))
             if info['python'] else []),
            ('section', _cfg_sections(os.path.join(d, 'plugin.cfg'))))
        for kind, items in kinds:
            for item in items:
                first = owners[kind].setdefault(item, name)
                if first == name:
                    continue
                if kind == 'component':
                    msgs.append("Plugins %s and %s both have Moonraker "
                                "component %s: Moonraker loads %s's"
                                % (first, name, item, first))
                elif kind == 'library':
                    msgs.append("Plugins %s and %s both have python/%s: "
                                "%s's is imported" % (first, name, item,
                                                      first))
                elif first not in info['requires']:
                    msgs.append("Plugins %s and %s both define [%s]: %s's "
                                "options replace %s's" % (first, name, item,
                                                          name, first))
                    owners[kind][item] = name
    return msgs

def ifs_owners(names, found):
    """Enabled plugins that drive the IFS themselves (owns_ifs)."""
    return [n for n in names if n in found and found[n]['owns_ifs']
            and not found[n]['error']]

def sync_ifs_mcu(names, found, mcu_dir=IFS_MCU_DIR, flag=IFS_KLIPPER_FLAG,
                 cfg=GENERIC_IFS_CFG):
    """Link Kiln's IFS pins (cfg) into mcu_dir while the IFS answers as
    Klipper (flag) and no enabled plugin owns the IFS; remove the link
    otherwise. True when it changed. OSError when mcu_dir can't be
    written."""
    want = os.path.exists(flag) and not ifs_owners(names, found)
    link = os.path.join(mcu_dir, os.path.basename(cfg))
    if want == os.path.lexists(link):
        return False
    if want:
        os.symlink(cfg, link)
    else:
        os.unlink(link)
    return True

def moonraker_text(names, found, ifs_flag=None, pinned_dir=None,
                   files=None):
    """The [include] list of the enabled plugins' moonraker.conf files.
    A pinned plugin's file without its own [update_manager] goes to
    pinned_dir/<name>.conf (added to files, path -> text) and is included
    from there: a file of its own, so a section two plugins have (or the
    [update_manager] below) is merged by Moonraker, not a duplicate."""
    if pinned_dir is None:
        pinned_dir = PINNED_MOONRAKER_DIR
    if files is None:
        files = {}
    lines = [MOONRAKER_HEADER.rstrip("\n")]
    updates = False
    for name in plan(names, found, ifs_flag=ifs_flag)[0]:
        info = found[name]
        if not info['moonraker']:
            continue
        path = os.path.join(info['dir'], 'moonraker.conf')
        try:
            text = read_regular(path)
        except (OSError, ValueError) as e:
            logging.warning("ad5x_plugins: %s skipped: %s", path, e)
            continue
        pinned = info.get('pinned') and without_update_manager(
            text, info['dir'])
        if pinned is not None and pinned is not False:
            # Pinned from the catalog: without its own update manager
            own = os.path.join(pinned_dir, name + ".conf")
            files[own] = pinned
            lines += ["# %s (pinned: its own [update_manager] left out)"
                      % (path,), "[include %s]" % (own,)]
            updates |= any(sect.startswith("update_manager")
                           for sect, _ in config_sections(pinned)[1:])
            continue
        updates |= any(sect.startswith("update_manager")
                       for sect, _ in config_sections(text)[1:])
        lines.append("[include %s]" % (path,))
    if updates:
        # Plugins kept up to date by Moonraker: this system has no package
        # manager for Moonraker's system updates.
        lines += ["[update_manager]", "enable_system_updates: False"]
    return "\n".join(lines) + "\n"

def write_moonraker(path, names, found, ifs_flag=None):
    """Write the Moonraker list at path and the pinned plugins' files
    (moonraker_text) in .kiln-pinned/ next to it, then remove old ones
    there. Runs as the klipper user (S62moonraker's step drops to it:
    the folder is klipper's). True if anything changed."""
    pdir = os.path.join(os.path.dirname(path), PINNED_DIR_NAME)
    files = {}
    text = moonraker_text(names, found, ifs_flag, pdir, files)
    try:
        st = os.lstat(pdir)
    except FileNotFoundError:
        st = None
    is_dir = st is not None and stat.S_ISDIR(st.st_mode)
    changed = False
    if files:
        if st is None:
            os.mkdir(pdir, 0o755)
        elif not is_dir:
            # Never written through a link (or into something else)
            raise OSError("%s isn't a folder" % (pdir,))
        for p, t in sorted(files.items()):
            changed |= write_if_changed(p, t)
    # The list before the clean-up: it never names a file already gone
    changed |= write_if_changed(path, text)
    if is_dir:
        for fn in os.listdir(pdir):
            p = os.path.join(pdir, fn)
            if fn.endswith(".conf") and p not in files:
                os.unlink(p)
                changed = True
    return changed

def drop_to_owner(folder):
    """As root, become the owner of folder (its group, no other groups)
    for good when that isn't root: the Moonraker list step at boot
    writes into klipper's config folder, and root mustn't follow anything
    placed there. A link counts as its own owner's (lstat). A root-owned
    folder (tests, the image check) needs no drop."""
    if os.geteuid() != 0:
        return
    st = os.lstat(folder)
    if st.st_uid == 0:
        return
    os.setgroups([])
    os.setgid(st.st_gid)
    os.setuid(st.st_uid)
    try:
        import pwd
        os.environ["HOME"] = pwd.getpwuid(st.st_uid).pw_dir
    except (ImportError, KeyError):
        pass

def plugin_paths(names, found, ifs_flag=None):
    """(python dirs, Moonraker component dirs) of the enabled plugins that
    run (plan), in plugins.cfg order."""
    python, components = [], []
    for name in plan(names, found, ifs_flag=ifs_flag)[0]:
        info = found[name]
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
    """name -> {title, description, url, requires_os, author, commit,
    community} of the catalog's valid entries (https git URLs; file:// for
    tests; commit, when given, 40 hex digits); a missing file is empty.
    community: not from one of Kiln's own repositories."""
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
        commit = p.get('commit') or ''
        if not isinstance(name, str) or not NAME_RE.match(name) or \
                not isinstance(url, str) or \
                not url.startswith(('https://', 'file://')) or \
                not isinstance(commit, str) or \
                (commit and not COMMIT_RE.match(commit)):
            continue
        out[name] = {'title': str(p.get('title') or name),
                     'description': str(p.get('description') or ''),
                     'url': url,
                     'requires_os': str(p.get('requires_os') or ''),
                     'author': str(p.get('author') or ''),
                     'commit': commit,
                     'community': not url.startswith(OFFICIAL_URL_PREFIXES)}
    return out

def is_pinned(plugin_dir):
    """Whether INSTALL_PLUGIN installed this plugin pinned to a catalog
    commit (PIN_GIT_KEY in its .git/config). A clone made by hand is not.
    Read from the file, not with git: root reads it at boot (S62moonraker)
    and git refuses a repository another user owns."""
    try:
        text = read_regular(os.path.join(plugin_dir, '.git', 'config'))
    except (OSError, ValueError):
        return False
    section, key = PIN_GIT_KEY.split('.')
    inside = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            inside = line.lower() == '[%s]' % (section,)
        elif inside and '=' in line:
            k, v = line.split('=', 1)
            if k.strip().lower() == key and v.strip().lower() == 'true':
                return True
    return False

SECTION_RE = re.compile(r"^\[[^\]]+\]")
# Moonraker's config reader (confighelper.py _parse_file): a section is
# r"\s*\[([^]]+)\]" after the inline comment (" #" or " ;") is cut
MOONRAKER_SECTION_RE = re.compile(r"\s*\[([^]]+)\]")
# Moonraker's user: a "~" in a plugin's moonraker.conf is this home
MOONRAKER_HOME = "/home/klipper"
# Next to moonraker-plugins.conf: pinned plugins' moonraker.conf without
# their own [update_manager], one file each (write_moonraker)
PINNED_DIR_NAME = ".kiln-pinned"
PINNED_MOONRAKER_DIR = os.path.join(CONFIG_DIR, PINNED_DIR_NAME)

def config_sections(text):
    """A Moonraker config file's sections as Moonraker reads them: a list
    of (section name, {option: (value, [line numbers])}), the part before
    the first section first with name "". Comments, inline comments
    (" #"/" ;" after a space), indented continuation lines and lower-case
    option names as in Moonraker's _parse_file. Each section also has its
    line numbers under the key None."""
    out = [("", {None: []})]
    opt_indent, last = -1, None
    for i, raw in enumerate(text.splitlines()):
        sect, opts = out[-1]
        if not raw.strip() or raw.lstrip()[0] in "#;":
            opts[None].append(i)
            continue
        line = raw.expandtabs(4)
        m = re.search(r" +[#;]", line)
        if m is not None:
            line = line[:m.start()]
        line = re.sub(r" \\(#|;)", r" \1", line)
        indent = len(line) - len(line.lstrip())
        if opt_indent != -1 and indent > opt_indent:
            # A value over several lines
            opts[None].append(i)
            if last is not None:
                value, at = opts[last]
                opts[last] = (value + "\n" + line.strip(), at + [i])
            continue
        m = MOONRAKER_SECTION_RE.match(line)
        if m is not None:
            opt_indent, last = -1, None
            # The name as Moonraker has it: "[ include x]" is no include
            out.append((m.group(1), {None: [i]}))
            continue
        opt_indent = indent
        parts = re.split(r"[:=]", line, 1)
        key, value = parts[0], parts[1] if len(parts) > 1 else ""
        last = key.strip().lower()
        opts[last] = (value.strip(), [i])
        opts[None].append(i)
    return out

def moonraker_path(value, home=MOONRAKER_HOME):
    """A path option as Moonraker's update manager reads it (expanduser
    for its user: "~" is home, "~name" that user's home), None when it
    isn't one."""
    if value.startswith("~"):
        user, slash, rest = value[1:].partition("/")
        if user:
            try:
                import pwd
                base = pwd.getpwnam(user).pw_dir
            except (ImportError, KeyError):
                return None
        else:
            base = home
        value = base + slash + rest
    if not value.startswith("/") or "\n" in value:
        return None
    return value

def own_entry_path(value, plugin_dir, home=MOONRAKER_HOME):
    """Whether an [update_manager] section's path names the plugin's own
    folder (config/plugins/NAME is a link to it)."""
    path = moonraker_path(value, home)
    return path is not None and (os.path.realpath(path)
                                 == os.path.realpath(plugin_dir))

def without_update_manager(text, plugin_dir, home=MOONRAKER_HOME):
    """A pinned plugin's moonraker.conf for Moonraker (plugin API 1.11):
    the [update_manager ...] section that updates the plugin itself (its
    path is the plugin's folder) left out, since Moonraker would check out
    the plugin's branch past the catalog's commit. Its other sections stay,
    other [update_manager]s too (mainsail-kiln's [update_manager mainsail]
    updates the Mainsail interface). Relative [include]s are made absolute
    (the text goes to a file of its own outside the plugin's folder).
    None when nothing is left out."""
    lines = text.splitlines()
    drop, dropped = set(), False
    for sect, opts in config_sections(text)[1:]:
        if sect == "update_manager" or sect.startswith("update_manager "):
            value = opts.get("path", ("", []))[0]
            if own_entry_path(value, plugin_dir, home):
                drop.update(opts[None])
                dropped = True
        elif sect.startswith("include "):
            inc = sect[8:].strip()
            if inc and not inc.startswith("/"):
                lines[opts[None][0]] = "[include %s]" % (
                    os.path.join(plugin_dir, inc),)
    if not dropped:
        return None
    return "\n".join(l for i, l in enumerate(lines) if i not in drop) + "\n"

def same_repo(a, b):
    """Whether two git URLs name the same repository (a trailing ".git" or
    "/" and the host's case aside). None when either is empty."""
    def norm(u):
        u = u.strip().rstrip('/')
        if u.endswith('.git'):
            u = u[:-4]
        head, sep, rest = u.partition('://')
        host, slash, path = rest.partition('/')
        return head.lower() + sep + host.lower() + slash + path
    if not a or not b:
        return None
    return norm(a) == norm(b)

def touches_moonraker(info):
    """A plugin whose switch changes what Moonraker loads."""
    return bool(info) and (info['moonraker'] or info['python']
                           or info['components'])

def write_if_changed(path, text):
    """Write text atomically unless the file already holds it. True if
    written."""
    try:
        if read_regular(path) == text:
            return False
    except (OSError, ValueError):
        pass
    # A new file, never one that is there (a link or a FIFO in klipper's
    # folder would be written through, or wait, as root at boot)
    tmp = path + ".tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o666)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return True

def has_root(plugin_dir):
    """The plugin ships root scripts (root/install.sh, update.sh or
    uninstall.sh)."""
    return any(os.path.isfile(os.path.join(plugin_dir, 'root', h))
               for h in ROOT_HOOKS)

def pack_root(root_dir, limit=ROOT_TAR_MAX):
    """(tar, sha256): the plugin's root/ folder as the uncompressed tar the
    root update agent unpacks (lib/plugin-root.sh). The same files always
    give the same bytes: names in order, no times or owners, modes 0755
    (folders, files with an execute bit) or 0644, so the sha256 says whether
    root/ changed since root made its copy (its .sha256). ValueError for
    anything but folders and plain files (a link, a FIFO) and over limit
    bytes; OSError when a file can't be read."""
    if os.path.islink(root_dir):
        raise ValueError("root/ is a link")
    buf = io.BytesIO()
    tar = tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT)
    def add(rel):
        for name in sorted(os.listdir(os.path.join(root_dir, rel))):
            path = os.path.join(rel, name) if rel else name
            full = os.path.join(root_dir, path)
            st = os.lstat(full)
            ti = tarfile.TarInfo(path)
            ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = 0, 0, 0, "", ""
            if stat.S_ISDIR(st.st_mode):
                ti.type, ti.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(ti)
                add(path)
            elif stat.S_ISREG(st.st_mode):
                ti.mode = 0o755 if st.st_mode & 0o111 else 0o644
                # no link followed, no FIFO waited for (opened, then checked)
                fd = os.open(full, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, 'rb') as f:
                    if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                        raise ValueError("root/%s changed while read" % path)
                    data = f.read(limit + 1)
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
            else:
                raise ValueError("root/%s is not a plain file or folder "
                                 "(links, FIFOs and devices are refused)"
                                 % (path,))
            if buf.tell() > limit:
                raise ValueError("root/ is over %d MB" % (limit >> 20,))
    add("")
    tar.close()
    data = buf.getvalue()
    if len(data) > limit:
        raise ValueError("root/ is over %d MB" % (limit >> 20,))
    return data, hashlib.sha256(data).hexdigest()

def root_from_git(plugin_dir):
    """Whether the plugin's root/ is what its git checkout holds: the
    plugin folder is a git clone and git sees nothing changed, new or
    ignored in root/. Files put there any other way (uploaded in Fluidd's
    file manager, copied by hand) make it False, and so does a git that
    can't answer."""
    if not os.path.isdir(os.path.join(plugin_dir, '.git')):
        return False
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    env.setdefault('HOME', '/home/klipper')
    try:
        res = subprocess.run(
            ['git', '-C', plugin_dir, 'status', '--porcelain', '--ignored',
             '--untracked-files=all', '--', 'root'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and not res.stdout.strip()

# Submodules (issue #69): a plugin that carries another project as a git
# submodule (afc-kiln: AFC-Klipper-Add-On, read through module_dirs) gets
# it with INSTALL_PLUGIN and UPDATE_PLUGIN, so Klipper's first start needs
# no network. The plugin's folder is a trust boundary: its .gitmodules is
# checked first (https URLs only, relative ones resolved against the
# plugin's own URL and kept on its host, paths inside the plugin), and git
# runs with SUBMODULE_PROTOCOLS as the only transports allowed.
def submodule_env(protocols=None):
    """Environment additions for git commands that may fetch submodules:
    only SUBMODULE_PROTOCOLS (or protocols) allowed, URLs taken as not
    typed by a person (git's own rule for submodules), never a prompt."""
    return {'GIT_ALLOW_PROTOCOL': protocols or SUBMODULE_PROTOCOLS,
            'GIT_PROTOCOL_FROM_USER': '0', 'GIT_TERMINAL_PROMPT': '0'}

def submodule_git(plugin_dir):
    """git for submodule commands in plugin_dir. The file and ext::
    transports are also refused in git's config (GIT_ALLOW_PROTOCOL from
    submodule_env overrides this, so it holds without it too)."""
    return ['git', '-c', 'protocol.file.allow=never',
            '-c', 'protocol.ext.allow=never', '-C', plugin_dir]

def has_submodules(plugin_dir):
    return os.path.lexists(os.path.join(plugin_dir, '.gitmodules'))

def submodule_update_argv(plugin_dir):
    """git submodule update --init --recursive for the plugin; shallow
    (--depth 1) when the plugin's own clone is."""
    argv = submodule_git(plugin_dir) + ['submodule', '--quiet', 'update',
                                        '--init', '--recursive']
    if os.path.exists(os.path.join(plugin_dir, '.git', 'shallow')):
        argv += ['--depth', '1']
    return argv

def git_output(text):
    """git's output without the lines about git-sh-i18n--envsubst: the
    image leaves that program out (post-build.sh), and git submodule's
    shell part asks for it only for its usage text, at each start."""
    return "\n".join(l for l in text.splitlines()
                     if "sh-i18n--envsubst" not in l).strip()

def run_git(argv, extra_env=None, timeout=GIT_LOCAL_TIMEOUT, data=None):
    """(rc, output) of a short git command (stdout and stderr together);
    rc None when git can't run or takes longer than timeout."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    env.update(extra_env or {})
    env.setdefault('HOME', '/home/klipper')
    try:
        res = subprocess.run(
            argv, input=data, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=env, timeout=timeout,
            stdin=None if data is not None else subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    return res.returncode, git_output(res.stdout.decode('utf-8',
                                                        'replace'))

def submodule_state(plugin_dir):
    """git submodule status --recursive (local, no network): which commit
    each submodule is at, or "" when the plugin has none (or git can't
    tell). Compared before and after UPDATE_PLUGIN."""
    if not has_submodules(plugin_dir):
        return ""
    rc, out = run_git(submodule_git(plugin_dir)
                      + ['submodule', 'status', '--recursive'],
                      submodule_env())
    return out if rc == 0 else ""

def resolve_submodule_url(url, parent):
    """A .gitmodules URL as git fetches it: a relative one (./x, ../x)
    resolved against the plugin's own URL parent the way git does (each
    ../ drops one folder of it). None when it can't be resolved: no
    parent, or more ../ than parent has folders (it would leave the
    host)."""
    if not url.startswith(('./', '../')):
        return url
    m = re.match(r'^([A-Za-z][A-Za-z0-9+.-]*://[^/]*)(/.*)?$', parent or '')
    if not m:
        return None
    base = m.group(1)
    path = [p for p in (m.group(2) or '').split('/') if p]
    rest = url
    while rest.startswith(('./', '../')):
        if rest.startswith('../'):
            if not path:
                return None
            path.pop()
            rest = rest[3:]
        else:
            rest = rest[2:]
    parts = [p for p in rest.split('/') if p]
    if not parts or any(p in ('.', '..') for p in parts):
        return None
    return base + '/' + '/'.join(path + parts)

def read_gitmodules(plugin_dir):
    """{name: {'path', 'url', 'update', ...}} from the plugin's .gitmodules
    as git reads it (git config: no include directives with -f). {} when
    there is none. ValueError when it can't be read (a link, not UTF-8,
    git refuses it)."""
    path = os.path.join(plugin_dir, '.gitmodules')
    if not os.path.lexists(path):
        return {}
    if os.path.islink(path):
        raise ValueError("it is a link")
    try:
        text = read_regular(path)
    except OSError as e:
        raise ValueError(str(e))
    rc, out = run_git(['git', 'config', '-f', '-', '-z', '--get-regexp',
                       r'^submodule\.'], data=text.encode('utf-8'))
    if rc == 1 and not out:
        return {}
    if rc != 0:
        raise ValueError("git can't read it: %s" % (out[-200:],))
    subs = {}
    for item in out.split('\0'):
        if not item:
            continue
        key, _, val = item.partition('\n')
        name, _, var = key[len('submodule.'):].rpartition('.')
        if name:
            subs.setdefault(name, {})[var] = val
    return subs

def submodule_errors(plugin_dir, parent=None):
    """Why INSTALL_PLUGIN / UPDATE_PLUGIN won't fetch the plugin's
    submodules: one text per problem in its .gitmodules, [] when it has
    none or all are fine. parent: the plugin's own git URL (what relative
    submodule URLs are resolved against). Allowed: URLs of
    SUBMODULE_PROTOCOLS (https://), and ./ ../ relative ones that resolve
    to one on the plugin's own host; paths inside the plugin; no
    "update = !command"."""
    try:
        subs = read_gitmodules(plugin_dir)
    except ValueError as e:
        return [".gitmodules: %s" % (e,)]
    schemes = tuple(p + '://' for p in SUBMODULE_PROTOCOLS.split(':') if p)
    errors = []
    for name in sorted(subs):
        sub = subs[name]
        url, path = sub.get('url', ''), sub.get('path', '')
        what = "submodule '%s'" % (name,)
        if not url:
            errors.append("%s has no url" % (what,))
        elif any(ord(c) < 32 for c in url):
            errors.append("%s: its url has control characters" % (what,))
        else:
            full = resolve_submodule_url(url, parent)
            if full is None:
                errors.append("%s: url '%s' leads out of the plugin's host "
                              "or has no https URL to be relative to"
                              % (what, url))
            elif not full.startswith(schemes):
                errors.append("%s: url '%s' is not https:// (only https "
                              "submodules are fetched)" % (what, url))
        parts = path.replace('\\', '/').split('/')
        if not path or path.startswith('/') or '\\' in path or any(
                p in ('', '.', '..') for p in parts) or \
                parts[0].lower() == '.git' or any(
                ord(c) < 32 for c in path):
            errors.append("%s: path '%s' is not a folder inside the plugin"
                          % (what, path))
        if sub.get('update', '').startswith('!'):
            errors.append("%s: update = !command is refused" % (what,))
    return errors

def write_new(path, data):
    """data (bytes) into path as a new file, renamed into place: a link or
    a FIFO someone put at path is replaced, never written through."""
    tmp = os.path.join(os.path.dirname(path),
                       "." + os.path.basename(path) + ".tmp")
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)

def unlink_quiet(path):
    try:
        os.unlink(path)
    except OSError:
        pass

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
        self.staging_dir = config.get('staging_dir', STAGING_DIR)
        self.catalog_file = config.get('catalog_file', CATALOG_FILE)
        self.restart_file = config.get('moonraker_restart_file',
                                       MOONRAKER_RESTART_FILE)
        self.ifs_mcu_dir = config.get('ifs_mcu_dir', IFS_MCU_DIR)
        self.ifs_klipper_flag = config.get('ifs_klipper_flag',
                                           IFS_KLIPPER_FLAG)
        self.generic_ifs_cfg = config.get('generic_ifs_cfg', GENERIC_IFS_CFG)
        self.factory_cfg = config.get('factory_cfg', FACTORY_CFG)
        # Root scripts: root's copies, the root update agent's folder
        self.roots_dir = config.get('plugins_root_dir', PLUGINS_ROOT_DIR)
        self.agent_dir = config.get('agent_dir', AGENT_DIR)
        self.root_done = None
        self.root_updates = []
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
        self.found = self._scan()
        # A plugin cloned by hand shows up without a command: the status
        # (the touch screen's Plugins page, Fluidd) rescans when the user
        # plugin folder changed, checked at most every DIR_CHECK seconds
        self.user_dir_mtime = dir_mtime(self.user_dir)
        self.next_dir_check = 0.
        # Enabled at this start (plugins.cfg as Klipper read it)
        self.loaded = read_enabled(self.plugins_file)[0]
        # Of those, the ones that run and the ones skipped (plan)
        self.active, self.skipped = plan(self.loaded, self.found,
                                         (self.shipped_dir, self.user_dir),
                                         self.ifs_klipper_flag)
        self.warnings = []
        self.modules = {}
        # Modules of the plugins' module_dirs, imported when first needed:
        # name -> (plugin, folder)
        self.lazy = {}
        # The plugin driving the IFS at this start ("": Kiln's [ifs])
        self.ifs_owner = (ifs_owners(self.active, self.found) or [""])[0]
        # Also while Klipper isn't ready: a plugin whose config stops
        # Klipper can be disabled from the console (also when the error is
        # raised below, by the IFS owner check or a plugin's extras)
        for cmd in ("ENABLE_PLUGIN", "DISABLE_PLUGIN", "LIST_PLUGINS"):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        when_not_ready=True,
                                        desc=getattr(self, "cmd_%s_help" % cmd))
        self._start_active()
        self._check_ifs_owner(config)
        self._load_extras(config)
        self.printer.register_event_handler("klippy:ready",
                                            self._handle_ready)
        for cmd in ("INSTALL_PLUGIN", "UPDATE_PLUGIN", "REMOVE_PLUGIN"):
            self.gcode.register_command(cmd, getattr(self, "cmd_" + cmd),
                                        desc=getattr(self, "cmd_%s_help" % cmd))
    # Startup
    def _scan(self):
        return scan(self.shipped_dir, self.user_dir, self.roots_dir,
                    self.catalog_file)
    def _warn(self, msg):
        logging.warning("ad5x_plugins: %s", msg)
        self.warnings.append(msg)
        pconfig = self.printer.lookup_object('configfile', None)
        if pconfig is not None and hasattr(pconfig, 'runtime_warning'):
            pconfig.runtime_warning(msg)
    def _start_active(self):
        """One warning per skipped plugin; plugins-active.cfg brought up to
        date (patch 0009 wrote it just before this config read, S61klipper
        at boot: normally it already is)."""
        self.uses_active = uses_active(self.factory_cfg)
        # An older ad5x.cfg reads plugins.cfg itself: the config is loaded
        parts = ("config, extras and Moonraker part" if self.uses_active
                 else "extras and Moonraker part")
        for name in self.loaded:
            if name in self.skipped:
                self._warn("Plugin %s skipped: %s. Its %s are not loaded "
                           "(DISABLE_PLUGIN NAME=%s)"
                           % (name, self.skipped[name], parts, name))
        # Two plugins with the same component, library or section: one
        # loses without an error, so say which
        for msg in collisions(self.loaded, self.found,
                              self.ifs_klipper_flag):
            self._warn(msg)
        _ACTIVE_SOURCE.update(plugins_file=self.plugins_file,
                              shipped_dir=self.shipped_dir,
                              user_dir=self.user_dir,
                              factory_cfg=self.factory_cfg,
                              catalog_file=self.catalog_file,
                              ifs_flag=self.ifs_klipper_flag)
        if not self.uses_active:
            return
        try:
            before, text = write_active(
                self.plugins_file, self.shipped_dir, self.user_dir,
                self.found, ifs_flag=self.ifs_klipper_flag)[2:]
        except OSError as e:
            logging.info("ad5x_plugins: can't write %s: %s",
                         active_path(self.plugins_file), e)
            return
        if before is not None and \
                effective_lines(before) != effective_lines(text):
            self._warn("Plugins changed after Klipper read %s; RESTART to "
                       "load them as plugins.cfg says" % (ACTIVE_NAME,))
    def _write_active(self):
        """plugins-active.cfg from plugins.cfg now; the plugins that run."""
        if not self.uses_active:
            return plan(read_enabled(self.plugins_file)[0], self.found,
                        ifs_flag=self.ifs_klipper_flag)[0]
        try:
            return write_active(self.plugins_file, self.shipped_dir,
                                self.user_dir, self.found,
                                ifs_flag=self.ifs_klipper_flag)[0]
        except OSError as e:
            logging.info("ad5x_plugins: can't write %s: %s",
                         active_path(self.plugins_file), e)
            return plan(read_enabled(self.plugins_file)[0], self.found,
                        ifs_flag=self.ifs_klipper_flag)[0]
    def _sync_ifs_mcu(self, names):
        try:
            return sync_ifs_mcu(names, self.found, self.ifs_mcu_dir,
                                self.ifs_klipper_flag, self.generic_ifs_cfg)
        except OSError as e:
            logging.info("ad5x_plugins: can't update %s: %s",
                         self.ifs_mcu_dir, e)
            return False
    def _check_ifs_owner(self, config):
        """A plugin that owns the IFS: with Kiln's [ifs] off and Kiln's
        IFS pins left out. Kiln's IFS pins back when no plugin owns it.
        plan already skipped an owner while the IFS doesn't answer as
        Klipper, and a second one (the first in plugins.cfg drives the
        IFS)."""
        owners = ifs_owners(self.active, self.found)
        # plugins.cfg edited by hand since the link was set: Klipper has
        # read the old pins; fixed for the next start
        if self._sync_ifs_mcu(self.active):
            raise config.error(
                "The IFS changed hands (%s); RESTART to load its pins"
                % ("plugin " + owners[0] if owners
                   else "Kiln's IFS module",))
        if owners and self.printer.lookup_object('ifs', None) is not None:
            raise config.error(
                "Plugin %s drives the IFS: its plugin.cfg must set "
                "[ifs] enable: False" % (owners[0],))
    def _load_extras(self, config):
        core = os.path.dirname(os.path.abspath(__file__))
        # Libraries the plugins bring (python/), after Klipper's own
        for d in plugin_paths(self.loaded, self.found,
                              self.ifs_klipper_flag)[0]:
            if d not in sys.path:
                sys.path.append(d)
        wanted = {}
        lazy = {}
        # lower-case module name -> (plugin, "folder/file")
        seen = {}
        for name in self.active:
            info = self.found[name]
            dirs = []
            if info['extras']:
                dirs.append((os.path.join(info['dir'], 'extras'), wanted))
            for d in info.get('module_dirs', []):
                rel = os.path.relpath(d, info['dir']).replace(os.sep, '/')
                if not os.path.isdir(d):
                    self._warn("Plugin %s: module folder %s is missing, its "
                               "modules are not loaded" % (name, rel))
                elif not inside(d, info['dir']):
                    self._warn("Plugin %s: module folder %s leads out of the "
                               "plugin folder (a link), its modules are not "
                               "loaded" % (name, rel))
                else:
                    dirs.append((d, lazy))
            for ext, into in dirs:
                rel = os.path.relpath(ext, info['dir']).replace(os.sep, '/')
                for mod, fn in extras_modules(ext):
                    if not MODULE_RE.match(mod):
                        continue
                    if into is lazy and not inside(os.path.join(ext, fn),
                                                   info['dir']):
                        self._warn("Plugin %s: %s/%s leads out of the plugin "
                                   "folder (a link), not loaded" % (
                                       name, rel, fn))
                        continue
                    if is_core_module(mod, core):
                        raise config.error(
                            "Plugin %s: %s/%s has the name of a Klipper "
                            "module; rename it" % (name, rel, fn))
                    # names that differ only in case are one name here
                    other = seen.get(mod.lower())
                    if other is not None:
                        raise config.error(
                            "Plugins %s and %s both have a module %s"
                            % (other[0], name, mod) if other[0] != name else
                            "Plugin %s has module %s twice (%s/%s, %s)"
                            % (name, mod, rel, fn, other[1]))
                    seen[mod.lower()] = (name, "%s/%s" % (rel, fn))
                    into[mod] = (name, ext)
        # The plugins' extras/ dirs join the extras package path (after
        # Klipper's own), so plugin modules and packages import as
        # extras.<module> and import each other. A RESTART starts over:
        # the last start's dirs and modules are dropped first.
        path = sys.modules['extras'].__path__
        for d in _PLUGIN_EXTRAS_DIRS:
            if d in path:
                path.remove(d)
        for full in list(sys.modules):
            if full.split('.')[0] == 'extras' and len(full.split('.')) > 1 \
                    and full.split('.')[1] in _PLUGIN_MODULES:
                del sys.modules[full]
        del _PLUGIN_EXTRAS_DIRS[:]
        _PLUGIN_MODULES.clear()
        for name, ext in list(wanted.values()) + list(lazy.values()):
            if ext not in path:
                path.append(ext)
                _PLUGIN_EXTRAS_DIRS.append(ext)
        # imported later (or by another module): dropped at the next start
        _PLUGIN_MODULES.update(lazy)
        self.lazy = lazy
        for mod, (name, ext) in sorted(wanted.items()):
            full = 'extras.' + mod
            _PLUGIN_MODULES.add(mod)
            try:
                module = importlib.import_module(full)
            except Exception as e:
                sys.modules.pop(full, None)
                logging.exception("ad5x_plugins: loading %s from %s", mod,
                                  ext)
                raise config.error("Plugin %s: extras/%s failed to load: "
                                   "%s" % (name, mod, e))
            self.modules[mod] = module
            logging.info("ad5x_plugins: loaded %s from plugin %s", mod, name)
        if not self.modules and not self.lazy:
            return
        # printer.load_object() only looks in klippy/extras: also find the
        # plugin modules (a plugin module may load another's section)
        self._klipper_load_object = self.printer.load_object
        self.printer.load_object = self._load_object
        # Objects for the plugin modules' config sections, as Klipper's
        # loader makes them for its own
        for section in config.get_prefix_sections(''):
            sname = section.get_name()
            if sname.split()[0] in self.modules or \
                    sname.split()[0] in self.lazy:
                self._load_object(config, sname)
    def _module(self, config, mod):
        """The plugin module named mod, importing a module_dirs one the
        first time it is needed; None for a module no plugin has."""
        module = self.modules.get(mod)
        if module is not None or mod not in self.lazy:
            return module
        name, ext = self.lazy[mod]
        full = 'extras.' + mod
        try:
            module = importlib.import_module(full)
        except Exception as e:
            sys.modules.pop(full, None)
            logging.exception("ad5x_plugins: loading %s from %s", mod, ext)
            rel = os.path.relpath(ext, self.found[name]['dir'])
            raise config.error("Plugin %s: %s/%s failed to load: %s" % (
                name, rel.replace(os.sep, '/'), mod, e))
        self.modules[mod] = module
        logging.info("ad5x_plugins: loaded %s from plugin %s (%s)", mod,
                     name, ext)
        return module
    def _load_object(self, config, section, *default):
        parts = section.split()
        module = self._module(config, parts[0]) if parts else None
        if module is None or self.printer.lookup_object(
                section, None) is not None:
            return self._klipper_load_object(config, section, *default)
        init = getattr(module, 'load_config_prefix' if len(parts) > 1
                       else 'load_config', None)
        if init is None:
            if default:
                return default[0]
            raise config.error("Unable to load module '%s'" % (section,))
        obj = init(config.getsection(section))
        self.printer.add_object(section, obj)
        return obj
    def _handle_ready(self):
        # Keep the Moonraker list in step (a system update may have added
        # or dropped a plugin's moonraker.conf). Moonraker reads it at its
        # next start.
        self._write_moonraker(self.loaded)
        # Root scripts of the enabled plugins: update.sh where root/ changed
        self._check_root_updates()
    def _write_moonraker(self, names):
        try:
            return write_moonraker(self.moonraker_file, names, self.found,
                                   self.ifs_klipper_flag)
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
        names = read_enabled(self.plugins_file)[0]
        self._sync_ifs_mcu(self._write_active())
        return names
    # Commands
    def _check_idle(self, gcmd):
        ps = self.printer.lookup_object('print_stats', None)
        if ps is not None and ps.get_status(
                self.printer.get_reactor().monotonic()).get(
                    'state') in BUSY_STATES:
            raise gcmd.error("Plugins can't be switched during a print "
                             "(Klipper restarts)")
    def _apply(self, gcmd, enable=(), disable=(), restart=None):
        """Write plugins.cfg, restart Moonraker if its parts changed, then
        Klipper (RESTART=0: later). gcmd None: from a background job (root's
        answer came); restart then says whether to restart."""
        respond = (gcmd.respond_info if gcmd is not None
                   else self.gcode.respond_info)
        if restart is None:
            restart = gcmd.get_int('RESTART', 1)
        try:
            names = self._write_enabled(enable, disable)
        except OSError as e:
            msg = "Can't write %s: %s" % (self.plugins_file, e)
            if gcmd is not None:
                raise gcmd.error(msg)
            raise Exception(msg)
        changed = self._write_moonraker(names)
        if changed or any(touches_moonraker(self.found.get(n))
                          for n in list(enable) + list(disable)):
            self._restart_moonraker(gcmd)
        if restart:
            respond("Restarting Klipper")
            if gcmd is not None:
                self.gcode.run_script_from_command("RESTART")
            else:
                self.gcode.run_script("RESTART")
        else:
            respond("Takes effect at the next RESTART")
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
    def _start_job(self, gcmd, name, action, argv, done, extra_env=None):
        if self.job['state'] == 'running':
            raise gcmd.error("Busy: %s %s" % (self.job['action'],
                                              self.job['name']))
        try:
            self._spawn(name, action, argv, done, extra_env)
        except OSError as e:
            raise gcmd.error("Can't run git: %s" % (e,))
        gcmd.respond_info(self.job['message'])
    def _spawn(self, name, action, argv, done, extra_env=None,
               message=None):
        """Run argv in the background as the job (name, action); done(rc,
        output) gives its result when it ends (or GIT_TIMEOUT passes). A
        done may start the next step with _spawn (the submodules after a
        clone): that one reports itself. OSError when argv can't run (the
        job is left as it was then)."""
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
        env.update(extra_env or {})
        env.setdefault('HOME', '/home/klipper')
        # A session of its own: a timeout kills git and what it started
        # (git submodule runs clones, which run git-remote-https)
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=env, start_new_session=True)
        self.job = {'name': name, 'action': action, 'state': 'running',
                    'message': message or "%s %s..." % (action, name)}
        self.job_done = done
        reactor = self.printer.get_reactor()
        self.job_end = reactor.monotonic() + GIT_TIMEOUT
        reactor.register_timer(self._poll_job, reactor.monotonic() + .5)
    def _poll_job(self, eventtime):
        rc = self.proc.poll()
        if rc is None:
            if eventtime < self.job_end:
                return eventtime + .5
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                self.proc.kill()
            rc = self.proc.wait()
            out = "timed out"
        else:
            out = git_output(self.proc.stdout.read().decode('utf-8',
                                                            'replace'))
        self.proc.stdout.close()
        self.proc = None
        job = self.job
        try:
            msg = self.job_done(rc, out.strip())
            state = 'done'
        except Exception as e:
            msg, state = str(e), 'failed'
        self.gcode.respond_info("%s %s: %s" % (job['action'], job['name'],
                                               msg))
        # done may have started the next job (ENABLE_PLUGIN ROOT=1 after an
        # install, the submodules after a clone): that one reports itself
        if self.job is job:
            self.job.update({'state': state, 'message': msg})
            self._save_job()
        return self.printer.get_reactor().NEVER
    def _save_job(self):
        try:
            write_if_changed(self.job_file, json.dumps(self.job))
        except OSError as e:
            logging.info("ad5x_plugins: %s: %s", self.job_file, e)
    # Root scripts: requests to the root update agent
    def _root_copy(self, name):
        return os.path.join(self.roots_dir, name)
    def _root_request(self, gcmd, name, action, done):
        """Ask root to run the plugin's root/<action>.sh (install, update,
        uninstall; lib/plugin-root.sh). In the background, like the git
        jobs (printer.ad5x_plugins.job): done(answer) is called with root's
        answer ("ok", "failed: ...", "timed out", "refused: ..."), or with
        a failure after ROOT_WAIT without one. done reports the end
        (_end_job); an exception there fails the job with its text."""
        if self.job['state'] == 'running':
            raise self.printer.command_error("Busy: %s %s" % (
                self.job['action'], self.job['name']))
        tar = os.path.join(self.agent_dir, "plugin-%s.tar" % (name,))
        request = os.path.join(self.agent_dir, "plugin-request")
        sha = ""
        try:
            if action != 'uninstall':
                data, sha = pack_root(os.path.join(
                    self.found[name]['dir'], 'root'))
        except (KeyError, OSError, ValueError) as e:
            raise self.printer.command_error(
                "Plugin %s: its root/ folder can't be packed: %s"
                % (name, e))
        try:
            # an answer to an older request (Klipper restarted meanwhile)
            unlink_quiet(os.path.join(self.agent_dir, "plugin-status"))
            if action != 'uninstall':
                write_new(tar, data)
            write_new(request, ("%s\n%s\n%s\n" % (action, name, sha))
                      .encode())
        except OSError as e:
            unlink_quiet(tar)
            raise self.printer.command_error(
                "Can't ask root to run %s's root/%s.sh: %s"
                % (name, action, e))
        self.job = {'name': name, 'action': 'root ' + action,
                    'state': 'running',
                    'message': "running root/%s.sh as root..." % (action,)}
        self.root_done = done
        reactor = self.printer.get_reactor()
        self.root_end = reactor.monotonic() + ROOT_WAIT
        reactor.register_timer(self._poll_root, reactor.monotonic() + 1.)
        msg = "Plugin %s: %s" % (name, self.job['message'])
        if gcmd is not None:
            gcmd.respond_info(msg)
        else:
            self.gcode.respond_info(msg)
    def _poll_root(self, eventtime):
        status = os.path.join(self.agent_dir, "plugin-status")
        try:
            answer = (read_regular(status, 512).strip().splitlines()
                      or ["failed: empty answer"])[0]
        except FileNotFoundError:
            answer = None
        except (OSError, ValueError) as e:
            answer = "failed: root's answer can't be read (%s)" % (e,)
        if answer is None:
            if eventtime < self.root_end:
                return eventtime + 1.
            answer = ("failed: no answer from root in %d s (is "
                      "S68ad5x-update-agent running?)" % (ROOT_WAIT,))
        # Klipper's own files: the request and the tar are gone when root
        # took them; still there, root never saw them
        name = self.job['name']
        for f in ("plugin-status", "plugin-request", "plugin-%s.tar" % name):
            unlink_quiet(os.path.join(self.agent_dir, f))
        done, self.root_done = self.root_done, None
        try:
            done(answer)
        except Exception as e:
            self._end_job('failed', str(e))
        return self.printer.get_reactor().NEVER
    def _end_job(self, state, msg):
        """The job's end: state done or failed, saved, in the console."""
        self.job.update({'state': state, 'message': msg})
        self._save_job()
        self.gcode.respond_info("%s %s: %s" % (self.job['action'],
                                               self.job['name'], msg))
    def _root_gate(self, gcmd, name, info):
        """A plugin with root scripts is enabled only with ROOT=1."""
        if info['root'] and not gcmd.get_int('ROOT', 0):
            raise gcmd.error(
                "Plugin %s runs code as root (its root/ scripts run as root "
                "when it is enabled, updated and disabled). Read them "
                "first (%s/root); to go ahead: ENABLE_PLUGIN NAME=%s ROOT=1"
                % (name, info['dir'], name))
    def _check_root_updates(self):
        """At klippy:ready: an enabled plugin whose root/ is not what root
        has a copy of (a plugin update since) gets its update.sh run, one
        plugin after the other, when root/ is what git checked out or the
        plugin is shipped; otherwise a warning (ENABLE_PLUGIN ROOT=1 runs
        it). An enabled plugin with root scripts but no root copy (enabled
        before it had them) gets a warning."""
        self.root_updates = []
        for name in self.active:
            info = self.found[name]
            if not info['root']:
                continue
            if not info['root_installed']:
                self._warn("Plugin %s has root scripts that were never "
                           "installed: DISABLE_PLUGIN NAME=%s, then "
                           "ENABLE_PLUGIN NAME=%s ROOT=1" % (name, name, name))
                continue
            try:
                changed = self._root_changed(name, info)
            except (OSError, ValueError) as e:
                self._warn("Plugin %s: its root/ folder can't be packed, "
                           "no update.sh: %s" % (name, e))
                continue
            if not changed:
                continue
            # Run by itself only what the plugin's author shipped (git, the
            # image); files uploaded or copied in wait for ROOT=1
            if info['source'] == 'shipped' or root_from_git(info['dir']):
                self.root_updates.append(name)
            else:
                self._warn("Plugin %s: its root/ changed outside git "
                           "(uploaded or copied in), so update.sh doesn't "
                           "run by itself. Read %s/root, then: ENABLE_PLUGIN "
                           "NAME=%s ROOT=1" % (name, info['dir'], name))
        if self.root_updates:
            reactor = self.printer.get_reactor()
            reactor.register_timer(self._next_root_update,
                                   reactor.monotonic() + 1.)
    def _root_changed(self, name, info):
        """Whether the plugin's root/ differs from root's copy (.sha256).
        OSError or ValueError when root/ can't be packed."""
        sha = pack_root(os.path.join(info['dir'], 'root'))[1]
        try:
            have = read_regular(os.path.join(self._root_copy(name),
                                             '.sha256'), 128).strip()
        except (OSError, ValueError):
            have = ""
        return have != sha
    def _update_done(self, answer):
        if answer == 'ok':
            self._end_job('done', "root/update.sh ok")
        else:
            self._end_job('failed', "root/update.sh %s" % (answer,))
    def _next_root_update(self, eventtime):
        if self.job['state'] == 'running':
            return eventtime + 2.
        if not self.root_updates:
            return self.printer.get_reactor().NEVER
        name = self.root_updates.pop(0)
        try:
            self._root_request(None, name, 'update', self._update_done)
        except Exception as e:
            self._warn("Plugin %s: update.sh not run: %s" % (name, e))
        if self.root_updates:
            return eventtime + 2.
        return self.printer.get_reactor().NEVER
    def _restart_after(self, info, msg):
        """Restart what a changed enabled plugin needs; returns msg."""
        msg += "; restarting Klipper"
        self.job.update({'state': 'done', 'message': msg})
        self._save_job()
        # An update may have made it an IFS owner, or not, or unusable
        self._sync_ifs_mcu(self._write_active())
        if touches_moonraker(info):
            self._restart_moonraker()
        self.gcode.run_script("RESTART")
        return msg
    cmd_INSTALL_PLUGIN_help = ("Install a plugin from the catalog: NAME= "
                               "[ENABLE=1 [ROOT=1]]")
    def _pin(self, d, commit, then, name, action, cleanup=None):
        """Pinned catalog entries (plugin API 1.11): check out commit in d
        (detached HEAD), fetching it from origin first when the clone or
        fetch didn't bring it (not on a branch). then() continues the job;
        failures call cleanup() (if given) and raise. Local changes are
        kept unless they collide."""
        def fail(msg):
            if cleanup:
                cleanup()
            raise Exception(msg)
        checkout = ["git", "-C", d, "checkout", "-q", "--detach", commit]
        rc, out = run_git(checkout)
        if rc == 0:
            return then()
        rc2, _ = run_git(["git", "-C", d, "cat-file", "-e",
                          commit + "^{commit}"])
        if rc2 == 0:
            fail("can't check out the catalog's commit %s: %s"
                 % (commit[:7], out[-300:]))
        def fetched(rc, out):
            if rc != 0:
                fail("the catalog's commit %s isn't on the plugin's "
                     "repository: %s" % (commit[:7], out[-300:]))
            rc, out = run_git(checkout)
            if rc != 0:
                fail("can't check out the catalog's commit %s: %s"
                     % (commit[:7], out[-300:]))
            return then()
        try:
            self._spawn(name, action, ["git", "-C", d, "fetch", "-q",
                                       "origin", commit], fetched, None,
                        "%s %s: fetching %s..." % (action, name,
                                                   commit[:7]))
        except OSError as e:
            fail("Can't run git: %s" % (e,))
        return "fetching the catalog's commit %s" % (commit[:7],)
    def cmd_INSTALL_PLUGIN(self, gcmd):
        name, entry = self._catalog_entry(gcmd)
        enable = gcmd.get_int('ENABLE', 0)
        root = gcmd.get_int('ROOT', 0)
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
        tmp = os.path.join(self.staging_dir, name)
        shutil.rmtree(tmp, ignore_errors=True)
        # Left by an install before STAGING_DIR (cut by a power loss)
        shutil.rmtree(os.path.join(self.user_dir, ".install-" + name),
                      ignore_errors=True)
        def done(rc, out):
            if rc != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                raise Exception("git clone failed: %s" % (out[-300:],))
            if not entry['commit']:
                return cloned()
            return self._pin(tmp, entry['commit'], cloned, name, "install",
                             lambda: shutil.rmtree(tmp, ignore_errors=True))
        def cloned():
            if entry['commit']:
                # Marks a pinned install (UPDATE_PLUGIN follows the
                # catalog's commit); a clone made by hand has no mark and
                # stays free (git pull, its own update manager)
                run_git(["git", "-C", tmp, "config", PIN_GIT_KEY, "true"])
            meta = read_metadata(tmp, name)
            if meta['error']:
                shutil.rmtree(tmp, ignore_errors=True)
                raise Exception("not a valid plugin: %s" % (meta['error'],))
            if not has_submodules(tmp):
                return installed()
            # Its submodules too, before it goes into place: a failure
            # leaves nothing behind, as a failed clone does
            errors = submodule_errors(tmp, entry['url'])
            if errors:
                shutil.rmtree(tmp, ignore_errors=True)
                raise Exception("submodules refused: %s" % ("; ".join(
                    errors),))
            try:
                self._spawn(name, "install", submodule_update_argv(tmp),
                            submodules_done, submodule_env(),
                            "install %s: submodules..." % (name,))
            except OSError as e:
                shutil.rmtree(tmp, ignore_errors=True)
                raise Exception("Can't run git: %s" % (e,))
            return "cloned, fetching its submodules"
        def submodules_done(rc, out):
            if rc != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                raise Exception("git submodule update failed: %s"
                                % (out[-300:],))
            return installed()
        def installed():
            try:
                os.rename(tmp, dest)
            except OSError as e:
                # staging_dir on another file system (a changed setup):
                # copied, then the staging copy removed
                if e.errno != errno.EXDEV:
                    shutil.rmtree(tmp, ignore_errors=True)
                    raise
                shutil.move(tmp, dest)
            self.found = self._scan()
            has_root = name in self.found and self.found[name]['root']
            if enable and (root or not has_root):
                # Saved first: enabling restarts Klipper (with root scripts,
                # after root's answer: that job reports itself)
                self.job.update({'state': 'done',
                                 'message': "installed and enabled"})
                self._save_job()
                self.gcode.run_script("ENABLE_PLUGIN NAME=%s%s" % (
                    name, " ROOT=1" if root else ""))
                if has_root:
                    return "installed, enabling"
                return "installed and enabled"
            if has_root:
                return ("installed, not enabled: it runs code as root (its "
                        "root/ scripts). Read them, then ENABLE_PLUGIN "
                        "NAME=%s ROOT=1" % (name,))
            return "installed (ENABLE_PLUGIN NAME=%s)" % (name,)
        for d in (self.user_dir, self.staging_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                raise gcmd.error("Can't create %s: %s" % (d, e))
        self._start_job(gcmd, name, "install",
                        ["git", "clone", "-q", entry['url'], tmp], done)
    cmd_UPDATE_PLUGIN_help = ("Update an installed plugin (git pull, or the "
                              "catalog's pinned commit): NAME=")
    def cmd_UPDATE_PLUGIN(self, gcmd):
        name = gcmd.get('NAME').strip().lower()
        d = os.path.join(self.user_dir, name)
        if not os.path.isdir(os.path.join(d, '.git')):
            raise gcmd.error("Plugin %s isn't a git install in %s"
                             % (name, self.user_dir))
        on = name in read_enabled(self.plugins_file)[0]
        if on:
            self._check_idle(gcmd)
        # Installed pinned from the catalog (plugin API 1.11): fetch, then
        # the catalog's commit. A clone made by hand isn't pinned.
        self.catalog = read_catalog(self.catalog_file)
        entry = self.catalog.get(name)
        commit = entry['commit'] if entry and is_pinned(d) else ''
        if commit:
            rc, origin = run_git(["git", "-C", d, "config", "--get",
                                  "remote.origin.url"])
            if rc != 0 or same_repo(origin, entry['url']) is False:
                commit = ''
        def rev(what="--short"):
            try:
                return subprocess.check_output(
                    ["git", "-C", d, "rev-parse", what, "HEAD"],
                    stderr=subprocess.DEVNULL).decode().strip()
            except (OSError, subprocess.CalledProcessError):
                return "?"
        before, before_full = rev(), rev("--verify")
        subs_before = submodule_state(d)
        after = []
        def back():
            # Nothing pulled: nothing to go back from
            if after and after[0] != before:
                return self._go_back(d, before_full)
            return ""
        def done(rc, out):
            if rc != 0:
                raise Exception("git pull failed: %s" % (out[-300:],))
            after.append(rev())
            if not has_submodules(d):
                return updated()
            # Its submodules at the commits the new version names; a
            # failure puts the previous version back
            rc, origin = run_git(["git", "-C", d, "config", "--get",
                                  "remote.origin.url"])
            errors = submodule_errors(d, origin if rc == 0 else None)
            if errors:
                raise Exception("submodules refused: %s%s" % (
                    "; ".join(errors), back()))
            # URLs changed in .gitmodules apply to submodules there already
            rc, out = run_git(submodule_git(d) + [
                'submodule', '--quiet', 'sync', '--recursive'],
                submodule_env())
            if rc != 0:
                raise Exception("git submodule sync failed: %s%s" % (
                    out[-300:], back()))
            try:
                self._spawn(name, "update", submodule_update_argv(d),
                            submodules_done, submodule_env(),
                            "update %s: submodules..." % (name,))
            except OSError as e:
                raise Exception("Can't run git: %s%s" % (e, back()))
            if after[0] == before:
                return "up to date (%s), checking its submodules" % (
                    after[0],)
            return "pulled %s -> %s, fetching its submodules" % (
                before, after[0])
        def submodules_done(rc, out):
            if rc != 0:
                raise Exception("git submodule update failed: %s%s" % (
                    out[-300:], back()))
            return updated()
        def updated():
            self.found = self._scan()
            subs_changed = submodule_state(d) != subs_before
            if after[0] == before and not subs_changed:
                return "up to date (%s)" % (after[0],)
            if after[0] == before:
                msg = "submodules updated (%s)" % (after[0],)
            else:
                msg = "updated %s -> %s" % (before, after[0])
            if on:
                return self._restart_after(self.found.get(name), msg)
            return msg
        if commit:
            def fetched(rc, out):
                if rc != 0:
                    raise Exception("git fetch failed: %s" % (out[-300:],))
                return self._pin(d, commit, lambda: done(0, ""), name,
                                 "update")
            self._start_job(gcmd, name, "update",
                            ["git", "-C", d, "fetch", "-q",
                             "--no-recurse-submodules", "origin"], fetched)
            return
        # Submodules only in the step after, with only https allowed
        self._start_job(gcmd, name, "update",
                        ["git", "-C", d, "pull", "-q", "--ff-only",
                         "--no-recurse-submodules"], done)
    def _go_back(self, d, commit):
        """After a failed submodule step of UPDATE_PLUGIN: the plugin back
        at commit (the version before the pull; local changes kept, as
        git reset --keep does) with its submodules where they were, no
        network used. The text to add to the failure."""
        if commit in ("", "?"):
            return "; the new version stays (its previous commit unknown)"
        rc, out = run_git(["git", "-C", d, "reset", "-q", "--keep", commit])
        if rc != 0:
            return ("; couldn't go back to the previous version (%s): %s"
                    % (commit[:7], out[-200:]))
        self.found = self._scan()
        # No transport allowed: only commits already there are checked out
        local = submodule_env("none")
        rc1, out1 = run_git(submodule_git(d) + [
            'submodule', '--quiet', 'sync', '--recursive'], local)
        rc2, out2 = run_git(submodule_git(d) + [
            'submodule', '--quiet', 'update', '--no-fetch', '--recursive'],
            local)
        if rc1 != 0 or rc2 != 0:
            return ("; the previous version (%s) is back, but its "
                    "submodules may not be: %s" % (commit[:7],
                                                   (out2 or out1)[-200:]))
        return "; the previous version (%s) is back" % (commit[:7],)
    cmd_REMOVE_PLUGIN_help = "Disable and delete an installed plugin: NAME="
    def cmd_REMOVE_PLUGIN(self, gcmd):
        self.found = self._scan()
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
        root = os.path.isdir(self._root_copy(name))
        if on or root:
            self._check_idle(gcmd)
        if root:
            # root/uninstall.sh first (root's copy), then the removal,
            # whatever it answered
            def done(answer):
                msg = "removed" if answer == 'ok' else \
                    "removed; root/uninstall.sh %s" % (answer,)
                if os.path.isdir(self._root_copy(name)):
                    msg += (". Root's copy of its root/ is still there: "
                            "DISABLE_PLUGIN NAME=%s runs uninstall.sh "
                            "again" % (name,))
                self._remove_now(None, name, info, on, msg,
                                 'done' if answer == 'ok' else 'failed')
            self._root_request(gcmd, name, 'uninstall', done)
            return
        self._remove_now(gcmd, name, info, on, "removed", 'done')
    def _remove_now(self, gcmd, name, info, on, msg, state):
        """REMOVE_PLUGIN's removal: off, deleted, Klipper restarted if it
        was on. gcmd None: from root's answer (a background job).
        Switched off first, then deleted: a folder that can't be deleted
        (files root made in it) leaves the plugin off and its folder (or
        what is left of it) in place, never on with half its files; the
        job says so and how to delete it. Klipper keeps running."""
        d = os.path.join(self.user_dir, name)
        names = None
        if on:
            try:
                names = self._write_enabled(disable=[name])
            except OSError as e:
                err = ("Plugin %s not removed: can't write %s: %s"
                       % (name, self.plugins_file, e))
                if gcmd is not None:
                    raise gcmd.error(err)
                raise Exception(err)
        try:
            shutil.rmtree(d)
        except OSError as e:
            # msg: "removed", or "removed; ..." with root's answer
            rest = msg[len("removed"):] if msg.startswith("removed") else ""
            msg = ("%snot deleted: %s can't be deleted (%s); delete it "
                   "as root: rm -rf %s%s"
                   % ("switched off, " if on else "", d, e, d, rest))
            state = 'failed'
            logging.warning("ad5x_plugins: REMOVE_PLUGIN %s: %s", name, e)
        self.found = self._scan()
        self.job = {'name': name, 'action': 'remove', 'state': state,
                    'message': msg}
        self._save_job()
        respond = (gcmd.respond_info if gcmd is not None
                   else self.gcode.respond_info)
        respond("Plugin %s %s" % (name, msg))
        if on:
            if self._write_moonraker(names) or touches_moonraker(info):
                self._restart_moonraker(gcmd)
            respond("Restarting Klipper")
            if gcmd is not None:
                self.gcode.run_script_from_command("RESTART")
            else:
                self.gcode.run_script("RESTART")
    cmd_ENABLE_PLUGIN_help = ("Enable a plugin and restart Klipper: NAME= "
                              "[ROOT=1] [RESTART=0]")
    def cmd_ENABLE_PLUGIN(self, gcmd):
        self.found = self._scan()
        name = gcmd.get('NAME').strip().lower()
        info = self.found.get(name)
        if info is None:
            raise gcmd.error("Unknown plugin '%s'. Available: %s" % (
                name, ", ".join(sorted(self.found)) or "none"))
        enabled = read_enabled(self.plugins_file)[0]
        if name in enabled:
            if info['root'] and info['root_installed'] and \
                    self._root_changed(name, info):
                # root/ changed in a way that doesn't run by itself
                # (_check_root_updates): ROOT=1 runs update.sh now
                self._check_idle(gcmd)
                self._root_gate(gcmd, name, info)
                self._root_request(gcmd, name, 'update', self._update_done)
                return
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
        if info['owns_ifs']:
            owners = ifs_owners(enabled, self.found)
            if owners:
                raise gcmd.error("Plugin %s can't be on together with %s: "
                                 "both drive the IFS and only one can; "
                                 "disable %s first" % (name, owners[0],
                                                       owners[0]))
            if not os.path.exists(self.ifs_klipper_flag):
                raise gcmd.error(
                    "Plugin %s drives the IFS, which needs the IFS on "
                    "Klipper firmware (/data/ad5x/ifs-klipper.enable, then "
                    "reboot)" % (name,))
        self._check_idle(gcmd)
        self._root_gate(gcmd, name, info)
        if info['root']:
            # root/install.sh first; plugins.cfg only after it said ok
            restart = gcmd.get_int('RESTART', 1)
            def done(answer):
                if answer != 'ok':
                    raise Exception("root/install.sh %s; the plugin stays "
                                    "off" % (answer,))
                self._end_job('done', "root/install.sh ok; %s %s enabled "
                              "(%s)" % (name, info['version'], info['source']))
                self._apply(None, enable=[name], restart=restart)
            self._root_request(gcmd, name, 'install', done)
            return
        gcmd.respond_info("Plugin %s %s enabled (%s)" % (
            name, info['version'], info['source']))
        self._apply(gcmd, enable=[name])
    cmd_DISABLE_PLUGIN_help = ("Disable a plugin and restart Klipper: NAME= "
                               "[RESTART=0]")
    def cmd_DISABLE_PLUGIN(self, gcmd):
        self.found = self._scan()
        name = gcmd.get('NAME').strip().lower()
        enabled = read_enabled(self.plugins_file)[0]
        # root has a copy of its root/ (enabled with ROOT=1): uninstall.sh
        root = NAME_RE.match(name) is not None and os.path.isdir(
            self._root_copy(name))
        if name not in enabled:
            if root:
                # off already (an uninstall that was refused, or the plugin
                # removed since): its root part goes now
                self._check_idle(gcmd)
                def done(answer):
                    self._end_job('done' if answer == 'ok' else 'failed',
                                  "root/uninstall.sh %s" % (answer,))
                self._root_request(gcmd, name, 'uninstall', done)
                return
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
        if root:
            # root/uninstall.sh first (root's copy), then the plugin is
            # off, whatever it answered
            restart = gcmd.get_int('RESTART', 1)
            def done(answer):
                msg = "disabled" if answer == 'ok' else \
                    "disabled; root/uninstall.sh %s" % (answer,)
                if os.path.isdir(self._root_copy(name)):
                    msg += (". Root's copy of its root/ is still there: "
                            "DISABLE_PLUGIN NAME=%s runs uninstall.sh "
                            "again" % (name,))
                self._end_job('done' if answer == 'ok' else 'failed', msg)
                self._apply(None, disable=[name], restart=restart)
            self._root_request(gcmd, name, 'uninstall', done)
            return
        gcmd.respond_info("Plugin %s disabled" % (name,))
        self._apply(gcmd, disable=[name])
    cmd_LIST_PLUGINS_help = "List the plugins (shipped and own) and which are on"
    def cmd_LIST_PLUGINS(self, gcmd):
        self.found = self._scan()
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
            if info['owns_ifs']:
                notes.append("drives the IFS")
            if info['root']:
                notes.append("root scripts installed" if
                             info['root_installed'] else
                             "runs code as root: ENABLE_PLUGIN ROOT=1")
            if name in self.skipped and on:
                notes.append("skipped" if info['error'] or not
                             info['compatible'] else
                             "skipped: " + self.skipped[name])
            if on != (name in self.loaded):
                notes.append("until RESTART")
            lines.append("%s %s %s (%s%s): %s%s" % (
                "[on] " if on else "[off]", name, info['version'] or "-",
                info['source'], ", " + info['author'] if info['author']
                else "", info['description'] or "-",
                " [%s]" % ("; ".join(notes),) if notes else ""))
        lines.append("ENABLE_PLUGIN NAME=<name> / DISABLE_PLUGIN NAME=<name>")
        gcmd.respond_info("\n".join(lines))
    def _rescan_if_changed(self, eventtime):
        if eventtime < self.next_dir_check:
            return
        self.next_dir_check = eventtime + DIR_CHECK
        mtime = dir_mtime(self.user_dir)
        if mtime != self.user_dir_mtime:
            self.user_dir_mtime = mtime
            self.found = self._scan()
    def get_status(self, eventtime):
        self._rescan_if_changed(eventtime)
        return {
            'api_version': PLUGIN_API_VERSION,
            'enabled': list(self.loaded),
            'available': {
                n: dict({k: i[k] for k in ('source', 'description',
                                           'version', 'author', 'url',
                                           'requires_os', 'compatible',
                                           'owns_ifs', 'root',
                                           'root_installed', 'pinned')},
                        # plugin API 1.11: not Kiln OS's own (installed
                        # by hand, or a community catalog entry)
                        community=not is_official(n, i['source'],
                                                  self.catalog))
                for n, i in self.found.items()},
            'ifs_owner': self.ifs_owner,
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
    S61klipper, before Klipper starts: write plugins-active.cfg (next to
    PLUGINS_CFG; prints the skipped plugins), link Kiln's IFS pins, or not.
    usage: ad5x_plugins.py moonraker [PLUGINS_CFG [OUT]]
           ad5x_plugins.py env [PLUGINS_CFG]
           ad5x_plugins.py klipper [PLUGINS_CFG]
           ad5x_plugins.py ifs-mcu [PLUGINS_CFG]"""
    modes = ("moonraker", "env", "klipper", "ifs-mcu")
    if len(argv) < 2 or argv[1] not in modes:
        sys.stderr.write("usage: ad5x_plugins.py moonraker [PLUGINS_CFG "
                         "[OUT]] | env [PLUGINS_CFG] | klipper "
                         "[PLUGINS_CFG] | ifs-mcu [PLUGINS_CFG]\n")
        return 2
    plugins_file = argv[2] if len(argv) > 2 else os.path.join(
        CONFIG_DIR, 'plugins.cfg')
    if argv[1] == "klipper":
        skipped = write_active(plugins_file, SHIPPED_DIR, USER_DIR)[1]
        for name in read_enabled(plugins_file)[0]:
            if name in skipped:
                sys.stdout.write("plugin %s skipped: %s\n"
                                 % (name, skipped[name]))
        return 0
    if argv[1] == "ifs-mcu":
        found = scan(SHIPPED_DIR, USER_DIR)
        names = plan(read_enabled(plugins_file)[0], found)[0]
        sync_ifs_mcu(names, found, IFS_MCU_DIR, IFS_KLIPPER_FLAG,
                     GENERIC_IFS_CFG)
        owners = ifs_owners(names, found)
        if owners:
            sys.stdout.write("IFS driven by plugin %s\n" % (owners[0],))
        return 0
    if argv[1] == "env":
        names = read_enabled(plugins_file)[0]
        sys.stdout.write(env_text(names, scan(SHIPPED_DIR, USER_DIR)))
        return 0
    out = argv[3] if len(argv) > 3 else os.path.join(
        CONFIG_DIR, 'moonraker-plugins.conf')
    # S62moonraker runs this as root: all of it is the config folder's
    # owner's (klipper's) to do
    drop_to_owner(os.path.dirname(os.path.abspath(out)))
    names = read_enabled(plugins_file)[0]
    found = scan(SHIPPED_DIR, USER_DIR)
    write_moonraker(out, names, found)
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
