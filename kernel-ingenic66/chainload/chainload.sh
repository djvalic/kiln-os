#!/bin/sh
# Boot a test kernel from RAM on the AD5X (stock 5.10 kernel running),
# without writing the eMMC or the boot flag. A hang is undone by a power
# cycle: the printer then boots its installed system as before.
#
#   chainload.sh stage [IMAGE] [EXTRA...]   load chainload.ko, stage the image
#   chainload.sh go                         stop everything and jump (no return;
#                                           SSH drops; runs detached)
#   chainload.sh unstage                    rmmod chainload
#
# Files: $DIR/chainload.ko, $DIR/xImage (default image). BusyBox ash.
#
# The test kernel boots the main OS from slot B (root=PARTLABEL=rootfs2)
# with ad5x.noslot: /usr/lib/ad5x/slot.sh then reports no slot, so
# S01ad5x-tryboot/S99ad5x-booted leave the boot flag alone.
# Boot messages go to the LCD (console=tty0 last).
DIR=${DIR:-/data/ad5x/chainload}
CMDLINE_BASE="console=ttyS0,115200n8 console=tty0 loglevel=8 ad5x.noslot mem=236M@0x0 mem=256M@0x30000000 rmem=16M@0xec00000 rtos_size=4M@0xfc00000 init=/linuxrc root=PARTLABEL=rootfs2 rootwait rootfstype=squashfs ro lpj=11935744"

die() { echo "chainload: $*" >&2; exit 1; }

stage() {
	img=${1:-$DIR/xImage}; shift 2>/dev/null
	[ "$(uname -r)" = "5.10.186+" ] || die "expects the stock 5.10.186+ kernel, not $(uname -r)"
	[ -f "$DIR/chainload.ko" ] || die "no $DIR/chainload.ko"
	[ -f "$img" ] || die "no image $img"
	grep -q '^chainload ' /proc/modules && die "already staged (chainload.sh unstage first)"
	krp=$(sed -n 's/^\([0-9a-f]*\) T kernel_restart_prepare$/\1/p' /proc/kallsyms)
	[ -n "$krp" ] || die "kernel_restart_prepare not in /proc/kallsyms"
	insmod "$DIR/chainload.ko" image="$img" krp=0x$krp \
		cmdline="\"$CMDLINE_BASE $*\"" || die "insmod failed (dmesg | tail)"
	dmesg | grep 'chainload:' | tail -40
	echo "staged. Next: chainload.sh go"
}

go_now() {
	exec >/dev/console 2>&1 </dev/null
	echo "chainload: stopping services"
	for s in S70helixscreen S65ad5x-screen S64ad5x-camera S63nginx \
		 S62moonraker S61klipper S60ad5x-eboard S50crond S49chronyd; do
		[ -x /etc/init.d/$s ] && /etc/init.d/$s stop
	done
	killall ustreamer ad5x-fbstream 2>/dev/null
	sleep 2
	# USB, Wi-Fi and Ethernet do DMA into RAM: stop them before the copy.
	# The network first: the Wi-Fi driver (8821cu) sits on USB and crashes
	# the kernel from a stale timer if its USB host goes away under it.
	for i in wlan0 wlan1 eth0; do ip link set $i down 2>/dev/null; done
	rmmod 8821cu soc_mac_driver 2>/dev/null
	for d in 13500000.otg 13540000.usb; do
		[ -e /sys/bus/platform/drivers/dwc2/$d ] &&
			echo $d > /sys/bus/platform/drivers/dwc2/unbind
	done
	# one CPU
	for c in /sys/devices/system/cpu/cpu[1-9]*/online; do
		[ -f "$c" ] && echo 0 > "$c"
	done
	sync
	for m in /data /home /mnt/usb; do mount -o remount,ro $m 2>/dev/null; done
	sync
	echo "chainload: jumping"
	echo 1 > /sys/module/chainload/parameters/go
	echo "chainload: jump refused; reboot to recover"
}

case "$1" in
stage) shift; stage "$@" ;;
go)
	grep -q '^chainload ' /proc/modules || die "not staged"
	echo "chainload: going; SSH will drop. Power-cycle if nothing happens in 3 minutes."
	# detached: the network goes down on the way
	setsid sh "$0" go-now >/dev/null 2>&1 </dev/null &
	;;
go-now) go_now ;;
unstage) rmmod chainload ;;
*) sed -n '2,20p' "$0"; exit 2 ;;
esac
