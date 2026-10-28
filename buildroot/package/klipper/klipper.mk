################################################################################
#
# klipper
#
################################################################################

# Host Klipper. The boards' firmware may be older (klipper/mcu-dicts):
# tools/test_image.sh checks this host against their data dictionaries.
# tools/bump_upstream.py sets both lines (DESCRIBE: git describe of it).
KLIPPER_VERSION = ee2c6fb6b00b2b5d097ef70d0868df7d74943b51
KLIPPER_DESCRIBE = v0.13.0-816-gee2c6fb6b
KLIPPER_SITE = $(call github,Klipper3d,klipper,$(KLIPPER_VERSION))
KLIPPER_LICENSE = GPL-3.0
KLIPPER_LICENSE_FILES = COPYING
KLIPPER_DEPENDENCIES = host-python3 python3 python-cffi python-greenlet \
	python-jinja2 python-markupsafe python-serial

KLIPPER_AD5X = $(BR2_EXTERNAL_AD5X_PATH)/../klipper
KLIPPER_CHELPER = $(@D)/klippy/chelper

# klippy builds chelper with gcc on first start; the printer has no
# compiler, so build it here with the same flags (minus the x86 SSE ones).
define KLIPPER_BUILD_CMDS
	cd $(KLIPPER_CHELPER) && $(TARGET_CC) $(TARGET_CFLAGS) \
		-Wall -O2 -shared -fPIC -flto -fwhole-program \
		-fno-use-linker-plugin -o c_helper.so \
		$$($(HOST_DIR)/bin/python3 -c 'import ast, sys; \
			t = ast.parse(open("__init__.py").read()); \
			print(" ".join(next(ast.literal_eval(n.value) for n in t.body \
				if isinstance(n, ast.Assign) and \
				getattr(n.targets[0], "id", "") == "SOURCE_FILES")))')
endef

define KLIPPER_INSTALL_TARGET_CMDS
	mkdir -p $(TARGET_DIR)/usr/lib/klipper
	rm -rf $(TARGET_DIR)/usr/lib/klipper/klippy
	cp -a $(@D)/klippy $(TARGET_DIR)/usr/lib/klipper/
	echo "$(KLIPPER_DESCRIBE)-ad5x" \
		> $(TARGET_DIR)/usr/lib/klipper/klippy/.version
	$(INSTALL) -m 0644 -t $(TARGET_DIR)/usr/lib/klipper/klippy/extras \
		$(KLIPPER_AD5X)/extras/*.py
	# Moonraker serves these read-only (config_examples, docs roots) and
	# warns when they are missing. Docs without their images (~2 MB).
	rm -rf $(TARGET_DIR)/usr/lib/klipper/config $(TARGET_DIR)/usr/lib/klipper/docs
	cp -a $(@D)/config $(TARGET_DIR)/usr/lib/klipper/
	mkdir -p $(TARGET_DIR)/usr/lib/klipper/docs
	cp -a $(@D)/docs/*.md $(TARGET_DIR)/usr/lib/klipper/docs/
	# Defaults, included read-only by the printer's printer.cfg
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/ad5x.cfg \
		$(TARGET_DIR)/usr/share/ad5x/config/ad5x.cfg
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/ifs.cfg \
		$(TARGET_DIR)/usr/share/ad5x/config/ifs.cfg
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/generic-flashforge-ifs.cfg \
		$(TARGET_DIR)/usr/share/ad5x/config/generic-flashforge-ifs.cfg
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/setup.cfg \
		$(TARGET_DIR)/usr/share/ad5x/config/setup.cfg
	# Shipped plugins (docs/plugins.md), read-only; the printer's
	# plugins.cfg says which are on
	rm -rf $(TARGET_DIR)/usr/share/ad5x/plugins
	mkdir -p $(TARGET_DIR)/usr/share/ad5x/plugins
	cp -r $(KLIPPER_AD5X)/plugins/. $(TARGET_DIR)/usr/share/ad5x/plugins/
	chmod -R u=rwX,go=rX $(TARGET_DIR)/usr/share/ad5x/plugins
	# The speaker's event sounds (ad5x_sound; tools/make_sounds.py)
	rm -rf $(TARGET_DIR)/usr/share/ad5x/sounds
	mkdir -p $(TARGET_DIR)/usr/share/ad5x/sounds
	cp $(KLIPPER_AD5X)/sounds/*.mid $(TARGET_DIR)/usr/share/ad5x/sounds/
	# Plugins in their own repositories this release offers (INSTALL_PLUGIN)
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/plugin-catalog.json \
		$(TARGET_DIR)/usr/share/ad5x/plugin-catalog.json
	# First-boot templates, copied to printer_data/config once
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/printer.cfg \
		$(TARGET_DIR)/usr/share/ad5x/defaults/printer.cfg
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/unit.cfg \
		$(TARGET_DIR)/usr/share/ad5x/defaults/unit.cfg
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/local.cfg \
		$(TARGET_DIR)/usr/share/ad5x/defaults/local.cfg
	$(INSTALL) -D -m 0644 $(KLIPPER_AD5X)/plugins.cfg \
		$(TARGET_DIR)/usr/share/ad5x/defaults/plugins.cfg
	# Templates of the printer's editable macros (macros/*.cfg in the
	# config dir, docs/config-layout.md): ad5x-config-templates (S05)
	# copies them and replaces them when they change
	rm -rf $(TARGET_DIR)/usr/share/ad5x/defaults/macros
	mkdir -p $(TARGET_DIR)/usr/share/ad5x/defaults/macros
	$(INSTALL) -m 0644 -t $(TARGET_DIR)/usr/share/ad5x/defaults/macros \
		$(KLIPPER_AD5X)/macros/*.cfg
endef

$(eval $(generic-package))
