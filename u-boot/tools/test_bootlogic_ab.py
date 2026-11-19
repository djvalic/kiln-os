#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""A/B boot rules (board/flashforge/ad5x/bootlogic.c, ad5x_ab_pick) on the
build host, through bootlogic_cli.

    u-boot/tools/test_bootlogic_ab.py U-BOOT-TREE

U-BOOT-TREE is a U-Boot source tree with Kiln's patches applied (the one
u-boot/build.sh unpacks, or USRC)."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def build(tree, out):
    b = os.path.join(tree, "board/flashforge/ad5x")
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-I", b, "-o", out,
                    os.path.join(HERE, "bootlogic_cli.c"),
                    os.path.join(b, "bootlogic.c")], check=True)


def run(cli, mode, **kv):
    text = "".join(f"{k} {v}\n" for k, v in kv.items())
    r = subprocess.run([cli, mode], input=text, capture_output=True,
                       text=True, check=True)
    return dict(l.split(" ", 1) if " " in l else (l, "")
                for l in r.stdout.splitlines() if not l.startswith("--"))


CASES = [
    # (name, inputs, expected subset)
    ("plain start stays",
     dict(slot="a", other_main=1),
     dict(slot="a", switched="0", failed="0", clear_upgrade="0")),
    ("update pending, still counting",
     dict(slot="b", other_main=1, upgrade=1),
     dict(slot="b", switched="0", failed="0", clear_upgrade="0")),
    ("bootlimit passed: back, update failed",
     dict(slot="b", other_main=1, upgrade=1, alt=1),
     dict(slot="a", switched="1", failed="1", clear_upgrade="1")),
    ("bootlimit passed, no other main OS: stay, count cleared",
     dict(slot="b", other_main=0, upgrade=1, alt=1),
     dict(slot="b", switched="0", failed="0", clear_upgrade="1")),
    ("install cut off with an update pending: back",
     dict(slot="a", other_main=1, upgrade=1, in_progress=1),
     dict(slot="b", switched="1", failed="1", clear_upgrade="1")),
    ("recovery_status left over without an update: stay",
     dict(slot="a", other_main=1, in_progress=1),
     dict(slot="a", switched="0", failed="0", clear_upgrade="0")),
    ("no kernel left: the other slot, no update to fail",
     dict(slot="a", other_main=1, no_kernel=1),
     dict(slot="b", switched="1", failed="0", clear_upgrade="1")),
    ("no kernel left in an updated slot: back, failed",
     dict(slot="b", other_main=1, upgrade=1, no_kernel=1),
     dict(slot="a", switched="1", failed="1", clear_upgrade="1")),
    ("no kernel left, already switched this start: stay",
     dict(slot="b", other_main=1, no_kernel=1, switched=1),
     dict(slot="b", switched="0")),
]

DECIDE = [
    # decide()'s fallback: set when 1.x would go to the recovery OS
    ("6.6 failed twice, no 7.3: fallback",
     dict(flag_b=1, data_ok=1, have_66=1, rel_66="r1", state_tries=2,
          state_kernel="66", state_release="r1"),
     dict(fallback="1")),
    ("plain start: no fallback",
     dict(flag_b=1, data_ok=1, have_66=1, rel_66="r1"),
     dict(target="main", fallback="0")),
]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    bad = 0
    with tempfile.TemporaryDirectory() as t:
        cli = os.path.join(t, "bootlogic_cli")
        build(sys.argv[1], cli)
        for mode, cases in (("ab", CASES), ("decide", DECIDE)):
            for name, inp, want in cases:
                got = run(cli, mode, **inp)
                diff = {k: (v, got.get(k)) for k, v in want.items()
                        if got.get(k) != v}
                print(("ok  " if not diff else "BAD ") + f"{mode}: {name}"
                      + (f" {diff} ({got.get('msg')})" if diff else ""))
                bad += bool(diff)
    print(f"{bad} failed" if bad else "all passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
