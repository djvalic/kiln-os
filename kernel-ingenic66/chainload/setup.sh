#!/bin/bash
# Prepare a linux-5.10.186 tree whose module ABI matches the stock AD5X
# kernel (5.10.186+, vermagic "SMP preempt mod_unload MIPS32_R5 32BIT"):
#   kernel-ingenic66/chainload/setup.sh [DIR]   (default ~/workspace/chainload-build)
# Then: make -C kernel-ingenic66/chainload KDIR=DIR/linux-5.10.186
set -euo pipefail
W=${1:-$HOME/workspace/chainload-build}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
export PATH=${TOOLBIN:-$REPO/buildroot/output/host/bin}:$PATH
# The tarball's URL and sha256 are pinned in buildroot/PINS
URL=$(sed -n 's/^LINUX_510_URL=//p' "$REPO/buildroot/PINS")
SHA=$(sed -n 's/^LINUX_510_SHA256=//p' "$REPO/buildroot/PINS")
[ -n "$URL" ] && [ -n "$SHA" ] || { echo "no LINUX_510_* in buildroot/PINS" >&2; exit 1; }
mkdir -p "$W"; cd "$W"
[ -f linux-5.10.186.tar.xz ] || curl -fLO "$URL"
echo "$SHA  linux-5.10.186.tar.xz" | sha256sum -c --quiet ||
	{ echo "linux-5.10.186.tar.xz: sha256 differs from buildroot/PINS (delete it to fetch again)" >&2; exit 1; }
[ -d linux-5.10.186 ] || tar xf linux-5.10.186.tar.xz
cd linux-5.10.186
M=(make ARCH=mips CROSS_COMPILE=mipsel-linux- HOSTCFLAGS=-std=gnu11 KCFLAGS=-Wno-error)
"${M[@]}" malta_defconfig >/dev/null
# 4 KiB pages (stock: getconf PAGESIZE 4096; 16 KiB here corrupts memory),
# HIGHMEM (stock has kmap_high), 2 CPUs.
# DEBUG_SPINLOCK: stock has do_raw_spin_lock; it moves struct module's
# init to 0xe0 like stock's modules (this_module 0x180, exit at 0x16c)
./scripts/config -e CPU_MIPS32_R5 -d CPU_MIPS32_R2 -e SMP -e MIPS_MT_SMP \
	-d PREEMPT_NONE -d PREEMPT_VOLUNTARY -e PREEMPT -e MODULES -e MODULE_UNLOAD \
	-d MODVERSIONS -d MODULE_SIG -e STACKPROTECTOR -e CPU_LITTLE_ENDIAN \
	-d CPU_BIG_ENDIAN --set-str LOCALVERSION "+" -d LOCALVERSION_AUTO \
	-d FUNCTION_TRACER -d FTRACE -e DEBUG_SPINLOCK \
	-e PAGE_SIZE_4KB -d PAGE_SIZE_16KB -e HIGHMEM --set-val NR_CPUS 2
"${M[@]}" olddefconfig >/dev/null
"${M[@]}" -j"$(nproc)" modules_prepare >/dev/null
echo "ready: $PWD ($(cat include/config/kernel.release))"
