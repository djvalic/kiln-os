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

# Prebuilt static files, trimmed for the image (board/ad5x/web-trim.py):
# a .woff is dropped where its .woff2 is there; the text files in assets/
# are there gzipped only (nginx: gzip_static always, gunzip on), the
# others plain with a gzipped copy (gzip_static on): the printer's CPU
# doesn't compress them at every page load. About 4 MiB less in the image
# than plain files with .gz copies beside them (squashfs, LZO).
define FLUIDD_INSTALL_TARGET_CMDS
	rm -rf $(TARGET_DIR)/usr/share/fluidd
	mkdir -p $(TARGET_DIR)/usr/share
	cp -r $(@D)/dist $(TARGET_DIR)/usr/share/fluidd
	python3 -I $(BR2_EXTERNAL_AD5X_PATH)/board/ad5x/web-trim.py \
		$(TARGET_DIR)/usr/share/fluidd
	chmod -R u=rwX,go=rX $(TARGET_DIR)/usr/share/fluidd
endef

$(eval $(generic-package))
