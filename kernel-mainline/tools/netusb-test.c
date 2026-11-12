// SPDX-License-Identifier: GPL-2.0
/*
 * USB and Ethernet test for the AD5X on a mainline test kernel. Runs as
 * /init of a test initramfs (no other userspace); it never opens the eMMC.
 *
 *   - the USB devices the host port finds (vendor:product, speed, driver)
 *   - wlan0 (rtw88, firmware from the initramfs): present, and up
 *   - eth0: the stock MAC address and 192.168.1.77/24, the link it gets
 *   - TCP on port 5001: everything sent to it is counted and thrown away,
 *     then the count and rate are sent back ("sink"); port 5002 sends
 *     64 MiB of zeroes ("source"). From another machine:
 *       dd if=/dev/zero bs=1M count=64 | nc -N 192.168.1.77 5001
 *       nc 192.168.1.77 5002 | pv > /dev/null
 *
 *   mipsel-linux-gcc -static -O2 -pthread -o init netusb-test.c
 *
 * The kernel benchmarks at the end fork + exec /t1 and /t2, built from
 * exec-target.c (see there); put them in the initramfs next to /init.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <net/if.h>
#include <net/if_arp.h>
#include <linux/wireless.h>
#include <netinet/in.h>
#include <poll.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/cachectl.h>
#include <sys/mman.h>
#include <stdint.h>
#include <signal.h>
#include <pthread.h>
#include <sys/wait.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define ETH_ADDR	"192.168.1.77"
#define ETH_MASK	"255.255.255.0"
static const unsigned char eth_mac[6] = { 0x24, 0xa1, 0x0d, 0xb7, 0x40, 0x5d };

static double now(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

/* First line of a sysfs file, without the newline; "" when unreadable */
static const char *line_of(const char *path)
{
	static char buf[256];
	FILE *f = fopen(path, "r");

	buf[0] = 0;
	if (f) {
		if (!fgets(buf, sizeof(buf), f))
			buf[0] = 0;
		fclose(f);
	}
	buf[strcspn(buf, "\n")] = 0;
	return buf;
}

static void link_name(const char *path, char *out, size_t n)
{
	char buf[256];
	ssize_t len = readlink(path, buf, sizeof(buf) - 1);
	char *p;

	if (len < 0) {
		snprintf(out, n, "-");
		return;
	}
	buf[len] = 0;
	p = strrchr(buf, '/');
	p = p ? p + 1 : buf;
	strncpy(out, p, n - 1);
	out[n - 1] = 0;
}

static int list_usb(void)
{
	char path[1024], vid[16], pid[16], speed[16], drv[64], prod[96];
	struct dirent *e;
	DIR *d = opendir("/sys/bus/usb/devices");
	int n = 0;

	if (!d) {
		printf("usb: no /sys/bus/usb/devices\n");
		return 0;
	}
	while ((e = readdir(d))) {
		if (e->d_name[0] == '.' || strchr(e->d_name, ':'))
			continue;
		snprintf(path, sizeof(path), "/sys/bus/usb/devices/%s/idVendor", e->d_name);
		snprintf(vid, sizeof(vid), "%s", line_of(path));
		snprintf(path, sizeof(path), "/sys/bus/usb/devices/%s/idProduct", e->d_name);
		snprintf(pid, sizeof(pid), "%s", line_of(path));
		snprintf(path, sizeof(path), "/sys/bus/usb/devices/%s/speed", e->d_name);
		snprintf(speed, sizeof(speed), "%s", line_of(path));
		snprintf(path, sizeof(path), "/sys/bus/usb/devices/%s/product", e->d_name);
		snprintf(prod, sizeof(prod), "%s", line_of(path));
		/* the driver of the first interface tells what bound */
		snprintf(path, sizeof(path), "/sys/bus/usb/devices/%s/%s:1.0/driver",
			 e->d_name, e->d_name);
		link_name(path, drv, sizeof(drv));
		printf("usb %-8s %s:%s %4s Mb/s  %-10s %s\n", e->d_name, vid, pid,
		       speed, drv, prod);
		n++;
	}
	closedir(d);
	return n;
}

