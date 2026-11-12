// SPDX-License-Identifier: GPL-2.0
/*
 * Read-only eMMC test for the AD5X on a mainline test kernel. Runs as /init
 * of a test initramfs (no other userspace).
 *
 * Before anything else reads the eMMC, every block device on it (the user
 * area, its partitions and the boot partitions) is set read-only with
 * BLKROSET, so nothing in this kernel can write to it. Then:
 *   - the card's bus settings (debugfs ios) and the GPT partition entries
 *   - a full read of one partition (EMMC_PART) with its CRC-32 (IEEE, as
 *     zlib.crc32) and the read rate; compare with a copy taken on stock
 *   - a read-only mount of that partition (squashfs) and its top directory
 *   - the device's write counter, which must still be 0
 *
 *   mipsel-linux-gcc -static -O2 -o init emmc-test.c
 */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define EMMC		"mmcblk0"
#define EMMC_PART	"mmcblk0p4"

static uint32_t crc_table[256];

static void crc32_init(void)
{
	uint32_t c;
	int i, k;

	for (i = 0; i < 256; i++) {
		c = i;
		for (k = 0; k < 8; k++)
			c = (c & 1) ? 0xedb88320 ^ (c >> 1) : c >> 1;
		crc_table[i] = c;
	}
}

static uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n)
{
	crc = ~crc;
	while (n--)
		crc = crc_table[(crc ^ *p++) & 0xff] ^ (crc >> 8);
	return ~crc;
}

