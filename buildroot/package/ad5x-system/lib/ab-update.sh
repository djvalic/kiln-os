# A/B updates (prototype): the main OS in both slots. The running slot
# writes the other one and points the boot flag at it; Kiln's U-Boot falls
# back to the running one if the new one doesn't finish starting twice. No
# recovery OS: U-Boot's last resort is safe mode (lib/safe.sh).
#
# /data/ad5x/ab marks a printer laid out this way: ad5x-update installs
# into the other slot, and the 1.x jobs that write the recovery OS into
# slot A (S99ad5x-install-recovery, S99ad5x-update-recovery) stay off.
AB_MARK=/data/ad5x/ab

ab_layout() { [ -f "$AB_MARK" ]; }

ab_die() { echo "ad5x-update: $*" >&2; exit 1; }

# ab_write DEV IMAGE: IMAGE onto DEV, its first 4 KiB last (until then the
# slot has no SquashFS superblock or uImage header: U-Boot and the SPL
# don't take it for a system), each step read back past the caches
ab_write() {
	_dev=$1 _img=$2
	_n=$(wc -c < "$_img")
	_cap=$(( $(cat /sys/class/block/${_dev##*/}/size) * 512 ))
	[ "$_n" -le "$_cap" ] || ab_die "$_img: $_n bytes don't fit $_dev ($_cap)"
	dd if=/dev/zero of="$_dev" bs=4096 count=1 conv=notrunc,fsync 2>/dev/null ||
		ab_die "$_dev: zeroing its start failed"
	dd if="$_img" of="$_dev" bs=4096 skip=1 seek=1 conv=notrunc,fsync 2>/dev/null ||
		ab_die "$_dev: writing failed"
	dd if="$_img" of="$_dev" bs=4096 count=1 conv=notrunc,fsync 2>/dev/null ||
		ab_die "$_dev: writing its start failed"
	sync
	echo 3 > /proc/sys/vm/drop_caches
	_want=$(sha256sum < "$_img" | cut -c1-64)
	_got=$( { dd if="$_dev" bs=4096 count=$((_n / 4096)) 2>/dev/null
		  [ $((_n % 4096)) = 0 ] || dd if="$_dev" bs=1 skip=$((_n / 4096 * 4096)) \
			count=$((_n % 4096)) 2>/dev/null; } | sha256sum | cut -c1-64)
	[ "$_got" = "$_want" ] || ab_die "$_dev reads back wrong ($_got, not $_want)"
}

# ab_install FILE [SHA256] [REBOOT]: the main OS in FILE (an update .zip
# with rootfs.squashfs and SHA256SUMS, or a rootfs.squashfs) into the other
# slot, then the boot flag on it
ab_install() {
	_file=$1 _sum=${2:-} _reboot=${3:-}
	case "$SLOT" in
	A) _to=B ;; B) _to=A ;; *) ab_die "not running from a slot ('${SLOT:-?}')" ;;
	esac
	start_done || ab_die "start-up has not finished yet; nothing done"
	_t=/data/ad5x/update/ab
	rm -rf "$_t"; mkdir -p "$_t"
	if [ "$_file" = - ]; then cat > "$_t/in"; _file=$_t/in; fi
	if [ -n "$_sum" ] && [ "$(sha256sum < "$_file" | cut -c1-64)" != "$_sum" ]; then
		ab_die "$_file: sha256 isn't $_sum"
	fi
	if [ "$(head -c 4 "$_file")" = hsqs ]; then
		_img=$_file
	else
		unzip -o -q -d "$_t" "$_file" rootfs.squashfs SHA256SUMS 2>/dev/null ||
			ab_die "$_file: not a squashfs or an update .zip with rootfs.squashfs"
		_img=$_t/rootfs.squashfs
		_w=$(sed -n 's/^\([0-9a-f]\{64\}\)  rootfs.squashfs$/\1/p' "$_t/SHA256SUMS")
		[ -n "$_w" ] && [ "$(sha256sum < "$_img" | cut -c1-64)" = "$_w" ] ||
			ab_die "rootfs.squashfs doesn't match the package's SHA256SUMS"
	fi
	[ "$(head -c 4 "$_img")" = hsqs ] || ab_die "$_img: not a squashfs"
	mkdir -p /data/ad5x
	touch "$AB_MARK"
	echo "ad5x-update: slot $SLOT is running; writing the main OS into slot $_to"
	ab_write "$(rootfs_of $_to)" "$_img"
	echo "ad5x-update: slot $_to's root ($(rootfs_of $_to)) written and read back"
	# what it holds, and its 6.6 for the kernel partition (the SPL's way in
	# when U-Boot proper is missing): from the slot itself (no loop device)
	_m=/run/ad5x-ab-check
	mkdir -p $_m
	mount -t squashfs -o ro "$(rootfs_of $_to)" $_m ||
		ab_die "slot $_to's new root doesn't mount"
	_rel=$(cat $_m/etc/ad5x-release 2>/dev/null)
	if [ ! -f $_m/usr/lib/ad5x/kernel66/xImage ] || [ -f $_m/etc/ad5x-recovery ]; then
		umount $_m
		ab_die "slot $_to now holds something that isn't Kiln's main OS; the boot flag stays on $SLOT"
	fi
	cp $_m/usr/lib/ad5x/kernel66/xImage "$_t/kernel.img"
	umount $_m
	ab_write "$(kernel_of $_to)" "$_t/kernel.img"
	echo "ad5x-update: slot $_to's kernel ($(kernel_of $_to)) written and read back"
	set_flag $_to
	[ "$(read_flag)" = "$(flag_for $_to)" ] || ab_die "the boot flag didn't take"
	rm -rf "$_t"
	echo "ad5x-update: done: ${_rel:-the new main OS} in slot $_to, boot flag on it;" \
		"slot $SLOT stays as it is (U-Boot goes back to it if $_to doesn't start)"
	if [ -n "$_reboot" ]; then sync; reboot; fi
	exit 0
}
