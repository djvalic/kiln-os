#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Worst-case stack depth of the SPL, from GCC's call-graph files.

Build the SPL with KCFLAGS=-fcallgraph-info=su (u-boot/build.sh does, in a
separate check build); GCC writes one .ci file (VCG) per object with each
function's stack frame and its calls. This walks the call graph from the
SPL's entry (board_init_f; _start itself uses no stack) and prints the
deepest path.

Indirect calls are resolved to the functions given with --indirect (the
SPL's console functions, called through struct serial_device); a call into
unknown code, a dynamic stack frame or recursion other than a function
calling itself once (x2600_spl_putc for "\\n") is an error.

GCC splits functions (name.part.N) and may then merge a part with an
identical function (identical code folding), leaving a call to the part
but no node for it. With --nm (``nm spl/u-boot-spl``) such a call counts
as a call to the function at the same address that has a node; without
one, or when none is found, it is an error, never left out.

  spl_stack.py SPL_OUT_DIR [--nm NM_OUTPUT] [--limit BYTES]
               [--root board_init_f]
Exit 0 when the worst case fits the limit, 1 otherwise.
"""
import argparse
import os
import re
import sys

NODE = re.compile(r'node: \{ title: "([^"]+)" label: "([^"]*)"')
EDGE = re.compile(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)"')
DEFAULT_INDIRECT = ("x2600_spl_putc", "x2600_spl_puts", "x2600_spl_getc",
                    "x2600_spl_tstc", "x2600_spl_serial_start",
                    "x2600_spl_serial_stop", "x2600_spl_setbrg")
# edges never taken: serial.c's get_current() prints "Cannot find
# console" (and hangs) only when default_serial_console() returns NULL; the
# SPL's never does
DEAD_EDGES = {("get_current", "puts"), ("get_current", "hang")}
# hand-written (start.S), no stack of the SPL's: ad5x_return_to_rom puts the
# boot ROM's stack pointer back and jumps to the ROM
ASM_NO_STACK = ("ad5x_return_to_rom",)


def load(outdir):
    frames, kind, edges, names = {}, {}, {}, {}
    for root, _, files in os.walk(outdir):
        for f in files:
            if not f.endswith(".ci"):
                continue
            with open(os.path.join(root, f), encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read()
            for title, label in NODE.findall(text):
                parts = label.split("\\n")
                if len(parts) >= 3 and "bytes" in parts[2]:
                    m = re.match(r"(\d+) bytes \((\w+)", parts[2])
                    frames[title] = int(m.group(1))
                    kind[title] = m.group(2)
                    names[title] = parts[0]
            for src, dst in EDGE.findall(text):
                edges.setdefault(src, []).append(dst)
    return frames, kind, edges, names


def parse_nm(text):
    """{address: [symbol names]} from nm output."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            try:
                out.setdefault(int(parts[0], 16), []).append(parts[2])
            except ValueError:
                pass
    return out


def aliases(target, frames, names, nm):
    """The defined nodes of the functions at the address of @target (a
    call-graph title such as file:name.part.0), from the nm map."""
    if not nm:
        return []
    short = target.rsplit(":", 1)[-1]
    out = []
    for syms in nm.values():
        if short not in syms:
            continue
        for other in syms:
            if other == short:
                continue
            out += [t for t, n in names.items() if n == other]
    return sorted(set(out))


def resolve(target, frames, names):
    """The defined nodes a call target can be: globals by name (GCC titles
    some, weak ones among them, file:name), statics by file:name, GCC's
    clones (.constprop.0, .isra.0) by prefix. Several (a weak and a strong
    definition): all of them, the deepest counts."""
    if target in frames:
        return [target]
    if ":" in target:
        return [t for t in frames if t.startswith(target + ".")]
    return [t for t, n in names.items() if n == target]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("outdir")
    ap.add_argument("--limit", type=lambda s: int(s, 0), default=0x800)
    ap.add_argument("--root", default="board_init_f")
    ap.add_argument("--indirect", default=",".join(DEFAULT_INDIRECT))
    ap.add_argument("--nm", help="nm output of spl/u-boot-spl (aliases)")
    a = ap.parse_args(argv)
    nm = {}
    if a.nm:
        with open(a.nm, encoding="utf-8") as fh:
            nm = parse_nm(fh.read())

    frames, kind, edges, names = load(a.outdir)
    if not frames:
        print("spl_stack: no .ci files under %s (build with "
              "KCFLAGS=-fcallgraph-info=su)" % a.outdir)
        return 1
    indirect = [t for n in a.indirect.split(",") if n
                for t in resolve(n, frames, names)]
    errors, notes = [], []
    memo = {}

    def depth(node, stack):
        if node in memo:
            return memo[node]
        if kind.get(node) not in ("static", "bounded"):
            errors.append("%s: %s stack frame" % (names.get(node, node),
                                                  kind.get(node)))
        best, path = 0, []
        for t in edges.get(node, []):
            if (names.get(node, node), t) in DEAD_EDGES:
                continue
            if t == "__indirect_call":
                cands = indirect
            else:
                cands = resolve(t, frames, names)
                if not cands:
                    if t in ("memcpy", "memset") or \
                            t.startswith("__builtin_"):
                        continue        # expanded inline
                    if t in ASM_NO_STACK:
                        continue
                    if re.search(r"\.part\.\d+$", t):
                        # a split part merged with an identical function
                        cands = aliases(t, frames, names, nm)
                        if cands:
                            notes.append("%s calls %s: counted as %s (the "
                                         "same code)" %
                                         (names.get(node, node), t,
                                          ", ".join(names[c]
                                                    for c in cands)))
                    if not cands:
                        errors.append("%s calls unknown %s%s" %
                                      (names.get(node, node), t,
                                       "" if nm or ".part." not in t else
                                       " (give --nm to resolve aliases)"))
                        continue
            for c in cands:
                if c == node:   # a function calling itself once
                    d, p = frames[c], [c]
                elif c in stack:
                    errors.append("recursion: %s -> %s" %
                                  (names.get(node, node), names.get(c, c)))
                    continue
                else:
                    d, p = depth(c, stack | {c})
                if d > best:
                    best, path = d, p
        memo[node] = (frames.get(node, 0) + best, [node] + path)
        return memo[node]

    root = (resolve(a.root, frames, names) or [None])[0]
    if root is None:
        print("spl_stack: no %s in the call graph" % a.root)
        return 1
    total, path = depth(root, {root})
    print("SPL stack, worst case from %s: %d bytes (limit %d)" %
          (a.root, total, a.limit))
    for n in path:
        print("  %5d  %s" % (frames[n], names.get(n, n)))
    for w in sorted(set(notes)):
        print("spl_stack: " + w)
    for e in sorted(set(errors)):
        print("spl_stack: ERROR: " + e)
    if errors or total > a.limit:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
