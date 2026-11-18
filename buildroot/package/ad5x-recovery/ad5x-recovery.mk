################################################################################
#
# ad5x-recovery
#
################################################################################

AD5X_RECOVERY_VERSION = 1
AD5X_RECOVERY_SITE = $(BR2_EXTERNAL_AD5X_PATH)/package/ad5x-recovery
AD5X_RECOVERY_SITE_METHOD = local
AD5X_RECOVERY_LICENSE = GPL-3.0
# Shared with the main OS, installed from its sources unchanged: the stock
# driver loader, the vendor files helper (ad5x-vendor, /usr/bin/cmd_*), Ethernet (stock MAC; DHCP or static from
# /data/ad5x/network.conf), Wi-Fi, the watchdog feeder (on Kiln's 6.6 only),
# and the slot/network helpers.
AD5X_RECOVERY_MAIN = $(BR2_EXTERNAL_AD5X_PATH)/package/ad5x-system
# ad5x-ff-decrypt (Return to Flashforge firmware: a Flashforge AD5X-*.tgz
# from a USB stick) uses mbedTLS's MD5 and DES, which SWUpdate brings
AD5X_RECOVERY_DEPENDENCIES = mbedtls

define AD5X_RECOVERY_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -Wall -O2 -o $(@D)/ad5x-ff-decrypt \
		$(@D)/src/ad5x-ff-decrypt.c $(TARGET_LDFLAGS) -lmbedcrypto
endef

define AD5X_RECOVERY_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/ad5x-ff-decrypt $(TARGET_DIR)/usr/bin/ad5x-ff-decrypt
	$(INSTALL) -D -m 0644 $(@D)/lib/recovery.sh \
		$(TARGET_DIR)/usr/lib/ad5x-recovery/recovery.sh
	$(INSTALL) -D -m 0755 $(@D)/lib/swu-postupdate \
		$(TARGET_DIR)/usr/lib/ad5x-recovery/swu-postupdate
	$(INSTALL) -D -m 0755 $(@D)/swupdate/mk-sw-description.sh \
		$(TARGET_DIR)/usr/lib/ad5x-recovery/mk-sw-description.sh
	$(INSTALL) -D -m 0755 $(@D)/swupdate/ad5x-slot-b.sh \
		$(TARGET_DIR)/usr/lib/ad5x-recovery/ad5x-slot-b.sh
	for f in $(@D)/bin/*; do \
		$(INSTALL) -D -m 0755 $$f $(TARGET_DIR)/usr/bin/$$(basename $$f) \
			|| exit 1; \
	done
	for f in $(@D)/init.d/S*; do \
		$(INSTALL) -D -m 0755 $$f $(TARGET_DIR)/etc/init.d/$$(basename $$f) \
			|| exit 1; \
	done
	# A copy of the stock files on a USB stick (Return to Flashforge
	# firmware's Save files to USB)
	$(INSTALL) -D -m 0755 $(AD5X_RECOVERY_MAIN)/bin/ad5x-stock-copy \
		$(TARGET_DIR)/usr/bin/ad5x-stock-copy
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/slot.sh \
		$(TARGET_DIR)/usr/lib/ad5x/slot.sh
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/network.sh \
		$(TARGET_DIR)/usr/lib/ad5x/network.sh
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/kernel.sh \
		$(TARGET_DIR)/usr/lib/ad5x/kernel.sh
	# Kiln's own boot loader (ad5x-bootloader-install, ad5x-return-stock);
	# memory.sh: the board's RAM for its bl_variant (ad5x.ram=)
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/bootloader.sh \
		$(TARGET_DIR)/usr/lib/ad5x/bootloader.sh
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/memory.sh \
		$(TARGET_DIR)/usr/lib/ad5x/memory.sh
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/watchdog.conf \
		$(TARGET_DIR)/usr/lib/ad5x/watchdog.conf
	$(AD5X_SYSTEM_INSTALL_VENDOR_SUPPORT)
	for s in S05ad5x-watchdog S06ad5x-modules S41ad5x-eth S42ad5x-wifi; do \
		$(INSTALL) -D -m 0755 $(AD5X_RECOVERY_MAIN)/init.d/$$s \
			$(TARGET_DIR)/etc/init.d/$$s || exit 1; \
	done
endef

$(eval $(generic-package))
