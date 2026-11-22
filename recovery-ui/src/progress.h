/* The tools' progress text in the screen's language.
 *
 * A tool's line "@progress N [code] text" (or "@step [code] text") carries
 * a fixed code in front of its English text; "[code:arg]" adds one value
 * (a file name) for the translation's %s. The code names the string
 * pg_<code> of the string table (i18n/en.txt). The English text stays the
 * tool's own: an English screen, an unknown code or a language without
 * that string shows it unchanged. The tools' log files keep English only
 * (the @progress lines are not written there). */
#ifndef RUI_PROGRESS_H
#define RUI_PROGRESS_H

#include <stddef.h>

/* Split s ("[code] text", "[code:arg] text" or plain "text") into code,
 * arg (empty when none) and the English text (a pointer into s). A code is
 * lower case letters, digits and "_" (at most ccap-1 of them), followed by
 * "]" or ":"; anything else (an English text that starts with "[") is
 * all text. */
void pg_split(const char *s, char *code, size_t ccap, char *arg, size_t acap,
	      const char **text);

/* The text to show for code/arg, english when it has no translation in
 * the current language; written into buf, which is returned */
const char *pg_text(const char *code, const char *arg, const char *english,
		    char *buf, size_t cap);

#endif
