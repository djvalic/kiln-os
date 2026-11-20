/* Read-only system queries (see sys.h) */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "sys.h"
#include "commands.h"
#include "i18n.h"

#include <arpa/inet.h>
#include <dirent.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <time.h>
#include <unistd.h>

bool sys_ip(const char *iface, char *buf, size_t cap)
{
	struct ifaddrs *ifa, *i;
	bool ok = false;
	if (getifaddrs(&ifa))
		return false;
	for (i = ifa; i && !ok; i = i->ifa_next) {
		if (!i->ifa_addr || i->ifa_addr->sa_family != AF_INET)
			continue;
		if (!(i->ifa_flags & IFF_UP))
			continue;
		if (iface ? strcmp(i->ifa_name, iface) : (i->ifa_flags & IFF_LOOPBACK) != 0)
			continue;
		ok = inet_ntop(AF_INET, &((struct sockaddr_in *)i->ifa_addr)->sin_addr,
			       buf, cap) != NULL;
	}
	freeifaddrs(ifa);
	return ok;
}

bool sys_main_ip(char *buf, size_t cap, char *iface, size_t icap)
{
	static const char *order[] = { "eth0", "wlan0", NULL };
	for (int k = 0; order[k]; k++)
		if (sys_ip(order[k], buf, cap)) {
			snprintf(iface, icap, "%s", order[k]);
			return true;
		}
	if (sys_ip(NULL, buf, cap)) {
		snprintf(iface, icap, "net");
		return true;
	}
	return false;
}

static bool read_small(const char *path, char *buf, size_t cap)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return false;
	ssize_t n = read(fd, buf, cap - 1);
	close(fd);
	if (n < 0)
		return false;
	buf[n] = 0;
	return true;
}

bool sys_part(const char *name, char *buf, size_t cap)
{
#ifdef RUI_FBDEV
	/* Only on the printer: laptop builds never look up block devices */
	const char *base = rui_get(PATH_SYS_BLOCK);
	DIR *d = opendir(base);
	if (!d)
		return false;
	struct dirent *e;
	bool ok = false;
	char want[64];
	snprintf(want, sizeof(want), "PARTNAME=%s\n", name);
	while (!ok && (e = readdir(d))) {
		if (e->d_name[0] == '.')
			continue;
		char p[512], ue[1024];
		snprintf(p, sizeof(p), "%s/%s/uevent", base, e->d_name);
		if (!read_small(p, ue, sizeof(ue)))
			continue;
		if (strstr(ue, want)) {
			const char *dn = strstr(ue, "DEVNAME=");
			if (dn) {
				dn += 8;
				size_t n = strcspn(dn, "\n");
				snprintf(buf, cap, "/dev/%.*s", (int)n, dn);
				ok = true;
			}
		}
	}
	closedir(d);
	return ok;
#else
	(void)name; (void)buf; (void)cap;
	return false;
#endif
}

static bool path_or_part(rui_entry e, const char *part, char *buf, size_t cap)
{
	const char *p = rui_get(e);
	if (p && *p) {
		snprintf(buf, cap, "%s", p);
		return true;
	}
	return sys_part(part, buf, cap);
}

bool sys_ota_flag(char *buf, size_t cap)
{
	char dev[160], raw[32];
	if (!path_or_part(PATH_OTA, "ota", dev, sizeof(dev)))
		return false;
	if (!read_small(dev, raw, 16))	/* "ota:kernel2" + NULs */
		return false;
	size_t n = 0;
	for (size_t i = 0; raw[i] && i < 15; i++)
		if (raw[i] >= 0x20 && raw[i] < 0x7f)
			raw[n++] = raw[i];
	raw[n] = 0;
	snprintf(buf, cap, "%s", raw);
	return n > 0;
}

bool sys_main_installed(void)
{
	char dev[160], m[8];
	if (!path_or_part(PATH_MAIN_ROOTFS, "rootfs2", dev, sizeof(dev)))
		return false;
	return read_small(dev, m, 5) && !memcmp(m, "hsqs", 4);
}

bool sys_last_update(char *buf, size_t cap)
{
	const char *path = rui_get(PATH_LAST_LOG);
	FILE *f = fopen(path, "re");
	if (!f)
		return false;
	struct stat sb;
	fstat(fileno(f), &sb);
	if (sb.st_size > 4096)
		fseek(f, -4096, SEEK_END);
	char line[512], last[512] = "";
	while (fgets(line, sizeof(line), f)) {
		line[strcspn(line, "\r\n")] = 0;
		if (line[strspn(line, " \t")])
			snprintf(last, sizeof(last), "%s", line);
	}
	fclose(f);
	if (!last[0])
		return false;
	char when[32];
	strftime(when, sizeof(when), "%Y-%m-%d %H:%M", localtime(&sb.st_mtime));
	snprintf(buf, cap, "%s  (%s)", last, when);
	return true;
}

