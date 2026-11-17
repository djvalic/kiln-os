#!/usr/bin/env bash
# Build U-Boot and the SPL for the AD5X (Ingenic X2600) from the v$UVER
# release + patches/, and check them (u-boot/README.md).
#
#   u-boot/build.sh               build with the cross compiler found:
#                                 Buildroot's ($TOOLBIN/mipsel-linux-gcc)
#                                 or Debian's (mipsel-linux-gnu-gcc)
#   u-boot/build.sh --container   the same in a podman (or docker)
#                                 container from u-boot/Containerfile
#   USRC=DIR u-boot/build.sh      build a development tree as it is
#   FIRST_MIB_DUMP=FILE           also make a first-MiB candidate from that
#                                 unit's dump (read only) and check it;
#   FIRST_MIB_ALSO="FILE ..."     other units' dumps to compare it with
#   JOBS=8, WORK=DIR, O=DIR       parallelism, work and output directories
#
# Output ($O/dist):
#   u-boot.bin             U-Boot proper, linked at 0x80100000
#   u-boot-emmc.img        it as a U-Boot uImage, for eMMC 0xA400 (Kiln's SPL)
#   u-boot-kernel-slot.img it as a Linux uImage (load = entry 0x80100000),
#                          for a kernel slot behind either SPL
#   spl-mmc.img            the SPL as the boot ROM loads it (header + code)
#   spl-usb.bin            the same with the USB tag, for the boot ROM's USB
#                          mode (tools/ad5x_usbboot.py run-spl; USB-BOOT.md)
#   spl-usb2.bin           the same tagged for stage 1 only: DDR, then U-Boot
#                          proper over USB, which offers the eMMC as a USB
#                          disk (ad5x_usbboot.py run-uboot; USB-BOOT.md)
#   spl-chainload.bin      the chainload-test SPL (never for the eMMC)
#   first-mib.img          with FIRST_MIB_DUMP: the unit's first MiB with
#                          the new SPL (a file; nothing writes a device)
#   first-mib-plan.json    with FIRST_MIB_DUMP: the only bytes an installer
#                          may write for it (0x4-0x7, 0x4400-0xA3FF), with
#                          what it must find there first (README)
#   first-mib-uboot.img    with FIRST_MIB_DUMP: first-mib.img with
#                          u-boot-emmc.img at 0xA400 (step 4 of the bench:
#                          tools/bench/ad5x-uboot-flash writes only those
#                          sectors), checked the same way
#   u-boot-spl.map, u-boot-spl.nm, report.txt, SHA256SUMS
# Fails when a check fails: the boot ROM's load size (24 KiB), the SPL's
# memory map in the SRAM window, its worst-case stack, the U-Boot image
# sizes, and with a dump the first-MiB check.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
UVER=2026.10
# GitHub's archive of the v2026.10 tag (ftp.denx.de's tarball is the same tree)
USHA256=f943a88389c8fd70a6b0d061a88267465e143c7ca6ea2b75837ab20f5b60c739
UURL=https://github.com/u-boot/u-boot/archive/refs/tags/v$UVER.tar.gz
WORK=${WORK:-$HOME/workspace/u-boot-ad5x-build}
TOOLBIN=${TOOLBIN:-$REPO/buildroot/output/host/bin}
JOBS=${JOBS:-$(nproc)}
O=${O:-$WORK/out}
UBOOT_EMMC_MAX=$((0x100000 - 0xa400))	# eMMC 0xA400 to the end of the first MiB
UBOOT_SLOT_MAX=$((8 << 20))		# a kernel slot

log() { printf '\n=== %s\n' "$*"; }
die() { echo "build.sh: ERROR: $*" >&2; exit 1; }

if [ "${1:-}" = --container ]; then
	shift
	ENG=$(command -v podman || command -v docker) || die "no podman or docker"
	IMG=kiln-uboot-build
	log "container image $IMG (u-boot/Containerfile)"
	"$ENG" build -q -t $IMG -f "$HERE/Containerfile" "$HERE" >/dev/null
	mkdir -p "$WORK"
	extra=()
	[ "$(basename "$ENG")" = podman ] && extra+=(--userns=keep-id)
	SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$REPO" log -1 --format=%ct -- u-boot 2>/dev/null || true)}
	for v in FIRST_MIB_DUMP FIRST_MIB_ALSO JOBS SOURCE_DATE_EPOCH; do
		[ -n "${!v:-}" ] && extra+=(-e "$v=${!v}")
	done
	# VOLOPT=,z on SELinux hosts
	vols=(-v "$REPO:/src:ro${VOLOPT:-}" -v "$WORK:/work${VOLOPT:-}")
	for f in ${FIRST_MIB_DUMP:-} ${FIRST_MIB_ALSO:-}; do
		vols+=(-v "$f:$f:ro${VOLOPT:-}")
	done
	exec "$ENG" run --rm "${extra[@]}" "${vols[@]}" -e HOME=/work \
		-e WORK=/work -e O=/work/out -e TOOLBIN=/nonexistent $IMG \
		/src/u-boot/build.sh "$@"
