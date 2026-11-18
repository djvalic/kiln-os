# Kiln OS updates in Moonraker's update manager (docs/updates.md)
#
# Adds a "Kiln OS" entry to update_manager, so Fluidd (and anything else
# using /machine/update/*) shows "Kiln OS vX -> vY" next to Fluidd and
# installs it with its Update button:
#   refresh: the newest release on the update server (GitHub or Gitea API)
#            for the printer's update channel, against /etc/kiln-version.
#            "stable" (the default): /repos/OWNER/REPO/releases/latest (no
#            drafts, no pre-releases). "test": the newest by version_key
#            among all releases vX.Y.Z[-SUFFIX] that are not drafts, so
#            release candidates (pre-releases) too, and the final release
#            once it is out. Switching back to stable never downgrades:
#            an older stable release is not offered.
#   update:  downloads kiln-os-VERSION-update.zip, checks it against the
#            release's SHA256SUMS, and hands it to ad5x-update-agent (root,
#            S68ad5x-update-agent), which stages it for the recovery OS and
#            reboots. The recovery installs it into slot B and boots it.
# Klipper and Moonraker: their entries offer the daily packages
# (pre-releases "klipper-vX.Y.Z-N-gHASH", "moonraker-..."): the newest one
# newer than what runs and tested on this OS or an older one (os_min in its
# release notes). Update downloads klipper-....tar.gz, checks it, and the
# agent unpacks it into /data/ad5x/apps/NAME and restarts the service. The
# image's copy runs again when it is newer (after a Kiln OS update) or the
# package is deleted (lib/apps.sh has the same rules).
# The kernel (issue #42): when /data/ad5x/kernel/failed names the release of
# our kernel in this image (S00ad5x-kernel), the printer runs on the stock
# kernel: a Moonraker warning says so (Fluidd shows it). The same when the
# opt-in mainline 7.3 kernel (ad5x-kernel mainline on) failed and the
# printer fell back to 6.6 (/data/ad5x/kernel/failed-mainline). Endpoints:
#   GET  /machine/kiln_os/kernel        running, ours, failed, why, ...
#   POST /machine/kiln_os/kernel_retry  the agent runs "ad5x-kernel retry"
#                                       (clears both records) and reboots
#                                       (refused while printing)
# The "Kiln OS" update entry's status has the same under "kernel".
# The recovery OS (issue #47):
#   POST /machine/kiln_os/boot_recovery the agent runs "ad5x-boot-recovery"
#                                       (boot flag on slot A) and reboots
#                                       into the recovery OS (refused while
#                                       printing or still starting up)
#   POST /machine/kiln_os/return_stock  the same, and the recovery OS opens
#                                       Return to Flashforge firmware
#                                       (ad5x-boot-recovery --return-stock);
#                                       nothing is written before a tap there
# Service restarts: the kiln_agent provider of Moonraker's machine
# component (service_provider below, Moonraker patch 0006) starts, stops
# and restarts klipper, moonraker, nginx, helixscreen and ad5x-camera
# through the agent (refused while printing).
# Reboot and shutdown: the same provider answers Moonraker's
# /machine/reboot and /machine/shutdown (and the reboot_machine and
# shutdown_machine remote methods) through the agent too, instead of
# upstream's "sudo reboot": refused while printing, while the recovery OS
# is being written and while start-up hasn't finished (docs/api.md).
# The plugin folder (docs/plugins.md): a link "plugins" in the config folder
# to /data/ad5x/plugins, made at Moonraker's start when missing, so Fluidd's
# file manager (Configuration) shows the plugins' files and can upload and
# edit them. Moonraker follows links to folders in a root and keeps .git
# folders out of reach. Fluidd 1.38 shows a root of its own read-only, so
# a link it is, not register_directory. Uploading runs nothing: root/
# scripts still need ENABLE_PLUGIN ... ROOT=1 (klipper/extras/ad5x_plugins.py).
# For clients (docs/api.md):
#   GET  /machine/kiln_os/info          OS version, API version (the plugin
#                                       API's, from os-release), running
#                                       kernel, feature names, update channel
#   POST /machine/kiln_os/channel       ?channel=stable|test: the update
#                                       channel, kept in Moonraker's database
#                                       (namespace kiln_os, key
#                                       update_channel; survives updates)
#   GET  /machine/kiln_os/memory        Extended memory mode (512 MiB boards,
#                                       docs/memory.md): available, enabled,
#                                       active, restart_needed, failed,
#                                       bootloader_update_needed, ...
#   POST /machine/kiln_os/memory        ?enable=true|false: the agent runs
#                                       "ad5x-memory extended on|off" (only
#                                       the switch in /data/ad5x/kernel; the
#                                       next start uses it), also while
#                                       printing; 409 not_available on 256 MiB
#   POST /machine/kiln_os/memory_notice_seen
#                                       the one-time notice "Extended memory
#                                       available" is seen (database
#                                       namespace kiln_os, memory_notice_seen)
# The same notice as a Moonraker announcement (feed kiln_os) for Fluidd and
# Mainsail; dismissing it there counts as seen (snoozing doesn't). Klipper's
# macro KILN_MEMORY_MODE [ENABLE=0|1] (macros/system.cfg) calls the remote
# method kiln_memory_mode, answered in the G-code console.
# The IFS firmware switch (docs/mcu-flashing.md, "IFS firmware switch"):
#   GET  /machine/kiln_os/ifs_firmware  available (the owner turned it on
#                                       and the image has Klipper's IFS
#                                       firmware), the running firmware,
#                                       the last switch: state idle,
#                                       running, done or failed, phase,
#                                       reason, message, version
#   POST /machine/kiln_os/ifs_firmware  ?target=stock|klipper: the agent
#                                       checks and answers at once, then
#                                       switches in the background (Klipper
#                                       stops for 1-4 minutes); klipper
#                                       only with the owner's opt-in,
#                                       refused while printing or while a
#                                       switch runs. No G-code starts it.
# Every endpoint answers an object (Moonraker adds HTTP's one "result");
# errors are KilnError: an HTTP status by kind and "[REASON] text"
# (docs/api.md, "Errors").
#
# [kiln_os]
# server: https://github.com    # or a Gitea server, e.g. http://HOST:3000
# repo: OWNER/REPO
# token_file: /data/ad5x/kiln-os.token   # read token, for a private repo
#
# This file may be distributed under the terms of the GNU GPLv3 license.

from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import pathlib
import re
import time
import urllib.request
from typing import (TYPE_CHECKING, Any, Callable, Dict, List, Optional,
                    Tuple)

from ..common import RequestType
from ..utils.exceptions import AgentError
from .update_manager.base_deploy import BaseDeploy

if TYPE_CHECKING:
    from ..common import WebRequest
    from ..confighelper import ConfigHelper
    from .http_client import HttpClient

VERSION_FILE = pathlib.Path("/etc/kiln-version")
WORK_DIR = pathlib.Path("/data/ad5x/kiln-update")
AGENT_REQUEST = WORK_DIR / "install"
AGENT_STATUS = WORK_DIR / "status"
AGENT_KERNEL_RETRY = WORK_DIR / "kernel-retry"
AGENT_BOOT_RECOVERY = WORK_DIR / "boot-recovery"
AGENT_RETURN_STOCK = WORK_DIR / "return-stock"
AGENT_REBOOT = WORK_DIR / "reboot"
AGENT_SHUTDOWN = WORK_DIR / "shutdown"
AGENT_IFS = WORK_DIR / "ifs-firmware"
PLUGINS_DIR = pathlib.Path("/data/ad5x/plugins")
PLUGINS_LINK = "plugins"
APPS_DIR = pathlib.Path("/data/ad5x/apps")
APP_SUB = {"klipper": "klippy", "moonraker": "moonraker"}
KERNEL_DIR = pathlib.Path("/data/ad5x/kernel")
OUR_KERNEL = pathlib.Path("/usr/lib/ad5x/kernel66/release")
MAINLINE_KERNEL = pathlib.Path("/usr/lib/ad5x/kernel-mainline/release")
KERNEL_WARNING = "kiln_os_kernel"
# AD5X_PLUGIN_API: post-build.sh copies PLUGIN_API_VERSION from Klipper's
# ad5x_plugins.py here, so Moonraker reads the same number Klipper offers
OS_RELEASE = pathlib.Path("/usr/lib/os-release")
# What this OS offers clients (docs/api.md, "Feature names"); "updates" and
# "lane_data" are added while their components run
FEATURES = ("ifs", "soak", "setup_wizard", "plugins", "kernel_retry",
            "boot_recovery", "3mf_upload", "print_error", "return_stock",
            "ifs_firmware")
