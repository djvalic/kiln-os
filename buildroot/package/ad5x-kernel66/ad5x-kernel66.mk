################################################################################
#
# ad5x-kernel66: our 6.6 kernel + chainload.ko (kernel-ingenic66/)
#
################################################################################

AD5X_KERNEL66_VERSION = 1
AD5X_KERNEL66_SITE = $(BR2_EXTERNAL_AD5X_PATH)/../kernel-ingenic66
AD5X_KERNEL66_SITE_METHOD = local
AD5X_KERNEL66_LICENSE = GPL-2.0
AD5X_KERNEL66_DEPENDENCIES = host-python3 wireless-regdb

AD5X_KERNEL66_SDK = $(call qstrip,$(BR2_PACKAGE_AD5X_KERNEL66_SDK))
AD5X_KERNEL66_KDIR510 = $(call qstrip,$(BR2_PACKAGE_AD5X_KERNEL66_KDIR510))
AD5X_KERNEL66_OUT = $(@D)/out

# The kernel builds in the SDK's own tree (build.sh copies our files in) into
# $(@D)/out; chainload.ko against the prepared 5.10 tree.
define AD5X_KERNEL66_BUILD_CMDS
	test -d $(AD5X_KERNEL66_SDK)/kernel/kernel-6.6 || \
		{ echo "ad5x-kernel66: no SDK at $(AD5X_KERNEL66_SDK)"; exit 1; }
	test -d $(AD5X_KERNEL66_KDIR510) || \
		{ echo "ad5x-kernel66: no 5.10 tree, run kernel-ingenic66/chainload/setup.sh"; exit 1; }
	cd $(@D) && SDK=$(AD5X_KERNEL66_SDK) OUT=$(AD5X_KERNEL66_OUT) \
		TOOLBIN=$(HOST_DIR)/bin REPO=$(BR2_EXTERNAL_AD5X_PATH)/.. \
		REGDB_DIR=$(BUILD_DIR)/wireless-regdb-$(WIRELESS_REGDB_VERSION) \
		bash ./build.sh
	$(MAKE) -C $(@D)/chainload KDIR=$(AD5X_KERNEL66_KDIR510) \
		CROSS_COMPILE=$(HOST_DIR)/bin/mipsel-linux-
	cat $(AD5X_KERNEL66_OUT)/include/config/kernel.release > $(@D)/release
endef

define AD5X_KERNEL66_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0644 $(AD5X_KERNEL66_OUT)/xImage-ad5x-6.6 \
		$(TARGET_DIR)/usr/lib/ad5x/kernel66/xImage
	$(INSTALL) -D -m 0644 $(@D)/chainload/chainload.ko \
		$(TARGET_DIR)/usr/lib/ad5x/kernel66/chainload.ko
	$(INSTALL) -D -m 0644 $(@D)/release \
		$(TARGET_DIR)/usr/lib/ad5x/kernel66/release
endef

$(eval $(generic-package))
