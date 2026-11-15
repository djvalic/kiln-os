# Plugin root scripts (docs/plugin-root-hooks.md), zMod's model: a plugin
# may ship root/install.sh, root/update.sh and root/uninstall.sh, which run
# as root when the plugin is enabled with ROOT=1, updated, and disabled or
# removed. They may also leave boot scripts in $PR_INITD, which
# S69ad5x-plugin-boot runs at each boot.
#
# Sourced by:
#   S68ad5x-update-agent  runs Klipper's requests (plugin_request). It uses
#                         S68's own helpers: log, say, busy, stage,
#                         unstage, good_sum, own_links.
#   S69ad5x-plugin-boot   the boot scripts; it uses only the pr_* helpers.
# The recovery image gets neither this file nor S69 (ad5x-recovery.mk).
#
# How a request comes in: Klipper (klipper/extras/ad5x_plugins.py) packs the
# plugin's root/ folder into $D/plugin-NAME.tar and then writes
# $D/plugin-request: three lines, the action (install, update or
# uninstall), the plugin name and the tar's sha256 (empty for uninstall).
# Both files are klipper's: they are moved into root's staging folder
# before root reads them (S68's stage). The answer goes to
# $D/plugin-status, one line: "ok", "failed: exit N", "timed out" or
# "refused: ...". Klipper waits for it (360 s at most).
#
# What root keeps: /data/ad5x/plugins-root/NAME, root's own copy of the
# plugin's root/ folder (root:root, nothing writable by group or others,
# no set-user-ID bits), with .sha256, the sha256 of the tar it came from
# (Klipper compares it with the plugin's root/ now to see whether an
# update must run). A hook only ever runs from this copy, never from the
# plugin's folder, which klipper can change.
#
# AD5X_DATA moves /data, AD5X_PLUGIN_ROOT_* the rest (tools/test_plugin_root.sh).

PR_DATA=${AD5X_DATA:-/data}
PR_DIR=$PR_DATA/ad5x/plugins-root
# Boot scripts: S<NN><plugin>[.suffix], run by S69ad5x-plugin-boot
PR_INITD=$PR_DIR/init.d
# While this file exists no boot script runs (create it from recovery SSH)
PR_OFF=$PR_DIR/.off
PR_LOG=$PR_DATA/ad5x/kiln-log/plugins-root.log
# Where the plugins are: a user plugin replaces a shipped one of the same
# name, as in ad5x_plugins.py
PR_USER_PLUGINS=$PR_DATA/ad5x/plugins
PR_SHIPPED_PLUGINS=${AD5X_SHIPPED_PLUGINS:-/usr/share/ad5x/plugins}
# Time a hook (install.sh, update.sh, uninstall.sh) may take, in seconds
PR_TIMEOUT=${AD5X_PLUGIN_ROOT_TIMEOUT:-300}
# The largest root/ tar root takes (Klipper refuses bigger ones first)
PR_TAR_MAX=8388608
# The owner every file a hook or boot script runs from must have (uid);
# the laptop test sets its own
PR_OWNER=${AD5X_PLUGIN_ROOT_OWNER:-0}
# A hook runs with this PATH only (the read-only image's folders)
PR_PATH=/usr/sbin:/usr/bin:/sbin:/bin
# Root's own scratch folder (pr_limited's marks)
PR_RUN=${AD5X_PLUGIN_ROOT_RUN:-/run/ad5x-plugin-root}

pr_log() {
	mkdir -p "${PR_LOG%/*}" 2>/dev/null
	printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$PR_LOG"
}