/* A 32-bit register through /dev/mem (CONFIG_DEVMEM); ~0 when unreadable */
static unsigned int reg32(unsigned long addr)
{
	unsigned long page = addr & ~0xfffUL;
	volatile unsigned int *m;
	unsigned int v = ~0U;
	int fd = open("/dev/mem", O_RDONLY | O_SYNC);

	if (fd < 0)
		return v;
	m = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED, fd, page);
	if (m != MAP_FAILED) {
		v = m[(addr - page) / 4];
		munmap((void *)m, 0x1000);
	}
	close(fd);
	return v;
}

/* What the PHY driver set: OPCR, USBPCR/USBPCR1 and the PHYs' own registers */
static void show_phy_regs(void)
{
	printf("phy: OPCR %08x; otg PCR %08x PCR1 %08x hs_tx %02x vbus %02x;",
	       reg32(0x10000024), reg32(0x1000003c), reg32(0x10000048),
	       reg32(0x10078030), reg32(0x1007803c));
	printf(" usb PCR %08x PCR1 %08x hs_tx %02x vbus %02x\n",
	       reg32(0x1000004c), reg32(0x100000e8),
	       reg32(0x10078430), reg32(0x1007843c));
	/* the host port's DWC2 core, to compare with the stock kernel's */
	printf("dwc2 usb: GOTGCTL %08x GAHBCFG %08x GUSBCFG %08x GRXFSIZ %08x GNPTXFSIZ %08x\n",
	       reg32(0x13540000), reg32(0x13540008), reg32(0x1354000c),
	       reg32(0x13540024), reg32(0x13540028));
	printf("dwc2 usb: HPTXFSIZ %08x GDFIFOCFG %08x HCFG %08x HFIR %08x HPRT %08x\n",
	       reg32(0x13540100), reg32(0x1354005c), reg32(0x13540400),
	       reg32(0x13540404), reg32(0x13540440));
}

static int has_usb(const char *vid, const char *pid)
{
	char path[1024], v[16];
	struct dirent *e;
	DIR *d = opendir("/sys/bus/usb/devices");
	int found = 0;

	while (d && (e = readdir(d))) {
		if (e->d_name[0] == '.' || strchr(e->d_name, ':'))
			continue;
		snprintf(path, sizeof(path), "/sys/bus/usb/devices/%s/idVendor", e->d_name);
		snprintf(v, sizeof(v), "%s", line_of(path));
		snprintf(path, sizeof(path), "/sys/bus/usb/devices/%s/idProduct", e->d_name);
		if (!strcmp(v, vid) && !strcmp(line_of(path), pid))
			found = 1;
	}
	if (d)
		closedir(d);
	return found;
}

static int if_up(int s, const char *name)
{
	struct ifreq r = { 0 };

	snprintf(r.ifr_name, IFNAMSIZ, "%s", name);
	if (ioctl(s, SIOCGIFFLAGS, &r))
		return -errno;
	r.ifr_flags |= IFF_UP;
	if (ioctl(s, SIOCSIFFLAGS, &r))
		return -errno;
	return 0;
}

static int set_addr(int s, const char *name, unsigned long req, const char *a)
{
	struct ifreq r = { 0 };
	struct sockaddr_in *sin = (struct sockaddr_in *)&r.ifr_addr;

	snprintf(r.ifr_name, IFNAMSIZ, "%s", name);
	sin->sin_family = AF_INET;
	inet_pton(AF_INET, a, &sin->sin_addr);
	return ioctl(s, req, &r) ? -errno : 0;
}

