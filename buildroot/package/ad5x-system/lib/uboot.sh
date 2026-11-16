# Kiln OS: Kiln's U-Boot's two sectors in the "ota" partition (sourced,
# after slot.sh; main OS only). U-Boot (u-boot/README.md, "ota layout";
# bootlogic.c) keeps there, as text:
#   0x90000 (sector 1152)  state: the main OS's unconfirmed starts. U-Boot
#                          writes it before each start of the main OS
#                          ("tries N", "kernel 66|73|stock", "release R");
#                          all zeros means none. S99ad5x-booted zeroes it
#                          once a start has finished (uboot_confirm).
#   0x90200 (sector 1153)  records: the kernels U-Boot found failed
#                          ("failed-own", "failed-mainline"), "fallbacks N"
#                          and "reason" of the last fallback. Kept until
#                          "ad5x-kernel retry" zeroes it.
# Each: "kiln-uboot-state 1" / "kiln-uboot-records 1", "key value" lines,
# then "crc32 XXXXXXXX" (zlib CRC-32 of every byte before that line), NUL
# padded. A sector that doesn't parse or has a wrong CRC counts as empty
# for U-Boot, and so here.
# shellcheck disable=SC2034 # used by the scripts that source this
UBOOT_STATE=1152
UBOOT_RECORDS=1153
UBOOT_STATE_MAGIC="kiln-uboot-state 1"
UBOOT_RECORDS_MAGIC="kiln-uboot-records 1"

# uboot_started: Kiln's U-Boot started this boot (it adds ad5x.uboot=1;
# neither SPL nor S00ad5x-kernel's chainload does)
uboot_started() {
	case " $(cat /proc/cmdline 2>/dev/null) " in *" ad5x.uboot=1 "*) return 0 ;; esac
	return 1
}

# The kernel slots: under Kiln's boot loader no Flashforge kernel is left
# in them; under Flashforge's, 5.10 stays as stock has it.
#
# kiln_slot_kernel [LIB]: with Kiln's SPL in the first MiB (boot_loader
# kiln, lib/slot.sh), the kernel both slots (p1 and p3) are to hold: this
# system's own 6.6 (LIB/kernel66/xImage), a whole uImage named as Kiln's
# 6.6, when it is the kernel running now (it has just started this
# system), or, on 7.3, when neither U-Boot's records nor S00's name its
# release as failed. Prints its path; 1 and nothing otherwise (then the
# slots are left as they are, never given kernel2's kernel). Who started
# the kernel (U-Boot, Kiln's SPL alone, the chain) doesn't matter.
kiln_slot_kernel() {
	ksk=${1:-/usr/lib/ad5x}/kernel66
	[ "$(boot_loader)" = kiln ] || return 1
	kiln_kernel "$ksk/xImage" || return 1
	ksr=$(cat "$ksk/release" 2>/dev/null)
	[ -n "$ksr" ] || return 1
	case "$(uname -r)" in
	"$ksr") ;;
	5.10.*) return 1 ;;	# Flashforge's kernel runs: 6.6 didn't start
	*)
		ksx=$(uboot_text $UBOOT_RECORDS "$UBOOT_RECORDS_MAGIC") &&
			[ "$(uboot_val "$ksx" failed-own)" = "$ksr" ] && return 1
		[ "$(sed -n 1p "${AD5X_DATA:-/data}/ad5x/kernel/failed" 2>/dev/null)" = "$ksr" ] &&
			return 1 ;;
	esac
	echo "$ksk/xImage"
}
# slot_a_kernel_src [LIB]: the kernel slot A (p1) is to hold. Kiln's SPL:
# kiln_slot_kernel's 6.6, or nothing. Otherwise (Flashforge's SPL, or not
# known): slot B's kernel (kernel2), as the stock chain has it, but never
# Kiln's U-Boot nor Kiln's 6.6 from there (Flashforge's SPL needs its 5.10
# in p1 for the recovery OS). Sets SLOT_A_SRC and SLOT_A_LOADER (kiln,
# flashforge, unknown); 1 with SLOT_A_SRC empty: leave p1 as it is,
# SLOT_A_WHY says why. (Not for $(...): it sets variables.)
slot_a_kernel_src() {
	SLOT_A_SRC= SLOT_A_WHY= SLOT_A_LOADER=$(boot_loader)
	if [ "$SLOT_A_LOADER" = kiln ]; then
		SLOT_A_SRC=$(kiln_slot_kernel "$1") && return 0
		SLOT_A_WHY="Kiln's SPL is in place and this system has no 6.6 to put there (none whole, not running, or recorded as failed)"
		return 1
	fi
	sak=$(kernel_of B)
	if uimage_is_uboot "$sak"; then
		SLOT_A_WHY="kernel2 holds Kiln's U-Boot, not a kernel"
		return 1
	fi
	case "$(uimage_name "$sak")" in Linux-6.6-ad5x*)
		SLOT_A_WHY="kernel2 holds Kiln's 6.6, which Flashforge's SPL is not to start"
		return 1 ;;
	esac
	SLOT_A_SRC=$sak
}

