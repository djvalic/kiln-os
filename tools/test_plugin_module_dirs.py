#!/usr/bin/env python3
"""Plugin API 1.7: module names with capitals, and plugin.json module_dirs
(more Klipper module folders inside a plugin, imported when needed).
Runs on the plugin harness, no printer needed:

    python3 tools/test_plugin_module_dirs.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plugin_harness as kiln  # noqa: E402
import ad5x_plugins  # noqa: E402  (plugin_harness puts it on sys.path)

# A plugin like afc-kiln: its own extras/, and a checkout of another
# project whose modules have capitals (AFC_lane, ...)
THING = '''
from extras.AFC_helper import WORD
class Thing:
    def __init__(self, config):
        self.word = WORD
        self.name = config.get_name()
        self.other = config.get_printer().load_object(config, "AFC_other one")
def load_config(config):
    return Thing(config)
'''
HELPER = 'WORD = "%s"\n'
OTHER = '''
class Other:
    def __init__(self, config):
        self.name = config.get_name()
def load_config_prefix(config):
    return Other(config)
'''
BROKEN = 'raise RuntimeError("must not be imported")\n'


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def forget():
    for name in list(sys.modules):
        if name.startswith("extras.") and name.split(".")[1] in (
                "AFC_thing", "AFC_helper", "AFC_other", "AFC_broken",
                "myafc_boot", "AFC_dup"):
            del sys.modules[name]


class ModuleDirsTest(unittest.TestCase):
    def setUp(self):
        forget()
        self.tmp = tempfile.mkdtemp()
        self.rig = kiln.Rig(self.tmp, sections={"AFC_thing": {}})
        self.dir = kiln.make_plugin(
            self.rig.user, "myafc",
            meta={"requires_os": "1.7", "module_dirs": ["vendor/extras"]},
            cfg="[AFC_thing]\n",
            extras={"myafc_boot.py": "def load_config(config):\n"
                                     "    return object()\n"})
        self.vendor = os.path.join(self.dir, "vendor", "extras")
        write(os.path.join(self.vendor, "__init__.py"), "")
        write(os.path.join(self.vendor, "AFC_thing.py"), THING)
        write(os.path.join(self.vendor, "AFC_helper.py"), HELPER % "one")
        write(os.path.join(self.vendor, "AFC_other.py"), OTHER)
        write(os.path.join(self.vendor, "AFC_broken.py"), BROKEN)

    def tearDown(self):
        forget()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def enable(self):
        self.rig.start()
        self.assertEqual(self.rig.gc("ENABLE_PLUGIN", NAME="myafc",
                                     RESTART="0"), "ok")
        return self.rig.start()

    def test_loaded_when_needed(self):
        rig = self.enable()
        thing = rig.printer.objects["AFC_thing"]
        self.assertEqual(thing.word, "one")
        # load_object() of a module_dirs module with a name after it
        self.assertIs(rig.printer.objects["AFC_other one"], thing.other)
        self.assertEqual(thing.other.name, "AFC_other one")
        # a module nothing asks for is never imported
        self.assertNotIn("extras.AFC_broken", sys.modules)
        self.assertEqual(rig.mod.warnings, [])

    def test_restart_reloads_files(self):
        self.enable()
        write(os.path.join(self.vendor, "AFC_helper.py"), HELPER % "second")
        rig = self.rig.start()
        self.assertEqual(rig.printer.objects["AFC_thing"].word, "second")

    def test_missing_folder_warns(self):
        shutil.rmtree(os.path.join(self.dir, "vendor"))
        self.rig.sections = {}
        rig = self.enable()
        self.assertTrue(any("vendor/extras is missing" in w
                            for w in rig.mod.warnings), rig.mod.warnings)
        self.assertIn("myafc_boot", rig.mod.modules)

    def test_same_module_twice_stops(self):
        write(os.path.join(self.dir, "extras", "AFC_other.py"), OTHER)
        self.rig.start()
        self.rig.gc("ENABLE_PLUGIN", NAME="myafc", RESTART="0")
        with self.assertRaises(kiln.ConfigError) as caught:
            self.rig.start()
        self.assertIn("AFC_other twice", str(caught.exception))

    def test_reserved_names_any_case(self):
        write(os.path.join(self.vendor, "Kiln_x.py"), "")
        self.assertIn("vendor/extras/Kiln_x.py",
                      ad5x_plugins.reserved_names(self.dir))


class ParseTest(unittest.TestCase):
    def test_parse(self):
        p = ad5x_plugins.parse_module_dirs
        self.assertEqual(p(None), ([], None))
        self.assertEqual(p(["AFC/extras", "./AFC/extras/", "lib"]),
                         (["AFC/extras", "lib"], None))
        for bad in ("AFC/extras", ["/abs"], ["../up"], ["a/../b"],
                    ["a\\b"], [""], ["extras"], [1], ["d%d" % i for i in range(9)]):
            self.assertIsNotNone(p(bad)[1], bad)

    def test_bad_module_dirs_is_a_plugin_error(self):
        tmp = tempfile.mkdtemp()
        try:
            d = kiln.make_plugin(tmp, "bad", meta={"module_dirs": ["../x"]})
            meta = ad5x_plugins.read_metadata(d, "bad")
            self.assertIn("module_dirs", meta["error"])
        finally:
            shutil.rmtree(tmp)

    def test_capital_names(self):
        self.assertTrue(ad5x_plugins.MODULE_RE.match("AFC_lane"))
        self.assertFalse(ad5x_plugins.MODULE_RE.match("_private"))
        self.assertFalse(ad5x_plugins.MODULE_RE.match("9lives"))


if __name__ == "__main__":
    unittest.main()
