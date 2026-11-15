#!/usr/bin/env python3
"""Check a Kiln OS plugin folder before you copy it to the printer.

Uses the plugin manager's own rules (klipper/extras/ad5x_plugins.py: the
same name, plugin.json, requires_os, plugin.cfg and extras checks that
decide whether the printer loads or skips the plugin), adds a few of its
own (unknown plugin.json keys, command names Klipper refuses, Python
syntax), then runs the plugin's tests (test_*.py
and tests/test_*.py) with KILN_TOOLS set to this tools/ folder, so a test
can load the plugin through Kiln's plugin manager (tools/plugin-template).

One line per finding: "<name>: error: ..." or "<name>: warning: ...".
Exit 0 when there are no errors (warnings allowed), 1 otherwise.

Names starting with kiln_ or ad5x_ (modules, components, sections,
macros) are errors, as on the printer, unless the plugin is official:
shipped (klipper/plugins/) or in klipper/plugin-catalog.json from Kiln's
own repositories (by plugin.json's name), or checked with --official.

usage: check_plugin.py [--no-tests] [--official] [--klippy DIR] PLUGIN_DIR...
  --klippy DIR  a Klipper klippy/ folder: also check module names against
                Klipper's own modules (else only Kiln OS's)
  --official    a Kiln OS plugin not in the catalog yet: kiln_ and ad5x_
                names allowed
  MOONRAKER_SRC (environment): a Moonraker source tree; also check
                component names against Moonraker's own
"""
import ast
import configparser
import difflib
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TEST_TIMEOUT = 300


def load_manager():
    """klipper/extras/ad5x_plugins.py, imported without Klipper."""
    path = os.path.join(REPO, "klipper", "extras", "ad5x_plugins.py")
    spec = importlib.util.spec_from_file_location("ad5x_plugins", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ap = load_manager()


def known_plugins():
    """Shipped plugin names and the catalog's (for requires/conflicts)."""
    names = set()
    shipped = os.path.join(REPO, "klipper", "plugins")
    if os.path.isdir(shipped):
        names.update(os.listdir(shipped))
    names.update(ap.read_catalog(os.path.join(REPO, "klipper",
                                              "plugin-catalog.json")))
    return names


def command_name_ok(name):
    """Klipper's rule for a command name (klippy/gcode.py register_command):
    G-code style (letter + number, M300) or upper case letters, digits and
    _ with no digit as the first or second character."""
    cmd = name.upper()
    try:
        float(cmd[1:])
        if cmd[0].isalpha() and cmd[1].isdigit():
            return True
    except (ValueError, IndexError):
        pass
    return (cmd.replace('_', 'A').isalnum() and not cmd[0].isdigit()
            and not cmd[1:2].isdigit())


def defines(path, names):
    """Whether a module (or package __init__) defines one of these
    functions at the top (load_config: Klipper makes objects for its
    sections; load_component: a Moonraker component)."""
    if os.path.isdir(path):
        path = os.path.join(path, "__init__.py")
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
    except (OSError, SyntaxError, ValueError):
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name in names
               for n in tree.body)


def official(name, path):
    """Whether the printer counts the plugin as Kiln OS's own: shipped
    (in this repository's klipper/plugins/) or in its catalog from Kiln's
    own repositories."""
    shipped = os.path.join(REPO, "klipper", "plugins")
    source = "shipped" if os.path.dirname(os.path.abspath(path)) == \
        shipped else "user"
    return ap.is_official(name, source, ap.read_catalog(
        os.path.join(REPO, "klipper", "plugin-catalog.json")))