/* A scan through wireless extensions: the access points' SSIDs and count */
static void wifi_scan(int s)
{
	static char buf[65535];
	struct iwreq w = { 0 };
	char *p, *end;
	int i, n = 0;

	snprintf(w.ifr_name, IFNAMSIZ, "wlan0");
	if (ioctl(s, SIOCSIWSCAN, &w)) {
		printf("wlan0: scan: %s\n", strerror(errno));
		return;
	}
	for (i = 0; i < 100; i++) {
		usleep(100000);
		memset(&w, 0, sizeof(w));
		snprintf(w.ifr_name, IFNAMSIZ, "wlan0");
		w.u.data.pointer = buf;
		w.u.data.length = sizeof(buf);
		if (!ioctl(s, SIOCGIWSCAN, &w))
			break;
		if (errno != EAGAIN) {
			printf("wlan0: scan results: %s\n", strerror(errno));
			return;
		}
	}
	printf("wlan0: scan done after %.1f s, %u bytes:", (i + 1) / 10.0,
	       w.u.data.length);
	p = buf;
	end = buf + w.u.data.length;
	while (p + IW_EV_LCP_LEN <= end) {
		struct iw_event e;

		memcpy(&e, p, IW_EV_LCP_LEN);
		if (e.len < IW_EV_LCP_LEN || p + e.len > end)
			break;
		if (e.cmd == SIOCGIWAP)
			n++;
		/* the SSID: a struct iw_point (minus its pointer), then the text */
		if (e.cmd == SIOCGIWESSID && e.len >= IW_EV_POINT_LEN) {
			__u16 len;

			memcpy(&len, p + IW_EV_LCP_LEN, sizeof(len));
			if (len > 32 || IW_EV_POINT_LEN + len > e.len)
				len = 0;
			if (n <= 12)
				printf(" \"%.*s\"", len, p + IW_EV_POINT_LEN);
		}
		p += e.len;
	}
	printf("\nwlan0: %d access points\n", n);
}

static int if_down(int s, const char *name)
{
	struct ifreq r = { 0 };

	snprintf(r.ifr_name, IFNAMSIZ, "%s", name);
	if (ioctl(s, SIOCGIFFLAGS, &r))
		return -errno;
	r.ifr_flags &= ~IFF_UP;
	return ioctl(s, SIOCSIFFLAGS, &r) ? -errno : 0;
}

/* Power the Wi-Fi chip down and up again: how often does the start fail? */
static void wifi_cycles(int s, int count)
{
	int i, err, bad = 0;

	for (i = 1; i <= count; i++) {
		if_down(s, "wlan0");
		usleep(500000);
		err = if_up(s, "wlan0");
		if (err)
			bad++;
		printf("wlan0: cycle %d: %s\n", i, err ? strerror(-err) : "ok");
	}
	printf("wlan0: %d of %d restarts failed\n", bad, count);
}

static int setup_eth(int s)
{
	struct ifreq r = { 0 };
	int err, i;

	snprintf(r.ifr_name, IFNAMSIZ, "eth0");
	r.ifr_hwaddr.sa_family = ARPHRD_ETHER;
	memcpy(r.ifr_hwaddr.sa_data, eth_mac, 6);
	if (ioctl(s, SIOCSIFHWADDR, &r))
		printf("eth0: set MAC: %s\n", strerror(errno));

	err = if_up(s, "eth0");
	if (err) {
		printf("eth0: up: %s\n", strerror(-err));
		return -1;
	}
	if (set_addr(s, "eth0", SIOCSIFADDR, ETH_ADDR) ||
	    set_addr(s, "eth0", SIOCSIFNETMASK, ETH_MASK))
		printf("eth0: address: %s\n", strerror(errno));

	for (i = 0; i < 100; i++) {
		if (!strcmp(line_of("/sys/class/net/eth0/carrier"), "1"))
			break;
		usleep(100000);
	}
	/* line_of() reuses its buffer: one value per printf */
	printf("eth0: carrier %s after %.1f s", line_of("/sys/class/net/eth0/carrier"),
	       i / 10.0);
	printf(", %s Mb/s", line_of("/sys/class/net/eth0/speed"));
	printf(" %s duplex", line_of("/sys/class/net/eth0/duplex"));
	printf(", MAC %s\n", line_of("/sys/class/net/eth0/address"));
	return 0;
}

static int listen_on(int port)
{
	struct sockaddr_in a = { .sin_family = AF_INET, .sin_port = htons(port) };
	int one = 1, s = socket(AF_INET, SOCK_STREAM, 0);

	setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
	if (s < 0 || bind(s, (struct sockaddr *)&a, sizeof(a)) || listen(s, 2)) {
		printf("tcp %d: %s\n", port, strerror(errno));
		return -1;
	}
	return s;
}

static void sink(int c)
{
	static char buf[65536];
	unsigned long long total = 0;
	double t0 = now(), t;
	char msg[128];
	ssize_t n;

	while ((n = read(c, buf, sizeof(buf))) > 0)
		total += n;
	t = now() - t0;
	snprintf(msg, sizeof(msg), "sink: %llu bytes in %.2f s, %.2f MB/s%s\n",
		 total, t, t > 0 ? total / t / 1e6 : 0, n < 0 ? " (error)" : "");
	printf("%s", msg);
	if (write(c, msg, strlen(msg)) < 0)
		printf("sink: reply: %s\n", strerror(errno));
}