# pr_name NAME: a plugin name as Klipper allows it (ad5x_plugins.py
# NAME_RE): a-z, 0-9, _ and -, starting with a letter or digit, at most 48
# characters. No dot: that is how a boot script's owner is told apart.
pr_name() {
	case $1 in ''|[!a-z0-9]*|*[!a-z0-9_-]*) return 1 ;; esac
	[ ${#1} -le 48 ]
}

# pr_safe PATH: there, not a link, owned by PR_OWNER (root) and not
# writable by group or others. This BusyBox has no stat: find tests the
# owner and the mode (as S64ad5x-camera does); an error counts as unsafe.
pr_safe() {
	[ -e "$1" ] && [ ! -L "$1" ] || return 1
	[ -n "$(find "$1" -maxdepth 0 -user "$PR_OWNER" ! -perm /022 2>/dev/null)" ]
}

# pr_plugin_dir NAME: the plugin's folder (data for the hook, never run)
pr_plugin_dir() {
	if [ -d "$PR_USER_PLUGINS/$1" ]; then
		echo "$PR_USER_PLUGINS/$1"
	else
		echo "$PR_SHIPPED_PLUGINS/$1"
	fi
}

# pr_limited SECS DIR OUT CMD...: run CMD in DIR with umask 022, stdin
# from /dev/null, output appended to OUT, in its own session and process
# group (setsid: without job control the background child is not a group
# leader, so setsid doesn't fork and $! is the group's id). After SECS the
# whole group gets TERM, 2 s later KILL: the hook and whatever it started
# in the foreground or with "&". A process that made its own session
# (start-stop-daemon -b) keeps running. Returns CMD's exit code, 124 when it
# was stopped at the limit. When PR_RUNNING names a file, the group's id is
# kept there meanwhile (S69ad5x-plugin-boot stop ends a step that runs).
# The timer is its own session too, so no sleep is left behind.
pr_limited() {
	pl_s=$1 pl_d=$2 pl_o=$3
	shift 3
	set +m 2>/dev/null
	# this call's own folder in root's PR_RUN (not /tmp, where anyone can
	# put a link in its place); the timer marks the limit there
	mkdir -p "$PR_RUN" && chmod 700 "$PR_RUN" &&
		pl_c=$(mktemp -d "$PR_RUN/call.XXXXXX") || return 1
	pl_mark=$pl_c/timeout
	(
		cd "$pl_d" || exit 1
		umask 022
		exec setsid "$@"
	) >> "$pl_o" 2>&1 < /dev/null &
	pl_p=$!
	[ -n "${PR_RUNNING:-}" ] && echo "$pl_p" > "$PR_RUNNING"
	setsid sh -c 'sleep "$1"; kill -0 "$2" 2>/dev/null || exit 0
		: > "$3"; kill -TERM "-$2" 2>/dev/null || kill -TERM "$2"
		sleep 2; kill -KILL "-$2" 2>/dev/null || kill -KILL "$2"' \
		sh "$pl_s" "$pl_p" "$pl_mark" > /dev/null 2>&1 < /dev/null &
	pl_k=$!
	wait $pl_p
	pl_rc=$?
	kill -TERM "-$pl_k" 2>/dev/null || kill -TERM "$pl_k" 2>/dev/null
	wait $pl_k 2>/dev/null
	[ -n "${PR_RUNNING:-}" ] && rm -f "$PR_RUNNING"
	# stopped at the limit: the timer marked it and CMD didn't end on its
	# own (one that exits 0 right at the limit is not a timeout)
	[ -e "$pl_mark" ] && [ $pl_rc != 0 ] && pl_rc=124
	rm -f "$pl_mark"
	rmdir "$pl_c"
	return $pl_rc
}

# pr_result RC: the answer text for an exit code
pr_result() {
	case $1 in
	0) echo ok ;;
	124) echo "timed out" ;;
	*) echo "failed: exit $1" ;;
	esac
}

# pr_remove NAME: the plugin's boot scripts and root's copy, gone.
# S50NAME and S50NAME.x are NAME's; S50NAME-x belongs to plugin NAME-x.
pr_remove() {
	rm -f "$PR_INITD"/S[0-9][0-9]"$1" "$PR_INITD"/S[0-9][0-9]"$1".*
	if [ -d "$PR_DIR/$1" ]; then
		rm -rf "$PR_DIR/.old-$1"
		mv "$PR_DIR/$1" "$PR_DIR/.old-$1" && rm -rf "$PR_DIR/.old-$1"
	fi
}

