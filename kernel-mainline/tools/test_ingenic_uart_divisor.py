#!/usr/bin/env python3
"""Check the X2600 fractional baud rate code of 8250_ingenic on the host.

Compiles ingenic_uart_frame_error(), ingenic_uart_better() and
ingenic_uart_get_divisor() from the kernel tree into a small program and
compares their choices with an independent model of the same rules, for
every 113th baud rate up to clk / 16 at three crystal rates. Also checks
that no choice is off by more than 8% of a bit at the end of a 12-bit
frame, and that the rates the plain divisor hits exactly keep it.

  KSRC=~/workspace/linux-7.3.3 kernel-mainline/tools/test_ingenic_uart_divisor.py
"""
import os
import re
import subprocess
import sys
import tempfile

KSRC = os.environ.get("KSRC", os.path.expanduser("~/workspace/linux-7.3.3"))
DRIVER = os.path.join(KSRC, "drivers/tty/serial/8250/8250_ingenic.c")
MAX_FRAME_ERROR = 0.08  # bits

HEADER = r"""
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
typedef uint64_t u64;
#define U64_MAX UINT64_MAX
#define BIT(n) (1U << (n))
#define GENMASK(h, l) (((~0U) << (l)) & (~0U >> (31 - (h))))
#define max(a, b) ((a) > (b) ? (a) : (b))
#define min(a, b) ((a) < (b) ? (a) : (b))
#define clamp(v, lo, hi) min(max(v, lo), hi)
#define DIV_ROUND_CLOSEST(x, d) (((x) + (d) / 2) / (d))
#define hweight16(x) __builtin_popcount((x) & 0xffff)
struct uart_port { unsigned int uartclk; };
"""

MAIN = r"""
int main(int argc, char **argv)
{
	struct uart_port p = { .uartclk = atoi(argv[1]) };
	unsigned int baud, frac, div;

	while (scanf("%u", &baud) == 1) {
		div = ingenic_uart_get_divisor(&p, baud, &frac);
		printf("%u %u %u %u\n", baud, div,
		       frac >> INGENIC_FRAC_UMR_SHIFT, frac & INGENIC_FRAC_UACR_MASK);
	}
	return 0;
}
"""


def build(tmp):
    src = open(DRIVER).read()
    defs = re.findall(r"#define (UART_UMR\w*|UART_UACR\w*|INGENIC_FRAC\w*)\s+(.*)", src)
    start = src.index("/*\n * Pick the bit cycles")
    end = src.index("static void ingenic_uart_set_divisor")
    prog = (HEADER + "".join("#define %s %s\n" % d for d in defs)
            + src[start:end] + MAIN)
    c = os.path.join(tmp, "t.c")
    exe = os.path.join(tmp, "t")
    open(c, "w").write(prog)
    subprocess.run(["gcc", "-O2", "-Wall", "-Werror", "-o", exe, c], check=True)
    return exe


def frame(clk, baud, div, umr):
    """The model: cycles added per bit (UACR) and worst edge error."""
    uacr = total = worst = 0
    for i in range(12):
        total += umr
        if (i + 1) * clk * 2 - 2 * total * div * baud - div * baud > 0:
            total += 1
            uacr |= 1 << i
        worst = max(worst, abs((i + 1) * clk - total * div * baud))
    return uacr, worst


def model(clk, baud):
    if clk % (16 * baud) == 0 and clk // (16 * baud) <= 0xFFFF:
        return clk // (16 * baud), 16, 0
    cands = []
    for umr in range(4, 32):
        base = clk // (baud * umr)
        for div in range(max(base, 3) - 2, base + 3):
            if div > 0xFFFF or clk // (baud * div) != umr:
                continue
            uacr, worst = frame(clk, baud, div, umr)
            cands.append((worst, div, umr, uacr))
    if not cands:
        return max(1, min(0xFFFF, (clk + 8 * baud) // (16 * baud))), 16, 0
    least = min(c[0] for c in cands)
    ok = [c for c in cands if c[0] <= least + clk // 100]
    best = min(ok, key=lambda c: (bin(c[3]).count("1"), c[0], abs(c[2] - 16), -c[2]))
    return best[1], best[2], best[3]


def frame_error_bits(clk, baud, div, umr, uacr):
    t = worst = 0
    for i in range(12):
        t += umr + ((uacr >> i) & 1)
        worst = max(worst, abs((i + 1) / baud - t * div / clk) * baud)
    return worst


def main():
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        exe = build(tmp)
        for clk in (24_000_000, 26_000_000, 48_000_000):
            rates = sorted(set(list(range(300, clk // 16 + 1, 113))
                               + [9600, 115200, 230400, 250000, 460800, 1_000_000]))
            out = subprocess.run([exe, str(clk)], input="\n".join(map(str, rates)),
                                 capture_output=True, text=True, check=True).stdout
            worst = 0.0
            for line in out.splitlines():
                baud, div, umr, uacr = map(int, line.split())
                if (div, umr, uacr) != model(clk, baud):
                    fails += 1
                    if fails <= 10:
                        print(f"FAIL clk {clk} baud {baud}: driver {div}/{umr}/{uacr:#x}, "
                              f"model {model(clk, baud)}")
                err = frame_error_bits(clk, baud, div, umr, uacr)
                if err > MAX_FRAME_ERROR:
                    fails += 1
                    print(f"FAIL clk {clk} baud {baud}: {err:.3f} bit off")
                if clk % (16 * baud) == 0 and (umr, uacr) != (16, 0):
                    fails += 1
                    print(f"FAIL clk {clk} baud {baud}: exact rate not kept")
                worst = max(worst, err)
            print(f"clk {clk}: {len(rates)} rates, worst {worst:.4f} bit")
    print("all OK" if not fails else f"{fails} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
