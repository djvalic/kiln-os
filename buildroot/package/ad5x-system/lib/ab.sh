# A/B updates (sourced; docs/ab-updates.md): the main OS in both slots,
# installed by SWUpdate into the slot that isn't running. Kiln's U-Boot
# (patch 0051) starts the slot in its environment's kiln_slot and guards an
# update with its standard boot count; this side sets the variables
# (SWUpdate's bootenv) and clears them once a start has finished
# (ab_confirm, from S99ad5x-booted).
#
# U-Boot says on the command line whether this start is A/B:
#   ad5x.ab=a|b  A/B, started from that slot
#   ad5x.ab=-    a U-Boot that knows A/B, the printer in 1.x's layout
#   (none)       an older U-Boot, or none: 1.x only
# Needs lib/slot.sh (SLOT, start_done, rootfs_of).
AB_LIB=${AD5X_LIB:-/usr/lib/ad5x}/ab
AB_WORK=/data/ad5x/update/ab

ab_arg() {
	for _w in $(cat /proc/cmdline 2>/dev/null); do
		case "$_w" in ad5x.ab=*) echo "${_w#ad5x.ab=}"; return 0 ;; esac
	done
}
ab_mode() { case "$(ab_arg)" in a|b) return 0 ;; esac; return 1; }
ab_capable() { [ -n "$(ab_arg)" ]; }

# ab_confirm: this start finished; an update in it is kept. U-Boot's boot
# count back to 0, and SWUpdate's ustate=1 (installed) to 0, in one write
# (fw_setenv -s: a power cut can't leave them half cleared), read back.
# ustate=3 (U-Boot went back from an update that didn't finish starting)
# stays, as SWUpdate expects, until the next update; it is reported here.
# Prints what it did.
ab_confirm() {
	ab_mode || return 0
	_u=$(fw_printenv -n upgrade_available 2>/dev/null)
	_c=$(fw_printenv -n bootcount 2>/dev/null)
	_s=$(fw_printenv -n ustate 2>/dev/null)
	[ "${_s:-0}" = 3 ] &&
		echo "A/B: the last update failed; U-Boot went back to slot $(ab_arg) (ustate 3, kept until the next update)"
	[ "${_u:-0}" = 0 ] && [ "${_c:-0}" = 0 ] && [ "${_s:-0}" != 1 ] && return 0
	_f=/run/ad5x-ab-confirm
	# fw_setenv's script: key=value lines (a line without '=' is skipped)
	printf 'upgrade_available=0\nbootcount=0\n' > $_f
	[ "${_s:-0}" = 1 ] && echo 'ustate=0' >> $_f
	fw_setenv -s $_f
	rm -f $_f
	_s2=$(fw_printenv -n ustate 2>/dev/null)
	if [ "$(fw_printenv -n upgrade_available 2>/dev/null)" = 0 ] &&
	   [ "$(fw_printenv -n bootcount 2>/dev/null)" = 0 ] &&
	   { [ "${_s:-0}" != 1 ] || [ "$_s2" = 0 ]; }; then
		echo "A/B: slot $(ab_arg) confirmed (upgrade_available ${_u:-0}, bootcount ${_c:-0}, ustate ${_s:-0} -> ${_s2:-0}, read back)"
	else
		echo "A/B: slot $(ab_arg): clearing U-Boot's boot count FAILED (it doesn't read back as 0); U-Boot goes back to the other slot after bootlimit starts"
	fi
}

ab_die() { echo "ad5x-update: $*" >&2; rm -rf "$AB_WORK"; exit 1; }

# ab_install FILE SUM REBOOT CONVERT: the main OS in FILE (an update .zip
# with rootfs.squashfs and SHA256SUMS, or a rootfs.squashfs; - for stdin)
# into the slot that isn't running, with SWUpdate. CONVERT: a printer in
# 1.x's layout (ad5x.ab=-, running slot B) gets it in slot A, over the
# recovery OS: from then on it is A/B.
ab_install() {
	_file=$1 _sum=$2 _reboot=$3 _convert=$4
	if ab_mode; then
		case "$(ab_arg)" in a) _to=b ;; *) _to=a ;; esac
	elif [ -n "$_convert" ]; then
		ab_capable || ab_die "this U-Boot doesn't know A/B (no ad5x.ab= on the command line): install Kiln's boot loader from this release first"
		[ "$SLOT" = B ] || ab_die "converting to A/B runs from the main OS in slot B"
		_to=a
		echo "ad5x-update: converting to A/B: the recovery OS in slot A is replaced by this main OS"
	else
		return 1
	fi
	start_done || ab_die "start-up has not finished yet; nothing done"
	rm -rf "$AB_WORK"; mkdir -p "$AB_WORK/tmp"
	if [ "$_file" = - ]; then cat > "$AB_WORK/in"; _file=$AB_WORK/in; fi
	[ -f "$_file" ] || ab_die "no file $_file"
	if [ -n "$_sum" ] && [ "$(sha256sum < "$_file" | cut -c1-64)" != "$_sum" ]; then
		ab_die "$_file: sha256 isn't $_sum"
	fi
	# /data needs room for the update and the .swu only (ab-pack.py
	# streams rootfs.squashfs from it); SWUpdate streams the .swu's root
	# into the slot (installed-directly)
	_ver=$(python3 "$AB_LIB/ab-pack.py" "$_file" "$AB_WORK/ab.swu" \
		"$AB_LIB/mk-ab-sw-description.sh" "$AB_LIB/ad5x-ab.sh") ||
		ab_die "packing the .swu from $_file"
	rm -f "$AB_WORK/in"
	echo "ad5x-update: slot $(echo "$SLOT" | tr AB ab) is running; SWUpdate installs $_ver into slot $_to"
	TMPDIR=$AB_WORK/tmp swupdate -v -e "stable,slot_$_to" -i "$AB_WORK/ab.swu" ||
		ab_die "SWUpdate failed; slot $_to isn't started (kiln_slot unchanged)"
	rm -rf "$AB_WORK"
	echo "ad5x-update: done: $_ver in slot $_to; U-Boot starts it next, and goes back to this slot if it doesn't finish starting"
	if [ -n "$_reboot" ]; then sync; reboot; fi
	exit 0
}