static void source(int c)
{
	static char buf[65536];
	unsigned long long total = 0, want = 64ULL << 20;
	double t0 = now(), t;
	ssize_t n;

	while (total < want && (n = write(c, buf, sizeof(buf))) > 0)
		total += n;
	t = now() - t0;
	printf("source: %llu bytes in %.2f s, %.2f MB/s\n", total, t,
	       t > 0 ? total / t / 1e6 : 0);
}

/*
 * Doubles kept in registers across sleeps must survive: an FP64 binary on a
 * kernel without O32_FP64_SUPPORT runs with FR=0 and loses them.
 */
static int fp_check(void)
{
	double a = 1.0 / 3.0, b = 2.5e-3, c = 12345.678;
	double t0 = now();
	int i;

	for (i = 0; i < 20; i++) {
		usleep(10000);
		a = a * 3.0 / 3.0;
		b += 0.0;
		c = c * 2.0 / 2.0;
	}
	printf("fp: 1/3 = %.9f, %.4f, %.3f, 20 x 10 ms took %.3f s: %s\n", a, b,
	       c, now() - t0,
	       a > 0.333333332 && a < 0.333333334 && b == 2.5e-3 &&
	       c == 12345.678 && now() - t0 > 0.15 && now() - t0 < 2.0 ?
	       "ok" : "FAIL");
	return 0;
}

/* Physical address of a virtual one, from /proc/self/pagemap (root only) */
static unsigned long long phys_of(const void *v)
{
	uint64_t e = 0;
	long psz = sysconf(_SC_PAGESIZE);
	int fd = open("/proc/self/pagemap", O_RDONLY);

	if (fd < 0)
		return 0;
	if (pread(fd, &e, 8, ((uintptr_t)v / psz) * 8) != 8)
		e = 0;
	close(fd);
	if (!(e >> 63))
		return 0;
	return (e & ((1ULL << 55) - 1)) * psz + ((uintptr_t)v % psz);
}

/*
 * Memory check, in a child process: lock MEM_MB of memory, fill each word
 * with a value made from its own address, then verify it all every 2 s.
 * Anything else writing to RAM (a DMA gone astray, the SoC's RISC-V core,
 * a bad DDR range) shows up as a mismatch at a physical address.
 */
#define MEM_MB	300
static void mem_check(void)
{
	size_t n = (size_t)MEM_MB << 20, words = n / 4, i;
	uint32_t *m = mmap(NULL, n, PROT_READ | PROT_WRITE,
			   MAP_PRIVATE | MAP_ANONYMOUS | MAP_POPULATE, -1, 0);
	unsigned long long lo = ~0ULL, hi = 0, pa;
	unsigned long pass = 0, bad = 0;

	if (m == MAP_FAILED || mlock(m, n)) {
		printf("mem: no %d MB: %s\n", MEM_MB, strerror(errno));
		_exit(1);
	}
	for (i = 0; i < words; i++)
		m[i] = (uint32_t)(uintptr_t)&m[i] ^ 0x5aa5c33c;
	for (i = 0; i < words; i += 1024) {	/* one sample per 4 KiB page */
		pa = phys_of(&m[i]);
		if (pa && pa < lo)
			lo = pa;
		if (pa > hi)
			hi = pa;
	}
	printf("mem: %d MB filled, physical %#llx..%#llx\n", MEM_MB, lo, hi);
	for (;;) {
		sleep(2);
		pass++;
		for (i = 0; i < words; i++) {
			uint32_t want = (uint32_t)(uintptr_t)&m[i] ^ 0x5aa5c33c;

			if (m[i] == want)
				continue;
			if (++bad <= 20)
				printf("mem: pass %lu: BAD at phys %#llx: %08x, want %08x\n",
				       pass, phys_of(&m[i]), m[i], want);
			m[i] = want;
		}
		if (pass % 10 == 0)
			printf("mem: %lu passes, %lu bad words\n", pass, bad);
	}
}

/*
 * Thread pointer reads, as glibc does them (rdhwr $29, UserLocal): native
 * when the kernel enables UserLocal, else each one traps and is emulated.
 * Also checks that thread-local data stays per thread.
 */
static __thread volatile int tls_var;

