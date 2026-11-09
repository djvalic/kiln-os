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
 *   mipsel-linux-gcc -static -O2 -o init netusb-test.c
 */
#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <net/if.h>
#include <net/if_arp.h>
#include <linux/wireless.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <stdint.h>
#include <signal.h>
#include <pthread.h>
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
	if (fork() == 0)
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
