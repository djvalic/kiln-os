# Kiln OS: this board's RAM and the memory mode of this start (sourced;
# docs/memory.md, "Extended memory"). One parser for S04ad5x-memory (the
# keys in /run/ad5x-memory.conf), lib/bootloader.sh's bl_variant (main and
# recovery OS), S00ad5x-kernel and ad5x-memory.
#
# The boot loader that starts Kiln's kernels says both on the command line:
#   ad5x.ram=256|512             the board's RAM, whatever this start got
#   ad5x.memmode=standard|extended
# (S00ad5x-kernel from the stock SPL's line; Kiln's U-Boot from the SoC ID).
# Extended means the second bank, mem=SIZE@0x30000000, is on the command
# line; standard means it is not. Without the tokens (the stock 5.10, the
# recovery OS on it, an older boot loader) the bank and MemTotal tell.
# Where a token is given more than once the last counts, as for the
# kernel's own options. An older Kiln U-Boot (ad5x.uboot=1 without
# ad5x.memmode=) can't choose the mode at all: mem_mode_fixed.
# AD5X_CMDLINE and AD5X_MEMINFO (tests) replace /proc/cmdline and
# /proc/meminfo; AD5X_MEMORY_ROOT (S04's test root) is put in front of both
# otherwise.

MEM_BANK_RE='^mem=[0-9]+[kmg]?@0x0*30000000$'

mem_cmdline_file() { echo "${AD5X_CMDLINE:-${AD5X_MEMORY_ROOT:-}/proc/cmdline}"; }
mem_meminfo_file() { echo "${AD5X_MEMINFO:-${AD5X_MEMORY_ROOT:-}/proc/meminfo}"; }

# mem_words [LINE]: LINE's words (default: the command line), one a line
mem_words() {
	if [ $# -gt 0 ]; then printf '%s\n' "$1"; else cat "$(mem_cmdline_file)" 2>/dev/null; fi |
		tr ' \t' '\n\n' | sed '/^$/d'
}

# mem_bank_on [LINE]: LINE (default: the command line) has the second
# bank, a word mem=SIZE@0x30000000
mem_bank_on() {
	mem_words "$@" | grep -E -i -q "$MEM_BANK_RE"
}

# mem_drop_bank: stdin with every mem=SIZE@0x30000000 word taken out,
# everything else byte for byte (as S00ad5x-kernel's kiln_mem)
mem_drop_bank() {
	sed 's/^/ /; s/$/ /
		:a
		s/ [mM][eE][mM]=[0-9][0-9]*[kKmMgG]\{0,1\}@0[xX]0*30000000 / /
		ta
		s/^ //; s/ $//'
}

# mem_token NAME: the value of the last NAME= word on the command line
# (empty: none)
mem_token() {
	mem_words | sed -n "s/^$1=//p" | tail -n 1
}
# mem_token_values NAME: the different values NAME= has there, one a line
mem_token_values() {
	mem_words | sed -n "s/^$1=//p" | sort -u
}

# mem_total_kb: MemTotal in kB (empty when unreadable)
mem_total_kb() {
	mtk=$(awk '$1 == "MemTotal:" { print $2; exit }' "$(mem_meminfo_file)" 2>/dev/null)
	case "$mtk" in ''|*[!0-9]*) return 0 ;; esac
	echo "$mtk"
}

# mem_hw_mib: the board's RAM in MiB, 256 or 512: ad5x.ram= first, else
# 512 with the second bank on the command line, else 512 with MemTotal at
# least 400000 kB, else 256
mem_hw_mib() {
	case "$(mem_token 'ad5x\.ram')" in
	256) echo 256; return 0 ;;
	512) echo 512; return 0 ;;
	esac
	if mem_bank_on; then echo 512; return 0; fi
	mhk=$(mem_total_kb)
	if [ -n "$mhk" ] && [ "$mhk" -ge 400000 ]; then echo 512; else echo 256; fi
}

# mem_mode: this start's memory mode, standard or extended: ad5x.memmode=
# first, else extended with the second bank on the command line
mem_mode() {
	case "$(mem_token 'ad5x\.memmode')" in
	standard) echo standard; return 0 ;;
	extended) echo extended; return 0 ;;
	esac
	if mem_bank_on; then echo extended; else echo standard; fi
}

# mem_mode_fixed: the boot loader that started this can't choose the
# memory mode, so a restart doesn't change it; only a boot loader update
# does. That is an older Kiln U-Boot (before u-boot patch 0032, e.g. the
# rc3 opt-in one): it writes the command line itself (ad5x.uboot=1) and
# passes the board's mem= banks as they are, with no ad5x.memmode= word.
# Not fixed: today's U-Boot (ad5x.memmode= with ad5x.uboot=1), the stock
# chain (S00ad5x-kernel adds the words, no ad5x.uboot=1), Kiln's SPL alone
# and the stock 5.10 (no ad5x.uboot=1: a fallback or not Kiln's kernel)
mem_mode_fixed() {
	mem_words | grep -q -x 'ad5x\.uboot=1' || return 1
	case "$(mem_token 'ad5x\.memmode')" in standard|extended) return 1 ;; esac
	return 0
}

# mem_when [CLOCKFILE]: when, for a failure record: the clock when it is
# set (after 2026-01-01), else "after <the saved clock> (last saved
# clock)" from CLOCKFILE (ad5x-clock's seconds; the clock is still at 1970
# before S05ad5x-data restores it), else "date unknown"
mem_when() {
	mwn=$(date -u +%s 2>/dev/null)
	case "$mwn" in ''|*[!0-9]*) mwn=0 ;; esac
	if [ "$mwn" -ge 1767225600 ]; then
		date -u '+%Y-%m-%d %H:%M UTC'
		return 0
	fi
	mws=$(cat "${1:-/data/ad5x/clock}" 2>/dev/null)
	case "$mws" in ''|*[!0-9]*) mws=0 ;; esac
	if [ "$mws" -ge 1767225600 ]; then
		echo "after $(date -u -d "@$mws" '+%Y-%m-%d %H:%M') UTC (last saved clock)"
	else
		echo "date unknown"
	fi
}