static unsigned long read_tp(void)
{
	unsigned long tp;

	__asm__ volatile(".set push\n.set mips32r2\nrdhwr %0, $29\n.set pop"
			 : "=r"(tp));
	return tp;
}

static void *tls_thread(void *arg)
{
	int i, bad = 0;

	tls_var = (int)(long)arg;
	for (i = 0; i < 100000; i++)
		if (tls_var != (int)(long)arg)
			bad++;
	return (void *)(long)bad;
}

static void tls_check(void)
{
	unsigned long tp0 = read_tp(), x = 0;
	pthread_t t1, t2;
	void *b1, *b2;
	double t0;
	int i;

	t0 = now();
	for (i = 0; i < 1000000; i++)
		x += read_tp();
	t0 = now() - t0;
	pthread_create(&t1, NULL, tls_thread, (void *)1L);
	pthread_create(&t2, NULL, tls_thread, (void *)2L);
	pthread_join(t1, &b1);
	pthread_join(t2, &b2);
	printf("tls: %.1f ns per thread pointer read (tp %#lx, sum %#lx), threads %s\n",
	       t0 * 1e3, tp0, x, !b1 && !b2 ? "ok" : "BAD");
}

/*
 * Kernel micro-benchmarks, each run 3 times, best kept: system call,
 * context switch (pipe ping-pong), fork, fork + exec of two small programs
 * (/t1, /t2: different code at the same addresses, so a stale I-cache would
 * run the wrong one and return the wrong code) and loopback TCP.
 */
static double best_of(double (*fn)(void))
{
	double b = 1e30, t;
	int i;

	for (i = 0; i < 3; i++) {
		t = fn();
		if (t < b)
			b = t;
	}
	return b;
}

static double b_syscall(void)
{
	double t0 = now();
	int i;

	for (i = 0; i < 200000; i++)
		getppid();
	return (now() - t0) / 200000 * 1e9;	/* ns */
}

static double b_pipe(void)
{
	int a[2], b[2], i;
	char c = 0;
	double t0;
	pid_t p;

	if (pipe(a) || pipe(b))
		return -1;
	p = fork();
	if (!p) {
		for (i = 0; i < 20000; i++)
			if (read(a[0], &c, 1) != 1 || write(b[1], &c, 1) != 1)
				break;
		_exit(0);
	}
	t0 = now();
	for (i = 0; i < 20000; i++)
		if (write(a[1], &c, 1) != 1 || read(b[0], &c, 1) != 1)
			break;
	t0 = now() - t0;
	waitpid(p, NULL, 0);
	close(a[0]); close(a[1]); close(b[0]); close(b[1]);
	return t0 / 20000 * 1e6;	/* us per round trip */
}

static double b_fork(void)
{
	double t0 = now();
	int i;

	for (i = 0; i < 1000; i++) {
		pid_t p = fork();

		if (!p)
			_exit(0);
		waitpid(p, NULL, 0);
	}
	return (now() - t0) / 1000 * 1e6;	/* us */
}

static int exec_bad;

static double b_exec(void)
{
	double t0 = now();
	int i, st;

	for (i = 0; i < 300; i++) {
		const char *prog = i & 1 ? "/t2" : "/t1";
		pid_t p = fork();

		if (!p) {
			execl(prog, prog, (char *)NULL);
			_exit(99);
		}
		waitpid(p, &st, 0);
		if (!WIFEXITED(st) || WEXITSTATUS(st) != (i & 1 ? 22 : 11))
			exec_bad++;
	}
	return (now() - t0) / 300 * 1e6;	/* us */
}

static double b_lo(void)
{
	static char buf[65536];
	struct sockaddr_in a = { .sin_family = AF_INET, .sin_port = htons(5099) };
	unsigned long long total = 0, want = 32ULL << 20;
	int one = 1, ls, c, s;
	double t0;
	pid_t p;
	ssize_t n;

	inet_pton(AF_INET, "127.0.0.1", &a.sin_addr);
	ls = socket(AF_INET, SOCK_STREAM, 0);
	setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
	if (bind(ls, (struct sockaddr *)&a, sizeof(a)) || listen(ls, 1))
		return -1;
	p = fork();
	if (!p) {
		s = socket(AF_INET, SOCK_STREAM, 0);
		if (connect(s, (struct sockaddr *)&a, sizeof(a)))
			_exit(1);
		while (total < want && (n = write(s, buf, sizeof(buf))) > 0)
			total += n;
		_exit(0);
	}
	c = accept(ls, NULL, NULL);
	t0 = now();
	while ((n = read(c, buf, sizeof(buf))) > 0)
		total += n;
	t0 = now() - t0;
	close(c);
	close(ls);
	waitpid(p, NULL, 0);
	return total / t0 / 1e6;	/* MB/s */
}

