#!/bin/bash
# Cut a release: tag, release notes, artifacts with checksums, and a Gitea
# release with the artifacts attached (docs/releasing.md).
#
# usage: tools/release.sh VERSION [--public] [--draft] [--pre] [--no-build]
#                         [--notes FILE] [--dry-run] [--no-push] [--staged DIR]
#   VERSION     vMAJOR.MINOR.PATCH (e.g. v1.0.0). Any suffix, a release
#               candidate v1.0.0-rc2..9 too, makes a pre-release on Gitea and
#               GitHub: only printers on the test update channel are
#               offered it (docs/updates.md, "Test channel"). v0.1.0 and
#               its candidates are refused: they became v1.0.0
#   --public    artifacts meant for publication: they must contain no
#               Flashforge files (tools/check_vendor_free.sh must pass on
#               both images); update zips carry no kernel. Without it the
#               release is private (home Gitea only) and may contain them.
#   --draft     create the Gitea release as a draft
#   --pre       mark it as a pre-release (automatic with a suffix)
#   --no-build  use the images already in buildroot/output*/images
#   --notes F   use F as the release notes instead of the generated ones
#   --dry-run   build artifacts and notes into dist/VERSION, no tag, no upload
#   --no-push   tag and build, but don't push or upload
#   --staged D  publish the files a stage run made (tools/autobuild.sh
#               --stage, D: /work/staged/VERSION with manifest.txt) as they
#               are, nothing built or made again: tags the staged commit,
#               the notes are D's RELEASE_NOTES.md. Needs --public. When a
#               publish of D tried before (D/publish.state) already tagged
#               the staged commit, the tag is used, not made again
#
# Gitea: ~/.config/ad5x/gitea.env (GITEA_URL, GITEA_REPO, GITEA_TOKEN;
# mode 600, never in the repository). Remote "origin" must point at it.
#
# Artifacts (dist/VERSION/):
#   kiln-os-VERSION-install.zip    first install from stock (USB stick or SSH):
#                                  installer, recovery OS and main OS
#                                  (tools/make_install_stick.sh)
#   kiln-os-VERSION-update.zip     main OS update (Fluidd, ad5x-update, or a
#                                  stick in the recovery OS)
#   kiln-os-VERSION-update.swu     the same as .swu (recovery web page)
#   kiln-os-VERSION-rescue.zip     a PC's tools to check, back up and repair
#                                  the eMMC when nothing starts, with the
#                                  files that start Kiln's U-Boot over USB
#                                  (tools/make_rescue_kit.sh)
#   SHA256SUMS, RELEASE_NOTES.md
# The main OS carries the recovery OS too: after an update, a printer
# rewrites its slot A when that recovery OS differs (S99ad5x-update-recovery).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

die() { echo "release: $*" >&2; exit 1; }
usage() { sed -n '2,30p' "$0"; exit "${1:-2}"; }

VERSION= PUBLIC= DRAFT=false PRE=false BUILD=1 NOTES= DRY= PUSH=1 STAGED= TAGGED=
while [ $# -gt 0 ]; do
	case "$1" in
	--public) PUBLIC=1 ;;
	--draft) DRAFT=true ;;
	--pre) PRE=true ;;
	--no-build) BUILD= ;;
	--notes) shift; NOTES=${1:?--notes needs a file} ;;
	--dry-run) DRY=1 ;;
	--no-push) PUSH= ;;
	--staged) shift; STAGED=${1:?--staged needs a folder} ;;
	-h|--help) usage 0 ;;
	-*) die "unknown option $1" ;;
	*) [ -z "$VERSION" ] || die "one VERSION only"; VERSION=$1 ;;
	esac
	shift
done
[ -n "$VERSION" ] || usage
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] ||
	die "VERSION must look like v1.0.0 (got $VERSION)"
# Release candidates stop at -rc9: Fluidd sorts -rc10 before -rc9; v0.1.0
# and its candidates became v1.0.0 (docs/releasing.md, "Release candidates")
python3 tools/release_version.py rc "$VERSION" || exit 1
# A version with a suffix, a release candidate (-rcN) too, is a
# pre-release on Gitea and GitHub: printers on the stable update channel
# read releases/latest, which skips it, and stay on the last vX.Y.Z; the
# test channel takes it (docs/releasing.md, "Release candidates")
if [ "$(python3 tools/release_version.py pre "$VERSION")" = true ]; then
	PRE=true
