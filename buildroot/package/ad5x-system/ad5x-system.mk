################################################################################
#
# ad5x-system
#
################################################################################

AD5X_SYSTEM_VERSION = 1
AD5X_SYSTEM_SITE = $(BR2_EXTERNAL_AD5X_PATH)/package/ad5x-system
AD5X_SYSTEM_SITE_METHOD = local
AD5X_SYSTEM_LICENSE = GPL-3.0
AD5X_SYSTEM_TOOLS = $(BR2_EXTERNAL_AD5X_PATH)/../tools
AD5X_SYSTEM_DEPENDENCIES = jpeg

# The touch screen in the browser (S65ad5x-screen, nginx /screen/)
define AD5X_SYSTEM_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -Wall -O2 -o $(@D)/ad5x-fbstream \
		$(@D)/src/ad5x-fbstream.c $(TARGET_LDFLAGS) -ljpeg -lpthread
endef

define AD5X_SYSTEM_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_TOOLS)/boot_eboard.py \
		$(TARGET_DIR)/usr/bin/boot_eboard
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_TOOLS)/ad5x_unit_cfg.py \
		$(TARGET_DIR)/usr/bin/ad5x-unit-cfg
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_TOOLS)/mcu_version.py \
		$(TARGET_DIR)/usr/bin/ad5x-mcu-version
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-mcu $(TARGET_DIR)/usr/bin/ad5x-mcu
	$(AD5X_SYSTEM_INSTALL_MCU_FIRMWARE)
	$(INSTALL) -D -m 0644 $(@D)/lib/network.sh \
		$(TARGET_DIR)/usr/lib/ad5x/network.sh
	$(INSTALL) -D -m 0644 $(@D)/lib/slot.sh \
		$(TARGET_DIR)/usr/lib/ad5x/slot.sh
	$(INSTALL) -D -m 0644 $(@D)/lib/kernel.sh \
		$(TARGET_DIR)/usr/lib/ad5x/kernel.sh
	$(INSTALL) -D -m 0644 $(@D)/lib/apps.sh \
		$(TARGET_DIR)/usr/lib/ad5x/apps.sh
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-touch-units \
		$(TARGET_DIR)/usr/bin/ad5x-touch-units
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-kernel \
		$(TARGET_DIR)/usr/bin/ad5x-kernel
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-sound \
		$(TARGET_DIR)/usr/bin/ad5x-sound
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-update \
		$(TARGET_DIR)/usr/bin/ad5x-update
	$(INSTALL) -D -m 0755 $(@D)/ad5x-fbstream \
		$(TARGET_DIR)/usr/bin/ad5x-fbstream
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-bootlog \
		$(TARGET_DIR)/usr/bin/ad5x-bootlog
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-config-templates \
		$(TARGET_DIR)/usr/bin/ad5x-config-templates
	$(AD5X_SYSTEM_INSTALL_VENDOR_SUPPORT)
	for f in $(@D)/init.d/S*; do \
		$(INSTALL) -D -m 0755 $$f $(TARGET_DIR)/etc/init.d/$$(basename $$f) \
			|| exit 1; \
	done
endef

# Vendor files (Flashforge/Ingenic drivers and board tools) come from the
# printer itself, /data/ad5x/vendor (ad5x-vendor); /usr/bin/cmd_* are our
# wrappers; ad5x-clock (last known time). Shared with the recovery image
# (ad5x-recovery.mk).
define AD5X_SYSTEM_INSTALL_VENDOR_SUPPORT
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_PKGDIR)/bin/ad5x-vendor \
		$(TARGET_DIR)/usr/bin/ad5x-vendor
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_PKGDIR)/bin/ad5x-clock \
		$(TARGET_DIR)/usr/bin/ad5x-clock
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_PKGDIR)/lib/vendor-tool \
		$(TARGET_DIR)/usr/lib/ad5x/vendor-tool
	for t in cmd_gpio cmd_fb cmd_jpeg_display; do \
		ln -sf ../lib/ad5x/vendor-tool $(TARGET_DIR)/usr/bin/$$t || exit 1; \
	done
endef
AD5X_SYSTEM_PKGDIR = $(BR2_EXTERNAL_AD5X_PATH)/package/ad5x-system

# The boards' Klipper firmware this image is tested against
# (klipper/mcu-dicts/FLASHED, built by tools/build_mcu.sh); ad5x-mcu flashes
# it when a board runs anything else. Plus its screens.
AD5X_SYSTEM_MCU_VERSION = $(strip $(shell cat $(BR2_EXTERNAL_AD5X_PATH)/../klipper/mcu-dicts/FLASHED))
AD5X_SYSTEM_MCU_DIR = $(BR2_EXTERNAL_AD5X_PATH)/../klipper/mcu-firmware/$(AD5X_SYSTEM_MCU_VERSION)
define AD5X_SYSTEM_INSTALL_MCU_FIRMWARE
	cd $(AD5X_SYSTEM_MCU_DIR) && sha256sum -c --quiet SHA256SUMS
	mkdir -p $(TARGET_DIR)/usr/share/ad5x/mcu
	cp $(AD5X_SYSTEM_MCU_DIR)/mainboard.bin $(AD5X_SYSTEM_MCU_DIR)/eboard.hex \
		$(AD5X_SYSTEM_MCU_DIR)/ifs.hex $(AD5X_SYSTEM_MCU_DIR)/SHA256SUMS $(TARGET_DIR)/usr/share/ad5x/mcu/
	echo $(AD5X_SYSTEM_MCU_VERSION) > $(TARGET_DIR)/usr/share/ad5x/mcu/VERSION
	python3 $(AD5X_SYSTEM_TOOLS)/make_install_screens.py --boards \
		$(TARGET_DIR)/usr/share/ad5x/screens >/dev/null
endef

$(eval $(generic-package))
