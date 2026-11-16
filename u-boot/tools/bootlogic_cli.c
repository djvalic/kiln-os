// SPDX-License-Identifier: GPL-2.0+
/*
 * Host driver for board/flashforge/ad5x/bootlogic.c (test_bootlogic.py).
 *
 *   bootlogic_cli decide    inputs as "key value" lines on stdin, the
 *                           decision as "key value" lines on stdout, then
 *                           the state and records sectors as U-Boot would
 *                           write them (between "--state--"/"--records--")
 *   bootlogic_cli parse     a 512-byte sector on stdin: "state ok|bad" and
 *                           "records ok|bad" with the fields
 *   bootlogic_cli slotaname NAME
 *                           "ok" when p1's kernel named NAME may start the
 *                           recovery OS (ad5x_slot_a_kernel_ok), else "no"
 *
 * Input keys: flag_b data_ok mainline_wanted after_install have_66 have_73
 * slot_a_ok wdt_off wdt_capable (0/1), rel_66 rel_73 s00_failed
 * s00_failed_mainline, state_tries state_kernel (66|73|none; anything
 * else, as an older build's "stock", is none) state_release,
 * rec_failed_own rec_failed_mainline
 * rec_fallbacks, wdt_os (the environment's, default 0). Output "wdt" is
 * ad5x_wdt_seconds() for the decision.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bootlogic.h"

static enum ad5x_kernel kernel_of(const char *s)
{
	if (!strcmp(s, "66"))
		return AD5X_K_66;
	if (!strcmp(s, "73"))
		return AD5X_K_73;
	return AD5X_K_NONE;
}

static unsigned long wdt_os;

static void set(struct ad5x_inputs *in, const char *k, const char *v)
{
	int n = atoi(v);

#define I(name) if (!strcmp(k, #name)) { in->name = n; return; }
#define S(name, field) if (!strcmp(k, name)) { \
	snprintf(field, sizeof(field), "%s", v); return; }
	I(flag_b) I(data_ok) I(mainline_wanted) I(after_install)
	I(have_66) I(have_73) I(slot_a_ok)
	I(wdt_off) I(wdt_capable)
	S("rel_66", in->rel_66) S("rel_73", in->rel_73)
	S("s00_failed", in->s00_failed)
	S("s00_failed_mainline", in->s00_failed_mainline)
	S("state_release", in->state.release)
	S("rec_failed_own", in->rec.failed_own)
	S("rec_failed_mainline", in->rec.failed_mainline)
	if (!strcmp(k, "state_tries")) { in->state.tries = n; return; }
	if (!strcmp(k, "state_kernel")) {
		in->state.kernel = kernel_of(v);
		return;
	}
	if (!strcmp(k, "rec_fallbacks")) { in->rec.fallbacks = n; return; }
	if (!strcmp(k, "wdt_os")) { wdt_os = strtoul(v, NULL, 10); return; }
	fprintf(stderr, "unknown key %s\n", k);
	exit(2);
}

static const char *target(enum ad5x_target t)
{
	return t == AD5X_BOOT_MAIN ? "main" :
	       t == AD5X_BOOT_RECOVERY ? "recovery" : "prompt";
}

static int decide(void)
{
	struct ad5x_inputs in;
	struct ad5x_decision d;
	char line[512], *v, buf[AD5X_REC_SIZE];

	memset(&in, 0, sizeof(in));
	while (fgets(line, sizeof(line), stdin)) {
		line[strcspn(line, "\n")] = '\0';
		if (!line[0])
			continue;
		v = strchr(line, ' ');
		if (!v)
			v = line + strlen(line);
		else
			*v++ = '\0';
		set(&in, line, v);
	}
	ad5x_decide(&in, &d);
	printf("target %s\nkernel %s\nwrite_flag %d\nstate_changed %d\n"
	       "rec_changed %d\nstate_tries %u\nstate_kernel %s\n"
	       "state_release %s\nrec_failed_own %s\nrec_failed_mainline %s\n"
	       "rec_fallbacks %u\nrec_reason %s\nmsg %s\nwdt %u\n",
	       target(d.target), ad5x_kernel_name(d.kernel), d.write_flag,
	       d.state_changed, d.rec_changed, d.state.tries,
	       ad5x_kernel_name(d.state.kernel), d.state.release,
	       d.rec.failed_own, d.rec.failed_mainline, d.rec.fallbacks,
	       d.rec.reason, d.msg, ad5x_wdt_seconds(&in, &d, wdt_os));
	ad5x_state_format(&d.state, buf);
	printf("--state--\n%s--end--\n", buf);
	ad5x_records_format(&d.rec, buf);
	printf("--records--\n%s--end--\n", buf);
	return 0;
}

static int parse(void)
{
	char buf[AD5X_REC_SIZE];
	struct ad5x_state st;
	struct ad5x_records rec;
	size_t n = fread(buf, 1, sizeof(buf), stdin);

	memset(buf + n, 0, sizeof(buf) - n);
	if (ad5x_state_parse(buf, &st))
		printf("state bad\n");
	else
		printf("state ok %u %s %s\n", st.tries,
		       ad5x_kernel_name(st.kernel), st.release);
	if (ad5x_records_parse(buf, &rec))
		printf("records bad\n");
	else
		printf("records ok %s|%s|%u|%s\n", rec.failed_own,
		       rec.failed_mainline, rec.fallbacks, rec.reason);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc == 2 && !strcmp(argv[1], "decide"))
		return decide();
	if (argc == 2 && !strcmp(argv[1], "parse"))
		return parse();
	if (argc == 3 && !strcmp(argv[1], "slotaname")) {
		printf("%s\n", ad5x_slot_a_kernel_ok(argv[2]) ? "ok" : "no");
		return 0;
	}
	fprintf(stderr, "usage: bootlogic_cli decide|parse|slotaname NAME\n");
	return 2;
}
