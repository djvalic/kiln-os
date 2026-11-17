# Safe mode: Kiln's U-Boot starts the main OS with ad5x.safe=1 when no slot
# finished starting (u-boot/README.md, "Boot rules"). Then only what it takes
# to repair the printer runs: /data checked, network, SSH, a screen saying so
# and ad5x-safe. Klipper, Moonraker, the web UI, plugins and the camera stay
# off, so a broken config or plugin can't stop the system again.
# AD5X_SAFE=1|0 overrides the command line (tests).
safe_mode() {
	case "${AD5X_SAFE:-}" in
	1) return 0 ;;
	0) return 1 ;;
	esac
	case " $(cat /proc/cmdline 2>/dev/null) " in
	*" ad5x.safe=1 "*) return 0 ;;
	esac
	return 1
}

# in an init script's start): "safe_skip NAME" ends it in safe mode
safe_skip() {
	safe_mode || return 1
	echo "$1: safe mode: not started"
	exit 0
}
