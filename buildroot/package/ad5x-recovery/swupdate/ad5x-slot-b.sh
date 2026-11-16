#!/bin/sh
# Shell script inside every main-OS .swu (tools/make_swu.sh), run by
# SWUpdate on the recovery OS (slot A):
#   ad5x-slot-b.sh preinst|postinst|postfailure [key=value...]
# The key=values come from the signed sw-description ("data"):
#   rootfs_size= rootfs_sha256= [kernel_size= kernel_sha256=]
#
# preinst      we run from slot A (rootfs, p2); rootfs2/kernel2/ota match
#              the SPL's partition table; rootfs2 isn't mounted; an update
#              without a kernel (the normal case: releases carry none) needs
#              a uImage already in kernel2 (the printer's own stock kernel),
#              which it keeps; the boot flag is pointed at slot A (here)
#              while slot B is rewritten.
# postinst     read back rootfs2 (and kernel2) and compare with the
#              sha256s; mount rootfs2 read-only and require
#              /etc/ad5x-release and /linuxrc; then boot flag -> slot B;
#              started by Kiln's U-Boot, also U-Boot's state and kernel
#              failure records cleared (rc_uboot_fresh).
# postfailure  boot flag stays on slot A.
# Any failure: exit 1, SWUpdate reports the update as failed.
. ${AD5X_RECOVERY_LIB:-/usr/lib/ad5x-recovery}/recovery.sh || exit 1
phase=$1; shift
for kv in "$@"; do
	case "$kv" in
	rootfs_size=*|rootfs_sha256=*|kernel_size=*|kernel_sha256=*) eval "${kv%%=*}=\${kv#*=}" ;;
	esac
done
say() { echo "ad5x-slot-b $phase: $*"; }
fail() { echo "ad5x-slot-b $phase: FAILED: $*" >&2; ad5x-bootlog "swu $phase failed: $*" 2>/dev/null; exit 1; }

case "$phase" in
preinst)
	[ "$(rc_slot)" = A ] || fail "not running from slot A (root $(rc_root))"
	# Return to Flashforge firmware (ad5x-return-stock) left unfinished:
	# finish it, or drop its record (ad5x-return-stock --forget)
	[ "$(sed -n 's/^state=//p' "$AD5X_DATA/ad5x/return-stock/state" 2>/dev/null)" = started ] &&
		fail "a Return to Flashforge firmware is not finished: finish it, or ad5x-return-stock --forget first"
	for n in rootfs2 kernel2 ota; do
		rc_spl_ok $n || fail "GPT entry $n differs from the SPL table"
		[ "$(readlink -f "$AD5X_DEV/disk/by-partlabel/$n")" = "$(readlink -f "$(rc_part $n)")" ] ||
			fail "$AD5X_DEV/disk/by-partlabel/$n doesn't point at $(rc_part $n)"
	done
	rc_mounted "$(rc_part rootfs2)" && fail "rootfs2 is mounted"
	[ -n "$rootfs_size" ] && [ -n "$rootfs_sha256" ] || fail "no rootfs size/sha256 in sw-description"
	[ "$rootfs_size" -le "$(rc_part_bytes rootfs2)" ] || fail "rootfs $rootfs_size bytes doesn't fit rootfs2"
	# Kiln's boot loader in the first MiB: no kernel but Kiln's 6.6 goes
	# into a slot, and the main OS puts its own there itself (S99ad5x-
	# update-recovery). An update that brings a kernel is refused; an
	# empty kernel2 gets only a Kiln 6.6 from p1, or stays empty (U-Boot
	# starts the main OS from rootfs2). Recovery OSes without
	# rc_boot_loader don't know this.
	kiln=
	command -v rc_boot_loader >/dev/null 2>&1 && [ "$(rc_boot_loader)" = kiln ] && kiln=1
	[ -n "$kiln" ] && [ -n "$kernel_size" ] &&
		fail "Kiln's boot loader is installed: updates that bring a kernel are not taken (slot B's kernel is the system's own 6.6)"
	if [ -z "$kernel_size" ] && [ -n "$kiln" ] && ! rc_uimage_len "$(rc_part kernel2)" >/dev/null &&
	   [ "$(rc_kernel_kind "$(rc_part kernel)")" != kiln ]; then
		say "kernel2 holds no kernel and kernel (p1) no Kiln 6.6: kernel2 stays empty (Kiln's boot loader; the main OS writes its 6.6 there)"
	elif [ -z "$kernel_size" ]; then
		# rootfs-only update: slot B keeps the kernel it has. Without one
		# there, it gets the kernel this recovery runs on (kernel, p1: the
		# printer's own stock kernel, or Kiln's 6.6 under Kiln's boot
		# loader), never one from the update.
		if ! rc_uimage_len "$(rc_part kernel2)" >/dev/null; then
			alen=$(rc_uimage_len "$(rc_part kernel)") ||
				fail "neither kernel2 nor kernel holds a kernel (uImage), and the update brings none"
			say "kernel2 holds no kernel: copying this slot's kernel ($alen bytes)"
			mkdir -p "$AD5X_RUN"
			# uImage header last: a copy cut short leaves no header in
			# kernel2, never a valid header over a broken body. Written
			# here, not in recovery.sh: this script runs on whichever
			# recovery OS is installed, older ones included.
			k2=$(rc_part kernel2)
			head -c "$alen" "$(rc_part kernel)" > "$AD5X_RUN/kernel.copy" &&
				dd if=/dev/zero of="$k2" bs=4096 count=1 conv=fsync,notrunc 2>/dev/null &&
				dd if="$AD5X_RUN/kernel.copy" of="$k2" bs=4096 skip=1 seek=1 conv=fsync,notrunc 2>/dev/null &&
				sync &&
				dd if="$AD5X_RUN/kernel.copy" of="$k2" bs=4096 count=1 conv=fsync,notrunc 2>/dev/null ||
				fail "copying the kernel to kernel2"
			rc_drop_caches
			[ "$(rc_sha "$(rc_part kernel2)" "$alen")" = "$(rc_sha "$AD5X_RUN/kernel.copy" "$alen")" ] ||
				fail "kernel2 copy reads back wrong"
			rm -f "$AD5X_RUN/kernel.copy"
		fi
		klen=$(rc_uimage_len "$(rc_part kernel2)") || fail "kernel2 holds no kernel (uImage)"
		[ "$klen" -le "$(rc_part_bytes kernel2)" ] || fail "kernel2 uImage header says $klen bytes, more than the partition"
		say "keeping the kernel in kernel2 ($klen bytes)"
	fi
	if [ "$(rc_flag_slot)" != A ]; then
		rc_set_flag A || fail "can't point the boot flag at slot A"
	fi
	say "writing slot B; boot flag $(rc_read_flag)"
	ad5x-bootlog "swu preinst ok" 2>/dev/null
	;;