static double now(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

static void cat(const char *path)
{
	char line[256];
	FILE *f = fopen(path, "r");

	if (!f) {
		printf("%s: %s\n", path, strerror(errno));
		return;
	}
	while (fgets(line, sizeof(line), f))
		printf("%s", line);
	fclose(f);
}

/* Set one block device read-only; returns 0 when it reads back as such */
static int set_ro(const char *name)
{
	char path[64];
	int fd, one = 1, ro = 0;

	snprintf(path, sizeof(path), "/dev/%s", name);
	fd = open(path, O_RDONLY);
	if (fd < 0) {
		printf("ro %s: open: %s\n", name, strerror(errno));
		return -1;
	}
	if (ioctl(fd, BLKROSET, &one) || ioctl(fd, BLKROGET, &ro) || !ro) {
		printf("ro %s: FAILED (%s)\n", name, strerror(errno));
		close(fd);
		return -1;
	}
	close(fd);
	printf("ro %s: ok\n", name);
	return 0;
}

static int set_all_ro(void)
{
	struct dirent *e;
	DIR *d = opendir("/sys/block");
	int bad = 0, n = 0;

	if (!d)
		return -1;
	/* the whole devices first: their partitions follow them */
	while ((e = readdir(d))) {
		if (strncmp(e->d_name, EMMC, strlen(EMMC)))
			continue;
		bad |= set_ro(e->d_name);
		n++;
	}
	closedir(d);

	d = opendir("/sys/block/" EMMC);
	while (d && (e = readdir(d))) {
		if (strncmp(e->d_name, EMMC "p", strlen(EMMC) + 1))
			continue;
		bad |= set_ro(e->d_name);
		n++;
	}
	if (d)
		closedir(d);
	return bad || !n ? -1 : 0;
}

static void show_gpt(void)
{
	uint8_t hdr[512], ent[128];
	uint32_t count, size, i, j;
	uint64_t lba;
	int fd = open("/dev/" EMMC, O_RDONLY);

	if (fd < 0 || pread(fd, hdr, 512, 512) != 512) {
		printf("gpt: read failed\n");
		goto out;
	}
	if (memcmp(hdr, "EFI PART", 8)) {
		printf("gpt: no signature\n");
		goto out;
	}
	memcpy(&lba, hdr + 72, 8);
	memcpy(&count, hdr + 80, 4);
	memcpy(&size, hdr + 84, 4);
	printf("gpt: entries at LBA %llu, %u of %u bytes\n",
	       (unsigned long long)lba, count, size);
	for (i = 0; i < count && i < 16 && size >= 128; i++) {
		uint64_t first, last;
		char name[37];

		if (pread(fd, ent, 128, lba * 512 + (uint64_t)i * size) != 128)
			break;
		memcpy(&first, ent + 32, 8);
		memcpy(&last, ent + 40, 8);
		if (!first && !last)
			continue;
		for (j = 0; j < 36; j++)	/* UTF-16LE, ASCII names */
			name[j] = ent[56 + 2 * j] ? ent[56 + 2 * j] : 0;
		name[36] = 0;
		printf("gpt %u: %-12s LBA %llu-%llu\n", i + 1, name,
		       (unsigned long long)first, (unsigned long long)last);
	}
out:
	if (fd >= 0)
		close(fd);
}

static int read_part(void)
{
	static uint8_t buf[1 << 20];
	uint64_t total = 0;
	uint32_t crc = 0;
	double t0, t;
	ssize_t n;
	int fd = open("/dev/" EMMC_PART, O_RDONLY);

	if (fd < 0) {
		printf("read %s: %s\n", EMMC_PART, strerror(errno));
		return -1;
	}
	t0 = now();
	while ((n = read(fd, buf, sizeof(buf))) > 0) {
		crc = crc32_update(crc, buf, n);
		total += n;
	}
	t = now() - t0;
	close(fd);
	if (n < 0) {
		printf("read %s: error after %llu bytes: %s\n", EMMC_PART,
		       (unsigned long long)total, strerror(errno));
		return -1;
	}
	printf("read %s: %llu bytes in %.2f s (%.1f MB/s), crc32 %08x\n",
	       EMMC_PART, (unsigned long long)total, t, total / t / 1e6, crc);
	return 0;
}

static void show_dir(const char *path)
{
	struct dirent *e;
	DIR *d = opendir(path);
	int n = 0;

	if (!d) {
		printf("%s: %s\n", path, strerror(errno));
		return;
	}
	printf("%s:", path);
	while ((e = readdir(d)))
		if (e->d_name[0] != '.') {
			printf(" %s", e->d_name);
			n++;
		}
	printf(" (%d entries)\n", n);
	closedir(d);
}

int main(void)
{
	char line[256];
	unsigned long long st[11] = { 0 };
	int i, ro;
	FILE *f;

	mkdir("/dev", 0755);
	mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
	mkdir("/proc", 0755);
	mount("proc", "/proc", "proc", 0, NULL);
	mkdir("/sys", 0755);
	mount("sysfs", "/sys", "sysfs", 0, NULL);
	mount("debugfs", "/sys/kernel/debug", "debugfs", 0, NULL);
	setvbuf(stdout, NULL, _IONBF, 0);
	crc32_init();

	printf("\n=== emmc-test\n");
	for (i = 0; i < 100 && access("/dev/" EMMC, F_OK); i++)
		usleep(100000);
	if (access("/dev/" EMMC, F_OK)) {
		printf("=== emmc result: FAIL (no /dev/%s)\n", EMMC);
		goto out;
	}

	ro = set_all_ro();
	if (ro) {
		printf("=== emmc result: FAIL (could not make it read-only; stopping)\n");
		goto out;
	}

	printf("--- ios\n");
	cat("/sys/kernel/debug/mmc0/ios");
	printf("--- partitions\n");
	cat("/proc/partitions");
	show_gpt();

	i = read_part();

	mkdir("/mnt", 0755);
	if (mount("/dev/" EMMC_PART, "/mnt", "squashfs", MS_RDONLY, NULL))
		printf("mount %s: %s\n", EMMC_PART, strerror(errno));
	else
		show_dir("/mnt");

	/* field 5: writes completed */
	f = fopen("/sys/block/" EMMC "/stat", "r");
	if (f && fgets(line, sizeof(line), f))
		sscanf(line, "%llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu",
		       &st[0], &st[1], &st[2], &st[3], &st[4], &st[5], &st[6],
		       &st[7], &st[8], &st[9], &st[10]);
	if (f)
		fclose(f);
	printf("stat: %llu reads, %llu writes\n", st[0], st[4]);
	printf("=== emmc result: %s (compare the crc32 with the stock copy)\n",
	       !i && !st[4] ? "read ok, no writes" : "FAIL");
out:
	for (;;)
		pause();
}