static void benchmarks(void)
{
	double lo = 0, t;
	int i;

	for (i = 0; i < 3; i++) {	/* throughput: best is highest */
		t = b_lo();
		if (t > lo)
			lo = t;
	}
	printf("bench: syscall %.0f ns, pipe round trip %.1f us, fork %.0f us, fork+exec %.0f us (%d wrong exits), loopback TCP %.1f MB/s\n",
	       best_of(b_syscall), best_of(b_pipe), best_of(b_fork),
	       best_of(b_exec), exec_bad, lo);
}

/*
 * SMP checks: which CPUs are online; a CPU-bound loop on both CPUs at once
 * against one; and stress for what SMP relies on, two threads pinned to
 * different CPUs each time: atomic increments (LL/SC), a mutex, message
 * passing through release/acquire, and TLB shootdowns (one thread maps,
 * fills and unmaps memory while the other keeps checking its own).
 */
static void pin(int cpu)
{
	cpu_set_t m;

	CPU_ZERO(&m);
	CPU_SET(cpu, &m);
	sched_setaffinity(0, sizeof(m), &m);
}

static volatile unsigned long spin_sink;

static void spin(void)
{
	unsigned long i, x = 0;

	for (i = 0; i < 100000000; i++)
		x += i ^ (x >> 3);
	spin_sink = x;
}

static double spin_on(int ncpu)
{
	double t0 = now();
	int i;

	for (i = 0; i < ncpu; i++)
		if (!fork()) {
			pin(i);
			spin();
			_exit(0);
		}
	for (i = 0; i < ncpu; i++)
		wait(NULL);
	return now() - t0;
}

#define SMP_N	2000000

static unsigned long at_count, mx_count;
static pthread_mutex_t mx = PTHREAD_MUTEX_INITIALIZER;
static volatile int stop_flag;

/* message passing: payload written, then published with release */
static int mp_data[16];
static int mp_seq, mp_ack;
static unsigned long mp_bad;

/* TLB shootdowns */
static unsigned long tlb_bad, tlb_maps;

static void *smp_thread(void *arg)
{
	long id = (long)arg;
	int i, k, v;

	pin(id);

	for (i = 0; i < SMP_N; i++)
		__atomic_fetch_add(&at_count, 1, __ATOMIC_RELAXED);
	for (i = 0; i < SMP_N / 4; i++) {
		pthread_mutex_lock(&mx);
		mx_count++;
		pthread_mutex_unlock(&mx);
	}

	/* message passing: thread 0 sends, thread 1 checks */
	for (v = 1; v <= 200000; v++) {
		if (id == 0) {
			for (k = 0; k < 16; k++)
				mp_data[k] = v;
			__atomic_store_n(&mp_seq, v, __ATOMIC_RELEASE);
			while (__atomic_load_n(&mp_ack, __ATOMIC_ACQUIRE) != v)
				;
		} else {
			while (__atomic_load_n(&mp_seq, __ATOMIC_ACQUIRE) != v)
				;
			for (k = 0; k < 16; k++)
				if (mp_data[k] != v)
					mp_bad++;
			__atomic_store_n(&mp_ack, v, __ATOMIC_RELEASE);
		}
	}

	/* TLB shootdowns: thread 0 maps and unmaps, thread 1 checks a buffer */
	if (id == 0) {
		double t0 = now();

		while (now() - t0 < 3) {
			unsigned int *p = mmap(NULL, 65536, PROT_READ | PROT_WRITE,
					       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);

			if (p == MAP_FAILED)
				break;
			for (k = 0; k < 16384; k += 1024)
				p[k] = k ^ 0x5a5a5a5a;
			for (k = 0; k < 16384; k += 1024)
				if (p[k] != (k ^ 0x5a5a5a5a))
					tlb_bad++;
			munmap(p, 65536);
			tlb_maps++;
		}
		stop_flag = 1;
	} else {
		static unsigned int buf[65536];
		unsigned int r = 0;

		while (!stop_flag) {
			for (k = 0; k < 65536; k += 1024)
				buf[k] = r + k;
			for (k = 0; k < 65536; k += 1024)
				if (buf[k] != r + k)
					tlb_bad++;
			r++;
		}
	}
	return NULL;
}

