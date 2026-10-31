#!/usr/bin/env python3
"""Regenerate the embedded Noto Sans subsets (fonts/*.c) for ad5x-recovery-ui.

usage: gen_fonts.py [NOTO_DIR]   (default /usr/share/fonts/noto)

Noto Sans / Noto Sans Mono (SIL OFL 1.1, fonts/OFL-1.1.txt), cut down to
Latin-1, a few punctuation marks, and every other character the recovery
UI's string table uses (i18n/*.txt, all languages), stripped of hinting,
then written as C arrays. A character the Noto Sans fonts do not draw
(CJK and Hangul need a separate font, not done yet) stops the build.
LVGL's Tiny TTF renders them at run time at any size; icons (LV_SYMBOL_*)
come from LVGL's built-in Montserrat as the fallback font.
The output is committed, so the build needs neither fontTools nor the fonts.
"""
import io
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
import gen_i18n  # noqa: E402
FONTS = {
    "noto_sans_regular": "NotoSans-Regular.ttf",
    "noto_sans_bold": "NotoSans-Bold.ttf",
    "noto_sans_mono": "NotoSansMono-Regular.ttf",
}
BASE_UNICODES = (list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) +
                 [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026])


def table_unicodes():
    """Every non-ASCII character of the string table, all languages."""
    tables, _ = gen_i18n.collect()
    chars = set()
    for tab in tables.values():
        for text in tab.values():
            chars.update(ord(c) for c in text if ord(c) > 0x7E)
    return sorted(chars)


def cut(path, unicodes):
    opts = subset.Options()
    opts.hinting = False
    opts.desubroutinize = True
    opts.layout_features = ["kern"]
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]   # keep copyright/licence
    opts.notdef_outline = True
    font = TTFont(path)
    sub = subset.Subsetter(opts)
    cmap = font.getBestCmap()
    # the base set is cut as before (a font may lack a few of its Latin-1
    # marks); the string table's own characters must all be there
    missing = [u for u in unicodes if u not in cmap and u not in BASE_UNICODES]
    if missing:
        names = ", ".join("U+%04X %s" % (u, chr(u)) for u in missing)
        raise SystemExit("gen_fonts: %s has no glyph for %s (CJK or Hangul "
                         "need a separate font)" % (os.path.basename(path), names))
    sub.populate(unicodes=unicodes)
    sub.subset(font)
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/noto"
    unicodes = sorted(set(BASE_UNICODES) | set(table_unicodes()))
    print("characters: %d (table adds %d)" % (len(unicodes),
          len(unicodes) - len(set(BASE_UNICODES))))
    for name, fname in FONTS.items():
        data = cut(os.path.join(src, fname), unicodes)
        lines = ["/* %s, subset by gen_fonts.py. SIL Open Font License 1.1"
                 " (OFL-1.1.txt). */" % fname,
                 "#include <stddef.h>",
                 "#include <stdint.h>",
                 "const uint8_t %s_ttf[] = {" % name]
        for i in range(0, len(data), 16):
            lines.append("  " + ",".join("0x%02x" % b for b in data[i:i + 16]) + ",")
        lines.append("};")
        lines.append("const size_t %s_ttf_len = %d;" % (name, len(data)))
        with open(os.path.join(HERE, name + ".c"), "w") as f:
            f.write("\n".join(lines) + "\n")
        print("%s: %d bytes" % (name, len(data)))


if __name__ == "__main__":
    main()
