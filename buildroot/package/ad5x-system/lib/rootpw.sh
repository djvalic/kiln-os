# Root's password (docs/install.md "SSH login and the root password").
# Sourced by S05ad5x-data in both OSes and by ad5x-passwd.
#
# /etc/shadow is on the read-only root. At each start S05 writes a copy
# with root's hash to /run/ad5x/shadow and binds it over /etc/shadow
# (rootpw_boot). The hash is Kiln's own (ROOTPW_FILE, written by
# ad5x-passwd) when that file is there and sound, else stock's (the
# usershare partition's /etc/shadow, read only: Kiln never writes that
# partition). A change applies to the bound copy at once (rootpw_apply),
# so no restart is needed. With neither hash root's password is the
# default "root" (ROOTPW_DEFAULT_HASH), never empty: the owner's choice,
# so a printer with no password at all can still be logged into. Hashes are never printed or
# logged, and never on a command line (other users read /proc/*/cmdline):
# only through shell builtins (printf, echo, test), the environment or a
# file.
#
# The variables are for the laptop test (tools/test_root_password.sh).
ROOTPW_FILE=${ROOTPW_FILE:-/data/ad5x/ssh/root-password}
ROOTPW_SHADOW=${ROOTPW_SHADOW:-/etc/shadow}
ROOTPW_RUN=${ROOTPW_RUN:-/run/ad5x}
ROOTPW_MOUNTS=${ROOTPW_MOUNTS:-/proc/mounts}
ROOTPW_UID=${ROOTPW_UID:-0}
ROOTPW_LOG=${ROOTPW_LOG:-/data/ad5x/kiln-log/passwd.log}
# The owner's lock on the touch screen's reset (ad5x-passwd --lock-reset)
ROOTPW_RESET_LOCK=${ROOTPW_RESET_LOCK:-${ROOTPW_FILE%/*}/screen-reset.disable}

# rootpw_valid HASH: a whole crypt hash of the kinds Kiln writes or stock
# uses: md5 ($1$, stock's), sha256 ($5$), sha512 ($6$, Kiln's), one line
rootpw_valid() {
	case $1 in
	*'
'*) return 1 ;;
	'$1$'*) _rp_n=22 ;;
	'$5$'*) _rp_n=43 ;;
	'$6$'*) _rp_n=86 ;;
	*) return 1 ;;
	esac
	printf '%s\n' "$1" | grep -Eqx '\$[156]\$(rounds=[0-9]{1,9}\$)?[./0-9A-Za-z]{1,16}\$[./0-9A-Za-z]{'$_rp_n'}'
}

# rootpw_stock_ok HASH: stock's hash is used as stock has it; only
# characters that could break the shadow line are refused
rootpw_stock_ok() {
	[ -n "$1" ] || return 1
	case $1 in *[!./0-9A-Za-z\$=!*]*) return 1 ;; esac
	return 0
}

rootpw_log() {
	mkdir -p "${ROOTPW_LOG%/*}" 2>/dev/null &&
		echo "$(date '+%F %T') $*" >> "$ROOTPW_LOG" 2>/dev/null
	return 0
}

# rootpw_saved: print Kiln's saved hash when ROOTPW_FILE is there and
# sound: a regular file (not a link, one name), root's, writable by root
# only, in a folder of root's that is no link, holding one valid hash.
# Anything else: a line on stderr (never the content) and false, so
# stock's password applies.
rootpw_saved() {
	_rp_f=$ROOTPW_FILE _rp_d=${ROOTPW_FILE%/*} _rp_why=
	[ -e "$_rp_f" ] || [ -L "$_rp_f" ] || return 1
	if [ -L "$_rp_f" ] || [ -L "$_rp_d" ]; then
		_rp_why="it is a link"
	elif [ ! -f "$_rp_f" ]; then
		_rp_why="not a regular file"
	else
		# mode, links, uid of the file, then uid of its folder
		set -- $(ls -lnd "$_rp_f") $(ls -lnd "$_rp_d" | awk '{print $3}')
		case $1 in
		?????w*|????????w*) _rp_why="writable by others" ;;
		esac
		[ "$2" = 1 ] || _rp_why="it has more than one name"
		[ "$3" = "$ROOTPW_UID" ] || _rp_why="not root's"
		[ "$(eval echo \${$#})" = "$ROOTPW_UID" ] || _rp_why="its folder is not root's"
		if [ -z "$_rp_why" ]; then
			if [ "$(wc -c < "$_rp_f")" -gt 256 ] || [ "$(wc -l < "$_rp_f")" -gt 1 ]; then
				_rp_why="not one hash"
			else
				_rp_h=$(cat "$_rp_f")
				rootpw_valid "$_rp_h" || _rp_why="not a password hash"
			fi
		fi
	fi
	if [ -n "$_rp_why" ]; then
		echo "rootpw: $_rp_f ignored ($_rp_why); stock's password applies" >&2
		return 1
	fi
	printf '%s\n' "$_rp_h"
}

rootpw_bound() { grep -q " $ROOTPW_SHADOW " "$ROOTPW_MOUNTS" 2>/dev/null; }

# Root's hash when there is none: the default password "root". A fixed
# SHA-512 crypt (salt KilnDefaultRoot1), made once with
# printf 'root\n' | openssl passwd -6 -salt KilnDefaultRoot1 -stdin, so
# every build and every start has the same one; post-build.sh (main and
# recovery) writes it into the image's /etc/shadow too, so a start that
# fails before S05 leaves root/root, not an empty password.
ROOTPW_DEFAULT_HASH='$6$KilnDefaultRoot1$ncn9fESTSHX0Q0tv6B.41zOgza1l8HjNpJP5zIgZrANSNo4dVe9WTCEjEC10mJiIhhlKgEGLOVJ9lramxE4EE.'

# rootpw_apply HASH: root's hash in the running system's /etc/shadow: the
# bound copy is rewritten in place (the bind keeps its file), or a new
# copy is made and bound. The hash goes to awk through its environment.
rootpw_apply() {
	mkdir -p "$ROOTPW_RUN" || return 1
	_rp_t=$( (umask 077; mktemp "$ROOTPW_RUN/.shadow.XXXXXX") ) || return 1
	(umask 077; H=$1 awk -F: -v OFS=: '$1 == "root" { $2 = ENVIRON["H"] } 1' \
		"$ROOTPW_SHADOW" > "$_rp_t") &&
		chmod 600 "$_rp_t" && grep -q "^root:" "$_rp_t" || {
		rm -f "$_rp_t"; return 1; }
	if rootpw_bound; then
		cat "$_rp_t" > "$ROOTPW_RUN/shadow" && rm -f "$_rp_t"
	else
		mv -f "$_rp_t" "$ROOTPW_RUN/shadow" &&
			mount --bind "$ROOTPW_RUN/shadow" "$ROOTPW_SHADOW"
	fi
}

# rootpw_boot STOCK_HASH: S05's step (both OSes). Stock's hash (may be
# empty) is kept in $ROOTPW_RUN/root-hash.stock for ad5x-passwd --stock;
# Kiln's saved hash wins when it is sound. Sets ROOTPW_FROM: kiln, stock
# or default (neither: the password is "root"). Does nothing when
# /etc/shadow is already bound (a second start of S05).
rootpw_boot() {
	ROOTPW_FROM=none _rp_use=
	mkdir -p "$ROOTPW_RUN"
	rm -f "$ROOTPW_RUN/root-hash.stock"
	if rootpw_stock_ok "$1"; then
		(umask 077; printf '%s\n' "$1" > "$ROOTPW_RUN/root-hash.stock")
		_rp_use=$1 ROOTPW_FROM=stock
	fi
	if _rp_own=$(rootpw_saved); then
		_rp_use=$_rp_own ROOTPW_FROM=kiln
	fi
	[ "$ROOTPW_FROM" = none ] && ROOTPW_FROM=default _rp_use=$ROOTPW_DEFAULT_HASH
	rootpw_bound && return 0
	rootpw_apply "$_rp_use"
}

# rootpw_save HASH: Kiln's hash into ROOTPW_FILE (0600, root's), written
# beside it and renamed into place
rootpw_save() {
	rootpw_valid "$1" || return 1
	_rp_d=${ROOTPW_FILE%/*}
	[ -L "$_rp_d" ] && return 1
	if [ -d "$ROOTPW_FILE" ] && [ ! -L "$ROOTPW_FILE" ]; then return 1; fi
	mkdir -p "$_rp_d" && chmod 700 "$_rp_d" || return 1
	_rp_t=$( (umask 077; mktemp "$_rp_d/.root-password.XXXXXX") ) || return 1
	(umask 077; printf '%s\n' "$1" > "$_rp_t") && chmod 600 "$_rp_t" && sync &&
		mv -f "$_rp_t" "$ROOTPW_FILE" && sync || { rm -f "$_rp_t"; return 1; }
}

# rootpw_stock_hash: stock's hash as rootpw_boot kept it; false without
rootpw_stock_hash() {
	_rp_s=$(cat "$ROOTPW_RUN/root-hash.stock" 2>/dev/null)
	rootpw_stock_ok "$_rp_s" && printf '%s\n' "$_rp_s"
}

# rootpw_stock: back to stock's password: Kiln's file is removed and
# stock's hash (kept by rootpw_boot) applied; without one (2) the default
# "root", as at a start with no password at all.
rootpw_stock() {
	_rp_r=0
	_rp_s=$(rootpw_stock_hash) || { _rp_s=$ROOTPW_DEFAULT_HASH _rp_r=2; }
	if [ -d "$ROOTPW_FILE" ] && [ ! -L "$ROOTPW_FILE" ]; then return 1; fi
	rm -f "$ROOTPW_FILE" || return 1
	sync
	rootpw_apply "$_rp_s" || return 1
	return $_rp_r
}

# rootpw_live: what root's entry in the running /etc/shadow is: empty,
# locked, default (the default hash) or set (no hash is printed)
rootpw_live() {
	_rp_l=$(H=$ROOTPW_DEFAULT_HASH awk -F: '$1 == "root" { print ($2 == "") ? "empty" : ($2 ~ /^[!*]/) ? "locked" : ($2 == ENVIRON["H"]) ? "default" : "set"; exit }' \
		"$ROOTPW_SHADOW" 2>/dev/null)
	echo "${_rp_l:-empty}"
}

# rootpw_reset_locked: the touch screen's "reset root password" is turned
# off (ad5x-passwd --lock-reset, over SSH). The lock is a regular file of
# root's; anything else there (a link, a folder: only root writes this
# folder) counts as locked too, so an odd file never opens the reset.
rootpw_reset_locked() { [ -e "$ROOTPW_RESET_LOCK" ] || [ -L "$ROOTPW_RESET_LOCK" ]; }

# rootpw_reset_unlock: the lock removed (HelixScreen's factory reset puts
# everything back to the defaults, and the default is unlocked). A folder
# there is left (and stays locked).
rootpw_reset_unlock() {
	if [ -d "$ROOTPW_RESET_LOCK" ] && [ ! -L "$ROOTPW_RESET_LOCK" ]; then return 1; fi
	rm -f "$ROOTPW_RESET_LOCK" && sync
}
