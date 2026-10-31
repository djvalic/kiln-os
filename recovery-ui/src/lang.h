/* The language of the recovery UI: the "language" key of the main OS's
 * settings.json (written by the setup wizard). No JSON library: the
 * recovery OS has none. */
#ifndef RUI_LANG_H
#define RUI_LANG_H

#include "i18n_ids.h"

/* A code from the picker ("en", "de", ...); anything else is LANG_EN */
rui_lang lang_from_code(const char *code);

/* The top-level "language" string of a JSON object text. Nested keys,
 * keys inside strings, a missing key or a non-string value give LANG_EN. */
rui_lang lang_from_settings_json(const char *json);

/* The same for a file; a missing or unreadable file gives LANG_EN */
rui_lang lang_from_settings_file(const char *path);

#endif
