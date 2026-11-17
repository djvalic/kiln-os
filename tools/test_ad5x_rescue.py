#!/usr/bin/env python3
"""ad5x_emmc_image.py --rescue, run without a printer: the script U-Boot
would source is carried out here against an eMMC image file (each piece
fetched from rescue/, its sha256 checked, written), starting from the first
MiB USBCloner writes. The result must be the release's eMMC with the
usershare asked for.

    python3 tools/test_ad5x_rescue.py
"""
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ad5x_emmc_image as img  # noqa: E402
import test_ad5x_emmc_repair as t  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    print("%s  %s" % ("ok  " if cond else "FAIL", name))
    if not cond:
        fails += 1


def record(first):
    r = first[img.RESCUE_LBA * 512:].split(b"\0")[0].decode()
    lines = r.split("\n")
    return lines[0], dict(l.split("=", 1) for l in lines[1:] if "=" in l)


def run_script(out, scr, disk):
    """What kr_piece does for each line of rescue.scr."""
    hdr = scr[:64]
    assert struct.unpack(">I", hdr[:4])[0] == img.UIMAGE_MAGIC
    assert hdr[30] == 6, "not a script image"
    n = struct.unpack(">I", scr[64:68])[0]
    text = scr[72:72 + n].decode()
    env, done = {}, 0
    with open(disk, "r+b") as d:
        for line in text.splitlines():
            for cmd in line.split("; "):
                m = re.fullmatch(r"setenv (\w+) (\S+)", cmd)
                if m:
                    env[m.group(1)] = m.group(2)
                elif cmd == "run kr_piece":
                    sz = int(env["sz"], 16)
                    if env["f"] == "-":
                        b = bytes(sz)
                    else:
                        b = open(os.path.join(out, env["f"][1:]), "rb").read()
                    if len(b) != sz or img.sha256(b) != env["sum"]:
                        raise AssertionError("piece %s: sha256" % env["f"])
                    if int(env["cnt"], 16) * 512 != sz:
                        raise AssertionError("piece %s: count" % env["f"])
                    d.seek(int(env["blk"], 16) * 512)
                    d.write(b)
                    done += 1
    return text, done


