# Russian translation kit for Kiln OS

Thank you for helping with the Russian text. This folder has everything you need to translate the Kiln OS touch
screen, and the recovery screen is one more file next to it. You don't need to build anything.

## The files

| File | What it is |
|---|---|
| `helixscreen-ru.yml` | The Russian text of the touch screen, exactly as Kiln OS builds it today (HelixScreen v1.1.0-rc.1 with my patches). This is the file to edit. |
| `helixscreen-en.yml` | The English text, with the same keys. Only for reference, please don't edit it. |
| `missing-ru.md` | What is still open or English, sorted by screen: choices to check, texts that are probably too long, characters the screen can't draw, my own Kiln screens that need a native speaker's check, and the recovery screen. |
| [`../../recovery-ui/i18n/ru.txt`](../../recovery-ui/i18n/ru.txt) | The recovery screen's Russian text. All lines have a first Russian version that I wrote; please check and correct it. Its English is in [`en.txt`](../../recovery-ui/i18n/en.txt) in the same folder. |

## How to translate

In `helixscreen-ru.yml` every line is `'English key': 'Russian text'`.

- Change only the Russian text on the right. Never change the English key on the left. The screen finds the text by
  that key.
- Keep every placeholder exactly as written: `{}`, `{0}`, `{:.1f}`, `%d`, `%s`, `%u`, `%.2f`, `%%`. You can move a
  placeholder to fit Russian word order, but don't remove, rename or add one.
- Keep `\n` (line break), leading and trailing spaces inside the quotes, and any other markup.
- Some keys have plural forms (`one:`, `few:`, `many:`, `other:`). Fill in all of them; `other:` must stay.
- Inside `'...'` an apostrophe is written twice: `''`.
- Keep product names and abbreviations in English: Klipper, Moonraker, Spoolman, OrcaSlicer, PLA, PETG, PID, MCU,
  Wi-Fi. IFS stays IFS, because it is the name of the filament unit.
- Where the stock Flashforge firmware on the AD5X has a Russian name for the same thing, please use it. That is what
  the first round in issue #23 did: "Смещение по Z", "Wi-Fi", "Компенсация вибраций".
- For terms that come up again and again (стол, сопло, слот, катушка ...), use the word that HelixScreen's
  [glossary](https://github.com/prestonbrown/helixscreen/blob/v1.1.0-rc.1/translations/GLOSSARY.md) lists for
  Russian, or the word the rest of the file already uses. HelixScreen's
  [translator guide](https://github.com/prestonbrown/helixscreen/blob/v1.1.0-rc.1/docs/devel/TRANSLATION_CONTRIBUTOR_GUIDE.md)
  has more detail.
- The screen is small. Keep text about as long as the English. `missing-ru.md` lists two texts that are already cut off.
- The screen font has no `→` and no `№`; both show as an empty box. Please avoid them.
- If a wording would change what a setting or a warning means, please ask me in the issue first.

For the recovery screen, edit `recovery-ui/i18n/ru.txt`. Each line is an id, one TAB, then the text. Keep the id and
the TAB, write the Russian after it, and keep `%s` / `%d` / `%u` in the same order. The full rules are at the top of
`en.txt`.

## How to send it to me

Either way is fine:

- **Pull request** to [djvalic/kiln-os](https://github.com/djvalic/kiln-os) that changes
  `translations/ru/helixscreen-ru.yml` and/or `recovery-ui/i18n/ru.txt`. You can edit the files on github.com
  with the pencil button, and GitHub opens the pull request for you.
- **Attach the files** to [issue #23](https://github.com/djvalic/kiln-os/issues/23) (GitHub accepts `.yml` and
  `.txt` files in comments), and I add them.

Partial work is welcome too: one screen at a time is fine.

I turn your file into a patch for the Kiln OS image, so the change reaches the printer with the next update.

## How to check the file before you send it

One broken line stops the whole file from loading, so please check that it is still valid YAML (needs Python 3 with
PyYAML, `pip install pyyaml`):

```sh
python3 -c "import sys, yaml; d = yaml.safe_load(open(sys.argv[1], encoding='utf-8')); print('OK,', len(d['translations']), 'keys')" helixscreen-ru.yml
```

It prints `OK, 4923 keys`. An error message names the line
to fix.
