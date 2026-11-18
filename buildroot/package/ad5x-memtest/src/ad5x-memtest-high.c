// SPDX-License-Identifier: GPL-3.0-or-later
// ad5x-memtest-high: the one-time test of the X2600H's high DRAM bank
// (physical 0x30000000-0x3fffffff: PFN 0x30000-0x3ffff, 65536 pages of
// 4 KiB) on the first start in Extended memory mode (S05ad5x-memtest,
// docs/memory.md). The SPL's DDR test covers the low window only, and the
// kernel's memtest= doesn't reach highmem on MIPS, so this tests the bank
// from userspace, early in the boot while it is nearly all free:
//
//   - vm.compact_unevictable_allowed 0 for the run (compaction then
//     leaves locked pages where they are; restored at the end, also on
//     SIGTERM/SIGINT/SIGHUP; a kernel without compaction has no such
//     file and moves nothing), page cache dropped
//   - a buffer the size of HighMem's free pages above its high mark
//     (/proc/zoneinfo), leaving at least --reserve-mib (48) of MemFree to
//     the rest of the system; mmap MAP_POPULATE, then mlock
//   - /proc/self/pagemap (root: PFNs) keeps the pages that landed in the
//     bank; the others are left untested
//   - 4 passes over those pages, each writing all of them, then reading
//     all of them back: the word's physical address, its inverse,
//     0x55555555, 0xaaaaaaaa (address lines and aliasing first, then
//     every bit both ways)
//   - the PFNs read again at the end: a page that moved makes the run
//     not count
//   - --limit-ms (60000) for the whole run, from the start of the program
//
// The last line on stdout is the result (the record S05ad5x-memtest keeps,
// with the date):
//   exit 0  memtest: N/65536 high-bank pages tested, 4 passes, T ms
//   exit 1  memtest: 0x3xxxxxxx reads 0xXXXXXXXX, 0xYYYYYYYY written
//   exit 2  memtest: not run: REASON
//   exit 3  memtest: time limit 60 s after K/4 passes, N/65536 high-bank pages, T ms
//           (no fault seen in the passes done)
//
// Laptop tests (tools/test_ad5x_memtest.sh), no root and no high bank:
//   --plan [--proc DIR]: the buffer size from DIR/zoneinfo and
//     DIR/meminfo, printed; nothing else is done
//   --self-test --pagemap FILE: an ordinary buffer of FILE's size / 8
//     pages, FILE taken as its pagemap (entry i = buffer page i), the
//     same filter, passes and result. --pagemap-after FILE2 for the
//     check at the end. Faults, applied after each write phase:
//     --fault PAGE:WORD:XOR[:PASS] (buffer page, word in it, bits
//     flipped; PASS 1-4, all passes without), --alias A:B (page A reads
//     what page B holds: one address line stuck), --delay-us US per page
//
// usage: ad5x-memtest-high [--limit-ms MS] [--reserve-mib MIB] [--max-mib MIB]
//        ad5x-memtest-high --plan [--proc DIR] [--reserve-mib MIB] [--max-mib MIB]
//        ad5x-memtest-high --self-test --pagemap FILE [--pagemap-after FILE]
//               [--fault PAGE:WORD:XOR[:PASS]] [--alias A:B] [--delay-us US]
//               [--limit-ms MS]
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define PAGE_SZ 4096u
#define PAGE_WORDS (PAGE_SZ / 4)
#define BANK_PFN 0x30000u
#define BANK_PAGES 0x10000u
#define NPASS 4
#define MIN_PAGES 256 // 1 MiB: less is not worth a test

enum { R_PASS = 0, R_FAULT = 1, R_NOTRUN = 2, R_TIME = 3 };

static const char *proc_dir = "/proc";
static long long t0_ms;
static long long limit_ms = 60000;
static long reserve_mib = 48;
static long max_mib;

// the pages under test: where they are mapped, which frame they are
struct tpage {
	volatile uint32_t *p;
	uint32_t pfn;
	uint32_t idx; // page index in the buffer
};
static struct tpage *tp;
static uint32_t ntp;
static uint8_t *buf;
static size_t buf_pages;

// self-test faults (buffer page indices)
static int selftest;
static long fault_page = -1, fault_word;
static uint32_t fault_xor;
static int fault_pass; // 0: every pass
static long alias_a = -1, alias_b = -1;
static unsigned delay_us;

