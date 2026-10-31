/* The interface to the recovery OS: every external command and path the UI
 * uses, in one table (commands.c). Each entry can be overridden at run
 * time with an environment variable AD5X_RUI_<NAME> (see commands.c). */
#ifndef RUI_COMMANDS_H
#define RUI_COMMANDS_H

#include <stddef.h>

typedef enum {
	/* Commands: /bin/sh -c strings; {X} placeholders are filled in,
	 * shell-quoted, by cmd_expand() */
	CMD_INSTALL,		/* {FILE}: install a .swu through the daemon */
	CMD_INSTALL_CHECK,	/* {FILE}: verify only */
	CMD_BACKUP,		/* {DRY} {ALL} {DEST} */
	CMD_RESTORE,		/* {DRY} {SRC} {PARTS} */
	CMD_RESTORE_STOCK,	/* {DRY} */
	CMD_BOOT_MAIN,		/* flag -> main OS (slot B) + reboot */
	CMD_REBOOT,
	CMD_POWEROFF,
	CMD_USB_MOUNT,		/* mount all USB sticks */
	CMD_USB_UMOUNT,		/* unmount them all */
	CMD_USB_LIST,		/* one line per mounted stick partition */
	CMD_STATUS,		/* key=value state, quick */
	CMD_STATUS_SLOTS,	/* same, plus slot_a= / slot_b= (slower) */
	CMD_SYSLOG,		/* recent system log on stdout */

	/* Paths */
	PATH_UPDATE_DIR,	/* staged *.swu files */
	PATH_LAST_LOG,		/* result of the last update */
	PATH_SWU_LOG,		/* SWUpdate daemon log */
	PATH_MOUNTS,		/* /proc/mounts */
	PATH_SYS_BLOCK,		/* /sys/class/block */
	PATH_OTA,		/* boot flag: device path, or "" = GPT name "ota" */
	PATH_MAIN_ROOTFS,	/* main OS root (slot B): path or "" = "rootfs2" */
	PATH_SWU_SOCKET,	/* SWUpdate progress socket */
	PATH_BACKUP_PREFIX,	/* backup sets: <stick>/<prefix>* directories */
	PATH_TOUCH_NAME,	/* evdev device name of the touch screen */
	PATH_FBDEV,		/* framebuffer */
	PATH_SETTINGS,		/* main OS settings.json: its "language" key */

	RUI_N_ENTRIES
} rui_entry;

/* The value (built-in default or environment override) */
const char *rui_get(rui_entry e);
const char *rui_name(rui_entry e);

/* Expand a command's placeholders. vars: NULL-terminated list of
 * "NAME", "value" pairs; values are shell-quoted, except for {PARTS}
 * which takes a space-separated list and quotes each word, and {DRY} /
 * {ALL} which are inserted as given (flags or ""). Returns malloc'd. */
char *cmd_expand(rui_entry e, const char *const *vars);

/* Single-quote s for /bin/sh (malloc'd) */
char *sh_quote(const char *s);

#endif
