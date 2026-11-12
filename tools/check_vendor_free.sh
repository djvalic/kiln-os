#!/bin/bash
# Check that release files contain no Flashforge/Ingenic files.
#
# usage: tools/check_vendor_free.sh [-s STOCKDIR]... [--no-stock] [-q] TARGET...
#   TARGET   a root filesystem: directory, rootfs.squashfs, rootfs.tar; an
#            update (.zip, .swu); an install stick directory or .zip. Images
#            and archives inside a target are unpacked and checked too.
#   -s DIR   reference stock firmware tree(s) to compare file hashes with
#            (default, when present: firmware/ff-repo/stock5x and
#            firmware/stock-3.1.0/unpacked, the local git-ignored download)
#   --no-stock  names and file types only
#   -q       print only findings and the result line
#
# Flags (any one makes the exit status 1):
#   - known vendor names: module_driver/, usr/lib/ad5x/stock-tools/, kernel
#     modules (*.ko, or ELF with a vermagic), libhardware2.so, libutils2.so,
#     ELF binaries named cmd_gpio / cmd_fb / cmd_jpeg_display (our /usr/bin
#     wrappers are links/scripts and pass), kernel images (kernel.uimage,
#     xImage*, uImage*, or any file starting with the uImage magic)
#   - any file of 64 bytes or more whose sha256 equals a file of the stock
#     firmware (when a reference tree is there); for non-ELF files that
#     stock itself took unchanged from open-source upstreams (UPSTREAM below:
#     Python, Klipper, nginx, iproute2 data...) such a match is only counted
# Exit status: 0 clean, 1 vendor files found, 2 usage or unpack error.
# Last line: "check_vendor_free: CLEAN ..." or "check_vendor_free: FOUND n ...".
set -uo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
US=$REPO/buildroot/output/host/bin/unsquashfs
[ -x "$US" ] || US=$REPO/buildroot/output-recovery/host/bin/unsquashfs
[ -x "$US" ] || US=$(command -v unsquashfs || true)
export AD5X_UNSQUASHFS=$US AD5X_REPO=$REPO
exec python3 - "$@" <<'PY'
import hashlib, io, os, shutil, stat, subprocess, sys, tarfile, tempfile, zipfile

REPO = os.environ["AD5X_REPO"]
UNSQ = os.environ.get("AD5X_UNSQUASHFS") or ""
USAGE = "usage: tools/check_vendor_free.sh [-s STOCKDIR]... [--no-stock] [-q] TARGET..."
OWN_KERNEL_DIR = ("usr/lib/ad5x/kernel66/", "usr/lib/ad5x/kernel-mainline/")
VENDOR_NAMES_ANY = {"libhardware2.so", "libutils2.so", "kernel.uimage"}
VENDOR_ELF_NAMES = {"cmd_gpio", "cmd_fb", "cmd_jpeg_display"}
# Parts of the stock firmware that are unmodified upstream open-source
# software (Python, Klipper, Moonraker, nginx, iproute2 data, ...): a file
# of ours that equals one of these non-ELF files came from the same upstream,
# not from Flashforge, and is only counted. ELF files are always flagged
# (our toolchain differs, so an identical binary was copied).
UPSTREAM = ("usr/prog/Python-", "usr/prog/klipper/", "usr/prog/moonraker/",
            "usr/data/nginx/", "usr/prog/nginx/", "usr/prog/opencv", "usr/prog/qt-",
            "usr/prog/ffmpeg", "usr/prog/curl", "usr/prog/libffi", "usr/prog/libzip",
            "usr/prog/openssl", "usr/prog/x264", "usr/prog/tslib", "usr/lib/python",
            "usr/share/", "usr/lib/tc/", "etc/iproute2/", "etc/ssl/", "etc/libnl/",
            "etc/network/if-", "bin/mk_cmds", "bin/compile_et",
            # Buildroot's own skeleton and package files (stock is Buildroot 2020.02)
            "etc/services", "etc/protocols", "etc/profile", "etc/nsswitch.conf",
            "etc/wpa_supplicant.conf", "etc/inittab", "etc/fstab", "etc/issue",
            "etc/init.d/rcS", "etc/init.d/rcK", "etc/init.d/S01", "etc/init.d/S02",
            "etc/init.d/S20urandom", "etc/init.d/S40network", "etc/init.d/S50dropbear",
            "etc/init.d/S30dbus", "etc/init.d/S41dhcpcd", "etc/mdev.conf")
