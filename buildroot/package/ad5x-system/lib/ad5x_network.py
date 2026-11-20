#!/usr/bin/env python3
# Kiln OS: NetworkManager's connections, made from the files Kiln OS has
# always read, and the Wi-Fi networks NetworkManager saves, written back
# there (docs/network.md). Main OS only: the recovery OS keeps
# wpa_supplicant and udhcpc (S41ad5x-eth, S42ad5x-wifi).
#
# /data/ad5x/network.conf and /data/ad5x/wpa_supplicant.conf stay the
# saved setup (docs/data-layout.md, docs/stability.md): the keyfiles are
# made new from them at every start, in /run (S40ad5x-network), so an edit
# there takes effect at the next start as before, and an older release or
# the recovery OS reads the same networks.
#
#   ad5x_network.py generate --out DIR --manifest FILE --conf FILE
#                            [--stock FILE] [--mac FILE] [--no-wifi]
#       Ethernet from network.conf (its values in AD5X_NET_MODE, _ADDRESS,
#       _GATEWAY, _DNS, _IFACE, as S40ad5x-network's shell read the file,
#       the same way lib/network.sh does), with stock's MAC from --mac.
#       Wi-Fi: one keyfile per network block of --conf; a --conf that
#       doesn't exist is made first from stock's networks (--stock), as
#       S42ad5x-wifi does. The manifest lists the Wi-Fi networks made.
#   ad5x_network.py writeback --dir DIR --manifest FILE --conf FILE
#       The Wi-Fi keyfiles in DIR (NetworkManager's, after the screen
#       joined or changed a network) back into --conf: a network block
#       that still matches is kept as written, one whose password,
#       priority or autoconnect changed gets those lines changed, a
#       network made at the start whose keyfile is gone is taken out, and
#       a new one is added. Blocks this can't turn into a keyfile (WEP,
#       enterprise, unreadable) and every other line stay as they are.
#       Nothing is written when nothing changed.
#
# Lines starting "ad5x-network:" on stdout are for network.log. Exit 0 on
# success, 1 on an error (S40ad5x-network then takes the old path).
#
# Ported from PR #53 by jolting (Hunter Laux): the keyfile layout (stock's
# MAC as cloned-mac-address, hidden=true for every saved network, priority
# and disabled kept, WEP and enterprise left out, SSIDs as byte lists,
# GKeyFile escapes) follows his nm-import.sh. Made to run at every start
# and to write back, in Python (byte-exact SSIDs; the main OS has Python).

import hashlib
import json
import os
import re
import sys

HEADER = ("# Wi-Fi networks (HelixScreen saves here; see S42ad5x-wifi)\n"
          "ctrl_interface=/var/run/wpa_supplicant\n"
          "update_config=1\n")
ETH_FILE = "kiln-ethernet.nmconnection"
WIFI_PREFIX = "kiln-wifi-"
# wpa_supplicant key_mgmt values a WPA/WPA2/WPA3 personal network uses
PSK_KM = {"WPA-PSK", "WPA-PSK-SHA256", "FT-PSK"}
SAE_KM = {"SAE", "FT-SAE", "SAE-EXT-KEY"}
# Infinite DHCP wait on Ethernet, as udhcpc -b (NetworkManager's "infinity")
DHCP_FOREVER = "2147483647"


def say(msg):
    print("ad5x-network: " + msg, flush=True)


# --- wpa_supplicant.conf --------------------------------------------------

def _value(raw):
    """A value as wpa_supplicant's config reader takes it: a quoted string
    up to its last quote (quoted=True), else the text before a #."""
    raw = raw.strip()
    if raw.startswith('"'):
        end = raw.rfind('"')
        if end > 0:
            return raw[1:end], True
        return raw[1:], True
    return raw.split("#", 1)[0].strip(), False


def parse_conf(text):
    """wpa_supplicant.conf as items in file order: ("top", line) for lines
    outside network blocks, ("block", lines, fields) for a block (lines
    with their newlines, fields {key: (value, quoted)})."""
    items, cur, fields = [], None, None
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if cur is None:
            if re.match(r"network\s*=\s*\{", s):
                cur, fields = [line], {}
            else:
                items.append(("top", line))
            continue
        cur.append(line)
        if s == "}":
            items.append(("block", cur, fields))
            cur = None
        elif s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            fields[k.strip()] = _value(v)
    if cur is not None:		# no closing brace: kept as it is
        items.extend(("top", line) for line in cur)
    return items


