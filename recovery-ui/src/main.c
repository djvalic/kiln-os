/* ad5x-recovery-ui: touch screen UI of the Kiln OS recovery system.
 *
 * usage: ad5x-recovery-ui [--shots DIR]
 *   (no option)  run on the panel (fbdev + evdev) or, in a laptop SDL
 *                build, in an 800x480 window
 *   --shots DIR  headless: render every screen to DIR/NN-name.png
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "lvgl.h"
#include "commands.h"
#include "job.h"
#include "swu.h"
#include "touch_cal.h"
#include "ui.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#ifdef RUI_FBDEV
#include <linux/fb.h>
#include <linux/input.h>
#endif

#define W 800
#define H 480

static uint32_t tick_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

/* --------------------------------------------------------------- PNG out */

static uint32_t crc_tab[256];

static uint32_t crc32_upd(uint32_t c, const uint8_t *p, size_t n)
{
	if (!crc_tab[1])
		for (uint32_t i = 0; i < 256; i++) {
			uint32_t v = i;
			for (int k = 0; k < 8; k++)
				v = v & 1 ? 0xEDB88320u ^ (v >> 1) : v >> 1;
			crc_tab[i] = v;
		}
	c = ~c;
	while (n--)
		c = crc_tab[(c ^ *p++) & 0xff] ^ (c >> 8);
	return ~c;
}

static void put32(uint8_t *p, uint32_t v)
{
	p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v;
}

static void chunk(FILE *f, const char *type, const uint8_t *data, uint32_t len)
{
	uint8_t hdr[8];
	put32(hdr, len);
	memcpy(hdr + 4, type, 4);
	fwrite(hdr, 1, 8, f);
	if (len)
		fwrite(data, 1, len, f);
	uint32_t c = crc32_upd(0, (const uint8_t *)type, 4);
	c = crc32_upd(c, data, len);
	put32(hdr, c);
	fwrite(hdr, 1, 4, f);
}

