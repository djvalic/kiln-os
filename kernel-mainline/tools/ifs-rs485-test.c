// SPDX-License-Identifier: GPL-2.0
/*
 * RS-485 test for the AD5X filament changer (IFS) on a mainline test kernel.
 * Runs as /init of a test initramfs (no other userspace): prints the RS-485
 * setup of the IFS port and, with the settings applied at boot as Klipper
 * finds them, fetches the MCU's whole data dictionary the way Klipper's host
 * does when it connects (identify requests until a short reply), checking
 * every frame (length, sequence byte, CRC16). The dictionary is printed as
 * hex between "DICT BEGIN" and "DICT END" for checking on a PC (zlib, JSON).
 * Then the same request with RS-485 switched off, which must go unanswered.
 *
 * Also fetches the dictionaries of the motion controller (ttyS2) and the
 * toolhead board (ttyS5), Klipper MCUs at 230400 baud, a rate the X2600
 * reaches only with its fractional divider; each port's divisor registers
 * are printed.
 *
 * Needs the IFS running Klipper firmware (115200 baud).
 *
 *   mipsel-linux-gcc -static -O2 -o init ifs-rs485-test.c
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/serial.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define PORT		"/dev/ttyS4"
#define SYNC		0x7e
#define MSG_HEADER	2	/* len, seq */
#define MSG_TRAILER	3	/* crc16, sync */
#define MSG_MIN		(MSG_HEADER + MSG_TRAILER)
#define MSG_SEQ_MASK	0x0f
#define MSG_DEST	0x10

static uint16_t crc16_ccitt(const uint8_t *buf, unsigned int len)
{
	uint16_t crc = 0xffff;

	while (len--) {
		uint8_t data = *buf++;

		data ^= crc & 0xff;
		data ^= data << 4;
		crc = ((((uint16_t)data << 8) | (crc >> 8)) ^
		       (uint8_t)(data >> 4) ^ ((uint16_t)data << 3));
	}
	return crc;
}

/* Klipper's variable-length integer encoding */
static int encode_int(uint8_t *p, int32_t v)
{
	int n = 0;

	if (v >= 0xc000000 || v < -0x4000000)
		p[n++] = 0x80 | ((v >> 28) & 0x7f);
	if (v >= 0x180000 || v < -0x80000)
		p[n++] = 0x80 | ((v >> 21) & 0x7f);
	if (v >= 0x3000 || v < -0x1000)
		p[n++] = 0x80 | ((v >> 14) & 0x7f);
	if (v >= 0x60 || v < -0x20)
		p[n++] = 0x80 | ((v >> 7) & 0x7f);
	p[n++] = v & 0x7f;
	return n;
}

static uint32_t parse_int(const uint8_t **pp)
{
	const uint8_t *p = *pp;
	uint8_t c = *p++;
	uint32_t v = c & 0x7f;

	if ((c & 0x60) == 0x60)
		v |= -0x20;
	while (c & 0x80) {
		c = *p++;
		v = (v << 7) | (c & 0x7f);
	}
	*pp = p;
	return v;
}

#define IDENTIFY_COUNT	40

/* identify offset=OFFSET count=40 (message id 1) */
static int build_identify(uint8_t *blk, unsigned int seq, unsigned int offset)
{
	uint16_t crc;
	int n = 0;

	blk[n++] = 0;
	blk[n++] = MSG_DEST | (seq & MSG_SEQ_MASK);
	blk[n++] = 1;
	n += encode_int(blk + n, offset);
	blk[n++] = IDENTIFY_COUNT;
	blk[0] = n + MSG_TRAILER;
	crc = crc16_ccitt(blk, n);
	blk[n++] = crc >> 8;
	blk[n++] = crc & 0xff;
	blk[n++] = SYNC;
	return n;
}

static void hexdump(const char *tag, const uint8_t *b, int n)
{
	int i;

	printf("%s (%d):", tag, n);
	for (i = 0; i < n && i < 48; i++)
		printf(" %02x", b[i]);
	printf("%s\n", n > 48 ? " ..." : "");
}

