# The web interface on port 80 (docs/web-interface.md): Fluidd (the
# default) or Mainsail, one at a time. Sourced by S61ad5x-web (at boot)
# and ad5x-webui (the switch, root). The same rules are in
# moonraker/components/kiln_os.py (GET /machine/kiln_os/webui).
#
# The choice: /data/ad5x/webui, one line "fluidd" or "mainsail" (root's
# folder: only root writes it, through ad5x-webui). Missing, unreadable,
# anything else, or a UI this image doesn't have: Fluidd.
# Each UI is served from its updatable copy in /data/ad5x/web/NAME
# (Moonraker's update manager updates it), made from the image's
# /usr/share/NAME when it is missing, broken or older than the image's
# (so a Kiln OS update never brings an older UI back); from the image's
# own files if the copy can't be made. Fluidd's copy is kept up to date
# at every boot (as before Mainsail was in); Mainsail's only once it is
# chosen, so a printer that never picks it keeps its 10 MB in /data.
# nginx's port 80 server includes /run/nginx/fluidd-root.conf (the name
# stays for every UI: plugins such as mainsail-kiln read and write it),
# one line "root DIR;".
# AD5X_DATA overrides /data, AD5X_SHARE /usr/share, AD5X_NGINX_RUN
# /run/nginx, AD5X_WEBUI_OWNER klipper:klipper (tools/test_ad5x_web.sh,
# tools/test_ad5x_webui.sh).

WEBUI_DATA=${AD5X_DATA:-/data}/ad5x
WEBUI_CHOICE=$WEBUI_DATA/webui
WEBUI_WEB=$WEBUI_DATA/web
WEBUI_SHARE=${AD5X_SHARE:-/usr/share}
WEBUI_RUN=${AD5X_NGINX_RUN:-/run/nginx}
WEBUI_ROOT_CONF=$WEBUI_RUN/fluidd-root.conf
WEBUI_MAP_CONF=$WEBUI_RUN/webui-map.conf
WEBUI_OWNER=${AD5X_WEBUI_OWNER:-klipper:klipper}
WEBUI_NAMES="fluidd mainsail"
WEBUI_DEFAULT=fluidd
# mainsail-kiln (a community plugin) serves the other UI on port 81 and
# decides which one is on port 80 itself (its WEB macro)
WEBUI_PLUGIN_CONF=$WEBUI_DATA/nginx/mainsail.conf

webui_known() {
	case " $WEBUI_NAMES " in *" $1 "*) [ -n "$1" ] ;; *) return 1 ;; esac
}

webui_title() {
	case $1 in fluidd) echo Fluidd ;; mainsail) echo Mainsail ;; *) echo "$1" ;; esac
}

webui_image() { echo "$WEBUI_SHARE/$1"; }
webui_copy_dir() { echo "$WEBUI_WEB/$1"; }

# webui_available NAME: this image has it, or a copy of it is in /data
webui_available() {
	webui_known "$1" || return 1
	[ -f "$(webui_image "$1")/index.html" ] || [ -f "$(webui_copy_dir "$1")/index.html" ]
}

# webui_stored: the stored choice, when the file is a plain file: its
# first line (of the first 32 bytes) with the whitespace around it taken
# off (else empty). Spaces inside stay, so "main sail" is no name. The
# same rule as kiln_os.py's webui_stored.
webui_stored() {
	[ -f $WEBUI_CHOICE ] && [ ! -L $WEBUI_CHOICE ] || return 0
	head -c 32 $WEBUI_CHOICE 2>/dev/null | head -n 1 |
		sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

# webui_choice: the UI for port 80 (fluidd when nothing valid is stored)
webui_choice() {
	local c
	c=$(webui_stored)
	if webui_known "$c" && webui_available "$c"; then
		echo "$c"
	else
		echo $WEBUI_DEFAULT
	fi
}

# Version from release_info.json ("v1.37.6" -> 1.37.6). Read only when it
# is a regular file, not a link: the copy in $WEBUI_WEB is klipper's, and
# a FIFO there would stop the boot at this read. Anything else: no version
# (the copy counts as broken and is made again from the image).
webui_ver() {
	[ -f "$1/release_info.json" ] && [ ! -L "$1/release_info.json" ] || return 0
	sed -n 's/.*"version" *: *"v\{0,1\}\([^"]*\)".*/\1/p' \
		"$1/release_info.json" 2>/dev/null | head -n 1
}

# webui_older A B: version A is older than B (numeric, dot by dot)
webui_older() {
	awk -v a="$1" -v b="$2" 'BEGIN {
		na = split(a, x, "."); nb = split(b, y, ".")
		n = na > nb ? na : nb
		for (i = 1; i <= n; i++) {
			if (x[i] + 0 < y[i] + 0) exit 0
			if (x[i] + 0 > y[i] + 0) exit 1
		}
		exit 1
	}'
}

