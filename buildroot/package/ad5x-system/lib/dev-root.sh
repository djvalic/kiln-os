#!/bin/sh
# Named root actions for plugins (docs/plugin-root-actions.md). Sourced by
# S69ad5x-dev-root (the root watcher), bin/ad5x-dev-root (the owner's tool)
# and tools/test_dev_root.sh.
#
# A request is data. It is split into words and never sourced or evaluated.
# The AD5X_* variables move the paths for the laptop tests only; on the
# printer the defaults are used and the owner of grants and the allow-list
# is root (uid 0).

DR_DIR=${AD5X_DEV_ROOT_DIR:-/data/ad5x/dev-root}
DR_GRANTS=$DR_DIR/grants
DR_REQUESTS=$DR_DIR/requests
DR_RESULTS=$DR_DIR/results
DR_CONF=${AD5X_ROOT_ACTIONS_CONF:-/usr/share/ad5x/root-actions.conf}
DR_ACTIONS=${AD5X_ROOT_ACTIONS_PREFIX:-/usr/share/ad5x/root-actions/}
DR_LOG=${AD5X_DEV_ROOT_LOG:-/data/ad5x/kiln-update/agent.log}
DR_RUN=${AD5X_DEV_ROOT_RUN:-/run/ad5x-dev-root}
DR_PID=${AD5X_DEV_ROOT_PID:-/run/ad5x-dev-root.pid}
DR_PLUGINS=${AD5X_DEV_ROOT_PLUGIN_DIRS:-/usr/share/ad5x/plugins /data/ad5x/plugins}
# Test only: a print state word ("printing", "standby", ...) instead of Moonraker
DR_PRINT_STATE=${AD5X_DEV_ROOT_PRINT_STATE:-}
# uid that must own grants and the allow-list (root on the printer)
DR_OWNER=${AD5X_DEV_ROOT_OWNER:-0}
DR_RATE_SECS=10
DR_TIMEOUT=60
DR_MAX_LINE=256

DR_WARNING="Root actions run as root on this printer, with only the arguments the
action's checks allow. Granting an action lets the plugin ask for it, and the
action runs as root each time it is asked, until the next reboot (grants are
cleared at every boot). Grant only plugins you trust, only the actions they need,
and turn them off again with: ad5x-dev-root disable PLUGIN"

dr_log() {
	mkdir -p "${DR_LOG%/*}" 2>/dev/null
	echo "$(date '+%F %T') dev-root: $*" >> "$DR_LOG"
}

# Plain names: letters, digits, dash, underscore
dr_plain_name() {
	case $1 in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac
	return 0
}

dr_digits() {
	case $1 in ''|*[!0-9]*) return 1 ;; esac
	return 0
}

# A whole request line may hold only plain tokens: no quotes, no shell
# characters, no tabs. Dash is last in the set, so it is literal.
dr_plain_line() {
	case $1 in *[!A-Za-z0-9_.,:/+=@%" "-]*) return 1 ;; esac
	return 0
}

# dr_setup: directories and their owners (klipper writes requests only)
dr_setup() {
	mkdir -p "$DR_GRANTS" "$DR_REQUESTS" "$DR_RESULTS" "$DR_RUN"
	chmod 711 "$DR_DIR"
	chmod 700 "$DR_GRANTS"
	chown klipper:klipper "$DR_REQUESTS" 2>/dev/null
	chmod 700 "$DR_REQUESTS"
	chown root:klipper "$DR_RESULTS" 2>/dev/null
	chmod 750 "$DR_RESULTS"
}

