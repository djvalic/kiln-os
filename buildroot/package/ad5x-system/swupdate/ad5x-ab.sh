#!/bin/sh
# Shell script inside an A/B .swu (lib/ab.sh, mk-ab-sw-description.sh), run
# by SWUpdate on the main OS:
#   ad5x-ab.sh preinst|postinst|postfailure slot=a|b rootfs_size= rootfs_sha256=
#
# preinst      the slot isn't the running one and its root isn't mounted;
#              the image fits; the slot's kernel partition loses its uImage
#              header, so nothing takes the slot's old kernel for the new
#              system while it is written.
# postinst     the root reads back with the sha256 (past the caches); it
#              mounts and is Kiln's main OS (/etc/ad5x-release, /linuxrc,
#              /usr/lib/ad5x/kernel66/xImage, no /etc/ad5x-recovery); its
#              6.6 goes into the slot's kernel partition, header last, read
#              back (the SPL's way in when U-Boot proper is missing). Then
#              SWUpdate writes U-Boot's environment (bootenv).
# postfailure  nothing: U-Boot's environment is unchanged, the running
#              slot stays the one started.
# Any failure: exit 1, SWUpdate reports the update as failed.
. ${AD5X_LIB:-/usr/lib/ad5x}/slot.sh || exit 1
phase=$1; shift
slot= rootfs_size= rootfs_sha256=
for kv in "$@"; do
	case "$kv" in
	slot=*|rootfs_size=*|rootfs_sha256=*) eval "${kv%%=*}=\${kv#*=}" ;;
	esac
done
say() { echo "ad5x-ab $phase: $*"; }
fail() { echo "ad5x-ab $phase: FAILED: $*" >&2; ad5x-bootlog "ab $phase failed: $*" 2>/dev/null; exit 1; }
case "$slot" in a) S=A ;; b) S=B ;; *) fail "no slot in sw-description" ;; esac
ROOT=$(rootfs_of $S) || fail "no root partition for slot $S"
KERN=$(kernel_of $S) || fail "no kernel partition for slot $S"
bytes() { echo $(( $(cat /sys/class/block/${1##*/}/size) * 512 )); }
drop() { sync; echo 3 > /proc/sys/vm/drop_caches; }
sha_of() {	# DEV|FILE LEN
	{ dd if="$1" bs=4096 count=$(($2 / 4096)) 2>/dev/null
	  [ $(($2 % 4096)) = 0 ] || dd if="$1" bs=1 skip=$(($2 / 4096 * 4096)) count=$(($2 % 4096)) 2>/dev/null
	} | sha256sum | cut -c1-64
}

case "$phase" in
preinst)
	[ "$S" != "$SLOT" ] || fail "slot $S is the running one"
	grep -q "^$ROOT " /proc/mounts && fail "$ROOT is mounted"
	[ -n "$rootfs_size" ] && [ -n "$rootfs_sha256" ] || fail "no rootfs size/sha256 in sw-description"
	[ "$rootfs_size" -le "$(bytes "$ROOT")" ] || fail "rootfs $rootfs_size bytes doesn't fit $ROOT"
	dd if=/dev/zero of="$KERN" bs=4096 count=1 conv=notrunc,fsync 2>/dev/null ||
		fail "clearing $KERN's header"
	say "writing slot $S ($ROOT)"
	ad5x-bootlog "ab preinst ok: slot $S" 2>/dev/null
	;;
postinst)
	drop
	got=$(sha_of "$ROOT" "$rootfs_size")
	[ "$got" = "$rootfs_sha256" ] || fail "$ROOT reads back $got, expected $rootfs_sha256"
	m=/run/ad5x-ab-check
	mkdir -p $m
	mount -t squashfs -o ro "$ROOT" $m || fail "$ROOT doesn't mount as squashfs"
	ok=
	[ -f $m/etc/ad5x-release ] && { [ -e $m/linuxrc ] || [ -L $m/linuxrc ]; } &&
		[ -f $m/usr/lib/ad5x/kernel66/xImage ] && [ ! -e $m/etc/ad5x-recovery ] && ok=1
	rel=$(cat $m/etc/ad5x-release 2>/dev/null)
	k=/data/ad5x/update/ab/kernel.img
	[ -n "$ok" ] && cp $m/usr/lib/ad5x/kernel66/xImage $k
	umount $m
	[ -n "$ok" ] || fail "slot $S doesn't hold Kiln's main OS"
	uimage_ok $k || fail "the new 6.6 isn't a uImage"
	n=$(wc -c < $k)
	[ "$n" -le "$(bytes "$KERN")" ] || fail "the new 6.6 doesn't fit $KERN"
	dd if=$k of="$KERN" bs=4096 skip=1 seek=1 conv=notrunc,fsync 2>/dev/null &&
		dd if=$k of="$KERN" bs=4096 count=1 conv=notrunc,fsync 2>/dev/null ||
		fail "writing $KERN"
	drop
	[ "$(sha_of "$KERN" "$n")" = "$(sha_of $k "$n")" ] || fail "$KERN reads back wrong"
	rm -f $k
	say "slot $S verified ($rel), its 6.6 in $KERN"
	ad5x-bootlog "ab postinst ok: slot $S $rel" 2>/dev/null
	;;
postfailure)
	say "update failed; U-Boot's environment unchanged, slot $SLOT stays"
	;;
esac
exit 0
