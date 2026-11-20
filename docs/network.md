# The network (main OS)

The main OS runs Ethernet and Wi-Fi with **NetworkManager**. The old way,
`wpa_supplicant` and `udhcpc` started by `S41ad5x-eth` and `S42ad5x-wifi`, is still
in the image: the printer takes it on its own when NetworkManager doesn't
bring the network up, and you can choose it with a file. The **recovery OS**
keeps the old way only. It has no NetworkManager (see
[recovery-os.md](recovery-os.md)).

The NetworkManager part was ported from PR #53 by jolting (Hunter Laux).

## What you edit stays the same

Your network settings stay in the same files as before
([data-layout.md](data-layout.md)), and every 1.x release reads them the
same way ([stability.md](stability.md)):

| File | What |
|---|---|
| `/data/ad5x/network.conf` | Ethernet: `MODE=dhcp` or `MODE=static`, `ADDRESS=a.b.c.d/nn`, `GATEWAY=`, `DNS="..."`, `IFACE=`. An invalid static address falls back to DHCP. |
| `/data/ad5x/wpa_supplicant.conf` | The saved Wi-Fi networks (mode 0600). The first start fills it with the networks saved on stock's screen. A block with `disabled=1` is saved but not joined automatically: stock saves its networks that way, so after a fresh install the printer joins none of them by itself until one is joined on the screen. |
| `/data/ad5x/wifi.disable` | No Wi-Fi at all. Nothing manages `wlan0` and it stays down (issue #44). |

At every start, `S40ad5x-network` makes NetworkManager's connections new from
these files. It writes them as keyfiles in `/run/ad5x-network/connections`,
in RAM. An edit to `network.conf` or `wpa_supplicant.conf` takes effect at
the next start, as before.

When the touch screen joins a network, changes a password or forgets a
network, NetworkManager saves that in its keyfiles. Kiln writes it back to
`wpa_supplicant.conf` right away (BusyBox `inotifyd` on the connections,
`lib/network-event`), and once more when the printer shuts down. So the
recovery OS, the old way and an older release in the other slot all have
the same networks. The write-back:

- keeps a block that didn't change exactly as you wrote it, comments and
  extra lines (`bssid=`, `freq_list=` ...) included;
- for a changed password, priority or "don't join automatically", changes
  only those lines in the block (a network joined on the screen loses its
  `disabled=1`, so it is joined automatically from then on);
- takes out a network that was forgotten on the screen;
- adds a network joined on the screen at the end;
- never touches lines it doesn't understand: WEP and enterprise (802.1X)
  networks, blocks without an SSID, everything outside the blocks;
- writes nothing when nothing changed.

NetworkManager can't use WEP or enterprise networks from
`wpa_supplicant.conf`: they are left out (the log counts them) and kept in
the file. With such a network, use the old way (below).

Connections you make with `nmcli` that these two files can't hold, such as
a VLAN, or Ethernet settings changed with `nmcli`, don't outlive a restart.
Put Ethernet settings in `network.conf`.

## Choosing the old way

| File | Effect |
|---|---|
| `/data/ad5x/network-legacy` | Yours. The old way at every start: `wpa_supplicant` and `udhcpc`, HelixScreen with its `wpa_supplicant` backend, as in rc3 and earlier. Delete it and restart to use NetworkManager again. |
| `/data/ad5x/network-legacy.auto` | The printer made it (see below). The old way at every start. It holds the date and the reason. Delete it and restart to try NetworkManager again. |

To switch with no update and no screen: `touch /data/ad5x/network-legacy`
over SSH, then restart. `/etc/init.d/S40ad5x-network status` shows the stack
of this start and the next one.

## Safety net

A printer that is only reached over the network must not be cut off by
NetworkManager. After `S40ad5x-network` starts NetworkManager, a check runs
in the background:

1. NetworkManager must be running within **30 s**.
2. Some interface must have an IPv4 address (scope global) within **120 s**
   of the start. A default route isn't required, because a static
   `network.conf` without `GATEWAY` has none.

If either fails **and a network was to be expected**, this same start switches
to the old way. A network is expected when an Ethernet cable is in
(`/sys/class/net/eth0/carrier`), or when a Wi-Fi network to join
automatically is saved (a block without `disabled=1`), Wi-Fi isn't off
(`wifi.disable`) and isn't switched off on the screen. A network saved with
`disabled=1` doesn't count: neither NetworkManager nor the old way joins it by
itself. The switch:

- writes NetworkManager's networks back to `wpa_supplicant.conf`;
- stops NetworkManager (TERM, then KILL after 10 s) and its `wpa_supplicant`,
  and clears the addresses on `eth0` and `wlan0`;
- removes `/run/NetworkManager`, so HelixScreen takes its `wpa_supplicant`
  backend;
- starts `S41ad5x-eth` and `S42ad5x-wifi`, and restarts HelixScreen if it is
  running.

If the old way then has an IPv4 address within **60 s**,
`network-legacy.auto` is written and later starts use the old way too. If it
has none either, the fault wasn't NetworkManager's: no file is written, and
the next start tries NetworkManager again.

When no network was to be expected (no cable, and no saved Wi-Fi network to
join automatically, as on a fresh install before the setup wizard's Wi-Fi
step, also when stock's networks were brought over with `disabled=1`),
NetworkManager stays, so the wizard can join a network through it.
`network.log` says why, for example "none to expect (no Ethernet cable, 1
saved Wi-Fi network(s), 0 to join automatically)".

A setup that fails before NetworkManager starts also takes the old way for
that start: no `NetworkManager` binary, or `ad5x_network.py` failing.

## Settings

`/etc/NetworkManager/NetworkManager.conf` (in the image):

- keyfiles only, in `/run/ad5x-network/connections`. NetworkManager's state
  (DHCP leases, its secret key) is in `/data/ad5x/NetworkManager`, which
  `/var/lib/NetworkManager` links to. `NetworkManager.state` there (the
  radio and networking switches set with `nmcli`) is removed at every start,
  and so are the DHCP lease files of connections no longer saved (a lease
  file is named by its connection's UUID; Kiln's connections keep theirs
  from start to start).
  HelixScreen applies its own Wi-Fi switch again at its start (patch 0051).
- DHCP with NetworkManager's internal client, the MAC as client ID (as
  `udhcpc`), Ethernet asking forever (`dhcp-timeout` infinity, as
  `udhcpc -b`), `autoconnect-retries=0` on Kiln's connections.
