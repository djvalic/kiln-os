// SPDX-License-Identifier: GPL-2.0
/*
 * AD5X MIPS diagnostics (CONFIG_AD5X_DIAG; test kernels only, off in releases).
 *
 *   - PRId and cache geometry (W6)
 *   - DMA cache maintenance checked against uncached memory (W7)
 *   - Does an index cache op on core 0 reach core 1's L1? (W6, finding D)
 *
 * Results are printed as "ad5x-diag:" lines in the kernel log.
 */
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/smp.h>
#include <linux/cpu.h>
#include <linux/dma-mapping.h>
#include <linux/platform_device.h>
#include <linux/io.h>
#include <linux/cache.h>
#include <asm/addrspace.h>
#include <asm/cpu.h>
#include <asm/cpu-info.h>

#define DIAG_LEN	4096

/* The index probe is the riskiest check: it runs only with ad5x_diag_index=1 on the command line. */
static bool run_index;
static int __init index_arg(char *s)
{
	run_index = s && !strcmp(s, "1");
	return 0;
}
early_param("ad5x_diag_index", index_arg);

static u8 *diag_buf;		/* cache-line aligned, DIAG_LEN bytes */
static u32 *sentinel;		/* one cache line in the index test */
static u32 seen_on_core1;

static void diag_report(const char *test, bool ok)
{
	pr_info("ad5x-diag: %s: %s\n", test, ok ? "ok" : "FAIL");
}

/* Uncached alias of a cacheable kernel buffer: reads and writes reach memory. */
static u8 *uncached(void *p)
{
	return (u8 *)CKSEG1ADDR(virt_to_phys(p));
}

static void touch(u8 *p, u8 val)
{
	memset(p, val, DIAG_LEN);
}

static bool all_bytes(const u8 *p, u8 val)
{
	int i;

	for (i = 0; i < DIAG_LEN; i++)
		if (p[i] != val)
			return false;
	return true;
}

/* Prints how many bytes differ from val, and the first one that does. */
static void bad_bytes(const u8 *p, u8 val, const char *what)
{
	int i, n = 0, first = -1;

	for (i = 0; i < DIAG_LEN; i++) {
		if (p[i] != val) {
			if (first < 0)
				first = i;
			n++;
		}
	}
	if (n)
		pr_info("ad5x-diag: %s: %d bad bytes, first at %d (0x%02x)\n",
			what, n, first, p[first]);
}

/* W7: each direction, checked against uncached memory and then cached reads. */
static void dma_diag(struct device *dev)
{
	dma_addr_t h;
	bool ok;

	/* TO_DEVICE: the CPU's writes must reach memory at map time. */
	touch(diag_buf, 0xa5);
	h = dma_map_single(dev, diag_buf, DIAG_LEN, DMA_TO_DEVICE);
	ok = !dma_mapping_error(dev, h) && all_bytes(uncached(diag_buf), 0xa5);
	dma_unmap_single(dev, h, DIAG_LEN, DMA_TO_DEVICE);
	diag_report("W7 dma to_device writeback", ok);

	/*
	 * FROM_DEVICE, repeated: memory gets new data behind a dirty cached copy;
	 * the invalidate must drop the cache so a cached read sees memory.
	 */
	{
		int round, failed = 0, rounds = 200, parked = 0;

#ifdef CONFIG_HOTPLUG_CPU
		/* Quiet run: core 1 parked, so only core 0 does cache maintenance here. */
		if (num_online_cpus() > 1 && !remove_cpu(1))
			parked = 1;
#endif
		for (round = 0; round < rounds; round++) {
			/*
			 * Zeros go to memory and stay in the cache as a clean copy.
			 * A dirty copy could be written back after the uncached write
			 * below and overwrite it, which would test the wrong thing.
			 */
			touch(diag_buf, 0x00);
			h = dma_map_single(dev, diag_buf, DIAG_LEN, DMA_TO_DEVICE);
			dma_unmap_single(dev, h, DIAG_LEN, DMA_TO_DEVICE);
			touch(uncached(diag_buf), 0x5a);	/* memory = 0x5a behind the clean copy */
			h = dma_map_single(dev, diag_buf, DIAG_LEN, DMA_FROM_DEVICE);
			dma_unmap_single(dev, h, DIAG_LEN, DMA_FROM_DEVICE);
			if (!all_bytes(diag_buf, 0x5a)) {
				failed++;
				if (failed <= 3)
					bad_bytes(diag_buf, 0x5a, "W7 from_device round");
			}
		}
		ok = !failed;
		pr_info("ad5x-diag: W7 from_device: %d of %d rounds with stale bytes (core 1 %s)\n",
			failed, rounds, parked ? "parked" : "online");
		if (parked && !add_cpu(1))
			pr_info("ad5x-diag: core 1 back online\n");
	}
	diag_report("W7 dma from_device invalidate", ok);

	/* BIDIRECTIONAL: both halves in one mapping. */
	touch(diag_buf, 0x3c);
	h = dma_map_single(dev, diag_buf, DIAG_LEN, DMA_BIDIRECTIONAL);
	ok = !dma_mapping_error(dev, h) && all_bytes(uncached(diag_buf), 0x3c);
	dma_unmap_single(dev, h, DIAG_LEN, DMA_BIDIRECTIONAL);
	touch(uncached(diag_buf), 0xc3);
	h = dma_map_single(dev, diag_buf, DIAG_LEN, DMA_BIDIRECTIONAL);
	dma_unmap_single(dev, h, DIAG_LEN, DMA_BIDIRECTIONAL);
	ok = ok && all_bytes(diag_buf, 0xc3);
	diag_report("W7 dma bidirectional", ok);
}

