import importlib.util
import os
import pathlib
import tempfile
import unittest

PATH = (pathlib.Path(__file__).resolve().parent.parent
        / "components" / "kiln_ifs_firmware.py")
spec = importlib.util.spec_from_file_location("kiln_ifs_firmware", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

KEYS = ("target", "state", "phase", "message", "version")


class ParseStatus(unittest.TestCase):
    def test_parse_full(self):
        text = ("target=stock\nstate=running\nphase=writing\n"
                "message=Flashing = fine\nversion=1.2.3\n")
        self.assertEqual(mod.parse_status(text), {
            "target": "stock", "state": "running", "phase": "writing",
            "message": "Flashing = fine", "version": "1.2.3"})

    def test_parse_missing_keys(self):
        r = mod.parse_status("state=done\n")
        self.assertEqual(set(r), set(KEYS))
        self.assertEqual(r["state"], "done")
        for k in KEYS:
            if k != "state":
                self.assertEqual(r[k], "")

    def test_parse_ignores_garbage_lines(self):
        r = mod.parse_status("junk\n\n=x\nbogus=1\ntarget=klipper\n# c\n")
        self.assertEqual(r["target"], "klipper")
        self.assertEqual(set(r), set(KEYS))


class ReadStatus(unittest.TestCase):
    def test_no_file_is_none(self):
        r = mod.read_status("/nonexistent/ifs-firmware.status")
        self.assertEqual(r["state"], "none")
        for k in KEYS:
            if k != "state":
                self.assertEqual(r[k], "")

    def test_reads_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s")
            with open(p, "w") as f:
                f.write("target=stock\nstate=done\n")
            r = mod.read_status(p)
        self.assertEqual((r["target"], r["state"]), ("stock", "done"))


class CheckRequest(unittest.TestCase):
    def test_ok(self):
        self.assertIsNone(mod.check_request("stock", "standby", "done"))
        self.assertIsNone(mod.check_request("klipper", "complete", "none"))

    def test_bad_target(self):
        self.assertEqual(mod.check_request("foo", "standby", "none"),
                         "target must be stock or klipper")

    def test_refused_printing_paused(self):
        for ps in ("printing", "paused"):
            self.assertEqual(mod.check_request("stock", ps, "done"),
                             "not while printing")

    def test_refused_running(self):
        self.assertEqual(mod.check_request("stock", "standby", "running"),
                         "a switch is already running")

    def test_klipper_unreachable_allowed(self):
        # Klipper down: nothing can be printing; the switch may bring it back
        self.assertIsNone(mod.check_request("klipper", None, "failed"))


class WriteRequest(unittest.TestCase):
    def test_request_written(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "ifs-firmware")
            mod.write_request(p, "stock")
            with open(p) as f:
                self.assertEqual(f.read(), "stock\n")
            self.assertEqual(os.listdir(os.path.dirname(p)),
                             ["ifs-firmware"])

    def test_pending_request_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ifs-firmware")
            mod.write_request(p, "stock")
            self.assertEqual(mod.check_request("klipper", "standby", "done",
                                               pending=True),
                             "a switch is already running")


if __name__ == "__main__":
    unittest.main()
