#!/usr/bin/env python3
"""__NAME__: the Klipper module (extras/__MOD__.py) with a stand-in
printer: only what the module uses.

usage: python3 tests/test_klipper.py
"""
import os
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, "extras"))
import __MOD__  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    print("%s %s" % ("ok  " if cond else "FAIL", name))
    fails += not cond


class GCode:
    def __init__(self):
        self.commands = {}

    def register_command(self, name, func, when_not_ready=False, desc=None):
        self.commands[name] = func


class GCmd:
    def __init__(self, **params):
        self.params, self.said = params, []

    def get(self, name, default=None):
        return self.params.get(name, default)

    def respond_info(self, msg):
        self.said.append(msg)


class Printer:
    def __init__(self):
        self.gcode = GCode()

    def lookup_object(self, name, default=None):
        return self.gcode if name == "gcode" else default


class Config:
    def __init__(self, options):
        self.printer, self.options = Printer(), options

    def get_printer(self):
        return self.printer

    def get(self, option, default=None):
        return self.options.get(option, default)


config = Config({"greeting": "Hi"})
obj = __MOD__.load_config(config)
check("status at start", obj.get_status(0.) == {"greeting": "Hi",
                                                 "count": 0})
gcmd = GCmd(NAME="you")
config.printer.gcode.commands["__MACRO___GREET"](gcmd)
check("__MACRO___GREET answers", gcmd.said == ["Hi, you!"])
check("count goes up", obj.get_status(0.)["count"] == 1)

print("%d failed" % fails if fails else "all passed")
sys.exit(1 if fails else 0)
