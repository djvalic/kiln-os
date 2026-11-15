# Klipper and Moonraker: the image's copy (/usr/lib/klipper,
# /usr/lib/moonraker) or a newer one from a daily package in
# /data/ad5x/apps/NAME (docs/updates.md). A package is used only while it
# is newer than the image's copy and the running OS is at least the
# release it was tested on (os_min in its kiln-app file); otherwise the
# image's copy runs, so an OS update with a newer Klipper wins by itself.
# Sourced by S61klipper, S62moonraker and S68ad5x-update-agent; the same
# rules are in moonraker/components/kiln_os.py.
APPS=/data/ad5x/apps

# ver_lt A B: version A is older than B. Both "vX.Y.Z-N-gHASH[-ad5x]"
# (git describe; N commits after the tag) and "vX.Y.Z[-rcN][+build]" (Kiln
# OS; a release candidate sorts below its release, rc2 below rc10)
ver_lt() {
	awk -v a="$1" -v b="$2" 'function key(v, k,  n, p) {
		sub(/^v/, "", v); sub(/\+.*/, "", v)
		n = split(v, p, /[.-]/)
		k[1] = p[1] + 0; k[2] = p[2] + 0; k[3] = p[3] + 0
		k[4] = (n >= 4 && p[4] ~ /^[0-9]+$/) ? p[4] + 0 : 0
		if (n >= 4 && p[4] ~ /^rc[0-9]+$/) k[4] = substr(p[4], 3) - 1000000
	}
	BEGIN {
		key(a, x); key(b, y)
		for (i = 1; i <= 4; i++) {
			if (x[i] < y[i]) exit 0
			if (x[i] > y[i]) exit 1
		}
		exit 1
	}'
}

os_version() { sed -n 's/^VERSION=//p' /etc/kiln-version 2>/dev/null; }

# app_sub NAME: the directory under the app root that holds the code
app_sub() { case "$1" in klipper) echo klippy ;; moonraker) echo moonraker ;; esac; }

# app_root NAME: the directory to run NAME from (holds klippy/ or moonraker/)
app_root() {
	local name=$1 sub img d min osv
	sub=$(app_sub "$name")
	img=/usr/lib/$name
	d=$APPS/$name
	if [ -f "$d/kiln-app" ] && [ -f "$d/$sub/.version" ]; then
		min=$(sed -n 's/^os_min=//p' "$d/kiln-app")
		osv=$(os_version)
		if [ -n "$osv" ] && [ -n "$min" ] && ! ver_lt "$osv" "$min" &&
		   ver_lt "$(cat "$img/$sub/.version")" "$(cat "$d/$sub/.version")"; then
			echo "$d"
			return
		fi
	fi
	echo "$img"
}
