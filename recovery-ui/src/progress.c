/* The tools' progress text in the screen's language (progress.h) */
#include "progress.h"
#include "i18n.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

/* The codes ad5x-bootloader-install and ad5x-return-stock print; the
 * string is pg_<code> (tools/test_recovery_lang.sh checks both sides) */
static const struct {
	const char *code;
	enum rui_str id;
	bool arg;		/* the text has one %s: the line's arg */
} codes[] = {
	{ "checking",       RS_PG_CHECKING,       false },
	{ "done",           RS_PG_DONE,           false },
	{ "bl_spl",         RS_PG_BL_SPL,         false },
	{ "bl_kernel2",     RS_PG_BL_KERNEL2,     false },
	{ "bl_kernel",      RS_PG_BL_KERNEL,      false },
	{ "bl_uboot",       RS_PG_BL_UBOOT,       false },
	{ "bl_step0",       RS_PG_BL_STEP0,       false },
	{ "bl_step1",       RS_PG_BL_STEP1,       false },
	{ "bl_step1_up",    RS_PG_BL_STEP1_UP,    false },
	{ "bl_step2",       RS_PG_BL_STEP2,       false },
	{ "bl_step3",       RS_PG_BL_STEP3,       false },
	{ "bl_step4",       RS_PG_BL_STEP4,       false },
	{ "bl_step4_up",    RS_PG_BL_STEP4_UP,    false },
	{ "bl_step5",       RS_PG_BL_STEP5,       false },
	{ "bl_step5_up",    RS_PG_BL_STEP5_UP,    false },
	{ "rs_unpack",      RS_PG_RS_UNPACK,      true },
	{ "rs_root",        RS_PG_RS_ROOT,        false },
	{ "rs_step1",       RS_PG_RS_STEP1,       false },
	{ "rs_step2",       RS_PG_RS_STEP2,       false },
	{ "rs_step3",       RS_PG_RS_STEP3,       false },
	{ "rs_step4",       RS_PG_RS_STEP4,       false },
	{ "rs_step5",       RS_PG_RS_STEP5,       false },
	{ "rs_step6",       RS_PG_RS_STEP6,       false },
	{ "rs_step7",       RS_PG_RS_STEP7,       false },
	{ "rs_step8",       RS_PG_RS_STEP8,       false },
	{ "rs_step9",       RS_PG_RS_STEP9,       false },
};

static bool code_char(char c)
{
	return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_';
}

void pg_split(const char *s, char *code, size_t ccap, char *arg, size_t acap,
	      const char **text)
{
	code[0] = arg[0] = 0;
	*text = s;
	if (s[0] != '[')
		return;
	size_t n = 1;
	while (code_char(s[n]))
		n++;
	if (n == 1 || n - 1 >= ccap || (s[n] != ']' && s[n] != ':'))
		return;
	const char *end = strchr(s + n, ']');
	if (!end)
		return;
	if (s[n] == ':')
		snprintf(arg, acap, "%.*s", (int)(end - s - n - 1), s + n + 1);
	snprintf(code, ccap, "%.*s", (int)(n - 1), s + 1);
	end++;
	while (*end == ' ')
		end++;
	*text = end;
}

const char *pg_text(const char *code, const char *arg, const char *english,
		    char *buf, size_t cap)
{
	for (size_t i = 0; code && *code && i < sizeof(codes) / sizeof(codes[0]); i++) {
		if (strcmp(code, codes[i].code))
			continue;
		if (!tr_has(codes[i].id))
			break;
		if (!codes[i].arg)
			snprintf(buf, cap, "%s", tr(codes[i].id));
		else if (arg && *arg)
			snprintf(buf, cap, tr(codes[i].id), arg);
		else
			break;
		return buf;
	}
	snprintf(buf, cap, "%s", english ? english : "");
	return buf;
}

/* The start of the reasons ad5x-return-stock and ad5x-bootloader-install
 * give (their FAIL lines; "refused: another" is the "result:" of a second
 * run) and the string for each (tools/test_recovery_lang.sh checks that
 * every start is still a tool's text) */