/* Reads the sentinel through core 1's cache (cached KSEG0 access). */
static void core1_read_sentinel(void *arg)
{
	seen_on_core1 = READ_ONCE(*sentinel);
}

/*
 * Index writeback-invalidate of the D-cache, one set, every way. It runs on
 * core 0 only. The op is encoded for a plain MIPS32 D-cache index writeback
 * invalidate (target D, function 1); the XBurst2 encoding is not in our docs.
 */
static void l1d_index_wb_inv_set(unsigned long set_addr, unsigned int ways,
				 unsigned int waysize)
{
	unsigned int w;

	for (w = 0; w < ways; w++) {
		unsigned long a = set_addr + w * waysize;

		__asm__ __volatile__(
			"cache	0x01, 0(%0)\n\t"
			: : "r" (a) : "memory");
	}
}

static void index_diag(void)
{
	const struct cache_desc *d = &boot_cpu_data.dcache;
	unsigned long set_addr;
	u32 v1 = 0x11111111, v2 = 0x22222222;
	unsigned long off;

	if (!run_index) {
		pr_info("ad5x-diag: W6 index op: not run (needs ad5x_diag_index=1)\n");
		return;
	}
	if (num_online_cpus() < 2) {
		pr_info("ad5x-diag: W6 index op: skipped (one CPU online)\n");
		return;
	}

	/* Sentinel: the line we cache on core 1 and then drop from core 0. */
	sentinel = (u32 *)diag_buf;
	off = (unsigned long)sentinel & (d->waysize - 1);
	set_addr = KSEG0 | (off & ~((unsigned long)d->linesz - 1));

	*sentinel = v1;
	smp_call_function_single(1, core1_read_sentinel, NULL, 1);	/* core 1 caches V1 */
	*(volatile u32 *)CKSEG1ADDR(virt_to_phys(sentinel)) = v2;	/* memory = V2 */
	l1d_index_wb_inv_set(set_addr, d->ways, d->waysize);
	smp_call_function_single(1, core1_read_sentinel, NULL, 1);

	if (seen_on_core1 == v1)
		pr_info("ad5x-diag: W6 index op on core 0: core 1 kept V1 (private L1, or not reached)\n");
	else if (seen_on_core1 == v2)
		pr_info("ad5x-diag: W6 index op on core 0: core 1 saw V2 (its line was dropped)\n");
	else
		pr_info("ad5x-diag: W6 index op: unexpected value 0x%08x\n", seen_on_core1);
	pr_info("ad5x-diag: W6 note: the L2 was not touched; a V1 can still come from L2\n");
}

static int __init ad5x_diag_init(void)
{
	const struct cache_desc *d = &boot_cpu_data.dcache;
	const struct cache_desc *s = &boot_cpu_data.scache;
	struct platform_device *pdev;
	int ret;

	pr_info("ad5x-diag: PRId 0x%08x\n", read_c0_prid());
	pr_info("ad5x-diag: dcache %u B/way, %u sets, %u ways, %u B lines\n",
		d->waysize, d->sets, d->ways, d->linesz);
	pr_info("ad5x-diag: scache %u B/way, %u sets, %u ways, %u B lines\n",
		s->waysize, s->sets, s->ways, s->linesz);

	diag_buf = kzalloc(DIAG_LEN + 2 * L1_CACHE_BYTES, GFP_KERNEL);
	if (!diag_buf)
		return -ENOMEM;
	diag_buf = PTR_ALIGN(diag_buf, L1_CACHE_BYTES);

	pdev = platform_device_register_simple("ad5x-diag-dma", -1, NULL, 0);
	if (IS_ERR(pdev)) {
		ret = PTR_ERR(pdev);
		pr_err("ad5x-diag: no dma device: %d\n", ret);
		return ret;
	}
	pdev->dev.coherent_dma_mask = DMA_BIT_MASK(32);
	pdev->dev.dma_mask = &pdev->dev.coherent_dma_mask;

	dma_diag(&pdev->dev);
	index_diag();

	platform_device_unregister(pdev);
	return 0;
}
late_initcall(ad5x_diag_init);