- Ethernet with stock's MAC (usershare `/MAC`, as `S41ad5x-eth` sets it) and
  no connection of NetworkManager's own (`no-auto-default=*`).
- Every saved Wi-Fi network `hidden=true` (as `S42ad5x-wifi`'s `scan_ssid=1`),
  power saving off (`wifi.powersave=2`, issue #37), no random MAC while
  scanning.
- `auth-polkit=root-only`: there is no polkit, and only root may change the
  network. HelixScreen runs as root; Klipper's and the web server's users
  can't.
- `/run/NetworkManager/conf.d/50-ad5x-wifi-disable.conf` (from `S40`):
  `wlan0` unmanaged while `wifi.disable` is there.

Moonraker stays off the D-Bus system bus that NetworkManager needs
(`S62moonraker` sets `DBUS_SYSTEM_BUS_ADDRESS` to no socket). Nothing Moonraker
does here uses the bus, and dbus_fast stays out of its memory (patch 0009).

## The touch screen

HelixScreen picks its Wi-Fi backend by itself at start. When
`/run/NetworkManager` exists it uses NetworkManager (`nmcli`), and otherwise
`wpa_supplicant`. On the old way `/run/NetworkManager` is never made, so the
screen works as in rc3. Kiln's patches 0046 and 0051 are in HelixScreen's Wi-Fi
manager, above both backends, so they apply to both.

Joining a network that already has a connection (one Kiln made from
`wpa_supplicant.conf`, or one the screen made earlier) updates that
connection in place (patch 0083): `nmcli connection modify` with the
password, its key management kept and autoconnect on, then `nmcli
connection up`. The connection keeps its file, its UUID and so its DHCP
lease, and the write-back changes the password in `wpa_supplicant.conf` and
takes out `disabled=1`. A join that doesn't end with the connection up puts
its password, password storage (`psk-flags`), autoconnect and hidden flag
back as they were (patch 0086): a wrong password, or a join cancelled by
tapping another network or by the screen stopping. NetworkManager saves the
change at once, so without that a mistyped password would replace the good
one for the next start. The Wi-Fi device decides, not `nmcli`'s exit
(`nmcli -t -f GENERAL.CON-UUID,GENERAL.STATE device show`): when `nmcli`
fails or is stopped after 30 s while NetworkManager is still joining, the
screen waits up to a minute more and keeps the new password when the
connection comes up; a cancelled join keeps it only when the connection is
already up. The plain `nmcli device wifi connect <network> password ...` that
HelixScreen uses for a new network is refused for a saved one by the
`nmcli` of NetworkManager 1.52 ("802-11-wireless-security.key-mgmt: property
is missing": it replaces the connection's security settings with the
password alone; fixed in 1.56). Upstream's way out, deleting the connection
and making a new one, stays for a connection without key management.

## Logs

- `printer_data/logs/network.log`: the stack chosen and why, the
  connections made, the safety net's result, every write-back. The previous
  start's is `network.log.1`.
- `printer_data/logs/wifi.log`: on NetworkManager written by
  `S46ad5x-wifi-log` (driver, firmware, the saved networks and how many of
  them are joined automatically, the join, power saving), on the old way by
  `S42ad5x-wifi`. With no network to join automatically it says so ("not
  waiting for a join") instead of waiting 60 s for one.

## Start-up order (main OS)

`S30dbus-daemon`, then `S40ad5x-network` (choice, connections, write-back
watcher, check), `S41ad5x-eth` and `S42ad5x-wifi` (only on the old way),
`S45NetworkManager` (only on NetworkManager, `/etc/default/NetworkManager`),
then `S46ad5x-wifi-log` (only on NetworkManager). The choice of this start is
in `/run/ad5x-network/mode` (`nm` or `legacy`). See
[boot-order.md](boot-order.md).

## Size

NetworkManager 1.52 with `nmcli`, GLib, D-Bus, libndp, readline and ncurses
add about 4.7 MB to the root filesystem (squashfs, LZO), measured from a
Buildroot 2026.02.3 build of these packages with Kiln's toolchain. To get
there, NetworkManager and GLib are built with `-Os` (`buildroot/external.mk`)
and the unused parts are dropped (`board/ad5x/network-nm.sh`: the initrd
generator, dispatcher, dhclient helper, ADSL plugin, GLib's and PCRE2's
tools, GLib's introspection library, D-Bus's session tools). The build has
no ModemManager, PPP, OVS, Bluetooth, team, nmtui, polkit or TLS library
(crypto `null`: only 802.1X certificates would need one).

## Tests

- `tools/test_network_nm.py`: the connections made from `network.conf` and
  `wpa_supplicant.conf` and the write-back. With the laptop's `nmcli`, every
  keyfile is also read back by NetworkManager's own parser.
- `tools/test_network_nm.sh`: the choice, the guards in S41, S42, S45 and S46,
  the safety net and the write-back trigger, in a sandbox. It also runs the
  laptop's own NetworkManager on Kiln's config when one is installed.
- `tools/test_image.sh`: the image has both stacks and the trims. Its
  NetworkManager, `nmcli`, D-Bus and `wpa_supplicant` start under qemu, and its
  Python makes connections.
