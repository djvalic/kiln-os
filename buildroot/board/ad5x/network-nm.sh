# NetworkManager in the main image's target tree (docs/network.md), sourced
# by board/ad5x/post-build.sh:
#   nm_target TARGET
# The recovery image has no NetworkManager (it keeps wpa_supplicant and
# udhcpc).
#
# From PR #53 by jolting (Hunter Laux); the list of parts dropped is
# longer here, measured with Buildroot 2026.02.3 (NetworkManager 1.52.1,
# GLib 2.86.5, D-Bus 1.14.10).
nm_target() {
	t=$1
	# The root is read-only: NetworkManager's state (leases, secret key)
	# on /data
	rm -rf "$t/var/lib/NetworkManager"
	mkdir -p "$t/var/lib"
	ln -s /data/ad5x/NetworkManager "$t/var/lib/NetworkManager"
	# Room in the 100 MiB slot. Nothing here runs these:
	# - NetworkManager's initrd generator, dispatcher (no scripts) and
	#   dhclient helper (dhcp=internal), the ADSL plugin, the D-Bus
	#   introspection files and its Thunderbolt udev rule
	rm -f "$t/usr/libexec/nm-initrd-generator" "$t/usr/libexec/nm-dispatcher" \
		"$t/usr/libexec/nm-dhcp-helper" \
		"$t"/usr/lib/NetworkManager/*/libnm-device-plugin-adsl.so \
		"$t/usr/share/dbus-1/system.d/nm-dispatcher.conf" \
		"$t/usr/share/dbus-1/system-services/org.freedesktop.nm_dispatcher.service" \
		"$t/usr/lib/udev/rules.d/90-nm-thunderbolt.rules"
	rm -rf "$t/usr/share/dbus-1/interfaces" "$t/etc/NetworkManager/dispatcher.d" \
		"$t/usr/lib/NetworkManager/dispatcher.d" "$t/etc/NetworkManager/dnsmasq.d" \
		"$t/etc/NetworkManager/dnsmasq-shared.d" "$t/usr/lib/NetworkManager/VPN" \
		"$t/usr/share/bash-completion"
	# - GLib's tools and its introspection library, PCRE2's tools and POSIX
	#   library (NetworkManager links libgio, libgobject, libglib,
	#   libgmodule; GLib, nginx and git link libpcre2-8)
	rm -f "$t/usr/bin/gio" "$t/usr/bin/gdbus" "$t/usr/bin/gsettings" \
		"$t/usr/bin/gapplication" "$t/usr/bin/gresource" \
		"$t/usr/bin/gio-querymodules" "$t/usr/libexec/gio-launch-desktop" \
		"$t/usr/bin/glib-compile-schemas" "$t/usr/bin/glib-compile-resources" \
		"$t/usr/bin/gobject-query" "$t/usr/bin/gi-compile-repository" \
		"$t/usr/bin/gi-decompile-typelib" "$t/usr/bin/gi-inspect-typelib" \
		"$t"/usr/lib/libgirepository-2.0.so* \
		"$t/usr/bin/pcre2test" "$t/usr/bin/pcre2grep" \
		"$t"/usr/lib/libpcre2-posix.so*
	rm -rf "$t/usr/share/glib-2.0" "$t/usr/share/gettext/its" "$t/usr/lib/gio"
	# - D-Bus's session bus and tools (dbus-daemon, dbus-uuidgen for
	#   S30dbus-daemon, the activation helper for wpa_supplicant and
	#   dbus-send/dbus-monitor stay)
	rm -f "$t/usr/bin/dbus-test-tool" "$t/usr/bin/dbus-launch" \
		"$t/usr/bin/dbus-update-activation-environment" \
		"$t/usr/bin/dbus-run-session" "$t/usr/bin/dbus-cleanup-sockets" \
		"$t/usr/share/dbus-1/session.conf" "$t/etc/dbus-1/session.conf"
	rm -rf "$t/usr/share/xml/dbus-1"
	# - libndp's tool. ncurses and readline stay whole: nmcli, wpa_cli
	#   and sqlite3 link them once they are in the build.
	rm -f "$t/usr/bin/ndptool"
	return 0
}
