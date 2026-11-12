################################################################################
#
# ad5x-kernel-mainline: mainline Linux 7.3.3 with the AD5X series
# (kernel-mainline/), opt-in beside 6.6 (S00ad5x-kernel, ad5x-kernel)
#
################################################################################

AD5X_KERNEL_MAINLINE_VERSION = 1
AD5X_KERNEL_MAINLINE_SITE = $(BR2_EXTERNAL_AD5X_PATH)/../kernel-mainline
AD5X_KERNEL_MAINLINE_SITE_METHOD = local
AD5X_KERNEL_MAINLINE_LICENSE = GPL-2.0
AD5X_KERNEL_MAINLINE_DEPENDENCIES = host-python3 wireless-regdb

# The kernel tarball (sha256-pinned in build.sh) and its unpacked tree are
# kept in the download directory, so a rebuild doesn't fetch it again;
# the build output goes to $(@D)/out.
AD5X_KERNEL_MAINLINE_WORK = $(BR2_DL_DIR)/ad5x-kernel-mainline

define AD5X_KERNEL_MAINLINE_BUILD_CMDS
	cd $(@D) && WORK=$(AD5X_KERNEL_MAINLINE_WORK) O=$(@D)/out \
		TOOLBIN=$(HOST_DIR)/bin JOBS=$(PARALLEL_JOBS) \
		REGDB_DIR=$(BUILD_DIR)/wireless-regdb-$(WIRELESS_REGDB_VERSION) \
		bash ./build.sh
endef

# chainload.ko comes from ad5x-kernel66 (/usr/lib/ad5x/kernel66): it loads
# any image
define AD5X_KERNEL_MAINLINE_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0644 $(@D)/out/xImage-ad5x-mainline \
		$(TARGET_DIR)/usr/lib/ad5x/kernel-mainline/xImage
	$(INSTALL) -D -m 0644 $(@D)/out/release \
		$(TARGET_DIR)/usr/lib/ad5x/kernel-mainline/release
endef

$(eval $(generic-package))
