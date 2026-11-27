################################################################################
#
# mainsail
#
################################################################################

MAINSAIL_VERSION = 2.19.0
MAINSAIL_SITE = https://github.com/mainsail-crew/mainsail/releases/download/v$(MAINSAIL_VERSION)
MAINSAIL_SOURCE = mainsail.zip
MAINSAIL_LICENSE = GPL-3.0

define MAINSAIL_EXTRACT_CMDS
	$(UNZIP) $(MAINSAIL_DL_DIR)/$(MAINSAIL_SOURCE) -d $(@D)/dist
endef

# Prebuilt static files, trimmed as Fluidd's (fluidd.mk,
# board/ad5x/web-trim.py): assets/ gzipped only, the rest plain with a
# .gz copy; about 3.1 MiB in the image (squashfs, LZO), less than the
# plain files alone (3.3 MiB; with .gz copies beside them 5.8 MiB).
# Served only after the owner picks Mainsail: then ad5x-webui copies this
# into /data/ad5x/web/mainsail, which Moonraker's update manager updates
# (lib/webui.sh).
define MAINSAIL_INSTALL_TARGET_CMDS
	rm -rf $(TARGET_DIR)/usr/share/mainsail
	mkdir -p $(TARGET_DIR)/usr/share
	cp -r $(@D)/dist $(TARGET_DIR)/usr/share/mainsail
	python3 -I $(BR2_EXTERNAL_AD5X_PATH)/board/ad5x/web-trim.py \
		$(TARGET_DIR)/usr/share/mainsail
	chmod -R u=rwX,go=rX $(TARGET_DIR)/usr/share/mainsail
endef

$(eval $(generic-package))