# The update channel (docs/updates.md, "Test channel"): in Moonraker's
# database, so it survives Kiln OS updates; only POST /machine/kiln_os/channel
# writes it (a protected namespace)
CHANNELS = ("stable", "test")
DEFAULT_CHANNEL = "stable"
DB_NAMESPACE = "kiln_os"
DB_CHANNEL_KEY = "update_channel"
# Extended memory mode (docs/memory.md): S04ad5x-memory's record of this
# start (MEM_KB, LOW_MEM, HW_MEM_MIB=256|512, MEM_MODE=standard|extended,
# MEM_MODE_FIXED=0|1: an older Kiln U-Boot that can't choose the mode),
# the switch (written by ad5x-memory, root) and the failure record of a
# start in extended mode that didn't finish (line 1: reason, date), both in
# KERNEL_DIR
MEMORY_CONF = pathlib.Path("/run/ad5x-memory.conf")
MEMORY_SWITCH = "extended-memory"
MEMORY_FAILED = "extended-memory-failed"
AGENT_MEMORY = WORK_DIR / "memory-mode"
MEMORY_MODES = ("standard", "extended")
DB_NOTICE_KEY = "memory_notice_seen"
# The notice (the touch screen's bell and a Moonraker announcement)
NOTICE_FEED = "kiln_os"
NOTICE_TITLE = "Extended memory available"
NOTICE_TEXT = (
    "This printer has 512 MiB of memory. Kiln OS uses 256 MiB by default, "
    "the same on every AD5X. You can switch Extended memory on in Settings "
    "> System. It isn't needed; it is off by default.")
NOTICE_URL = ("https://github.com/djvalic/kiln-os/blob/main/docs/api.md"
              "#get-machinekiln_osmemory")
MEMORY_FAILED_TEXT = ("Extended memory was turned off: the printer didn't "
                      "finish starting with it.")
REMOTE_MEMORY = "kiln_memory_mode"
# The IFS firmware switch: the agent's status of the last switch (root's
# folder, S68ad5x-update-agent ifs_job), the owner's opt-in (either file;
# root's folder, so only the owner over SSH, or a plugin's root script the
# owner allowed, makes one), the image's Klipper firmware for the IFS and
# its version, and S61klipper's record that the IFS answered as Klipper
IFS_STATUS = pathlib.Path("/data/ad5x/kiln-status/ifs-firmware")
IFS_OPTIN = pathlib.Path("/data/ad5x/ifs-switch.enable")
IFS_KLIPPER_ENABLE = pathlib.Path("/data/ad5x/ifs-klipper.enable")
IFS_IMAGE = pathlib.Path("/usr/share/ad5x/mcu/ifs.hex")
IFS_IMAGE_VERSION = pathlib.Path("/usr/share/ad5x/mcu/IFS_VERSION")
IFS_ANSWERS_KLIPPER = pathlib.Path("/run/ad5x/ifs-klipper")
IFS_TARGETS = ("stock", "klipper")
IFS_STATES = ("running", "done", "failed")
IFS_KEYS = ("target", "state", "phase", "reason", "message", "version")
# A Kiln OS release tag (not the daily packages "klipper-v...", not "sources")
OS_TAG = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?")


# Errors (docs/api.md, "Errors"): an HTTP status by kind (400 a bad or
# missing parameter, 409 refused because of the printer's state, 500 a
# failure on the printer, 502 a download, 503 the root agent or the
# database not there or not answering) and a short reason for programs.
# Moonraker's HTTP error body has only "code" and "message" (and a
# traceback), so the reason starts the message, "[REASON] text", on both
# transports. Over the websocket Moonraker also passes an AgentError's data
# on as the JSON-RPC error's "data": {"reason": REASON} there. AgentError
# is Moonraker's class for errors that carry data; its own code (424) is
# replaced by ours.
class KilnError(AgentError):
    def __init__(self, reason: str, message: str, code: int) -> None:
        super().__init__(f"[{reason}] {message}", {"reason": reason})
        self.status_code = code
        self.reason = reason


# kernel_retry's and boot_recovery's reply: the object itself, as every
# Kiln endpoint (Moonraker adds the one "result" of HTTP replies). "result"
# is deprecated: touch screens before v0.1.0-rc1 (HelixScreen 0055) read
# result.result and get this code through a daily Moonraker package; it
# goes at the next major API version (docs/api.md). Clients read "state".
REBOOTING: Dict[str, str] = {"state": "rebooting", "result": "rebooting"}


def bad_parameter(message: str) -> KilnError:
    return KilnError("bad_parameter", message, 400)


# The agent's refusals ("refused: TEXT" in its status file) by the start of
# TEXT (S68ad5x-update-agent, ad5x-boot-recovery); anything else it refuses
# is "refused". tools/test_kiln_os.py checks that every refusal in those
# scripts has a reason here.
AGENT_REFUSALS: Tuple[Tuple[str, str], ...] = (
    ("a print is running", "printing"),
    ("the print state is unknown", "print_state_unknown"),
    ("no answer from Moonraker", "print_state_unknown"),
    ("start-up has not finished", "starting_up"),
    ("the recovery OS is being written", "recovery_updating"),
    ("slot A doesn't hold the recovery OS", "no_recovery"),
    ("this printer has 256 MiB", "not_available"),
    ("the IFS firmware is being switched", "ifs_switching"),
    ("the IFS firmware switch is off", "not_enabled"),
    ("this image has no Klipper firmware for the IFS", "not_available"),
    ("the printer is busy", "printer_busy"),
)
# Refusals that are failures on the printer (500)
AGENT_REFUSAL_FAILURES = ("can't write the boot flag",)


def agent_error(status: str) -> KilnError:
    """The error for an agent status that is a refusal or a failure"""
    kind, _, text = status.partition(":")
    # One line: the message is also HTTP's reason phrase
    text = "; ".join(t.strip() for t in text.splitlines() if t.strip()) \
        or kind
    if kind == "refused" and not text.startswith(AGENT_REFUSAL_FAILURES):
        reason = next((r for start, r in AGENT_REFUSALS
                       if text.startswith(start)), "refused")
        return KilnError(reason, text[:1].upper() + text[1:], 409)
    return KilnError("agent_failed", f"The update agent failed: {text}", 500)


def read_kiln_version() -> Dict[str, str]:
    info = {"VERSION": "v0.0.0", "COMMIT": "", "DATE": ""}
    try:
        for line in VERSION_FILE.read_text().splitlines():
            key, sep, val = line.partition("=")
            if sep:
                info[key.strip()] = val.strip()
    except OSError:
        # Images from before /etc/kiln-version: older than any release
        info["VERSION"] = "v0.0.0"
    return info


def read_api_version() -> Optional[str]:
    """AD5X_PLUGIN_API from os-release, None when missing"""
    try:
        for line in OS_RELEASE.read_text().splitlines():
            key, sep, val = line.partition("=")
            if sep and key.strip() == "AD5X_PLUGIN_API":
                return val.strip().strip('"\'') or None
    except (OSError, ValueError):
        pass
    return None


def version_key(ver: str) -> tuple:
    # vMAJOR.MINOR.PATCH[-pre][-test.RUN][+build]: build metadata doesn't
    # count, a pre-release sorts before its release (v1.0.0-rc2 < v1.0.0),
    # numbers in it compare as numbers (rc2 < rc10), and a builder test
    # build VERSION-test.RUN sorts just below VERSION. The same as
    # tools/release_version.py, which picks the versions the builder releases.
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", ver.strip())
    if m is None:
        return (-1, -1, -1, (0, ()), 0, "")
    core = tuple(int(x) for x in m.group(1, 2, 3))
    pre, run = m.group(4) or "", ""
    t = re.fullmatch(r"(.*?)(?:^|-)test\.(.+)", pre)
    if t:
        pre, run = t.groups()
    parts = tuple((0, int(x), "") if x.isdigit() else (1, 0, x)
                  for x in re.findall(r"\d+|[A-Za-z]+", pre))
    return core + ((0, parts) if pre else (1, ()), 0 if t else 1, run)