/*
 * Cross-CPU instruction cache coherence: thread 1 (CPU 1) keeps running a
 * function in a buffer that thread 0 (CPU 0) rewrites, flushing it with
 * cacheflush() on its own CPU, before telling thread 1 to call it again.
 * Thread 1 must then get the new value. When the kernel performs the
 * flush only on the calling CPU, this holds only if the hardware applies
 * cache instructions to both cores.
 */
#define XC_N	20000

static unsigned int *xc_code;
static int xc_gen, xc_ack;
static unsigned long xc_stale;

static void *xc_thread(void *arg)
{
	long id = (long)arg;
	int g;

	pin(id);
	for (g = 1; g <= XC_N; g++) {
		if (id == 0) {
			xc_code[0] = 0x24020000 | (g & 0x7fff);	/* li v0, g */
			cacheflush(xc_code, 16, BCACHE);
			__atomic_store_n(&xc_gen, g, __ATOMIC_RELEASE);
			while (__atomic_load_n(&xc_ack, __ATOMIC_ACQUIRE) != g)
				;
		} else {
			int (*fn)(void) = (int (*)(void))xc_code;

			while (__atomic_load_n(&xc_gen, __ATOMIC_ACQUIRE) != g)
				fn();	/* keep the old code in this CPU's cache */
			if (fn() != (g & 0x7fff))
				xc_stale++;
			__atomic_store_n(&xc_ack, g, __ATOMIC_RELEASE);
		}
	}
	return NULL;
}

