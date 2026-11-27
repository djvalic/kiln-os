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
#                  "filament_id": "PKLNPLA" (the slot's own, or Kiln's for
#                  the IFS types below),
#                  "spool_id", "vendor_name", "name" (the slot's, when set),
#                  "scan_time" (UTC, "%Y-%m-%dT%H:%M:%SZ", set
#                  when the slot's content changes after the first write)}
# The slot's spool details come from IFS_SET_MATERIAL SPOOL_ID= VENDOR=
# NAME= FILAMENT_ID= BED_TEMP= (plugin API 1.12, issue #101): spool_id,
# vendor_name, name, filament_id and bed_temp as set, FILAMENT_ID exactly
# as sent (an id from Orca's own library, e.g. "OFDSrzZ8"). Without a FILAMENT_ID, filament_id is the
# OrcaSlicer filament id of Kiln's profile for the slot's type (kiln-orca,
# profiles/tools/gen.py FILAMENT_IDS: keep both the same). OrcaSlicer then
# picks that exact profile, a user preset too; without the key (a custom
# type, an empty slot) it matches "material" against its system presets
# only.
# Kept up to date from Klipper's ifs_materials (IFS_SET_MATERIAL, the touch
# screen) and ifs.loaded_channels (a slot without filament is empty, its
# spool details left out as its type and colour are).
# No "vendor" or "spool_name" key: HelixScreen reads those as its own
# spellings and would not take an outside edit; Kiln writes the slot's
# vendor and name under "vendor_name" and "name" (the lane_data names).
#
# HelixScreen (the touch screen) writes the same records, each time the
# whole record, with keys of its own ("writer": "helixscreen", spool_id,
# vendor_name, filament_type, helix_*, its own filament_id). So Kiln merges:
# it reads the records, changes only its own keys (merge_lane) and writes
# only the lanes that then differ. Every other key stays, spool_id too.
# "writer" is never set: HelixScreen won't write a record another program
# signed, which would stop the screen's own slot edits. A spool detail the
# slot doesn't have leaves HelixScreen's key as it is; one Kiln wrote and
# the slot no longer has (cleared, the filament out) is taken out again.
# A HelixScreen write
# drops Kiln's keys in turn, so a cheap check (a read; a write only when a
# Kiln key is missing or wrong) runs a few seconds after each slot change
# and once a minute.
#
# AFC (AFC-Klipper-Add-On, the afc-kiln plugin) writes lane_data itself,
# one record per AFC lane (afc-kiln: T0..T3 for the same four slots). So
# when Klipper has an "AFC" object (its [AFC] section; Klipper names the
# object as the section is written and loads extras/AFC.py for it only by
# that spelling, so the check is case-sensitive), Kiln doesn't sync, stops
# its check and deletes the lane1..lane4 records it wrote alone (own_record:
# no "writer", only Kiln's keys); a record with HelixScreen's or AFC's keys
# stays. Checked again at each klippy ready: AFC can come or go with a
# Klipper restart.
#
# [kiln_lanes]
#
# This file may be distributed under the terms of the GNU GPLv3 license.

from __future__ import annotations
import asyncio
import copy
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..confighelper import ConfigHelper

NAMESPACE = "lane_data"
SLOTS = (1, 2, 3, 4)
KEYS = [f"lane{s}" for s in SLOTS]
# IFS slot type -> OrcaSlicer filament_id of Kiln's filament profile
FILAMENT_IDS = {
    "PLA": "PKLNPLA", "SILK": "PKLNSLK", "PLA-CF": "PKLNPCF",
    "PETG": "PKLNPET", "PETG-CF": "PKLNPGC", "ABS": "PKLNABS",
    "TPU": "PKLNTPU",
}
KILN_IDS = frozenset(FILAMENT_IDS.values())
# Klipper's object for AFC-Klipper-Add-On's [AFC] section
AFC_OBJECT = "AFC"
# the keys of a record Kiln wrote alone (merge_lane into no record)
OWN_KEYS = frozenset(("lane", "material", "color", "nozzle_temp",
                      "bed_temp", "filament_id", "spool_id", "vendor_name",
                      "name", "scan_time"))
# Kiln's content keys that say which filament is in the slot (another
# writer's bed_temp goes stale when one changes; the spool details don't)
FILAMENT_KEYS = ("lane", "material", "color", "nozzle_temp", "filament_id",
                 "slot_filament_id")
