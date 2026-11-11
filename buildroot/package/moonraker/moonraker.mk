################################################################################
#
# moonraker
#
################################################################################

# tools/bump_upstream.py sets both lines (DESCRIBE: git describe of it)
MOONRAKER_VERSION = b559b9a81161f958a43c2f527b6ad96f73310d5d
MOONRAKER_DESCRIBE = v0.11.0-4-gb559b9a81
MOONRAKER_SITE = $(call github,Arksine,moonraker,$(MOONRAKER_VERSION))
MOONRAKER_LICENSE = GPL-3.0
MOONRAKER_LICENSE_FILES = LICENSE
MOONRAKER_DEPENDENCIES = python3 python-tornado python-pillow python-distro \
	python-jinja2 python-serial python-dbus-fast python-inotify-simple \
	python-libnacl python-streaming-form-data

# Pure Python, run from its source tree (as on a Klipper host). The
# metadata extractor is started as a script, so the .py files stay.
define MOONRAKER_INSTALL_TARGET_CMDS
	rm -rf $(TARGET_DIR)/usr/lib/moonraker
	mkdir -p $(TARGET_DIR)/usr/lib/moonraker
	cp -a $(@D)/moonraker $(TARGET_DIR)/usr/lib/moonraker/
	echo "$(MOONRAKER_DESCRIBE)-ad5x" > $(TARGET_DIR)/usr/lib/moonraker/moonraker/.version
	$(INSTALL) -D -m 0644 $(BR2_EXTERNAL_AD5X_PATH)/../moonraker/moonraker.conf \
		$(TARGET_DIR)/usr/share/ad5x/defaults/moonraker.conf
	$(INSTALL) -D -m 0644 $(BR2_EXTERNAL_AD5X_PATH)/../moonraker/moonraker-updates.conf \
		$(TARGET_DIR)/usr/share/ad5x/moonraker-updates.conf
	# Kiln OS entry in the update manager (docs/updates.md)
	$(INSTALL) -D -m 0644 $(BR2_EXTERNAL_AD5X_PATH)/../moonraker/components/kiln_os.py \
		$(TARGET_DIR)/usr/lib/moonraker/moonraker/components/kiln_os.py
	# IFS slots for slicers (lane_data, OrcaSlicer's filament sync)
	$(INSTALL) -D -m 0644 $(BR2_EXTERNAL_AD5X_PATH)/../moonraker/components/kiln_lanes.py \
		$(TARGET_DIR)/usr/lib/moonraker/moonraker/components/kiln_lanes.py
	# IFS firmware switch status for the touch screen
	$(INSTALL) -D -m 0644 $(BR2_EXTERNAL_AD5X_PATH)/../moonraker/components/kiln_ifs_firmware.py \
		$(TARGET_DIR)/usr/lib/moonraker/moonraker/components/kiln_ifs_firmware.py
endef

$(eval $(generic-package))
