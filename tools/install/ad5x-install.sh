#!/bin/sh
# First install of Kiln OS on a Flashforge AD5X running its stock
# firmware (with or without zMod). docs/install.md has the whole procedure.
#
# usage: ad5x-install.sh [--check] [--yes] [--reboot] [--retry] [--usb]
#                        [--dir DIR] [--recovery FILE|URL] [--main FILE.zip|URL]
#                        [--sums FILE|URL] [--emmc-backup DIR] [--log FILE]
#   --check        verify only (printer, partitions, files, space); write nothing
#   --yes          don't ask before writing (SSH); implied by --usb
#   --reboot       reboot when done (SSH); implied by --usb
#   --retry        install again although an earlier attempt already switched
#                  to Kiln OS and the printer is back on stock
#   --usb          run from the install stick (flashforge_init.sh): screens on
#                  the panel, eMMC backup to the stick when it has room
#   --dir DIR      the install bundle (default: this script's directory):
#                  recovery.squashfs, ad5x-main-*.zip, SHA256SUMS, ad5x-vendor,
#                  screens/ (tools/make_install_stick.sh makes it)
#   --recovery, --main, --sums   other files (or http(s) URLs, fetched with
#                  curl/wget into /usr/data/ad5x/install/dl) instead of DIR's
#   --emmc-backup DIR   also copy the first MiB and partitions p1-p6 of the
#                  eMMC into DIR/ad5x-backup-<date>-<n> (about 1.3 GB; the
#                  format ad5x-backup/ad5x-restore use). userdata isn't copied
#   --log FILE     log here too (always: /usr/data/ad5x/install/install.log)
#
# Run as root on the stock system (stock's SSH, e.g. root/root after zMod,
# not inside zMod's chroot), or from the install stick. Steps:
#   1. checks: an AD5X (device tree ingenic,x2600, MACHINE=AD5X), the eMMC
#      layout the boot loader expects (docs/boot-slots.md), stock running in
#      the slot the boot flag names, the stock kernel there, free space,
#      the files' sha256s. Nothing is written before all checks pass.
#   2. stock's root and kernel -> /usr/data/ad5x/stock (rootfs.squashfs,
#      kernel.img, SHA256SUMS; ad5x-restore-stock puts them back)
#   3. the vendor files (Flashforge/Ingenic drivers and board tools) of the
#      running stock system -> /usr/data/ad5x/vendor (ad5x-vendor extract:
#      MANIFEST, SHA256SUMS). Releases don't contain them.
#   4. the idle slot is written and read back: stock in slot A (the usual
#      case) -> the main OS into slot B; stock in slot B -> the recovery OS
#      into slot A. Its kernel partition gets the printer's own stock kernel
#      (copied from the running slot), never a kernel from the release.
#   5. the other image is left for the first start: recovery.squashfs in
#      /usr/data/ad5x/install (the main OS writes it into slot A once it has
#      started completely, S99ad5x-install-recovery), or the main .zip in
#      /usr/data/ad5x/update (the recovery OS installs it at its first start)
#   6. the boot flag is set to the written slot (last), then reboot.
# State in /usr/data/ad5x/install/state; a second run is safe (finished steps
# are checked, not repeated blindly). Exit status: 0 done (or check OK),
# 1 failed, 2 usage, 3 refused (not an AD5X, not stock, already installed).
#
# Test overrides: AD5X_SYS AD5X_DEV AD5X_CMDLINE AD5X_MOUNTS AD5X_DT
# AD5X_USERDATA AD5X_ROOT AD5X_APP_STARTUP AD5X_TMP.
: "${AD5X_SYS:=/sys}" "${AD5X_DEV:=/dev}" "${AD5X_CMDLINE:=/proc/cmdline}"
: "${AD5X_MOUNTS:=/proc/mounts}" "${AD5X_DT:=/proc/device-tree}"
: "${AD5X_USERDATA:=/usr/data}" "${AD5X_ROOT:=}" "${AD5X_TMP:=/tmp/ad5x-install}"
: "${AD5X_APP_STARTUP:=/usr/prog/app_startup.sh}"
export AD5X_SYS AD5X_DEV AD5X_CMDLINE

