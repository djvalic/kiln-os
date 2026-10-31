/* Reads the wizard's language from the main OS's settings.json. Busybox
 * shell and Python are not in the recovery OS, so this is a small scanner:
 * it walks the text, skips strings, and looks only at the keys of the
 * top-level object. Anything it does not understand gives English. */
#include "lang.h"

#include <ctype.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

rui_lang lang_from_code(const char *code)
{
	if (!code)
		return LANG_EN;
	for (int i = 0; i < LANG__COUNT; i++)
		if (!strcmp(code, rui_lang_code[i]))
			return (rui_lang)i;
	return LANG_EN;
}

/* Copy the JSON string that starts at p (on its opening quote) into out
 * (cap bytes, always NUL-terminated). Returns the position after the
 * closing quote, or NULL when the string never closes. *overflow is set
 * when it did not fit. A backslash keeps the next character as it is. */
static const char *json_string(const char *p, char *out, size_t cap, bool *overflow)
{
	size_t n = 0;
	*overflow = false;
	for (p++; *p; p++) {
		if (*p == '"') {
			out[n] = 0;
			return p + 1;
		}
		char c = *p;
		if (c == '\\' && p[1])
			c = *++p;
		if (n + 1 < cap)
			out[n++] = c;
		else
			*overflow = true;
	}
	return NULL;
}

static const char *skip_ws(const char *p)
{
	while (*p && isspace((unsigned char)*p))
		p++;
	return p;
}

rui_lang lang_from_settings_json(const char *j)
{
	int depth = 0;
	const char *p = j;
	while (p && *p) {
		char c = *p;
		if (c == '{' || c == '[') {
			depth++;
		} else if (c == '}' || c == ']') {
			depth--;
		} else if (c == '"') {
			char key[32];
			bool over;
			const char *end = json_string(p, key, sizeof(key), &over);
			if (!end)
				break;
			p = end;
			/* A string followed by ':' is a key; top level = depth 1 */
			if (depth == 1) {
				const char *q = skip_ws(p);
				if (*q == ':' && !over && !strcmp(key, "language")) {
					q = skip_ws(q + 1);
					if (*q != '"')
						return LANG_EN;
					char val[16];
					bool vover;
					if (!json_string(q, val, sizeof(val), &vover) || vover)
						return LANG_EN;
					return lang_from_code(val);
				}
			}
			continue;
		}
		p++;
	}
	return LANG_EN;
}

rui_lang lang_from_settings_file(const char *path)
{
	if (!path || !*path)
		return LANG_EN;
	FILE *f = fopen(path, "rb");
	if (!f)
		return LANG_EN;
	size_t cap = 4096, n = 0;
	char *buf = malloc(cap + 1);
	if (!buf) {
		fclose(f);
		return LANG_EN;
	}
	for (;;) {
		if (n == cap) {
			if (cap >= (1u << 20))	/* settings are a few KB */
				break;
			char *nb = realloc(buf, cap * 2 + 1);
			if (!nb)
				break;
			buf = nb;
			cap *= 2;
		}
		size_t r = fread(buf + n, 1, cap - n, f);
		if (r == 0)
			break;
		n += r;
	}
	fclose(f);
	buf[n] = 0;
	rui_lang lang = lang_from_settings_json(buf);
	free(buf);
	return lang;
}
