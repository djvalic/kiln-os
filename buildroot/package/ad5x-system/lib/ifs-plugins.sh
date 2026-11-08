# Klipper plugins that drive the IFS themselves (S61klipper, ad5x-mcu).
# PD is the printer_data directory (/home/klipper/printer_data).

# ifs_plugins PD: the names of the enabled plugins (an [include] line in
# plugins.cfg that isn't commented out) whose plugin.json has "owns_ifs"
# true (plugin API 1.5), or the older "requires_ifs_klipper" /
# "requires_klipper_firmware"
ifs_plugins() {
	[ -f "$1/config/plugins.cfg" ] || return 0
	sed -n 's|^[[:space:]]*\[include[[:space:]]*\([^[:space:]]*\)/plugi.*|\1|p' \
		"$1/config/plugins.cfg" | while read -r d; do
		grep -qE '"(owns_ifs|requires_ifs_klipper|requires_klipper_firmware)"[[:space:]]*:[[:space:]]*true' \
			"$d/plugin.json" 2>/dev/null && echo "${d##*/}"
	done
}

# disable_plugins PD NAME...: turn plugins off as DISABLE_PLUGIN does (comment
# out their include), keeping the file itself: it is Klipper's user's
disable_plugins() {
	pf=$1/config/plugins.cfg; shift
	pt=$(mktemp) || return 1
	cp "$pf" "$pt" || { rm -f "$pt"; return 1; }
	for pn; do
		sed -i "s|^\([[:space:]]*\[include[^]]*/$pn/plugi\)|#\1|" "$pt" || { rm -f "$pt"; return 1; }
	done
	cat "$pt" > "$pf"
	prc=$?
	rm -f "$pt"
	return $prc
}
