# Updates: releases and the printer

How Kiln OS updates are made and installed.

```
 Release builder                        GitHub                     Printer
 ─────────────────────────────          ─────                      ───────
 newer Klipper/Moonraker/Fluidd/   ──►  release vX.Y.Z        ◄──  Moonraker kiln_os: newest
 HelixScreen? build + test               kiln-os-…-update.zip       release vs /etc/kiln-version
 → commit bumps, tools/release.sh        SHA256SUMS            ──►  Fluidd: "Kiln OS a -> b",
                                                                   Update: download, check,
                                                                   agent stages + reboots,
                                                                   recovery installs slot B
```

Two kinds of update:

| | Kiln OS | Klipper / Moonraker packages |
|---|---|---|
| How often | weekly (Sunday) | daily, when upstream has new commits |
| What | the whole system image | just that program (a few MB) |
| GitHub | release `vX.Y.Z` | pre-release `klipper-vA.B.C-N-gHASH-ad5x` (newest 5 kept) |
| Install | reboot into the recovery OS (~3 min) | unpack into `/data/ad5x/apps/NAME`, restart it (seconds) |
| Fluidd entry | Kiln OS | klipper, moonraker |

## How releases are made

Kiln OS releases are built and tested automatically before they are
offered: every week the newest Klipper, Moonraker, Fluidd and HelixScreen
are built into both images, tested (our Klipper modules, Klipper against
the boards' flashed firmware, Moonraker start-up, the recovery OS's update
and the installer), and released only if every test passes. Daily Klipper
and Moonraker packages go through the same tests inside the newest
release. Versions: `vMAJOR.MINOR.PATCH`.

Release notes: a "What's new" section from `CHANGELOG.md` (the release's
`## vX.Y.Z` section, else `## Unreleased`, which is renamed after the
release; `tools/changelog_section.sh`). Gitea's notes also list the
commits. After editing the changelog, `tools/publish_github.sh notes TAG`
rewrites a GitHub release's notes.