check= yes= reboot_after= retry= usb= DIR= RECOVERY= MAIN= SUMS= EMMC= XLOG=
while [ $# -gt 0 ]; do
	case "$1" in
	--check) check=1 ;;
	--yes) yes=1 ;;
	--reboot) reboot_after=1 ;;
	--retry) retry=1 ;;
	--usb) usb=1 yes=1 reboot_after=1 ;;
	--dir) DIR=$2; shift ;;
	--recovery) RECOVERY=$2; shift ;;
	--main) MAIN=$2; shift ;;
	--sums) SUMS=$2; shift ;;
	--emmc-backup) EMMC=$2; shift ;;
	--log) XLOG=$2; shift ;;
	-h|--help) sed -n '2,49p' "$0"; exit 0 ;;
	*) sed -n '2,49p' "$0" >&2; exit 2 ;;
	esac
	shift
done
[ -n "$DIR" ] || DIR=$(cd "$(dirname "$0")" && pwd)
U=$AD5X_USERDATA
I=$U/ad5x/install
STOCK=$U/ad5x/stock
VENDOR=$U/ad5x/vendor
T=$AD5X_TMP
mkdir -p "$T"
[ -n "$check" ] || mkdir -p "$I"
LOG=$T/install.log
[ -n "$check" ] || LOG=$I/install.log