fi

# the cross compiler
if [ -x "$TOOLBIN/mipsel-linux-gcc" ]; then
	export PATH=$TOOLBIN:/usr/local/bin:/usr/bin:/bin
	CROSS=mipsel-linux-
elif command -v mipsel-linux-gnu-gcc >/dev/null; then
	CROSS=mipsel-linux-gnu-
else
	die "no MIPS cross compiler: build Buildroot's toolchain (TOOLBIN), install gcc-mipsel-linux-gnu, or use --container"
fi

if [ -z "${USRC:-}" ]; then
	USRC=$WORK/u-boot-$UVER
	tarball=$WORK/u-boot-$UVER.tar.gz
	mkdir -p "$WORK"
	if [ ! -f "$tarball" ]; then
		log "fetch u-boot $UVER"
		curl -fsSL -o "$tarball.part" "$UURL"
		mv "$tarball.part" "$tarball"
	fi
	echo "$USHA256  $tarball" | sha256sum -c --quiet
	log "unpack + patches"
	rm -rf "$USRC"
	tar xzf "$tarball" -C "$WORK"
	for p in "$HERE"/patches/*.patch; do
		patch -d "$USRC" -p1 --quiet < "$p"
	done
fi

# Reproducible: the time of the last commit to u-boot/ (else the release's)
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
	SOURCE_DATE_EPOCH=$(git -C "$REPO" log -1 --format=%ct -- u-boot 2>/dev/null || true)
	[ -n "$SOURCE_DATE_EPOCH" ] || SOURCE_DATE_EPOCH=1791504000
fi
export SOURCE_DATE_EPOCH

mk() {	# mk OUTDIR [make args...]
	local out=$1; shift
	make -s -C "$USRC" O="$out" CROSS_COMPILE=$CROSS "$@" </dev/null
}
build() {	# build OUTDIR [config line...]
	local out=$1 l; shift
	rm -rf "$out"
	mk "$out" ad5x_defconfig
	for l in "$@"; do echo "$l" >> "$out/.config"; done
	[ $# -eq 0 ] || mk "$out" olddefconfig
}

log "build ($JOBS jobs, ${CROSS}gcc $("${CROSS}gcc" -dumpversion))"
build "$O"
mk "$O" -j"$JOBS"
log "chainload-test SPL"
build "$O-chainload" CONFIG_AD5X_SPL_CHAINLOAD=y
mk "$O-chainload" -j"$JOBS" spl/u-boot-spl.bin
log "stack check build (-fcallgraph-info=su)"
build "$O-stack"
mk "$O-stack" -j"$JOBS" KCFLAGS=-fcallgraph-info=su spl/u-boot-spl.bin
cmp -s "$O/spl/u-boot-spl.bin" "$O-stack/spl/u-boot-spl.bin" ||
	die "the stack check build's SPL differs from the real one"

D=$O/dist
rm -rf "$D"; mkdir -p "$D"
T=$HERE/tools
"${CROSS}nm" -n "$O/spl/u-boot-spl" > "$D/u-boot-spl.nm"
cp "$O/spl/u-boot-spl.map" "$O/u-boot.bin" "$D/"
cp "$O-chainload/spl/u-boot-spl.bin" "$D/spl-chainload.bin"
{
	echo "Kiln U-Boot $UVER + $(ls "$HERE"/patches/*.patch | wc -l) patches"
	echo "compiler: $("${CROSS}gcc" --version | head -1)"
	echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
	echo
	python3 -I "$T/ad5x_spl_image.py" image "$O/spl/u-boot-spl.bin" \
		"$D/spl-mmc.img" --nm "$D/u-boot-spl.nm"
	echo
	python3 -I "$T/spl_stack.py" "$O-stack/spl" --nm "$D/u-boot-spl.nm"
	echo
	if python3 -I "$T/ad5x_spl_image.py" image "$D/spl-chainload.bin" \
		"$D/should-not-exist" >/dev/null 2>&1; then
		die "the chainload SPL was accepted for a boot ROM image"
	fi
	echo "chainload-test SPL: $(stat -c %s "$D/spl-chainload.bin") bytes, refused for the boot ROM (as it must be)"
} | tee "$D/report.txt"
[ "${PIPESTATUS[0]}" = 0 ] || die "a check failed (above)"
grep -q "^spl_stack: ERROR" "$D/report.txt" && die "SPL stack check failed"
python3 -I "$T/ad5x_spl_image.py" usb-image "$D/spl-mmc.img" \
	"$D/spl-usb.bin" | tee -a "$D/report.txt"
[ "${PIPESTATUS[0]}" = 0 ] || die "spl-usb.bin: the USB image failed (above)"
python3 -I "$T/ad5x_spl_image.py" usb-image --stage2 "$D/spl-mmc.img" \
	"$D/spl-usb2.bin" | tee -a "$D/report.txt"
[ "${PIPESTATUS[0]}" = 0 ] || die "spl-usb2.bin: the USB image failed (above)"

MKIMAGE=$O/tools/mkimage
ver=$(sed -n 's/^#define PLAIN_VERSION "\(.*\)"/\1/p' "$O/include/generated/version_autogenerated.h")
"$MKIMAGE" -q -A mips -O u-boot -T firmware -C none -a 0x80100000 \
	-e 0x80100000 -n "Kiln U-Boot $ver" -d "$O/u-boot.bin" "$D/u-boot-emmc.img"
"$MKIMAGE" -q -A mips -O linux -T kernel -C none -a 0x80100000 \
	-e 0x80100000 -n "Kiln U-Boot $ver" -d "$O/u-boot.bin" \
	"$D/u-boot-kernel-slot.img"
sz=$(stat -c %s "$D/u-boot-emmc.img")
[ "$sz" -le $UBOOT_EMMC_MAX ] ||
	die "u-boot-emmc.img is $sz bytes, more than the $UBOOT_EMMC_MAX from 0xA400 to 1 MiB"
[ "$(stat -c %s "$D/u-boot-kernel-slot.img")" -le $UBOOT_SLOT_MAX ] ||
	die "u-boot-kernel-slot.img doesn't fit a kernel slot"
{
	echo
	echo "U-Boot proper: $(stat -c %s "$O/u-boot.bin") bytes; as a uImage $sz of $UBOOT_EMMC_MAX bytes at eMMC 0xA400"
	"${CROSS}nm" "$O/u-boot" | awk '$3=="board_get_usable_ram_top"{f=1} END{exit !f}' &&
		echo "U-Boot proper: usable RAM top 0x8EB00000 (ramoops 0x0EB00000-0x0EBFFFFF kept)"
} | tee -a "$D/report.txt"

if [ -n "${FIRST_MIB_DUMP:-}" ]; then
	log "first-MiB candidate from $FIRST_MIB_DUMP"
	python3 -I "$T/ad5x_spl_image.py" first-mib "$FIRST_MIB_DUMP" \
		"$D/spl-mmc.img" "$D/first-mib.img"
	also=()
	for f in ${FIRST_MIB_ALSO:-}; do also+=(--also "$f"); done
	python3 -I "$T/check_first_mib.py" "$D/first-mib.img" \
		--unit "$FIRST_MIB_DUMP" --spl "$D/spl-mmc.img" "${also[@]}" |
		tee -a "$D/report.txt"
	[ "${PIPESTATUS[0]}" = 0 ] || die "first-MiB check failed"
	python3 -I "$T/ad5x_spl_image.py" write-plan "$FIRST_MIB_DUMP" \
		"$D/spl-mmc.img" "$D/first-mib-plan.json"
	python3 -I "$T/ad5x_spl_image.py" apply-plan "$D/first-mib-plan.json" \
		"$FIRST_MIB_DUMP" "$WORK/plan-check.img" >/dev/null
	cmp -s "$WORK/plan-check.img" "$D/first-mib.img" ||
		die "the write plan doesn't give first-mib.img"
	rm -f "$WORK/plan-check.img"
	echo "write plan: first-mib-plan.json writes 0x4-0x7 and 0x4400-0xA3FF only; applied to the dump it gives first-mib.img" |
		tee -a "$D/report.txt"
	# U-Boot proper at 0xA400 on top of it (the bench's step 4)
	python3 -I "$T/ad5x_spl_image.py" uboot-mib "$D/first-mib.img" \
		"$D/u-boot-emmc.img" "$D/first-mib-uboot.img" | tee -a "$D/report.txt"
	[ "${PIPESTATUS[0]}" = 0 ] || die "first-mib-uboot.img failed (above)"
	python3 -I "$T/check_first_mib.py" "$D/first-mib-uboot.img" \
		--unit "$FIRST_MIB_DUMP" --spl "$D/spl-mmc.img" \
		--uboot "$D/u-boot-emmc.img" "${also[@]}" | tee -a "$D/report.txt"
	[ "${PIPESTATUS[0]}" = 0 ] || die "first-MiB check with U-Boot failed"
fi

(cd "$D" && sha256sum -- * | grep -v SHA256SUMS > SHA256SUMS)
log "done: $D"
ls -l "$D"