def pick_release(rels: Any, channel: str) -> Optional[Dict[str, Any]]:
    """The release a channel offers from a release list (GitHub's or
    Gitea's /releases): the newest Kiln OS tag by version_key, drafts left
    out; pre-releases (release candidates) only on "test". None when there
    is none. (The stable channel asks the server for releases/latest; this
    gives the same release from a list.)"""
    best: Optional[Dict[str, Any]] = None
    if not isinstance(rels, list):
        return None
    for rel in rels:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        tag = str(rel.get("tag_name", ""))
        if OS_TAG.fullmatch(tag) is None or "test." in tag:
            continue
        if channel != "test" and rel.get("prerelease"):
            continue
        if best is None or version_key(tag) > version_key(
                str(best["tag_name"])):
            best = rel
    return best


def describe_key(ver: str) -> tuple:
    # "v0.13.0-812-gabc1234-ad5x" (git describe) or "v0.0.1+3.gabc" (OS)
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-(\d+))?", ver.strip())
    if m is None:
        return (-1, -1, -1, -1)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4) or 0))


def short_describe(ver: str) -> str:
    # For Fluidd's semver compare: "v0.13.0-812" (N as a numeric
    # pre-release field compares right among versions of one tag)
    k = describe_key(ver)
    return f"v{k[0]}.{k[1]}.{k[2]}-{k[3]}" if k[0] >= 0 else ver


def app_root(name: str) -> pathlib.Path:
    # Same rules as lib/apps.sh: a package is used while it is newer than
    # the image's copy and the OS is at least its os_min
    sub = APP_SUB[name]
    img = pathlib.Path("/usr/lib") / name
    d = APPS_DIR / name
    try:
        meta = dict(line.split("=", 1) for line in
                    (d / "kiln-app").read_text().splitlines() if "=" in line)
        pkg_ver = (d / sub / ".version").read_text().strip()
        img_ver = (img / sub / ".version").read_text().strip()
    except (OSError, ValueError):
        return img
    os_ver = read_kiln_version()["VERSION"]
    if (version_key(os_ver) >= version_key(meta.get("os_min", "v999.0.0"))
            and describe_key(pkg_ver) > describe_key(img_ver)):
        return d
    return img


def read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):   # ValueError: not UTF-8
        return "?"


def read_record(path: pathlib.Path) -> str:
    """A kernel record file, "" when missing or unreadable"""
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""
    except PermissionError as e:
        logging.info(f"kiln_os: can't read {path}: {e}")
        return ""
    except (OSError, ValueError) as e:
        logging.info(f"kiln_os: {path} unreadable: {e}")
        return ""


def kernel_status() -> Dict[str, Any]:
    """The running kernel, ours in this image and S00ad5x-kernel's record
    (failed: the release on line 1, why and when on line 2)."""
    ours = read_text(OUR_KERNEL)
    failed = read_record(KERNEL_DIR / "failed").splitlines()
    try:
        unfinished = int(read_record(KERNEL_DIR / "unfinished").strip())
    except ValueError:
        unfinished = 0
    running = os.uname().release
    failed_rel = failed[0].strip() if failed else ""
    mainline = read_text(MAINLINE_KERNEL)
    mainline = "" if mainline == "?" else mainline
    mfailed = read_record(KERNEL_DIR / "failed-mainline").splitlines()
    mfailed_rel = mfailed[0].strip() if mfailed else ""
    return {
        "running": running,
        "stock": running.startswith("5.10."),
        "ours": "" if ours == "?" else ours,
        "failed": failed_rel,
        "failed_why": failed[1].strip() if len(failed) > 1 else "",
        "ours_failed": ours != "?" and failed_rel == ours,
        "unfinished": unfinished,
        "mainline": mainline,
        "mainline_on": (KERNEL_DIR / "mainline").exists(),
        "mainline_failed": bool(mainline) and mfailed_rel == mainline,
        "mainline_failed_why": mfailed[1].strip() if len(mfailed) > 1 else "",
    }


def link_plugins(config_dir: str) -> str:
    """The "plugins" link in the config folder to PLUGINS_DIR: made when
    nothing has that name; anything else there (the user's own folder or
    link) is left alone. Returns what was found or done."""
    if not config_dir:
        return "no config folder"
    link = pathlib.Path(config_dir) / PLUGINS_LINK
    if link.is_symlink():
        if os.readlink(link) == str(PLUGINS_DIR):
            return "linked"
        return f"{link} is a link to {os.readlink(link)}; left alone"
    if link.exists():
        return f"{link} exists and is not the link; left alone"
    if not PLUGINS_DIR.is_dir():
        return f"no {PLUGINS_DIR}"
    try:
        link.symlink_to(PLUGINS_DIR, target_is_directory=True)
    except OSError as e:
        return f"can't make {link}: {e}"
    return "link made"


def safe_kernel_status() -> Dict[str, Any]:
    """kernel_status(), or {"error": ...}: a broken record must never stop
    the component or the update status (the endpoints turn the error into
    a 500, reason kernel_records_unreadable)"""
    try:
        return kernel_status()
    except Exception as e:
        logging.exception("kiln_os: kernel status")
        return {"error": str(e)}


def kernel_notice(st: Dict[str, Any]) -> str:
    """The warning while our kernel (or the opt-in mainline one) is
    recorded as failed, else ''."""
    if not st.get("ours_failed"):
        if not (st.get("mainline_failed") and st.get("mainline_on")):
            return ""
        why = st["mainline_failed_why"]
        why = f" ({why})" if why else ""
        return (
            f"Running the 6.6 kernel: the mainline {st['mainline']} kernel "
            f"you turned on failed to start{why}. The printer works as "
            "usual on 6.6. To try it again: POST /machine/kiln_os/"
            "kernel_retry (the printer reboots), or 'ad5x-kernel retry' over "
            "SSH, then reboot. 'ad5x-kernel mainline off' stops trying it.")
    why = f" ({st['failed_why']})" if st["failed_why"] else ""
    return (
        "Running the stock kernel: Kiln's kernel failed to start"
        f"{why}. Sound and some drivers are unavailable. To try it again: "
        "POST /machine/kiln_os/kernel_retry (the printer reboots), or "
        "'ad5x-kernel retry' over SSH, then reboot.")


def read_memory_conf() -> Dict[str, str]:
    """/run/ad5x-memory.conf as a dict; {} when missing or unreadable"""
    conf: Dict[str, str] = {}
    for line in read_record(MEMORY_CONF).splitlines():
        key, sep, val = line.partition("=")
        if sep:
            conf[key.strip()] = val.strip().strip('"\'')
    return conf


def memory_status(seen: bool) -> Dict[str, Any]:
    """Extended memory mode: GET /machine/kiln_os/memory's object. SEEN:
    the notice was seen (database). Without HW_MEM_MIB in the record (an
    older S04ad5x-memory) the mode is not available. A failure record
    turns the switch off as far as the next start goes (the boot paths
    start standard until "ad5x-memory extended on" removes it), so enabled
    is false then and the failure is in "failed". MEM_MODE_FIXED=1 (an
    older Kiln U-Boot started this): only a boot loader update changes the
    mode, so bootloader_update_needed is true, and restart_needed and
    notice_pending are false (a restart wouldn't do it)."""
    conf = read_memory_conf()
    try:
        hw: Optional[int] = int(conf.get("HW_MEM_MIB", ""))
    except ValueError:
        hw = None
    if hw not in (256, 512):
        hw = None
    try:
        mem_kb: Optional[int] = int(conf.get("MEM_KB", ""))
    except ValueError:
        mem_kb = None
    active = conf.get("MEM_MODE", "")
    if active not in MEMORY_MODES:
        active = "standard"
    lines = read_record(KERNEL_DIR / MEMORY_FAILED).splitlines()
    failed = lines[0].strip() if lines else ""
    switch = KERNEL_DIR / MEMORY_SWITCH
    enabled = (switch.exists() or switch.is_symlink()) and not failed
    available = hw == 512
    update = available and conf.get("MEM_MODE_FIXED") == "1"
    return {
        "available": available,
        "enabled": enabled,
        "active": active,
        "restart_needed": (available and not update
                           and enabled != (active == "extended")),
        "failed": failed or None,
        "notice_pending": (available and not update
                           and active == "standard"
                           and not enabled and not seen),
        "bootloader_update_needed": update,
        "hw_mem_mib": hw,
        "mem_kb": mem_kb,
    }


