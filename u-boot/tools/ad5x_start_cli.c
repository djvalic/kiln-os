// SPDX-License-Identifier: GPL-2.0+
/*
 * Host driver for the start-up hand-offs (mach/ad5x_start.h), U-Boot
 * proper's stop key (board/flashforge/ad5x/stopkey.h) and the X2600
 * variant decision (mach/x2600_ram.h), for test_ad5x_start.py. One command per line on stdin, one answer line each
 * (flushed, so the test can talk to it):
 *
 *   plan V [SLPC]               attempt skip_uboot forced slot_b usb stop
 *                               (SLPC 1: CPM_SLPC held the USB request)
 *   value A SKIP F SB PHASE S   the CPSPR value for that plan, phase, slot
 *   entry V                     what U-Boot proper writes as it starts
 *   gaveup V                    what U-Boot proper resets with, no key
 *   usbvalue V                  what the SPL leaves as it asks for USB
 *   ubkernel WHAT TRIES         what it leaves as it jumps to a kernel
 *   stopkey HEX                 1-based index of the byte completing the
 *                               stop key in the bytes HEX, 0 if none
 *   tries                       AD5X_START_TRIES
 *   stage2                      AD5X_USB_STAGE2 (the "KILNUSB2" value)
 *   socid D0 D1                 x2600_socid_decode() of eFuse words
 *                               0x1a and 0x1b (signed)
 *   ram ID                      x2600_ram_mib(ID), ID signed
 *   ddrid ID                    X2600_DDR_ID(ID)
 *   drop HEX                    x2600_args_drop_high_bank() of the
 *                               string HEX, as hex ("-" when empty)
 *   kiln HEX                    x2600_args_kiln_low() of it, the same way
 *   memory MIB EXT SIZE HEX     x2600_args_memory() of it in a SIZE-byte
 *                               buffer (0: the string's length +
 *                               X2600_ARGS_MEMORY_MAX): "1|0 HEX"
 *   spl MIB NAMEHEX HEX         x2600_args_spl() of it for a uImage named
 *                               NAMEHEX ("-": empty), in a buffer of its
 *                               size + X2600_ARGS_MEMORY_MAX, as the SPL's
 *   memmax                      X2600_ARGS_MEMORY_MAX
 *   lpj MIB HEX                 x2600_args_lpj() of it for MIB, as hex
 *
 * Numbers in C syntax (0x...).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ad5x_start.h"
#include "stopkey.h"
#include "x2600_ram.h"

static unsigned int num(const char *s)
{
	return (unsigned int)strtoul(s, NULL, 0);
}

/* hex @h ("-": empty) into @s (@n bytes), NUL-terminated; its length */
static unsigned int unhex(const char *h, char *s, unsigned int n)
{
	char b[3] = "";
	unsigned int i;

	if (!strcmp(h, "-"))
		h = "";
	for (i = 0; h[2 * i] && h[2 * i + 1] && i < n - 1; i++) {
		b[0] = h[2 * i];
		b[1] = h[2 * i + 1];
		s[i] = (char)strtoul(b, NULL, 16);
	}
	s[i] = '\0';
	return i;
}

static void puthex(const char *s)
{
	unsigned int i;

	for (i = 0; s[i]; i++)
		printf("%02x", (unsigned char)s[i]);
	printf("%s", i ? "" : "-");
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
		if (!strcmp(a[0], "plan") && (n == 2 || n == 3)) {
			ad5x_start_plan(num(a[1]), n == 3 ? (int)num(a[2]) : 0,
					&p);
			printf("%u %d %d %d %d %d\n", p.attempt, p.skip_uboot,
			       p.forced, p.slot_b, p.usb, p.stop);
		} else if (!strcmp(a[0], "value") && n == 7) {
			p.attempt = num(a[1]);
			p.skip_uboot = num(a[2]);
			p.forced = num(a[3]);
			p.slot_b = num(a[4]);
			p.usb = p.stop = 0;
			printf("0x%x\n", ad5x_start_value(&p,
				(enum ad5x_phase)num(a[5]), num(a[6])));
		} else if (!strcmp(a[0], "entry") && n == 2) {
			printf("0x%x\n", ad5x_start_uboot_entry(num(a[1])));
		} else if (!strcmp(a[0], "gaveup") && n == 2) {
			printf("0x%x\n", ad5x_start_uboot_gave_up(num(a[1])));
		} else if (!strcmp(a[0], "usbvalue") && n == 2) {
			printf("0x%x\n", ad5x_start_usb_value(num(a[1])));
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
		} else if (!strcmp(a[0], "stage2")) {
			printf("0x%x\n", AD5X_USB_STAGE2);
		} else if (!strcmp(a[0], "socid") && n == 3) {
			printf("%d\n", x2600_socid_decode(num(a[1]), num(a[2])));
		} else if (!strcmp(a[0], "ram") && n == 2) {
			printf("%u\n", x2600_ram_mib((int)strtol(a[1], NULL, 0)));
		} else if (!strcmp(a[0], "ddrid") && n == 2) {
			printf("0x%x\n", X2600_DDR_ID(num(a[1])));
		} else if ((!strcmp(a[0], "drop") || !strcmp(a[0], "kiln")) &&
			   n <= 2) {
			const char *h = n == 2 ? a[1] : "";
			char s[2048], b[3] = "";

			for (i = 0; h[2 * i] && h[2 * i + 1] &&
			     i < sizeof(s) - 1; i++) {
				b[0] = h[2 * i];
				b[1] = h[2 * i + 1];
				s[i] = (char)strtoul(b, NULL, 16);
			}
			s[i] = '\0';
			if (a[0][0] == 'd')
				x2600_args_drop_high_bank(s);
			else
				x2600_args_kiln_low(s);
			for (i = 0; s[i]; i++)
				printf("%02x", (unsigned char)s[i]);
			printf("%s\n", i ? "" : "-");
		} else if (!strcmp(a[0], "memory") && (n == 4 || n == 5)) {
			char s[2048];
			unsigned int len = unhex(n == 5 ? a[4] : "", s,
						 sizeof(s) - 64);
			unsigned int size = num(a[3]);
			int ext;

			if (!size)
				size = len + X2600_ARGS_MEMORY_MAX;
			if (size > sizeof(s) || size <= len) {
				printf("error\n");
			} else {
				ext = x2600_args_memory(s, size, num(a[1]),
							(int)num(a[2]));
				printf("%d ", ext);
				puthex(s);
				printf("\n");
			}
		} else if (!strcmp(a[0], "spl") && (n == 3 || n == 4)) {
			char s[2048], name[64];
			unsigned int len = unhex(n == 4 ? a[3] : "", s,
						 sizeof(s) - 64);

			unhex(a[2], name, sizeof(name));
			/* the SPL's: sizeof(AD5X_ARGS) + X2600_ARGS_MEMORY_MAX */
			x2600_args_spl(s, len + 1 + X2600_ARGS_MEMORY_MAX,
				       num(a[1]), name);
			puthex(s);
			printf("\n");
		} else if (!strcmp(a[0], "lpj") && (n == 2 || n == 3)) {
			char s[2048];

			unhex(n == 3 ? a[2] : "", s, sizeof(s));
			x2600_args_lpj(s, num(a[1]));
			puthex(s);
			printf("\n");
		} else if (!strcmp(a[0], "memmax")) {
			printf("%u\n", (unsigned int)X2600_ARGS_MEMORY_MAX);
		} else {
			printf("error\n");
		}
		fflush(stdout);
	}
	return 0;
}
