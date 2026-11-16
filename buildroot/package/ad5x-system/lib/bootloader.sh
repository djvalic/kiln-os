# Kiln OS: Kiln's own boot loader (Kiln's SPL and U-Boot proper, u-boot/)
# in the eMMC's first MiB (sourced, after slot.sh: uimage_ok,
# uimage_data_ok). Shared by the recovery OS's ad5x-bootloader-install and
# ad5x-return-stock, and the main OS's S99ad5x-booted (the install record
# only). docs/own-boot-loader.md.
#
# The layout, the first MiB an install leads to and the write order are
# the bench tools' (tools/bench/ad5x-spl-flash and ad5x-uboot-flash,
# tools/bench/README.md steps 3-5), which wrote them on a printer:
#   0x0004-0x0007  the boot ROM's SPL length (LBA 0, the INGE block)
#   0x4400-0xA3FF  the SPL range (sectors 34-81): the SPL image, then 0xFF
#   0xA400-...     U-Boot proper (sector 82 on): a U-Boot uImage, which
#                  Kiln's SPL starts only when its header and data CRCs
#                  check; Flashforge's U-Boot there is raw (no uImage)
# Nothing else of the first MiB (the GPT at 0x200-0x43FF above all) is
# ever written.
#
# Write order (README.md, "Write order"): the SPL's header sector (34)
# zeroed first, then sectors 35-81, then the length at 0x4, then sector 34
# last: the boot ROM checks only that header, and without one it goes to
# USB boot mode by itself (djvalic/kiln-os#68), so no moment leaves a
# header in front of an SPL body cut short. U-Boot proper:
# its body first, its header sector last, so until the very end 0xA400
# holds no uImage magic and Kiln's SPL boots the flagged slot; taking it
# out: the header sector first. Every range is read back past the caches
# (O_DIRECT where dd has it).
#
# Functions set BL_WHY when they fail; bl_put_* print what they write
# through say() when the caller has one (else echo).

# shellcheck disable=SC2034 # used by the scripts that source this
BL_MIB=1048576
BL_LEN_OFF=4
BL_SPL_OFF=17408 BL_SPL_LBA=34 BL_SPL_SECTORS=48 BL_SPL_END=41984
BL_UB_OFF=41984 BL_UB_LBA=82
BL_UB_LOAD=80100000				# U-Boot proper's load address and entry
BL_DDR_OFF=34872 BL_DDR_LEN=188			# the stock SPL's DDR3 table (W634GU6QG-11)
BL_OTA_LBA=1024 BL_OTA_N=130			# ota 0x80000-0x903FF: U-Boot's settings, state, records
BL_DATA=${AD5X_DATA:-/data}/ad5x/bootloader	# the install record (state) and its log
BL_STATE=$BL_DATA/state
BL_FILES=${AD5X_BOOTLOADER_FILES:-/usr/share/ad5x/bootloader}	# spl-mmc.img, u-boot-emmc.img, SHA256SUMS

# The boards Kiln's SPL and U-Boot are known to fit (djvalic/kiln-os#68):
# one line each, "SPL DDR note", SPL and DDR being the first 16 hex digits
# of the sha256 of the stock SPL range (sectors 34-81, bytes 0x4480-0x4483
# read as zeros: bl_fp_spl) and of the stock SPL's DDR3 table (188 bytes
# at 34872), as the fingerprint snippet in docs/own-boot-loader.md prints
# them. Kiln's SPL carries that DDR table and the stock SPL's clock
# values byte for byte, so it is only for a board built the same way.
BL_ALLOWLIST="f7b9d763c1e83af8 61b7ee909c0baa50 W634GU6QG-11; two boards known (djvalic's, where Kiln's boot loader was proven; alexshev86's, the same by its dump)"
# tests only (tools/test_bootloader_install.sh): another list
[ -n "${AD5X_TEST:-}" ] && [ -n "${AD5X_TEST_ALLOWLIST:-}" ] && BL_ALLOWLIST=$AD5X_TEST_ALLOWLIST

