#!/bin/sh
# Print the CHANGELOG.md section of a release, for its release notes.
#
# usage: tools/changelog_section.sh TAG [CHANGELOG]
#
# The text under "## TAG" or "## TAG (date)", or under "## Unreleased" when
# there is no such section; nothing when neither has text. The "##" heading
# itself is left out, "###" subheadings stay. tools/release.sh renames
# "## Unreleased" to "## TAG (date)" once TAG is released.
TAG=${1:?TAG}
F=${2:-$(dirname "$0")/../CHANGELOG.md}
[ -f "$F" ] || exit 0
section() {
	awk -v h="## $1" '
		$0 == h || index($0, h " (") == 1 { on = 1; next }
		on && /^## / { exit }
		on { print }' "$F" | sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}'
}
s=$(section "$TAG")
[ -n "$s" ] || s=$(section Unreleased)
[ -z "$s" ] || printf '%s\n' "$s"