/* Read for up to ms milliseconds, after the first byte until 50 ms of silence */
static int read_reply(int fd, uint8_t *buf, int size, int ms)
{
	int n = 0;

	while (n < size) {
		struct timeval tv = { 0, (n ? 50 : ms) * 1000 };
		fd_set rf;
		int r;

		FD_ZERO(&rf);
		FD_SET(fd, &rf);
		if (select(fd + 1, &rf, NULL, NULL, &tv) <= 0)
			break;
		r = read(fd, buf + n, size - n);
		if (r <= 0)
			break;
		n += r;
	}
	return n;
}

/*
 * Check the frames in buf. Returns the number of valid frames and, through
 * next_seq, the sequence the MCU expects next (from the last valid frame).
 */
static const uint8_t *last_content;
static int last_content_len;

static int check_frames(const uint8_t *buf, int n, int *next_seq, int *payload)
{
	int i = 0, good = 0;

	while (i < n) {
		int len = buf[i];
		uint16_t crc;

		if (len < MSG_MIN || len > 64 || i + len > n || buf[i + len - 1] != SYNC) {
			i++;		/* resync */
			continue;
		}
		crc = crc16_ccitt(buf + i, len - MSG_TRAILER);
		if ((buf[i + len - 3] << 8 | buf[i + len - 2]) != crc ||
		    (buf[i + 1] & ~MSG_SEQ_MASK) != MSG_DEST) {
			i++;
			continue;
		}
		good++;
		*next_seq = buf[i + 1] & MSG_SEQ_MASK;
		*payload += len - MSG_MIN;
		if (len > MSG_MIN) {
			last_content = buf + i + MSG_HEADER;
			last_content_len = len - MSG_MIN;
		}
		printf("  frame: len %d seq %d %s\n", len, buf[i + 1] & MSG_SEQ_MASK,
		       len == MSG_MIN ? "(ack/nak, no data)" : "(with data)");
		i += len;
	}
	return good;
}

static int set_rs485(int fd, int on)
{
	struct serial_rs485 rs;

	memset(&rs, 0, sizeof(rs));
	if (ioctl(fd, TIOCGRS485, &rs) < 0) {
		printf("TIOCGRS485: %s\n", strerror(errno));
		return -1;
	}
	if (on)
		rs.flags |= SER_RS485_ENABLED | SER_RS485_RTS_ON_SEND;
	else
		rs.flags &= ~SER_RS485_ENABLED;
	if (ioctl(fd, TIOCSRS485, &rs) < 0) {
		printf("TIOCSRS485: %s\n", strerror(errno));
		return -1;
	}
	ioctl(fd, TIOCGRS485, &rs);
	printf("rs485: flags 0x%x (%s%s%s) delay before %u ms, after %u ms\n",
	       rs.flags, rs.flags & SER_RS485_ENABLED ? "enabled" : "disabled",
	       rs.flags & SER_RS485_RTS_ON_SEND ? ", RTS on send" : "",
	       rs.flags & SER_RS485_RX_DURING_TX ? ", rx during tx" : "",
	       rs.delay_rts_before_send, rs.delay_rts_after_send);
	return 0;
}

/* Up to three identify requests; returns the number of frames with data */
static int identify_round(int fd, const char *name)
{
	uint8_t blk[16], buf[512];
	int seq = 0, try, data_frames = 0;

	printf("--- %s\n", name);
	tcflush(fd, TCIOFLUSH);
	for (try = 0; try < 3; try++) {
		int n, len, next = -1, payload = 0, good;

		len = build_identify(blk, seq, 0);
		if (write(fd, blk, len) != len)
			printf("write: %s\n", strerror(errno));
		tcdrain(fd);
		hexdump("  sent", blk, len);
		n = read_reply(fd, buf, sizeof(buf), 500);
		if (!n) {
			printf("  no reply\n");
			continue;
		}
		hexdump("  got", buf, n);
		good = check_frames(buf, n, &next, &payload);
		printf("  %d valid frame(s), %d payload bytes\n", good, payload);
		if (payload)
			data_frames++;
		if (next >= 0 && !payload)
			seq = next;	/* the MCU told us which sequence it expects */
		else if (payload)
			break;
	}
	return data_frames;
}