bl_say() { if command -v say >/dev/null 2>&1; then say "$@"; else echo "$@"; fi; }
bl_fsize() { wc -c < "$1" | tr -d ' '; }
bl_le32() { od -An -t u4 -j "$2" -N 4 "$1" 2>/dev/null | tr -d ' '; }
# bl_h FILE BS SKIP COUNT: the first 16 hex digits of the sha256 of a range
bl_h() { dd if="$1" bs="$2" skip="$3" count="$4" 2>/dev/null | sha256sum | cut -c1-16; }
bl_drop_caches() { sync; { echo 3 > /proc/sys/vm/drop_caches; } 2>/dev/null; return 0; }

# bl_read DEV LBA COUNT OUT: sectors of DEV as the eMMC has them (caches
# dropped, then O_DIRECT; a plain read when dd has no iflag=direct)
bl_read() {
	bl_drop_caches
	rm -f "$4"
	dd if="$1" of="$4" bs=512 skip="$2" count="$3" iflag=direct 2>/dev/null &&
		[ "$(bl_fsize "$4")" = $(($3 * 512)) ] && return 0
	rm -f "$4"
	dd if="$1" of="$4" bs=512 skip="$2" count="$3" 2>/dev/null &&
		[ "$(bl_fsize "$4")" = $(($3 * 512)) ]
}

# bl_banner FILE (a first MiB): its SPL's "U-Boot SPL ..." banner
bl_banner() {
	tail -c +$((BL_SPL_OFF + 1)) "$1" 2>/dev/null | head -c $((BL_SPL_END - BL_SPL_OFF)) |
		tr -c ' -~' '\n' | grep 'U-Boot SPL' | head -n 1
}
# bl_loader FILE (a first MiB): whose SPL it holds, as slot.sh's
# boot_loader: kiln (its KILNCLK record), flashforge (U-Boot SPL 2013.07)
# or unknown
bl_loader() {
	case "$(tail -c +$((BL_SPL_OFF + 1)) "$1" 2>/dev/null | head -c $((BL_SPL_END - BL_SPL_OFF)) |
		tr -c ' -~' '\n' | grep -e 'KILNCLK' -e '^U-Boot SPL 2013\.07' | head -n 1)" in
	*KILNCLK*) echo kiln ;;
	"U-Boot SPL 2013.07"*) echo flashforge ;;
	*) echo unknown ;;
	esac
}
# bl_ddr_table FILE (a first MiB): hex of the SPL's DDR3 table, 188 bytes
# from its name W634GU6QG-11 (Kiln's SPL carries the stock table byte for
# byte, elsewhere in its range); empty when not found
bl_ddr_table() {
	tail -c +$((BL_SPL_OFF + 1)) "$1" 2>/dev/null | head -c $((BL_SPL_END - BL_SPL_OFF)) |
		od -An -v -t x1 | tr -d ' \n' |
		awk '{ i = index($0, "5736333447553651472d3131")
		       if (i > 0 && i % 2 == 1) print substr($0, i, 376) }'
}

