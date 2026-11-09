# Log housekeeping. Sourced by S05ad5x-data and S61klipper.

# klippy_log_retention DIR: Klipper's dated logs (klippy.log.YYYY-MM-DD,
# from its midnight rollover) kept to at most 5 and 50 MB with klippy.log,
# oldest removed first; klippy.log and the newest dated one always stay.
# Only while Klipper is stopped: its log handler renames and deletes these
# files itself at the rollover. Its own limit (backupCount 5) counts files,
# not bytes, so a day with a flood of lines stayed on the eMMC.
klippy_log_retention() {
	total=0
	[ -f "$1/klippy.log" ] && total=$(wc -c < "$1/klippy.log")
	n=0
	for f in $(ls -1r "$1"/klippy.log.[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] 2>/dev/null); do
		n=$((n + 1))
		total=$((total + $(wc -c < "$f")))
		if [ $n -gt 1 ] && { [ $n -gt 5 ] || [ $total -gt 52428800 ]; }; then
			rm -f "$f" && echo "klipper: removed old log ${f##*/}"
		fi
	done
}

# trim_log FILE [BYTES]: keep the last BYTES (default 64 KiB) of an
# append-only log, from its first whole line on. Written in place (same
# owner, mode and inode); nothing is written while it is under the limit.
trim_log() {
	max=${2:-65536}
	[ -f "$1" ] || return 0
	[ "$(wc -c < "$1")" -gt "$max" ] || return 0
	tail -c "$max" "$1" | sed 1d > "$1.trim" && cat "$1.trim" > "$1"
	rm -f "$1.trim"
}

# Kiln's own logs that are only ever appended to: trimmed once a boot
# (S05ad5x-data). klippy.log, moonraker.log and helixscreen.log rotate on
# their own; wifi.log keeps one start (S42).
KILN_APPEND_LOGS="/data/ad5x/update/last.log /data/ad5x/recovery/update.log
/data/ad5x/mcu/log /data/ad5x/kiln-update/agent.log /data/ad5x/umask.log"
kiln_logs_trim() {
	for f in $KILN_APPEND_LOGS; do
		trim_log "$f"
	done
}