log() { echo "$*"; echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; [ -n "$XLOG" ] && echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$XLOG"; true; }
SCREENS=$DIR/screens
show() {	# screen name (screens/NAME.jpg), only with --usb
	[ -n "$usb" ] && [ -f "$SCREENS/$1.jpg" ] && [ -e "$AD5X_DEV/fb0" ] || return 0
	cmd_jpeg_display "$SCREENS/$1.jpg" >/dev/null 2>&1
	true
}
fail() { log "FAILED: $*"; show failed; exit 1; }
refuse() { log "NOT INSTALLED: $*"; show "${REFUSE_SCREEN:-refused}"; exit 3; }
step() { STEP=$1; log "== step $1/6: $2"; show "step$1"; }

part() {	# GPT name -> device
	for u in "$AD5X_SYS"/class/block/*/uevent; do
		grep -qx "PARTNAME=$1" "$u" 2>/dev/null || continue
		echo "$AD5X_DEV/$(sed -n 's/^DEVNAME=//p' "$u")"; return 0
	done
	return 1
}
part_sys() {
	for u in "$AD5X_SYS"/class/block/*/uevent; do
		grep -qx "PARTNAME=$1" "$u" 2>/dev/null && { echo "${u%/uevent}"; return 0; }
	done
	return 1
}
part_bytes() { s=$(part_sys "$1") && echo $(( $(cat "$s/size") * 512 )); }
sha() { sha256sum "$1" | cut -d' ' -f1; }
sha_n() { head -c "$2" "$1" | sha256sum | cut -d' ' -f1; }
fsize() { wc -c < "$1" | tr -d ' '; }
mounted() { grep -q "^$1 " "$AD5X_MOUNTS"; }
drop_caches() { sync; { echo 3 > /proc/sys/vm/drop_caches; } 2>/dev/null; true; }
# hex of COUNT bytes at OFFSET (stock's BusyBox od has no -t/-A: hexdump)
hexat() { hexdump -v -s "$2" -n "$3" -e '1/1 "%02x"' "$1" 2>/dev/null; }
uimage_len() {
	[ "$(hexat "$1" 0 4)" = 27051956 ] || return 1
	echo $(( 0x$(hexat "$1" 12 4) + 64 ))
}
squashfs_used() {	# superblock bytes_used, 64-bit little endian at 40 (< 4 GiB here)
	h=$(hexat "$1" 40 8)
	[ ${#h} = 16 ] && [ "${h#????????}" = 00000000 ] || { echo 0; return 1; }
	echo $(( 0x$(echo "$h" | cut -c7-8)$(echo "$h" | cut -c5-6)$(echo "$h" | cut -c3-4)$(echo "$h" | cut -c1-2) ))
}
read_flag() { head -c 11 "$(part ota)" 2>/dev/null | tr -d '\0\n'; }
free_kb() { df -Pk "$1" 2>/dev/null | awk 'NR == 2 { print $4 }'; }

# Partition table compiled into the boot loader (docs/boot-slots.md)
SPL="kernel:2048:16384 rootfs:18432:204800 kernel2:223232:16384
rootfs2:239616:204800 ota:444416:2048 usershare:446464:2097152
userdata:2543616:12238848"

fetch() {	# FILE|URL -> local path
	case "$1" in
	http://*|https://*)
		mkdir -p "$I/dl"; f=$I/dl/${1##*/}
		log "downloading $1"
		if [ -x /usr/prog/curl-7.55.1-https/bin/curl ]; then
			/usr/prog/curl-7.55.1-https/bin/curl -kfsSL -o "$f" "$1"
		elif command -v curl >/dev/null; then curl -fsSL -o "$f" "$1"
		else wget -q -O "$f" "$1"
		fi || fail "download of $1"
		echo "$f" ;;
	*) echo "$1" ;;
	esac
}

log "=== Kiln OS installer $(cat "$DIR/VERSION" 2>/dev/null) ${check:+(check only)}${usb:+ (USB)}"
log "bundle: $DIR"

# ---------------------------------------------------------------- 1. checks
step 1 "checking the printer and the files"
[ "$(id -u)" = 0 ] || refuse "run as root"
# Not inside zMod's chroot (its own SSH): the stock root must be / here
if [ -z "$AD5X_ROOT" ] && [ -d /proc/1/root ]; then
	[ "$(ls -id / | awk '{print $1}')" = "$(ls -id /proc/1/root/ | awk '{print $1}')" ] ||
		refuse "this shell is inside a chroot (zMod's SSH?); log in to stock's SSH (port 22, root) instead"
fi
compat=$(tr '\0' ' ' < "$AD5X_DT/compatible" 2>/dev/null)
case "$compat" in *x2600*) ;; *) refuse "not an AD5X: device tree '$compat' (expected ingenic,x2600)" ;; esac
machine=${MACHINE_ARG:-$(sed -n 's/^MACHINE=//p' "$AD5X_APP_STARTUP" 2>/dev/null | head -1)}
[ "$machine" = AD5X ] || refuse "not an AD5X: stock's machine name is '${machine:-unknown}'"
for e in $SPL; do
	n=${e%%:*} r=${e#*:}
	s=$(part_sys "$n") || refuse "no eMMC partition '$n' (layout differs from the AD5X's)"
	# userdata is the last partition and is found through the GPT, not the
	# boot loader: a different size (stock 3.1.6 printers) is only logged.
	# Its start, and every other partition, must match exactly.
	if [ "$(cat "$s/start"):$(cat "$s/size")" != "$r" ]; then
		if [ "$n" = userdata ] && [ "$(cat "$s/start")" = "${r%%:*}" ]; then
			log "note: userdata is $(cat "$s/start"):$(cat "$s/size") (expected $r); the boot loader does not read it, so continuing"
		else
			refuse "partition $n at $(cat "$s/start"):$(cat "$s/size"), the boot loader expects $r (docs/boot-slots.md)"
		fi
	fi
done
log "AD5X: device tree '$compat', eMMC layout matches the boot loader"

root=$(sed -n 's/.*root=\([^ ]*\).*/\1/p' "$AD5X_CMDLINE")
case "${root##*/}" in
"$(basename "$(part rootfs)")") RUN=A IDLE=B ;;
"$(basename "$(part rootfs2)")") RUN=B IDLE=A ;;
*) refuse "running root '$root' is neither rootfs (p2) nor rootfs2 (p4)" ;;
esac
if [ -f "$AD5X_ROOT/etc/ad5x-release" ]; then
	REFUSE_SCREEN=installed
	refuse "this printer already runs Kiln OS ($(cat "$AD5X_ROOT/etc/ad5x-release")): update it instead (docs/recovery-os.md, ad5x-update)"
fi
[ -f "$AD5X_ROOT/etc/ota_bin/ota_local_method.sh" ] || [ -d "$AD5X_ROOT/module_driver" ] ||
	refuse "the running system doesn't look like the stock firmware (no /etc/ota_bin, no /module_driver)"