fi

# --- Checks --------------------------------------------------------------
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
	[ -n "$DRY" ] || die "uncommitted changes; commit or stash them first"
	echo "release: dry run on a tree with uncommitted changes"
fi
# A staged build (--staged): its manifest names the version and the commit
# that was built and tested; the tags on origin count too
staged() { sed -n "s/^$1=//p" "$STAGED/manifest.txt"; }
if [ -n "$STAGED" ]; then
	[ -f "$STAGED/manifest.txt" ] || die "--staged: no $STAGED/manifest.txt"
	[ "$(staged version)" = "$VERSION" ] || die "--staged: $STAGED holds $(staged version), not $VERSION"
	[ -n "$PUBLIC" ] || die "--staged: only with --public (the stage checked its images vendor-free)"
	BUILD=
	git fetch -q --tags origin || die "git fetch --tags origin"
fi
if git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
	# A publish of this staged build tried before and tagged the staged
	# commit: it goes on from there (Gitea and GitHub reuse what is there)
	if [ -n "$STAGED" ] && [ -f "$STAGED/publish.state" ] &&
		[ "$(git rev-parse "refs/tags/$VERSION^{commit}")" = "$(staged commit)" ]; then
		TAGGED=1
		echo "release: tag $VERSION is there from an earlier try of this publish: not tagged again"
	else
		die "tag $VERSION exists already"
	fi
fi
if [ -n "$STAGED" ]; then
	COMMIT=$(staged commit)
	# HEAD is the staged commit, or the CHANGELOG commit an earlier try of
	# this publish put on it (nothing else changed)
	[ "$(git rev-parse HEAD)" = "$COMMIT" ] || {
		[ -n "$TAGGED" ] && [ "$(git rev-parse -q --verify HEAD^)" = "$COMMIT" ] &&
			git diff --quiet "$COMMIT" HEAD -- . ':(exclude)CHANGELOG.md'
	} || die "--staged: HEAD $(git rev-parse --short HEAD) is not the staged commit ${COMMIT:0:12}"
else
	COMMIT=$(git rev-parse HEAD)
fi
PREV=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)	# not the daily klipper-/moonraker- tags
if [ -z "$DRY" ] && [ -n "$PUSH" ]; then
	[ -f ~/.config/ad5x/gitea.env ] || die "no ~/.config/ad5x/gitea.env"
	# shellcheck disable=SC1090
	set -a; . ~/.config/ad5x/gitea.env; set +a
	: "${GITEA_URL:?}" "${GITEA_REPO:?}" "${GITEA_TOKEN:?}"
	git remote get-url origin >/dev/null 2>&1 || die "no git remote origin"
	git fetch -q origin
	git merge-base --is-ancestor "$COMMIT" "origin/$(git branch --show-current)" ||
		echo "release: note: $COMMIT is not on origin yet; it gets pushed"
fi
if [ -n "$PUBLIC" ]; then
	[ -x tools/check_vendor_free.sh ] ||
		die "--public needs tools/check_vendor_free.sh (vendor-free images, docs/install.md)"
fi