# bl_fp_spl FILE: the SPL part of the fingerprint: the first 16 hex digits
# of the sha256 of the SPL range (0x4400-0xA3FF) with bytes 0x4480-0x4483
# read as zeros. Ingenic's USBCloner puts its DDR type there (0x00840084)
# whenever it writes from block 0, so a board restored over USB has it;
# neither SPL reads those bytes (#68). Where they are zero, as on a board
# never written by USBCloner, this is the plain range's hash.
bl_fp_spl() {
	{ dd if="$1" bs=128 skip=136 count=1 2>/dev/null	# 0x4400-0x447F
	  printf '\000\000\000\000'				# 0x4480-0x4483
	  dd if="$1" bs=4 skip=4385 count=95 2>/dev/null	# 0x4484-0x45FF
	  dd if="$1" bs=512 skip=35 count=47 2>/dev/null	# sectors 35-81
	} | sha256sum | cut -c1-16
}
# bl_stamp_only A B (first MiBs): they differ, and only in 0x4480-0x4483,
# where USBCloner stamps its DDR type (bl_fp_spl): one of them was written
# back over USB since the other was read
bl_stamp_only() {
	cmp -l "$1" "$2" 2>/dev/null | awk '{ o = $1 - 1; if (o < 17536 || o > 17539) bad = 1 }
		END { exit (bad || NR == 0) }'
}
# bl_fingerprint FILE: the stock boot loader's fingerprint lines as the
# snippet in docs/own-boot-loader.md (and #68) prints them (length, spl,
# uboot, ddr, banner). Sets BL_FP_SPL and BL_FP_DDR. Meaningful on a
# first MiB with Flashforge's SPL (the disk before Kiln's, or the saved
# boot.img)
bl_fingerprint() {
	BL_FP_SPL=$(bl_fp_spl "$1")
	BL_FP_DDR=$(bl_h "$1" 1 $BL_DDR_OFF $BL_DDR_LEN)
	echo "length: $(bl_le32 "$1" $BL_LEN_OFF)"
	echo "spl:    $BL_FP_SPL"
	echo "uboot:  $(bl_h "$1" 512 $BL_UB_LBA $((2048 - BL_UB_LBA)))"
	echo "ddr:    $BL_FP_DDR $(dd if="$1" bs=1 skip=$BL_DDR_OFF count=12 2>/dev/null | tr -c ' -~' '?')"
	echo "banner: $(dd if="$1" bs=512 skip=$BL_SPL_LBA count=$BL_SPL_SECTORS 2>/dev/null |
		tr -cs 'A-Za-z0-9 :().-' '\n' | grep -m1 'U-Boot SPL')"
}
# bl_allowed SPL DDR: on the allowlist; BL_BOARD gets its note
bl_allowed() {
	BL_BOARD=$(printf '%s\n' "$BL_ALLOWLIST" | awk -v s="$1" -v d="$2" '
		$1 == s && $2 == d { $1 = ""; $2 = ""; sub(/^  /, ""); print; f = 1; exit }
		END { exit !f }') || { BL_BOARD=; return 1; }
}

# bl_spl_image_ok FILE: an SPL image for the eMMC (spl-mmc.img, u-boot/
# build.sh): LPSM, its block count x 512 = its size, at most 24 KiB, the
# INGE params copy at 0x100 with the same length, Kiln's KILNCLK record,
# not the USB image (KILNUSB1 at 0x7F0) nor the chainload test SPL
bl_spl_image_ok() {
	BL_WHY=
	bs=$(bl_fsize "$1" 2>/dev/null) || { BL_WHY="can't read it"; return 1; }
	[ "$(head -c 4 "$1")" = LPSM ] || { BL_WHY="no LPSM magic"; return 1; }
	bc=$(bl_le32 "$1" 4)
	[ "$bs" -gt 2048 ] && [ "$bs" -le $((BL_SPL_END - BL_SPL_OFF)) ] && [ $((bc * 512)) = "$bs" ] ||
		{ BL_WHY="$bs bytes, $bc blocks: not a whole SPL image of at most 24 KiB"; return 1; }
	[ "$(tail -c +257 "$1" | head -c 4)" = INGE ] && [ "$(bl_le32 "$1" 260)" = "$bs" ] ||
		{ BL_WHY="no INGE params copy at 0x100 with its length"; return 1; }
	[ "$(tail -c +$((0x7F0 + 1)) "$1" | head -c 8)" != KILNUSB1 ] ||
		{ BL_WHY="this is the USB image (spl-usb.bin), not the eMMC one"; return 1; }
	grep -q 'KILN-SPL-CHAINLOAD-TEST-ONLY' "$1" && { BL_WHY="the chainload test SPL"; return 1; }
	tr -c ' -~' '\n' < "$1" | grep -q KILNCLK || { BL_WHY="no KILNCLK record (not Kiln's SPL)"; return 1; }
	return 0
}

bl_ufield() { od -An -v -t x1 -j "$2" -N 4 "$1" 2>/dev/null | tr -d ' \n'; }
bl_ubyte() { od -An -v -t u1 -j "$2" -N 1 "$1" 2>/dev/null | tr -d ' '; }
# bl_uboot_image_ok FILE MAX: a U-Boot uImage Kiln's SPL starts
# (spl_load_uimage: magic, header and data CRCs, MIPS, OS U-Boot) and
# Kiln's (load = entry 0x80100000, "Kiln U-Boot"), header + ih_size
# within MAX bytes (as ad5x-uboot-flash's kiln_uimage). BL_UB_SIZE: header
# + data
bl_uboot_image_ok() {
	BL_WHY=
	[ "$(bl_ufield "$1" 0)" = 27051956 ] || { BL_WHY="no uImage magic"; return 1; }
	BL_UB_SIZE=$((0x$(bl_ufield "$1" 12) + 64))
	uimage_ok "$1" || { BL_WHY="header CRC wrong"; return 1; }
	[ "$(bl_ubyte "$1" 29)" = 5 ] && [ "$(bl_ubyte "$1" 28)" = 17 ] ||
		{ BL_WHY="not a MIPS U-Boot uImage (OS $(bl_ubyte "$1" 28), arch $(bl_ubyte "$1" 29))"; return 1; }
	[ "$(bl_ufield "$1" 16)" = $BL_UB_LOAD ] && [ "$(bl_ufield "$1" 20)" = $BL_UB_LOAD ] ||
		{ BL_WHY="load 0x$(bl_ufield "$1" 16), entry 0x$(bl_ufield "$1" 20): not 0x$BL_UB_LOAD"; return 1; }
	[ "$BL_UB_SIZE" -le "$2" ] || { BL_WHY="$BL_UB_SIZE bytes, more than the $2 it may take"; return 1; }
	case "$(tail -c +33 "$1" 2>/dev/null | head -c 12)" in
	"Kiln U-Boot ") ;;
	*) BL_WHY="its name isn't Kiln U-Boot"; return 1 ;;
	esac
	uimage_data_ok "$1" || { BL_WHY="data CRC wrong (or cut short)"; return 1; }
}

