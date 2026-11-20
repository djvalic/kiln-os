# Contributing to Kiln OS

Thank you for looking. This page says how the code is organised, how to
build it, how to test it, and how changes are taken in. If you are new,
read [docs/architecture.md](docs/architecture.md) first, then the
[docs index](docs/README.md). Words like "slot", "eboard" or "chainload"
are in the [glossary](docs/glossary.md).

## Where the code lives

Kiln OS is developed in a private repository. The public GitHub repository
is an export of it: at every release, `tools/export_public.sh` copies an
allowlisted part of the tree and GitHub's `main` branch is replaced with
that copy. Some of the tree is not in the export yet, mainly the test
scripts and the builder (see below), and some lab notes that are still
being cleaned up.

This has one consequence for pull requests, explained under
[Pull requests](#pull-requests).

## Building

What exists today, and what you need for it:

| What | Where | Public |
|---|---|---|
| Both OS images (Buildroot external tree, two defconfigs) | `buildroot/`, [buildroot/README.md](buildroot/README.md) | yes |
| Kiln's 6.6 kernel and `chainload.ko` | `kernel-ingenic66/` (built by the `ad5x-kernel66` package) | yes |
| The opt-in 7.3 kernel | `kernel-mainline/` (built by `ad5x-kernel-mainline`) | yes |
| Board firmware (mainboard, eboard, IFS) | `tools/build_mcu.sh`, `klipper/mcu-configs/`, `klipper/mcu-patches/` | yes |
| Update files (`.zip`, `.swu`) | `tools/make_swu.sh` | yes |
| First-install files | `tools/make_install_stick.sh`, `tools/install/` | yes |
| Release (artifacts, checksums, notes) | `tools/release.sh` | yes |
| Vendor-free check | `tools/check_vendor_free.sh` | yes |
| The automated builder (Docker image, weekly and daily runs, all tests) | `tools/builder/`, `tools/autobuild.sh`, `tools/autobuild_apps.sh`, `tools/kiln-build` | **not yet** |

### What a build needs

- A Linux x86-64 machine with Buildroot's usual host tools, about 60 GB of
  disk, and network access for the downloads. `tools/builder/Dockerfile`
  (private for now) installs, on Debian trixie: `build-essential`, `g++`,
  `cpio`, `unzip`, `rsync`, `bc`, `lzop`, `python3` with `setuptools`,
  `flex`, `bison`, `libssl-dev`, `libelf-dev`, `squashfs-tools`,
  `u-boot-tools`, `device-tree-compiler` and the usual archivers.
- Buildroot **2026.02.3**, checked out at `buildroot/src` (git-ignored).
- Ingenic's X2600 6.6 SDK kernel tree at `~/workspace/ingenic-sdk-6.6`
  (or set `BR2_PACKAGE_AD5X_KERNEL66_SDK`). How to get it:
  `kernel-ingenic66/README.md`.
- A prepared `linux-5.10.186` tree for `chainload.ko` at
  `~/workspace/chainload-build/linux-5.10.186` (or set
  `BR2_PACKAGE_AD5X_KERNEL66_KDIR510`), made by
  `kernel-ingenic66/chainload/setup.sh` with Buildroot's toolchain. It
  downloads the 5.10.186 source from kernel.org.
- For the board firmware: `arm-none-eabi-gcc` and `arm-none-eabi-newlib`.

No Flashforge file is needed or used: the default build is vendor-free.

### The sequence

This is the order the maintainer's builder uses (`build_all` in
`tools/autobuild.sh`), written out by hand. It has not been run as written
outside the builder, so if a step fails, please open an issue.
[buildroot/README.md](buildroot/README.md) has the background.

```
git clone --depth 1 --branch 2026.02.3 https://github.com/buildroot/buildroot.git buildroot/src
export AD5X_VENDOR_FREE=1
BR="make -C buildroot/src BR2_EXTERNAL=$PWD/buildroot"

# 1. The toolchain, then the 5.10 tree chainload.ko is built against
$BR O=$PWD/buildroot/output ad5x_defconfig
$BR O=$PWD/buildroot/output toolchain
kernel-ingenic66/chainload/setup.sh        # uses buildroot/output/host/bin

# 2. The recovery OS first: the main image carries it
$BR O=$PWD/buildroot/output-recovery ad5x_recovery_defconfig
$BR O=$PWD/buildroot/output-recovery

# 3. The main OS, with the recovery image inside
AD5X_RECOVERY_IMAGE=$PWD/buildroot/output-recovery/images/rootfs.squashfs \
  $BR O=$PWD/buildroot/output

# 4. Check, then make an update file
tools/check_vendor_free.sh buildroot/output/images/rootfs.squashfs \
  buildroot/output-recovery/images/rootfs.squashfs
mkdir -p dist
tools/make_swu.sh --both -V v0.0.0-test.1 -o dist/test.swu   # dist/test.swu and dist/test.zip
```