# seconds: re-check after a slot change (HelixScreen writes for the same
# change land within it), and between the checks otherwise
RECHECK_DELAY = 5.
CHECK_PERIOD = 60.


def filament_id(material: Any) -> Optional[str]:
    """Kiln's OrcaSlicer filament id for a slot type (any case, spaces
    around ignored), None for a custom type or an empty slot."""
    if not isinstance(material, str):
        return None
    return FILAMENT_IDS.get(material.strip().upper())


def _text(v: Any) -> Optional[str]:
    return v if isinstance(v, str) and v else None


def _int(v: Any) -> Optional[int]:
    if isinstance(v, int) and not isinstance(v, bool) and v > 0:
        return v
    return None


def slot_content(materials: Dict[str, Any],
                 ifs: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Kiln's own content per lane, from printer.ifs_materials and
    printer.ifs: lane, material, color, nozzle_temp, filament_id (Kiln's
    for the type, None for a custom type or an empty slot), and the slot's
    spool details (1.12, None when not set or the slot is empty):
    slot_filament_id, spool_id, vendor_name, name, bed_temp."""
    slots = materials.get("slots") or {}
    present: Optional[List[int]] = None
    if ifs.get("connected") and ifs.get("loaded_channels") is not None:
        present = list(ifs["loaded_channels"])
    content = {}
    for s in SLOTS:
        m = slots.get(str(s)) or {}
        mtype = m.get("type") or ""
        if present is not None and s not in present:
            mtype = ""
        temp = m.get("temp") if mtype else None
        content[f"lane{s}"] = {
            "lane": str(s - 1),
            "material": mtype,
            "color": (m.get("color") or "") if mtype else "",
            "nozzle_temp": int(round(temp)) if temp else 0,
            "filament_id": filament_id(mtype),
            "slot_filament_id": _text(m.get("filament_id")) if mtype
            else None,
            "spool_id": _int(m.get("spool_id")) if mtype else None,
            "vendor_name": _text(m.get("vendor")) if mtype else None,
            "name": _text(m.get("name")) if mtype else None,
            "bed_temp": _int(m.get("bed_temp")) if mtype else None,
        }
    return content


def helix_filament_id(rec: Dict[str, Any]) -> bool:
    """True when the record's filament_id is HelixScreen's: a string id
    that isn't one of Kiln's, marked with helix_filament_id_source (the
    linked Spoolman spool's extra.orca_filament_id, "spoolman") or written
    with a catalog pick (helix_catalog_id: HelixScreen sets no marker then).
    """
    fid = rec.get("filament_id")
    if not isinstance(fid, str) or not fid.strip() or fid in KILN_IDS:
        return False
    for marker in ("helix_filament_id_source", "helix_catalog_id"):
        v = rec.get(marker)
        if isinstance(v, str) and v:
            return True
    return False


def merge_lane(old: Optional[Dict[str, Any]], content: Dict[str, Any],
               changed: bool, now: str,
               prev: Optional[Dict[str, Any]] = None,
               untouched: bool = True) -> Dict[str, Any]:
    """The record Kiln stores: old (another writer's keys kept) with Kiln's
    keys from content. changed: the slot's content moved since Kiln's last
    pass (new scan_time). prev: Kiln's content for the lane at its last
    pass, None at the first (after a Moonraker start). untouched: old is
    the record as Kiln left it at that pass (nobody wrote it since).

    A spool detail (spool_id, vendor_name, name, filament_id, a positive
    bed_temp) the slot doesn't have is Kiln's to take out when Kiln wrote
    it: the value it wrote at the last pass, in a record nobody rewrote
    since (a HelixScreen write of the same value makes it HelixScreen's).
    At the first pass, with nothing remembered: all of them in a record
    without "writer" (only Kiln writes those; HelixScreen signs its own),
    none in a signed one."""
    rec = dict(old) if isinstance(old, dict) else {}
    first = prev is None
    own_record = first and isinstance(old, dict) and "writer" not in old
    prev = prev or {}

    def was_kilns(key: str, pkey: Optional[str] = None) -> bool:
        if own_record:
            return rec.get(key) is not None
        p = prev.get(pkey or key)
        return untouched and p is not None and rec.get(key) == p

    mtype = content["material"]
    rec["lane"] = content["lane"]
    rec["material"] = mtype
    rec["color"] = content["color"]
    rec["nozzle_temp"] = content["nozzle_temp"]
    # The slot's spool details (IFS_SET_MATERIAL, 1.12) when it has them;
    # without, another writer's key stays (HelixScreen's spool link)
    for key in ("vendor_name", "name"):
        v = content.get(key)
        if v is not None:
            rec[key] = v
        elif was_kilns(key):
            del rec[key]
    spool = content.get("spool_id")
    if spool is not None:
        rec["spool_id"] = spool
    elif was_kilns("spool_id"):
        rec["spool_id"] = None
    # The slot's bed temperature, else none (0): Kiln's own taken out.
    # Another writer's (HelixScreen's, for its material) is kept while the
    # slot holds the same filament: a change of spool details alone
    # (VENDOR=, ...) leaves it.
    bed = rec.get("bed_temp")
    filament_changed = changed and any(
        prev.get(k) != content.get(k) for k in FILAMENT_KEYS)
    if content.get("bed_temp") is not None:
        rec["bed_temp"] = content["bed_temp"]
    elif isinstance(bed, int) and bed > 0 and was_kilns("bed_temp"):
        rec["bed_temp"] = 0
    elif not (mtype and not filament_changed and isinstance(bed, int)
              and not isinstance(bed, bool) and bed > 0):
        rec["bed_temp"] = 0
    # The slot's own FILAMENT_ID, exactly as set, wins. One Kiln wrote and
    # the slot no longer has is taken out first.
    # Else a HelixScreen brand id is kept, an empty slot and another
    # material too: HelixScreen keeps the spool link and its id over both
    # (it writes it again at its next write), and OrcaSlicer reads a slot
    # with material "" as empty whatever its filament_id.
    sfid = content.get("slot_filament_id")
    if sfid is None and was_kilns("filament_id", "slot_filament_id"):
        del rec["filament_id"]
    if sfid is not None:
        rec["filament_id"] = sfid
        rec.pop("helix_filament_id_source", None)
    elif not helix_filament_id(rec):
        fid = content["filament_id"]
        if fid is not None:
            rec["filament_id"] = fid
            rec.pop("helix_filament_id_source", None)
        elif isinstance(rec.get("filament_id"), str):
            # Kiln's id (or an unmarked one) for a type it has none for
            del rec["filament_id"]
            rec.pop("helix_filament_id_source", None)
    rec.setdefault("spool_id", None)
    if changed:
        rec["scan_time"] = now
    elif not isinstance(rec.get("scan_time"), str):
        rec["scan_time"] = ""
    return rec


def merge_lanes(records: Dict[str, Any], content: Dict[str, Dict[str, Any]],
                prev: Optional[Dict[str, Dict[str, Any]]],
                now: str, stored: Optional[Dict[str, Any]] = None
                ) -> Dict[str, Dict[str, Any]]:
    """The lanes to write: records (as read from the database) merged with
    content, only those that differ from what's stored. prev is Kiln's
    content at its last pass (None before the first), stored the records
    as that pass left them (None: not known, taken as untouched)."""
    out = {}
    for key, c in content.items():
        old = records.get(key)
        changed = prev is not None and prev.get(key) != c
        untouched = stored is None or stored.get(key) == old
        rec = merge_lane(old, c, changed, now,
                         prev.get(key) if prev is not None else None,
                         untouched)
        if rec != old:
            out[key] = rec
    return out


def has_afc(objects: Any) -> bool:
    """True when Klipper's object list (printer.objects.list) has AFC's
    main object. Exact name: AFC's lanes, units and hubs are other objects
    ("AFC_stepper lane1", "AFC_BoxTurtle Turtle_1") that come with it."""
    return isinstance(objects, (list, tuple)) and AFC_OBJECT in objects


def own_record(key: str, rec: Any) -> bool:
    """True when rec, stored under key, is a record Kiln wrote alone: no
    "writer" (HelixScreen signs its records), only Kiln's keys (none of
    HelixScreen's or AFC's, such as AFC's "td" and "extruder_index" under
    an AFC lane named lane1) and Kiln's tool for that key."""
    if key not in KEYS or not isinstance(rec, dict) or "writer" in rec:
        return False
    if not set(rec) <= OWN_KEYS:
        return False
    return rec.get("lane") == str(KEYS.index(key))


def build_lanes(materials: Dict[str, Any], ifs: Dict[str, Any],
                prev: Optional[Dict[str, Dict[str, Any]]] = None,
                now: str = "") -> Dict[str, Dict[str, Any]]:
    """The four records Kiln writes into an empty namespace."""
    content = slot_content(materials, ifs)
    return {key: merge_lane(None, c, prev is not None
                            and prev.get(key) != c, now,
                            prev.get(key) if prev is not None else None)
            for key, c in content.items()}


class KilnLanes:
    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.db = self.server.load_component(config, "database")
        self.materials: Dict[str, Any] = {}
        self.ifs: Dict[str, Any] = {}
        # Kiln's content at the last pass, None before the first; the
        # records as that pass left them
        self.content: Optional[Dict[str, Dict[str, Any]]] = None
        self.stored: Optional[Dict[str, Any]] = None
        # Klipper has AFC (at the last klippy ready): lane_data is AFC's
        self.afc = False
        self.lock = asyncio.Lock()
        self.timer = self.server.get_event_loop().register_timer(
            self._on_timer)
        self.server.register_event_handler(
            "server:klippy_ready", self._on_ready)

    async def _on_ready(self) -> None:
        kapis = self.server.lookup_component("klippy_apis")
        objects = await kapis.get_object_list(default=None)
        if objects is None:
            logging.info("kiln_lanes: no object list from Klipper, "
                         "taken as without AFC")
        self.afc = has_afc(objects)
        if self.afc:
            self.timer.stop()
            self.materials = {}
            self.ifs = {}
            self.content = None
            self.stored = None
            logging.info("kiln_lanes: AFC in Klipper, lane_data left to AFC")
            await self._remove_own()
            return
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
        await self._sync()
        self.timer.start(CHECK_PERIOD)

    async def _on_status(self, status: Dict[str, Any],
                         eventtime: float) -> None:
        if self.afc:
            return
        changed = False
        if "ifs_materials" in status:
            self.materials.update(status["ifs_materials"])
            changed = True
        if "ifs" in status:
            self.ifs.update(status["ifs"])
            changed = True
        if not changed or not self.materials:
            return
        if slot_content(self.materials, self.ifs) == self.content:
            return
        await self._sync()
        # HelixScreen writes for the same change after Kiln: check again
        self.timer.stop()
        self.timer.start(RECHECK_DELAY)

    async def _on_timer(self, eventtime: float) -> float:
        if self.afc:
            self.timer.stop()
            return eventtime
        if self.materials:
            await self._sync()
        return eventtime + CHECK_PERIOD

    async def _sync(self) -> None:
        """Read the records, merge Kiln's keys in, write the lanes that
        differ (none: no write). Nothing with AFC."""
        async with self.lock:
            # checked under the lock: a pass waiting on _remove_own's
            if self.afc:
                return
            content = slot_content(self.materials, self.ifs)
            try:
                records = await self.db.get_batch(NAMESPACE, KEYS)
            except Exception:
                logging.exception("kiln_lanes: lane_data not readable")
                return
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            records = records or {}
            lanes = merge_lanes(records, content, self.content, now,
                                self.stored)
            if lanes:
                try:
                    await self.db.insert_batch(NAMESPACE, lanes)
                except Exception:
                    logging.exception("kiln_lanes: lane_data not written")
                    return
                logging.debug(f"kiln_lanes: {lanes}")
            self.content = content
            self.stored = {k: copy.deepcopy(lanes.get(k, records.get(k)))
                           for k in KEYS}

    async def _remove_own(self) -> None:
        """Delete the lane1..lane4 records Kiln wrote alone (own_record),
        so AFC's are the only ones; any other record stays."""
        async with self.lock:
            try:
                records = await self.db.get_batch(NAMESPACE, KEYS)
            except Exception:
                logging.exception("kiln_lanes: lane_data not readable")
                return
            own = [k for k in KEYS if own_record(k, (records or {}).get(k))]
            if not own:
                return
            try:
                await self.db.delete_batch(NAMESPACE, own)
            except Exception:
                logging.exception("kiln_lanes: lane_data not deleted")
                return
            logging.info(f"kiln_lanes: removed its records {own} (AFC)")


def load_component(config: ConfigHelper) -> KilnLanes:
    return KilnLanes(config)
