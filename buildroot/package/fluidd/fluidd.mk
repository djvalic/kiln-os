################################################################################
#
# fluidd
#
################################################################################

FLUIDD_VERSION = 1.38.0
FLUIDD_SITE = https://github.com/fluidd-core/fluidd/releases/download/v$(FLUIDD_VERSION)
FLUIDD_SOURCE = fluidd.zip
FLUIDD_LICENSE = GPL-3.0

define FLUIDD_EXTRACT_CMDS
	$(UNZIP) $(FLUIDD_DL_DIR)/$(FLUIDD_SOURCE) -d $(@D)/dist
endef

# Prebuilt static files. Text files also go in gzipped (nginx gzip_static):
# the printer's CPU doesn't compress them at every page load.
define FLUIDD_INSTALL_TARGET_CMDS
	rm -rf $(TARGET_DIR)/usr/share/fluidd
	mkdir -p $(TARGET_DIR)/usr/share
	cp -r $(@D)/dist $(TARGET_DIR)/usr/share/fluidd
	find $(TARGET_DIR)/usr/share/fluidd -type f \( -name '*.js' \
		-o -name '*.css' -o -name '*.svg' -o -name '*.json' \
		-o -name '*.html' -o -name '*.webmanifest' \) \
		-exec gzip -9 -n -k -f {} +
	chmod -R u=rwX,go=rX $(TARGET_DIR)/usr/share/fluidd
endef

$(eval $(generic-package))