# bl_compose BOOT SPL UBOOT OUT: the first MiB an install leads to, made
# from this printer's saved one (boot.img, Flashforge's SPL) as u-boot/
# tools/ad5x_spl_image.py's first-mib and uboot-mib make it: the SPL range
# 0xFF, the SPL image over it, the unit's params copy at 0x4500 kept with
# the image's length, the length at 0x4 the image's; U-Boot's uImage at
# 0xA400 (the rest of its last sector boot.img's). Nothing else changes.
bl_compose() {
	BL_WHY=
	cp "$1" "$4" || { BL_WHY="can't copy ${1##*/}"; return 1; }
	head -c $((BL_SPL_END - BL_SPL_OFF)) /dev/zero | tr '\000' '\377' |
		dd of="$4" bs=512 seek=$BL_SPL_LBA conv=notrunc 2>/dev/null &&
	dd if="$2" of="$4" bs=512 seek=$BL_SPL_LBA conv=notrunc 2>/dev/null &&
	dd if="$1" of="$4" bs=1 skip=$((BL_SPL_OFF + 256)) seek=$((BL_SPL_OFF + 256)) count=256 conv=notrunc 2>/dev/null &&
	dd if="$2" of="$4" bs=1 skip=260 seek=$((BL_SPL_OFF + 260)) count=4 conv=notrunc 2>/dev/null &&
	dd if="$2" of="$4" bs=1 skip=260 seek=$BL_LEN_OFF count=4 conv=notrunc 2>/dev/null &&
	dd if="$3" of="$4" bs=512 seek=$BL_UB_LBA conv=notrunc 2>/dev/null &&
	[ "$(bl_fsize "$4")" = $BL_MIB ] || { BL_WHY="putting the images together failed"; return 1; }
}

# bl_spl_class CUR BOOT FINAL: how 0-0xA3FF of CUR stands: "final" (FINAL's),
# "stock" (BOOT's), "partial" (differs from BOOT only in 0x4-0x7 and the
# SPL range: a write cut short, or another Kiln SPL), "other OFFSET" (the
# first byte outside them that differs)
bl_spl_class() {
	head -c $BL_UB_OFF "$1" > "$1.spl" 2>/dev/null
	if head -c $BL_UB_OFF "$3" 2>/dev/null | cmp -s - "$1.spl"; then echo final
	else
		head -c $BL_UB_OFF "$2" 2>/dev/null | cmp -l - "$1.spl" 2>/dev/null |
			awk -v s=$BL_SPL_OFF '{ o = $1 - 1
				if ((o >= 4 && o <= 7) || o >= s) { n++; next }
				if (f == "") f = o }
				END { if (NR == 0) print "stock"; else if (f != "") print "other " f; else print "partial" }'
	fi
	rm -f "$1.spl"
}
# bl_ub_class CUR BOOT FINAL: how 0xA400-1 MiB of CUR stands: "final",
# "stock", "kiln" (another whole Kiln U-Boot: another build's) or
# "partial" (neither: a write cut short)
bl_ub_class() {
	tail -c +$((BL_UB_OFF + 1)) "$1" > "$1.ub" 2>/dev/null
	if tail -c +$((BL_UB_OFF + 1)) "$3" | cmp -s - "$1.ub"; then echo final
	elif tail -c +$((BL_UB_OFF + 1)) "$2" | cmp -s - "$1.ub"; then echo stock
	elif bl_uboot_image_ok "$1.ub" $((BL_MIB - BL_UB_OFF)); then echo kiln
	else echo partial; fi
	rm -f "$1.ub"
}