# pr_hook NAME STEP: run STEP.sh (install, update, uninstall) from root's
# copy of the plugin's root/ folder, if it has one. Its answer text is in
# PR_RESULT; returns 0 for ok (also when there is no such script).
# How it runs: as root, in plugins-root/NAME, with a clean environment
# (PATH, HOME, LANG, PLUGIN, PLUGIN_DIR, KILN_ACTION), PR_TIMEOUT seconds
# at most, output in PR_LOG. Executable: run as it is (its #! line);
# otherwise with /bin/sh.
pr_hook() {
	local dir=$PR_DIR/$1 f=$PR_DIR/$1/$2.sh rc
	PR_RESULT=ok
	[ -e "$f" ] || [ -L "$f" ] || return 0
	if ! pr_safe "$PR_DIR" || ! pr_safe "$dir" || ! pr_safe "$f" || [ ! -f "$f" ]; then
		pr_log "$1: $2.sh not run: it or its folder is not root's own plain file"
		PR_RESULT="refused: $2.sh is not root's own plain file"
		return 1
	fi
	set -- "$1" "$2"
	[ -x "$f" ] && set -- "$@" "./$2.sh" || set -- "$@" /bin/sh "./$2.sh"
	pr_log "$1: running $2.sh"
	pr_limited "$PR_TIMEOUT" "$dir" "$PR_LOG" \
		env -i PATH="$PR_PATH" HOME=/root LANG=C PLUGIN="$1" \
		PLUGIN_DIR="$(pr_plugin_dir "$1")" KILN_ACTION="$2" \
		"$3" ${4:+"$4"}
	rc=$?
	PR_RESULT=$(pr_result $rc)
	pr_log "$1: $2.sh: $PR_RESULT"
	[ $rc = 0 ]
}

# pr_setup: root's folders; what a reboot left behind is cleared (S68 start)
pr_setup() {
	mkdir -p "$PR_INITD"
	chown root:root "$PR_DIR" "$PR_INITD"
	chmod 755 "$PR_DIR" "$PR_INITD"
	rm -rf "$PR_DIR"/.old-*
	# Klipper's request of before the reboot: never run after it
	rm -f "$D/plugin-request" "$D/plugin-status" "$D"/plugin-*.tar
	# The named root actions of older releases (S69ad5x-dev-root), once.
	# Moved into root's staging folder first, where klipper can't reach
	# it, then removed.
	if [ -e "$PR_DATA/ad5x/dev-root" ] || [ -L "$PR_DATA/ad5x/dev-root" ]; then
		local t
		mkdir -p "$STAGE" && chmod 700 "$STAGE" && t=$(mktemp -d "$STAGE/r.XXXXXX") &&
			mv "$PR_DATA/ad5x/dev-root" "$t/" && rm -rf "$t"
		pr_log "removed /data/ad5x/dev-root (named root actions, no longer in Kiln OS)"
	fi
}

