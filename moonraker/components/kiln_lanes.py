# The IFS slots in Moonraker's database, namespace "lane_data", for slicers
#
# OrcaSlicer's Moonraker printer agent (nightlies after 2.4.2, Preferences >
# Developer > "Use printer agents instead of print hosts") reads
# /server/database/item?namespace=lane_data to fill its filament list with
# what is loaded, the same data AFC writes. One record per IFS slot:
#   lane1..lane4: {"lane": "0".."3"  (the slicer tool: slot 1 = T0, as
#                                     IFS_MAP_TOOL's default map)
#                  "material": "PLA" ("" = no filament or no type set)
#                  "color": "#RRGGBB", "nozzle_temp": 220, "bed_temp": 0,
#                  "spool_id", "scan_time" (UTC, "%Y-%m-%dT%H:%M:%SZ", set
#                  when the slot's content changes after the first write)}
# Kept up to date from Klipper's ifs_materials (IFS_SET_MATERIAL, the touch
# screen) and ifs.loaded_channels (a slot without filament is empty).
# No "vendor" or "name" key: HelixScreen reads "vendor" and "spool_name" as
# its own spellings and would not take an outside edit, and Kiln has no
# vendor or spool name to write under "vendor_name" or "name".
#
# [kiln_lanes]
#
# This file may be distributed under the terms of the GNU GPLv3 license.

from __future__ import annotations
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..confighelper import ConfigHelper

NAMESPACE = "lane_data"
SLOTS = (1, 2, 3, 4)


def build_lanes(materials: Dict[str, Any], ifs: Dict[str, Any],
                prev: Optional[Dict[str, Dict[str, Any]]] = None,
                now: str = "") -> Dict[str, Dict[str, Any]]:
    """lane_data records from printer.ifs_materials and printer.ifs.

    prev is the last lanes written (None before the first write). A lane
    whose content is unchanged keeps its scan_time; a changed lane gets now.
    """
    slots = materials.get("slots") or {}
    present: Optional[List[int]] = None
    if ifs.get("connected") and ifs.get("loaded_channels") is not None:
        present = list(ifs["loaded_channels"])
    lanes = {}
    for s in SLOTS:
        m = slots.get(str(s)) or {}
        mtype = m.get("type") or ""
        if present is not None and s not in present:
            mtype = ""
        temp = m.get("temp") if mtype else None
        lane = {
            "lane": str(s - 1),
            "material": mtype,
            "color": (m.get("color") or "") if mtype else "",
            "nozzle_temp": int(round(temp)) if temp else 0,
            "bed_temp": 0,
            "spool_id": None,
        }
        old = (prev or {}).get(f"lane{s}")
        if old is not None and {k: v for k, v in old.items()
                                if k != "scan_time"} == lane:
            lane["scan_time"] = old.get("scan_time", "")
        else:
            lane["scan_time"] = now if prev is not None else ""
        lanes[f"lane{s}"] = lane
    return lanes


class KilnLanes:
    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.db = self.server.load_component(config, "database")
        self.materials: Dict[str, Any] = {}
        self.ifs: Dict[str, Any] = {}
        self.written: Optional[Dict[str, Any]] = None
        self.server.register_event_handler(
            "server:klippy_ready", self._on_ready)

    async def _on_ready(self) -> None:
        kapis = self.server.lookup_component("klippy_apis")
        objs = {"ifs_materials": None,
                "ifs": ["connected", "loaded_channels"]}
        try:
            status = await kapis.subscribe_objects(objs, self._on_status)
        except self.server.error as e:
            logging.info(f"kiln_lanes: no IFS in Klipper ({e})")
            return
        if "ifs_materials" not in status:
            logging.info("kiln_lanes: no [ifs] in Klipper, lane_data unused")
            return
        self.materials = status.get("ifs_materials") or {}
        self.ifs = status.get("ifs") or {}
        await self._write()

    async def _on_status(self, status: Dict[str, Any],
                         eventtime: float) -> None:
        changed = False
        if "ifs_materials" in status:
            self.materials.update(status["ifs_materials"])
            changed = True
        if "ifs" in status:
            self.ifs.update(status["ifs"])
            changed = True
        if changed and self.materials:
            await self._write()

    async def _write(self) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        lanes = build_lanes(self.materials, self.ifs, self.written, now)
        if lanes == self.written:
            return
        await self.db.insert_batch(NAMESPACE, lanes)
        self.written = lanes
        logging.debug(f"kiln_lanes: {lanes}")


def load_component(config: ConfigHelper) -> KilnLanes:
    return KilnLanes(config)