# dr_boot_clear: no grant and no pending request survives a boot. Called
# before the watcher starts, so nothing granted before the reboot can run.
dr_boot_clear() {
	mkdir -p "$DR_GRANTS" "$DR_REQUESTS"
	for f in "$DR_GRANTS"/* "$DR_GRANTS"/.[!.]* "$DR_REQUESTS"/* "$DR_REQUESTS"/.[!.]*; do
		[ -e "$f" ] || [ -L "$f" ] || continue
		rm -f "$f"
	done
	dr_log "boot: grants and pending requests cleared"
}

# Busybox here has no stat: owner, mode and size come from ls and wc
dr_uid() { ls -ln "$1" | awk '{print $3}'; }
dr_perm() { ls -ld "$1" | awk '{print $1}'; }
dr_size() { wc -c < "$1" | tr -d ' '; }

# dr_grant_ok PLUGIN ACTION: 0 if the plugin's grant file is a plain file
# owned by DR_OWNER with no group or other access, and lists the action
dr_grant_ok() {
	g=$DR_GRANTS/$1.grant
	[ -f "$g" ] && [ ! -L "$g" ] || return 1
	[ "$(dr_uid "$g")" = "$DR_OWNER" ] || return 1
	case $(dr_perm "$g") in -rw-------|-r--------) ;; *) return 1 ;; esac
	grep -qxF -- "action $2" "$g"
}

# The allow-list must be a plain file owned by DR_OWNER, not writable by group
# or others (the same check as load_conf in S64ad5x-camera)
dr_conf_ok() {
	[ -f "$DR_CONF" ] && [ ! -L "$DR_CONF" ] || return 1
	[ "$(dr_uid "$DR_CONF")" = "$DR_OWNER" ] || return 1
	case $(dr_perm "$DR_CONF") in
	?????w????|????????w?) return 1 ;;
	esac
	return 0
}

# dr_load_action NAME: reads NAME's block from the allow-list into A_SCRIPT,
# A_ARGC, A_PRINT, A_WRITES and A_RE_1..A_RE_<A_ARGC>. Returns 0 if the block
# is valid, 1 if NAME is not in the list, 2 if the block is not valid (DR_WHY).
# Blocks are read as data: each line is split into words, nothing is run.
dr_load_action() {
	A_SCRIPT= A_ARGC=0 A_PRINT=no A_WRITES=
	dr_i=1
	while [ $dr_i -le 9 ]; do eval "unset A_RE_$dr_i"; dr_i=$((dr_i + 1)); done
	DR_WHY=
	dr_conf_ok || { DR_WHY="allow-list missing or not owned by root"; return 2; }
	dr_found=0
	while read -r dr_key dr_val dr_rest || [ -n "$dr_key" ]; do
		case $dr_key in ''|'#'*) continue ;; esac
		if [ "$dr_key" = action ]; then
			[ $dr_found = 1 ] && break
			[ "$dr_val" = "$1" ] && dr_found=1
			continue
		fi
		[ $dr_found = 1 ] || continue
		case $dr_key in
		script) A_SCRIPT=$dr_val ;;
		args) A_ARGC=$dr_val ;;
		arg)
			dr_digits "$dr_val" && [ "$dr_val" -ge 1 ] && [ "$dr_val" -le 9 ] ||
				{ DR_WHY="bad argument index in $1"; return 2; }
			eval "A_RE_$dr_val=\$dr_rest" ;;
		writes) A_WRITES=$dr_val ;;
		print_safe) A_PRINT=$dr_val ;;
		*) DR_WHY="unknown line in $1: $dr_key"; return 2 ;;
		esac
	done < "$DR_CONF"
	[ $dr_found = 1 ] || { DR_WHY="not in the image's list"; return 1; }
	dr_digits "$A_ARGC" && [ "$A_ARGC" -le 9 ] || { DR_WHY="bad args count in $1"; return 2; }
	case $A_PRINT in yes|no) ;; *) DR_WHY="bad print_safe in $1"; return 2 ;; esac
	case $A_SCRIPT in "$DR_ACTIONS"*) ;; *) DR_WHY="script of $1 is outside the actions directory"; return 2 ;; esac
	case $A_SCRIPT in *..*) DR_WHY="script of $1 has '..'"; return 2 ;; esac
	dr_i=1
	while [ $dr_i -le "$A_ARGC" ]; do
		eval "[ -n \"\${A_RE_$dr_i:-}\" ]" || { DR_WHY="argument $dr_i of $1 has no regex"; return 2; }
		dr_i=$((dr_i + 1))
	done
	return 0
}

# dr_print_check: 0 if a print may run now, 1 if one is printing or paused,
# 2 if the state cannot be read (refused: fail closed)
dr_print_check() {
	s=$DR_PRINT_STATE
	if [ -z "$s" ]; then
		s=$(wget -q -T 5 -O- 'http://127.0.0.1:7125/printer/objects/query?print_stats=state' 2>/dev/null |
			sed -n 's/.*"state": *"\([a-z_]*\)".*/\1/p' | head -n 1)
	fi
	case $s in
	printing|paused) return 1 ;;
	standby|complete|cancelled|error) return 0 ;;
	*) return 2 ;;
	esac
}

# dr_run ARGV...: runs the script with exec (no shell) and the time limit
dr_run() {
	if command -v timeout >/dev/null 2>&1; then
		timeout $DR_TIMEOUT "$@"
		return
	fi
	"$@" &
	p=$!
	( sleep $DR_TIMEOUT; kill $p 2>/dev/null ) &
	k=$!
	wait $p
	rc=$?
	kill $k 2>/dev/null
	wait $k 2>/dev/null
	return $rc
}

