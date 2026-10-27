#!/usr/bin/env bash
# Build the Ingenic X2600 SDK Linux 6.6 kernel for the Flashforge AD5X.
#
#   kernel-ingenic66/build.sh   defconfig + fragment, zImage + modules, uImage
#   JOBS=8 kernel-ingenic66/build.sh     parallelism (default: nproc)
#   NO_CONFIG=1 kernel-ingenic66/build.sh  keep the existing out-ad5x/.config
#
# Touches the SDK kernel tree only by (idempotently):
#   - copying ad5x.dts + ad5x-display.dtsi into module_drivers/dts/x2600/
#   - copying panel-kx070.c into module_drivers/.../ingenic/displays/
#   - applying patches/0001-* (Kconfig/Makefile hook for the panel)
#   SDK=DIR                   Ingenic SDK checkout (default ~/workspace/ingenic-sdk-6.6,
#                             github.com/Llixuma/ingenic-linux-kernel6.6-x2000-v1.0-20250221)
# Output: $SDK/out-ad5x/xImage-ad5x-6.6 (legacy uImage, load=entry=0x80f00000)
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=${REPO:-$(cd "$HERE/.." && pwd)}
SDK=${SDK:-$HOME/workspace/ingenic-sdk-6.6}
KSRC=${KSRC:-$SDK/kernel/kernel-6.6}
OUT=${OUT:-$SDK/out-ad5x}
TOOLBIN=${TOOLBIN:-$REPO/buildroot/output/host/bin}
JOBS=${JOBS:-$(nproc)}
IMAGE=$OUT/xImage-ad5x-6.6
MAX_SIZE=$((8 * 1024 * 1024))	# SPL limit for a kernel slot

export PATH=$TOOLBIN:$PATH
MAKE=(make -C "$KSRC" O="$OUT" ARCH=mips CROSS_COMPILE=mipsel-linux-
      HOSTCFLAGS="-Wno-error=incompatible-pointer-types -std=gnu11")

log() { printf '\n=== %s\n' "$*"; }

log "sync AD5X files into $KSRC"
install -m 0644 "$HERE/ad5x.dts" "$HERE/ad5x-display.dtsi" \
	"$KSRC/module_drivers/dts/x2600/"
install -m 0644 "$HERE/panel-kx070.c" \
	"$KSRC/module_drivers/drivers/video/fbdev/ingenic/displays/"
