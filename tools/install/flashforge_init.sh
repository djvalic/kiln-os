#!/bin/sh
# Kiln OS install stick (tools/make_install_stick.sh; docs/install.md).
# Goes in the top directory of a FAT USB stick, next to the folder
# ad5x-install/.
#
# The stock firmware's /usr/prog/app_startup.sh runs /mnt/flashforge_init.sh
# from a FAT stick at boot, as root, before the Flashforge app (and zMod)
# start; it passes the machine name and id ("AD5X 0026"). This script runs
# the installer (ad5x-install/ad5x-install.sh --usb, the same one as the SSH
# path) and shows its progress on the panel. Log: ad5x-install.log here.
#
# - Done: the installer restarts the printer into Kiln OS. Stock's init
#   ignores a normal reboot while this hook runs (it is part of stock's
#   start-up), so the installer forces one (ad5x-install.sh, restart()).
#   Kiln OS never runs this file (only stock's app_startup.sh does), so
#   leaving the stick in is harmless.
# - Done, but the printer is still running after all of that (about 20 s):
#   the installer shows "Switch off and on" (screens/powercycle.jpg) and
#   the printer waits here. A power cycle is safe then: the switch is made.
# - Refused or failed: the message stays on the screen and the printer waits
#   here (exit 0: stock's app_startup.sh then sleeps instead of starting the
#   app). Remove the stick and power-cycle: the printer starts as before.
#   Nothing is written before all checks pass, and the boot flag last.
# - A second run on stock after the install already switched slots means the
#   new system didn't come up: refused, unless a file "ad5x-install-retry"
#   is on the stick (it is deleted when used, so this can't loop).
#   "ad5x-no-emmc-backup" on the stick skips the optional eMMC backup
#   (about 1.3 GB on the stick).
#
# Never put an AD5X-*.tgz on this stick: stock would install it as firmware.
S=$(cd "$(dirname "$0")" && pwd)
B=$S/ad5x-install
LOG=$S/ad5x-install.log
exec >>"$LOG" 2>&1
echo "=== $(date) Kiln OS install stick, args: $*"

hold() {	# keep the message on the screen; stock then sleeps (exit 0)
	sync
	echo "waiting: remove the stick and power-cycle the printer"
	exit 0
}
# Step 1's frames (the ring turns) about once a second while the files on
# the stick are checked, as ad5x-install.sh does for every step; stopped
# (between two pictures) before anything else is shown and before the
# installer takes over the screen; it also ends by itself when this script
# is gone.
ANIM=
anim_stop() {
	[ -n "$ANIM" ] || return 0
	kill "$ANIM" 2>/dev/null
	wait "$ANIM" 2>/dev/null
	ANIM=
}
anim_loop() {	# OWNER NAME
	trap 'kill $sp 2>/dev/null; exit 0' TERM
	sp=
	while :; do
		for f in "$B/screens/$2.jpg" "$B/screens/$2"-[0-9]*.jpg; do
			kill -0 "$1" 2>/dev/null || exit 0
			[ -f "$f" ] && cmd_jpeg_display "$f" >/dev/null 2>&1
			sleep 1 & sp=$!
			wait $sp
		done
	done
}
screen() {
	anim_stop
	[ -f "$B/screens/$1.jpg" ] || return 0
	if [ -f "$B/screens/$1-1.jpg" ]; then
		anim_loop $$ "$1" >/dev/null 2>&1 &
		ANIM=$!
	else
		cmd_jpeg_display "$B/screens/$1.jpg" >/dev/null 2>&1
	fi
	true
}
trap anim_stop EXIT

# Our own system never runs this; if it somehow does, do nothing.
if [ -f /etc/ad5x-release ]; then
	echo "Kiln OS is running: nothing to install (use an update instead)"
	exit 1
fi
screen step1
# The board heartbeat stock starts after this hook (app_startup.sh
# sys_start.sh); the install takes a few minutes.
[ -x /usr/prog/sys_start.sh ] && /usr/prog/sys_start.sh >/dev/null 2>&1 &

if [ ! -f "$B/SHA256SUMS" ] || ! ( cd "$B" && sha256sum -c SHA256SUMS ); then
	echo "the files on the stick are incomplete or damaged (SHA256SUMS); copy them again"
	screen failed
	hold
fi
retry=
# used once: a new system that fails again must not start an install loop
[ -f "$S/ad5x-install-retry" ] && { retry=--retry; rm -f "$S/ad5x-install-retry"; sync; }
emmc="--emmc-backup $S"
[ -f "$S/ad5x-no-emmc-backup" ] && emmc=
anim_stop	# the installer shows its own screens from here
MACHINE_ARG=$1 sh "$B/ad5x-install.sh" --usb --dir "$B" $retry $emmc
rc=$?
echo "installer exit $rc"
# 0: installed, but the restart didn't happen (the installer forced it and
# then put up the switch-off-and-on screen)
[ $rc = 0 ] && echo "installed; the printer did not restart by itself"
hold
