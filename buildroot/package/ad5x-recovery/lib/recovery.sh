# AD5X recovery OS: shared shell helpers (sourced by the init scripts and
# the ad5x-* tools). See docs/recovery-os.md.
#
# Partitions are found by their GPT name (PARTNAME in sysfs), as in the
# main OS (/usr/lib/ad5x/slot.sh). For tests on the laptop every system
# path can be redirected (tools/test_recovery.sh):
#   AD5X_SYS      sysfs root            (default /sys)
#   AD5X_DEV      device directory      (default /dev)
#   AD5X_CMDLINE  kernel command line   (default /proc/cmdline)
#   AD5X_MOUNTS   mount table           (default /proc/mounts)
#   AD5X_DATA     userdata mount point  (default /data)
#   AD5X_RUN      runtime state dir     (default /run/ad5x)

: "${AD5X_SYS:=/sys}" "${AD5X_DEV:=/dev}" "${AD5X_CMDLINE:=/proc/cmdline}"
: "${AD5X_MOUNTS:=/proc/mounts}" "${AD5X_DATA:=/data}" "${AD5X_RUN:=/run/ad5x}"

# Partition table compiled into the SPL (docs/boot-slots.md): name, start
# LBA, sectors. The SPL boots by these numbers, not by the GPT; anything that
# writes a slot checks the GPT still agrees.
RC_SPL_TABLE="kernel:2048:16384 rootfs:18432:204800 kernel2:223232:16384
rootfs2:239616:204800 ota:444416:2048 usershare:446464:2097152
userdata:2543616:12238848"

# Names the backup/restore tools know, in disk order. "boot" is the first
# MiB of the disk (protective MBR + Ingenic boot block, GPT, SPL, U-Boot).
RC_PARTS="kernel rootfs kernel2 rootfs2 ota usershare userdata"

rc_say() { echo "${0##*/}: $*"; }
rc_die() { echo "${0##*/}: error: $*" >&2; exit 1; }

# sysfs directory of a partition, by GPT name
rc_part_sys() {
	for u in "$AD5X_SYS"/class/block/*/uevent; do
		[ -f "$u" ] || continue
		grep -qx "PARTNAME=$1" "$u" 2>/dev/null && { echo "${u%/uevent}"; return 0; }
	done
	return 1
}
# GPT name -> device path
rc_part() {
	s=$(rc_part_sys "$1") || return 1
	echo "$AD5X_DEV/$(sed -n 's/^DEVNAME=//p' "$s/uevent")"
}
rc_part_bytes() { s=$(rc_part_sys "$1") && echo $(( $(cat "$s/size") * 512 )); }
rc_part_start() { s=$(rc_part_sys "$1") && cat "$s/start"; }
# The disk holding the slots (mmcblk0): parent of the "rootfs" partition
rc_disk() {
	s=$(rc_part_sys rootfs) || return 1
	d=$(readlink -f "$s/..") || return 1
	echo "$AD5X_DEV/${d##*/}"
}
# Size of a name: a partition, or "boot" = the first MiB of the disk
rc_bytes() { [ "$1" = boot ] && echo 1048576 || rc_part_bytes "$1"; }
rc_dev() { [ "$1" = boot ] && rc_disk || rc_part "$1"; }

# GPT entry agrees with the SPL's built-in table?
rc_spl_ok() {
	want=$(echo "$RC_SPL_TABLE" | tr ' ' '\n' | grep "^$1:") || return 1
	s=$(rc_part_sys "$1") || return 1
	[ "$(cat "$s/start")" = "$(echo "$want" | cut -d: -f2)" ] &&
	[ "$(cat "$s/size")" = "$(echo "$want" | cut -d: -f3)" ]
}