# dr_result PLUGIN N TEXT: writes results/PLUGIN.N.res (one line, then the time)
dr_result() {
	t=$DR_RESULTS/.$1.$2.tmp
	printf '%s at %s\n' "$3" "$(date '+%F %T')" > "$t" || return 1
	chgrp klipper "$t" 2>/dev/null
	chmod 640 "$t"
	mv -f "$t" "$DR_RESULTS/$1.$2.res"
}

# dr_refuse REASON: uses plugin, n, action and f from dr_handle
dr_refuse() {
	dr_log "refused $plugin.$n ${action:--}: $1"
	dr_result "$plugin" "$n" "refused: $1"
	rm -f "$f"
}

# dr_handle FILE: one request, checked in the order of docs/plugin-root-actions.md.
# The file is always deleted after this, whatever the outcome.
dr_handle() {
	f=$1
	base=${f##*/}
	case $base in *.req) ;; *) return 0 ;; esac
	stem=${base%.req}
	n=${stem##*.}
	plugin=${stem%.*}
	action=
	if [ "$plugin" = "$stem" ] || ! dr_digits "$n" || ! dr_plain_name "$plugin"; then
		dr_log "ignored request file $base: bad file name"
		rm -f "$f"
		return 0
	fi
	if [ -L "$f" ] || [ ! -f "$f" ]; then dr_refuse "not a plain file"; return 0; fi
	if [ "$(dr_size "$f")" -gt $DR_MAX_LINE ]; then dr_refuse "request too long"; return 0; fi
	line=
	read -r line < "$f" || true
	printf '%s\n' "$line" | cmp -s - "$f" || printf '%s' "$line" | cmp -s - "$f" ||
		{ dr_refuse "request is not one line"; return 0; }
	dr_plain_line "$line" || { dr_refuse "request has characters that are not allowed"; return 0; }
	set -f
	set -- $line
	set +f
	[ $# -ge 2 ] || { dr_refuse "bad request"; return 0; }
	r_plugin=$1
	action=$2
	shift 2
	# 1. plugin name: a plain name, and the same one as the file name
	[ "$r_plugin" = "$plugin" ] || { dr_refuse "request names plugin $r_plugin, file is for $plugin"; return 0; }
	# 2. action name and grant
	dr_plain_name "$action" || { dr_refuse "bad action name"; return 0; }
	dr_grant_ok "$plugin" "$action" || { dr_refuse "action not granted"; return 0; }
	# 3. allow-list entry
	dr_load_action "$action"
	case $? in
	1) dr_refuse "action is not in the image's list"; return 0 ;;
	2) dr_refuse "allow-list entry is not valid: $DR_WHY"; return 0 ;;
	esac
	# 4. argument count and each argument against its regex
	[ $# = "$A_ARGC" ] || { dr_refuse "wants $A_ARGC argument(s), got $#"; return 0; }
	i=0
	for v in "$@"; do
		i=$((i + 1))
		eval "re=\$A_RE_$i"
		printf '%s\n' "$v" | grep -Eqx -e "$re" || { dr_refuse "argument $i is not allowed"; return 0; }
	done
	[ -f "$A_SCRIPT" ] && [ ! -L "$A_SCRIPT" ] || { dr_refuse "script is missing"; return 0; }
	# 5. no print, unless the action is print_safe
	if [ "$A_PRINT" != yes ]; then
		dr_print_check
		case $? in
		1) dr_refuse "a print is running"; return 0 ;;
		2) dr_refuse "cannot read the print state"; return 0 ;;
		esac
	fi
	# 6. one action per plugin per DR_RATE_SECS (counted when it runs)
	now=$(date +%s)
	last=$(cat "$DR_RUN/last.$plugin" 2>/dev/null)
	case $last in ''|*[!0-9]*) last=0 ;; esac
	if [ "$last" -le "$now" ] && [ $((now - last)) -lt $DR_RATE_SECS ]; then
		dr_refuse "rate limit: one action per $DR_RATE_SECS s for a plugin"
		return 0
	fi
	mkdir -p "$DR_RUN"
	echo "$now" > "$DR_RUN/last.$plugin"
	# 7. run the fixed script with the validated arguments only
	dr_run "$A_SCRIPT" "$@"
	rc=$?
	if [ $rc = 0 ]; then
		dr_log "ran $plugin $action ($*): ok"
		dr_result "$plugin" "$n" ok
	else
		dr_refuse "script failed (exit $rc)"
		return 0
	fi
	rm -f "$f"
	return 0
}

# dr_scan: one pass over the pending requests (klipper writes names ending in
# .req, and starts temporary names with a dot, which are not read)
dr_scan() {
	mkdir -p "$DR_RESULTS"
	for f in "$DR_REQUESTS"/*.req; do
		[ -e "$f" ] || [ -L "$f" ] || continue
		dr_handle "$f"
	done
}
