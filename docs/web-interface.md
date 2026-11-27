# The web interface: Fluidd or Mainsail

Kiln OS comes with two web interfaces for the printer: **Fluidd** and
**Mainsail**. One of them opens when you type the printer's address into
a browser (`http://<printer-ip>/`). Fluidd is the default, also on a
printer that updates from an older Kiln OS: nothing changes until you
pick Mainsail.

Both talk to the same Klipper and Moonraker and show the same cameras
(`/webcam/`) and touch screen view (`/screen/`). Each keeps its own
settings (dashboard layout, macro buttons, themes), so switching back
and forth loses nothing.

Both start with the same macro list: the groups Filament, IFS,
Calibration, During print, Light & sound and System (Fluidd calls them
categories, Mainsail macro groups), with the slicer's and Kiln's internal
macros hidden. Each group has its own colour, the same in both: Filament
green, IFS teal, Calibration purple, During print blue, Light & sound
amber, System grey (Fluidd marks each button with it, Mainsail colours the
group). Macros in no group are under Uncategorized in both;
Mainsail's Uncategorized is kept up to date at each start, so macros a
plugin adds show up there too (delete that group in Mainsail's
Settings > Macros to stop it). Differences come from Mainsail itself: it
shows macro names instead of Fluidd's short labels, sorts the groups by
name, hides a macro that Fluidd only greys out while printing, and has no
buttons for Klipper commands that a macro replaces (`BED_MESH_CALIBRATE`,
`SCREWS_TILT_CALCULATE`) or that aren't macros (`M300`). Your own changes
in either one are never overwritten.

Only the chosen one may talk to the printer: the two are never both in
control. The other is only files on the printer's storage. It uses no
memory: nginx (one small worker) only sends files when a browser asks,
the switch changes one line of nginx's settings and reloads it, and any
of the unused interface's files the system had cached in memory are
dropped by itself when memory is needed.

## Switching

- **On the touch screen:** Settings > System > Web interface (turn on
  Settings > Advanced settings first, at the bottom of Settings). It lists
  the interfaces the printer has and shows the one on now; pick the other
  and the screen says "Web interface is now Mainsail. Reload the
  printer's page in your browser." (or Fluidd). While the mainsail-kiln
  plugin is on, the row is greyed: "Managed by the mainsail-kiln plugin".
- **From the console** in Fluidd or Mainsail: `KILN_WEBUI NAME=mainsail`
  or `KILN_WEBUI NAME=fluidd`. `KILN_WEBUI` alone says which one is on.
- **Over SSH:** `ad5x-webui mainsail` or `ad5x-webui fluidd`.
  `ad5x-webui` alone prints the current one, `ad5x-webui status` more.

The switch takes a second and needs no restart. It works while printing
too; the print isn't touched.

The first switch to Mainsail copies it from the system into
`/data/ad5x/web/mainsail` (about 10 MB) so it can be updated, like
Fluidd's copy in `/data/ad5x/web/fluidd`.

## A tab that still shows the old interface

- **Already open:** the printer disconnects it at the switch. Its console
  shows "This printer now uses Mainsail: reload the page" (or Fluidd),
  then it shows that it lost the connection and keeps trying to
  reconnect; each try is turned away the same way. Reload the page.
- **Reloaded:** both interfaces keep a copy of themselves in the browser
  (a service worker), so the very first load after a switch can still
  come from that copy. The printer then hands the browser a small
  clean-up worker instead of the old one: it deletes that copy and
  reloads the tab, which brings up the new interface within a moment.
  Only the cached pages go; settings kept in the browser stay. If a
  browser blocks cookies for the printer, closing the tab and opening it
  again does the same.
- Hosted copies (`app.fluidd.xyz`, `my.mainsail.xyz`) or ones in Docker or Home Assistant that you point at
  the printer count as Fluidd or Mainsail too: only the chosen one
  connects.

## Updates

Software Updates (Fluidd: Settings > Software updates; Mainsail: Machine
> Update Manager) offers updates for the interface you are using. The
other one keeps its copy and its version, and gets its update entry back
when you switch to it. A Kiln OS update never brings an older interface
back: the copy is only replaced when the system's own is newer.

Mainsail doesn't list Kiln OS's own update entries (`Kiln OS`, `klipper`,
`moonraker`): it shows only the entry types it knows. Update Kiln OS from
the touch screen or from Fluidd.

To go back to the system's own version of an interface: delete
`/data/ad5x/web/fluidd` or `/data/ad5x/web/mainsail` over SSH and
restart the printer.

