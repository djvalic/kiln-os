# Kiln OS updates in Moonraker's update manager (docs/updates.md)
#
# Adds a "Kiln OS" entry to update_manager, so Fluidd (and anything else
# using /machine/update/*) shows "Kiln OS vX -> vY" next to Fluidd and
# installs it with its Update button:
#   refresh: the newest release on the update server (GitHub or Gitea API,
#            /repos/OWNER/REPO/releases/latest: no drafts, no pre-releases)
#            against /etc/kiln-version
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
APPS_DIR = pathlib.Path("/data/ad5x/apps")
APP_SUB = {"klipper": "klippy", "moonraker": "moonraker"}
KERNEL_DIR = pathlib.Path("/data/ad5x/kernel")
OUR_KERNEL = pathlib.Path("/usr/lib/ad5x/kernel66/release")
MAINLINE_KERNEL = pathlib.Path("/usr/lib/ad5x/kernel-mainline/release")
KERNEL_WARNING = "kiln_os_kernel"


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


def version_key(ver: str) -> tuple:
    # vMAJOR.MINOR.PATCH[-pre][+build]: build metadata doesn't count, a
    # pre-release sorts before its release (as semver, which Fluidd uses)
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", ver.strip())
    if m is None:
        return (-1, -1, -1, 0, "")
    pre = m.group(4)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)),
            0 if pre else 1, pre or "")


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
    if (describe_key(os_ver) >= describe_key(meta.get("os_min", "v999.0.0"))
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


def safe_kernel_status() -> Dict[str, Any]:
    """kernel_status(), or {"error": ...}: a broken record must never stop
    the component or the update status"""
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
    AGENT_STATUS.unlink(missing_ok=True)
    tmp = request.with_name(request.name + ".tmp")
    tmp.write_text(content)
    tmp.rename(request)
    for _ in range(timeout):
        await asyncio.sleep(1.)
        status = read_text(AGENT_STATUS)
        if status.startswith(done):
            return status
        if status.startswith(("failed", "refused")):
            raise server.error(f"Update agent: {status}")
    # Not picked up later by surprise (an agent without this request)
    request.unlink(missing_ok=True)
    raise server.error(
        "Update agent didn't answer (is S68ad5x-update-agent running?)")


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
        await loop.run_in_executor(
            None, self._download, url, dest, size, loop, notify)
        resp = await self.http.get(sums_url, headers=self.headers(),
                                   enable_cache=False)
        resp.raise_for_status()
        want = ""
        for line in resp.text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                want = parts[0]
        if not want:
            dest.unlink()
            raise self.server.error(f"{name} not in SHA256SUMS")
        notify("Checking the download...")
        have = await loop.run_in_executor(None, sha256_file, dest)
        if have != want:
            dest.unlink()
            raise self.server.error(
                f"Download damaged (sha256 {have}, expected {want})")
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
            raise self.server.error(f"Download incomplete ({done}/{size})")
        part.rename(dest)

    async def hand_over(self, name: str, sha: str, done: Tuple[str, ...],
                        timeout: int = 120) -> str:
        """Ask S68ad5x-update-agent (root) to install WORK_DIR/NAME."""
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

    def __init__(self, config: ConfigHelper, src: Source) -> None:
        super().__init__(config, KILN_OS, KILN_OS)
        self.src = src
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
                    "sums_url", "notes"):
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
        })
        return storage

    def _has_update(self) -> bool:
        return (self.zip_url != "" and
                version_key(self.remote_version) > version_key(self.version))

    async def refresh(self) -> None:
        self.warnings = []
        try:
            # "latest": no drafts and no pre-releases (the daily packages)
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
        self.log_info(f"local {self.version}, newest {self.remote_version}")

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
            "now, installs it in the recovery OS and starts again (about "
            "3 minutes).", is_complete=True)
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
            "channel": "stable",
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
        os_key = describe_key(read_kiln_version()["VERSION"])
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
                if m is None or describe_key(m.group(1)) > os_key:
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
        self.server.register_endpoint(
            "/machine/kiln_os/kernel", RequestType.GET, self._handle_kernel)
        self.server.register_endpoint(
            "/machine/kiln_os/kernel_retry", RequestType.POST,
            self._handle_kernel_retry)
        self.server.register_endpoint(
            "/machine/kiln_os/boot_recovery", RequestType.POST,
            self._handle_boot_recovery)
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
        um.updaters[KILN_OS] = KilnDeploy(cfg, src)
        self.apps = []
        for name in ("klipper", "moonraker"):
            upd = um.updaters.get(name)
            if upd is not None and type(upd) is BaseDeploy:
                self.apps.append(AppUpdates(upd, name, src))
        logging.info(f"kiln_os: updates from {server_url}/{repo}")

    async def _handle_kernel(self, web_request: WebRequest) -> Dict[str, Any]:
        return kernel_status()

    async def _handle_kernel_retry(self, web_request: WebRequest
                                   ) -> Dict[str, Any]:
        st = kernel_status()
        if not st["ours"]:
            raise self.server.error("This image has no kernel of its own")
        if not st["stock"] and not st["failed"] \
                and not st["mainline_failed"]:
            raise self.server.error(
                "Kiln's kernel is running: nothing to retry")
        # The agent refuses while printing, runs "ad5x-kernel retry" and
        # reboots
        status = await ask_agent(self.server, AGENT_KERNEL_RETRY, "retry\n",
                                 ("rebooting",), timeout=30)
        self.server.remove_warning(KERNEL_WARNING)
        return {"result": status}

    async def _handle_boot_recovery(self, web_request: WebRequest
                                    ) -> Dict[str, Any]:
        # The agent refuses while printing or starting up, or without the
        # recovery OS in slot A; otherwise points the boot flag at it and
        # reboots
        status = await ask_agent(self.server, AGENT_BOOT_RECOVERY,
                                 "boot-recovery\n", ("rebooting",),
                                 timeout=30)
        return {"result": status}


def load_component(config: ConfigHelper) -> KilnOS:
    return KilnOS(config)
