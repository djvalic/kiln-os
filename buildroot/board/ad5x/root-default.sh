# Sourced by post-build.sh (main and recovery): root's empty password in
# the image's /etc/shadow (Buildroot's root::, BR2_TARGET_GENERIC_ROOT_PASSWD
# unset) becomes the default "root", the same fixed hash S05ad5x-data
# binds when there is no Kiln or stock password (lib/rootpw.sh,
# ROOTPW_DEFAULT_HASH). So a start that fails before S05 leaves root/root,
# never an empty password. A root hash set some other way is left alone.
root_default_shadow() {	# TARGET
	local lib=$BR2_EXTERNAL_AD5X_PATH/package/ad5x-system/lib/rootpw.sh h
	h=$(sed -n "s/^ROOTPW_DEFAULT_HASH='\(.*\)'$/\1/p" "$lib")
	case $h in '$6$'*) ;; *) echo "root-default: no ROOTPW_DEFAULT_HASH in $lib" >&2; return 1 ;; esac
	[ -f "$1/etc/shadow" ] || { echo "root-default: no $1/etc/shadow" >&2; return 1; }
	H=$h awk -F: -v OFS=: '$1 == "root" && $2 == "" { $2 = ENVIRON["H"] } 1' \
		"$1/etc/shadow" > "$1/etc/shadow.new"
	chmod 600 "$1/etc/shadow.new"
	mv -f "$1/etc/shadow.new" "$1/etc/shadow"
	grep -q '^root:\$6\$' "$1/etc/shadow" || grep -q '^root:[^:]' "$1/etc/shadow" ||
		{ echo "root-default: root's password still empty" >&2; return 1; }
}
