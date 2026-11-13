#!/bin/bash
# Cut a release: tag, release notes, artifacts with checksums, and a Gitea
# release with the artifacts attached (docs/releasing.md).
#
# usage: tools/release.sh VERSION [--public] [--draft] [--pre] [--no-build]
#                         [--notes FILE] [--dry-run] [--no-push]
#   VERSION     vMAJOR.MINOR.PATCH (e.g. v0.1.0; -rc1 etc. allowed)
#   --public    artifacts meant for publication: they must contain no
#               Flashforge files (tools/check_vendor_free.sh must pass on
#               both images); update zips carry no kernel. Without it the
#               release is private (home Gitea only) and may contain them.
#   --draft     create the Gitea release as a draft
#   --pre       mark it as a pre-release
#   --no-build  use the images already in buildroot/output*/images
#   --notes F   use F as the release notes instead of the generated ones
#   --dry-run   build artifacts and notes into dist/VERSION, no tag, no upload
#   --no-push   tag and build, but don't push or upload
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
#   SHA256SUMS, RELEASE_NOTES.md
# The main OS carries the recovery OS too: after an update, a printer
# rewrites its slot A when that recovery OS differs (S99ad5x-update-recovery).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

die() { echo "release: $*" >&2; exit 1; }
usage() { sed -n '2,24p' "$0"; exit "${1:-2}"; }

VERSION= PUBLIC= DRAFT=false PRE=false BUILD=1 NOTES= DRY= PUSH=1
while [ $# -gt 0 ]; do
	case "$1" in
	--public) PUBLIC=1 ;;
	--draft) DRAFT=true ;;
	--pre) PRE=true ;;
	--no-build) BUILD= ;;
	--notes) shift; NOTES=${1:?--notes needs a file} ;;
	--dry-run) DRY=1 ;;
	--no-push) PUSH= ;;
	-h|--help) usage 0 ;;
	-*) die "unknown option $1" ;;
	*) [ -z "$VERSION" ] || die "one VERSION only"; VERSION=$1 ;;
	esac
	shift
done
[ -n "$VERSION" ] || usage
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] ||
	die "VERSION must look like v0.1.0 (got $VERSION)"
case "$VERSION" in *-*) PRE=true ;; esac

# --- Checks --------------------------------------------------------------
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
	[ -n "$DRY" ] || die "uncommitted changes; commit or stash them first"
	echo "release: dry run on a tree with uncommitted changes"
fi
if git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
	die "tag $VERSION exists already"
fi
COMMIT=$(git rev-parse HEAD)
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
rm -rf "$DIST"
mkdir -p "$DIST"
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

# --- Artifacts -------------------------------------------------------------
NAME=kiln-os-$VERSION
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
echo "release: artifacts in $DIST:"
( cd "$DIST" && ls -l "$NAME"-* SHA256SUMS RELEASE_NOTES.md | awk '{print "  " $5 "\t" $9}' )

[ -n "$DRY" ] && { echo "release: dry run, no tag, nothing uploaded"; exit 0; }

# --- Tag, push, Gitea release ------------------------------------------------
git tag -a "$VERSION" -F "$DIST/RELEASE_NOTES.md" "$COMMIT"
echo "release: tagged $VERSION at $COMMIT"
[ -n "$PUSH" ] || { echo "release: --no-push: not pushed or uploaded"; exit 0; }
# The branch only when it has commits the remote lacks (the builder's
# "Upstream" commit); master may have moved on meanwhile, the tag still
# names the released commit
BR=$(git branch --show-current)
git fetch -q origin
if git merge-base --is-ancestor HEAD "origin/$BR" 2>/dev/null; then
	git push -q origin "$VERSION"
else
	git push -q origin "$BR" "$VERSION" ||
		die "push failed: origin/$BR has commits this release lacks (rebase, then release again)"
fi

API=$GITEA_URL/api/v1/repos/$GITEA_REPO
AUTH=(-H "Authorization: token $GITEA_TOKEN")
BODY=$(python3 -c 'import json,sys; print(json.dumps({"tag_name": sys.argv[1],
	"name": "Kiln OS " + sys.argv[1], "body": open(sys.argv[2]).read(),
	"draft": sys.argv[3] == "true", "prerelease": sys.argv[4] == "true"}))' \
	"$VERSION" "$DIST/RELEASE_NOTES.md" "$DRAFT" "$PRE")
REL=$(curl -sf -m 60 "${AUTH[@]}" -H "Content-Type: application/json" \
	-X POST "$API/releases" -d "$BODY") || die "creating the Gitea release failed"
RID=$(echo "$REL" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
for f in "$DIST/$NAME"-* "$DIST/SHA256SUMS"; do
	curl -sf -m 1800 "${AUTH[@]}" -X POST \
		"$API/releases/$RID/assets?name=$(basename "$f")" \
		-F "attachment=@$f" >/dev/null || die "uploading $(basename "$f") failed"
	echo "release: uploaded $(basename "$f")"
done
echo "release: $GITEA_URL/$GITEA_REPO/releases/tag/$VERSION"

# The public GitHub repository (source export and release), when configured
if [ -n "$PUBLIC" ] && [ "$DRAFT" = false ] && [ -x tools/publish_github.sh ]; then
	tools/publish_github.sh os "$VERSION" "$DIST" || die "GitHub release failed"
fi
