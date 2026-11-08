#!/bin/sh
# ad5x-mcu ifs-firmware: stock <-> Klipper on the IFS, with stubs for the
# flasher, the version queries and ps. usage: sh tools/test_ifs_firmware.sh
HERE=$(cd "$(dirname "$0")/.." && pwd)
MCU=$HERE/buildroot/package/ad5x-system/bin/ad5x-mcu
LIB=$HERE/buildroot/package/ad5x-system/lib
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*"; exit 1; }

mkdir -p "$T/bin"
# the flasher logs the HEX it got; the IFS then runs what the file says
cat > "$T/bin/ad5x-flash-ifs" <<'S'
#!/bin/sh
for a; do h=$a; done
echo "$h" >> "$STUB_DIR/flashed"
[ -n "$STUB_FLASH_FAIL" ] && { echo "Can not connect"; exit 1; }
[ -n "$STUB_NOCHANGE" ] || cat "$h" > "$STUB_DIR/ifs-state"
echo "STM32Write: success"
S
cat > "$T/bin/ad5x-mcu-version" <<'S'
#!/bin/sh
[ -z "$STUB_SILENT" ] && [ "$(cat "$STUB_DIR/ifs-state")" = klipper ] && { echo "$STUB_IFS_VERSION"; exit 0; }
exit 1
S
cat > "$T/bin/ad5x-ifs-f19" <<'S'
#!/bin/sh
[ -z "$STUB_SILENT" ] && [ "$(cat "$STUB_DIR/ifs-state")" = stock ] && { echo 3.0.7; exit 0; }
exit 1
S
cat > "$T/bin/ps" <<'S'
#!/bin/sh
[ -n "$STUB_KLIPPY" ] && echo "  123 klipper python3 /usr/lib/klipper/klippy/klippy.py"
exit 0
S
chmod +x "$T/bin/"*

setup() {	# fresh tree; the IFS runs the other firmware than the target
	rm -rf "$T/w"; W=$T/w
	mkdir -p "$W/data/ad5x/kiln-update" "$W/fw" "$W/us/PROGRAM/control/1.1.1" "$W/pd/config" "$W/plug/happy-hare" "$W/plug/zmod-compat" "$W/stub"
	echo klipper > "$W/fw/ifs.hex"; echo v0.13.0-IFS > "$W/fw/IFS_VERSION"
	echo stock > "$W/us/PROGRAM/control/1.1.1/ifs.hex"
	m=$(md5sum "$W/us/PROGRAM/control/1.1.1/ifs.hex" | cut -d' ' -f1)
	echo "$m  ./ifs.hex" > "$W/us/PROGRAM/control/1.1.1/md5sum.list"
	echo '{"owns_ifs": true}' > "$W/plug/happy-hare/plugin.json"
	echo '{"name": "zmod-compat"}' > "$W/plug/zmod-compat/plugin.json"
	cat > "$W/pd/config/plugins.cfg" <<P
[include $W/plug/happy-hare/plugin.cfg]
[include $W/plug/zmod-compat/plugin.cfg]
P
	cp "$W/pd/config/plugins.cfg" "$W/plugins.orig"
	touch "$W/data/ad5x/ifs-klipper.enable"
	echo "$1" > "$W/stub/ifs-state"
	STATUS=$W/status
}
run() {	# TARGET -> exit code of ad5x-mcu ifs-firmware
	IFS_WAIT=0 IFS_VERIFY_WAIT=0 PATH=${RUN_BIN:-$T/bin}:$PATH STUB_DIR=$W/stub STUB_IFS_VERSION=v0.13.0-IFS \
	AD5X_DATA=$W/data AD5X_MCU_FW=$W/fw AD5X_USERSHARE=$W/us AD5X_RUN=$W/run \
	AD5X_PD=$W/pd AD5X_SCREENS=$W/none IFS_FW_STATUS=$STATUS AD5X_LIB=$LIB \
	sh "$MCU" ifs-firmware "$1" > "$W/out" 2>&1
}
st() { sed -n "s/^$1=//p" "$STATUS"; }
want_status() {	# KEY VALUE
	[ "$(st "$1")" = "$2" ] || { cat "$STATUS" 2>&1; fail "$CASE: status $1='$(st "$1")', want '$2'"; }
}
untouched() {	# nothing flashed, enable file and plugins as before
	[ ! -s "$W/stub/flashed" ] || fail "$CASE: flashed $(cat "$W/stub/flashed")"
	[ -f "$W/data/ad5x/ifs-klipper.enable" ] || fail "$CASE: enable file gone"
	cmp -s "$W/pd/config/plugins.cfg" "$W/plugins.orig" || fail "$CASE: plugins.cfg changed"
}

CASE=to_stock; setup klipper
ino=$(ls -i "$W/pd/config/plugins.cfg" | cut -d' ' -f1)
run stock || { rc=$?; cat "$W/out"; fail "$CASE: exit $rc"; }
[ "$(cat "$W/stub/flashed")" = "$W/us/PROGRAM/control/1.1.1/ifs.hex" ] || fail "$CASE: flashed $(cat "$W/stub/flashed")"
[ ! -e "$W/data/ad5x/ifs-klipper.enable" ] || fail "$CASE: enable file still there"
grep -q "^#\[include .*/happy-hare/" "$W/pd/config/plugins.cfg" || fail "$CASE: happy-hare still on"
grep -q "^\[include .*/zmod-compat/" "$W/pd/config/plugins.cfg" || fail "$CASE: zmod-compat touched"
[ "$(ls -i "$W/pd/config/plugins.cfg" | cut -d' ' -f1)" = "$ino" ] || fail "$CASE: plugins.cfg replaced (owner)"
want_status state done; want_status target stock; want_status version 3.0.7
echo "PASS $CASE"

