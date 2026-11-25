#!/usr/bin/env python3
"""A stand-in printer for plugin tests: Kiln OS's plugin manager
(klipper/extras/ad5x_plugins.py) on stub Klipper objects (gcode,
print_stats, configfile, reactor, config sections), no printer and no
Klipper needed. tools/test_ad5x_plugins.py and the tests that
tools/new_plugin.sh makes use it (tools/check_plugin.py sets KILN_TOOLS to
this folder):

    sys.path.insert(0, os.environ["KILN_TOOLS"])
    import plugin_harness as kiln
    rig = kiln.Rig(tmpdir, sections={"my_light": {"greeting": "Hi"}})
    shutil.copytree(plugin_dir, os.path.join(rig.user, "my-light"))
    rig.start()
    rig.gc("ENABLE_PLUGIN", NAME="my-light", RESTART="0")   # -> "ok"
    rig.start()             # the restart: the plugin's extras load
    rig.printer.objects["my_light"], rig.mod.warnings, rig.info()

A plugin with root scripts (root/, docs/plugin-root-hooks.md) is enabled
with ROOT=1; root's answer comes from the stand-in root:

    rig.gc("ENABLE_PLUGIN", NAME="my-light", ROOT="1", RESTART="0")
    rig.root_answer("ok")   # as if root/install.sh said ok

A plugin that drives the IFS (plugin.json owns_ifs) runs only while the
IFS answers as Klipper; the stand-in says so with a file:

    open(rig.flag, "w").close()   # else the plugin is skipped, a warning

The stubs cover what the plugin manager uses and Klipper's config getters
(get, getint, getfloat, getboolean); a plugin module that needs more
(MCU pins, toolhead) brings its own stand-ins.
"""
import json
import os
import shutil
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "klipper", "extras"))
import ad5x_plugins  # noqa: E402

# Klipper's extras package (the plugins' extras/ dirs join its path)
sys.modules.setdefault("extras", types.ModuleType("extras")).__path__ = []

class CommandError(Exception):
    pass

class ConfigError(Exception):
    pass

class GCode:
    def __init__(self, log):
        self.commands, self.log = {}, log
    def register_command(self, name, func, when_not_ready=False, desc=None):
        self.commands[name] = func
        self.not_ready = getattr(self, 'not_ready', set())
        if when_not_ready:
            self.not_ready.add(name)
    def run_script_from_command(self, script):
        self.log.append(("gcode", script))
    def run_script(self, script):
        self.log.append(("script", script))
    def respond_info(self, msg):
        self.log.append(("info", msg))

class GCmd:
    error = CommandError
    def __init__(self, log, **params):
        self.params, self.log = params, log
    def get(self, name, default=None):
        if name not in self.params and default is None:
            raise CommandError("missing %s" % name)
        return str(self.params.get(name, default))
    def get_int(self, name, default=None):
        return int(self.params.get(name, default))
    def respond_info(self, msg):
        self.log.append(("info", msg))

class PrintStats:
    state = "standby"
    def get_status(self, eventtime):
        return {"state": self.state}

class Reactor:
    NEVER = 9e99
    timers = []
    def monotonic(self):
        return 0.
    def register_timer(self, cb, when=NEVER):
        Reactor.timers.append(cb)

def run_timers(limit=600):
    """Run registered timers until they are done (background git jobs)."""
    while Reactor.timers:
        cb = Reactor.timers.pop(0)
        for i in range(limit):
            if cb(.05 * i) >= Reactor.NEVER:
                break
            time.sleep(.05)

class ConfigFile:
    def __init__(self):
        self.warnings = []
    def runtime_warning(self, msg):
        self.warnings.append(msg)

class Printer:
    def __init__(self, log):
        self.objects = {"gcode": GCode(log), "print_stats": PrintStats(),
                        "configfile": ConfigFile()}
        self.handlers = {}
    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)
    def add_object(self, name, obj):
        if name in self.objects:
            raise ConfigError("duplicate %s" % name)
        self.objects[name] = obj
    def load_object(self, config, section, *default):
        # Klipper's: klippy/extras only (none here)
        if section in self.objects:
            return self.objects[section]
        if default:
            return default[0]
        raise ConfigError("Unable to load module '%s'" % (section,))
    def register_event_handler(self, event, cb):
        self.handlers[event] = cb
    def get_reactor(self):
        return Reactor()

class Section:
    """Config section: options from a dict; records what was read."""
    error = ConfigError
    def __init__(self, printer, name, opts, all_sections):
        self.printer, self.name, self.opts = printer, name, opts
        self.all = all_sections
    def get_printer(self):
        return self.printer
    def get_name(self):
        return self.name
    def get(self, option, default=None):
        return self.opts.get(option, default)
    def getint(self, option, default=None, minval=None, maxval=None):
        val = self.opts.get(option, default)
        return None if val is None else int(val)
    def getfloat(self, option, default=None, minval=None, maxval=None,
                 above=None, below=None):
        val = self.opts.get(option, default)
        return None if val is None else float(val)
    def getboolean(self, option, default=None):
        val = self.opts.get(option, default)
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return val
    def getsection(self, name):
        return Section(self.printer, name, self.all.get(name, {}), self.all)
    def get_prefix_sections(self, prefix):
        return [self.getsection(n) for n in self.all if n.startswith(prefix)]
    def get_prefix_options(self, prefix):
        return [o for o in self.opts if o.startswith(prefix)]