/* RGB PNG from XRGB8888, zlib "stored" blocks (no compressor needed) */
static int png_write(const char *path, const uint32_t *px, int w, int h)
{
	size_t raw_len = (size_t)h * (1 + 3 * w);
	uint8_t *raw = malloc(raw_len), *r = raw;
	for (int y = 0; y < h; y++) {
		*r++ = 0;
		for (int x = 0; x < w; x++) {
			uint32_t v = px[y * w + x];
			*r++ = v >> 16; *r++ = v >> 8; *r++ = v;
		}
	}
	size_t nblk = (raw_len + 65534) / 65535;
	size_t z_len = 2 + raw_len + nblk * 5 + 4;
	uint8_t *z = malloc(z_len), *o = z;
	*o++ = 0x78; *o++ = 0x01;
	uint32_t a = 1, b = 0;
	for (size_t off = 0; off < raw_len; off += 65535) {
		size_t n = raw_len - off < 65535 ? raw_len - off : 65535;
		*o++ = off + n == raw_len;
		*o++ = n & 0xff; *o++ = n >> 8;
		*o++ = ~n & 0xff; *o++ = (~n >> 8) & 0xff;
		memcpy(o, raw + off, n);
		o += n;
		for (size_t i = 0; i < n; i++) {
			a = (a + raw[off + i]) % 65521;
			b = (b + a) % 65521;
		}
	}
	put32(o, (b << 16) | a);
	FILE *f = fopen(path, "wb");
	if (!f) {
		free(raw);
		free(z);
		return -1;
	}
	static const uint8_t sig[8] = { 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n' };
	fwrite(sig, 1, 8, f);
	uint8_t ihdr[13];
	put32(ihdr, w);
	put32(ihdr + 4, h);
	ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = ihdr[11] = ihdr[12] = 0;
	chunk(f, "IHDR", ihdr, 13);
	chunk(f, "IDAT", z, (uint32_t)z_len);
	chunk(f, "IEND", NULL, 0);
	fclose(f);
	free(raw);
	free(z);
	return 0;
}

/* ------------------------------------------------------------- headless */

static uint32_t *frame;
static lv_display_t *hdisp;
static const char *shot_dir;

static void headless_flush(lv_display_t *d, const lv_area_t *a, uint8_t *px)
{
	int32_t w = lv_area_get_width(a);
	for (int32_t y = a->y1; y <= a->y2; y++)
		memcpy(&frame[y * W + a->x1], px + (size_t)(y - a->y1) * w * 4, (size_t)w * 4);
	lv_display_flush_ready(d);
}

static void shot(const char *name)
{
	lv_obj_invalidate(lv_screen_active());
	lv_refr_now(hdisp);
	char p[512];
	snprintf(p, sizeof(p), "%s/%s.png", shot_dir, name);
	if (png_write(p, frame, W, H))
		fprintf(stderr, "cannot write %s\n", p);
	else
		printf("%s\n", p);
}

static int run_shots(const char *dir)
{
	shot_dir = dir;
	mkdir(dir, 0755);
	frame = calloc(W * H, 4);
	hdisp = lv_display_create(W, H);
	lv_display_set_color_format(hdisp, LV_COLOR_FORMAT_XRGB8888);
	size_t sz = (size_t)W * H * 4;
	void *buf = malloc(sz);
	lv_display_set_buffers(hdisp, buf, NULL, sz, LV_DISPLAY_RENDER_MODE_FULL);
	lv_display_set_flush_cb(hdisp, headless_flush);
	ui_init(hdisp);
	return ui_run_shots(shot) ? 1 : 0;
}

/* ---------------------------------------------------------------- panel */

#ifdef RUI_FBDEV
/* Show page 0 of the double-buffered framebuffer (stock tools may leave
 * the second page panned in); LVGL draws at the current offset. */
static void fb_pan0(const char *dev)
{
	int fd = open(dev, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		return;
	struct fb_var_screeninfo v;
	if (!ioctl(fd, FBIOGET_VSCREENINFO, &v) && (v.yoffset || v.xoffset)) {
		v.xoffset = v.yoffset = 0;
		ioctl(fd, FBIOPAN_DISPLAY, &v);
	}
	close(fd);
}

/* /dev/input/eventN whose name is PATH_TOUCH_NAME */
static bool find_touch(char *path, size_t cap)
{
	const char *want = rui_get(PATH_TOUCH_NAME);
	DIR *d = opendir("/dev/input");
	struct dirent *e;
	bool ok = false;
	while (d && !ok && (e = readdir(d))) {
		if (strncmp(e->d_name, "event", 5))
			continue;
		char p[300], name[128] = "";
		snprintf(p, sizeof(p), "/dev/input/%s", e->d_name);
		int fd = open(p, O_RDONLY | O_CLOEXEC);
		if (fd < 0)
			continue;
		if (ioctl(fd, EVIOCGNAME(sizeof(name) - 1), name) >= 0 && !strcmp(name, want)) {
			snprintf(path, cap, "%s", p);
			ok = true;
		}
		close(fd);
	}
	if (d)
		closedir(d);
	return ok;
}

static lv_indev_t *touch;

static void touch_try(lv_timer_t *t)
{
	char p[300];
	if (touch || !find_touch(p, sizeof(p)))
		return;
	touch = lv_evdev_create(LV_INDEV_TYPE_POINTER, p);
	if (!touch)
		return;
	slog("touch: %s (%s)", p, rui_get(PATH_TOUCH_NAME));
	/* The calibration (touch_cal.h): AD5X_RUI_TOUCH_CAL="minx miny maxx
	 * maxy" from S80ad5x-recovery-ui (swap min/max to invert), else the
	 * panel's usual range; AD5X_RUI_TOUCH_SWAP=1 swaps X and Y */
	const char *cal = getenv("AD5X_RUI_TOUCH_CAL");
	int v[4];
	bool from_env = touch_cal_from_env(cal, v);
	lv_evdev_set_calibration(touch, v[0], v[1], v[2], v[3]);
	if (from_env)
		slog("touch calibration: X %d..%d Y %d..%d (AD5X_RUI_TOUCH_CAL)",
		     v[0], v[2], v[1], v[3]);
	else
		slog("touch calibration: X %d..%d Y %d..%d (default; AD5X_RUI_TOUCH_CAL %s)",
		     v[0], v[2], v[1], v[3], cal ? "not usable" : "not set");
	const char *sw = getenv("AD5X_RUI_TOUCH_SWAP");
	if (sw && *sw == '1')
		lv_evdev_set_swap_axes(touch, true);
	if (t)
		lv_timer_delete(t);
}
#endif

/* LVGL log to stderr. Tiny TTF reports every glyph it hasn't got as an
 * error ("cache not allocated"): those are the LV_SYMBOL_* icons, drawn
 * by the fallback font, so that one is dropped. */
static void log_cb(lv_log_level_t level, const char *buf)
{
	(void)level;
	if (!strstr(buf, "cache not allocated"))
		fputs(buf, stderr);
}

int main(int argc, char **argv)
{
	signal(SIGPIPE, SIG_IGN);
	setvbuf(stdout, NULL, _IOLBF, 0);
	if (argc > 1 && (!strcmp(argv[1], "-h") || !strcmp(argv[1], "--help"))) {
		printf("usage: %s [--shots DIR]\n", argv[0]);
		return 0;
	}
	lv_init();
	lv_log_register_print_cb(log_cb);
	lv_tick_set_cb(tick_ms);
	swu_start(rui_get(PATH_SWU_SOCKET));

	if (argc > 2 && !strcmp(argv[1], "--shots"))
		return run_shots(argv[2]);

	lv_display_t *disp = NULL;
#if defined(RUI_FBDEV)
	fb_pan0(rui_get(PATH_FBDEV));
	disp = lv_linux_fbdev_create();
	if (!disp || lv_linux_fbdev_set_file(disp, rui_get(PATH_FBDEV)) != LV_RESULT_OK) {
		fprintf(stderr, "cannot open %s\n", rui_get(PATH_FBDEV));
		return 1;
	}
	ui_init(disp);
	touch_try(NULL);
	if (!touch) {
		slog("touch screen not found yet (%s), retrying", rui_get(PATH_TOUCH_NAME));
		lv_timer_create(touch_try, 2000, NULL);
	}
#elif defined(RUI_SDL)
	disp = lv_sdl_window_create(W, H);
	lv_sdl_mouse_create();
	ui_init(disp);
#else
	(void)disp;
	fprintf(stderr, "headless build: only --shots DIR\n");
	return 2;
#endif
	for (;;) {
		uint32_t d = lv_timer_handler();
		if (d > 30)
			d = 30;
		usleep(d * 1000);
	}
}