# earlier attempts
st=$(sed -n 's/^state=//p' "$I/state" 2>/dev/null)
case "$st" in
flag-set|done)
	[ -n "$retry" ] || refuse "an earlier install already switched to Kiln OS (state '$st', $I/install.log), and the printer is running stock again: the new system didn't finish starting, or stock was put back. To install again anyway: --retry (USB: put a file ad5x-install-retry on the stick)" ;;
esac
[ -n "$st" ] && log "earlier attempt stopped at '$st'; continuing"

flag=$(read_flag)
# the boot loader starts slot B on "ota:kernel2" and slot A on anything else
case $RUN in A) [ "$flag" != ota:kernel2 ] ;; B) [ "$flag" = ota:kernel2 ] ;; esac ||
	refuse "boot flag '$flag' doesn't name the running slot $RUN (a stock update pending?); restart first"
if [ $RUN = A ]; then
	RUNROOT=$(part rootfs) RUNKERN=$(part kernel) DSTROOT=$(part rootfs2) DSTKERN=$(part kernel2)
	DSTNAME=rootfs2 WHAT=main FLAG=ota:kernel2
else
	RUNROOT=$(part rootfs2) RUNKERN=$(part kernel2) DSTROOT=$(part rootfs) DSTKERN=$(part kernel)
	DSTNAME=rootfs WHAT=recovery FLAG=ota:kernel
