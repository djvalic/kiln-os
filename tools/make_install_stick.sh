#!/bin/bash
# Make the Kiln OS install files: a folder (or .zip) to copy onto a FAT
# USB stick, or onto the printer for the SSH install (docs/install.md).
#
# usage: tools/make_install_stick.sh [-r RECOVERY.squashfs] [-m MAIN.zip]
#            [-V VERSION] [--private] [-o DIR | --zip FILE.zip]
#        tools/make_install_stick.sh ... --device /dev/sdX
#   -r   recovery image (default buildroot/output-recovery/images/rootfs.squashfs)
#   -m   main OS update .zip without a kernel (default: made from
#        buildroot/output/images/rootfs.squashfs with tools/make_swu.sh --zip)
#   -V   version (default: from the zip, else date)
#   -o   output folder (default ./ad5x-install-stick-VERSION); its contents go
#        in the top directory of the stick
#   --zip FILE   also pack the folder into FILE (unzip it onto the stick)
#   --private    allow files that contain Flashforge/Ingenic files (your own
#        private build; such a stick must never be shared). Without it every
#        file is checked with tools/check_vendor_free.sh and refused if not clean
#   --device DEV erase the whole USB stick DEV (e.g. /dev/sdb), make one FAT32
#        partition and copy the files onto it. Needs root (run with sudo), DEV
#        must be a removable USB disk that isn't mounted, and you must type
#        its path to confirm. Everything on it is lost.
#
# Layout (stick top directory):
#   flashforge_init.sh      run by the stock firmware at boot (installer entry)
#   README.txt
#   ad5x-install/           ad5x-install.sh, ad5x-vendor, recovery.squashfs,
#                           ad5x-main-VERSION.zip, screens/*.jpg, VERSION,
#                           SHA256SUMS (checked before anything runs)
# The same ad5x-install/ folder is the SSH install: copy it to the printer
# (/usr/data/ad5x-install) and run "sh ad5x-install.sh --check", then without
# --check. Never put an AD5X-*.tgz next to these files: stock would install it.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
RECOVERY=$REPO/buildroot/output-recovery/images/rootfs.squashfs
MAIN= VERSION= OUT= ZIPOUT= PRIVATE= DEVICE=
usage() { sed -n '2,32p' "$0" >&2; exit 2; }
die() { echo "make_install_stick: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
	case "$1" in
	-r) RECOVERY=$2; shift ;;
	-m) MAIN=$2; shift ;;
	-V) VERSION=$2; shift ;;
	-o) OUT=$2; shift ;;
	--zip) ZIPOUT=$2; shift ;;
	--private) PRIVATE=1 ;;
	--device) DEVICE=$2; shift ;;
	-h|--help) sed -n '2,32p' "$0"; exit 0 ;;
	*) usage ;;
	esac
	shift
done

# --device checks first: nothing is built for a device that would be refused
if [ -n "$DEVICE" ]; then
	[ -b "$DEVICE" ] || die "$DEVICE is not a block device"
	dn=$(basename "$(readlink -f "$DEVICE")")
	[ -d "/sys/block/$dn" ] || die "$DEVICE is not a whole disk (give /dev/sdX, not a partition)"
	[ "$(cat "/sys/block/$dn/removable" 2>/dev/null)" = 1 ] ||
		readlink -f "/sys/block/$dn" | grep -q /usb ||
		die "$DEVICE is not a removable USB disk"
	sz=$(( $(cat "/sys/block/$dn/size") * 512 ))
	[ "$sz" -le $((256 * 1024 * 1024 * 1024)) ] || die "$DEVICE is larger than 256 GB; not a stick?"
	grep -q "^/dev/$dn" /proc/mounts && die "$DEVICE (or a partition of it) is mounted; unmount it first"
	[ "$(id -u)" = 0 ] || die "--device needs root (sudo)"
	for t in sfdisk mkfs.vfat; do command -v $t >/dev/null || die "$t not installed"; done
fi

