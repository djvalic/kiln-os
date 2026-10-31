/* THE TABLE: how ad5x-recovery-ui talks to the recovery OS.
 *
 * Edit the defaults here when the recovery OS tools change (they are
 * documented in docs/recovery-os.md). Every entry can also be overridden
 * without rebuilding: AD5X_RUI_<NAME>=value in the environment, e.g.
 *   AD5X_RUI_CMD_BACKUP='ad5x-backup --verbose {DRY} {ALL} {DEST}'
 * (that is how the laptop simulation, sim/run-sim.sh, points it at fakes).
 *
 * Commands run through /bin/sh -c in a background process; stdout and
 * stderr go to the log view. Exit status 0 = success; the last output line
 * is shown as the result. Progress for the bar is taken from the output: a
 * line "@progress <0-100> [text]" (or "@step <text>"), else the last "NN%"
 * on a line; installs take theirs from SWUpdate's progress socket.
 */
#include "commands.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const struct {
	const char *name;
	const char *def;
} table[RUI_N_ENTRIES] = {
	/* Recovery OS tools, docs/recovery-os.md "CLI tools" */
	[CMD_INSTALL]       = { "CMD_INSTALL",       "ad5x-swu-apply {FILE}" },
	[CMD_INSTALL_CHECK] = { "CMD_INSTALL_CHECK", "ad5x-swu-apply --check {FILE}" },
	[CMD_BACKUP]        = { "CMD_BACKUP",        "ad5x-backup {DRY} {ALL} {DEST}" },
	[CMD_RESTORE]       = { "CMD_RESTORE",       "ad5x-restore {DRY} {SRC} {PARTS}" },
	[CMD_RESTORE_STOCK] = { "CMD_RESTORE_STOCK", "ad5x-restore-stock {DRY}" },
	[CMD_BOOT_MAIN]     = { "CMD_BOOT_MAIN",     "ad5x-boot-main" },
	[CMD_REBOOT]        = { "CMD_REBOOT",        "sync; reboot" },
	[CMD_POWEROFF]      = { "CMD_POWEROFF",      "sync; poweroff" },
	[CMD_USB_MOUNT]     = { "CMD_USB_MOUNT",     "ad5x-usb mount 0" },
	[CMD_USB_UMOUNT]    = { "CMD_USB_UMOUNT",    "ad5x-usb umount" },
	[CMD_USB_LIST]      = { "CMD_USB_LIST",      "ad5x-usb list" },
	[CMD_STATUS]        = { "CMD_STATUS",        "ad5x-status" },
	[CMD_STATUS_SLOTS]  = { "CMD_STATUS_SLOTS",  "ad5x-status --slots" },
	[CMD_SYSLOG]        = { "CMD_SYSLOG",
		"(logread 2>/dev/null || cat /var/log/messages 2>/dev/null) | tail -n 300" },

	[PATH_UPDATE_DIR]   = { "PATH_UPDATE_DIR",   "/data/ad5x/update" },
	[PATH_LAST_LOG]     = { "PATH_LAST_LOG",     "/data/ad5x/update/last.log" },
	[PATH_SWU_LOG]      = { "PATH_SWU_LOG",      "/run/ad5x/swupdate.log" },
	[PATH_MOUNTS]       = { "PATH_MOUNTS",       "/proc/mounts" },
	[PATH_SYS_BLOCK]    = { "PATH_SYS_BLOCK",    "/sys/class/block" },
	[PATH_OTA]          = { "PATH_OTA",          "" },
	[PATH_MAIN_ROOTFS]  = { "PATH_MAIN_ROOTFS",  "" },
	[PATH_SWU_SOCKET]   = { "PATH_SWU_SOCKET",   "/tmp/swupdateprog" },
	[PATH_BACKUP_PREFIX] = { "PATH_BACKUP_PREFIX", "ad5x-backup-" },
	[PATH_TOUCH_NAME]   = { "PATH_TOUCH_NAME",   "TSC2007 Touchscreen" },
	[PATH_FBDEV]        = { "PATH_FBDEV",        "/dev/fb0" },
	[PATH_SETTINGS]     = { "PATH_SETTINGS",     "/data/ad5x/helixscreen/config/settings.json" },
};

const char *rui_name(rui_entry e)
{
	return table[e].name;
}

const char *rui_get(rui_entry e)
{
	char env[64];
	snprintf(env, sizeof(env), "AD5X_RUI_%s", table[e].name);
	const char *v = getenv(env);
	return v ? v : table[e].def;
}

char *sh_quote(const char *s)
{
	size_t n = 3;
	for (const char *p = s; *p; p++)
		n += *p == '\'' ? 4 : 1;
	char *out = malloc(n), *o = out;
	*o++ = '\'';
	for (const char *p = s; *p; p++) {
		if (*p == '\'') {
			memcpy(o, "'\\''", 4);
			o += 4;
		} else {
			*o++ = *p;
		}
	}
	*o++ = '\'';
	*o = 0;
	return out;
}

/* Growing string */
struct sb { char *s; size_t len, cap; };

static void sb_add(struct sb *b, const char *s, size_t n)
{
	if (b->len + n + 1 > b->cap) {
		b->cap = (b->len + n + 1) * 2;
		b->s = realloc(b->s, b->cap);
	}
	memcpy(b->s + b->len, s, n);
	b->len += n;
	b->s[b->len] = 0;
}

static void sb_adds(struct sb *b, const char *s)
{
	sb_add(b, s, strlen(s));
}

static void add_value(struct sb *b, const char *name, const char *val)
{
	if (!strcmp(name, "DRY") || !strcmp(name, "ALL")) {
		sb_adds(b, val);	/* flags as given */
	} else if (!strcmp(name, "PARTS")) {
		char *copy = strdup(val), *save = NULL;
		int first = 1;
		for (char *w = strtok_r(copy, " ", &save); w; w = strtok_r(NULL, " ", &save)) {
			char *q = sh_quote(w);
			if (!first)
				sb_adds(b, " ");
			sb_adds(b, q);
			free(q);
			first = 0;
		}
		free(copy);
	} else {
		char *q = sh_quote(val);
		sb_adds(b, q);
		free(q);
	}
}

char *cmd_expand(rui_entry e, const char *const *vars)
{
	const char *t = rui_get(e);
	struct sb b = { 0 };
	sb_adds(&b, "");
	while (*t) {
		const char *open = strchr(t, '{');
		const char *close = open ? strchr(open, '}') : NULL;
		if (!open || !close) {
			sb_adds(&b, t);
			break;
		}
		sb_add(&b, t, open - t);
		char name[32];
		size_t n = close - open - 1;
		if (n >= sizeof(name))
			n = sizeof(name) - 1;
		memcpy(name, open + 1, n);
		name[n] = 0;
		const char *val = NULL;
		for (const char *const *v = vars; v && v[0]; v += 2)
			if (!strcmp(v[0], name))
				val = v[1];
		if (val)
			add_value(&b, name, val);
		else if (strcmp(name, "DRY") && strcmp(name, "ALL") && strcmp(name, "PARTS"))
			sb_add(&b, open, close - open + 1);	/* unknown: keep */
		t = close + 1;
	}
	return b.s;
}