def main():
    with tempfile.TemporaryDirectory() as td:
        image = t.release(td)
        src = os.path.join(td, "src")
        mac = "02:AA:BB:CC:DD:EE"
        out = os.path.join(td, "rescue-set")
        rc = img.main(["--spl", os.path.join(src, "spl"), "--uboot",
                       os.path.join(src, "uboot"), "--kernel",
                       os.path.join(src, "kernel"), "--main",
                       os.path.join(src, "rootfs.squashfs"), "--recovery",
                       os.path.join(src, "rootfs.squashfs"), "--data-mib",
                       "32", "--mac", mac, "--rescue", "192.168.1.10:8000",
                       "--test-image", out])
        check("image with --rescue --mac", rc == 0)
        first = open(os.path.join(out, img.RESCUE_FIRST), "rb").read()
        magic, rec = record(first)
        scr = open(os.path.join(out, "rescue", "rescue.scr"), "rb").read()
        check("record: magic, server, port", magic == "KILN-RESCUE 1" and
              rec["server"] == "192.168.1.10" and rec["port"] == "8000")
        check("record: the script's sha256", rec["sha256"] == img.sha256(scr))
        check("record: the MAC chosen", rec.get("mac") == mac)
        normal = open(os.path.join(out, "00-first-mib.bin"), "rb").read()
        check("rescue first MiB = the normal one + the record",
              first[:img.RESCUE_LBA * 512] == normal[:img.RESCUE_LBA * 512]
              and not any(normal[img.RESCUE_LBA * 512:]))

        # a wrecked eMMC: random bytes, then USBCloner's first MiB
        whole = os.path.join(out, "TEST-ONLY-whole-emmc-do-not-flash.img")
        disk = os.path.join(td, "emmc.img")
        size = os.path.getsize(whole)
        with open(disk, "wb") as d:
            for _ in range(size // (1 << 20)):
                d.write(os.urandom(1 << 20))
            d.seek(0)
            d.write(first)
        text, done = run_script(out, scr, disk)
        check("script: %d pieces, the first MiB last" % done,
              text.rstrip().splitlines()[-3].find("00-first-mib") > 0)
        same = True
        sums = img_sums = open(os.path.join(out, "SHA256SUMS")).read()
        with open(disk, "rb") as d:
            for line in img_sums.splitlines():
                name = line.split()[1]
                key = "00-first-mib.bin" if name.startswith("00-") else \
                    name.split("-")[0]
                if key not in t.rep.IMAGE_FILES:
                    continue
                b = open(os.path.join(out, name), "rb").read()
                d.seek(t.rep.IMAGE_FILES[key][1])
                if d.read(len(b)) != b:
                    print("  differs: %s" % name)
                    same = False
        check("eMMC holds every piece of the release, usershare included",
              same and "p6-usershare.img" in sums)
        us = os.path.join(td, "p6.img")
        with open(disk, "rb") as d, open(us, "wb") as f:
            d.seek(img.PARTS[5][2] * 512)
            f.write(d.read(img.PARTS[5][3] * 512))
        r = subprocess.run(["debugfs", "-c", "-R", "cat /MAC", us],
                           capture_output=True, text=True)
        check("usershare /MAC is the one chosen", r.stdout.strip() == mac)

        # this printer's own usershare is preferred; a bad one falls back
        good = t.usershare(td)
        bad = os.path.join(td, "bad.img")
        with open(bad, "wb") as f:
            f.write(bytes(4096))
        out2 = os.path.join(td, "set2")
        rc = img.main(["--spl", os.path.join(src, "spl"), "--uboot",
                       os.path.join(src, "uboot"), "--kernel",
                       os.path.join(src, "kernel"), "--main",
                       os.path.join(src, "rootfs.squashfs"), "--recovery",
                       os.path.join(src, "rootfs.squashfs"), "--data-mib",
                       "32", "--usershare", bad, "--usershare", good,
                       "--mac", mac, "--rescue", "192.168.1.10", out2])
        _, rec2 = record(open(os.path.join(out2, img.RESCUE_FIRST),
                              "rb").read())
        check("the printer's own usershare used (its /MAC)",
              rc == 0 and rec2.get("mac") == t.MAC)
        out3 = os.path.join(td, "set3")
        rc = img.main(["--spl", os.path.join(src, "spl"), "--uboot",
                       os.path.join(src, "uboot"), "--kernel",
                       os.path.join(src, "kernel"), "--main",
                       os.path.join(src, "rootfs.squashfs"), "--recovery",
                       os.path.join(src, "rootfs.squashfs"), "--usershare",
                       bad, "--rescue", "192.168.1.10", out3])
        check("no good usershare and no --mac: refused", rc == 1)
        # --from-update: an update zip whose main OS carries the kernel and
        # the recovery OS, which carries the SPL and U-Boot
        def squash(tree, out):
            subprocess.run(["mksquashfs", tree, out, "-quiet", "-noappend"],
                           check=True, stdout=subprocess.DEVNULL)

        def update_zip(name, uboot):
            rt = os.path.join(td, name + "-rec")
            bl = os.path.join(rt, "usr/share/ad5x/bootloader")
            os.makedirs(bl)
            spl_b = open(os.path.join(src, "spl"), "rb").read()
            for n, b in (("spl-mmc.img", spl_b), ("u-boot-emmc.img", uboot)):
                open(os.path.join(bl, n), "wb").write(b)
            open(os.path.join(bl, "SHA256SUMS"), "w").write(
                "%s  spl-mmc.img\n%s  u-boot-emmc.img\n" %
                (img.sha256(spl_b), img.sha256(uboot)))
            rec = os.path.join(td, name + "-rec.squashfs")
            squash(rt, rec)
            mt = os.path.join(td, name + "-main")
            for d in ("usr/lib/ad5x/kernel66", "usr/share/ad5x/recovery"):
                os.makedirs(os.path.join(mt, d))
            kern = open(os.path.join(src, "kernel"), "rb").read()
            open(os.path.join(mt, img.MAIN_KERNEL), "wb").write(kern)
            rb = open(rec, "rb").read()
            open(os.path.join(mt, img.MAIN_RECOVERY), "wb").write(rb)
            open(os.path.join(mt, img.MAIN_RECOVERY_SHA), "w").write(
                img.sha256(rb) + "\n")
            main = os.path.join(td, name + "-main.squashfs")
            squash(mt, main)
            z = os.path.join(td, name + "-update.zip")
            import zipfile
            with zipfile.ZipFile(z, "w") as zf:
                zf.write(main, "rootfs.squashfs")
                zf.writestr("SHA256SUMS", "%s  rootfs.squashfs\n" %
                            img.sha256(open(main, "rb").read()))
            return z, kern, rb

        new_uboot = t.uimage(b"Kiln U-Boot test",
                             b"KILN-RESCUE 1\n" + os.urandom(100000))
        z, kern, rb = update_zip("new", new_uboot)
        out4 = os.path.join(td, "set4")
        rc = img.main(["--from-update", z, "--mac", mac, "--rescue",
                       "192.168.1.10", out4])
        check("--from-update --rescue", rc == 0 and
              open(os.path.join(out4, "p1-kernel.img"), "rb").read() == kern
              and open(os.path.join(out4, "p2-rootfs-recovery.img"),
                       "rb").read() == rb)
        old_uboot = t.uimage(b"Kiln U-Boot test", os.urandom(100000))
        z, _, _ = update_zip("old", old_uboot)
        rc = img.main(["--from-update", z, "--mac", mac, "--rescue",
                       "192.168.1.10", os.path.join(td, "set5")])
        check("a U-Boot without the rescue: refused", rc == 1 and
              not os.path.exists(os.path.join(td, "set5")))
    print("failures: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
