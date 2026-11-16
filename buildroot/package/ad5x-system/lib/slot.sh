# Kiln OS: A/B slot helpers (sourced). The boot loader picks the slot
# from the ota partition: "ota:kernel2" boots kernel2 + rootfs2 (slot B),
# anything else kernel + rootfs (slot A). See docs/boot-slots.md.
#
# Sets SLOT/OTHER (A or B, empty when not booted as an installed system,
# e.g. in USB test mode) and provides part, flag_for, set_flag, read_flag,
# start_done.

part() {	# GPT name -> /dev path
	for u in /sys/class/block/*/uevent; do
		grep -qx "PARTNAME=$1" "$u" && { echo /dev/$(sed -n 's/^DEVNAME=//p' "$u"); return 0; }
	done
	return 1
}
flag_for() { [ "$1" = B ] && echo ota:kernel2 || echo ota:kernel; }
rootfs_of() { [ "$1" = B ] && part rootfs2 || part rootfs; }
kernel_of() { [ "$1" = B ] && part kernel2 || part kernel; }
set_flag() {	# slot
	echo "$(flag_for $1)" > "$(part ota)" && sync
}
read_flag() { head -c 11 "$(part ota)" | tr -d '\0\n'; }
# start_done: this boot's start-up has finished. S99ad5x-booted makes
# BOOTED_MARK (in /run: gone at every boot) after pointing the boot flag
# back at this slot; both are checked, as the flag alone doesn't tell:
# S01ad5x-tryboot leaves it on this slot when the other one can't start.
BOOTED_MARK=/run/ad5x-booted
start_done() { [ -f "$BOOTED_MARK" ] && [ "$(read_flag)" = "$(flag_for "$SLOT")" ]; }
# uimage_ok DEV: DEV starts with a legacy uImage header (magic 27051956)
# whose header CRC (CRC-32 of the 64 bytes with the CRC field zeroed, big
# endian at offset 4) is right. gzip's trailer carries that CRC-32 (little
# endian), so this needs nothing beyond BusyBox. The body is not checked.
uimage_ok() {
	uh=$(head -c 64 "$1" 2>/dev/null | od -An -v -t x1 | tr -d ' \n')
	[ ${#uh} = 128 ] || return 1
	case $uh in 27051956*) ;; *) return 1 ;; esac
	set -- $( { head -c 4 "$1"; printf '\000\000\000\000'; head -c 64 "$1" | tail -c 56; } |
		gzip -c | tail -c 8 | head -c 4 | od -An -t x1)
	[ $# = 4 ] && [ "$4$3$2$1" = "$(echo "$uh" | cut -c9-16)" ]
}
# uimage_data_ok DEV: uimage_ok, and the body (ih_size bytes after the
# header, size big endian at offset 12) has the header's data CRC (offset
# 24). Reads the whole kernel: for checks on request, not at boot.
uimage_data_ok() {
	uimage_ok "$1" || return 1
	us=$((0x$(echo "$uh" | cut -c25-32)))
	set -- $(tail -c +65 "$1" | head -c "$us" | gzip -c | tail -c 8 | od -An -t x1)
	# CRC-32, then the length mod 2^32 (both little endian)
	[ $# = 8 ] && [ "$4$3$2$1" = "$(echo "$uh" | cut -c49-56)" ] &&
		[ $((0x$8$7$6$5)) = "$us" ]
}
# uimage_is_uboot DEV: uimage_ok, and the uImage is Kiln's U-Boot proper
# (u-boot/build.sh: load address 0x80100000, U-Boot's own, or the name
# "Kiln U-Boot ..."), not a kernel: as u-boot-kernel-slot.img in kernel2
uimage_is_uboot() {
	uimage_ok "$1" || return 1
	[ "$(echo "$uh" | cut -c33-40)" = 80100000 ] && return 0
	case "$(head -c 64 "$1" | tail -c 32 | tr -d '\000')" in "Kiln U-Boot"*) return 0 ;; esac
	return 1
}
# uimage_name DEV: the uImage's name (ih_name, NULs dropped)
uimage_name() { head -c 64 "$1" 2>/dev/null | tail -c 32 | tr -d '\000'; }
# kiln_kernel DEV: a whole uImage (header and data CRCs) of Kiln's 6.6, as
# kernel-ingenic66/build.sh names it ("Linux-6.6-ad5x")
kiln_kernel() {
	uimage_data_ok "$1" || return 1
	case "$(uimage_name "$1")" in Linux-6.6-ad5x*) return 0 ;; esac
	return 1
}
# stock_kernel DEV: a whole uImage of Flashforge's 5.10 ("Linux-5.10...")
stock_kernel() {
	uimage_data_ok "$1" || return 1
	case "$(uimage_name "$1")" in Linux-5.10*) return 0 ;; esac
	return 1
}
# boot_loader: whose SPL the disk's first MiB holds (0x4400-0xA3FF):
# "kiln" (Kiln's SPL: its KILNCLK clock record, u-boot/ patch 0023),
# "flashforge" (the banner of its U-Boot SPL 2013.07), else "unknown".
# With Kiln's SPL no Flashforge kernel belongs in a slot (lib/uboot.sh,
# kiln_slot_kernel); only with Flashforge's SPL does 5.10 stay there.
boot_loader() {
	bl_r=$(part rootfs2) || { echo unknown; return 0; }
	bl_s=$(dd if="${bl_r%p[0-9]*}" bs=512 skip=34 count=48 2>/dev/null |
		tr -c ' -~' '\n' | grep -e 'KILNCLK' -e '^U-Boot SPL 2013\.07' | head -n 1)
	case "$bl_s" in
	*KILNCLK*) echo kiln ;;
	"U-Boot SPL 2013.07"*) echo flashforge ;;
	*) echo unknown ;;
	esac
}
# kernel_same SRC DEV: DEV holds SRC: a partition as a whole (cmp), a
# file in DEV's first bytes (a kernel partition is longer than its uImage)
kernel_same() {
	if [ -b "$1" ] || [ -c "$1" ]; then
		cmp -s "$1" "$2"
	else
		head -c "$(wc -c < "$1")" "$2" 2>/dev/null | cmp -s - "$1"
	fi
}

SLOT= OTHER=
# ad5x.noslot: a test boot of another kernel (kernel-ingenic66/chainload)
# that must not touch the boot flag.
if [ -z "$AD5X_USB" ] && [ -f /etc/ad5x-release ] &&
   ! grep -qw ad5x.noslot /proc/cmdline; then
	case "$(sed -n 's/.*root=\([^ ]*\).*/\1/p' /proc/cmdline)" in
	"$(part rootfs)"|PARTLABEL=rootfs) SLOT=A OTHER=B ;;
	"$(part rootfs2)"|PARTLABEL=rootfs2) SLOT=B OTHER=A ;;
	esac
fi