# bl_dd FROM DEV DD-ARGS...: one dd to the device, synced, said
bl_dd() {
	bdf=$1 bdd=$2; shift 2
	bl_say "  dd if=${bdf##*/} of=$bdd $* conv=notrunc,fsync"
	dd if="$bdf" of="$bdd" "$@" conv=notrunc,fsync 2>/dev/null || { bl_say "  dd failed"; return 1; }
}
# bl_same_range DEV FROM OFF LEN: DEV's bytes OFF..OFF+LEN-1 (whole
# sectors, past the caches) are FROM's
bl_same_range() {
	bsl=$(($3 / 512)) bsn=$((($3 + $4 + 511) / 512 - $3 / 512))
	bl_read "$1" $bsl $bsn "${BL_TMP:-/tmp}/bl-rb.$$" || return 1
	cmp -s -n "$4" "${BL_TMP:-/tmp}/bl-rb.$$" "$2" $(($3 - bsl * 512)) "$3"
	bsr=$?
	rm -f "${BL_TMP:-/tmp}/bl-rb.$$"
	return $bsr
}

# bl_put_spl FROM DISK: FROM's SPL range and length field on the disk, the
# SPL's header sector last, each read back; 0 when 0-0xA3FF of the disk
# then reads back as FROM's. The boot ROM checks only the header in sector
# 34 (LPSM and the block count, no checksum), so: sector 34 zeroed first
# (from then on the boot ROM finds no SPL and goes to USB boot mode by
# itself, #68), then sectors 35-81, then the length at 0x4 (with no header
# in place its value doesn't matter; in place before and after, it covers
# the SPL that is there), then sector 34. A power cut at any moment leaves
# the old SPL whole, or no header (USB boot mode, the J28 restore), or the
# new SPL whole: never a header in front of a body cut short.
bl_put_spl() {
	bl_read "$2" 0 1 "${BL_TMP:-/tmp}/bl-s0.$$" || return 1
	bln=$(bl_le32 "${BL_TMP:-/tmp}/bl-s0.$$" $BL_LEN_OFF) blw=$(bl_le32 "$1" $BL_LEN_OFF)
	rm -f "${BL_TMP:-/tmp}/bl-s0.$$"
	bl_say "  sector 34 (the SPL's header, 0x4400-0x45FF) zeroed: until it is written last, the boot ROM finds no SPL"
	bl_dd /dev/zero "$2" bs=512 seek=$BL_SPL_LBA count=1 &&
		bl_read "$2" $BL_SPL_LBA 1 "${BL_TMP:-/tmp}/bl-h0.$$" &&
		[ -z "$(tr -d '\000' < "${BL_TMP:-/tmp}/bl-h0.$$" | head -c 1)" ] || { rm -f "${BL_TMP:-/tmp}/bl-h0.$$"; return 1; }
	rm -f "${BL_TMP:-/tmp}/bl-h0.$$"
	bl_say "  bytes 0x4600-0xA3FF (the SPL's body) from ${1##*/} ('$(bl_banner "$1")')"
	bl_dd "$1" "$2" bs=512 skip=$((BL_SPL_LBA + 1)) seek=$((BL_SPL_LBA + 1)) count=$((BL_SPL_SECTORS - 1)) &&
		bl_same_range "$2" "$1" $((BL_SPL_OFF + 512)) $((BL_SPL_END - BL_SPL_OFF - 512)) || return 1
	bl_say "  bytes 0x4-0x7 (the boot ROM's length) $bln -> $blw"
	bl_dd "$1" "$2" bs=4 skip=1 seek=1 count=1 &&
		bl_same_range "$2" "$1" $BL_LEN_OFF 4 || return 1
	bl_say "  sector 34 (the SPL's header) from ${1##*/}, last"
	bl_dd "$1" "$2" bs=512 skip=$BL_SPL_LBA seek=$BL_SPL_LBA count=1 &&
		bl_same_range "$2" "$1" $BL_SPL_OFF 512 || return 1
	bl_same_range "$2" "$1" 0 $BL_UB_OFF
}

