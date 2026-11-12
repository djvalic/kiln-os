# NetworkManager in an image's target tree (docs/networkmanager.md),
# sourced by the post-build scripts of the main and the recovery image:
#   nm_target TARGET
nm_target() {
	t=$1
	# The networking of the releases before NetworkManager. Buildroot never
	# removes anything from the target tree, so drop them here.
	rm -f "$t/etc/init.d/S10mdev" "$t/etc/mdev.conf" \
		"$t/etc/init.d/S41ad5x-eth" "$t/etc/init.d/S42ad5x-wifi" \
		"$t/usr/lib/ad5x/network.sh"
	# The root is read-only: NetworkManager's state on /data
	# (S44ad5x-network makes the directory)
	rm -rf "$t/var/lib/NetworkManager"
	mkdir -p "$t/var/lib"
	ln -s /data/ad5x/NetworkManager/lib "$t/var/lib/NetworkManager"
	# Room in the 100 MiB slot: nothing here uses them
	rm -f "$t/usr/bin/pcre2test" "$t/usr/bin/pcre2grep" \
		"$t/usr/bin/gdbus" "$t/usr/bin/gio" "$t/usr/bin/gresource" \
		"$t/usr/bin/gsettings" "$t/usr/bin/gapplication" \
		"$t/usr/bin/glib-compile-schemas" "$t/usr/bin/gio-querymodules"
	rm -rf "$t/usr/share/bash-completion" "$t/usr/libexec/nm-dispatcher" \
		"$t/etc/NetworkManager/dispatcher.d"
}