/*
 * Fetch the data dictionary as Klipper's host does: identify at increasing
 * offsets until a reply carries fewer than IDENTIFY_COUNT bytes. Returns its
 * size, or -1.
 */
static int fetch_dictionary(int fd, uint8_t *dict, int size)
{
	uint8_t blk[16], buf[512];
	int seq = 0, total = 0, tries = 0;

	printf("--- data dictionary (identify loop, settings from boot)\n");
	tcflush(fd, TCIOFLUSH);
	{
		/* end any half-received block on the MCU, as Klipper does */
		static const uint8_t sync[4] = { SYNC, SYNC, SYNC, SYNC };

		if (write(fd, sync, sizeof(sync)) < 0)
			printf("write: %s\n", strerror(errno));
		tcdrain(fd);
	}
	while (total < size && tries < 20) {
		int n, len, next = -1, payload = 0;
		const uint8_t *p, *end;
		uint32_t msgid, offset, dlen;

		len = build_identify(blk, seq, total);
		if (write(fd, blk, len) != len)
			return -1;
		tcdrain(fd);
		last_content = NULL;
		n = read_reply(fd, buf, sizeof(buf), 500);
		if (!check_frames(buf, n, &next, &payload) || !last_content) {
			tries++;
			if (next >= 0)
				seq = next;	/* resync with the MCU's sequence */
			continue;
		}
		seq = next;
		p = last_content;
		end = p + last_content_len;
		msgid = parse_int(&p);
		offset = parse_int(&p);
		dlen = *p++;
		if (msgid != 0 || offset != (uint32_t)total || p + dlen > end) {
			printf("  unexpected reply: msgid %u offset %u len %u\n",
			       msgid, offset, dlen);
			tries++;
			continue;
		}
		memcpy(dict + total, p, dlen);
		total += dlen;
		if (dlen < IDENTIFY_COUNT)
			return total;
	}
	return -1;
}

/* GPIO port C (PC3 = driver enable) and UART4, read through /dev/mem */
static volatile uint32_t *gpb, *gpc, *uart4, *gpio_all;

static void map_regs(void)
{
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	void *p;

	if (fd < 0) {
		printf("/dev/mem: %s\n", strerror(errno));
		return;
	}
	p = mmap(NULL, 0x5000, PROT_READ, MAP_SHARED, fd, 0x13601000);
	if (p != MAP_FAILED)
		gpio_all = p;
	p = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED, fd, 0x13602000);
	if (p != MAP_FAILED)
		gpb = p;
	p = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED, fd, 0x13603000);
	if (p != MAP_FAILED)
		gpc = p;
	p = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x10034000);
	if (p != MAP_FAILED)
		uart4 = p;
}

static void show_regs(const char *when)
{
	if (gpb)
		printf("  [%s] PB: int %08x msk %08x pat1 %08x pat0 %08x pin %08x\n", when,
		       gpb[0x10 / 4], gpb[0x20 / 4], gpb[0x30 / 4], gpb[0x40 / 4],
		       gpb[0x00 / 4]);
	if (gpc)
		printf("  [%s] PC3: pin %u int %u msk %u pat1 %u pat0 %u\n", when,
		       (gpc[0x00 / 4] >> 3) & 1, (gpc[0x10 / 4] >> 3) & 1,
		       (gpc[0x20 / 4] >> 3) & 1, (gpc[0x30 / 4] >> 3) & 1,
		       (gpc[0x40 / 4] >> 3) & 1);
	if (uart4)
		printf("  [%s] UART4: lcr %02x mcr %02x lsr %02x ier %02x umr %02x uacr %03x\n",
		       when, uart4[3] & 0xff, uart4[4] & 0xff, uart4[5] & 0xff,
		       uart4[1] & 0xff, uart4[9] & 0xff, uart4[10] & 0xfff);
}