# uboot_text SECTOR MAGIC: the sector's text, MAGIC line to crc32 line,
# when it parses as U-Boot's ad5x_*_parse() does: MAGIC first, then lines
# with a space, shorter than 192 bytes, ending in a crc32 line whose value
# is the CRC-32 of everything before it (gzip's trailer carries the same
# CRC, so BusyBox is enough). U-Boot's parser stops at the first NUL.
uboot_text() {
	o=$(part ota) || return 1
	t=$(dd if="$o" bs=512 skip="$1" count=1 2>/dev/null | tr '\000' '\n' | sed '/^$/,$d')
	[ "$(printf '%s\n' "$t" | head -n 1)" = "$2" ] || return 1
	printf '%s\n' "$t" | awk 'NR == 1 { next }
		length($0) >= 192 || index($0, " ") == 0 { exit }
		/^crc32 [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$/ { f = 1; exit }
		/^crc32 / { exit }
		END { exit !f }' || return 1
	c=$(printf '%s\n' "$t" | sed -n 's/^crc32 //p' | head -n 1)
	# shellcheck disable=SC2046 # four words, the CRC's bytes
	set -- $(printf '%s\n' "$t" | sed '/^crc32 /,$d' | gzip -c | tail -c 8 | head -c 4 | od -An -t x1)
	[ $# = 4 ] && [ "$4$3$2$1" = "$c" ] || return 1
	printf '%s\n' "$t" | sed '/^crc32 /q'
}
# uboot_head SECTOR: its first line, whatever its CRC (empty when none)
uboot_head() {
	o=$(part ota) || return 0
	dd if="$o" bs=512 skip="$1" count=1 2>/dev/null | tr '\000' '\n' | head -n 1
}
# uboot_val TEXT KEY: KEY's value in a sector's text
uboot_val() { printf '%s\n' "$1" | sed -n "s/^$2 //p" | head -n 1; }

# uboot_zero SECTOR: 0 when its 512 bytes read back as zeros (O_DIRECT
# when this dd has it, past the page cache; else a plain read), 1 when not,
# 2 when it can't be read. UBOOT_READ says how it was read.
uboot_zero() {
	o=$(part ota) || return 2
	UBOOT_READ=O_DIRECT
	h=$(dd if="$o" bs=512 skip="$1" count=1 iflag=direct 2>/dev/null | od -An -v -t x1 | tr -d ' \n')
	if [ ${#h} != 1024 ]; then
		UBOOT_READ="a plain read"
		h=$(dd if="$o" bs=512 skip="$1" count=1 2>/dev/null | od -An -v -t x1 | tr -d ' \n')
	fi
	[ ${#h} = 1024 ] || return 2
	[ -z "$(printf '%s' "$h" | tr -d 0)" ]
}

# uboot_clear SECTOR: zero it (synced) and read it back. Prints what
# happened; 1 when it isn't zero after that
uboot_clear() {
	uboot_zero "$1"
	case $? in
	0) echo "already empty"; return 0 ;;
	2) echo "can't read sector $1 of the ota partition"; return 1 ;;
	esac
	o=$(part ota)
	if ! dd if=/dev/zero of="$o" bs=512 seek="$1" count=1 conv=fsync,notrunc 2>/dev/null; then
		echo "writing zeros to sector $1 of $o failed"
		return 1
	fi
	if uboot_zero "$1"; then
		echo "cleared (read back as zeros, $UBOOT_READ)"
		return 0
	fi
	echo "sector $1 of $o doesn't read back as zeros after the write ($UBOOT_READ)"
	return 1
}

# uboot_records_line TEXT: the records in one line, for logs
uboot_records_line() {
	echo "failed own kernel $(uboot_val "$1" failed-own), failed mainline $(uboot_val "$1" failed-mainline), $(uboot_val "$1" fallbacks) fallback(s); last: $(uboot_val "$1" reason)"
}
