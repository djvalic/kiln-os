#!/bin/sh
# The root update agent's "ifs-firmware" request and S61klipper's stale IFS
# link, with stubs for ad5x-mcu, Klipper's init script and the print state.
# usage: sh tools/test_update_agent_ifs.sh
HERE=$(cd "$(dirname "$0")/.." && pwd)
PKG=$HERE/buildroot/package/ad5x-system
AGENT=$PKG/init.d/S68ad5x-update-agent
S61=$PKG/init.d/S61klipper
MCU=$PKG/bin/ad5x-mcu
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*"; exit 1; }

mkdir -p "$T/bin"
# the real ad5x-mcu for ifs-status; ifs-firmware is the stub
cat > "$T/bin/ad5x-mcu" <<S
#!/bin/sh
if [ "\$1" = ifs-firmware ]; then
	echo "mcu \$*" >> "\$STUB_DIR/calls"
	[ -z "\$STUB_MCU_HOOK" ] || eval "\$STUB_MCU_HOOK"
	[ -z "\$STUB_MCU_RUNNING" ] || sh $MCU ifs-status state=running
	exit \${STUB_MCU_RC:-0}
fi
exec sh $MCU "\$@"
S
cat > "$T/bin/klipper-init" <<'S'
#!/bin/sh
echo "init $1" >> "$STUB_DIR/calls"
S
for c in chown chmod; do printf '#!/bin/sh\nexit 0\n' > "$T/bin/$c"; done
printf '#!/bin/sh\nexit 0\n' > "$T/bin/start-stop-daemon"
# no Moonraker here: print and Klipper state only from AD5X_PRINT_STATE
printf '#!/bin/sh\nexit 1\n' > "$T/bin/wget"
chmod +x "$T/bin/"*

setup() {
	rm -rf "$T/w"; W=$T/w
	mkdir -p "$W/data/ad5x/kiln-update" "$W/data/ad5x/kiln-status" "$W/stub"
	: > "$W/stub/calls"
	export AD5X_DATA=$W/data STUB_DIR=$W/stub AD5X_KLIPPER_INIT=$T/bin/klipper-init
	mkdir -p "$W/lib"; echo "APPS=$W/apps; app_root() { echo /usr/lib/\$1; }" > "$W/lib/apps.sh"
	echo "SLOT= OTHER=" > "$W/lib/slot.sh"
	echo "klippy_log_retention() { :; }" > "$W/lib/logs.sh"
	export AD5X_LIB=$W/lib PATH="$T/bin:$PATH" AD5X_PRINT_STATE=standby
	unset STUB_MCU_RC STUB_MCU_HOOK STUB_MCU_RUNNING
	D=$W/data/ad5x/kiln-update; ST=$W/data/ad5x/kiln-status/ifs-firmware.status
}
req() { echo "$1" > $D/ifs-firmware; sh $AGENT handle-ifs-firmware; }
val() { sed -n "s/^$1=//p" $ST; }
calls() { tr '\n' ',' < $W/stub/calls; }

test_request_runs_switch() {
	setup; req stock
	[ "$(calls)" = "init stop,mcu ifs-firmware stock,init start," ] || fail "order: $(calls)"
	[ ! -e $D/ifs-firmware ] || fail "request file left"
}
test_link_request_ignored() {
	setup; echo klipper > $W/secret; ln -s $W/secret $D/ifs-firmware
	sh $AGENT handle-ifs-firmware
	[ "$(calls)" = "" ] || fail "a linked request ran: $(calls)"
	[ "$(val state)" = failed ] || fail "state: $(val state)"
	[ -f $W/secret ] || fail "the link's target went away"
}
test_fifo_request_does_not_hang() {
	setup; mkfifo $D/ifs-firmware
	timeout 10 sh $AGENT handle-ifs-firmware || fail "stuck on a FIFO request"
	[ "$(calls)" = "" ] || fail "a FIFO request ran: $(calls)"
}
test_start_even_after_failure() {
	setup; STUB_MCU_RC=1 req klipper
	[ "$(calls)" = "init stop,mcu ifs-firmware klipper,init start," ] || fail "order: $(calls)"
	[ "$(val state)" = failed ] || fail "state after crash: $(val state)"
}
test_refused_while_printing() {
	for p in printing paused; do
		setup; AD5X_PRINT_STATE=$p req stock
		[ -z "$(calls)" ] || fail "$p: ran $(calls)"
		[ "$(val state)" = refused ] || fail "$p: state $(val state)"
	done
}
test_refused_without_moonraker() {
	# no answer: a print may run, as for installs (busy)
	setup; unset AD5X_PRINT_STATE; req stock
	[ -z "$(calls)" ] || fail "ran $(calls)"
	[ "$(val state)" = refused ] && [ "$(val message)" = "no answer from Moonraker" ] || fail "status $(cat $ST)"
}
test_second_request_while_running() {
	setup
	printf 'target=klipper\nstate=running\nphase=writing\nmessage=Switching\nversion=\n' > $ST
	cp $ST $W/before
	req stock
	[ -z "$(calls)" ] || fail "ran $(calls)"
	cmp -s $ST $W/before || fail "status changed: $(cat $ST)"
	grep -q "already running" $D/agent.log || fail "refusal not logged"
}
test_request_during_switch_dropped() {
	setup
	# a second request arrives while the (stub) switch runs
	STUB_MCU_HOOK="echo klipper > $D/ifs-firmware" req stock
	[ "$(calls)" = "init stop,mcu ifs-firmware stock,init start," ] || fail "second switch ran: $(calls)"
	[ ! -e $D/ifs-firmware ] || fail "second request left"
}
test_exit0_leaving_running() {
	setup; STUB_MCU_RUNNING=1 req stock
	[ "$(val state)" = failed ] && [ "$(val message)" = "the switch stopped unexpectedly" ] || fail "status $(cat $ST)"
}
test_bad_request() {
	setup; req foo
	[ -z "$(calls)" ] || fail "ran $(calls)"
	[ "$(val state)" = failed ] && [ "$(val message)" = "bad request" ] || fail "status $(cat $ST)"
	[ ! -e $D/ifs-firmware ] || fail "request file left"
}
test_interrupted_at_start() {
	setup
	printf 'target=klipper\nstate=running\nphase=writing\nmessage=Switching\nversion=\n' > $ST
	sh $AGENT start; sh $AGENT stop
	[ "$(val state)" = failed ] && [ "$(val message)" = "interrupted (restart)" ] || fail "status $(cat $ST)"
}
test_s61_removes_stale_link() {
	setup
	mkdir -p $W/run/ifs-mcu; touch $W/run/ifs-mcu/generic-flashforge-ifs.cfg
	AD5X_RUN=$W/run sh $S61 start >/dev/null 2>&1
	[ ! -e $W/run/ifs-mcu/generic-flashforge-ifs.cfg ] || fail "stale link left"
}

for t in test_request_runs_switch test_link_request_ignored test_fifo_request_does_not_hang test_start_even_after_failure test_refused_while_printing test_refused_without_moonraker \
	test_second_request_while_running test_request_during_switch_dropped test_exit0_leaving_running test_bad_request test_interrupted_at_start \
	test_s61_removes_stale_link; do
	( $t ) || exit 1
	echo "ok $t"
done
