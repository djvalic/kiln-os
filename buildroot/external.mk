include $(sort $(wildcard $(BR2_EXTERNAL_AD5X_PATH)/package/*/*.mk))

# NetworkManager and GLib (main image, docs/network.md) built for size, not
# speed: -Os after Buildroot's -O2 (the last -O wins). About 0.3 MB less
# in the 100 MiB slot (measured, squashfs LZO). Included after Buildroot's
# own packages, so this replaces their default (TARGET_CFLAGS).
NETWORK_MANAGER_CFLAGS = $(TARGET_CFLAGS) -Os
LIBGLIB2_CFLAGS = $(TARGET_CFLAGS) -Os
