/* Current language and the lookup behind tr() (table: i18n_tab.c) */
#include "i18n.h"

#include <stdio.h>
#include <string.h>

static rui_lang cur = LANG_EN;

void i18n_set_lang(rui_lang lang)
{
	cur = (lang >= 0 && lang < LANG__COUNT) ? lang : LANG_EN;
}

rui_lang i18n_get_lang(void)
{
	return cur;
}

const char *tr(enum rui_str id)
{
	const char *s = rui_i18n_text[cur][id];
	return s && *s ? s : rui_i18n_text[LANG_EN][id];
}

const char *tr_sym(const char *sym, enum rui_str id)
{
	static char ring[8][256];
	static unsigned next;
	char *out = ring[next++ % 8];
	snprintf(out, sizeof(ring[0]), "%s  %s", sym ? sym : "", tr(id));
	return out;
}