MIN_HASH_SIZE = 64

args = sys.argv[1:]
stock_dirs, use_stock, quiet, targets = [], True, False, []
while args:
    a = args.pop(0)
    if a == "-s" and args:
        stock_dirs.append(args.pop(0))
    elif a == "--no-stock":
        use_stock = False
    elif a == "-q":
        quiet = True
    elif a in ("-h", "--help"):
        print(USAGE); sys.exit(0)
    elif a.startswith("-"):
        print(USAGE, file=sys.stderr); sys.exit(2)
    else:
        targets.append(a)
if not targets:
    print(USAGE, file=sys.stderr); sys.exit(2)
if use_stock and not stock_dirs:
    for d in ("firmware/ff-repo/stock5x", "firmware/stock-3.1.0/unpacked"):
        if os.path.isdir(os.path.join(REPO, d)):
            stock_dirs.append(os.path.join(REPO, d))


def say(*a):
    if not quiet:
        print(*a)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def head(path, n):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def is_elf(path):
    return head(path, 4) == b"\x7fELF"


def is_uimage(path):
    return head(path, 4) == bytes.fromhex("27051956")


def has_vermagic(path):
    try:
        with open(path, "rb") as f:
            return b"vermagic=" in f.read(4 << 20)
    except OSError:
        return False


stock_hashes = {}
if use_stock:
    for d in stock_dirs:
        n = 0
        for root, _, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                if stat.S_ISREG(st.st_mode) and st.st_size >= MIN_HASH_SIZE:
                    # every path: stock keeps some upstream files twice
                    # (etc/profile and usr/prog/etc/profile), and the walk
                    # order differs between filesystems
                    stock_hashes.setdefault(sha256(p), []).append(
                        os.path.relpath(p, d))
                    n += 1
        say("reference: %s (%d files)" % (d, n))
    if not stock_dirs:
        say("reference: none (no stock firmware tree here): names and types only")

findings = []
upstream_same = [0]
tmp = tempfile.mkdtemp(prefix="check_vendor_free.")


def flag(where, why):
    findings.append((where, why))
    print("VENDOR: %s: %s" % (where, why))