# --- Build ---------------------------------------------------------------
build() {	# OUTDIR DEFCONFIG
	bash -c "make -C buildroot/src O=$REPO/$1 BR2_EXTERNAL=$REPO/buildroot $2 >/dev/null &&
		make -C buildroot/src O=$REPO/$1 BR2_EXTERNAL=$REPO/buildroot" \
		> "$DIST/build-${1##*/}.log" 2>&1 ||
		die "build in $1 failed, see $DIST/build-${1##*/}.log"
}
DIST=$REPO/dist/$VERSION
NAME=kiln-os-$VERSION
rm -rf "$DIST"
mkdir -p "$DIST"
if [ -n "$STAGED" ]; then
	# The staged files exactly as they were tested, checked against the
	# stage's SHA256SUMS (it lists the licences file too: GitHub's own
	# SHA256SUMS); the source archives GitHub lacks are in D/sources
	cp -a "$STAGED/$NAME"-* "$STAGED/SHA256SUMS" "$STAGED/RELEASE_NOTES.md" "$DIST/" ||
		die "--staged: copying the files from $STAGED failed"
	( cd "$DIST" && sha256sum -c --quiet SHA256SUMS ) || die "--staged: the files don't match the staged SHA256SUMS"
	for f in "$DIST/$NAME"-*; do
		grep -q "  $(basename "$f")\$" "$DIST/SHA256SUMS" ||
			die "--staged: $(basename "$f") is not in the staged SHA256SUMS"
	done
	[ -n "$NOTES" ] || NOTES=$STAGED/RELEASE_NOTES.md
	cp "$NOTES" "$DIST/RELEASE_NOTES.md"
	export KILN_STAGED_SOURCES=$STAGED/sources
	echo "release: the staged $VERSION (commit ${COMMIT:0:12}), nothing built or made again"
fi
# Not for a staged build: the images, the artifacts and the notes are made here
if [ -z "$STAGED" ]; then
if [ -n "$BUILD" ]; then
	echo "release: building the main OS and the recovery OS (logs in $DIST)"
	[ -n "$PUBLIC" ] && export AD5X_VENDOR_FREE=1
	# /etc/kiln-version in the image (post-build.sh): the printer's
	# update check compares it with the newest release
	export AD5X_VERSION=$VERSION
	# The recovery OS first: the main image carries it (S99ad5x-update-recovery)
	build buildroot/output-recovery ad5x_recovery_defconfig
	export AD5X_RECOVERY_IMAGE=$REPO/buildroot/output-recovery/images/rootfs.squashfs
	build buildroot/output ad5x_defconfig
fi
MAIN=buildroot/output/images/rootfs.squashfs
REC=buildroot/output-recovery/images/rootfs.squashfs
[ -f "$MAIN" ] && [ -f "$REC" ] || die "missing $MAIN or $REC (build first)"
# The main image must carry exactly this recovery OS: printers updated with
# it rewrite their slot A from that copy
inmain=$(buildroot/output/host/bin/unsquashfs -cat "$MAIN" usr/share/ad5x/recovery/rootfs.sha256 2>/dev/null || true)
[ "$inmain" = "$(sha256sum < "$REC" | cut -d' ' -f1)" ] ||
	die "the main image doesn't carry $REC (rebuild the main OS after the recovery OS)"

if [ -n "$PUBLIC" ]; then
	echo "release: checking that no Flashforge files are in the images"
	tools/check_vendor_free.sh "$MAIN" || die "main image contains Flashforge files"
	tools/check_vendor_free.sh "$REC" || die "recovery image contains Flashforge files"
fi
# The rescue kit (below) takes the USB start files from the recovery OS's
# boot loader build: checked here, before the artifacts, so a build
# without them stops the release early (make_rescue_kit.sh checks them again)
BLDIST=buildroot/output-recovery/images/bootloader
for f in spl-usb2.bin u-boot.bin; do
	[ -f "$BLDIST/$f" ] || die "$BLDIST/$f missing: the boot loader build has no USB stage 2 (u-boot/build.sh); the rescue kit needs it"
done

# --- Artifacts -------------------------------------------------------------
KOPT=()
[ -n "$PUBLIC" ] && KOPT=(-K)	# no stock kernel in public update files
tools/make_swu.sh -r "$MAIN" "${KOPT[@]}" -V "$VERSION" --both \
	-o "$DIST/$NAME-update.swu" >/dev/null
[ -f "$DIST/$NAME-update.zip" ] || die "make_swu.sh wrote no zip"
SOPT=(--private)
[ -n "$PUBLIC" ] && SOPT=()	# public: every file checked vendor-free
tools/make_install_stick.sh -r "$REC" -m "$DIST/$NAME-update.zip" -V "$VERSION" \
	"${SOPT[@]}" -o "$DIST/install" --zip "$DIST/$NAME-install.zip" \
	> "$DIST/install-stick.log" 2>&1 || die "make_install_stick.sh failed, see $DIST/install-stick.log"
rm -rf "$DIST/install"
# The rescue kit: the PC tools and the files that start Kiln's U-Boot over
# USB, from the recovery OS's boot loader build (docs/emmc-repair.md)
tools/make_rescue_kit.sh -b "$BLDIST" \
	-V "$VERSION" -o "$DIST/$NAME-rescue.zip" >/dev/null ||
	die "make_rescue_kit.sh failed"
if [ -n "$PUBLIC" ]; then
	tools/check_vendor_free.sh -q "$DIST/$NAME-rescue.zip" ||
		die "the rescue kit contains Flashforge files"
fi

# --- Notes -----------------------------------------------------------------
if [ -n "$NOTES" ]; then
	cp "$NOTES" "$DIST/RELEASE_NOTES.md"
else
	{
		echo "# Kiln OS $VERSION"
		echo
		if [ -n "$PUBLIC" ]; then
			echo "Contains no Flashforge files: a first install copies them from"
			echo "the printer itself (see docs/install.md)."
		else
			echo "Private build: the images contain Flashforge files from the"
			echo "stock firmware. Do not publish these artifacts."
		fi
		echo
		echo "New install (from the stock firmware): \`$NAME-install.zip\`,"
		echo "see docs/install.md."
		echo "Your stock/zMod settings and configs are not carried over (back them up),"
		echo "Kiln OS updates the boards' firmware itself at its first start."
		echo
		echo "Updating a printer already on Kiln OS: Fluidd → Software Updates →"
		echo "Kiln OS → Update, or copy \`$NAME-update.zip\` to it and run"
		echo "\`ad5x-update --reboot FILE\`, or put it on a USB stick with an empty"
		echo "\`ad5x-autoupdate\` file and start the recovery OS (docs/updates.md,"
		echo "\"From a USB stick\")."
		echo
		echo "A printer that doesn't start at all: \`$NAME-rescue.zip\` has the"
		echo "PC tools to check, back up and repair its eMMC over USB, or with"
		echo "USBCloner and the network (docs/emmc-repair.md)."
		echo
		# What's new: the release's CHANGELOG.md section
		new=$(tools/changelog_section.sh "$VERSION")
		if [ -n "$new" ]; then
			echo "## What's new"
			echo
			echo "$new"
			echo
		fi
		if [ -n "$PREV" ]; then
			echo "## Changes since $PREV"
			RANGE=$PREV..$COMMIT
		else
			echo "## Changes"
			RANGE=$COMMIT
		fi
		echo
		git log --reverse --no-merges --format='- %s' "$RANGE"
		echo
		echo "Built from \`$COMMIT\`."
	} > "$DIST/RELEASE_NOTES.md"
fi
( cd "$DIST" && sha256sum "$NAME"-* > SHA256SUMS )
fi	# not a staged build
echo "release: artifacts in $DIST:"
( cd "$DIST" && ls -l "$NAME"-* SHA256SUMS RELEASE_NOTES.md | awk '{print "  " $5 "\t" $9}' )

[ -n "$DRY" ] && { echo "release: dry run, no tag, nothing uploaded"; exit 0; }

# --- Tag, push, Gitea release ------------------------------------------------
if [ -z "$TAGGED" ]; then
	git tag -a "$VERSION" -F "$DIST/RELEASE_NOTES.md" "$COMMIT"
	echo "release: tagged $VERSION at $COMMIT"
fi
# CHANGELOG.md: the released entries move under "## VERSION (date)" and a
# new empty "## Unreleased" starts, so the next release's notes don't
# repeat them. A commit of its own after the tagged one: the tag stays on
# the commit the images were built from.
python3 tools/release_version.py changelog "$VERSION" "$(date +%F)" CHANGELOG.md ||
	echo "release: warning: CHANGELOG.md not renamed"
if ! git diff --quiet -- CHANGELOG.md; then
	git commit -q -m "CHANGELOG: $VERSION released" -- CHANGELOG.md
	echo "release: CHANGELOG.md: Unreleased is now $VERSION"
fi
[ -n "$PUSH" ] || { echo "release: --no-push: not pushed or uploaded"; exit 0; }
# The branch up to the tag only when it has commits the remote lacks (the
# builder's "Upstream" commit); master may have moved on meanwhile, the tag
# still names the released commit
BR=$(git branch --show-current)
git fetch -q origin
# refs/tags/: a release branch can have the version's name (v1.0.1-rc3), and
# then "git push origin v1.0.1-rc3" fails ("matches more than one")
if git merge-base --is-ancestor "$COMMIT" "origin/$BR" 2>/dev/null; then
	git push -q origin "refs/tags/$VERSION"
else
	git push -q origin "$COMMIT:refs/heads/$BR" "refs/tags/$VERSION" ||
		die "push failed: origin/$BR has commits this release lacks (rebase, then release again)"
fi
# Then the CHANGELOG commit. The release stands without it: when the branch
# moved on meanwhile it is not pushed (no rebase here: the public source
# export below must stay the released tree) and the rename is left to do
# by hand.
if [ "$(git rev-parse HEAD)" != "$COMMIT" ]; then
	git push -q origin "HEAD:refs/heads/$BR" ||
		echo "release: warning: CHANGELOG.md commit not pushed: rename \"## Unreleased\" to \"## $VERSION ($(date +%F))\" on $BR by hand"
fi

API=$GITEA_URL/api/v1/repos/$GITEA_REPO
AUTH=(-H "Authorization: token $GITEA_TOKEN")
BODY=$(python3 -c 'import json,sys; print(json.dumps({"tag_name": sys.argv[1],
	"name": "Kiln OS " + sys.argv[1], "body": open(sys.argv[2]).read(),
	"draft": sys.argv[3] == "true", "prerelease": sys.argv[4] == "true"}))' \
	"$VERSION" "$DIST/RELEASE_NOTES.md" "$DRAFT" "$PRE")
