#!/bin/bash
# Build Klipper MCU firmware for the AD5X mainboard, eboard and IFS (Nations N32G455).
#
# usage: tools/build_mcu.sh [mainline|xblax] [klipper checkout]
#   mainline (default): upstream Klipper plus klipper/mcu-patches (eboard
#                       restart and bootloader request, from xblax/klipper;
#                       IFS RS-485 and bootloader),
#                       klipper/mcu-configs/ad5x-<board>.mainline.config
#                       (mainline only: the IFS)
#   xblax:              xblax/klipper (AD5M mod fork), klipper/mcu-configs/ad5x-<board>.config
#   The checkout defaults to firmware/builds/klipper-<source>.
# Output: firmware/builds/<version>/{mainboard.bin,eboard.hex,ifs.hex,*.dict}
# Needs arm-none-eabi-gcc and arm-none-eabi-newlib.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
SOURCE=${1:-mainline}
case "$SOURCE" in
    mainline)
        KLIPPER_URL=https://github.com/Klipper3d/klipper
        KLIPPER_REV=9cb99754c   # v0.13.0-800, first release line with N32G45x at 144 MHz
        SUFFIX=.mainline ;;
    xblax)
        KLIPPER_URL=https://github.com/xblax/klipper
        KLIPPER_REV=fc2aaae69   # v0.13.0-285-gfc2aaae69-ffadm5, as shipped by the AD5M mod
        SUFFIX= ;;
    *) echo "unknown source: $SOURCE" >&2; exit 1 ;;
esac
KLIPPER=${2:-$REPO/firmware/builds/klipper-$SOURCE}

if [ ! -d "$KLIPPER" ]; then
    git clone -q "$KLIPPER_URL" "$KLIPPER"
fi
git -C "$KLIPPER" checkout -q --detach "$KLIPPER_REV"
if [ "$SOURCE" = mainline ]; then
    # Applied as commits with fixed author/committer data, so the version
    # string (and the build) is the same on every machine.
    for p in "$REPO"/klipper/mcu-patches/*.patch; do
        GIT_COMMITTER_NAME=ad5x GIT_COMMITTER_EMAIL=ad5x@localhost \
        GIT_COMMITTER_DATE="2026-10-15T00:00:00Z" \
            git -C "$KLIPPER" am -q --committer-date-is-author-date "$p"
    done
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
VERSION=""
BOARDS="mainboard eboard"
[ "$SOURCE" = mainline ] && BOARDS="$BOARDS ifs"
for board in $BOARDS; do
    cp "$REPO/klipper/mcu-configs/ad5x-$board$SUFFIX.config" "$WORK/$board.config"
    make -s -C "$KLIPPER" KCONFIG_CONFIG="$WORK/$board.config" OUT="$WORK/out-$board/" olddefconfig
    make -s -C "$KLIPPER" -j"$(nproc)" KCONFIG_CONFIG="$WORK/$board.config" OUT="$WORK/out-$board/"
    # IAPCommand and IFSCommand want Intel hex. Make it ourselves (mainline
    # writes only klipper.bin for stm32) and, like stock ADM_App.hex, put the reset
    # handler (vector table word 1) in the start-address record, not the
    # image start that plain objcopy writes. From klipper.bin, not the elf:
    # the tools send no addresses, so the hex must have no gaps (the elf's
    # sections can leave alignment holes).
    RESET=$(od -An -tx4 -j4 -N4 "$WORK/out-$board/klipper.bin" | tr -d ' ')
    APP=$(sed -n 's/^CONFIG_FLASH_APPLICATION_ADDRESS=//p' "$WORK/$board.config")
    arm-none-eabi-objcopy -I binary -O ihex --change-section-address .data="$APP" \
        --set-start=0x$RESET \
        "$WORK/out-$board/klipper.bin" "$WORK/out-$board/klipper.hex"
    VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
        "$WORK/out-$board/klipper.dict")
done

DEST="$REPO/firmware/builds/$VERSION"
mkdir -p "$DEST"
# The mainboard is flashed as a raw image (NationsCommand), the eboard and ifs as hex (IAPCommand/IFSCommand).
cp "$WORK/out-mainboard/klipper.bin"  "$DEST/mainboard.bin"
cp "$WORK/out-mainboard/klipper.dict" "$DEST/mainboard.dict"
cp "$WORK/out-eboard/klipper.hex"     "$DEST/eboard.hex"
cp "$WORK/out-eboard/klipper.dict"    "$DEST/eboard.dict"
if [ -f "$WORK/out-ifs/klipper.hex" ]; then
    cp "$WORK/out-ifs/klipper.hex"    "$DEST/ifs.hex"
    cp "$WORK/out-ifs/klipper.dict"   "$DEST/ifs.dict"
fi
(cd "$DEST" && sha256sum $(ls mainboard.bin eboard.hex ifs.hex 2>/dev/null) > SHA256SUMS)
echo "Built $VERSION in $DEST"
