#!/usr/bin/env python3
"""__NAME__: plugin.cfg parses and has the macro. With Kiln OS's tools
(KILN_TOOLS=<kiln-os>/tools; tools/check_plugin.py sets it) Kiln's plugin
manager also enables the plugin and loads it, as on the printer, with a
stand-in printer.

usage: python3 tests/test_plugin.py
"""
import configparser
import os
import shutil
import sys
import tempfile

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "__NAME__"
fails = 0


def check(name, cond):
    global fails
    print("%s %s" % ("ok  " if cond else "FAIL", name))
    fails += not cond


# plugin.cfg as Klipper reads it ('#' starts a comment)
with open(os.path.join(PLUGIN, "plugin.cfg")) as f:
    text = "\n".join(l.split("#", 1)[0] for l in f.read().split("\n"))
cfg = configparser.RawConfigParser(strict=False)
cfg.read_string(text)
check("plugin.cfg has the macro",
      cfg.has_section("gcode_macro __MACRO___HELLO"))

tools = os.environ.get("KILN_TOOLS")
if tools:
    sys.path.insert(0, tools)
    import plugin_harness as kiln  # noqa: E402  Kiln OS's stand-in printer
    tmp = tempfile.mkdtemp()
    try:
        sections = {s: dict(cfg.items(s)) for s in cfg.sections()}
        rig = kiln.Rig(tmp, sections=sections)
        shutil.copytree(PLUGIN, os.path.join(rig.user, NAME),
                        ignore=shutil.ignore_patterns("__pycache__", ".git"))
        rig.start()
        # root scripts (root/): enabled with ROOT=1 after root/install.sh
        # said ok; a stand-in root answers here, nothing runs as root
        root = any(os.path.isfile(os.path.join(PLUGIN, "root", h))
                   for h in ("install.sh", "update.sh", "uninstall.sh"))
        params = {"NAME": NAME, "RESTART": "0"}
        if root:
            params["ROOT"] = "1"
        res = rig.gc("ENABLE_PLUGIN", **params)
        if root and res == "ok":
            rig.root_answer("ok")
        check("ENABLE_PLUGIN", res == "ok" and NAME in rig.enabled())
        rig.start()  # the restart that loads it
        check("loaded, not skipped",
              NAME in rig.mod.active and not rig.mod.warnings)
        for mod in rig.mod.modules:
            if mod in sections:
                check("[%s] object made" % mod, mod in rig.printer.objects)
    finally:
        shutil.rmtree(tmp)
else:
    print("skip Kiln's plugin manager (KILN_TOOLS not set)")

print("%d failed" % fails if fails else "all passed")
sys.exit(1 if fails else 0)
