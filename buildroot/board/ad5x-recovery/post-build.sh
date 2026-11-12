#!/bin/sh
# Recovery image, after the target tree is assembled ($1 = target dir).
# - Vendor files as the main image (board/ad5x/bundle-stock.sh): none by
#   default, bundled only in a private build.
# - rcS (boot trace), S10udevd and NetworkManager's configuration from the
#   main image's overlay; NetworkManager as in the main image (network-nm.sh).
# - Release marks: /etc/ad5x-release ("Kiln OS recovery <version> (<date>)"),
#   /etc/ad5x-recovery
#   (tells it from the main OS), /etc/hwrevision for SWUpdate's hardware check.
# - SWUpdate's public key /etc/swupdate/public.pem (docs/recovery-os.md):
#   AD5X_SWU_PUBKEY (a PEM public key), else ~/.config/ad5x/swupdate-public.pem,
#   else derived from the private key AD5X_SWU_KEY or
#   ~/.config/ad5x/swupdate-private.pem. Without one the image has no key and
#   SWUpdate doesn't start. Private keys never go into the image or the repo.
# - Buildroot's S80swupdate and its progress client (which would reboot on
#   its own) are replaced by S70swupdate.
set -e
TARGET=$1
EXT=$BR2_EXTERNAL_AD5X_PATH

. "$EXT/board/ad5x/bundle-stock.sh"
bundle_stock "$TARGET"

MAIN=$EXT/board/ad5x/rootfs-overlay
install -D -m 0755 "$MAIN/etc/init.d/rcS" "$TARGET/etc/init.d/rcS"
install -D -m 0755 "$MAIN/etc/init.d/S10udevd" "$TARGET/etc/init.d/S10udevd"
install -D -m 0644 "$MAIN/etc/NetworkManager/NetworkManager.conf" \
	"$TARGET/etc/NetworkManager/NetworkManager.conf"
install -D -m 0644 "$MAIN/etc/default/NetworkManager" \
	"$TARGET/etc/default/NetworkManager"
install -D -m 0644 "$MAIN/etc/udev/rules.d/80-net-name-slot.rules" \
	"$TARGET/etc/udev/rules.d/80-net-name-slot.rules"
. "$EXT/board/ad5x/network-nm.sh"
nm_target "$TARGET"
install -D -m 0644 "$MAIN/etc/network/interfaces" "$TARGET/etc/network/interfaces"

# The release it was built for (AD5X_VERSION, else git as the main image's
# post-build.sh) and the real build date: BR2_REPRODUCIBLE's date wrapper
# returns SOURCE_DATE_EPOCH (Buildroot's own date) unless that is empty.
# Neither counts in the content ID below.
RVER=${AD5X_VERSION:-$(git -C "$EXT/.." describe --tags --match 'v[0-9]*' 2>/dev/null || echo dev)}
echo "Kiln OS recovery $RVER ($(SOURCE_DATE_EPOCH= date -u +%Y-%m-%d))" > "$TARGET/etc/ad5x-release"
echo "Kiln OS recovery (slot A); see docs/recovery-os.md" > "$TARGET/etc/ad5x-recovery"
echo "ad5x 1.0" > "$TARGET/etc/hwrevision"

mkdir -p "$TARGET/etc/swupdate"
rm -f "$TARGET/etc/swupdate/public.pem"
if [ "${AD5X_SWU_SIGNED:-}" = 1 ]; then
	pub=${AD5X_SWU_PUBKEY:-$HOME/.config/ad5x/swupdate-public.pem}
	priv=${AD5X_SWU_KEY:-$HOME/.config/ad5x/swupdate-private.pem}
	if [ -f "$pub" ]; then
		install -m 0644 "$pub" "$TARGET/etc/swupdate/public.pem"
		echo "post-build: SWUpdate public key from $pub"
	elif [ -f "$priv" ]; then
		openssl rsa -in "$priv" -pubout -out "$TARGET/etc/swupdate/public.pem" 2>/dev/null
		echo "post-build: SWUpdate public key derived from $priv"
	else
		echo "post-build: WARNING no SWUpdate key (AD5X_SWU_PUBKEY), image can't take updates"
	fi
else
	echo "post-build: open update mode (no SWUpdate key; unsigned .swu with sha256 checks)"
fi
if [ -f "$TARGET/etc/swupdate/public.pem" ]; then
	grep -q 'PRIVATE KEY' "$TARGET/etc/swupdate/public.pem" &&
		{ echo "post-build: ERROR $pub is a private key"; exit 1; }
	openssl pkey -pubin -in "$TARGET/etc/swupdate/public.pem" -noout ||
		{ echo "post-build: ERROR not a PEM public key"; exit 1; }
fi

rm -f "$TARGET/etc/init.d/S80swupdate" \
	"$TARGET/usr/lib/swupdate/conf.d/90-start-progress"

# Content ID (docs/recovery-os.md, "Updates"): sha256 over every path, mode
# and content in the tree, except the marks that carry the build date. The
# main OS rewrites slot A only when its recovery OS has another ID, not at
# every update (BR2_REPRODUCIBLE keeps unchanged binaries byte-identical).
rm -f "$TARGET/etc/ad5x-recovery-id"
id=$(cd "$TARGET" && find . ! -path ./etc/ad5x-release ! -path ./etc/ad5x-recovery-id \
		\( -type f -o -type l \) | LC_ALL=C sort | while IFS= read -r f; do
	if [ -L "$f" ]; then
		printf '%s l %s\n' "$f" "$(readlink "$f")"
	else
		printf '%s %s %s\n' "$f" "$(stat -c %a "$f")" "$(sha256sum < "$f" | cut -d' ' -f1)"
	fi
done | sha256sum | cut -c1-16)
echo "$id" > "$TARGET/etc/ad5x-recovery-id"
echo "post-build: recovery content ID $id"