# rc_crc32 FILE OFF LEN: the CRC-32 (zlib's, as the GPT and uImage use)
# of LEN bytes of FILE from OFF, 8 hex digits; gzip's trailer carries it
# (little endian), so this needs nothing beyond BusyBox (as slot.sh's
# uimage_ok). Data on stdin instead with FILE "-".
rc_crc32() {
	if [ "$1" = - ]; then set -- $(gzip -c | tail -c 8 | head -c 4 | od -An -t x1)
	else set -- $(tail -c +$(($2 + 1)) "$1" 2>/dev/null | head -c "$3" | gzip -c | tail -c 8 | head -c 4 | od -An -t x1); fi
	[ $# = 4 ] && echo "$4$3$2$1"
}
# rc_gpt FILE: FILE (a first MiB) has a GPT whose entries end before the
# SPL at 0x4400 (LBA 34): its header (EFI PART) at LBA 1 with the right
# header CRC, 1-128 entries of 128 bytes from the LBA the header names
# (LBA 2 on most boards; 32 on some, with a copy at LBA 2: a board
# restored over USB, djvalic/kiln-os#68) whose CRC is the one the header
# has, the array ending at LBA 34 at the latest, the first usable LBA 34
# or more. Sets RCG_LBA (the entries' LBA), RCG_N (their count), RCG_END
# (the byte the array ends at), RCG_FIRST (the first usable LBA). Says
# what is wrong otherwise.
rc_gpt() {
	rcg_f=$1
	RCG_LBA= RCG_N= RCG_END= RCG_FIRST=
	[ "$(tail -c +513 "$rcg_f" 2>/dev/null | head -c 8)" = "EFI PART" ] || { echo "no GPT header (EFI PART) at offset 512"; return 1; }
	rcg_hsz=$(od -An -t u4 -j 524 -N 4 "$rcg_f" | tr -d ' ')
	RCG_FIRST=$(od -An -t u8 -j 552 -N 8 "$rcg_f" | tr -d ' ')
	RCG_LBA=$(od -An -t u8 -j 584 -N 8 "$rcg_f" | tr -d ' ')
	RCG_N=$(od -An -t u4 -j 592 -N 4 "$rcg_f" | tr -d ' ')
	rcg_esz=$(od -An -t u4 -j 596 -N 4 "$rcg_f" | tr -d ' ')
	# small numbers only (an u8 past 2^63 would wrap in the shell's sums)
	for rcg_v in rcg_hsz RCG_FIRST RCG_LBA RCG_N rcg_esz; do
		eval "case \${$rcg_v} in ''|*[!0-9]*|??????????*) $rcg_v=99999999 ;; esac"
	done
	[ "$rcg_hsz" -ge 92 ] && [ "$rcg_hsz" -le 512 ] || { echo "GPT header: size $rcg_hsz"; return 1; }
	rcg_c=$( { tail -c +513 "$rcg_f" | head -c 16; printf '\000\000\000\000'
		tail -c +533 "$rcg_f" | head -c $((rcg_hsz - 20)); } | rc_crc32 -)
	[ "$rcg_c" = "$(od -An -t x4 -j 528 -N 4 "$rcg_f" | tr -d ' ')" ] || { echo "GPT header: its CRC is wrong"; return 1; }
	[ "$rcg_esz" = 128 ] && [ "$RCG_N" -ge 1 ] && [ "$RCG_N" -le 128 ] && [ "$RCG_LBA" -ge 2 ] && [ "$RCG_LBA" -le 33 ] ||
		{ echo "GPT header: $RCG_N entries of $rcg_esz bytes at LBA $RCG_LBA, not 1-128 entries of 128 bytes from LBA 2-33"; return 1; }
	RCG_END=$((RCG_LBA * 512 + RCG_N * 128))
	[ "$RCG_END" -le 17408 ] ||
		{ echo "GPT: $RCG_N entries at LBA $RCG_LBA end at $(printf '0x%x' $RCG_END), past 0x4400 (the SPL)"; return 1; }
	[ "$RCG_FIRST" -ge 34 ] || { echo "GPT: first usable LBA $RCG_FIRST, before 34 (the SPL at 0x4400)"; return 1; }
	[ "$(rc_crc32 "$rcg_f" $((RCG_LBA * 512)) $((RCG_N * 128)))" = "$(od -An -t x4 -j 600 -N 4 "$rcg_f" | tr -d ' ')" ] ||
		{ echo "GPT: the CRC of its $RCG_N entries at LBA $RCG_LBA isn't the header's"; return 1; }
}

# rc_boot_check FILE: FILE holds a first MiB for this printer: the boot
# ROM's block (INGE) at 0, a GPT (rc_gpt: header at 512, its entries where
# the header says, ending before the SPL, both CRCs right), and every
# partition of RC_SPL_TABLE among them at the table's start and size,
# which this disk's partitions have too (so the GPT written back agrees
# with the SPL and with the disk as it is). Says what is wrong otherwise.
rc_boot_check() {
	# (rcb_* names: the callers' variables stay untouched)
	rcb_f=$1
	[ "$(head -c 4 "$rcb_f")" = INGE ] || { echo "no Ingenic boot block (INGE) at offset 0"; return 1; }
	rc_gpt "$rcb_f" || return 1
	rcb_cnt=$RCG_N rcb_off=$((RCG_LBA * 512))
	# each entry as 16 numbers: type GUID (2), unique GUID (2), first and
	# last LBA, flags, name (9 words, UTF-16)
	rcb_gpt= rcb_i=0
	set -- $(od -An -v -t u8 -j $rcb_off -N $((rcb_cnt * 128)) "$rcb_f")
	while [ $# -ge 16 ]; do
		if [ "$5" != 0 ]; then
			rcb_name=$(tail -c +$((rcb_off + rcb_i * 128 + 57)) "$rcb_f" | head -c 72 | tr -d '\000')
			rcb_gpt="$rcb_gpt $rcb_name:$5:$(($6 - $5 + 1))"
		fi
		shift 16; rcb_i=$((rcb_i + 1))
	done
	for rcb_e in $RC_SPL_TABLE; do
		rcb_n=${rcb_e%%:*}
		case "$rcb_gpt " in *" $rcb_e "*) ;; *)
			echo "its GPT has no $rcb_n at sector $(echo $rcb_e | cut -d: -f2), $(echo $rcb_e | cut -d: -f3) sectors (the SPL table)"; return 1 ;;
		esac
		rc_spl_ok "$rcb_n" || { echo "this disk's $rcb_n differs from the SPL table"; return 1; }
	done
}