static bool usb_fs(const char *fs)
{
	static const char *ok[] = { "vfat", "exfat", "ext4", "ext3", "ext2",
		"ntfs", "ntfs3", "fuseblk", NULL };
	for (int i = 0; ok[i]; i++)
		if (!strcmp(fs, ok[i]))
			return true;
	return false;
}

/* Unescape /proc/mounts octal escapes (\040 = space) in place */
static void unoct(char *s)
{
	char *o = s;
	while (*s) {
		if (s[0] == '\\' && s[1] >= '0' && s[1] <= '7' && s[2] && s[3]) {
			*o++ = (char)((s[1] - '0') * 64 + (s[2] - '0') * 8 + (s[3] - '0'));
			s += 4;
		} else {
			*o++ = *s++;
		}
	}
	*o = 0;
}

int sys_usb_list(usb_vol *v, int max)
{
	int n = 0;
	FILE *f = fopen(rui_get(PATH_MOUNTS), "re");
	char line[512];
	while (f && n < max && fgets(line, sizeof(line), f)) {
		char dev[128], dir[256], fs[32];
		if (sscanf(line, "%127s %255s %31s", dev, dir, fs) != 3)
			continue;
		if (strncmp(dev, "/dev/sd", 7) || !usb_fs(fs))
			continue;
		unoct(dir);
		usb_vol *u = &v[n++];
		memset(u, 0, sizeof(*u));
		snprintf(u->dev, sizeof(u->dev), "%s", dev);
		snprintf(u->dir, sizeof(u->dir), "%s", dir);
		snprintf(u->fs, sizeof(u->fs), "%s", fs);
		struct statvfs sv;
		if (!statvfs(dir, &sv)) {
			u->free_mb = (unsigned long long)sv.f_bavail * sv.f_frsize >> 20;
			u->size_mb = (unsigned long long)sv.f_blocks * sv.f_frsize >> 20;
		}
	}
	if (f)
		fclose(f);
	int mounted = n;

	/* Not mounted: sd* partitions (or whole disks without partitions) */
	const char *base = rui_get(PATH_SYS_BLOCK);
	DIR *d = opendir(base);
	struct dirent *e;
	while (d && n < max && (e = readdir(d))) {
		if (strncmp(e->d_name, "sd", 2))
			continue;
		char p[512], s[64];
		snprintf(p, sizeof(p), "%s/%s/partition", base, e->d_name);
		bool is_part = access(p, F_OK) == 0;
		if (!is_part) {	/* whole disk: only if it has no partitions */
			char sub[512];
			snprintf(sub, sizeof(sub), "%s/%s/%s1", base, e->d_name, e->d_name);
			if (access(sub, F_OK) == 0)
				continue;
		}
		snprintf(p, sizeof(p), "%s/%s/size", base, e->d_name);
		if (!read_small(p, s, sizeof(s)) || strtoull(s, NULL, 10) == 0)
			continue;
		char dev[64];
		snprintf(dev, sizeof(dev), "/dev/%s", e->d_name);
		bool dup = false;
		for (int i = 0; i < mounted; i++)
			if (!strcmp(v[i].dev, dev))
				dup = true;
		if (dup)
			continue;
		usb_vol *u = &v[n++];
		memset(u, 0, sizeof(*u));
		snprintf(u->dev, sizeof(u->dev), "%s", dev);
		u->size_mb = strtoull(s, NULL, 10) * 512 >> 20;
	}
	if (d)
		closedir(d);
	return n;
}

static bool has_suffix(const char *s, const char *suf)
{
	size_t a = strlen(s), b = strlen(suf);
	return a >= b && !strcmp(s + a - b, suf);
}

static int add_swu_dir(const char *dir, const char *where, file_ent *f, int n, int max)
{
	DIR *d = opendir(dir);
	if (!d)
		return n;
	struct dirent *e;
	while (n < max && (e = readdir(d))) {
		if (e->d_name[0] == '.' || !(has_suffix(e->d_name, ".swu") || has_suffix(e->d_name, ".zip")))
			continue;
		file_ent *x = &f[n];
		snprintf(x->path, sizeof(x->path), "%s/%s", dir, e->d_name);
		struct stat sb;
		if (stat(x->path, &sb) || !S_ISREG(sb.st_mode))
			continue;
		snprintf(x->name, sizeof(x->name), "%s  (%s)", e->d_name, where);
		x->size = sb.st_size;
		x->mtime = sb.st_mtime;
		n++;
	}
	closedir(d);
	return n;
}