class Checker:
    def __init__(self, path, klippy=None, run_tests=True, official=False):
        self.dir = os.path.abspath(path)
        self.name = os.path.basename(self.dir.rstrip(os.sep))
        self.klippy = klippy
        self.run_tests = run_tests
        self.official = official
        self.errors = self.warnings = 0
        self.lines = []
        self.sections = []

    def error(self, msg):
        self.errors += 1
        self.lines.append("%s: error: %s" % (self.name, msg))

    def warn(self, msg):
        self.warnings += 1
        self.lines.append("%s: warning: %s" % (self.name, msg))

    def note(self, msg):
        self.lines.append("%s: %s" % (self.name, msg))

    def rel(self, path):
        return os.path.relpath(path, self.dir)

    def run(self):
        if not os.path.isdir(self.dir):
            self.error("%s is not a folder" % (self.dir,))
            return self
        self.repo_name()
        if not ap.NAME_RE.match(self.name):
            self.error("folder name '%s' is not a plugin name (a-z, 0-9, - "
                       "and _, starting with a letter or digit, at most 48)"
                       % (self.name,))
        self.check_json()
        self.check_cfg()
        if not os.path.isfile(os.path.join(self.dir, "README.md")):
            self.warn("no README.md (what it does, how to use it)")
        self.check_python()
        self.check_extras()
        self.check_moonraker()
        self.check_names()
        self.check_root()
        if self.run_tests and not self.errors:
            self.tests()
        return self

    def repo_name(self):
        """A git repository is cloned under the plugin's name (kiln-notify
        as notify): check it under plugin.json's name."""
        if not os.path.exists(os.path.join(self.dir, ".git")):
            return
        try:
            name = json.loads(ap.read_regular(
                os.path.join(self.dir, "plugin.json"))).get("name")
        except (OSError, ValueError, AttributeError):
            return
        if isinstance(name, str) and ap.NAME_RE.match(name) and \
                name != self.name:
            self.note("git repository %s: checked as %s (clone it as %s)"
                      % (self.name, name, name))
            self.name = name

    # plugin.json
    def check_json(self):
        meta = ap.read_metadata(self.dir, self.name)
        if meta['error']:
            self.error(meta['error'])
        try:
            data = json.loads(ap.read_regular(
                os.path.join(self.dir, "plugin.json")))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key in ap.unknown_keys(data):
            if key == 'root_actions':
                self.error("plugin.json: root_actions (named root actions) "
                           "were removed in plugin API 1.6; put root "
                           "scripts in root/ (docs/plugin-root-hooks.md)")
                continue
            near = difflib.get_close_matches(key, ap.PLUGIN_JSON_KEYS, 1)
            self.error("plugin.json: unknown key '%s'%s" % (
                key, " (did you mean '%s'?)" % near[0] if near else ""))
        if 'name' not in data:
            self.error("plugin.json: no name (set \"name\": \"%s\")"
                       % (self.name,))
        for key in ('description', 'version', 'author', 'url',
                    'requires_os'):
            if key in data and not isinstance(data[key], str):
                self.error("plugin.json: %s must be a string" % (key,))
        for key in ('description', 'version'):
            if not data.get(key):
                self.warn("plugin.json: no %s (LIST_PLUGINS shows it)"
                          % (key,))
        req = meta['requires_os']
        if not req:
            self.warn("plugin.json: no requires_os (set \"%s\", this "
                      "system's plugin API)" % (ap.PLUGIN_API_VERSION,))
        elif not meta['error'] and not ap.api_compatible(req):
            have = ap.parse_version(ap.PLUGIN_API_VERSION)
            need = ap.parse_version(req)
            self.error("plugin.json: requires_os %s doesn't fit plugin API "
                       "%s: %s" % (req, ap.PLUGIN_API_VERSION,
                                   "a newer Kiln OS is needed" if
                                   need[0] == have[0] else
                                   "the major version differs"))
        known = known_plugins()
        for key in ('requires', 'conflicts'):
            val = data.get(key)
            if val is not None and not isinstance(val, (list, str)):
                self.error("plugin.json: %s must be a list of plugin names"
                           % (key,))
                continue
            for other in meta[key]:
                if not ap.NAME_RE.match(other):
                    self.error("plugin.json: %s: '%s' is not a plugin name"
                               % (key, other))
                elif other == self.name:
                    self.error("plugin.json: %s names the plugin itself"
                               % (key,))
                elif key == 'requires' and other not in known:
                    self.warn("plugin.json: requires '%s', which is neither "
                              "shipped nor in the catalog" % (other,))
        if 'owns_ifs' in data and not isinstance(data['owns_ifs'], bool):
            self.error("plugin.json: owns_ifs must be true or false")

    # root/: scripts that run as root (docs/plugin-root-hooks.md), packed
    # the way the plugin manager sends them to root
    def check_root(self):
        path = os.path.join(self.dir, "root")
        if not os.path.lexists(path):
            return
        if not os.path.islink(path) and not os.path.isdir(path):
            self.error("root is not a folder")
            return
        try:
            ap.pack_root(path)
        except (OSError, ValueError) as e:
            self.error("%s; the printer can't send root/ to root, so the "
                       "plugin can't be enabled" % (e,))
            return
        if not ap.has_root(self.dir):
            self.warn("root/ has none of %s: the printer ignores it"
                      % (", ".join(ap.ROOT_HOOKS),))
            return
        req = ap.parse_version(
            ap.read_metadata(self.dir, self.name)['requires_os'])
        if not req or req < (1, 6):
            self.warn("root/ scripts need plugin API 1.6: set \"requires_os\": "
                      "\"1.6\" (an older Kiln OS enables the plugin without "
                      "running them)")
        self.note("runs code as root: enabled only with ENABLE_PLUGIN "
                  "NAME=%s ROOT=1 (docs/plugin-root-hooks.md)" % (self.name,))

    # plugin.cfg
    def check_cfg(self):
        path = os.path.join(self.dir, "plugin.cfg")
        if not os.path.isfile(path):
            self.error("no plugin.cfg (required, may hold only comments); "
                       "the printer doesn't see this folder as a plugin")
            self.sections = []
            return
        err = ap.cfg_error(path)
        if err:
            self.error(err)
            self.sections = []
            return
        text = ap.read_regular(path)
        text = "\n".join(l.split('#', 1)[0] for l in text.split('\n'))
        parser = configparser.RawConfigParser(
            strict=False, inline_comment_prefixes=(';', '#'))
        parser.read_string(text, path)
        self.sections = parser.sections()
        for sec in self.sections:
            words = sec.split()
            if words[0] == "gcode_macro" and len(words) > 1 and \
                    not command_name_ok(words[1]):
                self.error("plugin.cfg: [%s]: Klipper refuses this command "
                           "name (letters, digits and _, no digit as the "
                           "first or second character)" % (sec,))

    # Python files: syntax only, nothing is run
    def check_python(self):
        for sub in ("extras", "python", os.path.join("moonraker",
                                                     "components"), "tests"):
            base = os.path.join(self.dir, sub)
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in sorted(files):
                    if not fn.endswith(".py"):
                        continue
                    path = os.path.join(root, fn)
                    try:
                        with open(path, encoding="utf-8") as f:
                            compile(f.read(), path, "exec")
                    except SyntaxError as e:
                        self.error("%s:%s: %s" % (self.rel(path), e.lineno,
                                                  e.msg))
                    except (OSError, ValueError) as e:
                        self.error("%s: %s" % (self.rel(path), e))

    # extras/: Klipper modules
    def check_extras(self):
        ext = os.path.join(self.dir, "extras")
        if not os.path.isdir(ext):
            return
        cores = [os.path.join(REPO, "klipper", "extras")]
        if self.klippy:
            cores.append(os.path.join(self.klippy, "extras"))
        prefix = self.name.replace('-', '_')
        for mod, fn in ap.extras_modules(ext):
            if not ap.MODULE_RE.match(mod):
                self.warn("extras/%s is not loaded: module names are a-z, "
                          "0-9 and _, starting with a letter" % (fn,))
                continue
            if any(ap.is_core_module(mod, c) for c in cores):
                self.error("extras/%s has the name of a Klipper or Kiln OS "
                           "module; rename it (%s_...)" % (fn, prefix))
            elif mod.startswith(ap.RESERVED_PREFIXES):
                pass    # check_names
            elif not mod.startswith(prefix):
                self.warn("extras/%s: start module names with the plugin "
                          "name (%s_...) so they don't clash with other "
                          "plugins" % (fn, prefix))
            if defines(os.path.join(ext, fn), (
                    "load_config", "load_config_prefix")) and not any(
                    s.split()[0] == mod for s in self.sections):
                self.warn("extras/%s: plugin.cfg has no [%s] section, so "
                          "Klipper makes no object of it" % (fn, mod))
        if not self.klippy:
            self.note("Klipper's own module names not checked (--klippy "
                      "DIR)")

    # moonraker.conf and moonraker/components/
    def check_moonraker(self):
        conf = os.path.join(self.dir, "moonraker.conf")
        msections = []
        if os.path.isfile(conf):
            parser = configparser.ConfigParser(
                strict=False, interpolation=None,
                inline_comment_prefixes=('#', ';'))
            try:
                parser.read_string(ap.read_regular(conf), conf)
                msections = parser.sections()
            except (configparser.Error, OSError, ValueError) as e:
                self.error("moonraker.conf doesn't parse: %s" % (
                    " ".join(str(e).split())[:200],))
        comps = os.path.join(self.dir, "moonraker", "components")
        if not os.path.isdir(comps):
            return
        kiln = os.path.join(REPO, "moonraker", "components")
        msrc = os.environ.get("MOONRAKER_SRC")
        theirs = os.path.join(msrc, "moonraker", "components") if msrc \
            else None
        for fn in sorted(os.listdir(comps)):
            path = os.path.join(comps, fn)
            if fn.endswith(".py") and os.path.isfile(path):
                mod = fn[:-3]
            elif os.path.isfile(os.path.join(path, "__init__.py")):
                mod = fn
            else:
                continue
            if mod == "__init__":
                continue
            if ap.is_core_module(mod, kiln) or (
                    theirs and ap.is_core_module(mod, theirs)):
                self.error("moonraker/components/%s has the name of a "
                           "Moonraker or Kiln OS component, which wins; "
                           "rename it" % (fn,))
            if defines(path, ("load_component",)) and not any(
                    s.split()[0] == mod for s in msections):
                self.warn("moonraker/components/%s: moonraker.conf has no "
                          "[%s] section, so Moonraker doesn't load it"
                          % (fn, mod))

    # kiln_ / ad5x_ names (the plugin manager's reserved_names)
    def check_names(self):
        names = ap.reserved_names(self.dir)
        if not names:
            return
        if self.official or official(self.name, self.dir):
            self.note("official Kiln OS plugin: may use %s names (%s)" % (
                " and ".join(ap.RESERVED_PREFIXES), ", ".join(names)))
            return
        for where in names:
            self.error("%s: names starting with %s are kept for Kiln OS and "
                       "its official plugins; the printer won't enable this "
                       "plugin. Rename it (%s_...)" % (
                           where, " or ".join(ap.RESERVED_PREFIXES),
                           self.name.replace('-', '_')))

    # the plugin's own tests
    def tests(self):
        found = []
        for sub in ("", "tests"):
            base = os.path.join(self.dir, sub)
            if os.path.isdir(base):
                found += [os.path.join(base, fn) for fn in sorted(
                    os.listdir(base)) if re.match(r"test_.*\.py$", fn)]
        if not found:
            self.note("no tests (test_*.py or tests/test_*.py)")
            return
        env = dict(os.environ, KILN_TOOLS=HERE, PYTHONDONTWRITEBYTECODE="1")
        for path in found:
            try:
                res = subprocess.run(
                    [sys.executable, path], cwd=self.dir, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    timeout=TEST_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.error("%s: no result after %d s" % (self.rel(path),
                                                         TEST_TIMEOUT))
                continue
            out = res.stdout.decode("utf-8", "replace").strip().splitlines()
            last = out[-1] if out else ""
            if res.returncode == 0:
                self.note("%s: passed%s" % (self.rel(path),
                                            " (%s)" % last if last else ""))
            else:
                fails = [l for l in out if "FAIL" in l or "Error" in l]
                self.error("%s failed (exit %d): %s" % (
                    self.rel(path), res.returncode,
                    (fails or [last])[0][:200]))
                if os.environ.get("CHECK_PLUGIN_VERBOSE"):
                    self.lines += ["    " + l for l in out[-30:]]


def main(argv):
    # The plugin manager logs what it ignores; the findings say it
    logging.disable(logging.WARNING)
    args, klippy, run_tests = [], os.environ.get("KLIPPY_DIR"), True
    is_official = False
    it = iter(argv[1:])
    for a in it:
        if a == "--no-tests":
            run_tests = False
        elif a == "--official":
            is_official = True
        elif a == "--klippy":
            klippy = next(it, None)
        elif a in ("-h", "--help"):
            sys.stdout.write(__doc__)
            return 0
        else:
            args.append(a)
    if not args:
        sys.stderr.write("usage: check_plugin.py [--no-tests] [--official] "
                         "[--klippy DIR] PLUGIN_DIR...\n")
        return 2
    if klippy and not os.path.isdir(os.path.join(klippy, "extras")):
        sys.stderr.write("check_plugin.py: %s has no extras/ (give the "
                         "klippy folder)\n" % (klippy,))
        return 2
    rc = 0
    for path in args:
        c = Checker(path, klippy, run_tests, is_official).run()
        for line in c.lines:
            print(line)
        if c.errors:
            print("%s: FAILED (%d error%s, %d warning%s)" % (
                c.name, c.errors, "s" * (c.errors != 1), c.warnings,
                "s" * (c.warnings != 1)))
            rc = 1
        else:
            print("%s: OK (%d warning%s, plugin API %s)" % (
                c.name, c.warnings, "s" * (c.warnings != 1),
                ap.PLUGIN_API_VERSION))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
