#!/bin/sh
# Recovery image, after the root filesystem images are made: a size check
# against the 100 MiB slot and a short README. Only a private build
# (bundle-stock.sh) also copies the stock kernel next to it (slot A keeps
# the printer's own stock kernel); AD5X_STOCK_KERNEL_DIR as in
# board/ad5x/post-image.sh. With BR2_PACKAGE_AD5X_KERNEL66 (off by
# default, ad5x_recovery_defconfig) our 6.6 kernel from the image is put
# next to it as xImage-6.6, for a test start (docs/recovery-os.md, "Our
# kernel"); nothing writes it to p1.
set -e
REPO=$(cd "$BR2_EXTERNAL_AD5X_PATH/.." && pwd)
. "$BR2_EXTERNAL_AD5X_PATH/board/ad5x/bundle-stock.sh"
K=${AD5X_STOCK_KERNEL_DIR:-$REPO/firmware/stock-3.1.0/unpacked/kernel-2.0.1}
rm -f "$BINARIES_DIR/xImage-stock"
if ad5x_bundle_vendor; then
	src=$(ls "$K"/ota_kernel/ota_v1/xImage.0000.* 2>/dev/null | head -1)
	if [ -n "$src" ]; then
		cp "$src" "$BINARIES_DIR/xImage-stock"
	else
		echo "post-image: WARNING no stock kernel in $K/ota_kernel"
	fi
fi
rm -f "$BINARIES_DIR/xImage-6.6"
K66=$TARGET_DIR/usr/lib/ad5x/kernel66
k66=
if [ -f "$K66/xImage" ]; then
	cp "$K66/xImage" "$BINARIES_DIR/xImage-6.6"
	k66="
xImage-6.6        our 6.6 kernel ($(cat "$K66/release" 2>/dev/null)), also in the image; not written to p1"
fi
# The content ID next to the image (the main image carries both: post-build.sh)
cp "$TARGET_DIR/etc/ad5x-recovery-id" "$BINARIES_DIR/rootfs.id"
size=$(wc -c < "$BINARIES_DIR/rootfs.squashfs")
[ "$size" -le 104857600 ] || { echo "post-image: rootfs.squashfs $size bytes > 100 MiB slot"; exit 1; }
cat > "$BINARIES_DIR/IMAGES.txt" <<TXT
AD5X recovery OS (slot A: kernel p1, rootfs p2). See docs/recovery-os.md.
rootfs.squashfs   recovery root filesystem (LZO squashfs), $size bytes
rootfs.tar        the same tree, for inspection or qemu tests$k66
$(ad5x_bundle_vendor && echo "xImage-stock      stock Linux 5.10.186 (u-boot image), eMMC units
PRIVATE build: contains Flashforge/Ingenic files; never publish it." || echo "Vendor-free build: no Flashforge/Ingenic files (tools/check_vendor_free.sh).")
TXT
