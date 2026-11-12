# Kiln OS: NetworkManager connections from the configuration of the
# releases before it, made once (docs/networkmanager.md). Sourced by
# S44ad5x-network, in the main OS and the recovery OS: busybox sh and awk
# only (the recovery OS has no Python).
#
#   nm_import            the first start: Ethernet from network.conf, Wi-Fi
#                        from wpa_supplicant.conf (or stock's networks),
#                        then the marker; never again after that
#
# The old files are read, never changed or removed: an older image (the
# other slot) still runs from them.

NM_DATA=/data/ad5x/NetworkManager
NM_CONN=$NM_DATA/system-connections
NM_MARK=$NM_DATA/imported
NM_NETCONF=/data/ad5x/network.conf
NM_WPACONF=/data/ad5x/wpa_supplicant.conf
NM_USERSHARE=/tmp/ad5x-usershare-net

nm_log() {
	echo "ad5x-network: $*"
	[ -n "$NM_LOG" ] && echo "$(date '+%F %T') $*" >> "$NM_LOG" 2>/dev/null
}

# Copy what the import needs from stock's usershare partition (read-only):
# the MAC stock assigns (/MAC) and the Wi-Fi networks joined on stock's
# screen (/wifi/wpa_supplicant.conf).
nm_usershare() {
	rm -rf $NM_USERSHARE
	mkdir -p $NM_USERSHARE
	for u in /sys/class/block/*/uevent; do
		grep -qx "PARTNAME=usershare" "$u" 2>/dev/null || continue
		dev=/dev/$(sed -n 's/^DEVNAME=//p' "$u")
		mkdir -p $NM_USERSHARE/mnt
		if mount -t ext4 -o ro "$dev" $NM_USERSHARE/mnt 2>/dev/null; then
			cp $NM_USERSHARE/mnt/MAC $NM_USERSHARE/MAC 2>/dev/null
			cp $NM_USERSHARE/mnt/wifi/wpa_supplicant.conf \
				$NM_USERSHARE/wpa_supplicant.conf 2>/dev/null
			umount $NM_USERSHARE/mnt
		fi
		rmdir $NM_USERSHARE/mnt 2>/dev/null
	done
}

nm_valid_cidr() {
	echo "$1" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$'
}

nm_write() {	# FILE: stdin to a keyfile NetworkManager accepts (root, 600)
	umask 077
	cat > "$1.tmp" && chmod 600 "$1.tmp" && mv "$1.tmp" "$1"
}

# Ethernet: DHCP, or the static address in network.conf (as S41 had it);
# stock's MAC on every kernel.
nm_import_ethernet() {
	MODE=dhcp ADDRESS= GATEWAY= DNS= IFACE=
	[ -f $NM_NETCONF ] && . $NM_NETCONF
	iface=${IFACE:-eth0}
	mac=$(tr -d ' \r\n' < $NM_USERSHARE/MAC 2>/dev/null)
	echo "$mac" | grep -Eqi '^([0-9a-f]{2}:){5}[0-9a-f]{2}$' || mac=
	if [ "$MODE" = static ] && ! nm_valid_cidr "$ADDRESS"; then
		nm_log "invalid static setup in $NM_NETCONF (ADDRESS='$ADDRESS'): DHCP"
		MODE=dhcp
	fi
	{
		echo "[connection]"
		echo "id=Ethernet"
		echo "uuid=$(cat /proc/sys/kernel/random/uuid)"
		echo "type=ethernet"
		echo "interface-name=$iface"
		echo "autoconnect-priority=10"
		echo
		echo "[ethernet]"
		[ -n "$mac" ] && echo "cloned-mac-address=$mac"
		echo
		echo "[ipv4]"
		if [ "$MODE" = static ]; then
			echo "method=manual"
			echo "address1=$ADDRESS${GATEWAY:+,$GATEWAY}"
			[ -n "$DNS" ] && echo "dns=$(echo $DNS | tr ' ' ';');"
		else
			echo "method=auto"
		fi
		echo
		echo "[ipv6]"
		echo "method=auto"
	} | nm_write $NM_CONN/ethernet.nmconnection
	nm_log "Ethernet ($iface): $MODE${mac:+, stock MAC $mac}"
}

# A keyfile's string value: backslash and leading/trailing spaces escaped
# (GKeyFile's rules).
nm_kf_str() {
	printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/^ /\\s/' -e 's/ $/\\s/'
}

# An SSID as the byte list a keyfile takes ("76;97;117;120;"): any byte
# allowed, UTF-8 included. $1 the SSID, $2 1 if it was written in hex.
nm_ssid_bytes() {
	if [ "$2" = 1 ]; then
		for b in $(echo "$1" | sed 's/../& /g'); do printf '%d;' "0x$b"; done
	else
		printf '%s' "$1" | od -An -v -tu1 | tr -s ' \n' '  ' |
			sed -e 's/^ *//' -e 's/ *$//' -e 's/ /;/g' -e 's/$/;/'
	fi
}