int sys_list_swu(file_ent *f, int max)
{
	int n = add_swu_dir(rui_get(PATH_UPDATE_DIR), tr(RS_SWU_STAGED), f, 0, max);
	usb_vol v[8];
	int nv = sys_usb_list(v, 8);
	for (int i = 0; i < nv; i++) {
		if (!v[i].dir[0])
			continue;
		n = add_swu_dir(v[i].dir, "USB", f, n, max);	/* top directory */
	}
	return n;
}

/* A partition image from ad5x-backup: NAME.img or NAME.img.000 (pieces) */
static bool image_part(const char *name, char *part, size_t cap)
{
	const char *dot = strstr(name, ".img");
	if (name[0] == '.' || !dot || (dot[4] && dot[4] != '.'))
		return false;
	size_t n = dot - name;
	if (!n || n >= cap || memchr(name, '.', n))
		return false;
	memcpy(part, name, n);
	part[n] = 0;
	return true;
}

/* eMMC order: boot kernel rootfs kernel2 rootfs2 ota usershare userdata, then
 * anything else by name */
static int part_rank(const char *p)
{
	static const char *order[] = { "boot", "kernel", "rootfs", "kernel2", "rootfs2",
		"ota", "usershare", "userdata", NULL };
	for (int i = 0; order[i]; i++)
		if (!strcmp(p, order[i]))
			return i;
	return 100;
}

static int cmp_part(const void *a, const void *b)
{
	int ra = part_rank(a), rb = part_rank(b);
	return ra != rb ? ra - rb : strcmp(a, b);
}

static bool scan_set(const char *path, const char *label, backup_set *b)
{
	DIR *d = opendir(path);
	if (!d)
		return false;
	memset(b, 0, sizeof(*b));
	struct dirent *e;
	while ((e = readdir(d))) {
		char part[24], fp[512];
		if (!image_part(e->d_name, part, sizeof(part)))
			continue;
		snprintf(fp, sizeof(fp), "%s/%s", path, e->d_name);
		struct stat sb;
		if (stat(fp, &sb) || !S_ISREG(sb.st_mode))
			continue;
		b->size += sb.st_size;
		bool dup = false;
		for (int i = 0; i < b->nparts; i++)
			if (!strcmp(b->parts[i], part))
				dup = true;
		if (!dup && b->nparts < 16)
			snprintf(b->parts[b->nparts++], sizeof(b->parts[0]), "%s", part);
	}
	closedir(d);
	if (!b->nparts)
		return false;
	qsort(b->parts, b->nparts, sizeof(b->parts[0]), cmp_part);
	snprintf(b->path, sizeof(b->path), "%s", path);
	snprintf(b->label, sizeof(b->label), "%s", label);
	return true;
}

static int cmp_set(const void *a, const void *b)
{	/* newest (largest name, dated) first */
	return strcmp(((const backup_set *)b)->label, ((const backup_set *)a)->label);
}

int sys_list_backups(backup_set *b, int max)
{
	int n = 0;
	usb_vol v[8];
	int nv = sys_usb_list(v, 8);
	const char *prefix = rui_get(PATH_BACKUP_PREFIX);
	for (int i = 0; i < nv && n < max; i++) {
		if (!v[i].dir[0])
			continue;
		/* ad5x-backup writes <stick>/ad5x-backup-<date>-<n>/ */
		DIR *d = opendir(v[i].dir);
		struct dirent *e;
		while (d && n < max && (e = readdir(d))) {
			if (strncmp(e->d_name, prefix, strlen(prefix)))
				continue;
			char p[600];
			snprintf(p, sizeof(p), "%s/%s", v[i].dir, e->d_name);
			if (scan_set(p, e->d_name, &b[n]))
				n++;
		}
		if (d)
			closedir(d);
	}
	qsort(b, n, sizeof(*b), cmp_set);
	return n;
}

void human_size(unsigned long long bytes, char *buf, size_t cap)
{
	if (bytes >= 1ULL << 30)
		snprintf(buf, cap, "%.1f GB", bytes / 1073741824.0);
	else if (bytes >= 1ULL << 20)
		snprintf(buf, cap, "%.0f MB", bytes / 1048576.0);
	else if (bytes >= 1024)
		snprintf(buf, cap, "%.0f KB", bytes / 1024.0);
	else
		snprintf(buf, cap, "%llu B", bytes);
}