rc_root() { sed -n 's/.*root=\([^ ]*\).*/\1/p' "$AD5X_CMDLINE"; }
# Running slot from root=: A (rootfs, p2) or B (rootfs2, p4), else empty.
# root= is a device (the Flashforge SPL: root=/dev/mmcblk0p2) or a GPT name
# (a boot loader of our own: root=PARTLABEL=rootfs), as in slot.sh.
rc_slot() {
	r=$(rc_root)
	case "$r" in
	PARTLABEL=rootfs) echo A; return ;;
	PARTLABEL=rootfs2) echo B; return ;;
	PARTLABEL=*) return ;;
	esac
	r=${r##*/}
	case "$r" in
	"$(basename "$(rc_part rootfs 2>/dev/null)" 2>/dev/null)") echo A ;;
	"$(basename "$(rc_part rootfs2 2>/dev/null)" 2>/dev/null)") echo B ;;
	esac
}
rc_mounted() { grep -q "^$1 " "$AD5X_MOUNTS"; }
rc_mountpoint_of() { awk -v d="$1" '$1 == d { print $2; exit }' "$AD5X_MOUNTS"; }

# Boot flag (first sector of "ota"): the SPL boots slot B on "ota:kernel2"
rc_read_flag() { head -c 11 "$(rc_part ota)" 2>/dev/null | tr -d '\0\n'; }
rc_flag_slot() { [ "$(rc_read_flag)" = ota:kernel2 ] && echo B || echo A; }
rc_set_flag() {	# A|B, written as stock does (echo, then sync)
	o=$(rc_part ota) || return 1
	rc_spl_ok ota || { echo "ota partition doesn't match the SPL table" >&2; return 1; }
	if [ "$1" = B ]; then echo ota:kernel2 > "$o"; else echo ota:kernel > "$o"; fi
	sync
	[ "$(rc_flag_slot)" = "$1" ]
}

