################################################################################
#
# happy-hare
#
################################################################################

HAPPY_HARE_VERSION = v4.1.0
HAPPY_HARE_SITE = $(call github,moggieuk,Happy-Hare,$(HAPPY_HARE_VERSION))
HAPPY_HARE_LICENSE = GPL-3.0
HAPPY_HARE_LICENSE_FILES = LICENSE
HAPPY_HARE_DEPENDENCIES = klipper moonraker

define HAPPY_HARE_INSTALL_TARGET_CMDS
	# Klipper extras (mmu_machine.py, mmu_stepper.py, mmu_servo.py, mmu_led_effect.py, mmu/)
	cp -a $(@D)/extras/mmu* $(TARGET_DIR)/usr/lib/klipper/klippy/extras/
	# Moonraker component
	$(INSTALL) -D -m 0644 $(@D)/components/mmu_server.py \
		$(TARGET_DIR)/usr/lib/moonraker/moonraker/components/mmu_server.py
	# Config templates / defaults
	mkdir -p $(TARGET_DIR)/usr/share/ad5x/happy-hare
	cp -a $(@D)/config $(TARGET_DIR)/usr/share/ad5x/happy-hare/
	# AD5X IFS hardware configuration
	$(INSTALL) -D -m 0644 $(BR2_EXTERNAL_AD5X_PATH)/../klipper/mmu-flashforge-ifs.cfg \
		$(TARGET_DIR)/usr/share/ad5x/config/mmu-flashforge-ifs.cfg
endef

$(eval $(generic-package))