static const struct {
	const char *start;
	enum rui_str id;
} whys[] = {
	{ "busy:",                                       RS_WHY_BUSY },
	{ "refused: another ",                           RS_WHY_BUSY },
	{ "a Return to Flashforge firmware is unfinished", RS_WHY_RS_UNFINISHED },
	{ "no Flashforge stock files found",             RS_WHY_NO_STOCK },
	{ "board: not on the allowlist",                 RS_WHY_BOARD },
	{ "chip: ",                                      RS_WHY_CHIP },
	{ "slot B holds no Kiln OS main system",         RS_WHY_NO_MAIN },
	{ "slot B's root doesn't mount",                 RS_WHY_NO_MAIN },
	{ "the main OS doesn't confirm",                 RS_WHY_UPDATE_MAIN },
	{ "the main OS has no whole Kiln 6.6",           RS_WHY_UPDATE_MAIN },
	{ "this recovery OS (ID ",                       RS_WHY_RECOVERY_OLD },
	{ "Kiln OS recorded its 6.6 ",                   RS_WHY_K66_FAILED },
	{ "/data: ",                                     RS_WHY_DATA_FULL },
	{ "--upgrade: no Kiln boot loader",              RS_WHY_NO_UPGRADE },
	{ "--flashforge-spl: ",                          RS_WHY_FFSPL },
	{ "--remove-kiln-data: ",                        RS_WHY_WIPE },
};

const char *why_text(const char *why, char *buf, size_t cap)
{
	why = why ? why : "";
	if (!tr_has(RS_WHY_OTHER)) {
		snprintf(buf, cap, "%s", why);
		return buf;
	}
	for (size_t i = 0; i < sizeof(whys) / sizeof(whys[0]); i++)
		if (!strncmp(why, whys[i].start, strlen(whys[i].start)) && tr_has(whys[i].id)) {
			snprintf(buf, cap, "%s", tr(whys[i].id));
			return buf;
		}
	snprintf(buf, cap, "%s", tr(RS_WHY_OTHER));
	return buf;
}

/* "YYYY-MM-DD HH:MM" at s */
static bool stamp(const char *s)
{
	static const char form[] = "dddd-dd-dd dd:dd";
	for (int i = 0; form[i]; i++)
		if (form[i] == 'd' ? !(s[i] >= '0' && s[i] <= '9') : s[i] != form[i])
			return false;
	return true;
}

/* The file name (no folder) of the text at s up to the first of stop */
static void file_of(const char *s, const char *stop, char *out, size_t cap)
{
	size_t n = strcspn(s, stop);
	const char *b = s;
	for (const char *q = s; q < s + n; q++)
		if (*q == '/')
			b = q + 1;
	snprintf(out, cap, "%.*s", (int)(n - (size_t)(b - s)), b);
}

const char *update_text(const char *line, char *buf, size_t cap)
{
	line = line ? line : "";
	if (!tr_has(RS_UPD_OTHER)) {
		snprintf(buf, cap, "%s", line);
		return buf;
	}
	char when[24] = "", msg[400], file[200];
	snprintf(msg, sizeof(msg), "%s", line);
	/* the file's time at the end, "  (YYYY-MM-DD HH:MM)" */
	size_t len = strlen(msg);
	if (len >= 20 && !strncmp(msg + len - 20, "  (", 3) && stamp(msg + len - 17) && msg[len - 1] == ')') {
		snprintf(when, sizeof(when), "%.16s", msg + len - 17);
		msg[len - 20] = 0;
	}
	/* the line's own time at the start (with seconds) */
	const char *m = msg;
	if (stamp(m)) {
		snprintf(when, sizeof(when), "%.16s", m);
		m += 16;
		if (m[0] == ':' && m[1] >= '0' && m[1] <= '9' && m[2] >= '0' && m[2] <= '9')
			m += 3;
	}
	while (*m == ' ')
		m++;
	if (!when[0])
		snprintf(when, sizeof(when), "?");
	if (!strncmp(m, "OK ", 3)) {
		file_of(m + 3, ":", file, sizeof(file));
		snprintf(buf, cap, tr(RS_UPD_OK), when, file);
	} else if (!strncmp(m, "SUCCESS", 7) || !strcmp(m, "rebooting into the main OS")) {
		snprintf(buf, cap, tr(RS_UPD_OK_NOFILE), when);
	} else if (!strncmp(m, "FAILED ", 7) && m[7] && m[7] != ' ') {
		file_of(m + 7, " ", file, sizeof(file));
		snprintf(buf, cap, tr(RS_UPD_FAILED), when, file);
	} else if (!strncmp(m, "FAILED", 6)) {
		snprintf(buf, cap, tr(RS_UPD_FAILED_NOFILE), when);
	} else if (!strncmp(m, "applying ", 9) && m[9]) {
		file_of(m + 9, "", file, sizeof(file));
		snprintf(buf, cap, tr(RS_UPD_STARTED), when, file);
	} else if (!strncmp(m, "skipping ", 9) && strstr(m, ": installed before")) {
		file_of(m + 9, ":", file, sizeof(file));
		snprintf(buf, cap, tr(RS_UPD_SKIPPED), when, file);
	} else {
		snprintf(buf, cap, tr(RS_UPD_OTHER), when);
	}
	return buf;
}
