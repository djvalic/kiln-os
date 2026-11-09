#!/usr/bin/env bash
# Build mainline Linux with the AD5X / Ingenic X2600 patch series.
#
#   kernel-mainline/build.sh          tree from the release tarball + patches/
#   KSRC=DIR kernel-mainline/build.sh build a development tree as it is
#                                     (git, patches committed on v$KVER)
#   JOBS=8, O=DIR                     parallelism, output directory
#   PLAIN=1                           ad5x_defconfig only, without kiln.config
#   REGDB_DIR=DIR, FW=DIR             wireless-regdb source; firmware directory
#
# The series (patches/*.patch, git format-patch output) is written to
# mainline rules: see README.md. check.sh lints it.
# Output: $O/xImage-ad5x-mainline (legacy uImage, load = entry = 0x80f00000,
# for chainload / ad5x-kernel test).
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
KVER=7.3.3
KSHA256=79c66dde66cd96877fcde8f7d36aec946b1f423d2b97b5a7b1751b75c764f3d1
WORK=${WORK:-$HOME/workspace/kernel-mainline-ad5x}
TOOLBIN=${TOOLBIN:-$REPO/buildroot/output/host/bin}
JOBS=${JOBS:-$(nproc)}
MAX_SIZE=$((8 * 1024 * 1024))	# a kernel slot, and chainload's MAX_IMAGE

log() { printf '\n=== %s\n' "$*"; }

if [ -z "${KSRC:-}" ]; then
	KSRC=$WORK/linux-$KVER
	tarball=$WORK/linux-$KVER.tar.xz
	mkdir -p "$WORK"
	if [ ! -f "$tarball" ]; then
		log "fetch linux-$KVER"
		curl -fsSL -o "$tarball.part" \
			"https://cdn.kernel.org/pub/linux/kernel/v${KVER%%.*}.x/linux-$KVER.tar.xz"
		mv "$tarball.part" "$tarball"
	fi
	echo "$KSHA256  $tarball" | sha256sum -c --quiet
	if [ ! -d "$KSRC/.git" ]; then
		log "unpack linux-$KVER"
		rm -rf "$KSRC"
		tar -xf "$tarball" -C "$WORK"
		git -C "$KSRC" init -q
		git -C "$KSRC" add -A
		git -C "$KSRC" -c user.name=build -c user.email=build@localhost \
			commit -q -m "Linux $KVER"
		git -C "$KSRC" tag "v$KVER"
	fi
	log "apply the series"
	git -C "$KSRC" checkout -q -f -B ad5x "v$KVER"
	git -C "$KSRC" clean -q -fdx
	shopt -s nullglob
	patches=("$HERE"/patches/*.patch)
	[ ${#patches[@]} -eq 0 ] || git -C "$KSRC" -c user.name=build \
		-c user.email=build@localhost am -q --keep-cr "${patches[@]}"
	git -C "$KSRC" log --oneline "v$KVER..HEAD" | cat
fi

O=${O:-$WORK/out}
export PATH=$TOOLBIN:$PATH
MAKE=(make -C "$KSRC" O="$O" ARCH=mips CROSS_COMPILE=mipsel-linux- -j"$JOBS")

mkdir -p "$O"
log "config: ad5x_defconfig"
"${MAKE[@]}" ad5x_defconfig

# Kiln OS's kernel: the board defconfig plus kiln.config (Wi-Fi with its
# firmware built in, webcams, zram...). PLAIN=1: the board defconfig only.
if [ -z "${PLAIN:-}" ]; then
	# rtw88 firmware, pinned as in kernel-ingenic66/build.sh
	FW=${FW:-$WORK/firmware}
	FW_URL=https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain
	FW_COMMIT=07338f9d33089aba6853cb7b3a1d9a8676c83580
	FW_SHA256=2ef409bc418549fcf294061dd0cae1fc22fd9da79b60524950b25de18732f3f0
	fw_bin=$FW/rtw88/rtw8821c_fw.bin
	if ! echo "$FW_SHA256  $fw_bin" | sha256sum -c --status 2>/dev/null; then
		log "fetch rtw88/rtw8821c_fw.bin (linux-firmware ${FW_COMMIT:0:12})"
		mkdir -p "$FW/rtw88"
		curl -fsSL -o "$fw_bin.tmp" "$FW_URL/rtw88/rtw8821c_fw.bin?id=$FW_COMMIT"
		if ! echo "$FW_SHA256  $fw_bin.tmp" | sha256sum -c --status; then
			echo "ERROR: rtw8821c_fw.bin sha256 mismatch: $(sha256sum "$fw_bin.tmp")"
			rm -f "$fw_bin.tmp"
			exit 1
		fi
		mv "$fw_bin.tmp" "$fw_bin"
	fi
	# regulatory.db for cfg80211, from wireless-regdb (the buildroot package
	# passes its source directory as REGDB_DIR)
	if [ -n "${REGDB_DIR:-}" ]; then
		install -m 0644 "$REGDB_DIR/regulatory.db" "$REGDB_DIR/regulatory.db.p7s" "$FW/"
	fi
	[ -f "$FW/regulatory.db" ] && [ -f "$FW/regulatory.db.p7s" ] || {
		echo "ERROR: no regulatory.db in $FW: set REGDB_DIR to the wireless-regdb source"
		exit 1
	}
	log "config: + kiln.config"
	(cd "$O" && "$KSRC/scripts/kconfig/merge_config.sh" -m -O "$O" \
		"$O/.config" "$HERE/kiln.config" >/dev/null)
	"$KSRC/scripts/config" --file "$O/.config" --set-str EXTRA_FIRMWARE_DIR "$FW"
	"${MAKE[@]}" olddefconfig
fi
log "build vmlinuz.bin"
"${MAKE[@]}" vmlinuz.bin 2>&1 | tee "$O/build.log"

# The SPL and chainload copy the payload to its load address and jump to
# it: it must be the raw self-extracting image (vmlinuz.bin), never the
# ELF file vmlinuz.
IMAGE=$O/xImage-ad5x-mainline
python3 "$HERE/tools/mkuimage.py" --load 0x80f00000 --entry 0x80f00000 \
	--name "Linux-$KVER-ad5x" "$O/arch/mips/boot/vmlinuz.bin" "$IMAGE"
size=$(stat -c %s "$IMAGE")
echo "$IMAGE: $size bytes (limit $MAX_SIZE)"
[ "$size" -le "$MAX_SIZE" ] || { echo "ERROR: larger than a kernel slot"; exit 1; }
