# The IFS firmware switch status for the touch screen
#
# The root agent writes key=value lines to
# /data/ad5x/kiln-status/ifs-firmware.status while it switches the IFS
# between stock and Klipper firmware. This serves them to the screen:
#   GET /server/kiln/ifs_firmware
#     -> {"target", "state", "phase", "message", "version"}, all strings;
#        state is "none" (the rest "") when there is no status file.
#   POST /server/kiln/ifs_firmware  {"target": "stock"|"klipper"}
#     -> asks the root agent (S68ad5x-update-agent) to switch: writes the
#        request file /data/ad5x/kiln-update/ifs-firmware and returns the
#        status. Refused (409) while printing or paused, or while a switch
#        is requested or running; 400 for another target.
# The switch stops Klipper, so it is started here and not by a G-code
# command: no macro or print file can start it. The file is read per
# request.
#
# [kiln_ifs_firmware]
# status_path: /data/ad5x/kiln-status/ifs-firmware.status   (optional)
#
# This file may be distributed under the terms of the GNU GPLv3 license.

from __future__ import annotations
import os
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..confighelper import ConfigHelper

STATUS_PATH = "/data/ad5x/kiln-status/ifs-firmware.status"
REQUEST_PATH = "/data/ad5x/kiln-update/ifs-firmware"
TARGETS = ("stock", "klipper")
# print_stats states during which the IFS can't be switched
BUSY_STATES = ("printing", "paused")
KEYS = ("target", "state", "phase", "message", "version")


def parse_status(text: str) -> Dict[str, str]:
    """The five status keys from key=value lines; missing ones are ""."""
    out = {k: "" for k in KEYS}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key in out:
            out[key] = value.strip()
    return out


def read_status(path: str) -> Dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return parse_status(f.read())
    except OSError:
        res = parse_status("")
        res["state"] = "none"
        return res


def check_request(target: str, print_state: Optional[str],
                  status_state: str, pending: bool = False
                  ) -> Optional[str]:
    """Why a switch to TARGET is refused, or None. print_state is None when
    Klipper doesn't answer: then nothing prints, and the switch may be what
    brings Klipper back."""
    if target not in TARGETS:
        return "target must be stock or klipper"
    if print_state in BUSY_STATES:
        return "not while printing"
    if status_state == "running" or pending:
        return "a switch is already running"
    return None


def write_request(path: str, target: str) -> None:
    """Written under a dot-name and renamed, so root never reads half a
    line."""
    directory = os.path.dirname(path)
    tmp = os.path.join(directory, "." + os.path.basename(path) + ".tmp")
    os.makedirs(directory, exist_ok=True)
    try:
        with open(tmp, "w") as f:
            f.write(target + "\n")
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


class KilnIfsFirmware:
    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.path = config.get("status_path", STATUS_PATH)
        self.request_path = config.get("request_path", REQUEST_PATH)
        from ..common import RequestType
        self.post = RequestType.POST
        self.server.register_endpoint(
            "/server/kiln/ifs_firmware", RequestType.GET | RequestType.POST,
            self._handle)

    async def _print_state(self) -> Optional[str]:
        kapis = self.server.lookup_component("klippy_apis")
        res = await kapis.query_objects({"print_stats": ["state"]}, None)
        if not isinstance(res, dict):
            return None
        return res.get("print_stats", {}).get("state")

    async def _handle(self, web_request: Any) -> Dict[str, str]:
        if web_request.get_request_type() != self.post:
            return read_status(self.path)
        target = web_request.get_str("target", "").strip().lower()
        why = check_request(target, await self._print_state(),
                            read_status(self.path)["state"],
                            os.path.exists(self.request_path))
        if why is not None:
            code = 400 if target not in TARGETS else 409
            raise self.server.error(why, code)
        try:
            write_request(self.request_path, target)
        except OSError as e:
            raise self.server.error(
                f"can't write {self.request_path}: {e}", 500)
        return read_status(self.path)


def load_component(config: ConfigHelper) -> KilnIfsFirmware:
    return KilnIfsFirmware(config)