# Gitea's create call can fail right after the tag push (HTTP 500, "UNIQUE
# constraint failed: release.repo_id, release.tag_name", v1.0.0-rc7): Gitea
# is still adding its own row for the new tag. Wait and try again. When a
# release for the tag is there by then (an earlier try that Gitea finished
# after the time-out), it is set to this release's settings and used.
gitea_release() {
	local try rel rid
	for try in 1 2 3 4; do
		rel=$(curl -sf -m 60 "${AUTH[@]}" -H "Content-Type: application/json" \
			-X POST "$API/releases" -d "$BODY") && { echo "$rel"; return 0; }
		if rel=$(curl -sf -m 60 "${AUTH[@]}" "$API/releases/tags/$VERSION") &&
			rid=$(echo "$rel" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])') &&
			rel=$(curl -sf -m 60 "${AUTH[@]}" -H "Content-Type: application/json" \
				-X PATCH "$API/releases/$rid" -d "$BODY"); then
			echo "release: using the Gitea release already there for $VERSION" >&2
			echo "$rel"
			return 0
		fi
		[ "$try" -lt 4 ] || break
		echo "release: creating the Gitea release failed (try $try of 4), again in ${RETRY_WAIT}s" >&2
		sleep "$RETRY_WAIT"
	done
	return 1
}
RETRY_WAIT=${KILN_RELEASE_RETRY_WAIT:-10}
REL=$(gitea_release) || die "creating the Gitea release failed"
RID=$(echo "$REL" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
# Files a release found already there has (from that earlier try) are kept
HAVE=$(echo "$REL" | python3 -c 'import json,sys
for a in json.load(sys.stdin).get("assets") or []: print(a["name"])')
for f in "$DIST/$NAME"-* "$DIST/SHA256SUMS"; do
	if printf '%s\n' "$HAVE" | grep -qxF "$(basename "$f")"; then
		echo "release: $(basename "$f") is there already"
		continue
	fi
	curl -sf -m 1800 "${AUTH[@]}" -X POST \
		"$API/releases/$RID/assets?name=$(basename "$f")" \
		-F "attachment=@$f" >/dev/null || die "uploading $(basename "$f") failed"
	echo "release: uploaded $(basename "$f")"
done
echo "release: $GITEA_URL/$GITEA_REPO/releases/tag/$VERSION"

# The public GitHub repository (source export and release), when configured
if [ -n "$PUBLIC" ] && [ "$DRAFT" = false ] && [ -x tools/publish_github.sh ]; then
	GHPRE=()
	[ "$PRE" = true ] && GHPRE=(--prerelease)
	tools/publish_github.sh os "$VERSION" "$DIST" "${GHPRE[@]}" || die "GitHub release failed"
fi
