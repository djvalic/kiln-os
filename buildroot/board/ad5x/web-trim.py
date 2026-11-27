#!/usr/bin/env python3
"""Trim a prebuilt web interface (Fluidd, Mainsail) for the image.

usage: web-trim.py DIR

- .woff fonts with a .woff2 of the same font beside them are deleted
  (Fluidd names them NAME-HASH.woff / NAME-HASH2.woff2, Mainsail NAME.woff
  / NAME.woff2), but only when every @font-face of the interface's CSS
  that names the .woff also names a .woff2: browsers then never ask for
  the .woff, and no .js or .html file (but the service worker) names
  it. Their entries leave the service worker's precache list
  (sw.js), else its install would fail on them. Anything else stays
  (Mainsail's robotoMono-regular.woff has no .woff2).
- Text files (js, css, svg, json, html, webmanifest) in DIR/assets are
  gzipped and the plain file removed: nginx serves the .gz
  (gzip_static always; gunzip on for a client without gzip, nginx.conf).
  A copy Moonraker updated later has plain files only: gzip_static finds
  no .gz there and nginx serves the plain file.
- Text files elsewhere (index.html, config.json, the manifest, sw.js, the
  themes' css) stay plain, as try_files and index need them, with a .gz
  copy beside them (gzip_static on).

Output is reproducible (gzip -9 -n). Prints what it did.
"""
import json
import os
import re
import subprocess
import sys

TEXT = (".js", ".css", ".svg", ".json", ".html", ".webmanifest")
# Vite's build hash: 8 characters of base64url, not all lower case
# letters (so "-regular" or "-medium" in a font's own name isn't one)
HASHED = re.compile(r"^(?P<stem>.+)-(?P<hash>[A-Za-z0-9_-]{8})$")


def stem(name):
    """The font's name without the extension and a build hash"""
    base = name.rsplit(".", 1)[0]
    m = HASHED.match(base)
    h = m.group("hash") if m else ""
    if m and not (h.isalpha() and h.islower()):
        return base, m.group("stem")
    return base, base


def files(top):
    for d, _dirs, names in os.walk(top):
        for n in sorted(names):
            yield os.path.join(d, n)


def font_faces(top):
    """Every @font-face block of the CSS files under TOP"""
    blocks = []
    for f in files(top):
        if f.endswith(".css"):
            with open(f, encoding="utf-8", errors="replace") as fh:
                blocks += re.findall(r"@font-face\s*\{[^}]*\}", fh.read())
    return blocks


def precache_drop(sw, rel):
    """SW (the service worker's text) without the precache entry of REL
    ({"revision":...,"url":"REL"} in either order, Workbox's manifest)"""
    u = re.escape(json.dumps(rel))
    for pat in (r'\{"revision":(?:null|"[^"]*"),"url":%s\},?' % u,
                r'\{"url":%s,"revision":(?:null|"[^"]*")\},?' % u):
        sw = re.sub(pat, "", sw)
    return sw.replace(",]", "]")


def code_texts(top):
    """The text of the .js and .html files under TOP but the service
    worker (sw.js, handled on its own): a .woff named there stays"""
    out = []
    for f in files(top):
        if f.endswith((".js", ".html")) and f != os.path.join(top, "sw.js"):
            with open(f, encoding="utf-8", errors="replace") as fh:
                out.append(fh.read())
    return out


def trim_woff(top):
    faces = font_faces(top)
    code = code_texts(top)
    # The service worker precaches every file by name: an entry for a
    # deleted file would make its install fail (and keep browsers on the
    # interface it cached before), so the entry goes too, or the file stays
    swf = os.path.join(top, "sw.js")
    sw = None
    if os.path.isfile(swf):
        with open(swf, encoding="utf-8") as fh:
            sw = fh.read()
    gone = kept = size = 0
    for f in files(top):
        if not f.endswith(".woff"):
            continue
        d, name = os.path.split(f)
        base, st = stem(name)
        twins = [n for n in os.listdir(d) if n.endswith(".woff2")
                 and (stem(n)[0] == base or stem(n)[1] == st)]
        using = [b for b in faces if name in b]
        rel = os.path.relpath(f, top).replace(os.sep, "/")
        new_sw = precache_drop(sw, rel) if sw is not None else None
        if twins and all(".woff2" in b for b in using) and \
                not any(name in t for t in code) and \
                (new_sw is None or name not in new_sw):
            size += os.path.getsize(f)
            os.unlink(f)
            sw = new_sw
            gone += 1
        else:
            kept += 1
    if sw is not None:
        with open(swf, "w", encoding="utf-8") as fh:
            fh.write(sw)
    print(f"web-trim: {gone} .woff deleted ({size} bytes; a .woff2 is "
          f"there), {kept} kept")


def gzip(paths, keep):
    if paths:
        subprocess.run(["gzip", "-9", "-n", "-f"] + (["-k"] if keep else [])
                       + paths, check=True)


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit(__doc__)
    top = sys.argv[1]
    trim_woff(top)
    assets = os.path.join(top, "assets")
    text = [f for f in files(top) if f.endswith(TEXT)]
    only_gz = [f for f in text if f.startswith(assets + os.sep)]
    both = [f for f in text if f not in only_gz]
    gzip(only_gz, keep=False)
    gzip(both, keep=True)
    print(f"web-trim: {len(only_gz)} files in assets/ as .gz only, "
          f"{len(both)} elsewhere plain and .gz")


if __name__ == "__main__":
    main()