def unpack(path, label):
    """Unpack an archive/image into a temp dir; return it or None."""
    h = head(path, 6)
    out = tempfile.mkdtemp(dir=tmp)
    try:
        if h[:4] == b"hsqs":
            if not UNSQ:
                print("check_vendor_free: no unsquashfs (build buildroot/output first)", file=sys.stderr)
                sys.exit(2)
            r = subprocess.run([UNSQ, "-n", "-f", "-d", out + "/r", path],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if r.returncode not in (0, 2):   # 2: could not create device nodes etc.
                print("check_vendor_free: unsquashfs %s failed: %s" % (label, r.stderr.decode()[-300:]),
                      file=sys.stderr)
                sys.exit(2)
            return out + "/r"
        if h[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(path) as z:
                z.extractall(out)
            return out
        if h[:6] in (b"070701", b"070702"):
            subprocess.run(["cpio", "-idm", "--quiet", "-D", out], stdin=open(path, "rb"), check=True)
            return out
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as t:
                members = [m for m in t.getmembers() if not (m.isdev() or m.ischr() or m.isblk() or m.isfifo())]
                t.extractall(out, members=members, filter="tar") if sys.version_info >= (3, 12) \
                    else t.extractall(out, members=members)
            return out
    except (OSError, zipfile.BadZipFile, tarfile.TarError, subprocess.CalledProcessError) as e:
        print("check_vendor_free: can't unpack %s: %s" % (label, e), file=sys.stderr)
        sys.exit(2)
    shutil.rmtree(out, ignore_errors=True)
    return None


ARCHIVE_NAMES = (".squashfs", ".zip", ".swu", ".tar")


def scan_tree(root, label):
    count = 0
    for dirpath, dirnames, files in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        for dn in list(dirnames):
            rd = rel_dir + dn
            if dn == "module_driver":
                flag("%s:/%s/" % (label, rd), "stock driver directory (module_driver)")
            if rd.endswith("usr/lib/ad5x/stock-tools"):
                flag("%s:/%s/" % (label, rd), "bundled stock board tools")
        for fn in files:
            p = os.path.join(dirpath, fn)
            rel = rel_dir + fn
            where = "%s:/%s" % (label, rel)
            st = os.lstat(p)
            if not stat.S_ISREG(st.st_mode):
                continue
            count += 1
            elf = is_elf(p)
            # Our own 6.6 and 7.3 kernels and chainload.ko (built from GPL
            # source in kernel-ingenic66/ and kernel-mainline/): no
            # kernel-type flags there; the hash
            # comparison with stock files below still applies.
            if rel.startswith(OWN_KERNEL_DIR):
                pass
            elif fn.endswith(".ko"):
                flag(where, "kernel module (.ko)")
            elif elf and has_vermagic(p):
                flag(where, "kernel module (ELF with vermagic)")
            if fn in VENDOR_NAMES_ANY:
                flag(where, "vendor file name")
            if fn in VENDOR_ELF_NAMES and elf:
                flag(where, "stock board tool binary")
            if fn.startswith(("xImage", "uImage")) and not rel.startswith(OWN_KERNEL_DIR):
                flag(where, "kernel image name")
            if is_uimage(p) and not rel.startswith(OWN_KERNEL_DIR):
                flag(where, "kernel image (uImage header)")
            if stock_hashes and st.st_size >= MIN_HASH_SIZE:
                s = sha256(p)
                if s in stock_hashes:
                    sps = sorted(stock_hashes[s])
                    sp = sps[0]
                    if not elf and any(x.startswith(UPSTREAM) for x in sps):
                        upstream_same[0] += 1
                    else:
                        flag(where, "identical to stock file %s" % sp)
            if fn.endswith(ARCHIVE_NAMES) or head(p, 4) in (b"hsqs", b"PK\x03\x04") \
                    or head(p, 6) in (b"070701", b"070702"):
                sub = unpack(p, where)
                if sub:
                    say("unpacked %s" % where)
                    count += scan_tree(sub, where)
    return count


total = 0
for t in targets:
    if os.path.isdir(t):
        total += scan_tree(t, t)
    elif os.path.isfile(t):
        sub = unpack(t, t)
        if sub is None:
            # a single plain file
            d = tempfile.mkdtemp(dir=tmp)
            shutil.copy(t, os.path.join(d, os.path.basename(t)))
            total += scan_tree(d, os.path.dirname(t) or ".")
        else:
            say("unpacked %s" % t)
            total += scan_tree(sub, t)
    else:
        print("check_vendor_free: no such file or directory: %s" % t, file=sys.stderr)
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(2)
shutil.rmtree(tmp, ignore_errors=True)
if findings:
    print("check_vendor_free: FOUND %d vendor file(s) in %d files checked" % (len(findings), total))
    sys.exit(1)
print("check_vendor_free: CLEAN (%d files checked%s)" % (
    total, ", hashes compared with %d stock files; %d identical upstream open-source files"
    % (len(stock_hashes), upstream_same[0]) if stock_hashes else ", no stock reference"))
PY
