#!/usr/bin/env python3
"""A/B boot rules (patch 0040) through tools/bootlogic_cli.c.

    cc -I$USRC/board/flashforge/ad5x -o bootlogic_cli \
        u-boot/tools/bootlogic_cli.c $USRC/board/flashforge/ad5x/bootlogic.c
    python3 u-boot/tools/test_bootlogic_ab.py ./bootlogic_cli
"""
import subprocess, sys
CLI = sys.argv[1]
R66, R73 = "6.6.18-rt23-ad5x", "7.3.4-ad5x"
LEG = dict(flag_b=1, data_ok=1, slot_a_ok=1, b_have_66=1, b_rel_66=R66, b_have_73=1, b_rel_73=R73)
AB = dict(flag_b=1, data_ok=1, a_have_66=1, a_rel_66=R66, a_have_73=1, a_rel_73=R73,
          b_have_66=1, b_rel_66=R66, b_have_73=1, b_rel_73=R73)
def run(**kw):
    inp = "".join("%s %s\n" % kv for kv in kw.items())
    out = subprocess.run([CLI, "decide"], input=inp, capture_output=True, text=True, check=True).stdout
    d = {}
    for l in out.split("--state--")[0].splitlines():
        k, _, v = l.partition(" "); d[k] = v
    return d
fails = 0
def check(name, d, **want):
    global fails
    bad = {k: (d.get(k), v) for k, v in want.items() if d.get(k) != str(v)}
    print(("ok   " if not bad else "FAIL ") + name + ("" if not bad else "  %s | %s" % (bad, d.get("msg"))))
    fails += bool(bad)

# legacy (Kiln 1.x: recovery in A, main in B) behaves as before
check("legacy normal", run(**LEG), target="main", slot="b", kernel="66", write_flag=0)
check("legacy flag A -> recovery", run(**{**LEG, "flag_b": 0}), target="recovery")
check("legacy 6.6 failed x2 -> recovery", run(**LEG, state_tries=2, state_kernel="66", state_release=R66),
      target="recovery", write_flag=1, rec_failed_own=R66)
check("legacy 6.6 1 try -> again", run(**LEG, state_tries=1, state_kernel="66", state_release=R66),
      target="main", slot="b", state_tries=2)
check("legacy 7.3 wanted", run(**LEG, mainline_wanted=1), target="main", kernel="73")
check("legacy 7.3 failed -> 6.6", run(**LEG, mainline_wanted=1, state_tries=1, state_kernel="73", state_release=R73),
      target="main", kernel="66", rec_failed_mainline=R73)
# A/B
check("ab normal B", run(**AB), target="main", slot="b", kernel="66", write_flag=0)
check("ab normal A", run(**{**AB, "flag_b": 0}), target="main", slot="a", kernel="66", write_flag=0)
check("ab B 6.6 failed x2 -> A, flag moved", run(**AB, state_tries=2, state_kernel="66", state_release=R66, state_slot="b"),
      target="main", slot="a", kernel="66", write_flag=1, rec_failed_own=R66, rec_failed_own_a="")
check("ab B 7.3 failed -> B 6.6", run(**AB, mainline_wanted=1, state_tries=1, state_kernel="73", state_release=R73, state_slot="b"),
      target="main", slot="b", kernel="66", rec_failed_mainline=R73, write_flag=0)
check("ab A 6.6 failed x2 (flag A) -> B", run(**{**AB, "flag_b": 0}, state_tries=2, state_kernel="66", state_release=R66, state_slot="a"),
      target="main", slot="b", write_flag=-1, rec_failed_own_a=R66)
check("ab both failed -> safe B", run(**AB, rec_failed_own_a=R66, state_tries=2, state_kernel="66", state_release=R66, state_slot="b"),
      target="safe", slot="b", kernel="66", wdt=0)
check("ab safe start 1 not finished -> safe again", run(**AB, rec_failed_own_a=R66, rec_failed_own=R66,
      state_tries=1, state_kernel="66", state_release=R66, state_slot="b", state_safe=1, wdt_os=30, b_wdt_capable=1),
      target="safe", slot="b", state_tries=2, wdt=0)
check("ab safe failed x2 -> prompt", run(**AB, rec_failed_own_a=R66, rec_failed_own=R66,
      state_tries=2, state_kernel="66", state_release=R66, state_slot="b", state_safe=1),
      target="prompt", safe_fail=1)
check("ab records of old release cleared on update", run(**AB, rec_failed_own="6.6.0-old", rec_failed_own_a="6.6.0-old"),
      target="main", slot="b", rec_failed_own="", rec_failed_own_a="")
check("ab watchdog runs into main", run(**AB, wdt_os=30, b_wdt_capable=1), target="main", wdt=30)
check("ab stale tries from other slot don't count", run(**AB, state_tries=5, state_kernel="66", state_release=R66, state_slot="a"),
      target="main", slot="b", state_tries=1)
check("ab only A has a main OS, flag B -> A", run(flag_b=1, data_ok=1, a_have_66=1, a_rel_66=R66),
      target="main", slot="a", write_flag=1)
check("nothing anywhere -> prompt", run(flag_b=1, data_ok=1), target="prompt")
print("failures:", fails); sys.exit(1 if fails else 0)