## The mainsail-kiln plugin

The community plugin [mainsail-kiln](https://github.com/DIEHARDave/mainsail-kiln)
serves both interfaces at once, one on port 80 and the other on port 81,
and swaps them with its `WEB` macro. While it is on, it decides which is
on port 80, and Kiln's switch is refused with a message saying so. Use
`WEB`, or disable the plugin (`DISABLE_PLUGIN NAME=mainsail`) to use
Kiln's switch. Both use the same Mainsail copy in
`/data/ad5x/web/mainsail` and the same `mainsail` update entry.

## For developers

- The choice: `/data/ad5x/webui`, one line `fluidd` or `mainsail`
  (root's folder; written only by `ad5x-webui`, which runs as root).
  Missing, empty or anything else: Fluidd.
- At boot, `S61ad5x-web` (with `/usr/lib/ad5x/webui.sh`) keeps the copies
  up to date and writes nginx's port 80 root line,
  `/run/nginx/fluidd-root.conf` (the name stays for both interfaces:
  plugins read it).
- The touch screen (HelixScreen patch 0108,
  [helixscreen-integration.md](helixscreen-integration.md), "Web
  interface"), Fluidd and Mainsail use Moonraker's
  `GET`/`POST /machine/kiln_os/webui` ([api.md](api.md)); the root update
  agent (`S68ad5x-update-agent`, request `webui`) runs
  `ad5x-webui --no-sync NAME`, as for Extended memory. Any client
  Moonraker lets in can switch, as with the other settings there.
- The copies in `/data/ad5x/web` have plain files, as Moonraker's own
  update writes them: `ad5x-webui` and `S61ad5x-web` unpack the image's
  `.gz` files when they make one (so plugins that edit the files, such as
  mainsail-kiln's patch of Mainsail's `assets/*.js`, find them).
- What counts as served is nginx's root line, kept in line with what
  nginx runs (a failed reload puts the old line back). A plugin that puts
  its own line back (mainsail-kiln's `DISABLE_PLUGIN`) can leave it
  different from the choice until the next start: shut-out and update
  entries follow the served one, `GET` says `mismatch`, and choosing the
  stored one again re-applies it.
- The image's copies are trimmed at build time
  (`buildroot/board/ad5x/web-trim.py`): text files in `assets/` only
  gzipped (nginx: `gzip_static always; gunzip on;`, so a browser without
  gzip gets them unpacked), the other text files plain with a `.gz`
  beside them, and `.woff` fonts that have a `.woff2` dropped (and out of
  the service worker's precache list). A copy Moonraker updated has plain
  files only; nginx serves those as they are (no `.gz` there).
- Only the chosen interface may connect: Moonraker's `kiln_os` component
  watches `server.connection.identify` (event
  `websockets:client_identified`) and closes every websocket that
  identifies as the other one (`client_name` `fluidd` or `mainsail`,
  `type` `web`): first a `notify_gcode_response`
  `!! This printer now uses NAME: reload the page`, a second later the
  close (code 1008), at each reconnect, and at a switch for the ones
  already open. Every other client (the touch screen, slicers, mobile
  apps, agents, connections that never identify) is left alone, as are
  both interfaces while mainsail-kiln serves them. Plain HTTP requests
  carry no name and aren't checked; both interfaces do everything
  through the websocket and stop while it is closed.
- Service workers: Fluidd 1.38 and Mainsail 2.19 both register `/sw.js`
  (scope `/`) and serve their cached `index.html` for every page load.
  Without help, a switch to Mainsail still showed Fluidd once (Mainsail's
  worker takes over at once: `skipWaiting`, `clientsClaim`), and a switch
  to Fluidd kept showing Mainsail until every tab was closed (Fluidd's
  worker waits for its own page to let it in, and that page never
  loads). So each page nginx sends sets the cookie `kiln_webui=NAME`;
  `/sw.js` (never cached) is the interface's own worker for a browser
  whose cookie names it (none counts as Fluidd), and Kiln's reset worker
  (`/usr/share/ad5x/webui-reset/sw.js`) for one whose cookie names the
  other: it takes over, deletes Cache Storage (not local storage or
  IndexedDB), unregisters itself and reloads the tabs (only when it
  deleted something, so no reload loop). The maps are in
  `/run/nginx/webui-map.conf` (`lib/webui.sh`); while mainsail-kiln serves
  both there is no cookie and every browser gets the real worker.
- Only the served interface has an update manager entry; Moonraker's
  `kiln_os` component moves the entries at a switch, without a restart.