Each GitHub release also publishes the source code behind it
(`tools/publish_sources.sh`): Buildroot's `legal-info` of
both images, with the licence texts and package list attached to the
release as `kiln-os-<version>-licenses.tar.gz`, and the source archives in
the `sources` release (a pre-release, so it is never "latest", which the
printers' update check reads). Each archive is named by package version and
uploaded once, so a release adds only what changed (usually Klipper and
Moonraker). Extra archives cover what `legal-info` can't see: the Ingenic
SDK's 6.6 kernel tree, kernel.org 5.10.186 (chainload.ko), the Klipper
commit of the board firmware, Fluidd's source and Buildroot itself.

### Board firmware

Klipper's host and the boards' firmware must agree on the commands. Each
image carries the board firmware it was tested with
(`klipper/mcu-firmware/<FLASHED>/`) and writes it to the boards at its
first start when they run anything else (`ad5x-mcu`,
`docs/mcu-flashing.md`, "Automatic updates"). A newer host that needs
commands this firmware doesn't have fails `test_image.sh` and isn't
released. To move on: build new firmware (`tools/build_mcu.sh`), add it to
`klipper/mcu-firmware/`, its dictionaries to `klipper/mcu-dicts/`, and
update `FLASHED`; the next release then updates every printer's boards.

## Test builds (not releases)

A quick or `--no-release` build is for testing only. It is versioned `vX.Y.Z-test.<run>` and
sorts below the release, so a printer on it is still offered the release later. Its update zip
is kept in the run's log folder (`update-<version>.zip`). It is never published, and
`tools/release.sh` refuses it (a test version has a second hyphen). Install one by hand with
`ad5x-update` from slot B (`docs/recovery-os.md`), passing the zip's sha256. See `docs/builder.md`.
`ad5x-update` refuses to stage anything until start-up has finished (the boot flag reads
`ota:kernel2` again); its message shows a loop that waits for that.

## The printer

- `/etc/kiln-version` (`post-build.sh`): `VERSION`, `COMMIT`, `DATE`. A
  release build has the release's version; a local build `vX.Y.Z+N.gHASH`
  (N commits after vX.Y.Z), which counts as vX.Y.Z.
- Moonraker's `kiln_os` component (`moonraker/components/kiln_os.py`,
  configured in `/usr/share/ad5x/moonraker-updates.conf`) adds "Kiln OS"
  to the update manager. It asks GitHub (`server`/`repo` in
  `moonraker-updates.conf`; a Gitea server works too) for the newest release (drafts and
  pre-releases don't count) when the update manager refreshes (daily, or
  Fluidd's refresh button).
- The update manager's own "klipper" and "moonraker" entries offer the
  newest package that is newer than what runs and whose `os_min` this OS
  meets. Update downloads and checks it, the agent unpacks it into
  `/data/ad5x/apps/NAME` and restarts Klipper or Moonraker (refused while
  printing). `S61klipper`/`S62moonraker` run the package while it is newer
  than the image's copy and the OS meets its `os_min`, otherwise the
  image's copy (`lib/apps.sh`; the same rules in `kiln_os.py`). So a Kiln
  OS update with a newer Klipper takes over by itself. Back to the
  image's copy: delete `/data/ad5x/apps/NAME` and restart it (or reboot).
- **Update** in Fluidd (refused while printing): Moonraker downloads
  `kiln-os-VERSION-update.zip` to `/data/ad5x/kiln-update`, checks it
  against the release's `SHA256SUMS` and asks `ad5x-update-agent`
  (`S68ad5x-update-agent`, root) to install it. The agent refuses while a
  print may run: Moonraker gives no answer at all ("no answer from
  Moonraker"), or Klipper is ready and its print state is printing, paused
  or unknown. A Klipper that is not ready (startup, shutdown, error,
  disconnected) can't be printing, so a printer with a broken Klipper can
  still be updated. It also refuses before start-up has finished ("refused:
  start-up has not finished yet, try again in a minute"; issue #47): until
  `S99ad5x-booted` has run, a reboot would count as an unfinished start of
  our kernel. It stages it with `ad5x-update` (boot flag on the recovery OS)
  and reboots. The recovery OS installs it into slot B, checks it and
  boots it (about 3 minutes). Log: `/data/ad5x/kiln-log/agent.log`.
  The update carries the release's recovery OS too: after the first
  complete start the main OS writes it into slot A if slot A holds
  another one (docs/recovery-os.md, "Updates of the recovery OS itself").
- Releases are public on GitHub (github.com/djvalic/kiln-os): no token
  needed. For a private repository, put a read token in
  `/data/ad5x/kiln-os.token`. A failed check shows an error in Fluidd and
  changes nothing.
- Fluidd itself also updates from Fluidd (its own entry, GitHub releases,
  `S61ad5x-web`).
- The kernel (issue #42): when `/data/ad5x/kernel/failed` names the release
  of our kernel in this image, the printer runs on the stock kernel
  (`S00ad5x-kernel`, `ad5x-kernel`). `kiln_os` then adds a Moonraker
  warning, which Fluidd shows: "Running the stock kernel: Kiln's kernel
  failed to start (why and when). Sound and some drivers are unavailable."
  Its endpoints:
  - `GET /machine/kiln_os/kernel`: `running` (`uname -r`), `stock` (5.10
    runs), `ours` (the release in this image, `""` if none), `failed`
    (line 1 of `failed`), `failed_why` (line 2: stage and last saved
    clock), `ours_failed` (`failed` names ours: the warning is up),
    `unfinished` (unfinished start-ups in a row). The "Kiln OS" entry of
    `/machine/update/status` has the same under `kernel`.
  - `POST /machine/kiln_os/kernel_retry`: writes `kernel-retry` in
    `/data/ad5x/kiln-update`; the agent runs `ad5x-kernel retry` and
    reboots, so our kernel is tried at the next boot. A recorded failure
    lasts until this (or `ad5x-kernel retry`): an update doesn't clear it,
    the release string is the same in every build. Answers
    `{"result": "rebooting"}`; an error while a print may run (the same
    rule as installs: "refused: a print is running", "no answer from
    Moonraker", "the print state is unknown"), before start-up has finished (the boot flag still
    points at the recovery OS), when our kernel runs and nothing is
    recorded as failed, or when the image has no kernel of its own. Example:
    `curl -X POST http://PRINTER/machine/kiln_os/kernel_retry` (through
    Fluidd's nginx) or port 7125.
- The recovery OS on request (issue #47):
  `POST /machine/kiln_os/boot_recovery` writes `boot-recovery` in
  `/data/ad5x/kiln-update`; the agent runs `ad5x-boot-recovery` (boot
  flag on the recovery OS in slot A) and reboots. Unlike an interrupted
  start this records nothing against our kernel. Answers
  `{"result": "rebooting"}`; an error while a print may run (the same rule
  as installs), before start-up has finished, while the recovery OS is
  being written into slot A, or when slot A doesn't hold the recovery OS.
  Example: `curl -X POST http://PRINTER/machine/kiln_os/boot_recovery`.
  Over SSH: `ad5x-boot-recovery`.

## From a USB stick

For a printer that can't reach the network (or Fluidd), a release can be
installed from a USB stick. The stick is read only by the **recovery OS**,
when the printer starts it: putting the stick in and restarting the
printer normally does nothing, because a normal start runs the main
system, which ignores the stick.

1. Format the stick FAT32 or ext4 (not exFAT).
2. Copy the release's `kiln-os-vX.Y.Z-update.zip` into its top directory,
   unchanged (not unpacked).
3. Next to it, create an empty file named `ad5x-autoupdate` (no
   extension; on Windows check that it isn't saved as
   `ad5x-autoupdate.txt`).
4. Put the stick in the printer and start the recovery OS (below). It
   installs the update (about 3 minutes, progress on the touch screen),
   writes `ad5x-autoupdate.log` on the stick and starts the new system.
   Each zip is installed only once (its sha256 goes to
   `/data/ad5x/update/applied.list`), so a stick left in doesn't install
   it again; take it out anyway.

Without `ad5x-autoupdate` the recovery OS only offers what is on the
stick: its touch screen's **Install update** page lists it.

Getting into the recovery OS:

- **From the network**, if it still works for a moment:
  `curl -X POST http://PRINTER/machine/kiln_os/boot_recovery` (or
  `ad5x-boot-recovery` over SSH). It is refused while printing and in the
  first minute after power-on, until start-up has finished. With the
  network up, Fluidd's own update (Settings → Software Updates → Kiln OS)
  is simpler than a stick.
- **From the touch screen** (no network needed): Settings → System →
  **Boot into recovery**, then Restart. It sends the same request, so it is
  refused the same way while printing or still starting.
- **Last resort: interrupt a start.** Switch the printer off while it is
  still starting (the Kiln OS logo, before the touch screen comes up) and
  on again: a start that didn't finish lands in the recovery OS. Side
  effect: the interrupted start counts against Kiln's own kernel, so the
  next start of the main system may use the stock kernel (Fluidd then
  warns "Running the stock kernel"). Fix it with `ad5x-kernel retry` over
  SSH, or `POST /machine/kiln_os/kernel_retry` (see "The kernel" above),
  which reboots the printer.

The recovery OS's other ways to install an update (its web page on port
8080, the drop folder): `docs/recovery-os.md`, "Updates (SWUpdate)".
