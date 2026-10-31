################################################################################
#
# helixscreen
#
################################################################################

# HELIXSCREEN_COMMIT: the tag's commit (tools/bump_upstream.py keeps both
# current). Git with submodules: LVGL, libhv, spdlog/fmt, libnl,
# wpa_supplicant's client, Lua, helix-xml etc. are vendored there.
HELIXSCREEN_VERSION = v1.1.0-beta.13
HELIXSCREEN_COMMIT = 1649a473a76cdc37447f40b53351d6dbeceb7fab
HELIXSCREEN_SITE = https://github.com/prestonbrown/helixscreen.git
HELIXSCREEN_SITE_METHOD = git
HELIXSCREEN_GIT_SUBMODULES = YES
HELIXSCREEN_LICENSE = GPL-3.0+
HELIXSCREEN_LICENSE_FILES = LICENSE
HELIXSCREEN_DEPENDENCIES = openssl zlib host-python3 \
	host-autoconf host-automake host-libtool host-pkgconf host-bison host-flex

# Upstream applies its LVGL/libhv/Lua/libnl patches with `git -C <submodule>
# apply`, so those must be git trees (Buildroot's tarball has only dangling
# .git files). The top-level repo stops git from finding this project's
# repo above it.
define HELIXSCREEN_GIT_INIT
	find $(@D) -name .git -type f -delete
	for d in lib/lvgl lib/libhv lib/lua lib/libnl .; do \
		(cd $(@D)/$$d && git init -q && git add -A . && \
		 git -c user.name=buildroot -c user.email=buildroot@localhost \
			commit -q --no-verify -m import) || exit 1; \
	done
endef
HELIXSCREEN_POST_EXTRACT_HOOKS += HELIXSCREEN_GIT_INIT

# Upstream's unified MIPS target (PLATFORM_TARGET=mips, also called ad5x/k1:
# fbdev, evdev, RGB565, IFS + CFS) with Buildroot's glibc toolchain instead
# of its static musl one: dynamic link, our r5 ISA (nan2008/fp64 kept), no
# -static. Packaging build (HELIX_PACKAGING=1): no mock backends, no remote
# control server. Crash/debug uploads to helixscreen.org off by default.
# Bluetooth and systemd stay off (not in the sysroot); no SDL/DRM/EGL.
# The vendored spdlog, not one the build host may have in /usr/include.
# HELIX_KILN_AD5X: this build is the Kiln OS AD5X image only (upstream's
# unified MIPS target also serves the K1); patch 0029 keys the AD5X default on it.
# CROSS_COMPILE is a bare prefix (host/bin is on PATH): libnl's configure
# derives --host from it.
HELIXSCREEN_CFLAGS = -march=mips32r5 -mnan=2008 -mfp64 \
	-D_LARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 \
	-Os -flto=auto -ffunction-sections -fdata-sections \
	-fno-omit-frame-pointer -funwind-tables -fmerge-all-constants -fno-ident \
	-Wno-error=conversion -Wno-error=sign-conversion \
	-DHELIX_RELEASE_BUILD -DHELIX_PLATFORM_MIPS -DHELIX_KILN_AD5X

HELIXSCREEN_MAKE_OPTS = \
	PLATFORM_TARGET=mips \
	CROSS_COMPILE=$(GNU_TARGET_NAME)- \
	TARGET_TRIPLE=$(GNU_TARGET_NAME) \
	TARGET_ARCH=mips32r5 \
	TARGET_CFLAGS="$(HELIXSCREEN_CFLAGS)" \
	TARGET_LDFLAGS="-Wl,--gc-sections -Wl,-O2 -Wl,--as-needed -flto=auto" \
	STRIP_BINARY=no \
	HELIX_PACKAGING=1 \
	ENABLE_DIAGNOSTIC_UPLOADS=no \
	ENABLE_REMOTE_CONTROL=no \
	ENABLE_MOCKS=no \
	ENABLE_SDL=no ENABLE_GLES_3D=no ENABLE_OPENGLES=no \
	HELIX_GIT_HASH=$(shell echo $(HELIXSCREEN_COMMIT) | cut -c1-8) \
	SPDLOG_SYSTEM_HEADER_PATHS= \
	SKIP_OPTIONAL_DEPS=1 \
	NO_COLOR=1

define HELIXSCREEN_BUILD_CMDS
	$(TARGET_MAKE_ENV) PYTHON=$(HOST_DIR)/bin/python3 \
		$(MAKE) -C $(@D) $(HELIXSCREEN_MAKE_OPTS)
endef

HELIXSCREEN_INSTDIR = $(TARGET_DIR)/usr/lib/helixscreen

# The layout of upstream's release package (bin, ui_xml, config, assets),
# under /usr/lib/helixscreen: the XML minified as upstream's release does
# (it stays resident in RAM), font sources, macOS icons and test data left
# out, and printer pictures only for FlashForge and the generic fallback.
# Only helix-screen: S70helixscreen starts it directly (no upstream
# launcher, splash or watchdog). No CA bundle (HTTPS is only for upstream's
# update/report servers).
define HELIXSCREEN_INSTALL_TARGET_CMDS
	rm -rf $(HELIXSCREEN_INSTDIR)
	$(INSTALL) -D -m 0755 $(@D)/build/mips/bin/helix-screen \
		$(HELIXSCREEN_INSTDIR)/bin/helix-screen
	cp -a $(@D)/ui_xml $(@D)/config $(HELIXSCREEN_INSTDIR)/
	find $(HELIXSCREEN_INSTDIR)/ui_xml \( -name '*.c' -o -name '*.h' \) -delete
	rm -f $(HELIXSCREEN_INSTDIR)/ui_xml/glyphs_panel.xml
	cd $(@D) && $(HOST_DIR)/bin/python3 scripts/minify_xml_tree.py \
		$(HELIXSCREEN_INSTDIR)/ui_xml
	rm -f $(addprefix $(HELIXSCREEN_INSTDIR)/config/,*.service *.path *.pkla \
		*.rules *.init *k2* *qidi* ensure-polkit-rule.sh \
		refresh-service-units.sh settings.json settings-test.json \
		helixconfig*.json)
	mkdir -p $(HELIXSCREEN_INSTDIR)/assets
	cp -a $(@D)/assets/config $(@D)/assets/fonts $(@D)/assets/images \
		$(@D)/assets/sounds $(@D)/assets/zoneinfo \
		$(@D)/assets/filaments.json $(HELIXSCREEN_INSTDIR)/assets/
	find $(HELIXSCREEN_INSTDIR)/assets/fonts \( -name '*.c' -o -name '*.ttf' \
		-o -name '*.otf' -o -name '.clang-format' \) -delete
	find $(HELIXSCREEN_INSTDIR)/assets -name '*.icns' -delete
	rm -f "$(HELIXSCREEN_INSTDIR)/assets/images/orcaslicer test cube.PNG"
	find $(HELIXSCREEN_INSTDIR)/assets/images/printers -maxdepth 1 -name '*.png' \
		! -name 'flashforge-*' ! -name 'generic-corexy.png' -delete
	ln -sf ../lib/helixscreen/bin/helix-screen $(TARGET_DIR)/usr/bin/helix-screen
endef

$(eval $(generic-package))
