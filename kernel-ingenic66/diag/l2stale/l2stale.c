// SPDX-License-Identifier: GPL-2.0
/*
 * l2stale: count stale DMA reads through the RTL8821CU's USB register reads
 * (test only, never in an image). Follow-up to PR #46's L2 fix
 * (WAR_INGENIC_L2_HIT_CACHEOP on mainline): does Kiln's 6.6 kernel, whose
 * mips_sc_inv() (arch/mips/xburst2/core/sc.c) does its uncached load after
 * the L2 invalidate instead of before it, return stale register values?
 *
 * Build against the kernel build the printer runs (no MODVERSIONS, so the
 * same SDK tree, config and release string are enough):
 *
 *   make -C $SDK/kernel/kernel-6.6 O=$SDK/out-ad5x ARCH=mips \
 *        CROSS_COMPILE=mipsel-linux- M=$PWD modules
 *
 * On the printer, Wi-Fi up (wlan0 present; associated or not):
 *
 *   insmod l2stale.ko mode=lines reads=20000; rmmod l2stale
 *   insmod l2stale.ko mode=driver reads=20000; rmmod l2stale
 *   dmesg | grep l2stale
 *
 * mode=lines   own buffers, each at the start of its own 64-byte L2 line, in
 *              a ring of 64; the CPU reads each result right after its
 *              transfer, as rtw88 does (PR #46: 1 stale read in 12 on
 *              mainline without the fix)
 * mode=driver  the driver's own path, rtw_read32() into rtw88's ring of
 *              4-byte buffers (PR #46: about 1 in 500 on mainline)
 *
 * Three registers with constant, different values are read in turn (the
 * ring sizes are not multiples of 3, so a buffer's earlier value is another
 * register's). A read that does not return its register's value counts as
 * bad, split into: "other-reg" (another register's value, i.e. what the
 * buffer held before: a stale read), "zero" (a failed or short read with
 * kernel patch 0017, or stale zeros in mode=lines clear=1), and "other".
 * Fixed: bad=0 over 20000 reads, a few runs and boots, both modes.
 *
 * The radio must stay on: unassociated, rtw88 powers the chip down (IPS)
 * and every register reads 0xeaeaeaea ("both read 0xeaeaeaea", or bad
 * reads when it powers down mid-run). A monitor interface keeps mac80211
 * out of idle:
 *
 *   iw phy phy0 interface add mon0 type monitor; ip link set mon0 up
 *   ... runs ...
 *   ip link set mon0 down; iw dev mon0 del
 *
 * Result on the printer (kiln-058 image, 2026-11-11): bad=0 in 11 runs of
 * 20000 (lines, lines clear=1, driver) over a warm and a cold boot.
 */
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/netdevice.h>
#include <linux/usb.h>
#include <linux/gfp.h>
#include <net/cfg80211.h>
#include <net/mac80211.h>

#include "main.h"
#include "hci.h"

#define SLOTS		64
#define SLOT_STRIDE	64	/* X2600 L2 line */
#define CALIB		32

static char *mode = "lines";
module_param(mode, charp, 0444);
MODULE_PARM_DESC(mode, "lines (own buffers, one per L2 line) or driver (rtw_read32)");
static unsigned int reads = 20000;
module_param(reads, uint, 0444);
static char *ifname = "wlan0";
module_param(ifname, charp, 0444);
static bool clear;
module_param(clear, bool, 0444);
MODULE_PARM_DESC(clear, "mode=lines: zero each buffer before its transfer, as patch 0017 does");
/* Outside rtw88's "on" sections (0x00-0xff, 0x1000-0x10ff), which need rtw_usb_reg_sec() */
static unsigned int regs[3] = { 0x0610, 0x0614, 0x0618 };	/* MACID, MACID+4, BSSID */
static int nregs = 3;
module_param_array(regs, uint, &nregs, 0444);

static struct usb_device *udev;
static struct rtw_dev *rtwdev;
static u8 *page;
static unsigned int usb_errors;

static u32 read_lines(unsigned int n, u32 addr)
{
	__le32 *data = (__le32 *)(page + (n % SLOTS) * SLOT_STRIDE);
	int ret;

	if (clear)
		*data = 0;
	/* rtw_usb_read()'s transfer: RTW_USB_CMD_REQ, RTW_USB_CMD_READ, index 0 */
	ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 0x05, 0xc0, addr, 0,
			      data, 4, 1000);
	if (ret != 4)
		usb_errors++;
	return le32_to_cpu(*data);
}

static u32 read_reg(unsigned int n, u32 addr)
{
	if (rtwdev)
		return rtw_read32(rtwdev, addr);
	return read_lines(n, addr);
}

static int __init l2stale_init(void)
{
	struct net_device *dev;
	struct ieee80211_hw *hw;
	u32 want[3];
	unsigned int n, i, j, bad = 0, zero = 0, otherreg = 0, other = 0;
	bool use_driver = !strcmp(mode, "driver");
	int ret = 0;

	if (!use_driver && strcmp(mode, "lines"))
		return -EINVAL;
	if (nregs != 3)
		return -EINVAL;
	dev = dev_get_by_name(&init_net, ifname);
	if (!dev || !dev->ieee80211_ptr) {
		pr_err("l2stale: no wireless %s\n", ifname);
		if (dev)
			dev_put(dev);
		return -ENODEV;
	}
	hw = wiphy_to_ieee80211_hw(dev->ieee80211_ptr->wiphy);
	udev = interface_to_usbdev(to_usb_interface(dev->ieee80211_ptr->wiphy->dev.parent));
	page = (u8 *)__get_free_page(GFP_KERNEL);
	if (!page) {
		ret = -ENOMEM;
		goto out;
	}
	if (use_driver)
		rtwdev = hw->priv;

	/* Each register must read the same CALIB times, and differ from the others */
	for (i = 0; i < 3; i++) {
		want[i] = read_reg(i, regs[i]);
		for (n = 1; n < CALIB; n++) {
			u32 v = read_reg(n, regs[i]);

			if (v != want[i]) {
				pr_err("l2stale: register 0x%x not constant (0x%08x, 0x%08x)\n",
				       regs[i], want[i], v);
				ret = -EAGAIN;
				goto out;
			}
		}
		for (j = 0; j < i; j++) {
			if (want[i] == want[j]) {
				pr_err("l2stale: registers 0x%x and 0x%x both read 0x%08x\n",
				       regs[i], regs[j], want[i]);
				ret = -EAGAIN;
				goto out;
			}
		}
	}
	usb_errors = 0;

	for (n = 0; n < reads; n++) {
		u32 v = read_reg(n, regs[n % 3]);

		if (v == want[n % 3])
			continue;
		bad++;
		if (v == want[(n + 1) % 3] || v == want[(n + 2) % 3])
			otherreg++;
		else if (!v)
			zero++;
		else
			other++;
		if (bad <= 8)
			pr_info("l2stale: read %u of 0x%x: 0x%08x, want 0x%08x\n",
				n, regs[n % 3], v, want[n % 3]);
	}
	pr_info("l2stale: mode=%s%s reads=%u bad=%u (other-reg %u, zero %u, other %u) usb-errors=%u\n",
		mode, !use_driver && clear ? " clear" : "", reads, bad, otherreg,
		zero, other, usb_errors);
out:
	if (page)
		free_page((unsigned long)page);
	dev_put(dev);
	return ret;
}

static void __exit l2stale_exit(void)
{
}

module_init(l2stale_init);
module_exit(l2stale_exit);
MODULE_DESCRIPTION("Stale DMA read count through rtw88 USB register reads (test only)");
MODULE_LICENSE("GPL");