`AD5X_VERSION` sets the version an image reports (`/etc/kiln-version`).
Without it, `post-build.sh` takes it from `git describe`. A main image
built without `AD5X_RECOVERY_IMAGE` carries no recovery OS; a printer that
installs it keeps the one it has.

Board firmware is built separately (`tools/build_mcu.sh`). An image
carries the version named in `klipper/mcu-dicts/FLASHED` (and
`FLASHED_IFS`) from `klipper/mcu-firmware/`; see `klipper/mcu-dicts/README.md`
before changing them.

### Trying a build on a printer

Install an update `.zip` you built with `ad5x-update` over SSH from the
main OS (it stages the file, boots the recovery OS, which installs it). See
[docs/updates.md](docs/updates.md), "Test builds", and
[docs/recovery-os.md](docs/recovery-os.md). Keep the recovery OS working:
it is how you get back.

## Tests

The tests are in `tools/test_*`. **They are not in the public export yet**,
so if you only have the GitHub copy you can't run them; the maintainer
runs them when porting your change (see below). The builder runs all of
them before every release. Each script's header says exactly what it covers.

Run them from the repository root. What they need:

| Needs | Tests |
|---|---|
| Python 3 only (some with `jinja2`) | `test_ad5x_nozzle.py`, `test_ad5x_soak.py`, `test_ad5x_soak_cancel.py`, `test_ad5x_sound.py`, `test_boot_eboard.py` (uses a pty; also runs stock's tool under qemu when the stock files are there), `test_kiln_lanes.py`, `test_kiln_os.py`, `test_moonraker_3mf.py`, `test_print_temps.py`, `test_print_start.py`, `test_quick_actions.py`, `test_heater_idle.py`, `test_pcb_fan_watch.py`, `test_flash_tools.py`, `test_plugin_api_doc.py`, `test_plugin_root_klipper.py`, `test_release_process.py`, `test_service_provider.py` (also checks Moonraker patch 0006 when a patched Moonraker source is given or built), `test_pyserial_mips.py` (pyserial built by Buildroot, or its tarball in `buildroot/dl` and `patch`), `test_network_nm.py` (with `nmcli` 1.40+ it also checks every keyfile with NetworkManager's own parser) |
| A Klipper checkout's `klippy/` as the argument, with `greenlet`, `cffi`, `pyserial` and `gcc` (Klipper builds its C helper) | `test_ad5x_plugins.py` (argument optional), `test_ad5x_setup.py`, `test_ad5x_weight.py`, `test_ifs.py`, `test_ad5x_resume.py`, `test_ad5x_log.py`, `test_klipper_reactor.py`, `test_klipper_mcu_restart.py`, `test_serial_tdd.py`, `test_plugin_tooling.py` (argument optional). Use the Klipper commit in `buildroot/package/klipper/klipper.mk`; the tests that need Kiln's host patches apply them to a copy. |
| A POSIX shell (some need a C compiler) | `test_ad5x_umask.sh`, `test_ad5x_web.sh`, `test_camera_conf.sh`, `test_config_templates.sh` (`--busybox ROOTFS` runs it with the image's BusyBox under qemu), `test_log_retention.sh`, `test_restore_stock.sh`, `test_touch_cal.sh`, `test_update_agent_links.sh`, `test_recovery_lang.sh`, `test_ifs_flash.sh` (bash), `test_plugin_root.sh`, `test_update_agent_service.sh`, `test_moonraker_migrate.sh`, `test_screen_tile.sh`, `test_watchdog.sh`, `test_memory.sh` |
| `bwrap` (bubblewrap) | `test_kernel_fallback.sh`, `test_wifi.sh`, `test_network_nm.sh` (also runs the computer's own NetworkManager on Kiln's config, when it has one) |
| A built image (`buildroot/output/images/rootfs.tar`), `qemu-user-static` (binfmt for MIPS) and `bwrap` | `test_image.sh`, `test_moonraker.sh`, `test_wizard.sh`, `test_mcu.sh`; `test_fb_show.sh` and `test_boot_logo.sh` run partly without one |
| Built images plus a `.swu` from `tools/make_swu.sh` | `test_recovery.sh` |
| Built images plus stock firmware files in the git-ignored `firmware/` | `test_install.sh` |
| Network (clones each catalog plugin) and a built image | `test_plugin_repos.sh` |
| Buildroot's HelixScreen download, `clang`, `lld`, SDL2 and other headers (see the script) | `test_helixscreen.sh` (with `test_helixscreen.known`, the known failures) |

When you change something a test covers, run that test. When you add
behaviour, add a case to the matching test, or a new `tools/test_*`
script, and list it in `tools/autobuild.sh` so the builder runs it.

## Rules for a change

### CHANGELOG.md

`CHANGELOG.md` is what people using Kiln OS read in the release notes.
Every change they can notice gets one entry in `## Unreleased`, **in the
same commit as the code**:

- one bullet, a short bold title, then what changes for the person at the
  printer, in plain words (not the code that changed);
- `(issue #N)` when it fixes a reported issue;
- internal changes nobody can notice (tests, refactors, developer docs)
  need no entry.

### Deviations from stock

Anything that behaves differently from Flashforge's stock firmware gets a
row in [docs/deviations-from-stock.md](docs/deviations-from-stock.md), in
the same commit: risk, what stock does, what Kiln OS does, the symptom if
it goes wrong, and how to go back. Update its "Last updated" line.

### Docs

Update the page that describes what you changed. A new init script or a
new file under `/data/ad5x` goes into
[docs/boot-order.md](docs/boot-order.md) and
[docs/data-layout.md](docs/data-layout.md). A new doc page goes into the
[index](docs/README.md), and onto the `ALLOW` list in
`tools/export_public.sh` if it should be public.

### Names

- **Kiln OS** is the product name: use it in anything a person reads
  (screens, messages, release notes, docs).
- Internal names keep the `ad5x` prefix: commands (`ad5x-update`), paths
  (`/data/ad5x`, `/usr/lib/ad5x`), init scripts (`S05ad5x-data`), Klipper
  modules (`ad5x_*.py`), release marks (`/etc/ad5x-release`). Installed
  printers depend on them, so don't rename them.
- New Moonraker components and new release files use `kiln_` / `kiln-`
  (`kiln_os.py`, `kiln-os-<version>-update.zip`).
- Plugins prefix their own macros, modules and variables with the plugin
  name, and leave `ad5x_` and `kiln_` to the system
  ([docs/plugin-api.md](docs/plugin-api.md), "Rules for plugins").
- No Flashforge files, ever: no binaries, firmware or extracted code in
  the repository or the images. Describe stock behaviour in your own
  words.

### Commits

- One change per commit, with its tests, docs and CHANGELOG line.
- The subject says what changed, plainly, with the area first:
  `Cameras: at most two USB cameras, a third no longer takes the screen's port`,
  `ad5x-mcu flash-ifs: Flashforge's ifs.hex is checked with F19, not as Klipper`.
- The body, if any, says why and what you checked.
- No tool or AI attribution lines (`Co-Authored-By:` for tools,
  session links and the like). Credit people, not tools.
- The code is GPL-3.0-or-later (the kernels GPL-2.0). Please put a
  licence line (for example `SPDX-License-Identifier: GPL-3.0-or-later`)
  at the top of new source files.

### Shell scripts

The printer runs BusyBox `sh`. Keep scripts POSIX (no bash-only syntax in
anything the image installs), set `umask 022` at the top of init scripts,
and check the applets the image's BusyBox has (it has no `stat`, for
example).

## Pull requests

Pull requests on GitHub are welcome. Because GitHub's `main` is replaced
by a fresh export at every release, a PR merged on GitHub would be lost at
the next release. So PRs are not merged there. Instead the maintainer
**ports** each accepted PR into the private repository by hand, keeps you
as the author or credits you in the commit and the release notes, adds the
tests and the CHANGELOG line (which you can't see or keep in the public
copy), and then closes the PR with a comment that links the release it
went into.

What helps:

- a short description of what changes on the printer and how you checked
  it (on a printer, or which commands you ran);
- one topic per PR;
- the CHANGELOG line you would like, in the PR description (the file
  itself is rewritten from the private copy at each release);
- for hardware or boot changes: what happens if it goes wrong, and how to
  get back.

Larger changes (a new board, a kernel change, anything in the boot path or
the update path): open an issue first, so we can agree on the approach
before you spend the time.

## Reporting a problem

Open an issue with the Kiln OS version (Fluidd, Settings, Software
Updates, or `cat /etc/kiln-version`), what you did and what happened.
Logs help: `klippy.log` and `moonraker.log` (Fluidd shows them), and for
start-up problems `/run/ad5x-boot.log`. See [docs/logs.md](docs/logs.md).