# Whose SPL the disk's first MiB holds (0x4400-0xA3FF), as the main OS's
# boot_loader (slot.sh): "kiln" (Kiln's SPL, its KILNCLK record),
# "flashforge" (its U-Boot SPL 2013.07 banner), else "unknown". AD5X_DISK
# overrides the disk (tests). With Kiln's SPL no Flashforge kernel goes
# into a slot; Flashforge's SPL goes back only over its own 5.10.
rc_boot_loader() {
	rcb_d=${AD5X_DISK:-$(rc_disk)} || { echo unknown; return 0; }
	rcb_s=$(dd if="$rcb_d" bs=512 skip=34 count=48 2>/dev/null |
		tr -c ' -~' '\n' | grep -e 'KILNCLK' -e '^U-Boot SPL 2013\.07' | head -n 1)
	case "$rcb_s" in
	*KILNCLK*) echo kiln ;;
	"U-Boot SPL 2013.07"*) echo flashforge ;;
	*) echo unknown ;;
	esac
}
# rc_uimage_name FILE...: the name in the uImage header the files start
# with (ih_name, NULs dropped); empty without a uImage
rc_uimage_name() {
	[ "$(cat "$@" 2>/dev/null | head -c 4 | od -An -t x1 | tr -d ' \n')" = 27051956 ] || return 0
	cat "$@" 2>/dev/null | head -c 64 | tail -c 32 | tr -d '\000'
}
# rc_kernel_kind FILE...: "kiln" (Kiln's 6.6, "Linux-6.6-ad5x"), "stock"
# (Flashforge's "Linux-5.10..."), "uboot" ("Kiln U-Boot"), "other", or
# "none" without a uImage header
rc_kernel_kind() {
	rck_n=$(rc_uimage_name "$@")
	case "$rck_n" in
	'') echo none ;;
	Linux-6.6-ad5x*) echo kiln ;;
	Linux-5.10*) echo stock ;;
	"Kiln U-Boot"*) echo uboot ;;
	*) echo other ;;
	esac
}