CASE=to_klipper; setup stock; rm "$W/data/ad5x/ifs-klipper.enable"
run klipper || { rc=$?; cat "$W/out"; fail "$CASE: exit $rc"; }
[ "$(cat "$W/stub/flashed")" = "$W/fw/ifs.hex" ] || fail "$CASE: flashed $(cat "$W/stub/flashed")"
[ -f "$W/data/ad5x/ifs-klipper.enable" ] || fail "$CASE: no enable file"
cmp -s "$W/pd/config/plugins.cfg" "$W/plugins.orig" || fail "$CASE: plugins.cfg changed"
want_status state done; want_status target klipper; want_status version v0.13.0-IFS
echo "PASS $CASE"

failed_case() {	# the reason is in message
	run stock && fail "$CASE: exit 0"
	untouched; want_status state failed
	[ -n "$(st message)" ] || fail "$CASE: no message"
	echo "PASS $CASE ($(st message))"
}
CASE=bad_md5; setup klipper
echo "00000000000000000000000000000000  ./ifs.hex" > "$W/us/PROGRAM/control/1.1.1/md5sum.list"
failed_case
CASE=no_control_dir; setup klipper; rm -r "$W/us/PROGRAM/control/1.1.1"
failed_case
CASE=md5_list_without_ifs_hex; setup klipper
echo "7ead35713526c3d79f83a1196676393e  ./other.bin" > "$W/us/PROGRAM/control/1.1.1/md5sum.list"
failed_case

CASE=neither_answers; setup klipper
STUB_SILENT=1; export STUB_SILENT
run stock && fail "$CASE: exit 0"
unset STUB_SILENT
[ -s "$W/stub/flashed" ] || fail "$CASE: nothing flashed"
[ ! -e "$W/data/ad5x/ifs-klipper.enable" ] || fail "$CASE: enable file still there"
grep -q "^#\[include .*/happy-hare/" "$W/pd/config/plugins.cfg" || fail "$CASE: happy-hare still on"
want_status state failed
case $(st message) in *"unplug"*"ad5x-mcu flash-ifs stock"*) ;; *) fail "$CASE: message '$(st message)'" ;; esac
echo "PASS $CASE"

CASE=neither_answers_klipper; setup stock; rm "$W/data/ad5x/ifs-klipper.enable"
STUB_SILENT=1; export STUB_SILENT
run klipper && fail "$CASE: exit 0"
unset STUB_SILENT
[ -f "$W/data/ad5x/ifs-klipper.enable" ] || fail "$CASE: no enable file"
want_status state failed
case $(st message) in *"unplug"*"ad5x-mcu flash-ifs "*) ;; *) fail "$CASE: message '$(st message)'" ;; esac
case $(st message) in *"flash-ifs klipper"*) fail "$CASE: bad way out" ;; esac
echo "PASS $CASE"

CASE=klipper_target_still_stock; setup stock; rm "$W/data/ad5x/ifs-klipper.enable"
STUB_NOCHANGE=1; export STUB_NOCHANGE
run klipper && fail "$CASE: exit 0"
unset STUB_NOCHANGE
[ ! -e "$W/data/ad5x/ifs-klipper.enable" ] || fail "$CASE: enable file on with a stock IFS"
want_status state failed; want_status version 3.0.7
echo "PASS $CASE"

CASE=stock_write_fails_klipper_answers; setup klipper
STUB_FLASH_FAIL=1; export STUB_FLASH_FAIL
run stock && fail "$CASE: exit 0"
unset STUB_FLASH_FAIL
[ -f "$W/data/ad5x/ifs-klipper.enable" ] || fail "$CASE: enable file gone"
cmp -s "$W/pd/config/plugins.cfg" "$W/plugins.orig" || fail "$CASE: plugins.cfg changed"
want_status state failed
echo "PASS $CASE"

CASE=no_flasher; setup klipper
mkdir -p "$T/bin2"; for f in ad5x-mcu-version ad5x-ifs-f19 ps; do cp "$T/bin/$f" "$T/bin2/"; done
RUN_BIN=$T/bin2
run stock && fail "$CASE: exit 0"
RUN_BIN=
untouched; want_status state failed
echo "PASS $CASE"

CASE=plugins_cfg_unwritable; setup klipper
chmod a-w "$W/pd/config/plugins.cfg"
if [ -w "$W/pd/config/plugins.cfg" ]; then echo "SKIP $CASE (root)"; else
	run stock && fail "$CASE: exit 0"
	chmod u+w "$W/pd/config/plugins.cfg"
	cmp -s "$W/pd/config/plugins.cfg" "$W/plugins.orig" || fail "$CASE: plugins.cfg changed"
	want_status state failed
	echo "PASS $CASE"
fi

CASE=refused_while_klipper_runs; setup klipper
echo "state=done" > "$STATUS"
STUB_KLIPPY=1; export STUB_KLIPPY
run stock && fail "$CASE: exit 0"
unset STUB_KLIPPY
untouched
[ "$(cat "$STATUS")" = "state=done" ] || fail "$CASE: status changed"
echo "PASS $CASE"
echo "all passed"
