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
 *   bootlogic_cli format    records as "key value" lines on stdin
 *                           (failed_own failed_mainline failed_mem
 *                           fallbacks reason): "left_out N", then the
 *                           512-byte sector ad5x_records_format() writes
 *   bootlogic_cli sector MAGIC
 *                           "KEY VALUE" lines on stdin ("\\n" in a value: a
 *                           newline), each given to ad5x_sec_add() after
 *                           MAGIC (its "\n" added): "left_out N", then the
 *                           512-byte sector
 *   bootlogic_cli slotaname NAME
 *                           "ok" when p1's kernel named NAME may start the
 *                           recovery OS (ad5x_slot_a_kernel_ok), else "no"
 *   bootlogic_cli rescue [N]
 *                           a 512-byte sector (LBA 2047) on stdin: "none",
 *                           "bad WHY", or "run|gaveup" and the fields as
 *                           "key value" lines (ad5x_rescue_parse); with N,
 *                           then "--counted--" and the sector with tries=N
 *                           (ad5x_rescue_counted) up to its first NUL, or
 *                           "--nofit--"
 *   bootlogic_cli nc FILE INPUT
 *                           the netconsole switch (ad5x_nc_decide): FILE 0/1
 *                           (/data/ad5x/netconsole exists), its text on
 *                           stdin, INPUT 0/1 (netconsole-input exists):
 *                           "off|out|in", then the address ("-": none) and
 *                           the note, a line each
 *
 * Input keys: flag_b data_ok mainline_wanted after_install have_66 have_73
 * slot_a_ok wdt_off wdt_capable ext_wanted ext_failed state_mem_ext (0/1),
 * ram_mib, rel_66 rel_73 s00_failed
 * s00_failed_mainline, state_tries state_kernel (66|73|none; anything
 * else, as an older build's "stock", is none) state_release,
 * rec_failed_own rec_failed_mainline rec_failed_mem
 * rec_fallbacks, wdt_os (the environment's, default 0). Output "wdt" is
 * ad5x_wdt_seconds() for the decision, "mem_ext" the memory mode.
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
	I(ext_wanted) I(ext_failed) I(ram_mib)
	S("rel_66", in->rel_66) S("rel_73", in->rel_73)
	S("s00_failed", in->s00_failed)
	S("s00_failed_mainline", in->s00_failed_mainline)
	S("state_release", in->state.release)
	S("rec_failed_own", in->rec.failed_own)
	S("rec_failed_mainline", in->rec.failed_mainline)
	S("rec_failed_mem", in->rec.failed_mem)
	if (!strcmp(k, "state_mem_ext")) { in->state.mem_ext = n; return; }
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
	       "rec_fallbacks %u\nrec_reason %s\nmsg %s\nwdt %u\n"
	       "mem_ext %d\nstate_mem_ext %d\nrec_failed_mem %s\n",
	       target(d.target), ad5x_kernel_name(d.kernel), d.write_flag,
	       d.state_changed, d.rec_changed, d.state.tries,
	       ad5x_kernel_name(d.state.kernel), d.state.release,
	       d.rec.failed_own, d.rec.failed_mainline, d.rec.fallbacks,
	       d.rec.reason, d.msg, ad5x_wdt_seconds(&in, &d, wdt_os),
	       d.mem_ext, d.state.mem_ext, d.rec.failed_mem);
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
		printf("state ok %u %s %s %s\n", st.tries,
		       ad5x_kernel_name(st.kernel), st.release,
		       st.mem_ext ? "ext" : "std");
	if (ad5x_records_parse(buf, &rec))
		printf("records bad\n");
	else
		printf("records ok %s|%s|%u|%s|%s\n", rec.failed_own,
		       rec.failed_mainline, rec.fallbacks, rec.reason,
		       rec.failed_mem);
	return 0;
}

static void put_sector(unsigned int left_out, const char *buf)
{
	printf("left_out %u\n", left_out);
	fwrite(buf, 1, AD5X_REC_SIZE, stdout);
}

