#!/bin/bash
# The source code behind a public Kiln OS release (GPL and other licences
# that ask for it), published next to the release on GitHub.
#
# usage: tools/publish_sources.sh TAG DIST
#   (called by tools/publish_github.sh os; needs GITHUB_REPO and GH_TOKEN)
#
# Writes DIST/kiln-os-TAG-licenses.tar.gz (attached to the release TAG):
#   README.txt         which source archive holds what, and where
#   main/, recovery/   Buildroot's legal-info for both images: manifest.csv
#                      (package, version, licence, source), the licence
#                      texts, buildroot.config, legal-info.sha256 (sha256 of
#                      every source file)
# and uploads the sources to the GitHub release "sources" (a pre-release, so
# never "latest": the printers' update check reads releases/latest). Each
# archive is named after its package version and uploaded once; later
# releases that use the same version share it:
#   src-<package>-<version>.tar          from legal-info (tarball + patches)
#   src-linux-ingenic-6.6-<commit>.tar.xz  the 6.6 kernel tree (Ingenic SDK)
#                                        our kernel is built from; our
#                                        patches/config are kernel-ingenic66/
#   src-linux-7.3.3.tar.xz               kernel.org tree the opt-in 7.3 kernel
#                                        is built from (+ kernel-mainline/)
#   src-linux-5.10.186.tar.xz            kernel.org tree chainload.ko builds
#                                        against (kernel-ingenic66/chainload)
#   src-klipper-mcu-<commit>.tar.gz      Klipper the boards' firmware is built
#                                        from (+ klipper/mcu-patches, -configs)
#   src-fluidd-source-<version>.tar.gz   Fluidd's source (the image ships its
#                                        built web files)
#   src-buildroot-<version>.tar.gz       Buildroot itself
# Our own packages (ad5x-*, local source) are this repository at TAG.
# SOURCES_DRY=DIR: nothing on GitHub; the archives are written to DIR.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"
die() { echo "publish_sources: $*" >&2; exit 1; }
TAG=${1:?TAG} DIST=${2:?DIST}
DRY=${SOURCES_DRY:-}
[ -n "$DRY" ] || : "${GITHUB_REPO:?}" "${GH_TOKEN:?}"
GITHUB_REPO=${GITHUB_REPO:-OWNER/REPO}
SRC_TAG=sources
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
# Same bytes for the same content (an archive is never uploaded twice)
TARX=(tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner)

# --- legal-info of both images ----------------------------------------------
for o in output output-recovery; do
	[ -d "buildroot/$o" ] || die "no buildroot/$o (build first)"
	make -C buildroot/src O="$REPO/buildroot/$o" BR2_EXTERNAL="$REPO/buildroot" \
		legal-info > "$work/legal-$o.log" 2>&1 || die "legal-info in buildroot/$o failed"
done

# --- the "sources" release -----------------------------------------------------
if [ -n "$DRY" ]; then
	mkdir -p "$DRY"; ls "$DRY" > "$work/have"
elif ! gh release view "$SRC_TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
	gh release create "$SRC_TAG" --repo "$GITHUB_REPO" --target main --prerelease \
		--latest=false --title "Source code of Kiln OS releases" --notes \
