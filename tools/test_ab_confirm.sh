#!/bin/sh
# Host test for ab_confirm (buildroot/package/ad5x-system/lib/ab.sh):
# fw_printenv/fw_setenv stubbed over a key=value file, /proc/cmdline
# replaced. Run from the repository root: tools/test_ab_confirm.sh
set -e
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
cat > "$T/bin/fw_printenv" <<'S'
#!/bin/sh
[ "$1" = -n ] && shift
v=$(sed -n "s/^$1=//p" "$ENVF" | tail -1); [ -n "$v" ] && echo "$v"; exit 0
S
cat > "$T/bin/fw_setenv" <<'S'
#!/bin/sh
# libubootenv's -s: key=value lines; lines without '=' are skipped
[ "$1" = -s ] || exit 1
grep '=' "$2" | while IFS='=' read -r k v; do
	grep -v "^$k=" "$ENVF" > "$ENVF.n" || true; echo "$k=$v" >> "$ENVF.n"; mv "$ENVF.n" "$ENVF"
done
S
chmod +x "$T/bin/"*
export PATH="$T/bin:$PATH" ENVF="$T/env"
sed "s|/proc/cmdline|$T/cmdline|g; s|/run/ad5x-ab-confirm|$T/confirm|g" \
	buildroot/package/ad5x-system/lib/ab.sh > "$T/ab.sh"
. "$T/ab.sh"
bad=0
check() {	# name cmdline env... -- expected key=value...
	name=$1 cl=$2; shift 2
	echo "$cl" > "$T/cmdline"; : > "$ENVF"
	while [ "$1" != -- ]; do echo "$1" >> "$ENVF"; shift; done; shift
	out=$(ab_confirm)
	for kv in "$@"; do
		got=$(fw_printenv -n "${kv%%=*}"); want=${kv#*=}
		[ "$got" = "$want" ] || { echo "BAD $name: ${kv%%=*} is '$got', want '$want' ($out)"; bad=1; return; }
	done
	echo "ok  $name: $out"
}
check "update confirmed" "root=x ad5x.ab=a" upgrade_available=1 bootcount=1 ustate=1 -- upgrade_available=0 bootcount=0 ustate=0
check "after a fallback: ustate 3 kept" "ad5x.ab=b" upgrade_available=0 bootcount=0 ustate=3 -- ustate=3 upgrade_available=0
check "nothing pending: nothing written" "ad5x.ab=b" ustate=0 -- ustate=0
check "1.x layout: untouched" "ad5x.ab=-" upgrade_available=1 bootcount=1 ustate=1 -- upgrade_available=1 bootcount=1 ustate=1
check "older U-Boot: untouched" "root=x" upgrade_available=1 -- upgrade_available=1
[ $bad = 0 ] && echo "all passed"; exit $bad