# Wi-Fi: one keyfile per network block of a wpa_supplicant.conf. hidden=true
# for each (stock never marks hidden networks, so S42 probed for every one
# with scan_ssid=1), priority and disabled kept. Open and WPA/WPA2/WPA3
# personal; WEP and enterprise networks are left out (counted). awk only
# splits the blocks into records; the bytes are counted in the shell (busybox
# awk works in characters, not bytes). Prints "imported skipped".
nm_import_wifi() {	# CONF
	us=$(printf '\037')
	n=0 skipped=0
	awk -v us="$us" '
	function val(v) {
		if (v ~ /^"/) { sub(/^"/, "", v); sub(/"[^"]*$/, "", v); return v }
		sub(/[ \t].*$/, "", v)
		return v
	}
	/^[ \t]*network[ \t]*=[ \t]*\{/ { inb = 1; split("", k); split("", q); next }
	inb && /^[ \t]*\}/ {
		inb = 0
		if (!("ssid" in k)) next
		other = ("wep_key0" in k) || k["key_mgmt"] ~ /IEEE8021X|WPA-EAP/
		print q["ssid"] us k["ssid"] us k["key_mgmt"] us ("psk" in k) us k["psk"] us k["priority"] us k["disabled"] us other
		next
	}
	inb {
		line = $0; sub(/^[ \t]+/, "", line)
		if (line ~ /^#/ || line !~ /=/) next
		key = substr(line, 1, index(line, "=") - 1); v = substr(line, index(line, "=") + 1)
		q[key] = (v ~ /^"/) ? 1 : 0; k[key] = val(v)
	}' "$1" > $NM_USERSHARE.wifi
	while IFS="$us" read -r quoted ssid keymgmt haspsk psk prio disabled other; do
		if [ "$other" = 1 ]; then skipped=$((skipped + 1)); continue; fi
		n=$((n + 1))
		if [ "$quoted" = 1 ]; then
			name=$ssid bytes=$(nm_ssid_bytes "$ssid" 0)
		else
			name="Wi-Fi $n" bytes=$(nm_ssid_bytes "$ssid" 1)
		fi
		{
			echo "[connection]"
			echo "id=$(nm_kf_str "$name")"
			echo "uuid=$(cat /proc/sys/kernel/random/uuid)"
			echo "type=wifi"
			[ -n "$prio" ] && echo "autoconnect-priority=$prio"
			[ "$disabled" = 1 ] && echo "autoconnect=false"
			echo
			echo "[wifi]"
			echo "mode=infrastructure"
			echo "ssid=$bytes"
			echo "hidden=true"
			if [ "$keymgmt" != NONE ] && [ "$haspsk" = 1 ]; then
				echo
				echo "[wifi-security]"
				[ "$keymgmt" = SAE ] && echo "key-mgmt=sae" || echo "key-mgmt=wpa-psk"
				echo "psk=$(nm_kf_str "$psk")"
			fi
			echo
			echo "[ipv4]"
			echo "method=auto"
			echo
			echo "[ipv6]"
			echo "method=auto"
		} | nm_write "$NM_CONN/wifi-$n.nmconnection"
	done < $NM_USERSHARE.wifi
	rm -f $NM_USERSHARE.wifi
	echo "$n $skipped"
}

nm_import() {
	mkdir -p $NM_CONN
	chmod 700 $NM_CONN
	nm_usershare
	nm_import_ethernet
	src=
	if [ -f $NM_WPACONF ]; then
		src=$NM_WPACONF
	elif [ -f $NM_USERSHARE/wpa_supplicant.conf ]; then
		src=$NM_USERSHARE/wpa_supplicant.conf
	fi
	if [ -n "$src" ]; then
		set -- $(nm_import_wifi $src)
		chmod 600 $NM_CONN/wifi-*.nmconnection 2>/dev/null
		nm_log "Wi-Fi: $1 network(s) from $src${2:+$([ "$2" != 0 ] && echo ", $2 left out (WEP/enterprise)")}"
	else
		nm_log "Wi-Fi: no saved networks to import"
	fi
	rm -rf $NM_USERSHARE
	date '+%F %T' > $NM_MARK
}