fi
log "stock runs from slot $RUN ($RUNROOT), boot flag '$flag'; slot $IDLE gets the $WHAT OS"
mounted "$DSTROOT" && refuse "$DSTROOT (slot $IDLE) is mounted"
KLEN=$(uimage_len "$RUNKERN") || refuse "no kernel (uImage) in $RUNKERN, the running slot's kernel partition"
[ "$KLEN" -le "$(part_bytes kernel)" ] || refuse "kernel in $RUNKERN claims $KLEN bytes"
log "stock kernel: $KLEN bytes in $RUNKERN (sha256 $(sha_n "$RUNKERN" "$KLEN" | cut -c1-16)...), copied to slot $IDLE's kernel partition"
zmod=
for z in "$U/zmod/zmod" "$U/.mod/.zmod" "$U/config/mod"; do [ -e "$z" ] && zmod="$zmod ${z#$U/}"; done
zmod=${zmod# }
if [ -n "$zmod" ]; then log "zMod: found ($zmod); its files on /usr/data stay, the main OS reads its settings"
else log "zMod: not installed (not needed)"
fi

# the files
RECOVERY=$(fetch "${RECOVERY:-$DIR/recovery.squashfs}") || exit 1
if [ -z "$MAIN" ]; then
	set -- "$DIR"/ad5x-main-*.zip
	[ $# -eq 1 ] && [ -f "$1" ] || refuse "need exactly one ad5x-main-*.zip in $DIR (or --main)"
	MAIN=$1
fi
MAIN=$(fetch "$MAIN") || exit 1
[ -n "$SUMS" ] || { [ -f "$DIR/SHA256SUMS" ] && SUMS=$DIR/SHA256SUMS; }
if [ -n "$SUMS" ]; then
	SUMS=$(fetch "$SUMS") || exit 1
	for f in "$RECOVERY" "$MAIN"; do
		w=$(grep " \*\{0,1\}\(.*/\)\{0,1\}${f##*/}\$" "$SUMS" | head -1 | cut -d' ' -f1)
		[ -n "$w" ] || refuse "${f##*/} isn't listed in $SUMS"
		[ "$(sha "$f")" = "$w" ] || refuse "${f##*/} is damaged (sha256 differs from $SUMS)"
	done
	log "files match $SUMS"
else
	log "WARNING: no SHA256SUMS: the files are only checked by their own contents"
fi
[ "$(head -c 4 "$RECOVERY")" = hsqs ] || refuse "$RECOVERY is not a squashfs image"
RSIZE=$(fsize "$RECOVERY")
[ "$RSIZE" -le "$(part_bytes rootfs)" ] || refuse "recovery image $RSIZE bytes > slot"
[ "$(hexat "$MAIN" 0 4)" = 504b0304 ] || refuse "$MAIN is not a .zip update"
list=$(unzip -l "$MAIN" 2>/dev/null)
echo "$list" | grep -q ' rootfs.squashfs$' || refuse "$MAIN has no rootfs.squashfs"
echo "$list" | grep -q ' SHA256SUMS$' || refuse "$MAIN has no SHA256SUMS"
echo "$list" | grep -q ' kernel.uimage$' &&
	refuse "$MAIN carries a kernel; the installer only takes releases without one (the printer keeps its own)"
MSHA=$(unzip -p "$MAIN" SHA256SUMS | awk '$2 == "rootfs.squashfs" || $2 == "*rootfs.squashfs" { print $1 }')
[ -n "$MSHA" ] || refuse "$MAIN's SHA256SUMS doesn't list rootfs.squashfs"
MSIZE=$(unzip -l "$MAIN" | awk '$4 == "rootfs.squashfs" { print $1 }')
[ -n "$MSIZE" ] && [ "$MSIZE" -le "$(part_bytes rootfs2)" ] || refuse "main rootfs ${MSIZE:-?} bytes doesn't fit the slot"
[ -f "$DIR/ad5x-vendor" ] || refuse "no ad5x-vendor next to the installer ($DIR)"
log "recovery: $RSIZE bytes; main: rootfs $MSIZE bytes (sha256 ${MSHA%${MSHA#????????????????}}...), no kernel"

# space on userdata: stock copy, vendor files, staged images
used=$(squashfs_used "$RUNROOT")
need=$(( (used + $(part_bytes kernel) + 4194304 + RSIZE + MSIZE + $(fsize "$MAIN") + 33554432) / 1024 ))
have=$(free_kb "$U")
[ -n "$have" ] || refuse "can't read the free space of $U"
[ -f "$STOCK/SHA256SUMS" ] && need=$((need - used / 1024))
# stock in B: the recovery OS unpacks the update zip on /data at its first start
[ $RUN = B ] && need=$((need + 2 * MSIZE / 1024))
[ "$have" -ge "$need" ] || refuse "$U has $((have / 1024)) MiB free, needs $((need / 1024)) MiB"
log "space: $U has $((have / 1024)) MiB free, needs about $((need / 1024)) MiB"

if [ -n "$check" ]; then
	log "CHECK OK: would save stock to $STOCK, copy the vendor files to $VENDOR, write the $WHAT OS into slot $IDLE ($DSTROOT + stock kernel to $DSTKERN), set the boot flag to '$FLAG'"
	exit 0
fi
if [ -z "$yes" ]; then
	printf 'Write Kiln OS into slot %s (stock is saved first)? Type YES: ' "$IDLE"
	read -r a; [ "$a" = YES ] || { log "cancelled"; exit 1; }
fi
echo "state=checked" > "$I/state"

# ---------------------------------------------------------------- 2. backup
step 2 "saving the stock system"
RSHA=$(sha_n "$RUNROOT" "$used")
if [ -f "$STOCK/SHA256SUMS" ] && grep -q "^$RSHA  rootfs.squashfs\$" "$STOCK/SHA256SUMS" &&
		( cd "$STOCK" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ); then
	log "stock already saved in $STOCK (rootfs $RSHA)"
else
	if [ -d "$STOCK" ]; then
		n=1; while [ -e "$STOCK.prev-$n" ]; do n=$((n + 1)); done
		mv "$STOCK" "$STOCK.prev-$n"; log "an older, different stock copy moved to $STOCK.prev-$n"
	fi
	mkdir -p "$STOCK.new"
	head -c "$used" "$RUNROOT" > "$STOCK.new/rootfs.squashfs" || fail "copying stock's root"
	cat "$RUNKERN" > "$STOCK.new/kernel.img" || fail "copying stock's kernel"
	sync; drop_caches
	( cd "$STOCK.new" && sha256sum rootfs.squashfs kernel.img > SHA256SUMS )
	[ "$(sha "$STOCK.new/rootfs.squashfs")" = "$RSHA" ] || fail "stock root copy reads back wrong"
	{ echo "stock system saved by ad5x-install.sh, $(date)"; echo "from slot $RUN: $RUNROOT ($used bytes), $RUNKERN"
	  cat "$AD5X_ROOT/etc/ota_info" 2>/dev/null; } > "$STOCK.new/MANIFEST.txt"
	mv "$STOCK.new" "$STOCK" && sync
	log "stock saved: $(tr '\n' ' ' < "$STOCK/SHA256SUMS")"
fi
echo "state=backed-up" > "$I/state"
if [ -n "$EMMC" ]; then
	disk=$AD5X_DEV/$(basename "$(readlink -f "$(part_sys rootfs)/..")")
	parts="boot kernel rootfs kernel2 rootfs2 ota usershare"
	total=1048576
	for n in $parts; do [ $n = boot ] || total=$((total + $(part_bytes $n))); done
	efree=$(free_kb "$EMMC")
	if [ -z "$efree" ] || [ $((total / 1024 + 65536)) -gt "$efree" ]; then
		log "eMMC backup skipped: $EMMC has $(( ${efree:-0} / 1024 )) MiB free, needs $((total / 1048576 + 64)) MiB (optional; docs/emmc-backup.md)"
	else
		i=1; while [ -e "$EMMC/ad5x-backup-install-$i" ]; do i=$((i + 1)); done
		O=$EMMC/ad5x-backup-install-$i; mkdir -p "$O"
		{ echo "AD5X eMMC backup (ad5x-install.sh), $(date)"; echo "running root: $root, slot $RUN"
		  echo "boot flag: $flag"; echo "disk: $disk"; echo "userdata not copied (mounted, too big)"
		  echo "# name device start_sector bytes sha256 files"; } > "$O/MANIFEST.txt"
		: > "$O/SHA256SUMS"; ok=1
		for n in $parts; do
			if [ $n = boot ]; then dev=$disk b=1048576 start=0
			else dev=$(part $n) b=$(part_bytes $n) start=$(cat "$(part_sys $n)/start"); fi
			s=$(head -c "$b" "$dev" | tee "$O/$n.img" | sha256sum | cut -d' ' -f1)
			sync
			[ "$(fsize "$O/$n.img")" = "$b" ] && [ "$(sha "$O/$n.img")" = "$s" ] || { ok=; log "eMMC backup: $n failed"; break; }
			echo "$s  $n.img" >> "$O/SHA256SUMS"
			echo "$n $dev $start $b $s $n.img" >> "$O/MANIFEST.txt"
			log "eMMC backup: $n OK"
		done
		[ -n "$ok" ] && log "eMMC backup: $O (keep it on a computer)" || log "eMMC backup incomplete (optional; installing anyway)"
	fi
fi

# ---------------------------------------------------------------- 3. vendor files
step 3 "copying the printer's own drivers and board tools"
SR=$T/stockroot
mkdir -p "$SR"
src=/ how="running system"
# a fresh read-only view of the root (no zMod bind mounts over it)
if mount -t squashfs -o ro "$RUNROOT" "$SR" 2>/dev/null; then src=$SR how="stock root $RUNROOT"
else log "can't mount $RUNROOT a second time, reading the files from /"
fi
[ -n "$AD5X_ROOT" ] && [ "$src" = / ] && src=$AD5X_ROOT
sh "$DIR/ad5x-vendor" extract "$src" "$VENDOR" "$how (slot $RUN), ad5x-install.sh" >> "$LOG" 2>&1
rc=$?
[ "$src" = "$SR" ] && umount "$SR"
[ $rc = 0 ] || fail "copying the vendor files (see the log)"
log "vendor files in $VENDOR: $(wc -l < "$VENDOR/SHA256SUMS") files"
echo "state=vendor" > "$I/state"

# ---------------------------------------------------------------- 4. idle slot
step 4 "writing the $WHAT OS into slot $IDLE"
if [ $WHAT = main ]; then
	IMG=$I/main.squashfs
	if [ ! -f "$IMG" ] || [ "$(sha "$IMG")" != "$MSHA" ]; then
		unzip -p "$MAIN" rootfs.squashfs > "$IMG" || fail "unpacking the main OS"
		[ "$(sha "$IMG")" = "$MSHA" ] || { rm -f "$IMG"; fail "main OS in the zip is damaged"; }
	fi
	ISHA=$MSHA
else
	IMG=$RECOVERY ISHA=$(sha "$RECOVERY")
fi
ISIZE=$(fsize "$IMG")
# kernel: the printer's own, from the running slot
if [ "$(sha_n "$DSTKERN" "$KLEN")" != "$(sha_n "$RUNKERN" "$KLEN")" ]; then
	head -c "$KLEN" "$RUNKERN" > "$T/kernel" || fail "reading the stock kernel"
	dd if="$T/kernel" of="$DSTKERN" bs=65536 conv=notrunc 2>/dev/null || fail "writing the kernel to $DSTKERN"
	drop_caches
	[ "$(sha_n "$DSTKERN" "$KLEN")" = "$(sha "$T/kernel")" ] || fail "$DSTKERN reads back wrong"
	rm -f "$T/kernel"
	log "stock kernel copied to $DSTKERN"
else
	log "$DSTKERN already holds the stock kernel"
fi
if [ "$(sha_n "$DSTROOT" "$ISIZE")" = "$ISHA" ]; then
	log "$DSTROOT already holds this image"
else
	dd if="$IMG" of="$DSTROOT" bs=1048576 conv=notrunc 2>/dev/null || fail "writing $DSTROOT"
	drop_caches
	got=$(sha_n "$DSTROOT" "$ISIZE")
	[ "$got" = "$ISHA" ] || fail "$DSTROOT reads back $got, image $ISHA"
	log "$DSTROOT written and read back ($ISIZE bytes)"
fi
M=$T/check
mkdir -p "$M"
if mount -t squashfs -o ro "$DSTROOT" "$M" 2>/dev/null; then
	ok=1
	[ -f "$M/etc/ad5x-release" ] && { [ -e "$M/linuxrc" ] || [ -L "$M/linuxrc" ]; } || ok=
	if [ $WHAT = recovery ]; then [ -f "$M/etc/ad5x-recovery" ] || ok=
	else [ ! -f "$M/etc/ad5x-recovery" ] || ok=; fi
	rel=$(cat "$M/etc/ad5x-release" 2>/dev/null)
	umount "$M"
	[ -n "$ok" ] || fail "$DSTROOT doesn't hold the $WHAT OS after writing"
	log "slot $IDLE: $rel"
else
	fail "$DSTROOT doesn't mount as squashfs after writing"
fi
[ $WHAT = main ] && rm -f "$IMG"
echo "state=slot-written" > "$I/state"

# ---------------------------------------------------------------- 5. stage the other image
step 5 "preparing the first start"
if [ $WHAT = main ]; then
	cp "$RECOVERY" "$I/recovery.squashfs.part" && mv "$I/recovery.squashfs.part" "$I/recovery.squashfs" || fail "copying the recovery image"
	sync
	[ "$(sha "$I/recovery.squashfs")" = "$(sha "$RECOVERY")" ] || fail "recovery image copy reads back wrong"
	sha "$I/recovery.squashfs" > "$I/recovery.sha256"
	rm -f "$I/recovery.tries"
	log "recovery image left in $I: the main OS writes it into slot A once it has started"
else
	mkdir -p "$U/ad5x/update"
	z=$U/ad5x/update/${MAIN##*/}
	cp "$MAIN" "$z.part" && mv "$z.part" "$z" || fail "copying the main OS update"
	sync
	[ "$(sha "$z")" = "$(sha "$MAIN")" ] || fail "update copy reads back wrong"
	log "main OS update left in $U/ad5x/update: the recovery OS installs it into slot B at its first start"
fi
echo "state=staged" > "$I/state"

# ---------------------------------------------------------------- 6. boot flag
step 6 "switching to the new system"
echo "$FLAG" > "$(part ota)" && sync
drop_caches
[ "$(read_flag)" = "$FLAG" ] || fail "boot flag reads back '$(read_flag)', not '$FLAG'"
echo "state=flag-set" > "$I/state"
log "boot flag '$FLAG': the next start runs slot $IDLE"
log "DONE. Going back to stock later: ad5x-restore-stock (recovery OS), see docs/install.md"
show done
if [ -n "$reboot_after" ]; then
	log "rebooting"
	sync; sleep 3
	reboot
else
	log "reboot to start Kiln OS"
fi
exit 0