static int format(void)
{
	char line[1024], *v, buf[AD5X_REC_SIZE];
	struct ad5x_records rec;

	memset(&rec, 0, sizeof(rec));
	while (fgets(line, sizeof(line), stdin)) {
		line[strcspn(line, "\n")] = '\0';
		v = strchr(line, ' ');
		v = v ? (*v = '\0', v + 1) : line + strlen(line);
#define F(name) if (!strcmp(line, #name)) { \
	snprintf(rec.name, sizeof(rec.name), "%s", v); continue; }
		F(failed_own) F(failed_mainline) F(failed_mem) F(reason)
		if (!strcmp(line, "fallbacks")) {
			rec.fallbacks = strtoul(v, NULL, 10);
			continue;
		}
		fprintf(stderr, "unknown key %s\n", line);
		return 2;
	}
	put_sector(ad5x_records_format(&rec, buf), buf);
	return 0;
}

static int sector(const char *magic)
{
	char line[2048], m[64], *v, *e, buf[AD5X_REC_SIZE];
	struct ad5x_sec s;

	snprintf(m, sizeof(m), "%s\n", magic);
	ad5x_sec_start(&s, buf, m);
	while (fgets(line, sizeof(line), stdin)) {
		line[strcspn(line, "\n")] = '\0';
		v = strchr(line, ' ');
		v = v ? (*v = '\0', v + 1) : line + strlen(line);
		while ((e = strstr(v, "\\n"))) {
			*e = '\n';
			memmove(e + 1, e + 2, strlen(e + 2) + 1);
		}
		ad5x_sec_add(&s, line, v);
	}
	put_sector(ad5x_sec_finish(&s), buf);
	return 0;
}

static int rescue(int argc, char **argv)
{
	char buf[AD5X_REC_SIZE], out[AD5X_REC_SIZE];
	struct ad5x_rescue_rec r;
	size_t n = fread(buf, 1, sizeof(buf), stdin);

	memset(buf + n, 0, sizeof(buf) - n);
	switch (ad5x_rescue_parse(buf, &r)) {
	case AD5X_RESCUE_NONE:
		printf("none\n");
		break;
	case AD5X_RESCUE_BAD:
		printf("bad %s\n", r.why);
		break;
	default:
		printf("%s\nserver %s\nport %s\nsha256 %s\nmac %s\nip %s\n"
		       "netmask %s\ntries %u\n",
		       r.tries < AD5X_RESCUE_TRIES ? "run" : "gaveup", r.server,
		       r.port, r.sha256, r.mac, r.ip, r.netmask, r.tries);
	}
	if (argc == 3) {
		if (ad5x_rescue_counted(buf, (unsigned int)atoi(argv[2]), out)) {
			printf("--nofit--\n");
		} else {
			printf("--counted--\n");
			fwrite(out, 1, strnlen(out, sizeof(out)), stdout);
		}
	}
	return 0;
}

static int nc(int file, int input)
{
	static const char *const mode[] = { "off", "out", "in" };
	char buf[256];
	struct ad5x_nc d;
	size_t n = fread(buf, 1, sizeof(buf) - 1, stdin);

	buf[n] = '\0';
	ad5x_nc_decide(file, buf, input, &d);
	printf("%s\n%s\n%s\n", mode[d.mode], d.ip[0] ? d.ip : "-", d.note);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc == 2 && !strcmp(argv[1], "decide"))
		return decide();
	if (argc == 2 && !strcmp(argv[1], "parse"))
		return parse();
	if (argc == 2 && !strcmp(argv[1], "format"))
		return format();
	if (argc == 3 && !strcmp(argv[1], "sector"))
		return sector(argv[2]);
	if (argc == 4 && !strcmp(argv[1], "nc"))
		return nc(atoi(argv[2]), atoi(argv[3]));
	if ((argc == 2 || argc == 3) && !strcmp(argv[1], "rescue"))
		return rescue(argc, argv);
	if (argc == 3 && !strcmp(argv[1], "slotaname")) {
		printf("%s\n", ad5x_slot_a_kernel_ok(argv[2]) ? "ok" : "no");
		return 0;
	}
	fprintf(stderr, "usage: bootlogic_cli decide|parse|format|sector MAGIC|"
		"slotaname NAME|"
		"rescue [N]|nc FILE INPUT\n");
	return 2;
}
