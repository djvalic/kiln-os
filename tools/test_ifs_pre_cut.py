#!/usr/bin/env python3
"""Focused, hardware-free tests of optional IFS pre-cut retraction."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location(
    "ifs", Path(__file__).resolve().parents[1] / "klipper/extras/ifs.py")
ifs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ifs)


class PreCutTests(unittest.TestCase):
    def setUp(self):
        self.m = m = ifs.IFS.__new__(ifs.IFS)
        m.pre_cut_retract_length = 20.
        m.pre_cut_retract_speed = 600.
        m.prime_length = 17.
        m.channel = 2
        m.channel_source = "kiln"
        m.refill_busy = False
        m.materials = [{"type": "PLA"} for _ in range(4)]
        m._in_print = Mock(return_value=True)
        m._purge_mode = Mock(return_value=2)
        m._head_has_filament = Mock(return_value=True)
        m._head_settled = Mock(return_value=True)
        m._query_status = Mock(return_value={"silk_state": 6})
        m.reactor = Mock()
        m.printer = Mock()
        m.printer.lookup_object.return_value.get_status.return_value = {
            "extrude_factor": 1., "speed_factor": 1.}
        m.gcode = Mock()
        for name in ("_release", "_check_stop", "_track", "_run_template",
                     "_ensure_hot", "_push", "_set_channel",
                     "_clear_inserted", "_unload", "_select", "_load"):
            setattr(m, name, Mock())
        for name in ("before_template", "cut_template", "purge_start_template",
                     "prime_template", "prime_at_print_template",
                     "after_template"):
            setattr(m, name, Mock())
        m.load_length = 1000.
        m.load_speed = 1200.

    def test_disabled(self):
        self.m.pre_cut_retract_length = 0.
        self.assertEqual(self.m._pre_cut_retract(2, 3), 0.)
        self.m._release.assert_not_called()
        self.m.gcode.run_script_from_command.assert_not_called()

    def test_eligible_retract(self):
        self.assertEqual(self.m._pre_cut_retract(2, 3), 20.)
        self.m._release.assert_called_once_with(2)
        self.m.gcode.run_script_from_command.assert_called_once_with(
            "M83\nG1 E-20 F600")

    def test_guard_conditions(self):
        m = self.m
        for obj, attr, bad in (
            (m, "channel_source", "adopted"),
            (m, "channel", 1),
            (m, "refill_busy", True),
            (m._in_print, "return_value", False),
            (m._purge_mode, "return_value", 0),
            (m._purge_mode, "return_value", 1),
            (m._head_has_filament, "return_value", None),
            (m._head_has_filament, "return_value", False),
            (m._query_status, "return_value", {"silk_state": 2}),
        ):
            with self.subTest(attr=attr, value=bad):
                original = getattr(obj, attr)
                try:
                    setattr(obj, attr, bad)
                    self.assertEqual(m._pre_cut_retract(2, 3), 0.)
                    m._release.assert_not_called()
                    m.gcode.run_script_from_command.assert_not_called()
                finally:
                    setattr(obj, attr, original)

    def test_material_and_overrides(self):
        m = self.m
        m.materials[2]["type"] = "PETG"
        self.assertEqual(m._pre_cut_retract(2, 3), 0.)
        m.materials[2]["type"] = "PLA"
        for key in ("extrude_factor", "speed_factor"):
            status = {"extrude_factor": 1., "speed_factor": 1.}
            status[key] = .9
            m.printer.lookup_object.return_value.get_status.return_value = status
            self.assertEqual(m._pre_cut_retract(2, 3), 0.)
        m.gcode.run_script_from_command.assert_not_called()

    def test_sensor_loss_aborts_before_cut(self):
        self.m._head_settled.return_value = False
        with self.assertRaises(ifs.IfsError):
            self.m._swap(2, 3, purge=False, allow_pre_cut=True)
        self.m._unload.assert_not_called()
        self.m._load.assert_not_called()
        self.m._push.assert_not_called()

    def test_compensated_swap(self):
        self.m._swap(2, 3, purge=False, allow_pre_cut=True)
        self.m._push.assert_called_once_with(3, 37.)

    def test_uncompensated_swap(self):
        self.m._swap(2, 3, purge=False)
        self.m._push.assert_called_once_with(3, 17.)
        self.m.gcode.run_script_from_command.assert_not_called()

    def test_first_tool_change_allows_retract(self):
        m = self.m
        m.first_swap_pending = True
        m._refuse_blocked = Mock()
        m.last_status = {"silk_state": 6}
        m._purge_mode_says_slicer = Mock(return_value=True)
        m._at_print_ok = Mock(return_value=False)
        m._require_homed = Mock(return_value=False)
        m._with_heat = Mock()
        cmd = Mock()
        cmd.get_int.return_value = None
        cmd.get_float.return_value = None
        m._tool_change(cmd, 3)
        self.assertFalse(m.first_swap_pending)
        args = m._with_heat.call_args.args
        self.assertEqual(args[-3:], (False, False, True))


if __name__ == "__main__":
    unittest.main()
