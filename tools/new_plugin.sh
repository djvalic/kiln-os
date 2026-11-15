#!/bin/bash
# Make a new Kiln OS plugin folder from tools/plugin-template:
# plugin.json (requires_os: this system's plugin API), plugin.cfg with one
# macro, README.md and tests/; --python adds a Klipper module
# (extras/<name>.py: a command and printer.<name>), --moonraker a Moonraker
# component (moonraker/components/<name>.py: an HTTP endpoint).
# Walkthrough: docs/plugin-first.md. Check it with tools/check_plugin.py.
#
# usage: tools/new_plugin.sh NAME [--python] [--moonraker]
#   NAME  the plugin name, or a path whose last part is the name (the
#         folder is made there; it must not exist yet)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
TPL=$HERE/plugin-template
usage() { echo "usage: $0 NAME [--python] [--moonraker]" >&2; exit 2; }

dest= python= moonraker=
for a in "$@"; do
	case $a in
	--python) python=1 ;;
	--moonraker) moonraker=1 ;;
	-h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
	-*) usage ;;
	*) [ -z "$dest" ] || usage; dest=$a ;;
	esac
done
[ -n "$dest" ] || usage
dest=${dest%/}
name=$(basename "$dest")

# A plugin name the loader takes (a-z, 0-9, - _, at most 48) that also
# makes valid Python module and Klipper command names (a letter first, no
# digit second: Klipper refuses MY3_HELLO)
if ! printf '%s\n' "$name" | grep -Eq '^[a-z][a-z0-9_-]{0,47}$'; then
	echo "new_plugin: '$name': use a-z, 0-9, - and _, starting with a letter (at most 48)" >&2
	exit 1
fi
case $name in
?[0-9]*) echo "new_plugin: '$name': no digit as the second character (Klipper refuses such command names)" >&2; exit 1 ;;
esac
mod=$(printf '%s' "$name" | tr '-' '_')
case $mod in
ad5x_*|kiln_*) echo "new_plugin: '$name': names starting with ad5x or kiln are kept for Kiln OS's own modules" >&2; exit 1 ;;
esac
macro=$(printf '%s' "$mod" | tr '[:lower:]' '[:upper:]')
class=$(printf '%s' "$mod" | awk -F_ '{for (i = 1; i <= NF; i++) printf "%s", toupper(substr($i, 1, 1)) substr($i, 2)}')
api=$(sed -n 's/^PLUGIN_API_VERSION = "\([0-9.]*\)".*/\1/p' "$HERE/../klipper/extras/ad5x_plugins.py")
[ -n "$api" ] || { echo "new_plugin: no PLUGIN_API_VERSION in klipper/extras/ad5x_plugins.py" >&2; exit 1; }
if [ -e "$dest" ]; then
	echo "new_plugin: $dest exists already" >&2
	exit 1
fi

# put SRC DEST: a template file with the names filled in
put() {
	mkdir -p "$(dirname "$dest/$2")"
	sed -e "s/__NAME__/$name/g" -e "s/__MOD__/$mod/g" -e "s/__MACRO__/$macro/g" \
		-e "s/__CLASS__/$class/g" -e "s/__API__/$api/g" "$TPL/$1" > "$dest/$2"
}
mkdir -p "$dest"
put plugin.json plugin.json
put README.md README.md
put tests/test_plugin.py tests/test_plugin.py
if [ -n "$python" ]; then
	put plugin-python.cfg plugin.cfg
	put extras/__MOD__.py "extras/$mod.py"
	put tests/test_klipper.py tests/test_klipper.py
	printf -- '- `extras/%s.py`: Klipper module, the `%s_GREET` command and\n  `printer.%s`\n' \
		"$mod" "$macro" "$mod" >> "$dest/README.md"
else
	put plugin.cfg plugin.cfg
fi
if [ -n "$moonraker" ]; then
	put moonraker.conf moonraker.conf
	put moonraker/components/__MOD__.py "moonraker/components/$mod.py"
	put tests/test_moonraker.py tests/test_moonraker.py
	printf -- '- `moonraker.conf`, `moonraker/components/%s.py`: Moonraker part,\n  `GET /server/%s/hello`\n' \
		"$mod" "$mod" >> "$dest/README.md"
fi
printf -- '- `tests/`: offline tests (`python3 tests/test_plugin.py`; Kiln OS'"'"'s\n  `tools/check_plugin.py` runs them all)\n' >> "$dest/README.md"
chmod +x "$dest"/tests/test_*.py
echo "Made $dest (plugin $name, plugin API $api)"
echo "Next: edit it, then run $HERE/check_plugin.py $dest (docs/plugin-first.md)"