// vm.compact_unevictable_allowed, as found
static char cua_path[256];
static char cua_old[16];
static size_t cua_len;
static volatile sig_atomic_t cua_saved;

static long long now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000LL + ts.tv_nsec / 1000000;
}

static int write_str(const char *path, const char *s, size_t len)
{
	int fd = open(path, O_WRONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	ssize_t r = write(fd, s, len);
	close(fd);
	return r == (ssize_t)len ? 0 : -1;
}

static void cua_restore(void)
{
	if (cua_saved) {
		write_str(cua_path, cua_old, cua_len);
		cua_saved = 0;
	}
}

static void on_signal(int sig)
{
	(void)sig;
	cua_restore(); // open/write/close: async-signal-safe
	_exit(R_NOTRUN);
}

static int not_run(const char *why)
{
	printf("memtest: not run: %s\n", why);
	return R_NOTRUN;
}

// --plan and the real run: how many pages to map. 0 and a reason in why
// when there is nothing to test.
static long plan_pages(char *why, size_t whylen)
{
	char path[512], line[256], name[32];
	long hm_free = -1, hm_high = -1, mem_free_kb = -1, v;
	int in_hm = 0;
	FILE *f;

	snprintf(path, sizeof path, "%s/zoneinfo", proc_dir);
	if (!(f = fopen(path, "r"))) {
		snprintf(why, whylen, "no %.100s", path);
		return 0;
	}
	while (fgets(line, sizeof line, f)) {
		if (sscanf(line, "Node %*d, zone %31s", name) == 1) {
			in_hm = strcmp(name, "HighMem") == 0;
			continue;
		}
		if (!in_hm)
			continue;
		if (sscanf(line, " pages free %ld", &v) == 1)
			hm_free = v;
		else if (hm_free >= 0 && hm_high < 0 && sscanf(line, " high %ld", &v) == 1)
			hm_high = v;
	}
	fclose(f);
	snprintf(path, sizeof path, "%s/meminfo", proc_dir);
	if ((f = fopen(path, "r"))) {
		while (fgets(line, sizeof line, f))
			if (sscanf(line, "MemFree: %ld kB", &v) == 1)
				mem_free_kb = v;
		fclose(f);
	}
	if (hm_free < 0) {
		snprintf(why, whylen, "no HighMem zone (the high bank is not in use)");
		return 0;
	}
	if (mem_free_kb < 0) {
		snprintf(why, whylen, "no MemFree in %s/meminfo", proc_dir);
		return 0;
	}
	if (hm_high < 0)
		hm_high = 0;
	long n = hm_free - hm_high;
	long cap = mem_free_kb / 4 - reserve_mib * 256;
	if (n > cap)
		n = cap;
	if (max_mib > 0 && n > max_mib * 256)
		n = max_mib * 256;
	printf("memtest: HighMem %ld pages free (high mark %ld), MemFree %ld kB, %ld MiB kept free: %ld pages to map\n",
	       hm_free, hm_high, mem_free_kb, reserve_mib, n > 0 ? n : 0);
	if (n < MIN_PAGES) {
		snprintf(why, whylen, "too little free memory (%ld pages; at least %d)",
			 n > 0 ? n : 0, MIN_PAGES);
		return 0;
	}
	return n;
}

// pfn[i] for buffer pages i: the frame, 0 for one not present or swapped.
// base_vpn: the buffer's first virtual page (0 for a self-test's file).
// *present: how many were present. -1 when the file can't be read.
static int read_pfns(const char *path, uint64_t base_vpn, size_t n, uint64_t *pfn,
		     size_t *present)
{
	uint64_t e[512];
	size_t i = 0;
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	if (present)
		*present = 0;
	while (i < n) {
		size_t k = n - i > 512 ? 512 : n - i;
		ssize_t r = pread(fd, e, k * 8, (off_t)((base_vpn + i) * 8));
		if (r != (ssize_t)(k * 8)) {
			close(fd);
			return -1;
		}
		for (size_t j = 0; j < k; j++) {
			uint64_t v = e[j];
			// bit 63 present, 62 swapped, 0-54 the PFN
			if ((v >> 63) && !((v >> 62) & 1)) {
				pfn[i + j] = v & ((1ULL << 55) - 1);
				if (present)
					(*present)++;
			} else {
				pfn[i + j] = 0;
			}
		}
		i += k;
	}
	close(fd);
	return 0;
}

static int in_bank(uint64_t pfn)
{
	return pfn >= BANK_PFN && pfn < BANK_PFN + BANK_PAGES;
}

static void inject(int pass)
{
	if (!selftest)
		return;
	if (alias_a >= 0)
		memcpy(buf + (size_t)alias_a * PAGE_SZ, buf + (size_t)alias_b * PAGE_SZ, PAGE_SZ);
	if (fault_page >= 0 && (fault_pass == 0 || fault_pass == pass + 1)) {
		volatile uint32_t *w = (volatile uint32_t *)(buf + (size_t)fault_page * PAGE_SZ);
		w[fault_word] ^= fault_xor;
	}
}

// 1 when the time is up
static int tick(void)
{
	if (delay_us)
		usleep(delay_us);
	return now_ms() - t0_ms > limit_ms;
}

static uint32_t bad_addr, bad_read, bad_written;

static int run_passes(int *done)
{
	static const char *const names[NPASS] = { "address", "inverse address",
						  "0x55555555", "0xaaaaaaaa" };
	*done = 0;
	for (int pass = 0; pass < NPASS; pass++) {
		uint32_t x = pass == 1 ? 0xffffffffu : 0;
		uint32_t c = pass == 2 ? 0x55555555u : 0xaaaaaaaau;
		int addr = pass < 2;
		for (uint32_t i = 0; i < ntp; i++) {
			volatile uint32_t *p = tp[i].p;
			uint32_t a = tp[i].pfn << 12;
			if (addr)
				for (uint32_t w = 0; w < PAGE_WORDS; w++)
					p[w] = (a + 4 * w) ^ x;
			else
				for (uint32_t w = 0; w < PAGE_WORDS; w++)
					p[w] = c;
			if (tick())
				return R_TIME;
		}
		__asm__ volatile("" ::: "memory");
		inject(pass);
		__asm__ volatile("" ::: "memory");
		for (uint32_t i = 0; i < ntp; i++) {
			volatile uint32_t *p = tp[i].p;
			uint32_t a = tp[i].pfn << 12;
			for (uint32_t w = 0; w < PAGE_WORDS; w++) {
				uint32_t want = addr ? (a + 4 * w) ^ x : c;
				uint32_t got = p[w];
				if (got != want) {
					bad_addr = a + 4 * w;
					bad_read = got;
					bad_written = want;
					printf("memtest: fault in pass %d/%d (%s), page %" PRIu32 " of %" PRIu32 " tested\n",
					       pass + 1, NPASS, names[pass], i + 1, ntp);
					return R_FAULT;
				}
			}
			if (tick())
				return R_TIME;
		}
		*done = pass + 1;
	}
	return R_PASS;
}

static int parse_long(const char *s, long *v)
{
	char *end;
	errno = 0;
	long r = strtol(s, &end, 0);
	if (errno || end == s || *end)
		return -1;
	*v = r;
	return 0;
}

static void usage(void)
{
	fputs("usage: ad5x-memtest-high [--limit-ms MS] [--reserve-mib MIB] [--max-mib MIB]\n"
	      "       ad5x-memtest-high --plan [--proc DIR] [--reserve-mib MIB] [--max-mib MIB]\n"
	      "       ad5x-memtest-high --self-test --pagemap FILE [--pagemap-after FILE]\n"
	      "              [--fault PAGE:WORD:XOR[:PASS]] [--alias A:B] [--delay-us US]\n"
	      "              [--limit-ms MS]\n",
	      stderr);
}

// Real run: settings, buffer and lock. 0 or R_NOTRUN (printed).
static int prepare_real(char *pagemap, size_t pmlen, uint64_t *base_vpn)
{
	char why[160], path[512];
	struct sigaction sa;

	memset(&sa, 0, sizeof sa);
	sa.sa_handler = on_signal;
	sigaction(SIGTERM, &sa, NULL);
	sigaction(SIGINT, &sa, NULL);
	sigaction(SIGHUP, &sa, NULL);

	// the OOM killer's first choice if memory runs out after all
	snprintf(path, sizeof path, "%s/self/oom_score_adj", proc_dir);
	write_str(path, "1000\n", 5);

	snprintf(cua_path, sizeof cua_path, "%s/sys/vm/compact_unevictable_allowed", proc_dir);
	int fd = open(cua_path, O_RDONLY | O_CLOEXEC);
	if (fd >= 0) {
		ssize_t r = read(fd, cua_old, sizeof cua_old - 1);
		close(fd);
		if (r > 0) {
			cua_len = (size_t)r;
			cua_saved = 1;
			if (write_str(cua_path, "0\n", 2) != 0)
				printf("memtest: compact_unevictable_allowed not set\n");
		}
	}
	sync();
	snprintf(path, sizeof path, "%s/sys/vm/drop_caches", proc_dir);
	if (write_str(path, "3\n", 2) != 0)
		printf("memtest: page cache not dropped\n");

	long n = plan_pages(why, sizeof why);
	if (n == 0)
		return not_run(why);
	buf_pages = (size_t)n;
	buf = mmap(NULL, buf_pages * PAGE_SZ, PROT_READ | PROT_WRITE,
		   MAP_PRIVATE | MAP_ANONYMOUS | MAP_POPULATE, -1, 0);
	if (buf == MAP_FAILED) {
		buf = NULL;
		snprintf(why, sizeof why, "mmap of %zu pages: %s", buf_pages, strerror(errno));
		return not_run(why);
	}
	if (mlock(buf, buf_pages * PAGE_SZ) != 0) {
		snprintf(why, sizeof why, "mlock of %zu pages: %s", buf_pages, strerror(errno));
		return not_run(why);
	}
	snprintf(pagemap, pmlen, "%s/self/pagemap", proc_dir);
	*base_vpn = (uintptr_t)buf / PAGE_SZ;
	return 0;
}

int main(int argc, char **argv)
{
	const char *pm_file = NULL, *pm_after = NULL;
	char pagemap[512], why[160];
	int plan = 0;
	uint64_t base_vpn = 0;

	t0_ms = now_ms();
	setvbuf(stdout, NULL, _IOLBF, 0);
	for (int i = 1; i < argc; i++) {
		const char *a = argv[i];
		const char *v = i + 1 < argc ? argv[i + 1] : NULL;
		long n;
		if (!strcmp(a, "--plan")) {
			plan = 1;
		} else if (!strcmp(a, "--self-test")) {
			selftest = 1;
		} else if (v && !strcmp(a, "--proc")) {
			proc_dir = v;
			i++;
		} else if (v && !strcmp(a, "--pagemap")) {
			pm_file = v;
			i++;
		} else if (v && !strcmp(a, "--pagemap-after")) {
			pm_after = v;
			i++;
		} else if (v && !strcmp(a, "--limit-ms") && !parse_long(v, &n) && n > 0) {
			limit_ms = n;
			i++;
		} else if (v && !strcmp(a, "--reserve-mib") && !parse_long(v, &n) && n >= 0) {
			reserve_mib = n;
			i++;
		} else if (v && !strcmp(a, "--max-mib") && !parse_long(v, &n) && n >= 0) {
			max_mib = n;
			i++;
		} else if (v && !strcmp(a, "--delay-us") && !parse_long(v, &n) && n >= 0) {
			delay_us = (unsigned)n;
			i++;
		} else if (v && !strcmp(a, "--fault")) {
			// PAGE:WORD:XOR[:PASS], each decimal or 0x hex
			unsigned long f[4] = { 0, 0, 0, 0 };
			const char *s = v;
			int k = 0;
			while (k < 4) {
				char *end;
				errno = 0;
				f[k++] = strtoul(s, &end, 0);
				if (errno || end == s || (*end && *end != ':'))
					k = -1;
				if (k < 0 || !*end)
					break;
				s = end + 1;
			}
			if (k < 3 || f[1] >= PAGE_WORDS || f[2] > 0xffffffffUL || f[3] > NPASS) {
				usage();
				return R_NOTRUN;
			}
			fault_page = (long)f[0];
			fault_word = (long)f[1];
			fault_xor = (uint32_t)f[2];
			fault_pass = (int)f[3];
			i++;
		} else if (v && !strcmp(a, "--alias")) {
			if (sscanf(v, "%ld:%ld", &alias_a, &alias_b) != 2 || alias_a < 0 || alias_b < 0) {
				usage();
				return R_NOTRUN;
			}
			i++;
		} else {
			usage();
			return R_NOTRUN;
		}
	}

	if (plan) {
		long n = plan_pages(why, sizeof why);
		if (n == 0)
			return not_run(why);
		printf("memtest: would test up to %ld pages (%ld MiB)\n", n, n / 256);
		return 0;
	}

	if (selftest) {
		struct stat st;
		if (!pm_file || stat(pm_file, &st) != 0 || st.st_size < 8 || st.st_size % 8) {
			usage();
			return R_NOTRUN;
		}
		buf_pages = (size_t)st.st_size / 8;
		if ((fault_page >= 0 && (size_t)fault_page >= buf_pages) ||
		    (alias_a >= 0 && ((size_t)alias_a >= buf_pages || (size_t)alias_b >= buf_pages))) {
			usage();
			return R_NOTRUN;
		}
		buf = mmap(NULL, buf_pages * PAGE_SZ, PROT_READ | PROT_WRITE,
			   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		if (buf == MAP_FAILED)
			return not_run("self-test buffer");
		snprintf(pagemap, sizeof pagemap, "%s", pm_file);
	} else {
		atexit(cua_restore);
		int r = prepare_real(pagemap, sizeof pagemap, &base_vpn);
		if (r)
			return r;
		pm_after = pagemap;
	}

	uint64_t *pfn = calloc(buf_pages, sizeof *pfn);
	tp = calloc(buf_pages < BANK_PAGES ? buf_pages : BANK_PAGES, sizeof *tp);
	if (!pfn || !tp)
		return not_run("out of memory for the page list");
	size_t present;
	if (read_pfns(pagemap, base_vpn, buf_pages, pfn, &present) != 0) {
		snprintf(why, sizeof why, "%.80s not readable (needs CONFIG_PROC_PAGE_MONITOR)", pagemap);
		return not_run(why);
	}
	size_t zero = 0;
	for (size_t i = 0; i < buf_pages; i++) {
		if (!pfn[i]) {
			zero++;
			continue;
		}
		if (!in_bank(pfn[i]) || ntp >= BANK_PAGES)
			continue;
		tp[ntp].p = (volatile uint32_t *)(buf + i * PAGE_SZ);
		tp[ntp].pfn = (uint32_t)pfn[i];
		tp[ntp].idx = (uint32_t)i;
		ntp++;
	}
	if (present == 0 || zero == buf_pages)
		return not_run("pagemap shows no page frame numbers (needs root)");
	printf("memtest: %zu pages mapped, %" PRIu32 " in the high bank\n", buf_pages, ntp);
	if (ntp == 0)
		return not_run("none of the mapped pages are in the high bank");

	int done;
	int r = run_passes(&done);
	long long ms = now_ms() - t0_ms;

	// the frames again: a page that moved was not tested where we think
	uint64_t *after = calloc(buf_pages, sizeof *after);
	uint32_t moved = 0;
	if (!after || read_pfns(pm_after ? pm_after : pagemap, base_vpn, buf_pages, after, NULL) != 0)
		moved = ntp; // can't tell: don't count it
	else
		for (uint32_t i = 0; i < ntp; i++)
			if (after[tp[i].idx] != tp[i].pfn)
				moved++;

	if (r == R_FAULT) {
		if (moved)
			printf("memtest: %" PRIu32 " pages moved during the test\n", moved);
		printf("memtest: 0x%08" PRIx32 " reads 0x%08" PRIx32 ", 0x%08" PRIx32 " written\n",
		       bad_addr, bad_read, bad_written);
		return R_FAULT;
	}
	if (moved) {
		snprintf(why, sizeof why, "%" PRIu32 " of %" PRIu32 " pages moved during the test",
			 moved, ntp);
		return not_run(why);
	}
	if (r == R_TIME) {
		printf("memtest: time limit %lld %s after %d/%d passes, %" PRIu32 "/%u high-bank pages, %lld ms\n",
		       limit_ms % 1000 ? limit_ms : limit_ms / 1000, limit_ms % 1000 ? "ms" : "s",
		       done, NPASS, ntp, BANK_PAGES, ms);
		return R_TIME;
	}
	printf("memtest: %" PRIu32 "/%u high-bank pages tested, %d passes, %lld ms\n", ntp,
	       BANK_PAGES, NPASS, ms);
	return R_PASS;
}
