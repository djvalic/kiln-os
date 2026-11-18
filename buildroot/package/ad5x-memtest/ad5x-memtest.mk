################################################################################
#
# ad5x-memtest
#
################################################################################

# Extended memory mode's high-bank test (S05ad5x-memtest, docs/memory.md).
# Static: it runs early in the boot and needs no shared library pages
# while it holds most of the free memory. Main OS only (ad5x_defconfig);
# tools/test_ad5x_memtest.sh builds the same source for the laptop.
AD5X_MEMTEST_VERSION = 1
AD5X_MEMTEST_SITE = $(BR2_EXTERNAL_AD5X_PATH)/package/ad5x-memtest
AD5X_MEMTEST_SITE_METHOD = local
AD5X_MEMTEST_LICENSE = GPL-3.0

define AD5X_MEMTEST_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -Wall -Wextra -O2 -static \
		-o $(@D)/ad5x-memtest-high $(@D)/src/ad5x-memtest-high.c \
		$(TARGET_LDFLAGS)
endef

define AD5X_MEMTEST_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/ad5x-memtest-high \
		$(TARGET_DIR)/usr/sbin/ad5x-memtest-high
	$(INSTALL) -D -m 0755 $(@D)/S05ad5x-memtest \
		$(TARGET_DIR)/etc/init.d/S05ad5x-memtest
endef

$(eval $(generic-package))
