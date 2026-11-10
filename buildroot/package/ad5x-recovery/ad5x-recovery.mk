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
# driver loader, the vendor files helper (ad5x-vendor, /usr/bin/cmd_*), the
# network (NetworkManager's files on /data and the one-time import of the
# older configuration, S44; the Wi-Fi log and off-switch check, S46), and
# the slot helpers.
AD5X_RECOVERY_MAIN = $(BR2_EXTERNAL_AD5X_PATH)/package/ad5x-system

define AD5X_RECOVERY_INSTALL_TARGET_CMDS
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
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/slot.sh \
		$(TARGET_DIR)/usr/lib/ad5x/slot.sh
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/nm-import.sh \
		$(TARGET_DIR)/usr/lib/ad5x/nm-import.sh
	$(INSTALL) -D -m 0644 $(AD5X_RECOVERY_MAIN)/lib/kernel.sh \
		$(TARGET_DIR)/usr/lib/ad5x/kernel.sh
	$(AD5X_SYSTEM_INSTALL_VENDOR_SUPPORT)
	for s in S06ad5x-modules S44ad5x-network S46ad5x-wifi; do \
		$(INSTALL) -D -m 0755 $(AD5X_RECOVERY_MAIN)/init.d/$$s \
			$(TARGET_DIR)/etc/init.d/$$s || exit 1; \
	done
endef

$(eval $(generic-package))