def _ssid_bytes(val, quoted):
    if quoted:
        return val.encode("utf-8", "surrogateescape")
    if re.fullmatch(r"(?:[0-9a-fA-F]{2})+", val or ""):
        return bytes.fromhex(val)
    return None


def block_net(fields):
    """The network a block holds as {ssid, km, psk, priority, autoconnect},
    or (None, why) for one this doesn't turn into a keyfile."""
    if "ssid" not in fields:
        return None, "no ssid"
    ssid = _ssid_bytes(*fields["ssid"])
    if not ssid or len(ssid) > 32:
        return None, "unreadable ssid"
    if fields.get("mode", ("0", False))[0] not in ("", "0"):
        return None, "not a client network"
    if fields.get("disabled", ("0", False))[0] not in ("", "0", "1"):
        return None, "P2P group"
    if any(k in fields for k in ("wep_key0", "wep_key1", "wep_key2",
                                 "wep_key3", "eap", "identity")):
        return None, "WEP/enterprise"
    km = fields.get("key_mgmt", ("WPA-PSK WPA-EAP", False))[0].split()
    psk = fields.get("psk") or fields.get("sae_password")
    if km == ["NONE"]:
        kind, psk = "none", None
    elif set(km) & (PSK_KM | SAE_KM):
        if not psk:
            return None, "no password"
        kind = "wpa-psk" if set(km) & PSK_KM else "sae"
        if "psk" not in fields:		# sae_password only
            kind = "sae"
        val, quoted = psk
        if quoted:
            psk = val
        elif re.fullmatch(r"[0-9a-fA-F]{64}", val):
            psk = val.lower()
        else:
            return None, "unreadable password"
    else:
        return None, "WEP/enterprise"
    try:
        prio = int(fields.get("priority", ("0", False))[0])
    except ValueError:
        prio = 0
    return {"ssid": ssid, "km": kind, "psk": psk,
            "priority": max(-999, min(999, prio)),
            "autoconnect": fields.get("disabled", ("0", False))[0] != "1"}, ""


def read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "surrogateescape")


def write_private(path, text):
    """text to path, 0600 from the start (issue #31), through a temp file."""
    tmp = path + ".tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(text.encode("utf-8", "surrogateescape"))
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.rename(tmp, path)


# --- keyfiles ---------------------------------------------------------------

def kf_str(s):
    """A GKeyFile string value: backslash, tab, newline, CR and spaces at
    the ends escaped."""
    s = (s.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
         .replace("\r", "\\r"))
    if s.startswith(" "):
        s = "\\s" + s[1:]
    if s.endswith(" "):
        s = s[:-1] + "\\s"
    return s


