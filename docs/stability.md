# What stays the same in 1.x

From v1.0.0 on, every 1.x release keeps the interfaces below as they are,
so plugins, slicer profiles, scripts and forks made for 1.0 keep working.
A change that would break one of them waits for 2.0 and is announced
before it lands.

The release candidates before v1.0.0 could still change them; the
"Road to v1.0" issue on GitHub collected the last requests. From v1.0.0
on, ask for additions in a new issue (below).

## Kept for all of 1.x

- **Plugin API** ([plugin-api.md](plugin-api.md)): the plugin layout,
  the `plugin.json` fields, the public commands, macros and status
  fields, the reserved names, plugins that drive the IFS, and root
  scripts. A 1.x update only adds to it (the minor version goes up); a
  plugin with `requires_os: "1.6"` runs on every later 1.x. The rules are
  in that page, "Version" and "Public and internal names".
- **Kiln's web API** ([api.md](api.md)): the `/machine/kiln_os/*`
  endpoints, the reply and error format and its reasons, Kiln's changes
  to Moonraker endpoints, the update manager entries and the Klipper
  status objects. Same rule and the same version number: `api_version` in
  `/machine/kiln_os/info` is the plugin API version (api.md, "Versions").
  v1.0.0 has plugin API 1.9; every 1.x has 1.9 or a later 1.y.
- **Your config files** ([config-layout.md](config-layout.md)):
  `printer.cfg`, `unit.cfg`, `local.cfg`, `plugins.cfg`,
  `ad5x-tuning.cfg` and `variables.cfg` are never changed by an update,
  and the include order stays. In `moonraker.conf` an update changes only
  lines exactly as an earlier image shipped them, keeps your copy as
  `moonraker.conf.bak-<date>` and says so in `config-updates.txt`. Files
  in `macros/` follow the rule in that page: an update that changes one
  keeps your edited copy as a backup and tells you.
- **Your data** ([data-layout.md](data-layout.md)): what lives where in
  `/data/ad5x`. An update keeps it and reads it the same way.
- **Updates and recovery** ([updates.md](updates.md),
  [boot-slots.md](boot-slots.md), [recovery-os.md](recovery-os.md)): the
  two system slots, the recovery OS, the install from a USB stick, the
  update file and the update from Fluidd, and the stable and test
  channels. Every 1.x release installs over any earlier 1.x.

## Can change in any 1.x release

- **Additions:** new commands, macros, endpoints, status fields,
  `plugin.json` keys and catalog plugins.
- **Anything internal:** names starting with `_` that plugin-api.md
  doesn't list as public, the bench tools it lists as internal, private
  Python functions, files in the read-only image (`/usr/share/ad5x`,
  init scripts) other than the paths plugin-api.md lists under "Paths",
  and `/run`.
- **Bundled software:** Klipper, Moonraker, Fluidd, HelixScreen and the
  kernel move to newer versions when that keeps the list above working.
  Their own changes are named in the CHANGELOG.
- **Defaults and looks:** a default that fixes a bug or a safety problem,
  and the look of the touch screen and web pages.

## Building on Kiln OS

- **Fork from a release tag** (`v1.0.0`, `v1.1.0`, ...). On GitHub, each
  release is one commit on top of the previous one, so a fork can merge
  each new release.
- **Plugins:** set `requires_os` to the plugin API version you wrote it
  for, and keep to the public names. `tools/check_plugin.py` checks
  `requires_os` and the reserved names; check the commands and fields you
  use against plugin-api.md yourself.
- **Something missing in the interfaces?** Open an issue. An addition can
  come in any 1.x; a change to what is listed above waits for 2.0.