def parse_enable(val: Any) -> bool:
    """enable= of POST /machine/kiln_os/memory and KILN_MEMORY_MODE"""
    v = str(val).strip().lower() if val is not None else ""
    if v in ("true", "1", "on", "yes"):
        return True
    if v in ("false", "0", "off", "no"):
        return False
    raise bad_parameter(
        "No enable given (true or false)" if not v
        else f"enable must be true or false, not '{val}'")


def memory_report(st: Dict[str, Any]) -> List[str]:
    """KILN_MEMORY_MODE's answer in the G-code console"""
    if not st["available"]:
        hw = st["hw_mem_mib"]
        has = f"this printer has {hw} MiB" if hw else \
            "this printer's memory size is unknown"
        return [f"Extended memory: not available ({has}; it needs 512 MiB)"]
    lines = [f"Extended memory: {'on' if st['enabled'] else 'off'} "
             f"(this start: {st['active']})"]
    if st["failed"]:
        lines.append(f"{MEMORY_FAILED_TEXT} ({st['failed']})")
    if st["bootloader_update_needed"]:
        lines.append("Needs a boot loader update to take effect: this boot "
                     "loader can't choose the memory mode")
    if st["restart_needed"]:
        lines.append("Takes effect at the next start (restart the printer)")
    return lines


def read_ifs_record() -> Dict[str, str]:
    """The agent's status of the last IFS firmware switch (key=value
    lines); {} when there is none or it can't be read"""
    rec: Dict[str, str] = {}
    for line in read_record(IFS_STATUS).splitlines():
        key, sep, val = line.partition("=")
        if sep and key in IFS_KEYS:
            rec[key] = val.strip()
    return rec


def ifs_firmware_status(ifs_version: Optional[str] = None
                        ) -> Dict[str, Any]:
    """GET /machine/kiln_os/ifs_firmware's object. IFS_VERSION: Klipper's
    printer.ifs.version ("3.0.7" on Flashforge's firmware, "Klipper ..."
    on Klipper's), None when Klipper didn't say. The running firmware:
    unknown during a switch; klipper when S61klipper found the IFS
    answering as Klipper at Klipper's last start; else from ifs.version;
    else what the last switch put on; else unknown."""
    rec = read_ifs_record()
    state = rec.get("state", "")
    if state not in IFS_STATES:
        state = "idle"
    target = rec.get("target", "")
    if target not in IFS_TARGETS:
        target = ""
    enabled = IFS_OPTIN.is_file() or IFS_KLIPPER_ENABLE.is_file()
    if state == "running":
        firmware = "unknown"
    elif IFS_ANSWERS_KLIPPER.exists():
        firmware = "klipper"
    elif ifs_version:
        firmware = ("klipper" if ifs_version.startswith("Klipper")
                    else "stock")
    elif state == "done" and target:
        firmware = target
    else:
        firmware = "unknown"
    image_version = read_record(IFS_IMAGE_VERSION).strip()
    return {
        "available": enabled and IFS_IMAGE.is_file(),
        "enabled": enabled,
        "firmware": firmware,
        "state": state,
        "target": target or None,
        "phase": rec.get("phase") or None if state == "running" else None,
        "reason": rec.get("reason") or None if state == "failed" else None,
        "message": rec.get("message") or None if state == "failed" else None,
        "version": rec.get("version") or None if state == "done" else None,
        "klipper_version": image_version or None,
    }


# One request at a time: the agent answers every request in one status file
AGENT_LOCK = asyncio.Lock()


async def ask_agent(server, request: pathlib.Path, content: str,
                    done: Tuple[str, ...], timeout: int = 120) -> str:
    """Write a request for S68ad5x-update-agent (root) and wait for its
    status: one starting with DONE, or an error for failed/refused."""
    async with AGENT_LOCK:
        return await _ask_agent(server, request, content, done, timeout)


async def _ask_agent(server, request: pathlib.Path, content: str,
                     done: Tuple[str, ...], timeout: int) -> str:
    tmp = request.with_name(request.name + ".tmp")
    try:
        AGENT_STATUS.unlink(missing_ok=True)
        tmp.write_text(content)
        tmp.rename(request)
    except OSError as e:
        # No folder for requests: S68ad5x-update-agent never started
        raise KilnError("agent_unavailable",
                        f"The update agent isn't available ({e})", 503)
    for _ in range(timeout):
        await asyncio.sleep(1.)
        status = read_text(AGENT_STATUS)
        if status.startswith(done):
            return status
        if status.startswith(("failed", "refused")):
            raise agent_error(status)
    # Not picked up later by surprise (an agent without this request)
    request.unlink(missing_ok=True)
    raise KilnError(
        "agent_timeout", f"The update agent didn't answer in {timeout} s "
        "(is S68ad5x-update-agent running?)", 503)


# Fluidd's service buttons and the update manager's restarts
# (/machine/services/restart|stop|start, managed_services): Moonraker's
# machine component with "[machine] provider: kiln_agent" (Moonraker patch
# 0006) uses service_provider() below. Moonraker runs as klipper and can't
# run init scripts: the root agent gets "service" ("ACTION NAME") and runs
# the init script it maps NAME to (S68ad5x-update-agent, service_request),
# refused while a print may run. For moonraker and nginx (both carry the
# reply back) it answers "done: restarting NAME" first and acts after.
# The services and the actions each allows (the agent checks the same)
SERVICES: Dict[str, Tuple[str, ...]] = {
    "klipper": ("start", "stop", "restart"),
    "moonraker": ("restart",),
    "nginx": ("restart",),
    "helixscreen": ("start", "stop", "restart"),
    "ad5x-camera": ("start", "stop", "restart"),
}
# Where each one's init script keeps its pid (the cameras: one per camera)
SERVICE_PIDS: Dict[str, str] = {
    "klipper": "/var/run/klipper.pid",
    "moonraker": "/var/run/moonraker.pid",
    "nginx": "/run/nginx/nginx.pid",
    "helixscreen": "/var/run/helixscreen.pid",
    "ad5x-camera": "/run/ad5x-camera/*.pid",
}
AGENT_SERVICE = WORK_DIR / "service"
PROC = pathlib.Path("/proc")