# pr_unpack NAME SUM TAR: check the staged tar (size, sha256) and unpack it
# into a new folder next to it, made root's; prints that folder. On a
# refusal the answer is said here and everything staged is removed.
pr_unpack() {
	local name=$1 sum=$2 tar=$3 t new have urc err
	t=${tar%/*}
	new=$t/root
	if [ "$(wc -c < "$tar")" -gt $PR_TAR_MAX ]; then
		unstage "$tar"; pr_log "$name: root files over $PR_TAR_MAX bytes"
		say "refused: the plugin's root files are too big"; return 1
	fi
	have=$(sha256sum "$tar" | cut -d' ' -f1)
	if [ "$have" != "$sum" ]; then
		unstage "$tar"; pr_log "$name: sha256 mismatch"
		say "failed: the plugin's root files changed on the way"; return 1
	fi
	# Unpacked by root in the staging folder, out of klipper's reach. Only
	# folders and plain files are kept: a link (it could point a hook at a
	# file klipper can change), a device node, a FIFO or a hard link to a
	# file outside refuses the whole lot. tar's error output goes to the
	# log, cut short, printable ASCII only (as S68's install_app).
	mkdir "$new"
	tar -xf "$tar" -C "$new" 2> "$t/tar.err"
	urc=$?
	err=$(head -c 2000 "$t/tar.err" | tr -c ' -~' ' ' | tr -s ' ' |
		head -c 300 | sed 's/^ //; s/ $//')
	rm -f "$tar" "$t/tar.err"
	if [ $urc != 0 ]; then
		rm -rf "$new"; rmdir "$t"
		pr_log "$name: root files don't unpack${err:+ ($err)}"
		say "failed: the plugin's root files don't unpack"; return 1
	fi
	if [ -n "$(find "$new" ! -type d ! -type f | head -n 1)" ] || ! own_links "$new"; then
		rm -rf "$new"; rmdir "$t"
		pr_log "$name: root/ holds a link, a device, a FIFO or a hard link out of it"
		say "refused: the plugin's root/ may hold only folders and plain files"; return 1
	fi
	chown -R root:root "$new"
	chmod -R go-w,ug-s "$new"
	chmod 755 "$new"
	printf '%s\n' "$sum" > "$new/.sha256"
	chmod 644 "$new/.sha256"
	echo "$new"
}

# pr_swap NEW NAME: NEW becomes plugins-root/NAME (renames on one file
# system; the old copy goes)
pr_swap() {
	local t=${1%/*}
	rm -rf "$PR_DIR/.old-$2"
	[ -d "$PR_DIR/$2" ] && mv "$PR_DIR/$2" "$PR_DIR/.old-$2"
	mv "$1" "$PR_DIR/$2" && rm -rf "$PR_DIR/.old-$2"
	rmdir "$t" 2>/dev/null
	sync
}

# plugin_request: one request from Klipper (see the top). S68 runs it in a
# subshell: ANSWER (S68's say) stays plugin-status only here, and
# Moonraker's "status" is never touched.
plugin_request() {
	local req r act name sum tar new
	ANSWER=plugin-status
	if ! req=$(stage plugin-request); then
		pr_log "ignored a plugin request that is not a plain file"
		say "failed: bad request"; return
	fi
	r=$(head -c 512 "$req")
	unstage "$req"
	act=$(printf '%s\n' "$r" | sed -n 1p)
	name=$(printf '%s\n' "$r" | sed -n 2p)
	sum=$(printf '%s\n' "$r" | sed -n 3p)
	case $act in install|update|uninstall) ;; *) act= ;; esac
	if [ -z "$act" ] || ! pr_name "$name" ||
	   { [ $act != uninstall ] && ! good_sum "$sum"; }; then
		pr_log "ignored a plugin request without an action, a plugin name and a sha256"
		say "failed: bad request"; return
	fi
	# Not while a print may run (S68's busy: printing, paused, the state
	# unknown, or no answer from Moonraker); the refusal is said there
	if busy "plugin $name $act"; then
		pr_log "$name: $act refused (a print may be running, see agent.log)"
		rm -f "$D/plugin-$name.tar"
		return
	fi
	mkdir -p "$PR_INITD"
	if [ $act = uninstall ]; then
		pr_log "$name: uninstall"
		pr_hook "$name" uninstall
		# gone whatever uninstall.sh said: the plugin is off now
		pr_remove "$name"
		say "$PR_RESULT"
		return
	fi
	if ! tar=$(stage "plugin-$name.tar"); then
		pr_log "$name: root files missing or not a plain file"
		say "failed: the plugin's root files are missing"; return
	fi
	new=$(pr_unpack "$name" "$sum" "$tar") || return
	pr_swap "$new" "$name"
	pr_log "$name: $act, root files $sum"
	if pr_hook "$name" $act; then
		say ok
	elif [ $act = install ]; then
		# the plugin stays off (Klipper enables it only after ok): nothing
		# of it is kept, no boot script runs
		pr_remove "$name"
		say "$PR_RESULT"
	else
		# an update keeps the new copy (the plugin is updated); the
		# answer says update.sh failed
		say "$PR_RESULT"
	fi
}
