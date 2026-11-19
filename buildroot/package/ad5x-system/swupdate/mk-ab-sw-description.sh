#!/bin/sh
# Print the sw-description for an A/B update of the main OS (lib/ab.sh).
#
# usage: mk-ab-sw-description.sh VERSION ROOTFS_SIZE ROOTFS_SHA256 SCRIPT
#   (ab-pack.py measures rootfs.squashfs as it streams from the update)
# Two selections, stable,slot_a and stable,slot_b: the rootfs streamed into
# that slot's root partition, ad5x-ab.sh around it, and U-Boot's
# environment for it (bootenv, one write once everything else succeeded):
# kiln_slot, upgrade_available=1 and bootcount=0, so U-Boot counts the new
# slot's starts and goes back after bootlimit (u-boot patch 0051).
set -e
VERSION=$1 RSIZE=$2 RSHA=$3 SCRIPT=$4
SSHA=$(sha256sum "$SCRIPT" | cut -d' ' -f1)
slot() {	# a|b, its root partition
	cat <<SLOT
		slot_$1 = {
			images: (
				{
					filename = "rootfs.squashfs";
					device = "$2";
					type = "raw";
					sha256 = "$RSHA";
					installed-directly = true;
				}
			);
			scripts: (
				{
					filename = "ad5x-ab.sh";
					type = "shellscript";
					data = "slot=$1 rootfs_size=$RSIZE rootfs_sha256=$RSHA";
					sha256 = "$SSHA";
				}
			);
			bootenv: (
				{ name = "kiln_slot"; value = "$1"; },
				{ name = "upgrade_available"; value = "1"; },
				{ name = "bootcount"; value = "0"; }
			);
		};
SLOT
}
cat <<DESC
software =
{
	version = "$VERSION";
	description = "Kiln OS (main system), A/B";
	hardware-compatibility: [ "1.0" ];

	stable = {
$(slot a /dev/mmcblk0p2)
$(slot b /dev/mmcblk0p4)
	};
}
DESC