[ -f "$RECOVERY" ] || die "no recovery image $RECOVERY (build buildroot/output-recovery)"
[ "$(head -c 4 "$RECOVERY")" = hsqs ] || die "$RECOVERY is not a squashfs image"
W=$(mktemp -d "${TMPDIR:-/tmp}/make_install_stick.XXXXXX")
trap 'rm -rf "$W"' EXIT
if [ -z "$MAIN" ]; then
	"$REPO/tools/make_swu.sh" --zip -o "$W/main.zip" ${VERSION:+-V "$VERSION"} >/dev/null
	MAIN=$(ls "$W"/*.zip)
fi
[ -f "$MAIN" ] || die "no main update $MAIN"
unzip -l "$MAIN" | grep -q ' kernel.uimage$' && die "$MAIN carries a kernel; the install takes updates without one (make_swu.sh without -k)"
if [ -z "$VERSION" ]; then
	VERSION=$(unzip -p "$MAIN" version.txt 2>/dev/null | sed -n 's/.*version \(.*\)/\1/p')
	[ -n "$VERSION" ] || VERSION=$(date -u +%Y%m%d%H%M)
fi
OUT=${OUT:-$PWD/ad5x-install-stick-$VERSION}
[ -e "$OUT" ] && die "$OUT exists"

if [ -z "$PRIVATE" ]; then
	echo "make_install_stick: checking for vendor files"
	"$REPO/tools/check_vendor_free.sh" -q "$RECOVERY" "$MAIN" ||
		die "the images contain Flashforge/Ingenic files: build them vendor-free (default), or --private for your own use only"
fi

B=$OUT/ad5x-install
mkdir -p "$B/screens"
install -m 0755 "$REPO/tools/install/flashforge_init.sh" "$OUT/flashforge_init.sh"
install -m 0755 "$REPO/tools/install/ad5x-install.sh" "$B/ad5x-install.sh"
install -m 0755 "$REPO/buildroot/package/ad5x-system/bin/ad5x-vendor" "$B/ad5x-vendor"
cp "$RECOVERY" "$B/recovery.squashfs"
cp "$MAIN" "$B/ad5x-main-$VERSION.zip"
echo "$VERSION" > "$B/VERSION"
python3 "$REPO/tools/make_install_screens.py" "$B/screens" >/dev/null
(cd "$B" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | sort | xargs sha256sum > SHA256SUMS)
cat > "$OUT/README.txt" <<TXT
Kiln OS $VERSION, install stick. See docs/install.md.
1. Copy everything here into the top folder of a FAT32 USB stick.
2. Printer off. Stick in. Printer on. The screen shows the steps (a few
   minutes; with enough room it first copies the eMMC to the stick, about
   1.3 GB). It restarts into Kiln OS by itself.
3. Log: ad5x-install.log on the stick.
Works on the stock firmware, with or without zMod. Never put an AD5X-*.tgz on
this stick. Back to stock later: ad5x-restore-stock over SSH (docs/install.md).
TXT
[ -n "$PRIVATE" ] && echo "PRIVATE build: contains Flashforge/Ingenic files. Never share it." >> "$OUT/README.txt"
ls "$OUT" | grep -qi '^AD5X-.*\.tgz$' && die "an AD5X-*.tgz ended up in $OUT"
echo "make_install_stick: $OUT ($(du -sh "$OUT" | cut -f1))"

if [ -n "$ZIPOUT" ]; then
	rm -f "$ZIPOUT"
	(cd "$OUT" && zip -q -r -0 "$(realpath -m "$ZIPOUT")" .)
	echo "make_install_stick: $ZIPOUT"
fi

if [ -n "$DEVICE" ]; then
	echo "ALL DATA ON $DEVICE ($(cat "/sys/block/$dn/device/model" 2>/dev/null | tr -s ' '), $((sz / 1000000)) MB) WILL BE ERASED."
	printf 'Type the device path (%s) to continue: ' "$DEVICE"
	read -r a
	[ "$a" = "$DEVICE" ] || die "not confirmed, nothing written"
	echo 'label: dos
type=c' | sfdisk -q "$DEVICE"
	sleep 2
	p=$(lsblk -lnpo NAME "$DEVICE" | sed -n 2p)
	[ -b "$p" ] || die "no partition on $DEVICE after partitioning"
	mkfs.vfat -F 32 -n AD5XINST "$p" >/dev/null
	m=$(mktemp -d)
	mount "$p" "$m"
	cp -r "$OUT"/. "$m"/
	(cd "$m/ad5x-install" && sha256sum -c --quiet SHA256SUMS) || { umount "$m"; die "copy on the stick doesn't verify"; }
	umount "$m"; rmdir "$m"; sync
	echo "make_install_stick: $DEVICE ready (FAT32 \"AD5XINST\")"
fi