# webui_unpack DIR: the copy's text files plain, as Moonraker's own
# update writes them: each X.gz web-trim.py made (js, css, svg, json,
# html, webmanifest) becomes X, or goes when X is there. The image keeps
# them gzipped only (space); the copy in /data has room, nginx gzips plain
# files as it sends them, and plugins that edit the files (mainsail-kiln
# patches Mainsail's assets/*.js and sw.js) find them, with no stale .gz
# that nginx would send instead.
webui_unpack() {
	local g p
	find "$1" -type f \( -name '*.js.gz' -o -name '*.css.gz' -o -name '*.svg.gz' \
		-o -name '*.json.gz' -o -name '*.html.gz' -o -name '*.webmanifest.gz' \) |
	while read -r g; do
		p=${g%.gz}
		if [ -f "$p" ]; then
			rm -f "$g"
		else
			zcat "$g" > "$p.tmp" && mv -f "$p.tmp" "$p" && rm -f "$g" ||
				{ rm -f "$p.tmp"; echo "web: can't unpack $g"; exit 1; }
		fi
	done
}

# webui_copy NAME: the copy in /data made from the image's when it is
# missing, broken or older (its text files plain: webui_unpack); true
# when there is a usable copy afterwards
webui_copy() {
	local img f have want
	img=$(webui_image "$1") f=$(webui_copy_dir "$1")
	if [ -f "$img/index.html" ] && mkdir -p $WEBUI_WEB 2>/dev/null; then
		chown $WEBUI_OWNER $WEBUI_WEB
		have=$(webui_ver "$f")
		want=$(webui_ver "$img")
		if [ ! -f "$f/index.html" ] || [ -z "$have" ] || webui_older "$have" "$want"; then
			echo "web: $(webui_title "$1") ${want:-?} from the image (was ${have:-none})"
			rm -rf "$f.new"
			if cp -a "$img" "$f.new" && webui_unpack "$f.new" &&
					chown -R $WEBUI_OWNER "$f.new"; then
				rm -rf "$f" && mv "$f.new" "$f"
			else
				rm -rf "$f.new"
			fi
		fi
	fi
	[ -f "$f/index.html" ]
}

# webui_dir NAME: the folder nginx serves for NAME (the copy, else the
# image's)
webui_dir() {
	if [ -f "$(webui_copy_dir "$1")/index.html" ]; then
		webui_copy_dir "$1"
	else
		webui_image "$1"
	fi
}

# webui_served: the UI the port 80 root line names now (empty: neither)
webui_served() {
	local line n
	line=$(head -c 512 $WEBUI_ROOT_CONF 2>/dev/null | head -n 1)
	for n in $WEBUI_NAMES; do
		case "$line" in
		"root $(webui_copy_dir $n);"|"root $(webui_image $n);") echo $n; return 0 ;;
		esac
	done
}

# webui_root_conf NAME: the port 80 root line for NAME, renamed into place
webui_root_conf() {
	mkdir -p $WEBUI_RUN || return 1
	echo "root $(webui_dir "$1");" > $WEBUI_ROOT_CONF.new &&
		chmod 644 $WEBUI_ROOT_CONF.new &&
		mv -f $WEBUI_ROOT_CONF.new $WEBUI_ROOT_CONF
}

# webui_map_conf NAME: nginx's maps for NAME on port 80
# ($WEBUI_RUN/webui-map.conf, included in nginx.conf's http block; the
# service worker part of docs/web-interface.md). Both interfaces have a
# service worker at /sw.js that serves their own cached page. Each page
# nginx sends sets the cookie kiln_webui=NAME; a browser whose cookie
# names the other interface (none counts as fluidd: browsers from before
# Mainsail was in saw Fluidd) gets /usr/share/ad5x/webui-reset/sw.js at
# /sw.js instead, which clears the cached pages, unregisters itself and
# reloads the tab: the old interface can't stay in the browser's cache.
# While a plugin serves both (webui_plugin), and on other ports (its
# port 81 server), no cookie and every browser gets the real /sw.js.
webui_map_conf() {
	local stale= cookie='""'
	if [ -z "$(webui_plugin)" ]; then
		cookie="\"kiln_webui=$1; Path=/; Max-Age=31536000; SameSite=Lax\""
		case $1 in
		fluidd) stale='    "1:mainsail" /.kiln-webui-stale;' ;;
		*) stale='    "1:fluidd" /.kiln-webui-stale;
    "1:" /.kiln-webui-stale;' ;;
		esac
	fi
	mkdir -p $WEBUI_RUN || return 1
	{
		echo "# Written by S61ad5x-web and ad5x-webui (lib/webui.sh): $1 on port 80"
		echo 'map "$kiln_port80:$cookie_kiln_webui" $kiln_sw_check {'
		echo '    default /sw.js;'
		[ -n "$stale" ] && echo "$stale"
		echo '}'
		echo 'map $kiln_port80 $kiln_webui_cookie {'
		echo '    default "";'
		echo "    1 $cookie;"
		echo '}'
	} > $WEBUI_MAP_CONF.new && chmod 644 $WEBUI_MAP_CONF.new &&
		mv -f $WEBUI_MAP_CONF.new $WEBUI_MAP_CONF
}

# webui_plugin: the plugin that serves both UIs itself (empty: none)
webui_plugin() {
	[ -f $WEBUI_PLUGIN_CONF ] && echo mainsail-kiln
	return 0
}
