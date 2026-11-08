#!/usr/bin/env bash
# Hold the AD5X / X2600 series to mainline's rules (README.md):
#   - checkpatch.pl --strict on every patch
#   - every commit builds on its own (bisectable), with W=1
#   - sparse (C=1) on the final tree
#   - dt_binding_check on the bindings the series touches, dtbs_check
#
#   KSRC=DIR kernel-mainline/check.sh   a development tree (v$KVER..HEAD)
#   FAST=1                              skip the per-commit builds
# Tools: sparse, and dtschema/yamllint (pip) on PATH; a missing tool fails
# the check, it is never skipped silently.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
KVER=7.3.3
KSRC=${KSRC:?set KSRC to the development tree}
TOOLBIN=${TOOLBIN:-$REPO/buildroot/output/host/bin}
O=${O:-$HOME/workspace/kernel-mainline-ad5x/check}
JOBS=${JOBS:-$(nproc)}
export PATH=$TOOLBIN:$PATH
MAKE=(make -C "$KSRC" O="$O" ARCH=mips CROSS_COMPILE=mipsel-linux- -j"$JOBS")
fail=0
bad() { echo "FAIL: $*"; fail=1; }
log() { printf '\n=== %s\n' "$*"; }

for t in sparse dt-validate yamllint; do
	command -v $t >/dev/null || bad "$t not found (see README.md, Tools)"
done
[ $fail = 0 ] || exit 1
git -C "$KSRC" diff --quiet HEAD || { echo "uncommitted changes in $KSRC"; exit 1; }
start=$(git -C "$KSRC" rev-parse --abbrev-ref HEAD)
trap 'git -C "$KSRC" checkout -q "$start"' EXIT

log "checkpatch --strict"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"; git -C "$KSRC" checkout -q "$start"' EXIT
git -C "$KSRC" format-patch -q -o "$tmp" "v$KVER..HEAD"
for p in "$tmp"/*.patch; do
	# FILE_PATH_CHANGES only guesses; MAINTAINERS coverage is checked below
	if ! "$KSRC/scripts/checkpatch.pl" --strict --quiet --ignore FILE_PATH_CHANGES \
		"$p" > "$tmp/out" 2>&1; then
		bad "$(basename "$p")"; cat "$tmp/out"
	fi
done

log "MAINTAINERS covers every added file"
for f in $(git -C "$KSRC" diff --name-only --diff-filter=A "v$KVER..HEAD"); do
	(cd "$KSRC" && ./scripts/get_maintainer.pl --no-git --no-rolestats -f "$f") |
		grep -q -v '@vger.kernel.org\|linux-kernel' || bad "no MAINTAINERS entry for $f"
done

mkdir -p "$O"
# Every commit is built with the series' final defconfig (olddefconfig drops
# what a commit does not have yet), so the X2600 code is built at each step.
# Warnings count in the files the series touches; mainline's own are not ours.
git -C "$KSRC" show HEAD:arch/mips/configs/ad5x_defconfig > "$tmp/defconfig"
touched=$(git -C "$KSRC" diff --name-only "v$KVER..HEAD" | paste -sd'|')
if [ -z "${FAST:-}" ]; then
	for c in $(git -C "$KSRC" rev-list --reverse "v$KVER..HEAD"); do
		log "build $(git -C "$KSRC" log --oneline -1 "$c")"
		git -C "$KSRC" checkout -q "$c"
		cp "$tmp/defconfig" "$O/.config"
		"${MAKE[@]}" -s olddefconfig
		"${MAKE[@]}" -s W=1 vmlinux 2> "$tmp/w" || bad "build at $c"
		grep -E 'warning:|error:' "$tmp/w" | grep -E "$touched" && bad "warnings at $c"
	done
	git -C "$KSRC" checkout -q "$start"
fi

log "sparse (C=1) on the files the series touches"
"${MAKE[@]}" -s ad5x_defconfig
"${MAKE[@]}" -s vmlinux
touch $(git -C "$KSRC" diff --name-only "v$KVER..HEAD" -- '*.c' | sed "s#^#$KSRC/#")
"${MAKE[@]}" -s C=1 vmlinux 2> "$tmp/sparse" || bad "sparse build"
grep -E 'warning:|error:' "$tmp/sparse" | grep -E "$touched" && bad "sparse warnings"

log "dt_binding_check / dtbs_check"
for y in $(git -C "$KSRC" diff --name-only "v$KVER..HEAD" -- 'Documentation/devicetree/bindings/*.yaml'); do
	"${MAKE[@]}" -s dt_binding_check DT_SCHEMA_FILES="${y#Documentation/devicetree/bindings/}" ||
		bad "dt_binding_check $y"
done
"${MAKE[@]}" -s dtbs_check 2> "$tmp/dtbs" || bad "dtbs_check"
# Known until the X2600 PDMA is supported: the UARTs have no dmas (as x1830)
grep -E 'ingenic/(x2600|ad5x)' "$tmp/dtbs" | grep -v "serial@1003[0-7]000: 'dma" &&
	bad "dtbs_check warnings"

[ $fail = 0 ] && echo "all checks passed" || { echo "checks failed"; exit 1; }