/* Every GPIO port and UART4's registers, to compare with the stock kernel */
static void dump_all(void)
{
	int port;

	for (port = 0; gpio_all && port < 5; port++) {
		volatile uint32_t *g = gpio_all + port * 0x1000 / 4;

		printf("P%c: int %08x msk %08x pat1 %08x pat0 %08x pin %08x\n",
		       'A' + port, g[0x10 / 4], g[0x20 / 4], g[0x30 / 4],
		       g[0x40 / 4], g[0x00 / 4]);
	}
	if (uart4)
		printf("UART4: ier %02x iir %02x lcr %02x mcr %02x lsr %02x msr %02x spr %02x isr %02x umr %02x uacr %03x\n",
		       uart4[1] & 0xff, uart4[2] & 0xff, uart4[3] & 0xff,
		       uart4[4] & 0xff, uart4[5] & 0xff, uart4[6] & 0xff,
		       uart4[7] & 0xff, uart4[8] & 0xff, uart4[9] & 0xff,
		       uart4[10] & 0xfff);
}

/* The divisor latch, behind LCR.DLAB: set it briefly, read, restore */
static void show_divisor(void)
{
	uint32_t lcr, dll, dlm;

	if (!uart4)
		return;
	lcr = uart4[3];
	uart4[3] = lcr | 0x80;
	dll = uart4[0] & 0xff;
	dlm = uart4[1] & 0xff;
	uart4[3] = lcr;
	printf("UART4 divisor: dll %u dlm %u -> %u, umr %u: %u baud from 24 MHz\n",
	       dll, dlm, dlm << 8 | dll, uart4[9] & 0xff,
	       24000000 / ((dlm << 8 | dll) * (uart4[9] & 0xff ? uart4[9] & 0xff : 16)));
}

static void show_counters(const char *when)
{
	char line[256];
	FILE *f;

	printf("  [%s]\n", when);
	f = fopen("/proc/tty/driver/serial", "r");
	while (f && fgets(line, sizeof(line), f))
		if (!strncmp(line, "4:", 2))
			printf("    %s", line);
	if (f)
		fclose(f);
	f = fopen("/proc/interrupts", "r");
	while (f && fgets(line, sizeof(line), f))
		if (strstr(line, "10034000") || strstr(line, "ttyS4") || strstr(line, " 43:"))
			printf("    %s", line);
	if (f)
		fclose(f);
}

/*
 * A software logic analyser: after sending one identify request, poll
 * PC3 (driver enable), PB25 (TX) and PB24 (RX) and log every change with
 * its time, for 6 ms.
 */
static void trace_request(int fd)
{
	static struct { uint32_t us; uint8_t v; } ev[600];
	uint8_t blk[16];
	struct timespec t0, t;
	uint32_t us = 0, n = 0, polls = 0;
	int len, i, last = -1;

	if (!gpb || !gpc)
		return;
	len = build_identify(blk, 0, 0);
	tcflush(fd, TCIOFLUSH);
	clock_gettime(CLOCK_MONOTONIC, &t0);
	if (write(fd, blk, len) != len)
		printf("write: %s\n", strerror(errno));
	while (us < 6000 && n < 600) {
		int v = ((gpc[0] >> 3) & 1) << 2 | ((gpb[0] >> 25) & 1) << 1 |
			((gpb[0] >> 24) & 1);

		polls++;
		if (v != last || (polls & 0x3ff) == 0) {
			clock_gettime(CLOCK_MONOTONIC, &t);
			us = (t.tv_sec - t0.tv_sec) * 1000000 +
			     (t.tv_nsec - t0.tv_nsec) / 1000;
			if (v != last) {
				ev[n].us = us;
				ev[n].v = v;
				n++;
				last = v;
			}
		}
	}
	printf("--- trace of one request (%u polls): time us  DE TX RX\n", polls);
	for (i = 0; i < n; i++)
		printf("  %6u  %u  %u  %u\n", ev[i].us, ev[i].v >> 2 & 1,
		       ev[i].v >> 1 & 1, ev[i].v & 1);
}