postinst)
	rc_drop_caches
	got=$(rc_sha "$(rc_part rootfs2)" "$rootfs_size")
	[ "$got" = "$rootfs_sha256" ] || fail "rootfs2 reads back $got, expected $rootfs_sha256"
	if [ -n "$kernel_size" ]; then
		got=$(rc_sha "$(rc_part kernel2)" "$kernel_size")
		[ "$got" = "$kernel_sha256" ] || fail "kernel2 reads back $got, expected $kernel_sha256"
		rc_uimage_len "$(rc_part kernel2)" >/dev/null || fail "kernel2 holds no uImage"
	elif ! rc_uimage_len "$(rc_part kernel2)" >/dev/null; then
		# an empty kernel2 is right only under Kiln's boot loader (preinst)
		command -v rc_boot_loader >/dev/null 2>&1 && [ "$(rc_boot_loader)" = kiln ] ||
			fail "kernel2 holds no uImage"
	fi
	m=$AD5X_RUN/swu-check
	mkdir -p "$m"
	mount -t squashfs -o ro "$(rc_part rootfs2)" "$m" || fail "rootfs2 doesn't mount as squashfs"
	ok=; [ -f "$m/etc/ad5x-release" ] && { [ -e "$m/linuxrc" ] || [ -L "$m/linuxrc" ]; } && ok=1
	rel=$(cat "$m/etc/ad5x-release" 2>/dev/null)
	umount "$m"
	[ -n "$ok" ] || fail "rootfs2 lacks /etc/ad5x-release or /linuxrc"
	rc_set_flag B || fail "can't point the boot flag at slot B"
	say "slot B verified ($rel); boot flag $(rc_read_flag)"
	# Started by Kiln's U-Boot: the new system gets fresh tries and
	# U-Boot's kernel failure records go (an install is the retry; the
	# kernel release string is the same in every build). Recovery OSes
	# without rc_uboot_fresh leave that to "Boot main OS". Not fatal.
	if command -v rc_uboot_fresh >/dev/null 2>&1; then
		r=$(rc_uboot_fresh "install of $rel")
		[ -n "$r" ] && say "$r"
	fi
	ad5x-bootlog "swu postinst ok: $rel" 2>/dev/null
	;;
postfailure)
	[ "$(rc_flag_slot)" = A ] || rc_set_flag A
	say "update failed; boot flag $(rc_read_flag)"
	;;
esac
exit 0
