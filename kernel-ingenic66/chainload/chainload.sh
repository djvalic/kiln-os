#!/bin/sh
# Boot a test kernel from RAM on the AD5X (stock 5.10 kernel running),
# without writing the eMMC or the boot flag. A hang is undone by a power
# cycle: the printer then boots its installed system as before.
#
#   chainload.sh stage [IMAGE] [EXTRA...]   load chainload.ko, stage the image
#   chainload.sh go                         stop everything and jump (no return;
#                                           SSH drops; runs detached)
#   chainload.sh unstage                    rmmod chainload
#   chainload.sh cmdline                    print the command line it passes
#
# Files: $DIR/chainload.ko, $DIR/xImage (default image). BusyBox ash.
#
# The test kernel boots the main OS from slot B (root=PARTLABEL=rootfs2)
# with ad5x.noslot: /usr/lib/ad5x/slot.sh then reports no slot, so
# S01ad5x-tryboot/S99ad5x-booted leave the boot flag alone.
# Boot messages go to the LCD (console=tty0 last).
# The command line is the running stock kernel's (/proc/cmdline, as
# S00ad5x-kernel passes it), with the low window of Kiln's kernels as
# S00ad5x-kernel's kiln_mem makes it (mem=236M@0x0 becomes mem=252M@0x0,
# rmem= goes). Its mem= arguments tell the board: a second bank at
# 0x30000000 means 512 MiB. In standard memory (the default, as
# S00ad5x-kernel's) that bank is taken out; EXTENDED=1 keeps it on a
# 512 MiB board. ad5x.ram=256|512 and ad5x.memmode=standard|extended say
# which (docs/memory.md, "Extended memory"). Its root= is replaced; the
# rest below comes after it, so it wins.
DIR=${DIR:-/data/ad5x/chainload}
PC=${CHAINLOAD_CMDLINE:-/proc/cmdline}	# (tests)
HW=256
tr ' ' '\n' < "$PC" | grep -E -i -q '^mem=[0-9]+[kmg]?@0x0*30000000$' && HW=512
MODE=standard BANK=
[ "${EXTENDED:-}" = 1 ] && [ $HW = 512 ] && MODE=extended
[ $MODE = standard ] && BANK='s/ [mM][eE][mM]=[0-9][0-9]*[kKmMgG]\{0,1\}@0[xX]0*30000000 / /g; '
CMDLINE_BASE="$(sed "s/^/ /; s/\$/ /; s/ root=[^ ]*//g; s/ rmem=[^ ]*//g; s/ mem=236M@0x0 / mem=252M@0x0 /g; ${BANK}s/^ //; s/ \$//" "$PC") console=tty0 loglevel=8 ad5x.noslot root=PARTLABEL=rootfs2 rootwait rootfstype=squashfs ro ad5x.ram=$HW ad5x.memmode=$MODE"

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
cmdline) echo "$CMDLINE_BASE" ;;
*) sed -n '2,26p' "$0"; exit 2 ;;
esac
