# printer.ifs_firmware: which firmware the IFS filament unit runs
# (Flashforge's or Klipper's), whether a switch is under way and the last
# result. The switch itself is asked for through Moonraker
# (POST /server/kiln/ifs_firmware, moonraker/components/kiln_ifs_firmware.py)
# and done by the root update agent (S68ad5x-update-agent), which writes the
# status file read here. There is deliberately no G-code command: the
# switch stops Klipper, and no macro or print file may start it.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os

REQUEST_PATH = "/data/ad5x/kiln-update/ifs-firmware"
STATUS_PATH = "/data/ad5x/kiln-status/ifs-firmware.status"
TARGETS = ("stock", "klipper")
STATUS_KEYS = ("target", "state", "phase", "message", "version")
CACHE_SECONDS = 1.

class IFSFirmware:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.request_path = config.get('request_path', REQUEST_PATH)
        self.status_path = config.get('status_path', STATUS_PATH)
        self.cache = None
        self.cache_time = None

    def _now(self):
        return self.printer.get_reactor().monotonic()

    def _read_status(self):
        """The five status keys as strings; all empty without a file."""
        last = {k: "" for k in STATUS_KEYS}
        try:
            with open(self.status_path) as f:
                for line in f:
                    key, sep, value = line.rstrip("\n").partition("=")
                    if sep and key in last:
                        last[key] = value.strip()
        except OSError:
            pass
        return last

    def _status(self):
        now = self._now()
        if self.cache is None or now - self.cache_time >= CACHE_SECONDS \
                or now < self.cache_time:
            self.cache = self._read_status()
            self.cache_time = now
        return self.cache

    def _firmware(self, last):
        if self.printer.lookup_object('mcu ifs', None) is not None:
            return "klipper"
        ifs = self.printer.lookup_object('ifs', None)
        if (ifs is not None and getattr(ifs, 'fd', None) is not None
                and not getattr(ifs, 'is_mcu_mode', False)):
            return "stock"
        if last['state'] == "done" and last['target'] in TARGETS:
            return last['target']
        return "unknown"

    def get_status(self, eventtime):
        last = self._status()
        return {
            'firmware': self._firmware(last),
            'switching': (last['state'] == "running"
                          or os.path.exists(self.request_path)),
            'last': dict(last)}

def load_config(config):
    return IFSFirmware(config)
