// SPDX-License-Identifier: GPL-2.0
/*
 * chainload: boot another kernel image from the running AD5X stock 5.10
 * kernel, from RAM, without writing the eMMC or the boot flag. A test
 * kernel that hangs is undone by a power cycle.
 *
 *   insmod chainload.ko image=/path/zImage cmdline="..." \
 *          krp=0x<kernel_restart_prepare from /proc/kallsyms>
 *     reads the image into pages above SAFE_MIN, builds argv, copies the
 *     trampoline; prints what it staged. Nothing else happens.
 *   echo 1 > /sys/module/chainload/parameters/go
 *     runs kernel_restart_prepare(NULL) (reboot notifiers, device
 *     shutdown: stops DMA), disables interrupts and enters the trampoline,
 *     which copies the image to 0x80f00000 and jumps there with
 *     a0 = argc, a1 = argv like the stock SPL. Needs one online CPU.
 *
 * The image is a raw self-extracting zImage linked at 0x80f00000, or the
 * same with a 64-byte legacy uImage header (skipped).
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/gfp.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/kallsyms.h>
#include <linux/cpumask.h>
#include <linux/string.h>
#include <asm/cacheflush.h>

#define LOAD_PHYS	0x00f00000UL
/*
 * Above everything a started zboot writes before the new kernel reads its
 * argv: the image copied to LOAD_PHYS (up to MAX_IMAGE), then its bss,
 * which holds mainline's 1 MiB .appended_dtb gap, 4 MiB heap and stack and
 * is cleared on entry. An 8 MiB mainline image would reach 0x01c02010;
 * 7.3.3 reaches 0x019dc3b0, 6.6 about 0x014b2450. kernel-mainline/build.sh
 * fails a build whose zboot ends above this.
 */
#define SAFE_MIN	0x02000000UL
#define SAFE_MAX	0x0ec00000UL	/* end of the 236M lowmem bank */
#define MAX_IMAGE	(8UL << 20)	/* kernel slot size */
#define MAX_PAGES	(MAX_IMAGE / PAGE_SIZE)
#define MAX_TRIES	(64UL << 20) / PAGE_SIZE
#define MAX_ARGS	64

extern char chainload_tramp[], chainload_tramp_end[];

static char *image;
module_param(image, charp, 0444);
MODULE_PARM_DESC(image, "kernel image (zImage or uImage) to boot");
static char *cmdline;
module_param(cmdline, charp, 0444);
MODULE_PARM_DESC(cmdline, "command line for the new kernel");
static unsigned long krp;
module_param(krp, ulong, 0444);
MODULE_PARM_DESC(krp, "address of kernel_restart_prepare (/proc/kallsyms)");

static unsigned long *pages;		/* KSEG0 addresses of image pages */
static unsigned long npages;
static unsigned long *rejects;		/* pages below SAFE_MIN, freed at exit */
static unsigned long nrejects;
/*
 * One contiguous 16 KiB block (order 2) above SAFE_MIN: trampoline at +0,
 * argv at +4 KiB, the page list for the trampoline at +8 KiB (2048 entries,
 * MAX_IMAGE / 4 KiB).
 */
#define BLOCK_ORDER	2
#define BLOCK_TRIES	2048	/* every 16 KiB block below SAFE_MIN */
static unsigned long block;
static unsigned long block_rejects[BLOCK_TRIES];
static unsigned long nblock_rejects;
static unsigned long tramp_page, argv_page, list_page;
static int argc;
static bool staged;

static bool safe(unsigned long va)
{
	unsigned long pa = va - PAGE_OFFSET;

	return pa >= SAFE_MIN && pa + PAGE_SIZE <= SAFE_MAX;
}

static unsigned long safe_page(void)
{
	while (nrejects < MAX_TRIES) {
		unsigned long va = __get_free_page(GFP_KERNEL);

		if (!va)
			return 0;
		if (safe(va))
			return va;
		rejects[nrejects++] = va;
	}
	return 0;
}

static unsigned long safe_block(void)
{
	while (nblock_rejects < BLOCK_TRIES) {
		unsigned long va = __get_free_pages(GFP_KERNEL, BLOCK_ORDER);

		if (!va)
			return 0;
		if (safe(va) && safe(va + (PAGE_SIZE << BLOCK_ORDER) - PAGE_SIZE))
			return va;
		block_rejects[nblock_rejects++] = va;
	}
	return 0;
}

static void free_all(void)
{
	unsigned long i;

	if (pages)
		for (i = 0; i < npages; i++)
			free_page(pages[i]);
	if (rejects)
		for (i = 0; i < nrejects; i++)
			free_page(rejects[i]);
	if (block)
		free_pages(block, BLOCK_ORDER);
	for (i = 0; i < nblock_rejects; i++)
		free_pages(block_rejects[i], BLOCK_ORDER);
	nblock_rejects = 0;
	block = 0;
	vfree(pages);
	vfree(rejects);
	pages = rejects = NULL;
	npages = nrejects = 0;
	list_page = argv_page = tramp_page = 0;
}