/* PC3 while a burst of sync bytes (ignored by Klipper) is being sent */
static void sample_during_tx(int fd)
{
	static uint8_t burst[400];

	memset(burst, SYNC, sizeof(burst));
	show_regs("idle");
	if (write(fd, burst, sizeof(burst)) < 0)
		printf("write: %s\n", strerror(errno));
	usleep(5000);
	show_regs("mid-tx");
	tcdrain(fd);
	usleep(20000);
	show_regs("after");
}

/* RS-485 off, RTS switched by hand around the request, RTS high = level */
static int manual_round(int fd, int level)
{
	uint8_t blk[16], buf[512];
	int bit = TIOCM_RTS, len, n, next = -1, payload = 0, good;

	printf("--- manual: RTS %s while sending\n", level ? "asserted" : "deasserted");
	tcflush(fd, TCIOFLUSH);
	ioctl(fd, level ? TIOCMBIC : TIOCMBIS, &bit);	/* idle */
	usleep(2000);
	ioctl(fd, level ? TIOCMBIS : TIOCMBIC, &bit);	/* send */
	len = build_identify(blk, 0, 0);
	if (write(fd, blk, len) != len)
		printf("write: %s\n", strerror(errno));
	tcdrain(fd);
	usleep(200);
	ioctl(fd, level ? TIOCMBIC : TIOCMBIS, &bit);	/* receive */
	n = read_reply(fd, buf, sizeof(buf), 500);
	if (!n) {
		printf("  no reply\n");
		return 0;
	}
	hexdump("  got", buf, n);
	good = check_frames(buf, n, &next, &payload);
	printf("  %d valid frame(s)\n", good);
	return good;
}

/* Divisor latch, UMR and UACR of the UART at phys, through /dev/mem */
static void show_divisor_at(const char *name, off_t phys)
{
	volatile uint32_t *u;
	uint32_t lcr, dll, dlm, umr, uacr, div;
	int fd = open("/dev/mem", O_RDWR | O_SYNC);

	if (fd < 0)
		return;
	u = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, phys);
	close(fd);
	if (u == MAP_FAILED)
		return;
	lcr = u[3];
	u[3] = lcr | 0x80;
	dll = u[0] & 0xff;
	dlm = u[1] & 0xff;
	u[3] = lcr;
	umr = u[9] & 0x1f;
	uacr = u[10] & 0xfff;
	div = dlm << 8 | dll;
	printf("%s divisor: dll %u dlm %u umr %u uacr %03x: %u baud from 24 MHz\n",
	       name, dll, dlm, umr, uacr,
	       div && umr ? 24000000 / (div * umr) : 0);
	munmap((void *)u, 0x1000);
}

static int open_port(const char *path, speed_t speed)
{
	struct termios tio;
	int fd = open(path, O_RDWR | O_NOCTTY);

	if (fd < 0) {
		printf("open %s: %s\n", path, strerror(errno));
		return -1;
	}
	tcgetattr(fd, &tio);
	cfmakeraw(&tio);
	tio.c_cflag |= CLOCAL | CREAD;
	tio.c_cflag &= ~(CRTSCTS | CSTOPB | PARENB);
	cfsetispeed(&tio, speed);
	cfsetospeed(&tio, speed);
	tcsetattr(fd, TCSANOW, &tio);
	return fd;
}