# Kiln's U-Boot started this system (it adds ad5x.uboot=1; Flashforge's
# SPL and Kiln's SPL alone don't)
rc_uboot() {
	case " $(cat "$AD5X_CMDLINE" 2>/dev/null) " in *" ad5x.uboot=1 "*) return 0 ;; esac
	return 1
}
# rc_uboot_fresh WHY: with Kiln's U-Boot, the main OS's next start is a
# fresh one (u-boot/README.md, "Boot rules"): U-Boot's state and records
# sectors in ota (0x90000, 0x90200: unconfirmed starts, the kernels it
# found failed) zeroed, synced and read back, and S00ad5x-kernel's
# failure records on /data (kernel/failed, failed-mainline, which U-Boot
# reads too) dropped, each with a line in kernel/history (the last
# fallback's reason as well). Without that, a 6.6 recorded as failed
# would send every start back here: U-Boot has no other kernel for the
# main OS, and the release string is the same in every build. Prints one
# line (nothing without ad5x.uboot=1); 1 when the sectors don't read back
# as zeros.
rc_uboot_fresh() {
	rc_uboot || return 0
	rcu_o=$(rc_part ota) || { echo "U-Boot's state NOT cleared: no ota partition"; return 1; }
	rcu_k=$AD5X_DATA/ad5x/kernel
	rcu_r=$(dd if="$rcu_o" bs=512 skip=1153 count=1 2>/dev/null | tr '\000' '\n' |
		sed -n 's/^reason //p' | head -n 1)
	if [ -d "$rcu_k" ]; then
		[ -n "$rcu_r" ] && [ "$rcu_r" != - ] &&
			echo "recovery OS: U-Boot's last fallback was: $rcu_r; records cleared ($1)" >> "$rcu_k/history"
		for rcu_f in failed failed-mainline; do
			[ -f "$rcu_k/$rcu_f" ] || continue
			echo "recovery OS: record $rcu_f ($(sed -n 1p "$rcu_k/$rcu_f")) cleared ($1)" >> "$rcu_k/history"
			rm -f "$rcu_k/$rcu_f"
		done
	fi
	rcu_bad=
	dd if=/dev/zero of="$rcu_o" bs=512 seek=1152 count=2 conv=fsync,notrunc 2>/dev/null || rcu_bad="the write failed"
	rc_drop_caches
	rcu_h=$(dd if="$rcu_o" bs=512 skip=1152 count=2 2>/dev/null | od -An -v -t x1 | tr -d ' \n')
	if [ -z "$rcu_bad" ] && { [ ${#rcu_h} != 2048 ] || [ -n "$(printf %s "$rcu_h" | tr -d 0)" ]; }; then
		rcu_bad="they don't read back as zeros"
	fi
	if [ -n "$rcu_bad" ]; then
		echo "U-Boot's state and records NOT cleared ($rcu_bad): the main OS may fall back here again"
		return 1
	fi
	echo "U-Boot's state and records cleared ($1): the main OS starts fresh"
}

rc_drop_caches() { sync; { echo 3 > /proc/sys/vm/drop_caches; } 2>/dev/null; true; }
# sha256 of the first SIZE bytes of a file or device
rc_sha() { head -c "$2" "$1" | sha256sum | cut -d' ' -f1; }
rc_fsize() { wc -c < "$1" | tr -d ' '; }

# What a rootfs partition holds: "ad5x <release>", "recovery <release>",
# "stock", "empty" (no squashfs) or "unknown" (squashfs, not mountable here)
rc_slot_holds() {
	dev=$(rc_part "$1") || { echo unknown; return; }
	[ "$(head -c 4 "$dev" 2>/dev/null)" = hsqs ] || { echo empty; return; }
	m=$AD5X_RUN/inspect.$$
	mkdir -p "$m"
	if ! mount -t squashfs -o ro "$dev" "$m" 2>/dev/null; then
		rmdir "$m"; echo unknown; return
	fi
	if [ -f "$m/etc/ad5x-recovery" ]; then echo "recovery $(cat "$m/etc/ad5x-release" 2>/dev/null)"
	elif [ -f "$m/etc/ad5x-release" ]; then echo "ad5x $(cat "$m/etc/ad5x-release")"
	elif [ -d "$m/usr/prog" ] || [ -f "$m/etc/ota_bin/ota_local_method.sh" ]; then echo stock
	else echo unknown
	fi
	umount "$m"; rmdir "$m"
}

# Bytes used by a squashfs (superblock bytes_used, offset 40, 8 bytes LE)
rc_squashfs_used() { od -An -t u8 -j 40 -N 8 "$1" | tr -d ' '; }
# uImage (legacy) total length: 64-byte header + ih_size (big endian, at 12)
rc_uimage_len() {
	[ "$(od -An -t x1 -N 4 "$1" | tr -d ' \n')" = 27051956 ] || return 1
	echo $(( 0x$(od -An -t x1 -j 12 -N 4 "$1" | tr -d ' \n') + 64 ))
}

# USB sticks: mounted at /run/ad5x/usb/<dev> by ad5x-usb mount
RC_USB=$AD5X_RUN/usb
rc_usb_mounts() {
	awk -v p="$RC_USB/" 'index($2, p) == 1 { print $2 }' "$AD5X_MOUNTS"
}
