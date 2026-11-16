################################################################################
#
# ad5x-bootloader
#
################################################################################

# Kiln's SPL and U-Boot proper (u-boot/, docs/own-boot-loader.md): the
# v2026.10 release tarball (the one u-boot/build.sh pins), u-boot/patches
# applied in order, then u-boot/build.sh on that tree (USRC) with
# Buildroot's cross compiler: the same build and the same checks as on the
# laptop (the boot ROM's 24 KiB, the SPL's memory map and stack, U-Boot's
# size). Only spl-mmc.img and u-boot-emmc.img go into the image (the
# recovery OS: /usr/share/ad5x/bootloader, ~370 KB), for the opt-in
# ad5x-bootloader-install; nothing installs them by itself. The whole dist
# goes to images/bootloader as well.
AD5X_BOOTLOADER_VERSION = 2026.10
AD5X_BOOTLOADER_SITE = $(call github,u-boot,u-boot,v$(AD5X_BOOTLOADER_VERSION))
AD5X_BOOTLOADER_LICENSE = GPL-2.0+
AD5X_BOOTLOADER_LICENSE_FILES = Licenses/gpl-2.0.txt
AD5X_BOOTLOADER_UBOOT = $(BR2_EXTERNAL_AD5X_PATH)/../u-boot
# U-Boot's own build: host tools need bison, flex and OpenSSL's headers
# (the builder image has them, tools/builder/Dockerfile)
AD5X_BOOTLOADER_DEPENDENCIES = host-bison host-flex

# The SPL's banner carries the build date: the last commit to u-boot/, as
# a laptop build of the same tree (u-boot/build.sh) has it, not Buildroot's
# SOURCE_DATE_EPOCH. Without git, build.sh's own fallback.
AD5X_BOOTLOADER_EPOCH := $(shell git -C $(AD5X_BOOTLOADER_UBOOT) log -1 --format=%ct -- . 2>/dev/null)

define AD5X_BOOTLOADER_APPLY_KILN_PATCHES
	for p in $(AD5X_BOOTLOADER_UBOOT)/patches/*.patch; do \
		patch -d $(@D) -p1 --quiet < $$p || exit 1; \
	done
endef
AD5X_BOOTLOADER_POST_PATCH_HOOKS += AD5X_BOOTLOADER_APPLY_KILN_PATCHES

# Buildroot's make variables (O=, BR2_EXTERNAL=, -j) must not reach
# U-Boot's make through MAKEFLAGS
define AD5X_BOOTLOADER_BUILD_CMDS
	cd $(@D) && env -u MAKEFLAGS -u MFLAGS -u MAKELEVEL -u O \
		$(if $(AD5X_BOOTLOADER_EPOCH),SOURCE_DATE_EPOCH=$(AD5X_BOOTLOADER_EPOCH),-u SOURCE_DATE_EPOCH) \
		USRC=$(@D) WORK=$(@D)/kiln-work O=$(@D)/kiln-out \
		TOOLBIN=$(HOST_DIR)/bin JOBS=$(PARALLEL_JOBS) \
		bash $(AD5X_BOOTLOADER_UBOOT)/build.sh
	cd $(@D)/kiln-out/dist && \
		sha256sum spl-mmc.img u-boot-emmc.img > $(@D)/kiln-out/SHA256SUMS
endef

define AD5X_BOOTLOADER_INSTALL_TARGET_CMDS
	for f in spl-mmc.img u-boot-emmc.img report.txt; do \
		$(INSTALL) -D -m 0644 $(@D)/kiln-out/dist/$$f \
			$(TARGET_DIR)/usr/share/ad5x/bootloader/$$f || exit 1; \
	done
	$(INSTALL) -D -m 0644 $(@D)/kiln-out/SHA256SUMS \
		$(TARGET_DIR)/usr/share/ad5x/bootloader/SHA256SUMS
	rm -rf $(BINARIES_DIR)/bootloader
	mkdir -p $(BINARIES_DIR)/bootloader
	cp $(@D)/kiln-out/dist/* $(BINARIES_DIR)/bootloader/
endef

$(eval $(generic-package))
