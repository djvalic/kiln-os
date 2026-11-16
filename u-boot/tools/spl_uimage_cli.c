// SPDX-License-Identifier: GPL-2.0+
/*
 * Host driver for the SPL's uImage loader (spl_crc32() and
 * spl_load_uimage() from arch/mips/mach-jz47xx/x2600/spl.c, which
 * test_spl_uimage.py cuts out of the patched file into spl_uimage.inc),
 * for test_spl_uimage.py:
 *
 *   spl_uimage_cli EMMC LBA MAX OS [FAIL_LBA]
 *
 * EMMC is a file standing in for the eMMC user area from byte 0; the
 * loader reads it through ad5x_emmc_read(), which fails for a read that
 * reaches past its end or covers FAIL_LBA (an eMMC read error). The
 * loader's RAM (its load addresses, 0x80008000-0x8EB00000) is mapped at
 * the same addresses. Prints "ep 0x..." (0 when the loader refuses the
 * image) and exits 0; a loader that doesn't return is killed by the test.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef unsigned long ulong;

#define __aligned(x)	__attribute__((aligned(x)))

/* include/image.h: the legacy header, big endian on the medium */
#define IH_MAGIC	0x27051956
#define IH_NMLEN	32
#define IH_OS_LINUX	5
#define IH_OS_U_BOOT	17
#define IH_ARCH_MIPS	5
struct legacy_img_hdr {
	uint32_t ih_magic, ih_hcrc, ih_time, ih_size, ih_load, ih_ep, ih_dcrc;
	uint8_t ih_os, ih_arch, ih_type, ih_comp;
	uint8_t ih_name[IH_NMLEN];
};
#define image_get_magic(h)	__builtin_bswap32((h)->ih_magic)
#define image_get_hcrc(h)	__builtin_bswap32((h)->ih_hcrc)
#define image_get_size(h)	__builtin_bswap32((h)->ih_size)
#define image_get_load(h)	__builtin_bswap32((h)->ih_load)
#define image_get_ep(h)		__builtin_bswap32((h)->ih_ep)
#define image_get_dcrc(h)	__builtin_bswap32((h)->ih_dcrc)
#define image_get_os(h)		((h)->ih_os)
#define image_get_arch(h)	((h)->ih_arch)

static u8 *emmc;
static long emmc_len;
static long fail_lba = -1;

/* spl.h */
static int ad5x_emmc_read(u32 lba, u32 cnt, void *dst)
{
	if (((long)lba + cnt) * 512 > emmc_len ||
	    (fail_lba >= lba && fail_lba < (long)lba + cnt))
		return -5;
	memcpy(dst, emmc + (long)lba * 512, (size_t)cnt * 512);
	return 0;
}

static void flush_cache(ulong start, ulong size)
{
	(void)start;
	(void)size;
}

#define puts(s)	fputs((s), stdout)

#include "spl_uimage.inc"

int main(int argc, char **argv)
{
	FILE *f;
	ulong ep;
	void *ram;

	if (argc < 5) {
		fprintf(stderr, "usage: %s EMMC LBA MAX OS [FAIL_LBA]\n",
			argv[0]);
		return 2;
	}
	/* the loader's RAM at its own addresses (KSEG0 0x80000000-) */
	ram = mmap((void *)0x80000000UL, 0x0f000000, PROT_READ | PROT_WRITE,
		   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
	if (ram != (void *)0x80000000UL) {
		fprintf(stderr, "can't map 0x80000000\n");
		return 3;
	}
	f = fopen(argv[1], "rb");
	if (!f || fseek(f, 0, SEEK_END) || (emmc_len = ftell(f)) < 0)
		return 2;
	rewind(f);
	emmc = malloc(emmc_len + 1);
	if (!emmc || fread(emmc, 1, emmc_len, f) != (size_t)emmc_len)
		return 2;
	fclose(f);
	if (argc > 5)
		fail_lba = strtol(argv[5], NULL, 0);
	ep = spl_load_uimage(strtoul(argv[2], NULL, 0),
			     strtoul(argv[3], NULL, 0),
			     strtoul(argv[4], NULL, 0));
	printf("\nep 0x%lx\n", ep);
	return 0;
}