def pid_running(path: pathlib.Path) -> bool:
    try:
        pid = int(path.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return False
    return pid > 0 and (PROC / str(pid)).is_dir()


def service_state(name: str) -> Dict[str, str]:
    """Moonraker's service state from the init script's pid file(s)"""
    pat = pathlib.Path(SERVICE_PIDS[name])
    running = name == "moonraker" or any(
        pid_running(p) for p in pat.parent.glob(pat.name))
    if running:
        return {"active_state": "active", "sub_state": "running"}
    return {"active_state": "inactive", "sub_state": "dead"}


async def service_action(server, action: str, name: str) -> str:
    """Ask the root agent to start, stop or restart a service; its answer,
    or an error (refused while printing, unknown service or action)"""
    allowed = SERVICES.get(name)
    if allowed is None:
        raise bad_parameter(f"Service '{name}' not available")
    if action not in allowed:
        raise bad_parameter(
            f"Service action '{action}' not available for {name}")
    status = await ask_agent(server, AGENT_SERVICE, f"{action} {name}\n",
                             ("done",), timeout=90)
    logging.info(f"kiln_os: {action} {name}: {status}")
    return status


# Moonraker's /machine/reboot and /machine/shutdown on Kiln OS: the agent
# gets "reboot" or "shutdown" and answers "rebooting" / "shutting down"
# before it acts, or refuses (printing, print_state_unknown, starting_up,
# recovery_updating: S68ad5x-update-agent, power_request). 30 s: the
# agent's checks take at most ~10 s, its loop 3 s.
async def machine_power(server, what: str) -> str:
    """Ask the root agent to reboot or shut down the printer; its answer,
    or an error (a refusal is 409 with the agent's reason)"""
    if what == "reboot":
        request, done = AGENT_REBOOT, "rebooting"
    elif what == "shutdown":
        request, done = AGENT_SHUTDOWN, "shutting down"
    else:
        raise bad_parameter(f"Machine action '{what}' not available")
    status = await ask_agent(server, request, f"{what}\n", (done,),
                             timeout=30)
    logging.info(f"kiln_os: {what}: {status}")
    return status


def service_provider(base: type) -> type:
    """The kiln_agent provider class on Moonraker's BaseProvider (passed
    in by machine.py, which imports this module only for this provider)"""

    class KilnAgentProvider(base):  # type: ignore[valid-type,misc]
        async def initialize(self) -> None:
            self._refresh(notify=False)
            pstats = self.server.lookup_component("proc_stats")
            pstats.register_stat_callback(self._update_service_status)

        def _update_service_status(self, sequence: int) -> None:
            if sequence % 2 == 0:   # every other second, as systemd_cli
                self._refresh(notify=True)

        def _refresh(self, notify: bool) -> None:
            for name in SERVICES:
                new = service_state(name)
                if self.available_services.get(name) != new:
                    self.available_services[name] = new
                    if notify:
                        self.server.send_event(
                            "machine:service_state_changed", {name: new})

        async def do_service_action(self, action: str,
                                    service_name: str) -> None:
            await service_action(self.server, action, service_name)
            self._refresh(notify=True)

        # Upstream runs "sudo reboot" / "sudo poweroff" here; on Kiln OS
        # the agent checks first (machine_power)
        async def reboot(self) -> None:
            await machine_power(self.server, "reboot")

        async def shutdown(self) -> None:
            await machine_power(self.server, "shutdown")

        async def extract_service_info(
            self, service_name: str, pid: int,
            properties: Optional[List[str]] = None, raw: bool = False
        ) -> Dict[str, Any]:
            if service_name not in SERVICES:
                return {}
            return {"unit_name": service_name, "is_default": True,
                    "manager": "kiln_agent"}

    return KilnAgentProvider


class Source:
    """The update server (GitHub or Gitea API) and the hand-over to the
    root agent."""

    def __init__(self, server, server_url: str, repo: str,
                 token_file: pathlib.Path) -> None:
        self.server = server
        self.server_url = server_url.rstrip("/")
        self.repo = repo
        self.token_file = token_file
        self.http: HttpClient = server.lookup_component("http_client")
        self.releases_url = f"{self.server_url}/{self.repo}/releases"
        # The two APIs return the same release fields (tag_name, body,
        # prerelease, assets[].name/size/browser_download_url)
        if re.match(r"https?://(www\.)?github\.com$", self.server_url):
            self.api_base = f"https://api.github.com/repos/{self.repo}"
        else:
            self.api_base = f"{self.server_url}/api/v1/repos/{self.repo}"

    def headers(self) -> Dict[str, str]:
        # Re-read each time: the token can be added without a restart
        tok = read_text(self.token_file)
        if tok and tok != "?":
            return {"Authorization": f"token {tok}"}
        return {}

    async def api(self, path: str) -> Any:
        url = f"{self.api_base}/{path}"
        resp = await self.http.get(url, headers=self.headers(),
                                   enable_cache=False, request_timeout=20.)
        resp.raise_for_status()
        return resp.json()

    async def fetch_checked(self, url: str, sums_url: str, name: str,
                            size: int, notify: Callable[..., None]
                            ) -> Tuple[pathlib.Path, str]:
        """Download NAME into WORK_DIR and check it against SHA256SUMS."""
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        for old in WORK_DIR.iterdir():
            if old.name.endswith((".zip", ".tar.gz", ".part")):
                old.unlink()
        dest = WORK_DIR / name
        notify(f"Downloading {name} ({max(size, 0) // (1024 * 1024)} MiB)...")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, self._download, url, dest, size, loop, notify)
            resp = await self.http.get(sums_url, headers=self.headers(),
                                       enable_cache=False)
            resp.raise_for_status()
        except KilnError:
            raise
        except Exception as e:
            raise KilnError("download_failed", f"Download failed: {e}", 502)
        want = ""
        for line in resp.text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                want = parts[0]
        if not want:
            dest.unlink()
            raise KilnError("download_failed", f"{name} not in SHA256SUMS",
                            502)
        notify("Checking the download...")
        have = await loop.run_in_executor(None, sha256_file, dest)
        if have != want:
            dest.unlink()
            raise KilnError(
                "download_failed",
                f"Download damaged (sha256 {have}, expected {want})", 502)
        return dest, want

    def _download(self, url: str, dest: pathlib.Path, size: int,
                  loop: asyncio.AbstractEventLoop,
                  notify: Callable[..., None]) -> None:
        # In a thread: Moonraker's download_file can't send the token
        req = urllib.request.Request(url, headers=self.headers())
        part = dest.with_name(dest.name + ".part")
        last = 0.0
        done = 0
        with urllib.request.urlopen(req, timeout=60) as resp, \
                part.open("wb") as out:
            size = int(resp.headers.get("Content-Length") or size)
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                now = time.monotonic()
                if size > 0 and now - last > 5.:
                    last = now
                    loop.call_soon_threadsafe(
                        notify, f"Downloading: {done * 100 // size}%")
        if size > 0 and done != size:
            part.unlink()
            raise KilnError("download_failed",
                            f"Download incomplete ({done}/{size})", 502)
        part.rename(dest)

    async def hand_over(self, name: str, sha: str, done: Tuple[str, ...],
                        timeout: int = 180) -> str:
        """Ask S68ad5x-update-agent (root) to install WORK_DIR/NAME.
        180 s: what the agent does before it answers (Moonraker's print
        state, up to 10 s; ad5x-update copying and checking the ~80 MB
        zip, about a minute on the printer; a daily package's unpack is
        shorter) three times over. It never waits for a recovery OS write
        (it refuses at once, recovery_updating)."""
        return await ask_agent(self.server, AGENT_REQUEST,
                               f"{name}\n{sha}\n", done, timeout)


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# The update manager's key for Kiln OS. Fluidd looks entries up by their
# "name" (hasUpdate, the Update button), so key and name must be the same.
KILN_OS = "Kiln OS"


