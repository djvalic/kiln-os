# ad5x-recovery-ui: LVGL v9 touch screen UI of the AD5X recovery OS.
#
# Printer (Buildroot does this, package/ad5x-recovery-ui):
#   make BACKEND=fbdev CC=<cross-gcc> LVGL_DIR=<lvgl source> [USE_LIBSWUPDATE=1]
# Laptop:
#   make                 headless build (renders screens to PNG only)
#   make BACKEND=sdl     800x480 SDL2 window, mouse = touch
#   make shots           headless screenshots of every screen with simulated
#                        data (sim/run-sim.sh) into $(SHOTS)
#   make sim             the SDL window with the same simulated data
# LVGL is downloaded once into build/ (pinned version, sha256 checked)
# Strings: i18n/*.txt -> src/i18n_*.{h,c} (python3 i18n/gen_i18n.py). The
# screens' language comes from the main OS's settings.json; the simulator
# takes one with RUI_SIM_LANG=de make sim (sim/run-sim.sh).
# unless LVGL_DIR points at a source tree.

LVGL_VERSION = 9.5.0
LVGL_SHA256 = 34a955cdf3a2d005507b704e87357af669a114523b6d3f77b5344fdc68717bc6
LVGL_URL = https://github.com/lvgl/lvgl/archive/v$(LVGL_VERSION)/lvgl-$(LVGL_VERSION).tar.gz

BACKEND ?= headless
O ?= build/$(BACKEND)
LVGL_DIR ?= build/lvgl-$(LVGL_VERSION)
USE_LIBSWUPDATE ?= 0
SHOTS ?= build/shots
PREFIX ?= /usr
DESTDIR ?=

CC ?= cc
CFLAGS ?= -O2 -g
APP = $(O)/ad5x-recovery-ui

CPPFLAGS += -I. -Isrc -I$(LVGL_DIR) -DLV_CONF_INCLUDE_SIMPLE
LDLIBS += -lpthread -lm

ifeq ($(BACKEND),fbdev)
CPPFLAGS += -DRUI_FBDEV
else ifeq ($(BACKEND),sdl)
CPPFLAGS += -DRUI_SDL $(shell pkg-config --cflags sdl2)
LDLIBS += $(shell pkg-config --libs sdl2)
else ifneq ($(BACKEND),headless)
$(error BACKEND must be fbdev, sdl or headless)
endif

ifeq ($(USE_LIBSWUPDATE),1)
CPPFLAGS += -DUSE_LIBSWUPDATE
LDLIBS += -lswupdate
endif

APP_SRCS = $(wildcard src/*.c) $(wildcard fonts/*.c)
APP_OBJS = $(patsubst %.c,$(O)/app/%.o,$(APP_SRCS))
LVGL_SRCS = $(shell find $(LVGL_DIR)/src -name '*.c' 2>/dev/null)
LVGL_OBJS = $(patsubst $(LVGL_DIR)/%.c,$(O)/lvgl/%.o,$(LVGL_SRCS))

all: $(APP)

# Two passes so the LVGL file list is read after the download
ifeq ($(LVGL_SRCS),)
$(APP): $(LVGL_DIR)/lvgl.h
	$(MAKE) $(APP)
else
$(APP): $(APP_OBJS) $(LVGL_OBJS)
	@echo "  LD $@"
	@$(CC) $(LDFLAGS) -o $@ $^ $(LDLIBS)
endif

$(O)/app/%.o: %.c lv_conf.h | $(LVGL_DIR)/lvgl.h
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -Wall -Wextra -Wno-unused-parameter -Wno-format-truncation -MMD -MP -c -o $@ $<

$(O)/lvgl/%.o: $(LVGL_DIR)/%.c lv_conf.h
	@mkdir -p $(dir $@)
	@echo "  CC lvgl/$*.c"
	@$(CC) $(CPPFLAGS) $(CFLAGS) -w -MMD -MP -c -o $@ $<

$(LVGL_DIR)/lvgl.h:
	@mkdir -p build
	curl -fsSL -o build/lvgl-$(LVGL_VERSION).tar.gz $(LVGL_URL)
	echo "$(LVGL_SHA256)  build/lvgl-$(LVGL_VERSION).tar.gz" | sha256sum -c -
	tar -xzf build/lvgl-$(LVGL_VERSION).tar.gz -C build
	touch $@

shots:
	$(MAKE) BACKEND=headless
	sim/run-sim.sh build/headless/ad5x-recovery-ui --shots $(SHOTS)

sim:
	$(MAKE) BACKEND=sdl
	sim/run-sim.sh build/sdl/ad5x-recovery-ui

install: $(APP)
	install -D -m 0755 $(APP) $(DESTDIR)$(PREFIX)/bin/ad5x-recovery-ui

clean:
	rm -rf $(O)

.PHONY: all shots sim install clean
-include $(shell find $(O) -name '*.d' 2>/dev/null)
