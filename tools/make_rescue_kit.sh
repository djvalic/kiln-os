#!/bin/bash
# The rescue kit: what a PC needs to check, back up and repair a printer's
# eMMC when nothing on it starts (docs/emmc-repair.md), as one zip for a
# release.
#
# usage: tools/make_rescue_kit.sh -b BOOTDIR -V VERSION -o OUT.zip
#   -b BOOTDIR  the boot loader build's dist (buildroot/output-recovery/
#               images/bootloader, or u-boot/build.sh's $O/dist): its
#               spl-usb2.bin and u-boot.bin start Kiln's U-Boot over USB
#   -V VERSION  the release (for the folder name and the README)
#   -o OUT.zip  the kit
#
# The kit (kiln-os-VERSION-rescue/):
#   README.txt, SHA256SUMS
#   boot/spl-usb2.bin, boot/u-boot.bin     the eMMC as a USB disk over J28
#   tools/ad5x_emmc_repair.py              find, check, backup, restore
#   tools/ad5x_emmc_image.py               eMMC files from the release's
#                                          update zip (--from-update), with
#                                          the USBCloner network rescue
#   tools/ad5x_usershare.py                check or make usershare (p6)
#   tools/ad5x_netconsole.py               U-Boot's console over UDP
#   u-boot/tools/ad5x_usbboot.py           the boot ROM's USB mode
#   u-boot/tools/ad5x_spl_image.py         (used by the two above)
#   docs/emmc-repair.md, docs/USB-BOOT.md  the steps
# The system itself isn't in it: --from-update takes it from the release's
# kiln-os-VERSION-update.zip.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
die() { echo "make_rescue_kit: $*" >&2; exit 1; }

BOOT= VERSION= OUT=
while getopts b:V:o: o; do
	case $o in
	b) BOOT=$OPTARG ;;
	V) VERSION=$OPTARG ;;
	o) OUT=$OPTARG ;;
	*) sed -n '6,11p' "$0" >&2; exit 2 ;;
	esac
done
[ -n "$BOOT" ] && [ -n "$VERSION" ] && [ -n "$OUT" ] || { sed -n '6,11p' "$0" >&2; exit 2; }
for f in spl-usb2.bin u-boot.bin; do
	[ -f "$BOOT/$f" ] || die "$BOOT/$f missing (a boot loader build from before the USB stage 2?)"
done
# spl-usb2.bin: the SPL for stage 1 only (tag KILNUSB2 at 0x7F0)
[ "$(dd if="$BOOT/spl-usb2.bin" bs=1 skip=$((0x7f0)) count=8 status=none)" = KILNUSB2 ] ||
	die "$BOOT/spl-usb2.bin has no KILNUSB2 tag"
grep -q "ums 0 mmc 0" "$BOOT/u-boot.bin" || die "$BOOT/u-boot.bin can't offer the eMMC over USB (ums)"
command -v zip >/dev/null || die "zip not installed"

NAME=kiln-os-$VERSION-rescue
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
K=$W/$NAME
mkdir -p "$K/boot" "$K/tools" "$K/u-boot/tools" "$K/docs"
cp "$BOOT/spl-usb2.bin" "$BOOT/u-boot.bin" "$K/boot/"
for f in ad5x_emmc_repair.py ad5x_emmc_image.py ad5x_usershare.py ad5x_netconsole.py; do
	cp "$REPO/tools/$f" "$K/tools/"
done
cp "$REPO/u-boot/tools/ad5x_usbboot.py" "$REPO/u-boot/tools/ad5x_spl_image.py" "$K/u-boot/tools/"
cp "$REPO/docs/emmc-repair.md" "$K/docs/"
cp "$REPO/u-boot/USB-BOOT.md" "$K/docs/"
chmod 755 "$K"/tools/*.py "$K"/u-boot/tools/*.py

cat > "$K/README.txt" <<EOF
Kiln OS $VERSION rescue kit
===========================

For a printer whose eMMC is damaged: check it, back it up, and write it
back, from a PC. The full steps are in docs/emmc-repair.md. This is bench
work on the mainboard; it is provided as is and you do it at your own risk.

You also need this release's kiln-os-$VERSION-update.zip (the system), a
USB cable on the mainboard's J28 header, and on the PC Python 3 with
pyusb, e2fsprogs (mke2fs, debugfs, e2fsck) and squashfs-tools
(unsquashfs). Linux works as is; on Windows use WSL, or route 2's
USBCloner.

Route 1, a Linux PC: the eMMC as a USB disk
  1. The printer into the boot ROM's USB mode (docs/USB-BOOT.md), then
       python3 u-boot/tools/ad5x_usbboot.py run-uboot boot/spl-usb2.bin boot/u-boot.bin
     Unmount whatever the desktop mounted of it (its usershare, userdata):
     the tools refuse a disk in use.
  2. sudo python3 tools/ad5x_emmc_repair.py check
  3. sudo python3 tools/ad5x_emmc_repair.py backup /somewhere/with/1.5GB
  4. python3 tools/ad5x_emmc_image.py --from-update kiln-os-$VERSION-update.zip emmc-files/
     sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/ --dry-run
     sudo python3 tools/ad5x_emmc_repair.py restore --image emmc-files/
     /data is kept (--new-data for a new one). The first MiB is built from
     this printer's own boot.img (found on the eMMC, or --stock-mib). On a
     printer still on Flashforge's boot loader this installs Kiln's own
     and needs --install-boot-loader; --parts p2,p4,p5 writes only the
     system instead (docs/emmc-repair.md, "The boot loader").

Route 2, USBCloner: the first MiB, then the rest over Ethernet
(installs Kiln's own boot loader)
  1. python3 tools/ad5x_emmc_image.py --from-update kiln-os-$VERSION-update.zip \\
         --stock-mib <your boot.img> --usershare <your backup>... \\
         --mac <your MAC, or random> --rescue <this PC's IP>:8000 rescue-set/
     (--keep-usershare and --keep-data leave those on the eMMC as they are)
  2. python3 -m http.server 8000 --bind <this PC's IP> --directory rescue-set/
     python3 tools/ad5x_netconsole.py        (to watch the rescue)
  3. USBCloner writes rescue-set/rescue-first-mib.bin at 0x0 (settings in
     rescue-set/RESCUE.txt); power off and on; Kiln's U-Boot fetches,
     checks and writes the rest, then starts Kiln OS.
  4. Stop the server and delete rescue-set/: it holds your usershare
     (Wi-Fi passwords, stock's root password hash).

Usershare (p6) holds this printer's factory data (its Ethernet address).
No release has it: keep a backup of it while the printer works.
EOF

(cd "$K" && find . -type f ! -name SHA256SUMS | sort | sed 's|^\./||' |
	xargs sha256sum > SHA256SUMS)
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
(cd "$W" && zip -q -r -X "$(realpath -m "$OUT")" "$NAME")
echo "make_rescue_kit: $OUT ($(du -k "$OUT" | cut -f1) KiB)"