"The source code of the third-party software in Kiln OS releases (GPL and
other licences), one archive per package version. Each release's
\`kiln-os-<version>-licenses.tar.gz\` lists the archives it uses.
Kiln OS's own code is this repository at the release's tag." >/dev/null ||
		die "creating the release $SRC_TAG"
fi
[ -n "$DRY" ] || gh release view "$SRC_TAG" --repo "$GITHUB_REPO" --json assets \
	-q '.assets[].name' > "$work/have" || die "listing $SRC_TAG"
up=0
upload() {	# FILE: attach to the sources release
	if [ -n "$DRY" ]; then cp "$1" "$DRY/"
	else gh release upload "$SRC_TAG" --repo "$GITHUB_REPO" "$1" >/dev/null ||
		die "uploading $(basename "$1")"
	fi
	echo "$(basename "$1")" >> "$work/have"
	up=$((up + 1))
	echo "publish_sources: uploaded $(basename "$1") ($(du -h "$1" | cut -f1))"
}
have() { grep -qx "$1" "$work/have"; }
LIST=$work/list	# PACKAGE VERSION LICENCE -> archive, for README.txt
: > "$LIST"

# Packages from legal-info (both images; the same version once)
for o in output output-recovery; do
	li=buildroot/$o/legal-info
	python3 - "$li/manifest.csv" <<'EOF' > "$work/pk-$o"
import csv, sys
for r in csv.DictReader(open(sys.argv[1])):
    local = r["SOURCE SITE"].startswith("/")
    print("\t".join([r["PACKAGE"], r["VERSION"], r["LICENSE"],
                     "local" if local else "remote"]))
EOF
	while IFS=$'\t' read -r pkg ver lic kind; do
		if [ "$kind" = local ]; then
			printf '%s\t%s\t%s\t%s\n' "$pkg" "$ver" "$lic" \
				"this repository at $TAG" >> "$LIST"
			continue
		fi
		d=$li/sources/$pkg-$ver
		[ -d "$d" ] || die "no source directory $d"
		a=src-$pkg-$ver.tar
		if ! have "$a"; then
			"${TARX[@]}" -cf "$work/$a" -C "$li/sources" "$pkg-$ver"
			upload "$work/$a"
			rm -f "$work/$a"
		fi
		printf '%s\t%s\t%s\t%s\n' "$pkg" "$ver" "$lic" "$a" >> "$LIST"
	done < "$work/pk-$o"
done

# Our 6.6 kernel: the SDK's kernel tree at the commit it was built from
SDK=$(sed -n 's/^BR2_PACKAGE_AD5X_KERNEL66_SDK="\(.*\)"$/\1/p' buildroot/output/.config)
SDK=${SDK//'$(HOME)'/$HOME}
if [ -n "$SDK" ]; then
	[ -d "$SDK/.git" ] || die "no git checkout at the kernel SDK $SDK"
	c=$(git -C "$SDK" rev-parse HEAD)
	a=src-linux-ingenic-6.6-${c:0:12}.tar.xz
	if ! have "$a"; then
		git -C "$SDK" archive --prefix="linux-ingenic-6.6-${c:0:12}/" "$c" kernel/kernel-6.6 |
			xz -T0 -6 > "$work/$a"
		upload "$work/$a"
		rm -f "$work/$a"
	fi
	printf '%s\t%s\t%s\t%s\n' linux-ingenic-6.6 "${c:0:12}" GPL-2.0 \
		"$a (+ kernel-ingenic66/ in this repository at $TAG: patches, config, device tree)" >> "$LIST"
	# chainload.ko: built against kernel.org's 5.10.186 (setup.sh)
	k=$(sed -n 's/^BR2_PACKAGE_AD5X_KERNEL66_KDIR510="\(.*\)"$/\1/p' buildroot/output/.config)
	k=${k//'$(HOME)'/$HOME}.tar.xz
	a=src-linux-5.10.186.tar.xz
	if ! have "$a"; then
		if [ -f "$k" ]; then
			cp "$k" "$work/$a"
		else
			curl -fsSL -o "$work/$a" https://cdn.kernel.org/pub/linux/kernel/v5.x/linux-5.10.186.tar.xz ||
				die "downloading linux-5.10.186"
		fi
		upload "$work/$a"
		rm -f "$work/$a"
	fi
	printf '%s\t%s\t%s\t%s\n' linux 5.10.186 GPL-2.0 \
		"$a (headers for chainload.ko, kernel-ingenic66/chainload/ in this repository)" >> "$LIST"
fi

# The opt-in 7.3 kernel: kernel.org's tarball (kernel-mainline/build.sh pins
# it) plus kernel-mainline/ in this repository (patches, kiln.config)
if grep -q '^BR2_PACKAGE_AD5X_KERNEL_MAINLINE=y' buildroot/output/.config; then
	kv=$(sed -n 's/^KVER=//p' kernel-mainline/build.sh)
	ks=$(sed -n 's/^KSHA256=//p' kernel-mainline/build.sh)
	a=src-linux-$kv.tar.xz
	if ! have "$a"; then
		k=$(ls buildroot/dl/ad5x-kernel-mainline/linux-$kv.tar.xz 2>/dev/null || true)
		if [ -n "$k" ]; then
			cp "$k" "$work/$a"
		else
			curl -fsSL -o "$work/$a" "https://cdn.kernel.org/pub/linux/kernel/v${kv%%.*}.x/linux-$kv.tar.xz" ||
				die "downloading linux-$kv"
		fi
		echo "$ks  $work/$a" | sha256sum -c --quiet || die "linux-$kv: sha256 mismatch"
		upload "$work/$a"
		rm -f "$work/$a"
	fi
	printf '%s\t%s\t%s\t%s\n' linux "$kv" GPL-2.0 \
		"$a (+ kernel-mainline/ in this repository at $TAG: patches, kiln.config, build.sh)" >> "$LIST"
fi

# The boards' firmware: upstream Klipper at the commit tools/build_mcu.sh uses
rev=$(sed -n 's/^[[:space:]]*KLIPPER_REV=\([0-9a-f]*\).*/\1/p' tools/build_mcu.sh | head -1)
[ -n "$rev" ] || die "no KLIPPER_REV in tools/build_mcu.sh"
full=$(git ls-remote https://github.com/Klipper3d/klipper.git 2>/dev/null | awk -v r="$rev" 'index($1, r) == 1 { print $1; exit }')
[ -n "$full" ] || full=$(gh api "repos/Klipper3d/klipper/commits/$rev" -q .sha) ||
	die "resolving Klipper $rev"
a=src-klipper-mcu-${full:0:12}.tar.gz
if ! have "$a"; then
	curl -fsSL -o "$work/$a" "https://github.com/Klipper3d/klipper/archive/$full.tar.gz" ||
		die "downloading Klipper $full"
	upload "$work/$a"
	rm -f "$work/$a"
fi
printf '%s\t%s\t%s\t%s\n' klipper-mcu-firmware "$(cat klipper/mcu-dicts/FLASHED)" GPL-3.0 \
	"$a (+ klipper/mcu-patches/ and klipper/mcu-configs/ in this repository)" >> "$LIST"

# Fluidd: the image ships its built web files (fluidd.zip)
fv=$(sed -n 's/^FLUIDD_VERSION = //p' buildroot/package/fluidd/fluidd.mk)
a=src-fluidd-source-$fv.tar.gz
if ! have "$a"; then
	curl -fsSL -o "$work/$a" "https://github.com/fluidd-core/fluidd/archive/refs/tags/v$fv.tar.gz" ||
		die "downloading Fluidd $fv"
	upload "$work/$a"
	rm -f "$work/$a"
fi
printf '%s\t%s\t%s\t%s\n' fluidd-source "$fv" GPL-3.0 "$a (the image's fluidd.zip is built from it)" >> "$LIST"

# Buildroot (the build scripts around everything above)
bv=$(git -C buildroot/src describe --tags --exact-match 2>/dev/null) ||
	die "buildroot/src is not on a release tag"
a=src-buildroot-$bv.tar.gz
if ! have "$a"; then
	git -C buildroot/src archive --prefix="buildroot-$bv/" HEAD | gzip -9 > "$work/$a"
	upload "$work/$a"
	rm -f "$work/$a"
fi
printf '%s\t%s\t%s\t%s\n' buildroot "$bv" GPL-2.0 "$a" >> "$LIST"

# --- the licences archive for the release ----------------------------------------
L=$work/kiln-os-$TAG-licenses
mkdir -p "$L"
for o in output:main output-recovery:recovery; do
	li=buildroot/${o%%:*}/legal-info n=${o##*:}
	mkdir -p "$L/$n"
	cp -a "$li/manifest.csv" "$li/licenses" "$li/buildroot.config" \
		"$li/legal-info.sha256" "$L/$n/"
done
{
	echo "Kiln OS $TAG: licences and source code"
	echo
	echo "Licence texts: main/licenses/ (main OS) and recovery/licenses/ (recovery OS)."
	echo "Package list with licences and original download sites: */manifest.csv."
	echo "sha256 of every source file: */legal-info.sha256."
	echo
	echo "Source archives: https://github.com/$GITHUB_REPO/releases/tag/$SRC_TAG"
	echo "Kiln OS's own code and build scripts: https://github.com/$GITHUB_REPO/tree/$TAG"
	echo "(buildroot/README.md: how to build both images)."
	echo
	echo "PACKAGE | VERSION | LICENCE | SOURCE"
	sort -u "$LIST" | awk -F'\t' '{ print $1 " | " $2 " | " $3 " | " $4 }'
} > "$L/README.txt"
"${TARX[@]}" -czf "$DIST/kiln-os-$TAG-licenses.tar.gz" -C "$work" "kiln-os-$TAG-licenses"
echo "publish_sources: $(sort -u "$LIST" | wc -l) packages, $up new source archive(s); $DIST/kiln-os-$TAG-licenses.tar.gz"
