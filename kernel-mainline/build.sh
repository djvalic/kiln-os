#!/usr/bin/env bash
# Build mainline Linux with the AD5X / Ingenic X2600 patch series.
#
#   kernel-mainline/build.sh          tree from the release tarball + patches/
#   KSRC=DIR kernel-mainline/build.sh build a development tree as it is
#                                     (git, patches committed on v$KVER)
#   JOBS=8, O=DIR                     parallelism, output directory
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