for p in "$HERE"/patches/*.patch; do
	[ -e "$p" ] || continue
	if patch -d "$KSRC" -p1 -R --dry-run -s -f <"$p" >/dev/null 2>&1; then
		echo "already applied: $(basename "$p")"
	else
		patch -d "$KSRC" -p1 -N -s <"$p"
		echo "applied: $(basename "$p")"
	fi
done

# DIAG=1: the test-only MIPS diagnostics (diag/), which need OUT set to a separate dir
if [ -n "${DIAG:-}" ]; then
	log "diagnostics: diag/ad5x-diag.c and its hooks"
	install -m 0644 "$HERE/diag/ad5x-diag.c" "$KSRC/arch/mips/kernel/"
	for p in "$HERE"/diag/*.patch; do
		[ -e "$p" ] || continue
		if patch -d "$KSRC" -p1 -R --dry-run -s -f <"$p" >/dev/null 2>&1; then
			echo "already applied: $(basename "$p")"
		else
			patch -d "$KSRC" -p1 -N -s <"$p"
			echo "applied: $(basename "$p")"
		fi
	done
fi

# Wi-Fi firmware for the built-in rtw88 (linux-firmware, redistributable)
FW=$SDK/firmware
FW_URL=https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain
if [ ! -s "$FW/rtw88/rtw8821c_fw.bin" ]; then
	log "fetch rtw88/rtw8821c_fw.bin (linux-firmware)"
	mkdir -p "$FW/rtw88"
	curl -fsSL -o "$FW/rtw88/rtw8821c_fw.bin" "$FW_URL/rtw88/rtw8821c_fw.bin"
fi

# regulatory.db for cfg80211 (built in: see ad5x.config). The buildroot package
# passes the wireless-regdb source directory as REGDB_DIR.
REGDB_DIR=${REGDB_DIR:?set REGDB_DIR to the wireless-regdb source dir}
install -m 0644 "$REGDB_DIR/regulatory.db" "$REGDB_DIR/regulatory.db.p7s" "$FW/"

mkdir -p "$OUT"
if [ -z "${NO_CONFIG:-}" ]; then
	log "config: x2600_halley7_linux_defconfig + ad5x.config"
	"${MAKE[@]}" x2600_halley7_linux_defconfig
	# merge_config.sh -m: merge only; then olddefconfig resolves deps
	(cd "$OUT" && "$KSRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" \
		"$OUT/.config" "$HERE/ad5x.config" ${DIAG:+"$HERE/diag/diag.config"})
	"$KSRC/scripts/config" --file "$OUT/.config" --set-str EXTRA_FIRMWARE_DIR "$FW"
	"${MAKE[@]}" olddefconfig
	# Report fragment options that did not survive (missing/unmet deps)
	log "fragment check"
	missing=0
	while IFS= read -r line; do
		case "$line" in
		CONFIG_*=*) sym=${line%%=*}; want=${line#*=} ;;
		"# CONFIG_"*" is not set") sym=${line#\# }; sym=${sym%% *}; want=n ;;
		*) continue ;;
		esac
		have=$(grep -E "^$sym=" "$OUT/.config" | head -1 | cut -d= -f2- || true)
		[ -z "$have" ] && have=n
		[ "$want" = '""' ] && [ "$have" = n ] && continue	# empty string == unset
		if [ "$have" != "$want" ]; then
			echo "  $sym: wanted $want, got $have"
			missing=1
		fi
	done <"$HERE/ad5x.config"
	[ $missing = 0 ] && echo "  all fragment options applied"
fi

log "build zImage + modules (-j$JOBS)"
"${MAKE[@]}" -j"$JOBS" zImage modules 2>&1 | tee "$OUT/build-ad5x.log"
rc=${PIPESTATUS[0]}
[ "$rc" = 0 ] || { echo "build failed ($rc), see $OUT/build-ad5x.log"; exit "$rc"; }

log "DTC warnings for ad5x"
grep -E "ad5x.*[Ww]arning" "$OUT/build-ad5x.log" || echo "  none"

# The release string is what S00 records and compares (failed/last-ok), so a
# quick and a full build must agree on it. It comes from the SDK tree's
# localversion-rt plus CONFIG_LOCALVERSION; pin it here so a changed SDK checkout
# fails the build instead of silently changing the string.
EXPECT_RELEASE=${EXPECT_RELEASE:-6.6.18-rt23-ad5x}
got_release=$(cat "$OUT/include/config/kernel.release")
if [ "$got_release" != "$EXPECT_RELEASE" ]; then
	echo "ERROR: kernel release is '$got_release', expected '$EXPECT_RELEASE'"
	echo "  (set EXPECT_RELEASE if the SDK's localversion-rt changed on purpose)"
	exit 1
fi
echo "kernel release: $got_release"

ZIMAGE=$OUT/arch/mips/boot/compressed/zImage
log "uImage"
python3 "$REPO/kernel-mainline/tools/mkuimage.py" --load 0x80f00000 --entry 0x80f00000 \
	--name "Linux-6.6-ad5x" "$ZIMAGE" "$IMAGE"

size=$(stat -c %s "$IMAGE")
printf '%s: %d bytes (%.2f MiB), limit %d\n' "$IMAGE" "$size" \
	"$(echo "$size / 1048576" | bc -l)" "$MAX_SIZE"
if [ "$size" -gt "$MAX_SIZE" ]; then
	echo "ERROR: image exceeds the 8 MiB kernel slot"
	exit 1
fi
ls -l "$OUT/vmlinux" "$ZIMAGE" "$IMAGE"
