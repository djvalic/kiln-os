// SPDX-License-Identifier: GPL-2.0+
/*
 * Host driver for the start-up hand-offs (mach/ad5x_start.h) and U-Boot
 * proper's stop key (board/flashforge/ad5x/stopkey.h), for
 * test_ad5x_start.py. One command per line on stdin, one answer line each
 * (flushed, so the test can talk to it):
 *
 *   plan V                      attempt skip_uboot forced slot_b stop
 *   value A SKIP F SB PHASE S   the CPSPR value for that plan, phase, slot
 *   entry V                     what U-Boot proper writes as it starts
 *   gaveup V                    what U-Boot proper resets with, no key
 *   ubkernel WHAT TRIES         what it leaves as it jumps to a kernel
 *   stopkey HEX                 1-based index of the byte completing the
 *                               stop key in the bytes HEX, 0 if none
 *   tries                       AD5X_START_TRIES
 *
 * Numbers in C syntax (0x...).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ad5x_start.h"
#include "stopkey.h"

static unsigned int num(const char *s)
{
	return (unsigned int)strtoul(s, NULL, 0);
}

int main(void)
{
	char line[4096], *a[8];
	struct ad5x_plan p;
	unsigned int st, i;
	int n;

	while (fgets(line, sizeof(line), stdin)) {
		n = 0;
		for (a[n] = strtok(line, " \t\n"); a[n] && n < 7;
		     a[++n] = strtok(NULL, " \t\n"))
			;
		if (!n)
			continue;
		if (!strcmp(a[0], "plan") && n == 2) {
			ad5x_start_plan(num(a[1]), &p);
			printf("%u %d %d %d %d\n", p.attempt, p.skip_uboot,
			       p.forced, p.slot_b, p.stop);
		} else if (!strcmp(a[0], "value") && n == 7) {
			p.attempt = num(a[1]);
			p.skip_uboot = num(a[2]);
			p.forced = num(a[3]);
			p.slot_b = num(a[4]);
			p.stop = 0;
			printf("0x%x\n", ad5x_start_value(&p,
				(enum ad5x_phase)num(a[5]), num(a[6])));
		} else if (!strcmp(a[0], "entry") && n == 2) {
			printf("0x%x\n", ad5x_start_uboot_entry(num(a[1])));
		} else if (!strcmp(a[0], "gaveup") && n == 2) {
			printf("0x%x\n", ad5x_start_uboot_gave_up(num(a[1])));
		} else if (!strcmp(a[0], "ubkernel") && n == 3) {
			printf("0x%x\n", ad5x_start_uboot_kernel(num(a[1]),
								 num(a[2])));
		} else if (!strcmp(a[0], "stopkey") && n <= 2) {
			const char *h = n == 2 ? a[1] : "";
			unsigned int done = 0;
			char b[3] = "";

			st = 0;
			for (i = 0; h[2 * i] && h[2 * i + 1]; i++) {
				b[0] = h[2 * i];
				b[1] = h[2 * i + 1];
				if (ad5x_stop_key(&st, (int)strtoul(b, NULL, 16))) {
					done = i + 1;
					break;
				}
			}
			printf("%u\n", done);
		} else if (!strcmp(a[0], "tries")) {
			printf("%d\n", AD5X_START_TRIES);
		} else {
			printf("error\n");
		}
		fflush(stdout);
	}
	return 0;
}