def make_plugin(base, name, meta=None, cfg="", extras=None, moonraker=None):
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "plugin.cfg"), "w") as f:
        f.write(cfg or "# %s\n" % name)
    if meta is not False:
        m = {"name": name, "description": "the %s plugin" % name,
             "version": "1.0.0", "requires_os": "1.0"}
        m.update(meta or {})
        with open(os.path.join(d, "plugin.json"), "w") as f:
            json.dump(m, f)
    for fn, src in (extras or {}).items():
        os.makedirs(os.path.join(d, "extras"), exist_ok=True)
        with open(os.path.join(d, "extras", fn), "w") as f:
            f.write(src)
    if moonraker is not None:
        with open(os.path.join(d, "moonraker.conf"), "w") as f:
            f.write(moonraker)
    return d

class Rig:
    def __init__(self, tmp, sections=None, plugins_cfg=None):
        self.tmp = tmp
        self.cfgdir = os.path.join(tmp, "config")
        self.shipped = os.path.join(tmp, "shipped")
        self.user = os.path.join(tmp, "user")
        for d in (self.cfgdir, self.shipped, self.user):
            os.makedirs(d, exist_ok=True)
        self.pfile = os.path.join(self.cfgdir, "plugins.cfg")
        self.mcudir = os.path.join(tmp, "ifs-mcu")
        os.makedirs(self.mcudir, exist_ok=True)
        self.flag = os.path.join(tmp, "ifs-klipper")
        self.generic = os.path.join(tmp, "generic-flashforge-ifs.cfg")
        self.link = os.path.join(self.mcudir, "generic-flashforge-ifs.cfg")
        self.mfile = os.path.join(self.cfgdir, "moonraker-plugins.conf")
        # root's copies of root/ and the root update agent's folder
        self.roots = os.path.join(tmp, "plugins-root")
        self.agent = os.path.join(tmp, "kiln-update")
        os.makedirs(self.roots, exist_ok=True)
        os.makedirs(self.agent, exist_ok=True)
        if plugins_cfg is not None:
            with open(self.pfile, "w") as f:
                f.write(plugins_cfg)
        self.sections = sections or {}
    def start(self, ifs=False, boot=True):
        """boot: write plugins-active.cfg first, as patch 0009 (before
        each config read) and S61klipper (at boot) do."""
        if boot:
            ad5x_plugins.write_active(
                self.pfile, self.shipped, self.user,
                catalog_file=os.path.join(self.tmp, "catalog.json"),
                ifs_flag=self.flag)
        self.log = []
        self.printer = Printer(self.log)
        if ifs:
            self.printer.objects["ifs"] = object()
        opts = {"plugins_file": self.pfile, "moonraker_file": self.mfile,
                "shipped_dir": self.shipped, "user_dir": self.user,
                "staging_dir": os.path.join(self.tmp, "staging"),
                "catalog_file": os.path.join(self.tmp, "catalog.json"),
                "moonraker_restart_file": os.path.join(self.tmp, "restart"),
                "ifs_mcu_dir": self.mcudir, "ifs_klipper_flag": self.flag,
                "generic_ifs_cfg": self.generic,
                "plugins_root_dir": self.roots, "agent_dir": self.agent,
                "factory_cfg": getattr(self, "factory_cfg",
                                       os.path.join(self.tmp, "none.cfg"))}
        all_sections = {"ad5x_plugins": opts}
        all_sections.update(self.sections)
        self.mod = ad5x_plugins.AD5XPlugins(
            Section(self.printer, "ad5x_plugins", opts, all_sections))
        return self
    def gc(self, cmd, **params):
        try:
            self.printer.objects["gcode"].commands[cmd](GCmd(self.log,
                                                             **params))
            return "ok"
        except CommandError as e:
            return "error: %s" % e
    def root_answer(self, answer="ok"):
        """The stand-in root: answers Klipper's pending request (install,
        update, uninstall) as the root update agent does, then runs the
        timers that wait for it. On "ok" root keeps its copy (an install or
        update) or drops it (an uninstall); nothing is run."""
        try:
            with open(os.path.join(self.agent, "plugin-request")) as f:
                action, name, sha = (f.read().split("\n") + ["", ""])[:3]
        except OSError:
            return False
        copy = os.path.join(self.roots, name)
        if answer == "ok" and action in ("install", "update"):
            os.makedirs(copy, exist_ok=True)
            with open(os.path.join(copy, ".sha256"), "w") as f:
                f.write(sha + "\n")
        elif action == "uninstall":
            shutil.rmtree(copy, ignore_errors=True)
        with open(os.path.join(self.agent, "plugin-status"), "w") as f:
            f.write(answer + "\n")
        run_timers()
        return True
    def enabled(self):
        return ad5x_plugins.read_enabled(self.pfile)[0]
    def text(self):
        with open(self.pfile) as f:
            return f.read()
    def info(self):
        return "\n".join(e[1] for e in self.log if e[0] == "info")
