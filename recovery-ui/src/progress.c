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
