import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "ifs_firmware", os.path.join(HERE, "..", "extras", "ifs_firmware.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeGcode:
    def __init__(self):
        self.cmds = {}

    def register_command(self, name, func, desc=None):
        self.cmds[name] = func


class FakeReactor:
    def __init__(self):
        self.now = 100.

    def monotonic(self):
        return self.now


class FakePrintStats:
    def __init__(self, state="standby"):
        self.state = state

    def get_status(self, eventtime):
        return {"state": self.state}


class FakePrinter:
    def __init__(self):
        self.objects = {}
        self.gcode = FakeGcode()
        self.reactor = FakeReactor()

    def lookup_object(self, name, default=None):
        if name == "gcode":
            return self.gcode
        return self.objects.get(name, default)

    def get_reactor(self):
        return self.reactor


class FakeConfig:
    def __init__(self, printer, opts):
        self.printer = printer
        self.opts = opts

    def get_printer(self):
        return self.printer

    def get(self, name, default=None):
        return self.opts.get(name, default)


class FakeIfs:
    def __init__(self, fd, is_mcu_mode):
        self.fd = fd
        self.is_mcu_mode = is_mcu_mode


class Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "sub")  # missing on purpose
        self.req = os.path.join(self.dir, "ifs-firmware")
        self.status = os.path.join(self.dir, "ifs-firmware.status")
        self.printer = FakePrinter()
        self.obj = mod.load_config(FakeConfig(self.printer, {
            "request_path": self.req, "status_path": self.status}))

    def test_no_gcode_command(self):
        # the switch stops Klipper: only Moonraker's POST starts it
        self.assertEqual(self.printer.gcode.cmds, {})

    def write_status(self, text):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.status, "w") as f:
            f.write(text)
        self.printer.reactor.now += 5

    def test_firmware_klipper_when_mcu_ifs(self):
        self.printer.objects["mcu ifs"] = object()
        self.printer.objects["ifs"] = FakeIfs(3, False)
        self.assertEqual(self.obj.get_status(0)["firmware"], "klipper")

    def test_firmware_stock_when_serial(self):
        self.printer.objects["ifs"] = FakeIfs(3, False)
        self.assertEqual(self.obj.get_status(0)["firmware"], "stock")

    def test_serial_not_opened_is_not_stock(self):
        self.printer.objects["ifs"] = FakeIfs(None, False)
        self.assertEqual(self.obj.get_status(0)["firmware"], "unknown")

    def test_firmware_from_last_result(self):
        self.write_status("target=stock\nstate=done\nphase=finished\n"
                          "message=ok\nversion=1.2\n")
        st = self.obj.get_status(0)
        self.assertEqual(st["firmware"], "stock")
        self.assertEqual(st["last"], {
            "target": "stock", "state": "done", "phase": "finished",
            "message": "ok", "version": "1.2"})

    def test_failed_last_result_is_unknown(self):
        self.write_status("target=stock\nstate=failed\n")
        self.assertEqual(self.obj.get_status(0)["firmware"], "unknown")

    def test_unknown(self):
        st = self.obj.get_status(0)
        self.assertEqual(st["firmware"], "unknown")
        self.assertFalse(st["switching"])
        self.assertEqual(st["last"], {k: "" for k in (
            "target", "state", "phase", "message", "version")})

    def test_switching_running(self):
        self.write_status("target=stock\nstate=running\n")
        self.assertTrue(self.obj.get_status(0)["switching"])

    def test_switching_request_pending(self):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.req, "w") as f:
            f.write("stock\n")
        self.assertTrue(self.obj.get_status(0)["switching"])

    def test_status_cache_once_a_second(self):
        self.write_status("target=stock\nstate=running\n")
        self.assertEqual(self.obj.get_status(0)["last"]["state"], "running")
        with open(self.status, "w") as f:
            f.write("target=stock\nstate=done\n")
        self.assertEqual(self.obj.get_status(0)["last"]["state"], "running")
        self.printer.reactor.now += 1.5
        self.assertEqual(self.obj.get_status(0)["last"]["state"], "done")


if __name__ == "__main__":
    unittest.main()