class KilnDeploy(BaseDeploy):
    """The "Kiln OS" entry: Kiln OS releases (tags vX.Y.Z)."""

    def __init__(self, config: ConfigHelper, src: Source,
                 channel: Callable[[], Any]) -> None:
        super().__init__(config, KILN_OS, KILN_OS)
        self.src = src
        # async: the update channel ("stable" or "test")
        self.get_channel = channel
        self.channel = DEFAULT_CHANNEL
        local = read_kiln_version()
        self.version = local["VERSION"]
        self.remote_version = "?"
        self.release_url = src.releases_url
        self.zip_url = ""
        self.zip_name = ""
        self.zip_size = -1
        self.sums_url = ""
        self.notes = ""
        self.warnings: List[str] = []

    async def initialize(self) -> Dict[str, Any]:
        storage = await super().initialize()
        for key in ("remote_version", "zip_url", "zip_name", "zip_size",
                    "sums_url", "notes", "channel"):
            if key in storage:
                setattr(self, key, storage[key])
        return storage

    def get_persistent_data(self) -> Dict[str, Any]:
        storage = super().get_persistent_data()
        storage.update({
            "remote_version": self.remote_version,
            "zip_url": self.zip_url,
            "zip_name": self.zip_name,
            "zip_size": self.zip_size,
            "sums_url": self.sums_url,
            "notes": self.notes,
            "channel": self.channel,
        })
        return storage

    def forget_release(self) -> None:
        """After a channel change: offer nothing until the next check"""
        self.remote_version = "?"
        self.zip_url = ""
        self.zip_name = ""
        self.zip_size = -1
        self.sums_url = ""
        self.notes = ""
        self._save_state()

    def _has_update(self) -> bool:
        return (self.zip_url != "" and
                version_key(self.remote_version) > version_key(self.version))

    async def refresh(self) -> None:
        self.warnings = []
        try:
            self.channel = await self.get_channel()
            if self.channel == "test":
                # Everything but drafts; the newest Kiln OS version wins
                # (v1.0.0-rc2 < v1.0.0: the final after its candidates)
                rel = pick_release(
                    await self.src.api("releases?limit=50&per_page=50"),
                    "test")
                if rel is None:
                    raise self.server.error("no Kiln OS release found")
            else:
                # "latest": no drafts and no pre-releases (release
                # candidates, the daily packages)
                rel = await self.src.api("releases/latest")
            assert isinstance(rel, dict)
            tag = str(rel.get("tag_name", ""))
            zip_name = f"kiln-os-{tag}-update.zip"
            assets = {a.get("name"): a for a in rel.get("assets", [])}
            if zip_name not in assets or "SHA256SUMS" not in assets:
                raise self.server.error(
                    f"release {tag} has no {zip_name} or SHA256SUMS")
            self.remote_version = tag
            self.zip_name = zip_name
            self.zip_url = assets[zip_name]["browser_download_url"]
            self.zip_size = int(assets[zip_name].get("size", -1))
            self.sums_url = assets["SHA256SUMS"]["browser_download_url"]
            self.notes = str(rel.get("body", ""))[:4000]
            self.release_url = str(rel.get("html_url", self.release_url))
        except Exception as e:
            msg = f"Update check failed: {e}"
            self.warnings.append(msg)
            self.log_exc(msg, traceback=False)
        self._save_state()
        self.log_info(f"local {self.version}, newest {self.remote_version} "
                      f"({self.channel} channel)")

    async def update(self) -> bool:
        if not self._has_update():
            self.notify("Kiln OS is up to date")
            return False
        _, sha = await self.src.fetch_checked(
            self.zip_url, self.sums_url, self.zip_name, self.zip_size,
            self.notify)
        # The agent stages it for the recovery OS (ad5x-update), reboots
        self.notify("Staging the update for the recovery OS...")
        await self.src.hand_over(self.zip_name, sha, ("rebooting",))
        self.notify(
            f"Kiln OS {self.remote_version} staged. The printer reboots "
            "now, installs it in the recovery OS and starts again (3-6 "
            "minutes).", is_complete=True)
        return True

    def notify(self, msg: str, is_complete: bool = False) -> None:
        self.cmd_helper.notify_update_response(msg, is_complete)

    def get_update_status(self) -> Dict[str, Any]:
        return {
            "name": KILN_OS,
            "configured_type": "kiln_os",
            "version": self.version,
            "remote_version": self.remote_version,
            "full_version_string": self.version,
            "remote_url": self.release_url.split("/releases")[0],
            "release_notes": self.notes,
            "channel": self.channel,
            "is_valid": True,
            "debug_enabled": False,
            "info_tags": [],
            "warnings": self.warnings,
            "anomalies": [],
            "kernel": safe_kernel_status(),
        }


class AppUpdates:
    """Daily Klipper/Moonraker packages on the update manager's own
    "klipper"/"moonraker" entries.

    Those entries must stay plain BaseDeploy objects (for Klipper, the
    update manager replaces anything else when Klippy connects), so this
    sets the methods on the instance instead of subclassing."""

    def __init__(self, upd: BaseDeploy, name: str, src: Source) -> None:
        self.upd = upd
        self.name = name
        self.src = src
        self.remote = ""          # newest usable package version
        self.url = ""
        self.sums_url = ""
        self.size = -1
        self.notes = ""
        self.warnings: List[str] = []
        self._base_init = upd.initialize
        self._base_data = upd.get_persistent_data
        upd.initialize = self.initialize            # type: ignore
        upd.get_persistent_data = self.get_persistent_data  # type: ignore
        upd.refresh = self.refresh                  # type: ignore
        upd.update = self.update                    # type: ignore
        upd.get_update_status = self.get_update_status  # type: ignore

    def running(self) -> Tuple[str, bool]:
        root = app_root(self.name)
        ver = read_text(root / APP_SUB[self.name] / ".version")
        return ver, root != pathlib.Path("/usr/lib") / self.name

    async def initialize(self) -> Dict[str, Any]:
        storage = await self._base_init()
        for key in ("remote", "url", "sums_url", "size", "notes"):
            if key in storage:
                setattr(self, key, storage[key])
        return storage

    def get_persistent_data(self) -> Dict[str, Any]:
        storage = self._base_data()
        storage.update({"remote": self.remote, "url": self.url,
                        "sums_url": self.sums_url, "size": self.size,
                        "notes": self.notes})
        return storage

    async def refresh(self) -> None:
        self.warnings = []
        os_key = version_key(read_kiln_version()["VERSION"])
        prefix = f"{self.name}-"
        best: Optional[Dict[str, Any]] = None
        try:
            rels = await self.src.api("releases?limit=50&per_page=50")
            for rel in rels:
                tag = str(rel.get("tag_name", ""))
                if rel.get("draft") or not tag.startswith(prefix + "v"):
                    continue
                m = re.search(r"^os_min:\s*(\S+)", str(rel.get("body", "")),
                              re.M)
                if m is None or version_key(m.group(1)) > os_key:
                    continue    # needs a newer Kiln OS than this one
                ver = tag[len(prefix):]
                if best is None or describe_key(ver) > describe_key(best["v"]):
                    best = {"v": ver, "rel": rel}
            if best is None:
                self.remote = ""
                self.url = ""
            else:
                rel = best["rel"]
                fname = f"{self.name}-{best['v']}.tar.gz"
                assets = {a.get("name"): a for a in rel.get("assets", [])}
                if fname not in assets or "SHA256SUMS" not in assets:
                    raise self.src.server.error(
                        f"{rel.get('tag_name')} has no {fname} or SHA256SUMS")
                self.remote = best["v"]
                self.url = assets[fname]["browser_download_url"]
                self.size = int(assets[fname].get("size", -1))
                self.sums_url = assets["SHA256SUMS"]["browser_download_url"]
                self.notes = str(rel.get("body", ""))[:4000]
        except Exception as e:
            msg = f"Update check failed: {e}"
            self.warnings.append(msg)
            self.upd.log_exc(msg, traceback=False)
        self.upd._save_state()

    def _has_update(self) -> bool:
        return (self.url != "" and
                describe_key(self.remote) > describe_key(self.running()[0]))

    async def update(self) -> bool:
        notify = self.upd.cmd_helper.notify_update_response
        if not self._has_update():
            notify(f"{self.name} is up to date")
            return False
        fname = f"{self.name}-{self.remote}.tar.gz"
        _, sha = await self.src.fetch_checked(
            self.url, self.sums_url, fname, self.size, notify)
        notify(f"Installing {self.name} {self.remote} and restarting it...")
        status = await self.src.hand_over(fname, sha, ("restart",))
        if self.name == "klipper":
            notify(f"Klipper {self.remote} installed and restarted",
                   is_complete=True)
        else:
            # The agent restarts Moonraker now: this connection ends
            notify(f"Moonraker {self.remote} installed; Moonraker "
                   "restarts now", is_complete=True)
        logging.info(f"kiln_os: {self.name} {self.remote}: {status}")
        return True

    def get_update_status(self) -> Dict[str, Any]:
        ver, from_pkg = self.running()
        remote = self.remote if self._has_update() else ver
        where = "daily package" if from_pkg else "part of Kiln OS"
        return {
            "name": self.name,
            "configured_type": "kiln_app",
            "version": short_describe(ver),
            "remote_version": short_describe(remote),
            "full_version_string": f"{ver} ({where})",
            "remote_url": self.src.releases_url.split("/releases")[0],
            "release_notes": self.notes,
            "channel": "dev",
            "is_valid": True,
            "debug_enabled": False,
            "info_tags": [],
            "warnings": self.warnings,
            "anomalies": [],
        }


