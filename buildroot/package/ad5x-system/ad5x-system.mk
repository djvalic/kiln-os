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
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_TOOLS)/flash_iap.py \
		$(TARGET_DIR)/usr/bin/ad5x-flash-iap
	ln -sf ad5x-flash-iap $(TARGET_DIR)/usr/bin/ad5x-flash-ifs
	ln -sf ad5x-flash-iap $(TARGET_DIR)/usr/bin/ad5x-flash-eboard
	$(INSTALL) -D -m 0755 $(AD5X_SYSTEM_TOOLS)/flash_n32.py \
		$(TARGET_DIR)/usr/bin/ad5x-flash-n32
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-mcu $(TARGET_DIR)/usr/bin/ad5x-mcu
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-fb-show $(TARGET_DIR)/usr/bin/ad5x-fb-show
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-fb-progress $(TARGET_DIR)/usr/bin/ad5x-fb-progress
	$(AD5X_SYSTEM_INSTALL_MCU_FIRMWARE)
	$(INSTALL) -D -m 0644 $(@D)/lib/network.sh \
		$(TARGET_DIR)/usr/lib/ad5x/network.sh
	# NetworkManager's connections from network.conf and
	# wpa_supplicant.conf, and back (S40ad5x-network, docs/network.md);
	# main image only, ad5x-recovery.mk doesn't install them
	$(INSTALL) -D -m 0644 $(@D)/lib/ad5x_network.py \
		$(TARGET_DIR)/usr/lib/ad5x/ad5x_network.py
	$(INSTALL) -D -m 0755 $(@D)/lib/network-event \
		$(TARGET_DIR)/usr/lib/ad5x/network-event
	$(INSTALL) -D -m 0644 $(@D)/lib/slot.sh \
		$(TARGET_DIR)/usr/lib/ad5x/slot.sh
	$(INSTALL) -D -m 0644 $(@D)/lib/kernel.sh \
		$(TARGET_DIR)/usr/lib/ad5x/kernel.sh
	$(INSTALL) -D -m 0644 $(@D)/lib/apps.sh \
		$(TARGET_DIR)/usr/lib/ad5x/apps.sh
	# The board's RAM and the memory mode (S00ad5x-kernel, S04ad5x-memory,
	# ad5x-memory; bootloader.sh's bl_variant): also in the recovery OS
	$(INSTALL) -D -m 0644 $(@D)/lib/memory.sh \
		$(TARGET_DIR)/usr/lib/ad5x/memory.sh
	# Kiln's U-Boot's state and records in ota (S99ad5x-booted,
	# ad5x-kernel); main image only, ad5x-recovery.mk doesn't install it
	$(INSTALL) -D -m 0644 $(@D)/lib/uboot.sh \
		$(TARGET_DIR)/usr/lib/ad5x/uboot.sh
	# Kiln's own boot loader in the first MiB: layout, fingerprint, writes,
	# its install record (S99ad5x-booted notes a start by it); also in
	# the recovery OS (ad5x-bootloader-install, ad5x-return-stock)
	$(INSTALL) -D -m 0644 $(@D)/lib/bootloader.sh \
		$(TARGET_DIR)/usr/lib/ad5x/bootloader.sh
	# The watchdog feeder's settings (S05ad5x-watchdog); in rootfs2 it also
	# tells Kiln's U-Boot that this system feeds the watchdog
	$(INSTALL) -D -m 0644 $(@D)/lib/watchdog.conf \
		$(TARGET_DIR)/usr/lib/ad5x/watchdog.conf
	# The plugins' root scripts (S68ad5x-update-agent, S69ad5x-plugin-boot);
	# main image only, ad5x-recovery.mk doesn't install it
	$(INSTALL) -D -m 0644 $(@D)/lib/plugin-root.sh \
		$(TARGET_DIR)/usr/lib/ad5x/plugin-root.sh
	$(INSTALL) -D -m 0644 $(@D)/lib/logs.sh \
		$(TARGET_DIR)/usr/lib/ad5x/logs.sh
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-moonraker-migrate \
		$(TARGET_DIR)/usr/bin/ad5x-moonraker-migrate
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-touch-units \
		$(TARGET_DIR)/usr/bin/ad5x-touch-units
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-kernel \
		$(TARGET_DIR)/usr/bin/ad5x-kernel
	# Extended memory on 512 MiB boards (root's; S68ad5x-update-agent)
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-memory \
		$(TARGET_DIR)/usr/sbin/ad5x-memory
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-sound \
		$(TARGET_DIR)/usr/bin/ad5x-sound
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-update \
		$(TARGET_DIR)/usr/bin/ad5x-update
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-boot-recovery \
		$(TARGET_DIR)/usr/bin/ad5x-boot-recovery
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-restore-stock \
		$(TARGET_DIR)/usr/bin/ad5x-restore-stock
	# the stock files' copy on usershare (S99ad5x-stock-copy); the recovery
	# image installs it too (Save files to USB)
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-stock-copy \
		$(TARGET_DIR)/usr/bin/ad5x-stock-copy
	$(INSTALL) -D -m 0755 $(@D)/ad5x-fbstream \
		$(TARGET_DIR)/usr/bin/ad5x-fbstream
	$(INSTALL) -D -m 0755 $(@D)/bin/ad5x-umask \
		$(TARGET_DIR)/usr/bin/ad5x-umask
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
# it when a board runs anything else. Plus its screens (and progress/, the
# pieces ad5x-fb-progress draws over mcu-updating.jpg). The IFS (filament
# unit) has its own version (klipper/mcu-dicts/FLASHED_IFS), so a new IFS
# build does not reflash the mainboard or eboard.
AD5X_SYSTEM_MCU_VERSION = $(strip $(shell cat $(BR2_EXTERNAL_AD5X_PATH)/../klipper/mcu-dicts/FLASHED))
AD5X_SYSTEM_MCU_DIR = $(BR2_EXTERNAL_AD5X_PATH)/../klipper/mcu-firmware/$(AD5X_SYSTEM_MCU_VERSION)
AD5X_SYSTEM_IFS_VERSION = $(strip $(shell cat $(BR2_EXTERNAL_AD5X_PATH)/../klipper/mcu-dicts/FLASHED_IFS))
AD5X_SYSTEM_IFS_DIR = $(BR2_EXTERNAL_AD5X_PATH)/../klipper/mcu-firmware/$(AD5X_SYSTEM_IFS_VERSION)
define AD5X_SYSTEM_INSTALL_MCU_FIRMWARE
	cd $(AD5X_SYSTEM_MCU_DIR) && sha256sum -c --quiet SHA256SUMS
	cd $(AD5X_SYSTEM_IFS_DIR) && sha256sum -c --quiet SHA256SUMS
	mkdir -p $(TARGET_DIR)/usr/share/ad5x/mcu
	cp $(AD5X_SYSTEM_MCU_DIR)/mainboard.bin $(AD5X_SYSTEM_MCU_DIR)/eboard.hex \
		$(AD5X_SYSTEM_MCU_DIR)/SHA256SUMS $(TARGET_DIR)/usr/share/ad5x/mcu/
	cp $(AD5X_SYSTEM_IFS_DIR)/ifs.hex $(TARGET_DIR)/usr/share/ad5x/mcu/
	cp $(AD5X_SYSTEM_IFS_DIR)/SHA256SUMS $(TARGET_DIR)/usr/share/ad5x/mcu/SHA256SUMS.ifs
	echo $(AD5X_SYSTEM_MCU_VERSION) > $(TARGET_DIR)/usr/share/ad5x/mcu/VERSION
	echo $(AD5X_SYSTEM_IFS_VERSION) > $(TARGET_DIR)/usr/share/ad5x/mcu/IFS_VERSION
	python3 $(AD5X_SYSTEM_TOOLS)/make_install_screens.py --boards \
		$(TARGET_DIR)/usr/share/ad5x/screens >/dev/null
endef

$(eval $(generic-package))