static void icache_check(void)
{
	pthread_t t[2];
	long i;

	xc_code = mmap(NULL, 4096, PROT_READ | PROT_WRITE | PROT_EXEC,
		       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (xc_code == MAP_FAILED)
		return;
	xc_code[0] = 0x24020000;	/* li v0, 0 */
	xc_code[1] = 0x03e00008;	/* jr ra */
	xc_code[2] = 0;			/* nop */
	cacheflush(xc_code, 16, BCACHE);
	for (i = 0; i < 2; i++)
		pthread_create(&t[i], NULL, xc_thread, (void *)i);
	for (i = 0; i < 2; i++)
		pthread_join(t[i], NULL);
	printf("smp: code rewritten on CPU 0 and run on CPU 1 %d times: %lu stale: %s\n",
	       XC_N, xc_stale, xc_stale ? "BAD" : "ok");
}

static unsigned long ipi_total(void)
{
	char line[256];
	unsigned long a = 0, b = 0;
	FILE *f = fopen("/proc/interrupts", "r");

	if (!f)
		return 0;
	while (fgets(line, sizeof(line), f))
		if (strstr(line, "ipi"))
			sscanf(line, " %*d: %lu %lu", &a, &b);
	fclose(f);
	return a + b;
}

static void show_interrupts(void)
{
	char line[256];
	FILE *f = fopen("/proc/interrupts", "r");

	if (!f)
		return;
	while (fgets(line, sizeof(line), f))
		if (strstr(line, "CPU0") || strstr(line, "ipi") ||
		    strstr(line, "ost"))
			printf("irq: %s", line);
	fclose(f);
}

static pid_t mem_pid;

static void smp_check(void)
{
	pthread_t t[2];
	double t1, t2;
	long i;

	printf("--- smp\n");
	/* the memory test in the background would take a CPU */
	kill(mem_pid, SIGKILL);
	waitpid(mem_pid, NULL, 0);
	printf("smp: online %s, possible %s\n",
	       line_of("/sys/devices/system/cpu/online"),
	       line_of("/sys/devices/system/cpu/possible"));
	t1 = spin_on(1);
	t2 = spin_on(2);
	printf("smp: loop on 1 CPU %.2f s, the same loop on 2 CPUs at once %.2f s: %.2fx the work per second\n",
	       t1, t2, 2 * t1 / t2);

	for (i = 0; i < 2; i++)
		pthread_create(&t[i], NULL, smp_thread, (void *)i);
	for (i = 0; i < 2; i++)
		pthread_join(t[i], NULL);
	printf("smp: atomic %lu/%d, mutex %lu/%d, message passing %lu bad, %lu maps, %lu bad words: %s\n",
	       at_count, 2 * SMP_N, mx_count, 2 * (SMP_N / 4), mp_bad,
	       tlb_maps, tlb_bad,
	       at_count == 2 * SMP_N && mx_count == 2 * (SMP_N / 4) &&
	       !mp_bad && !tlb_bad ? "ok" : "BAD");
	icache_check();
	show_interrupts();

	/* the same benchmarks with every process on CPU 0 */
	if (!fork()) {
		pin(0);
		unsigned long i0;

		printf("pinned to CPU 0: ");
		benchmarks();
		i0 = ipi_total();
		b_fork();
		printf("pinned to CPU 0: %.1f IPIs per fork\n",
		       (ipi_total() - i0) / 1000.0);
		i0 = ipi_total();
		b_exec();
		printf("pinned to CPU 0: %.1f IPIs per fork+exec\n",
		       (ipi_total() - i0) / 300.0);
		_exit(0);
	}
	wait(NULL);
}

int main(void)
{
	int s, i, n, ls, lo;
	struct pollfd p[2];

	mkdir("/dev", 0755);
	mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
	mkdir("/proc", 0755);
	mount("proc", "/proc", "proc", 0, NULL);
	mkdir("/sys", 0755);
	mount("sysfs", "/sys", "sysfs", 0, NULL);
	mount("debugfs", "/sys/kernel/debug", "debugfs", 0, NULL);
	setvbuf(stdout, NULL, _IONBF, 0);

	printf("\n=== netusb-test\n");
	tls_check();
	mem_pid = fork();
	if (mem_pid == 0)
		mem_check();
	sleep(3);	/* let the fill finish before the USB tests */
	fp_check();

	/* the hub, then its devices, enumerate within a few seconds */
	for (i = 0; i < 150; i++) {
		if (has_usb("0bda", "c811") && has_usb("1bcf", "2281"))
			break;
		usleep(100000);
	}
	printf("--- usb after %.1f s\n", i / 10.0);
	n = list_usb();
	printf("usb: %d devices; hub %s, camera %s, wifi %s\n", n,
	       has_usb("05e3", "0610") ? "yes" : "NO",
	       has_usb("1bcf", "2281") ? "yes" : "NO",
	       has_usb("0bda", "c811") ? "yes" : "NO");
	show_phy_regs();

	s = socket(AF_INET, SOCK_DGRAM, 0);
	if_up(s, "lo");

	printf("--- wlan0\n");
	for (i = 0; i < 50 && access("/sys/class/net/wlan0", F_OK); i++)
		usleep(100000);
	if (access("/sys/class/net/wlan0", F_OK)) {
		printf("wlan0: missing\n");
	} else {
		char drv[64];

		link_name("/sys/class/net/wlan0/device/driver", drv, sizeof(drv));
		printf("wlan0: driver %s, MAC %s\n", drv,
		       line_of("/sys/class/net/wlan0/address"));
		for (i = 1; i <= 5; i++) {
			n = if_up(s, "wlan0");
			printf("wlan0: up, try %d: %s\n", i, n ? strerror(-n) : "ok");
			if (!n)
				break;
			sleep(1);
		}
		if (!n) {
			wifi_cycles(s, 5);
			if_up(s, "wlan0");
			wifi_scan(s);
		}
	}

	printf("--- eth0\n");
	setup_eth(s);

	ls = listen_on(5001);
	lo = listen_on(5002);
	benchmarks();
	smp_check();
	printf("=== netusb ready: sink on %s:5001, source on :5002\n", ETH_ADDR);
	p[0] = (struct pollfd){ .fd = ls, .events = POLLIN };
	p[1] = (struct pollfd){ .fd = lo, .events = POLLIN };
	for (;;) {
		if (poll(p, 2, -1) <= 0)
			continue;
		for (i = 0; i < 2; i++) {
			int c;

			if (!(p[i].revents & POLLIN))
				continue;
			c = accept(p[i].fd, NULL, NULL);
			if (c < 0)
				continue;
			if (i == 0)
				sink(c);
			else
				source(c);
			close(c);
		}
	}
}
