#!/usr/bin/env python3
"""__NAME__: the Moonraker component (moonraker/components/__MOD__.py)
with a stand-in server. MOONRAKER_SRC: a Moonraker source tree for the
real moonraker.common (optional).

usage: python3 tests/test_moonraker.py
"""
import asyncio
import enum
import importlib.util
import os
import sys
import types

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = 0


def check(name, cond):
    global fails
    print("%s %s" % ("ok  " if cond else "FAIL", name))
    fails += not cond


# Moonraker imports a component as moonraker.components.<name>
src = os.environ.get("MOONRAKER_SRC")
if src:
    sys.path.insert(0, src)
    import moonraker.common  # noqa: F401
else:
    pkg = types.ModuleType("moonraker")
    pkg.__path__ = []
    common = types.ModuleType("moonraker.common")

    class RequestType(enum.Flag):
        GET = enum.auto()
        POST = enum.auto()
    common.RequestType = RequestType
    sys.modules.update({"moonraker": pkg, "moonraker.common": common})
comps = types.ModuleType("moonraker.components")
comps.__path__ = []
sys.modules["moonraker.components"] = comps
spec = importlib.util.spec_from_file_location(
    "moonraker.components.__MOD__",
    os.path.join(PLUGIN, "moonraker", "components", "__MOD__.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Server:
    def __init__(self):
        self.endpoints = {}

    def register_endpoint(self, path, request_types, callback, **kw):
        self.endpoints[path] = (request_types, callback)


class Config:
    def __init__(self, options):
        self.server, self.options = Server(), options

    def get_server(self):
        return self.server

    def get(self, option, default=None):
        return self.options.get(option, default)


config = Config({"greeting": "Hi"})
mod.load_component(config)
rtype, cb = config.server.endpoints.get("/server/__MOD__/hello",
                                        (None, None))
check("GET /server/__MOD__/hello registered", cb is not None and
      rtype == sys.modules["moonraker.common"].RequestType.GET)
check("reply", cb is not None and
      asyncio.run(cb(None)) == {"message": "Hi"})

print("%d failed" % fails if fails else "all passed")
sys.exit(1 if fails else 0)