class KilnOS:
    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.updates = False
        self.server.register_endpoint(
            "/machine/kiln_os/info", RequestType.GET, self._handle_info)
        self.server.register_endpoint(
            "/machine/kiln_os/kernel", RequestType.GET, self._handle_kernel)
        self.server.register_endpoint(
            "/machine/kiln_os/kernel_retry", RequestType.POST,
            self._handle_kernel_retry)
        self.server.register_endpoint(
            "/machine/kiln_os/boot_recovery", RequestType.POST,
            self._handle_boot_recovery)
        self.server.register_endpoint(
            "/machine/kiln_os/return_stock", RequestType.POST,
            self._handle_return_stock)
        self.server.register_endpoint(
            "/machine/kiln_os/channel", RequestType.POST,
            self._handle_channel)
        # GET and POST: JSON-RPC machine.kiln_os.get_memory and
        # machine.kiln_os.post_memory (Moonraker's names for an endpoint
        # with two request types)
        self.server.register_endpoint(
            "/machine/kiln_os/memory", RequestType.GET | RequestType.POST,
            self._handle_memory)
        self.server.register_endpoint(
            "/machine/kiln_os/memory_notice_seen", RequestType.POST,
            self._handle_memory_notice_seen)
        # JSON-RPC machine.kiln_os.get_ifs_firmware and post_ifs_firmware
        self.server.register_endpoint(
            "/machine/kiln_os/ifs_firmware",
            RequestType.GET | RequestType.POST, self._handle_ifs_firmware)
        # KILN_MEMORY_MODE (macros/system.cfg)
        self.server.register_remote_method(REMOTE_MEMORY,
                                           self._remote_memory_mode)
        # Fluidd's and Mainsail's dismiss of the notice's announcement
        self.server.register_event_handler(
            "announcements:dismissed", self._on_announcement_dismissed)
        self.notice_lock = asyncio.Lock()
        self.deploy: Optional[KilnDeploy] = None
        self.db = self.server.lookup_component("database", None)
        if self.db is not None:
            try:
                # Protected: clients can read it, only the endpoint writes
                self.db.register_local_namespace(DB_NAMESPACE)
            except Exception:
                logging.exception("kiln_os: database namespace")
        fm = self.server.lookup_component("file_manager", None)
        cfg_dir = fm.get_directory("config") if fm is not None else ""
        logging.info(f"kiln_os: plugin folder: {link_plugins(cfg_dir)}")
        # Browsable through the link, but left out of server.files.list
        # (Moonraker patch 0008): that list runs on the event loop at
        # ~14 ms per file on the AD5X, and Mainsail and Fluidd ask for the
        # config root at each page load (PR #70: ~2200 plugin files blocked
        # Moonraker for a minute). Registered whether or not the link is
        # ours: it only matters where the plugin folder is reached
        if fm is not None and hasattr(fm, "add_unlisted_path"):
            try:
                fm.add_unlisted_path(PLUGINS_DIR)
            except Exception:
                logging.exception("kiln_os: plugin folder unlisted")
        st = safe_kernel_status()
        notice = kernel_notice(st)
        if notice:
            self.server.add_warning(notice, KERNEL_WARNING)
        logging.info(f"kiln_os: kernel {st.get('running', '?')}, ours "
                     f"{st.get('ours') or 'none'}, "
                     f"failed {st.get('failed') or 'no'}")
        server_url = config.get("server")
        repo = config.get("repo")
        token_file = pathlib.Path(
            config.get("token_file", "/data/ad5x/kiln-os.token"))
        um = self.server.load_component(config, "update_manager", None)
        if um is None:
            self.server.add_warning(
                "[kiln_os]: needs [update_manager]; Kiln OS updates off")
            return
        src = Source(self.server, server_url, repo, token_file)
        cfg = um.app_config.read_supplemental_dict({"kiln_os": {}})
        self.deploy = KilnDeploy(cfg, src, self.get_channel)
        um.updaters[KILN_OS] = self.deploy
        self.updates = True
        self.apps = []
        for name in ("klipper", "moonraker"):
            upd = um.updaters.get(name)
            if upd is not None and type(upd) is BaseDeploy:
                self.apps.append(AppUpdates(upd, name, src))
        logging.info(f"kiln_os: updates from {server_url}/{repo}")

    async def get_channel(self) -> str:
        """The update channel; "stable" when unset or unreadable"""
        if self.db is None:
            return DEFAULT_CHANNEL
        try:
            ch = await self.db.get_item(DB_NAMESPACE, DB_CHANNEL_KEY,
                                        DEFAULT_CHANNEL)
        except Exception:
            logging.exception("kiln_os: reading the update channel")
            return DEFAULT_CHANNEL
        return ch if ch in CHANNELS else DEFAULT_CHANNEL

    async def _handle_channel(self, web_request: WebRequest
                              ) -> Dict[str, Any]:
        ch = web_request.get_str("channel", None)
        if ch is None:
            raise bad_parameter("No channel given (stable or test)")
        ch = str(ch).strip().lower()
        if ch not in CHANNELS:
            raise bad_parameter(
                f"Unknown update channel '{ch}' (stable or test)")
        if self.db is None:
            raise KilnError("database_unavailable",
                            "Moonraker's database is not available", 503)
        old = await self.get_channel()
        await self.db.insert_item(DB_NAMESPACE, DB_CHANNEL_KEY, ch)
        if ch != old and self.deploy is not None:
            # What the old channel offered is not offered on this one
            self.deploy.channel = ch
            self.deploy.forget_release()
        logging.info(f"kiln_os: update channel {old} -> {ch}")
        return {"channel": ch, "previous": old}

    async def _handle_info(self, web_request: WebRequest) -> Dict[str, Any]:
        # The reply is the object itself (Moonraker adds one "result")
        features = list(FEATURES)
        if self.updates:
            features.append("updates")
        if self.server.lookup_component("kiln_lanes", None) is not None:
            features.append("lane_data")
        if read_memory_conf().get("HW_MEM_MIB") == "512":
            features.append("memory_mode")
        return {
            "os_version": read_kiln_version()["VERSION"],
            "api_version": read_api_version(),
            "kernel": os.uname().release,
            "features": features,
            "update_channel": await self.get_channel(),
        }

    def _kernel_status(self) -> Dict[str, Any]:
        """The kernel status, or a 500 when the records can't be read (the
        update status keeps {"error": ...} instead: safe_kernel_status)"""
        st = safe_kernel_status()
        if "error" in st:
            raise KilnError("kernel_records_unreadable",
                            f"Can't read the kernel records: {st['error']}",
                            500)
        return st

    async def _handle_kernel(self, web_request: WebRequest) -> Dict[str, Any]:
        return self._kernel_status()

    async def _handle_kernel_retry(self, web_request: WebRequest
                                   ) -> Dict[str, Any]:
        st = self._kernel_status()
        if not st["ours"]:
            raise KilnError("no_own_kernel",
                            "This image has no kernel of its own", 409)
        if not st["stock"] and not st["failed"] \
                and not st["mainline_failed"]:
            raise KilnError("nothing_to_retry",
                            "Kiln's kernel is running: nothing to retry", 409)
        # The agent refuses while printing, runs "ad5x-kernel retry" and
        # reboots
        await ask_agent(self.server, AGENT_KERNEL_RETRY, "retry\n",
                        ("rebooting",), timeout=30)
        self.server.remove_warning(KERNEL_WARNING)
        return dict(REBOOTING)

    async def _handle_boot_recovery(self, web_request: WebRequest
                                    ) -> Dict[str, Any]:
        # The agent refuses while printing or starting up, or without the
        # recovery OS in slot A; otherwise points the boot flag at it and
        # reboots
        await ask_agent(self.server, AGENT_BOOT_RECOVERY, "boot-recovery\n",
                        ("rebooting",), timeout=30)
        return dict(REBOOTING)

    async def _handle_return_stock(self, web_request: WebRequest
                                   ) -> Dict[str, Any]:
        # As boot_recovery, and the recovery OS opens Return to Flashforge
        # firmware (it writes nothing before a tap there)
        await ask_agent(self.server, AGENT_RETURN_STOCK, "return-stock\n",
                        ("rebooting",), timeout=30)
        return dict(REBOOTING)

    # Extended memory mode (docs/memory.md)

    async def component_init(self) -> None:
        # After the announcements component's own init (a core component,
        # set up before the others): its entries are loaded by then
        await self._sync_memory_notice()

    async def notice_seen(self) -> bool:
        if self.db is None:
            return False
        try:
            return bool(await self.db.get_item(DB_NAMESPACE, DB_NOTICE_KEY,
                                               False))
        except Exception:
            logging.exception("kiln_os: reading memory_notice_seen")
            return False

    async def memory_status(self) -> Dict[str, Any]:
        return memory_status(await self.notice_seen())

    async def _store_notice_seen(self) -> None:
        if self.db is None:
            raise KilnError("database_unavailable",
                            "Moonraker's database is not available", 503)
        await self.db.insert_item(DB_NAMESPACE, DB_NOTICE_KEY, True)

    async def set_memory_mode(self, enable: bool) -> Dict[str, Any]:
        """The switch through the agent ("ad5x-memory extended on|off");
        allowed while printing (only a file changes, the next start uses
        it). The owner has found the setting: the notice counts as seen."""
        st = await self.memory_status()
        if not st["available"]:
            hw = st["hw_mem_mib"]
            raise KilnError(
                "not_available", "Extended memory needs 512 MiB of memory; "
                + (f"this printer has {hw} MiB" if hw
                   else "this printer's memory size is unknown"), 409)
        mode = "on" if enable else "off"
        status = await ask_agent(self.server, AGENT_MEMORY, f"{mode}\n",
                                 ("done",), timeout=30)
        logging.info(f"kiln_os: extended memory {mode}: {status}")
        if self.db is not None:
            try:
                await self._store_notice_seen()
            except Exception:
                logging.exception("kiln_os: storing memory_notice_seen")
        await self._sync_memory_notice()
        return await self.memory_status()

    async def _handle_memory(self, web_request: WebRequest
                             ) -> Dict[str, Any]:
        if web_request.get_request_type() == RequestType.POST:
            return await self.set_memory_mode(
                parse_enable(web_request.get_str("enable", None)))
        return await self.memory_status()

    async def _handle_memory_notice_seen(self, web_request: WebRequest
                                         ) -> Dict[str, Any]:
        await self._store_notice_seen()
        await self._sync_memory_notice()
        return await self.memory_status()

    async def _remote_memory_mode(self, enable: Any = None) -> None:
        """KILN_MEMORY_MODE [ENABLE=0|1]: the mode, or switch it; the
        answer in the G-code console (Klipper doesn't wait for it)"""
        try:
            if enable is None:
                st = await self.memory_status()
            else:
                st = await self.set_memory_mode(parse_enable(enable))
            lines = [f"// {line}" for line in memory_report(st)]
        except Exception as e:
            if not isinstance(e, KilnError):
                logging.exception("kiln_os: KILN_MEMORY_MODE")
            lines = [f"!! KILN_MEMORY_MODE: {e}"]
        for line in lines:
            self.server.send_event("server:gcode_response", line)

    # The IFS firmware switch (docs/mcu-flashing.md)

    async def _ifs_version(self) -> Optional[str]:
        """Klipper's printer.ifs.version; None when Klipper doesn't answer
        or has no ifs object (a plugin drives the IFS)"""
        kapis = self.server.lookup_component("klippy_apis", None)
        if kapis is None:
            return None
        try:
            res = await kapis.query_objects({"ifs": ["version"]}, None)
        except Exception:
            return None
        if not isinstance(res, dict) or not isinstance(res.get("ifs"), dict):
            return None
        ver = res["ifs"].get("version")
        return ver if isinstance(ver, str) and ver else None

    async def ifs_firmware_status(self) -> Dict[str, Any]:
        return ifs_firmware_status(await self._ifs_version())

    async def switch_ifs_firmware(self, target: str) -> Dict[str, Any]:
        """Ask the agent to switch the IFS to TARGET. It checks again
        (print state, idle_timeout, opt-in, a running switch), answers at
        once and switches in the background; the reply is the GET object
        with state running."""
        if target not in IFS_TARGETS:
            raise bad_parameter(
                "No target given (stock or klipper)" if not target
                else f"target must be stock or klipper, not '{target}'")
        st = ifs_firmware_status()
        if st["state"] == "running":
            raise KilnError("ifs_switching",
                            "The IFS firmware is being switched, try again "
                            "in a few minutes", 409)
        if target == "klipper" and not st["enabled"]:
            raise KilnError(
                "not_enabled", "The IFS firmware switch is off (the owner "
                f"turns it on over SSH: touch {IFS_OPTIN})", 409)
        if target == "klipper" and not IFS_IMAGE.is_file():
            raise KilnError("not_available", "This image has no Klipper "
                            "firmware for the IFS", 409)
        status = await ask_agent(self.server, AGENT_IFS, f"{target}\n",
                                 ("done",), timeout=30)
        logging.info(f"kiln_os: IFS firmware {target}: {status}")
        return await self.ifs_firmware_status()

    async def _handle_ifs_firmware(self, web_request: WebRequest
                                   ) -> Dict[str, Any]:
        if web_request.get_request_type() == RequestType.POST:
            target = web_request.get_str("target", None)
            return await self.switch_ifs_firmware(
                str(target).strip().lower() if target is not None else "")
        return await self.ifs_firmware_status()

    # The notice as a Moonraker announcement (feed kiln_os): there while
    # notice_pending, removed otherwise. Its id changes with each add
    # ("kiln_os/DATE"), so it is found by feed and title. A dismiss in
    # Fluidd or Mainsail marks the notice seen; a snooze (a dismiss with a
    # wake time) doesn't. Kiln's own "seen" dismisses it first, so clients
    # get Moonraker's announcement_dismissed.

    async def _notices(self, ann: Any) -> List[Dict[str, Any]]:
        try:
            entries = await ann.get_announcements(include_dismissed=True)
        except Exception:
            logging.exception("kiln_os: listing announcements")
            return []
        return [e for e in entries if isinstance(e, dict)
                and e.get("feed") == NOTICE_FEED
                and e.get("title") == NOTICE_TITLE]

    async def _sync_memory_notice(self) -> None:
        ann = self.server.lookup_component("announcements", None)
        if ann is None:
            return
        async with self.notice_lock:
            try:
                await self._sync_notice(ann)
            except Exception:
                logging.exception("kiln_os: memory notice announcement")

    async def _sync_notice(self, ann: Any) -> None:
        ours = await self._notices(ann)
        seen = await self.notice_seen()
        if not seen and self.db is not None and any(
                e.get("dismissed") and not e.get("dismiss_wake")
                for e in ours):
            # Dismissed while this component wasn't listening
            await self._store_notice_seen()
            seen = True
        st = memory_status(seen)
        if st["notice_pending"]:
            for e in ours[1:]:
                await self._drop_notice(ann, e, False)
            if not ours:
                entry = ann.add_internal_announcement(
                    NOTICE_TITLE, NOTICE_TEXT, NOTICE_URL, "normal",
                    NOTICE_FEED)
                logging.info("kiln_os: memory notice announced "
                             f"({entry.get('entry_id')})")
            return
        for e in ours:
            await self._drop_notice(ann, e, seen)

    async def _drop_notice(self, ann: Any, entry: Dict[str, Any],
                           dismiss: bool) -> None:
        eid = entry["entry_id"]
        try:
            if dismiss and not entry.get("dismissed"):
                await ann.dismiss_announcement(eid)
            await ann.remove_announcement(eid)
        except Exception as e:
            logging.info(f"kiln_os: announcement {eid}: {e}")

    async def _on_announcement_dismissed(self, data: Any) -> None:
        eid = str(data.get("entry_id", "")) if isinstance(data, dict) else ""
        ann = self.server.lookup_component("announcements", None)
        if ann is None or not eid.startswith(NOTICE_FEED + "/"):
            return
        entry = next((e for e in await self._notices(ann)
                      if e.get("entry_id") == eid), None)
        if entry is None or entry.get("dismiss_wake") or self.db is None:
            # Gone (Kiln removed it), snoozed, or nowhere to keep it
            return
        try:
            await self._store_notice_seen()
        except Exception:
            logging.exception("kiln_os: storing memory_notice_seen")
            return
        logging.info("kiln_os: memory notice dismissed in a web client")
        await self._sync_memory_notice()


def load_component(config: ConfigHelper) -> KilnOS:
    return KilnOS(config)
