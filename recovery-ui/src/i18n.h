/* Recovery UI strings: the language picked in the setup wizard
 * (lang.c) and the table in i18n_tab.c (built from the text files in i18n/). */
#ifndef RUI_I18N_H
#define RUI_I18N_H

#include "i18n_ids.h"

/* Language for tr() from now on; unknown values mean English */
void i18n_set_lang(rui_lang lang);
rui_lang i18n_get_lang(void);

/* The text of a string in the current language (English when the
 * translation is still empty). Valid for the life of the program. */
const char *tr(enum rui_str id);

/* "sym  text" for buttons and labels with an icon. The buffer is shared
 * by the last 8 calls: use the result at once (LVGL copies label text). */
const char *tr_sym(const char *sym, enum rui_str id);

#endif
