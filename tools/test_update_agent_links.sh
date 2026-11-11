#!/bin/sh
# The root update agent's answers in klipper's folder: a link or a FIFO
# klipper puts at "status" or "agent.log" must not make root write through
# it or wait forever. Stubs for Moonraker (no answer) and the slot helpers.
# usage: sh tools/test_update_agent_links.sh
HERE=$(cd "$(dirname "$0")/.." && pwd)
AGENT=$HERE/buildroot/package/ad5x-system/init.d/S68ad5x-update-agent
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*"; exit 1; }

mkdir -p "$T/bin" "$T/lib"
# no Moonraker: every request is refused, which writes the status and the log
printf '#!/bin/sh\nexit 1\n' > "$T/bin/wget"
for c in chown start-stop-daemon; do printf '#!/bin/sh\nexit 0\n' > "$T/bin/$c"; done
chmod +x "$T/bin/"*
echo "APPS=$T/apps; app_root() { echo /usr/lib/\$1; }; app_sub() { echo \$1; }" > "$T/lib/apps.sh"
echo "SLOT= OTHER=; read_flag() { :; }; flag_for() { :; }" > "$T/lib/slot.sh"
export AD5X_LIB=$T/lib PATH="$T/bin:$PATH"

setup() {
	rm -rf "$T/w"; W=$T/w; export AD5X_DATA=$W/data
	D=$W/data/ad5x/kiln-update; LOGD=$W/data/ad5x/kiln-log
	mkdir -p "$W"; echo secret > "$W/secret"
	sh $AGENT start; sh $AGENT stop
}
retry() { : > $D/kernel-retry; timeout 10 sh $AGENT once || fail "agent stuck or failed"; }
answer() { cat $D/status; }

test_status_answered() {
	setup; retry
	[ "$(answer)" = "refused: no answer from Moonraker" ] || fail "status: $(answer)"
	grep -q "kernel retry refused" $LOGD/agent.log || fail "nothing in $LOGD/agent.log"
}
test_status_link_replaced() {
	setup; ln -s $W/secret $D/status; retry
	[ "$(cat $W/secret)" = secret ] || fail "written through the link: $(cat $W/secret)"
	[ -f $D/status ] && [ ! -L $D/status ] || fail "status is still a link"
	[ "$(answer)" = "refused: no answer from Moonraker" ] || fail "status: $(answer)"
}
test_status_fifo_replaced() {
	setup; mkfifo $D/status; retry
	[ -f $D/status ] && [ ! -p $D/status ] || fail "status is still a FIFO"
}
test_status_folder_left() {
	setup; mkdir $D/status; retry
	[ -d $D/status ] && [ -z "$(ls $D/status)" ] || fail "something went into klipper's folder"
	grep -q "is a folder" $LOGD/agent.log || fail "not logged"
}
test_status_link_to_folder() {
	setup; mkdir $W/etc; ln -s $W/etc $D/status; retry
	[ -z "$(ls $W/etc)" ] || fail "a file went into the linked folder: $(ls $W/etc)"
}
test_log_not_in_klippers_folder() {
	setup; ln -s $W/secret $D/agent.log; retry
	[ "$(cat $W/secret)" = secret ] || fail "the log went through klipper's link"
	[ -s $LOGD/agent.log ] || fail "no log in $LOGD"
}

for t in test_status_answered test_status_link_replaced test_status_fifo_replaced \
	test_status_folder_left test_status_link_to_folder test_log_not_in_klippers_folder; do
	( $t ) || exit 1
	echo "ok $t"
done