def kf_unstr(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append({"s": " ", "n": "\n", "t": "\t", "r": "\r",
                        "\\": "\\", ";": ";"}.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_keyfile(text):
    """{group: {key: raw value}}. As GKeyFile reads it: the spaces after
    "=" go, a value's trailing spaces stay (NetworkManager writes an SSID
    or password that ends in a space that way)."""
    groups, g = {}, None
    for line in text.splitlines():
        s = line.lstrip()
        if not s.strip() or s.startswith("#"):
            continue
        if s.startswith("[") and s.rstrip().endswith("]"):
            g = groups.setdefault(s.rstrip()[1:-1], {})
        elif g is not None and "=" in s:
            k, v = s.split("=", 1)
            g[k.strip()] = v.lstrip(" \t")
    return groups


def kf_ssid(v):
    """[wifi] ssid as NetworkManager writes it: a byte list ("72;105;")
    or a string."""
    if re.fullmatch(r"(?:\d{1,3};)+\d{0,3}", v):
        nums = [int(n) for n in v.split(";") if n != ""]
        if all(n < 256 for n in nums):
            return bytes(nums)
    return kf_unstr(v).encode("utf-8", "surrogateescape")


def keyfile_net(groups):
    """The Wi-Fi network of a keyfile as block_net gives it, and its SSID;
    (None, SSID) for one wpa_supplicant.conf can't hold, (None, None) for
    no Wi-Fi network at all."""
    c, w = groups.get("connection", {}), groups.get("wifi") or groups.get("802-11-wireless")
    if c.get("type") not in ("wifi", "802-11-wireless") or w is None or "ssid" not in w:
        return None, None
    ssid = kf_ssid(w["ssid"])
    if w.get("mode", "infrastructure") != "infrastructure":
        return None, ssid
    sec = groups.get("wifi-security") or groups.get("802-11-wireless-security")
    psk = None
    if not sec:
        km = "none"
    else:
        km = sec.get("key-mgmt", "")
        if km not in ("wpa-psk", "sae"):
            return None, ssid
        if "psk" not in sec:		# kept by an agent, not in the file
            return None, ssid
        psk = kf_unstr(sec["psk"])
        if re.fullmatch(r"[0-9a-fA-F]{64}", psk):
            psk = psk.lower()
    try:
        prio = int(c.get("autoconnect-priority", "0"))
    except ValueError:
        prio = 0
    return {"ssid": ssid, "km": km, "psk": psk, "priority": prio,
            "autoconnect": c.get("autoconnect", "true").lower() not in ("false", "0", "no")}, ssid


def uuid_for(name):
    """A fixed UUID per connection (name-based, MD5): the same network gets
    the same UUID at every start, so its DHCP lease file is found again."""
    h = bytearray(hashlib.md5(b"kiln-os-network:" + name).digest())
    h[6] = (h[6] & 0x0F) | 0x30
    h[8] = (h[8] & 0x3F) | 0x80
    x = h.hex()
    return "%s-%s-%s-%s-%s" % (x[:8], x[8:12], x[12:16], x[16:20], x[20:])


def conn_name(ssid, n):
    try:
        name = ssid.decode("utf-8")
        if name.isprintable() and name.strip():
            return name
    except UnicodeDecodeError:
        pass
    return "Wi-Fi %d" % n


def wifi_keyfile(net, n, key):
    out = ["[connection]",
           "id=" + kf_str(conn_name(net["ssid"], n)),
           "uuid=" + uuid_for(b"wifi:" + key),
           "type=wifi",
           "autoconnect-retries=0"]
    if net["priority"]:
        out.append("autoconnect-priority=%d" % net["priority"])
    if not net["autoconnect"]:
        out.append("autoconnect=false")
    # hidden: stock saves no scan_ssid, so S42ad5x-wifi probes for every
    # saved network (a hidden one is found only when asked for by name)
    out += ["", "[wifi]", "mode=infrastructure",
            "ssid=" + "".join("%d;" % b for b in net["ssid"]),
            "hidden=true"]
    if net["km"] != "none":
        out += ["", "[wifi-security]", "key-mgmt=" + net["km"],
                "psk=" + kf_str(net["psk"])]
    out += ["", "[ipv4]", "method=auto", "", "[ipv6]", "method=auto", ""]
    return "\n".join(out)


IPV4 = r"(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)"


def ethernet_keyfile(env, mac):
    mode = env.get("AD5X_NET_MODE", "") or "dhcp"
    addr = env.get("AD5X_NET_ADDRESS", "")
    gw = env.get("AD5X_NET_GATEWAY", "")
    dns = env.get("AD5X_NET_DNS", "").split()
    iface = env.get("AD5X_NET_IFACE", "") or "eth0"
    if mode == "static" and not re.fullmatch(IPV4 + r"/(?:[0-9]|[12][0-9]|3[0-2])", addr):
        say("invalid static setup in /data/ad5x/network.conf (ADDRESS='%s'), using DHCP" % addr)
        mode = "dhcp"
    out = ["[connection]", "id=Ethernet", "uuid=" + uuid_for(b"ethernet"),
           "type=ethernet", "interface-name=" + iface, "autoconnect-priority=10",
           "autoconnect-retries=0", ""]
    out.append("[ethernet]")
    # stock's MAC on eth0, as S41ad5x-eth sets it
    if mac and iface == "eth0":
        out.append("cloned-mac-address=" + mac)
    out += ["", "[ipv4]"]
    if mode == "static":
        if gw and not re.fullmatch(IPV4, gw):
            say("network.conf: GATEWAY='%s' isn't an address, left out" % gw)
            gw = ""
        good = [d for d in dns if re.fullmatch(IPV4, d)]
        if len(good) != len(dns):
            say("network.conf: DNS entries that aren't addresses left out")
        out += ["method=manual", "address1=" + addr + ("," + gw if gw else "")]
        if good:
            out.append("dns=" + "".join(d + ";" for d in good))
        say("Ethernet (%s): static %s%s" % (iface, addr, " via " + gw if gw else ""))
    else:
        # udhcpc -b went on asking for ever: so does this
        out += ["method=auto", "dhcp-timeout=" + DHCP_FOREVER]
        say("Ethernet (%s): DHCP%s" % (iface, ", stock MAC" if mac and iface == "eth0" else ""))
    out += ["", "[ipv6]", "method=auto", ""]
    return "\n".join(out)


def read_mac(path):
    try:
        with open(path) as f:
            mac = f.read().strip()
    except OSError:
        return ""
    return mac.lower() if re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac) else ""


def stock_conf(path):
    """S42ad5x-wifi's first start: stock's saved networks only (from the
    first network block on), under our own header."""
    try:
        lines = read_text(path).splitlines(keepends=True)
    except OSError:
        return None
    for i, line in enumerate(lines):
        if re.match(r"\s*network\s*=", line):
            nets = "".join(lines[i:])
            return HEADER + "\n" + nets + ("" if nets.endswith("\n") else "\n")
    return None


def generate(args):
    out, conf = args["--out"], args["--conf"]
    os.makedirs(out, mode=0o700, exist_ok=True)
    mac = read_mac(args.get("--mac", ""))
    write_private(os.path.join(out, ETH_FILE), ethernet_keyfile(os.environ, mac))
    made = []
    if "--no-wifi" in args:
        say("Wi-Fi off (remove /data/ad5x/wifi.disable to use it)")
    else:
        if not os.path.exists(conf):
            text = stock_conf(args["--stock"]) if args.get("--stock") else None
            write_private(conf, text or HEADER)
            say("new %s%s" % (conf, " with stock's saved networks" if text else " (no networks yet)"))
        try:
            items = parse_conf(read_text(conf))
        except OSError as e:
            say("can't read %s: %s" % (conf, e.strerror))
            items = []
        n = skipped = auto = 0
        seen = {}
        for it in items:
            if it[0] != "block":
                continue
            net, why = block_net(it[2])
            if net is None:
                skipped += 1
                continue
            n += 1
            auto += net["autoconnect"]
            dup = seen.get(net["ssid"], 0)
            seen[net["ssid"]] = dup + 1
            key = net["ssid"] + (b"#%d" % dup if dup else b"")
            name = "%s%d.nmconnection" % (WIFI_PREFIX, n)
            write_private(os.path.join(out, name), wifi_keyfile(net, n, key))
            made.append({"file": name, "ssid": net["ssid"].hex()})
        # disabled=1 (stock saves its networks that way until one is
        # joined): saved, but not joined at the start
        say("Wi-Fi: %d network(s) from %s, %d to join automatically%s" % (
            n, conf, auto,
            ", %d left out (WEP, enterprise or unreadable)" % skipped if skipped else ""))
    write_private(args["--manifest"], json.dumps({"wifi": made}) + "\n")
    return 0


# --- write back -------------------------------------------------------------

def conf_ssid(ssid):
    """The ssid line wpa_supplicant itself writes: quoted when every byte
    is printable ASCII, else hex (wpa_config_write_string)."""
    if all(32 <= b < 127 for b in ssid):
        return '"%s"' % ssid.decode("ascii")
    return ssid.hex()


def conf_psk(net):
    p = net["psk"]
    return p if re.fullmatch(r"[0-9a-f]{64}", p) else '"%s"' % p


def new_block(net):
    lines = ["network={", "\tssid=" + conf_ssid(net["ssid"]), "\tscan_ssid=1"]
    if net["km"] == "none":
        lines.append("\tkey_mgmt=NONE")
    else:
        lines += ["\tpsk=" + conf_psk(net),
                  "\tkey_mgmt=" + ("SAE" if net["km"] == "sae" else "WPA-PSK")]
    if net["priority"]:
        lines.append("\tpriority=%d" % net["priority"])
    if not net["autoconnect"]:
        lines.append("\tdisabled=1")
    return [l + "\n" for l in lines + ["}"]]


def changed_block(lines, old, new):
    """A block with its password, key_mgmt, priority and disabled lines set
    to the keyfile's; its other lines (bssid, comments...) kept."""
    want = {}
    if new["km"] != old["km"] or new["psk"] != old["psk"]:
        if new["km"] == "none":
            want["psk"] = None
            want["sae_password"] = None
            want["key_mgmt"] = "NONE"
        else:
            want["psk"] = conf_psk(new)
            want["sae_password"] = None
            want["key_mgmt"] = "SAE" if new["km"] == "sae" else "WPA-PSK"
    if new["priority"] != old["priority"]:
        want["priority"] = "%d" % new["priority"] if new["priority"] else None
    if new["autoconnect"] != old["autoconnect"]:
        want["disabled"] = None if new["autoconnect"] else "1"
    out, done = [], set()
    for line in lines[:-1]:
        s = line.strip()
        k = s.split("=", 1)[0].strip() if "=" in s and not s.startswith("#") else None
        if k in want:
            if want[k] is not None and k not in done:
                indent = line[:len(line) - len(line.lstrip())] or "\t"
                out.append("%s%s=%s\n" % (indent, k, want[k]))
            done.add(k)
            continue
        out.append(line)
    for k, v in want.items():
        if v is not None and k not in done:
            out.append("\t%s=%s\n" % (k, v))
    out.append(lines[-1])
    return out


def keyfile_nets(d):
    """{ssid: net} of the Wi-Fi keyfiles in d (the newest file wins when
    two hold the same SSID), the SSIDs of Wi-Fi keyfiles this can't write
    into wpa_supplicant.conf (their blocks are never taken out), and the
    number of those."""
    nets, other, bad = {}, set(), 0
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return None, other, 0
    for name in names:
        if not name.endswith(".nmconnection"):
            continue
        p = os.path.join(d, name)
        try:
            groups = parse_keyfile(read_text(p))
            mtime = os.stat(p).st_mtime
        except OSError:
            bad += 1
            continue
        net, ssid = keyfile_net(groups)
        if net is None:
            if ssid is not None:
                other.add(ssid)
                bad += 1
            continue
        old = nets.get(ssid)
        if old is None or mtime >= old[0]:
            nets[ssid] = (mtime, net)
    return {k: v[1] for k, v in nets.items()}, other, bad


def writeback(args):
    conf = args["--conf"]
    nets, other, bad = keyfile_nets(args["--dir"])
    if nets is None:
        say("writeback: no %s" % args["--dir"])
        return 1
    try:
        manifest = json.loads(read_text(args["--manifest"]))["wifi"]
        made = {bytes.fromhex(m["ssid"]) for m in manifest}
    except (OSError, ValueError, KeyError, TypeError):
        say("writeback: no manifest, nothing taken out")
        manifest, made = None, set()
    try:
        old_text = read_text(conf)
    except FileNotFoundError:
        old_text = HEADER
    items = parse_conf(old_text)
    out, used, notes = [], set(), []
    for it in items:
        if it[0] == "top":
            out.append(it[1])
            continue
        lines, fields = it[1], it[2]
        net, _ = block_net(fields)
        if net is None:		# WEP, enterprise, unreadable: as it is
            out.extend(lines)
            continue
        ssid = net["ssid"]
        new = nets.get(ssid)
        # Gone: made at this start, and no keyfile for it at all now
        # (forgotten on the screen or with nmcli)
        gone = new is None and ssid in made and ssid not in other
        if gone:
            if out and not out[-1].strip():	# its blank line too
                out.pop()
            notes.append("removed")
            continue
        if new is None or ssid in used:
            # never in NetworkManager, only in a keyfile this can't
            # read, or a second block for the same network: as it is
            out.extend(lines)
            continue
        used.add(ssid)
        if all(new[k] == net[k] for k in ("km", "psk", "priority", "autoconnect")):
            out.extend(lines)
        else:
            out.extend(changed_block(lines, net, new))
            notes.append("changed")
    added = []
    for ssid, new in nets.items():
        if ssid not in used:
            if out and out[-1].strip():
                out.append("\n")
            out.extend(new_block(new))
            notes.append("added")
            added.append(ssid)
    text = "".join(out)
    if text == old_text:
        return 0
    write_private(conf, text)
    # A network added here was made at this start too: forgotten (or
    # renamed) later in the same start, it is taken out again
    if added and manifest is not None:
        manifest += [{"file": None, "ssid": x.hex()} for x in added if x not in made]
        write_private(args["--manifest"], json.dumps({"wifi": manifest}) + "\n")
    say("Wi-Fi networks saved to %s: %s" % (conf, ", ".join(
        "%d %s" % (notes.count(k), k) for k in ("added", "changed", "removed") if k in notes)
        or "rewritten"))
    if bad:
        say("writeback: %d keyfile(s) left out (no password in the file, or not WPA personal)" % bad)
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] not in ("generate", "writeback"):
        print("usage: ad5x_network.py generate|writeback ... (see the file's head)",
              file=sys.stderr)
        return 2
    args, i = {}, 2
    while i < len(argv):
        a = argv[i]
        if a == "--no-wifi":
            args[a] = True
            i += 1
        elif a.startswith("--") and i + 1 < len(argv):
            args[a] = argv[i + 1]
            i += 2
        else:
            print("ad5x_network.py: bad argument %s" % a, file=sys.stderr)
            return 2
    need = {"generate": ("--out", "--manifest", "--conf"),
            "writeback": ("--dir", "--manifest", "--conf")}[argv[1]]
    for k in need:
        if k not in args:
            print("ad5x_network.py: %s needed" % k, file=sys.stderr)
            return 2
    try:
        return (generate if argv[1] == "generate" else writeback)(args)
    except OSError as e:
        say("%s failed: %s" % (argv[1], e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
