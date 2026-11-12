// SPDX-License-Identifier: GPL-2.0
/*
 * Exec target for the fork + exec check of netusb-test.c: exits with
 * CODE. Built twice, as /t1 (CODE=11) and /t2 (CODE=22), so that two
 * programs with different code are loaded at the same addresses; a
 * stale instruction cache would run the wrong one.
 *
 *   mipsel-linux-gcc -static -O2 -DCODE=11 -o t1 exec-target.c
 *   mipsel-linux-gcc -static -O2 -DCODE=22 -o t2 exec-target.c
 */
#include <unistd.h>

int main(void)
{
	volatile int x = CODE;
	int i;

	for (i = 0; i < 1000; i++)
		x = (x * 3 + CODE) % 97;
	_exit(CODE);
}
