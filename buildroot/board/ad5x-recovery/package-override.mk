# Buildroot packages the recovery OS takes at a newer version than
# Buildroot 2026.02.3 has (BR2_PACKAGE_OVERRIDE_FILE in
# ad5x_recovery_defconfig; docs/builder.md, Pins). Buildroot reads this
# file before its own package/*/*.mk; "override" keeps their version line
# from replacing ours. The sha256 of each download is in
# patches/NAME/VERSION/NAME.hash (BR2_GLOBAL_PATCH_DIR: Buildroot takes a
# hash from any of the package's hash files). Drop an entry, and its
# patches/NAME/VERSION, once Buildroot's own package has that version.

# mbedTLS 3.6.7 (LTS, 2026-07-07: security fixes) for SWUpdate and
# ad5x-ff-decrypt, as in Buildroot 2026.08.1
override MBEDTLS_VERSION = 3.6.7
override MBEDTLS_CPE_ID_VENDOR = trustedfirmware

# Buildroot's default override file, for a developer's <pkg>_OVERRIDE_SRCDIR
-include $(CONFIG_DIR)/local.mk