/* Fetch an MCU's dictionary and print it as DICT BEGIN name ... DICT END */
static void mcu_dictionary(const char *name, const char *path, speed_t speed,
			   off_t phys)
{
	static uint8_t dict[65536];
	int fd, i, n;

	printf("=== %s (%s)\n", name, path);
	fd = open_port(path, speed);
	if (fd < 0)
		return;
	show_divisor_at(name, phys);
	n = fetch_dictionary(fd, dict, sizeof(dict));
	printf("%s dictionary: %d bytes%s\n", name, n, n > 0 ? "" : " (FAILED)");
	if (n > 0) {
		printf("DICT BEGIN %s\n", name);
		for (i = 0; i < n; i++)
			printf("%02x%s", dict[i], (i % 32 == 31) ? "\n" : "");
		printf("\nDICT END\n");
	}
	close(fd);
}

int main(void)
{
	struct termios tio;
	int fd, with, without;

	mkdir("/dev", 0755);
	mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
	mkdir("/proc", 0755);
	mount("proc", "/proc", "proc", 0, NULL);
	setvbuf(stdout, NULL, _IONBF, 0);

	{
		/* The clock tree as the CGU driver computes it */
		char line[256];
		FILE *f;

		mkdir("/sys", 0755);
		mount("sysfs", "/sys", "sysfs", 0, NULL);
		mount("debugfs", "/sys/kernel/debug", "debugfs", 0, NULL);
		f = fopen("/sys/kernel/debug/clk/clk_summary", "r");
		printf("=== clock tree\n");
		while (f && fgets(line, sizeof(line), f))
			printf("%s", line);
		if (f)
			fclose(f);
	}
	mcu_dictionary("mcu", "/dev/ttyS2", B230400, 0x10032000);
	mcu_dictionary("eboard", "/dev/ttyS5", B230400, 0x10035000);

	printf("\n=== ifs-rs485-test on %s\n", PORT);
	fd = open(PORT, O_RDWR | O_NOCTTY);
	if (fd < 0) {
		printf("open %s: %s\n", PORT, strerror(errno));
		goto out;
	}
	tcgetattr(fd, &tio);
	cfmakeraw(&tio);
	tio.c_cflag |= CLOCAL | CREAD;
	tio.c_cflag &= ~(CRTSCTS | CSTOPB | PARENB);
	cfsetispeed(&tio, B115200);
	cfsetospeed(&tio, B115200);
	tcsetattr(fd, TCSANOW, &tio);

	map_regs();
	printf("--- registers (mainline)\n");
	dump_all();
	show_divisor();
	show_counters("before");
	trace_request(fd);
	printf("--- PC3 and UART4 around a transmission (RS-485 from boot)\n");
	sample_during_tx(fd);

	{
		static uint8_t dict[65536];
		int i, n;

		n = fetch_dictionary(fd, dict, sizeof(dict));
		printf("dictionary: %d bytes%s\n", n, n > 0 ? "" : " (FAILED)");
		if (n > 0) {
			printf("DICT BEGIN ifs\n");
			for (i = 0; i < n; i++)
				printf("%02x%s", dict[i], (i % 32 == 31) ? "\n" : "");
			printf("\nDICT END\n");
		}
	}

	show_counters("after the dictionary attempt");
	printf("as configured at boot:\n");
	set_rs485(fd, 1);
	with = identify_round(fd, "RS-485 on (driver enable on PC3)");

	set_rs485(fd, 0);
	without = identify_round(fd, "RS-485 off (transceiver never driven)");

	{
		int m1 = manual_round(fd, 1), m0 = manual_round(fd, 0);

		printf("=== manual: RTS high while sending %s, RTS low while sending %s\n",
		       m1 ? "ANSWERED" : "silent", m0 ? "ANSWERED" : "silent");
	}
	printf("=== result: identify answered with RS-485 %s, %s without it\n",
	       with ? "on: PASS" : "on: FAIL",
	       without ? "answered (unexpected)" : "silent (expected)");
	set_rs485(fd, 1);
	close(fd);
out:
	for (;;)
		pause();
}