static int read_image(void)
{
	struct file *f;
	loff_t pos = 0;
	unsigned char hdr[64];
	size_t size = 0;
	ssize_t n;
	int ret = 0;

	/* No struct inode access (its layout depends on unknown options):
	 * the size is what kernel_read() returns until end of file. */
	f = filp_open(image, O_RDONLY, 0);
	if (IS_ERR(f))
		return PTR_ERR(f);
	if (kernel_read(f, hdr, sizeof(hdr), &pos) != sizeof(hdr)) {
		ret = -EIO;
		goto out;
	}
	/* legacy uImage magic 0x27051956, big-endian */
	if (hdr[0] == 0x27 && hdr[1] == 0x05 && hdr[2] == 0x19 && hdr[3] == 0x56)
		pr_info("chainload: uImage header skipped\n");
	else
		pos = 0;
	for (;;) {
		unsigned long va;

		if (npages >= MAX_PAGES) {
			ret = -EFBIG;
			goto out;
		}
		va = safe_page();
		if (!va) {
			ret = -ENOMEM;
			goto out;
		}
		memset((void *)va, 0, PAGE_SIZE);
		n = kernel_read(f, (void *)va, PAGE_SIZE, &pos);
		if (n <= 0) {
			free_page(va);
			if (n < 0)
				ret = n;
			break;
		}
		pages[npages++] = va;
		size += n;
		if (n < PAGE_SIZE)
			break;
	}
	if (!ret && !size)
		ret = -ENODATA;
	if (!ret)
		pr_info("chainload: %s: %zu bytes in %lu pages (%lu low pages skipped)\n",
			image, size, npages, nrejects);
out:
	filp_close(f, NULL);
	return ret;
}

static int build_argv(void)
{
	char **argv = (char **)argv_page;
	char *s = (char *)(argv_page + (MAX_ARGS + 1) * sizeof(char *));
	char *end = (char *)(argv_page + PAGE_SIZE - 1);
	const char *p = cmdline;

	argc = 0;
	argv[argc++] = strcpy(s, "chainload");
	s += strlen(s) + 1;
	while (*p) {
		const char *w;
		size_t n;

		while (*p == ' ')
			p++;
		if (!*p)
			break;
		w = p;
		while (*p && *p != ' ')
			p++;
		n = p - w;
		if (argc >= MAX_ARGS || s + n + 1 > end)
			return -E2BIG;
		memcpy(s, w, n);
		s[n] = 0;
		argv[argc++] = s;
		s += n + 1;
	}
	argv[argc] = NULL;
	return 0;
}

static int check_krp(void)
{
	char name[KSYM_SYMBOL_LEN];

	if (!krp)
		return -EINVAL;
	sprint_symbol(name, krp);
	if (strncmp(name, "kernel_restart_prepare+0x0/", 27)) {
		pr_err("chainload: krp=%lx is %s, not kernel_restart_prepare\n",
		       krp, name);
		return -EINVAL;
	}
	return 0;
}

static int go_set(const char *val, const struct kernel_param *kp)
{
	void (*prepare)(char *) = (void *)krp;
	void (*tramp)(unsigned long, unsigned long, unsigned long, unsigned long);

	if (!sysfs_streq(val, "1"))
		return -EINVAL;
	if (!staged)
		return -ENODATA;
	if (num_online_cpus() != 1 || raw_smp_processor_id() != 0) {
		pr_err("chainload: take the other CPUs offline first\n");
		return -EBUSY;
	}
	tramp = (void *)tramp_page;
	flush_icache_range(tramp_page, tramp_page + PAGE_SIZE);
	pr_emerg("chainload: shutting devices down and jumping to %s\n", image);
	prepare(NULL);
	local_irq_disable();
	tramp(list_page, npages, argc, argv_page);
	return 0;	/* not reached */
}

static const struct kernel_param_ops go_ops = {
	.set = go_set,
};
module_param_cb(go, &go_ops, NULL, 0200);
MODULE_PARM_DESC(go, "write 1 to boot the staged image (no return)");

static int __init chainload_init(void)
{
	size_t tsize = chainload_tramp_end - chainload_tramp;
	int ret, i;

	if (!image || !cmdline)
		return -EINVAL;
	ret = check_krp();
	if (ret)
		return ret;
	pages = vmalloc(MAX_PAGES * sizeof(*pages));
	rejects = vmalloc(MAX_TRIES * sizeof(*rejects));
	if (!pages || !rejects) {
		ret = -ENOMEM;
		goto fail;
	}
	ret = read_image();
	if (ret)
		goto fail;
	block = safe_block();
	if (!block) {
		ret = -ENOMEM;
		goto fail;
	}
	tramp_page = block;
	argv_page = block + PAGE_SIZE;
	list_page = block + 2 * PAGE_SIZE;
	if (npages * sizeof(unsigned long) > 2 * PAGE_SIZE || tsize > PAGE_SIZE) {
		ret = -E2BIG;
		goto fail;
	}
	memcpy((void *)list_page, pages, npages * sizeof(unsigned long));
	memcpy((void *)tramp_page, chainload_tramp, tsize);
	ret = build_argv();
	if (ret)
		goto fail;
	pr_info("chainload: trampoline %lx (%zu bytes), list %lx, argv %lx, argc %d\n",
		tramp_page - PAGE_OFFSET, tsize, list_page - PAGE_OFFSET,
		argv_page - PAGE_OFFSET, argc);
	for (i = 1; i < argc; i++)
		pr_info("chainload:   argv[%d] %s\n", i, ((char **)argv_page)[i]);
	pr_info("chainload: staged; echo 1 > /sys/module/chainload/parameters/go\n");
	staged = true;
	return 0;
fail:
	pr_err("chainload: staging failed (%d)\n", ret);
	free_all();
	return ret;
}

static void __exit chainload_exit(void)
{
	free_all();
}

module_init(chainload_init);
module_exit(chainload_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Boot another kernel image from RAM (AD5X test)");