# bl_put_uboot FROM DISK END: FROM's sectors from 0xA400 to END (bytes,
# exclusive, a sector boundary) on the disk: the body first, the header
# sector last, each read back; 0 when the range then reads back as FROM's
bl_put_uboot() {
	bln=$((($3 - BL_UB_OFF) / 512))
	if [ "$bln" -gt 1 ]; then
		bl_dd "$1" "$2" bs=512 skip=$((BL_UB_LBA + 1)) seek=$((BL_UB_LBA + 1)) count=$((bln - 1)) &&
			bl_same_range "$2" "$1" $((BL_UB_OFF + 512)) $(($3 - BL_UB_OFF - 512)) || return 1
	fi
	bl_dd "$1" "$2" bs=512 skip=$BL_UB_LBA seek=$BL_UB_LBA count=1 &&
		bl_same_range "$2" "$1" $BL_UB_OFF 512 &&
		bl_same_range "$2" "$1" $BL_UB_OFF $(($3 - BL_UB_OFF))
}
# bl_unput_uboot FROM DISK END: FROM's bytes (boot.img's: Flashforge's
# unused U-Boot) back from 0xA400 to END: the header sector first (from
# then on Kiln's SPL finds no U-Boot there), then the rest
bl_unput_uboot() {
	bln=$((($3 - BL_UB_OFF) / 512))
	bl_dd "$1" "$2" bs=512 skip=$BL_UB_LBA seek=$BL_UB_LBA count=1 &&
		bl_same_range "$2" "$1" $BL_UB_OFF 512 || return 1
	if [ "$bln" -gt 1 ]; then
		bl_dd "$1" "$2" bs=512 skip=$((BL_UB_LBA + 1)) seek=$((BL_UB_LBA + 1)) count=$((bln - 1)) || return 1
	fi
	bl_same_range "$2" "$1" $BL_UB_OFF $(($3 - BL_UB_OFF))
}

# bl_put_kernel FILE DEV: a kernel uImage into a slot: 4 KiB of zeros, the
# rest, the first 4 KiB (the header last: a copy cut short leaves no
# header, which both SPLs refuse), read back
bl_put_kernel() {
	blk=$(bl_fsize "$1")
	bl_say "  $1 -> $2: 4 KiB of zeros, the rest, the first 4 KiB (the uImage header last), $blk bytes"
	dd if=/dev/zero of="$2" bs=4096 count=1 conv=notrunc,fsync 2>/dev/null &&
		dd if="$1" of="$2" bs=4096 skip=1 seek=1 conv=notrunc,fsync 2>/dev/null &&
		sync && dd if="$1" of="$2" bs=4096 count=1 conv=notrunc,fsync 2>/dev/null ||
		{ bl_say "  dd failed"; return 1; }
	bl_drop_caches
	cmp -s -n "$blk" "$1" "$2"
}

# The install record ($BL_STATE, key=value): state=started|installed|
# verified|unverified (ad5x-bootloader-install), removed (ad5x-return-stock
# took Kiln's U-Boot out), and what was noted with it
bl_stval() { sed -n "s/^$1=//p" "$BL_STATE" 2>/dev/null | head -n 1; }
bl_stset() {	# KEY VALUE (synced)
	mkdir -p "$BL_DATA" 2>/dev/null
	{ grep -v "^$1=" "$BL_STATE" 2>/dev/null; echo "$1=$2"; } > "$BL_STATE.new" &&
		mv -f "$BL_STATE.new" "$BL_STATE" && sync
}
# bl_note_main_start: the main OS's S99ad5x-booted, on a start by Kiln's
# U-Boot (ad5x.uboot=1): the first such start after an install goes into
# the record (the recovery screen shows it). Nothing without a record.
bl_note_main_start() {
	case "$(bl_stval state)" in installed|verified|unverified) ;; *) return 0 ;; esac
	[ -n "$(bl_stval main_start)" ] && return 0
	bl_stset main_start "$(date '+%Y-%m-%d %H:%M:%S'), kernel $(uname -r)"
}
