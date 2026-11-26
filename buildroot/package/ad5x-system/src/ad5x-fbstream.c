// SPDX-License-Identifier: GPL-3.0-or-later
// ad5x-fbstream: the touch screen in the browser, with touch (as zMod's
// screen view in Fluidd). Reads the buffer the display shows through DRM
// (/dev/dri/card0: the CRTC's framebuffer, where HelixScreen draws on the
// mainline kernel), else the visible part of /dev/fb0 (double-buffered:
// yoffset from FBIOGET_VSCREENINFO), encodes JPEG with libjpeg and serves on 127.0.0.1:PORT (nginx: /screen/):
//   GET /                         page: the stream, click/drag = touch
//   GET /?action=stream, /stream  multipart MJPEG at FPS
//   GET /?action=snapshot, /snapshot  one JPEG
//   GET /touch?s=down|move|up&x=X&y=Y   touch at screen pixel X,Y
//
// Touches are written into the touch panel's own evdev node (no uinput in
// this kernel); the screen reads them like real ones. HelixScreen maps raw
// panel values to pixels in two steps, inverted here from its settings.json:
// the linear touch_range scale (LVGL evdev), then the affine calibration
// (a..f, rotation 0). Re-read when settings.json changes.
//
// The touch panel can't tell these touches from a finger, so each one is
// first recorded in MARKER (default /run/ad5x/remote-touch, root's): one
// line "STATE TIME", STATE "down" (a browser finger is on the screen) or
// "up", TIME the seconds since boot (CLOCK_BOOTTIME, as /proc/uptime) of
// the last browser touch, always 26 bytes and rewritten in place (pwrite:
// no new space). A touch that can't be recorded is not made (503). A
// restart counts as a touch, and a press an earlier run left down (the
// record says "down": it died before the "up") is released first, so it
// doesn't stay held in the input system. SIGTERM and SIGINT release a
// press this run holds and record "up" before it exits.
// The update agent reads it: the touch screen's root password reset is
// refused while a browser holds the screen or touched it lately
// (physical access only; S68ad5x-update-agent).
//
// usage: ad5x-fbstream [-p PORT] [-f FPS] [-q QUALITY] [-d FBDEV]
//                      [-t TOUCH_EVDEV] [-s SETTINGS_JSON] [-D DRMDEV]
//                      [-m MARKER]
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#include <drm/drm.h>
#include <drm/drm_fourcc.h>
#include <drm/drm_mode.h>
#include <jpeglib.h>

static const char *fbdev = "/dev/fb0";
static const char *drmdev = "/dev/dri/card0";
static const char *touchdev;	// found by name when not given
static const char *settings = "/data/ad5x/helixscreen/config/settings.json";
static const char *marker = "/run/ad5x/remote-touch";
static int marker_fd = -1;
static int port = 8092, fps = 2, quality = 70;

static int fb_fd = -1;
static uint8_t *fb_mem;
static size_t fb_len;
static struct fb_fix_screeninfo fix;
static unsigned screen_w = 800, screen_h = 480;
static int drm_fd = -1;

static int fb_open(void)
{
	struct fb_var_screeninfo var;
	fb_fd = open(fbdev, O_RDONLY);
	if (fb_fd < 0 || ioctl(fb_fd, FBIOGET_FSCREENINFO, &fix) < 0
	    || ioctl(fb_fd, FBIOGET_VSCREENINFO, &var) < 0) {
		perror(fbdev);
		if (fb_fd >= 0)
			close(fb_fd);
		fb_fd = -1;
		return -1;
	}
	screen_w = var.xres;
	screen_h = var.yres;
	fb_len = fix.smem_len;
	fb_mem = mmap(NULL, fb_len, PROT_READ, MAP_SHARED, fb_fd, 0);
	if (fb_mem == MAP_FAILED) {
		perror("mmap");
		close(fb_fd);
		fb_fd = -1;
		return -1;
	}
	return 0;
}

static uint8_t channel(uint32_t px, const struct fb_bitfield *f)
{
	uint32_t v = (px >> f->offset) & ((1u << f->length) - 1);
	return f->length >= 8 ? v >> (f->length - 8) : v << (8 - f->length);
}

// The pixels of one frame and how to read them
struct frame {
	const uint8_t *base;
	unsigned w, h, bpp;	// bpp in bytes: 2 or 4
	size_t pitch;
	struct fb_bitfield red, green, blue;
};

// JPEG of a frame into a malloc'd buffer
static int encode(const struct frame *f, unsigned char **out, size_t *out_len)
{
	struct jpeg_compress_struct c;
	struct jpeg_error_mgr err;
	unsigned x, y;
	uint8_t *row = malloc(f->w * 3);

	if (!row)
		return -1;
	c.err = jpeg_std_error(&err);
	jpeg_create_compress(&c);
	*out = NULL;
	*out_len = 0;
	jpeg_mem_dest(&c, out, out_len);
	c.image_width = f->w;
	c.image_height = f->h;
	c.input_components = 3;
	c.in_color_space = JCS_RGB;
	jpeg_set_defaults(&c);
	jpeg_set_quality(&c, quality, TRUE);
	jpeg_start_compress(&c, TRUE);
	for (y = 0; y < f->h; y++) {
		const uint8_t *src = f->base + (size_t)y * f->pitch;
		for (x = 0; x < f->w; x++) {
			uint32_t px = f->bpp == 4 ? ((const uint32_t *)src)[x]
						  : ((const uint16_t *)src)[x];
			row[x * 3] = channel(px, &f->red);
			row[x * 3 + 1] = channel(px, &f->green);
			row[x * 3 + 2] = channel(px, &f->blue);
		}
		JSAMPROW r = row;
		jpeg_write_scanlines(&c, &r, 1);
	}
	jpeg_finish_compress(&c);
	jpeg_destroy_compress(&c);
	free(row);
	return 0;
}

// The visible part of /dev/fb0 (double-buffered: yoffset)
static int fb_grab(unsigned char **out, size_t *out_len)
{
	struct fb_var_screeninfo var;
	struct frame f;

	if (fb_fd < 0 || ioctl(fb_fd, FBIOGET_VSCREENINFO, &var) < 0)
		return -1;
	f.bpp = var.bits_per_pixel / 8;
	if (f.bpp != 2 && f.bpp != 4)
		return -1;
	if ((size_t)(var.yoffset + var.yres) * fix.line_length > fb_len)
		var.yoffset = 0;
	f.base = fb_mem + (size_t)var.yoffset * fix.line_length
		+ (size_t)var.xoffset * f.bpp;
	f.w = var.xres;
	f.h = var.yres;
	f.pitch = fix.line_length;
	f.red = var.red;
	f.green = var.green;
	f.blue = var.blue;
	return encode(&f, out, out_len);
}

// The buffer the display shows, through DRM. On the mainline kernel
// HelixScreen draws through DRM, and /dev/fb0 (the kernel's fbdev
// emulation) then keeps showing the boot splash. Reading another
// client's buffer needs root (GETFB2 returns no handle otherwise).
static int drm_grab(unsigned char **out, size_t *out_len)
{
	uint32_t crtcs[8];
	struct drm_mode_card_res res = { 0 };
	struct drm_mode_crtc crtc;
	struct drm_mode_fb_cmd2 fb = { 0 };
	struct drm_mode_map_dumb map = { 0 };
	struct drm_gem_close gc = { 0 };
	struct frame f = { 0 };
	unsigned i;
	size_t len;
	void *mem;
	int ret = -1;

	if (drm_fd < 0)
		return -1;
	res.crtc_id_ptr = (uintptr_t)crtcs;
	res.count_crtcs = 8;
	if (ioctl(drm_fd, DRM_IOCTL_MODE_GETRESOURCES, &res) < 0)
		return -1;
	if (res.count_crtcs > 8)
		res.count_crtcs = 8;
	for (i = 0; i < res.count_crtcs; i++) {
		memset(&crtc, 0, sizeof(crtc));
		crtc.crtc_id = crtcs[i];
		if (ioctl(drm_fd, DRM_IOCTL_MODE_GETCRTC, &crtc) == 0
		    && crtc.mode_valid && crtc.fb_id)
			break;
	}
	if (i == res.count_crtcs)
		return -1;
	fb.fb_id = crtc.fb_id;
	if (ioctl(drm_fd, DRM_IOCTL_MODE_GETFB2, &fb) < 0 || !fb.handles[0])
		return -1;
	switch (fb.pixel_format) {
	case DRM_FORMAT_XRGB8888:
	case DRM_FORMAT_ARGB8888:
		f.bpp = 4;
		f.red = (struct fb_bitfield){ 16, 8, 0 };
		f.green = (struct fb_bitfield){ 8, 8, 0 };
		f.blue = (struct fb_bitfield){ 0, 8, 0 };
		break;
	case DRM_FORMAT_XBGR8888:
	case DRM_FORMAT_ABGR8888:
		f.bpp = 4;
		f.red = (struct fb_bitfield){ 0, 8, 0 };
		f.green = (struct fb_bitfield){ 8, 8, 0 };
		f.blue = (struct fb_bitfield){ 16, 8, 0 };
		break;
	case DRM_FORMAT_RGB565:
		f.bpp = 2;
		f.red = (struct fb_bitfield){ 11, 5, 0 };
		f.green = (struct fb_bitfield){ 5, 6, 0 };
		f.blue = (struct fb_bitfield){ 0, 5, 0 };
		break;
	default:
		goto out;
	}
	f.w = fb.width < crtc.mode.hdisplay ? fb.width : crtc.mode.hdisplay;
	f.h = fb.height < crtc.mode.vdisplay ? fb.height : crtc.mode.vdisplay;
	if (crtc.x + f.w > fb.width || crtc.y + f.h > fb.height)
		crtc.x = crtc.y = 0;
	f.pitch = fb.pitches[0];
	map.handle = fb.handles[0];
	if (ioctl(drm_fd, DRM_IOCTL_MODE_MAP_DUMB, &map) < 0)
		goto out;
	len = (size_t)fb.offsets[0] + (size_t)fb.pitches[0] * fb.height;
	mem = mmap(NULL, len, PROT_READ, MAP_SHARED, drm_fd, map.offset);
	if (mem == MAP_FAILED)
		goto out;
	f.base = (const uint8_t *)mem + fb.offsets[0]
		+ (size_t)crtc.y * f.pitch + (size_t)crtc.x * f.bpp;
	ret = encode(&f, out, out_len);
	munmap(mem, len);
out:
	gc.handle = fb.handles[0];
	ioctl(drm_fd, DRM_IOCTL_GEM_CLOSE, &gc);
	return ret;
}

// Open the DRM device without keeping DRM master. The kernel makes the
// first process to open the primary node master (drm_master_open), and
// this starts at S65, before HelixScreen (S70). Kept, master would make
// HelixScreen's drmSetMaster fail with EBUSY on its DRM backend (no
// modeset, no picture), and on fbdev it would block the fbdev
// emulation's pan and blank (drm_master_internal_acquire). Nothing here
// needs master: GETRESOURCES, GETCRTC, GETFB2, MAP_DUMB and GEM_CLOSE
// are plain ioctls, and GETFB2 gives handles to root (CAP_SYS_ADMIN)
// without master. DROP_MASTER gives EINVAL when this file isn't master
// (another client opened first); any other failure closes the device,
// so DRM is never held, and the screen is read from /dev/fb0.
static void drm_open(void)
{
	drm_fd = open(drmdev, O_RDWR | O_CLOEXEC);
	if (drm_fd < 0)
		return;	// no DRM (6.6, stock): /dev/fb0
	if (ioctl(drm_fd, DRM_IOCTL_DROP_MASTER, 0) == 0) {
		fprintf(stderr, "%s: DRM master dropped\n", drmdev);
	} else if (errno != EINVAL) {
		fprintf(stderr, "%s: DROP_MASTER: %s; reading %s\n",
			drmdev, strerror(errno), fbdev);
		close(drm_fd);
		drm_fd = -1;
	}
}

// JPEG of the visible screen into a malloc'd buffer
static int grab_jpeg(unsigned char **out, size_t *out_len)
{
	if (drm_grab(out, out_len) == 0)
		return 0;
	return fb_grab(out, out_len);
}

// --- Touch ---------------------------------------------------------------

static pthread_mutex_t touch_lock = PTHREAD_MUTEX_INITIALIZER;
static int touch_fd = -1;
static time_t cal_mtime;
static double cal[6] = { 1, 0, 0, 0, 1, 0 };	// a b c d e f
static int cal_valid;
static int range[4];				// min_x max_x min_y max_y
static int range_valid;
static int range_swap;				// touch_range swap_axes

// Number after "key": inside the object that follows "section": (enough
// for HelixScreen's settings.json; not a general JSON parser)
static int json_num(const char *js, const char *section, const char *key,
		    double *out)
{
	char pat[64];
	const char *p, *end;
	snprintf(pat, sizeof(pat), "\"%s\"", section);
	if (!(p = strstr(js, pat)) || !(p = strchr(p, '{')))
		return -1;
	end = strchr(p, '}');
	snprintf(pat, sizeof(pat), "\"%s\"", key);
	if (!(p = strstr(p, pat)) || (end && p > end) || !(p = strchr(p, ':')))
		return -1;
	*out = strtod(p + 1, NULL);
	return 0;
}

static void load_calibration(void)
{
	struct stat st;
	char *js;
	FILE *f;
	double v[6], r[4];
	static const char *ck[6] = { "a", "b", "c", "d", "e", "f" };
	static const char *rk[4] = { "min_x", "max_x", "min_y", "max_y" };
	int i, ok;

	if (stat(settings, &st) < 0 || st.st_mtime == cal_mtime)
		return;
	cal_mtime = st.st_mtime;
	if (!(f = fopen(settings, "r")))
		return;
	js = calloc(1, st.st_size + 1);
	if (js && fread(js, 1, st.st_size, f) == (size_t)st.st_size) {
		ok = 1;
		for (i = 0; i < 6; i++)
			ok &= json_num(js, "calibration", ck[i], &v[i]) == 0;
		// "valid": true inside the calibration object only: an invalid
		// affine (the seed since issue #90) is followed by touch_range's
		const char *cp = strstr(js, "\"calibration\"");
		const char *ce = cp ? strchr(cp, '}') : NULL;
		const char *cv = cp ? strstr(cp, "\"valid\": true") : NULL;
		cal_valid = ok && cv && (!ce || cv < ce);
		if (cal_valid)
			memcpy(cal, v, sizeof(v));
		ok = 1;
		for (i = 0; i < 4; i++)
			ok &= json_num(js, "touch_range", rk[i], &r[i]) == 0;
		// A min above its max is an inverted axis: HelixScreen's
		// three-point calibration (1.1.0-beta.16) stores a flipped Y that
		// way, where the older calibration flipped it in the affine
		range_valid = ok && r[1] != r[0] && r[3] != r[2];
		for (i = 0; range_valid && i < 4; i++)
			range[i] = (int)r[i];
		const char *rp = strstr(js, "\"touch_range\"");
		const char *re = rp ? strchr(rp, '}') : NULL;
		const char *sw = rp ? strstr(rp, "\"swap_axes\": true") : NULL;
		range_swap = range_valid && sw && (!re || sw < re);
	}
	free(js);
	fclose(f);
}

static int find_touch(void)
{
	char path[64], name[128];
	int i, fd;
	if (touchdev)
		return open(touchdev, O_WRONLY);
	for (i = 0; i < 16; i++) {
		snprintf(path, sizeof(path), "/dev/input/event%d", i);
		if ((fd = open(path, O_RDWR)) < 0)
			continue;
		if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) > 0
		    && strstr(name, "ouch"))
			return fd;
		close(fd);
	}
	return -1;
}

static void emit(int type, int code, int value)
{
	struct input_event ev = { .type = type, .code = code, .value = value };
	gettimeofday(&ev.time, NULL);
	if (write(touch_fd, &ev, sizeof(ev)) < 0)
		perror("touch write");
}

static int roundi(double v)
{
	return (int)(v < 0 ? v - 0.5 : v + 0.5);
}

// v clamped between a and b, in either order
static int clampi(int v, int a, int b)
{
	int lo = a < b ? a : b, hi = a < b ? b : a;
	return v < lo ? lo : v > hi ? hi : v;
}

// Screen pixel -> raw panel value: undo the affine, then the range scale
static void to_raw(double sx, double sy, int *rx, int *ry)
{
	double px = sx, py = sy;
	if (cal_valid) {
		double det = cal[0] * cal[4] - cal[1] * cal[3];
		if (det > 1e-6 || det < -1e-6) {
			double x = sx - cal[2], y = sy - cal[5];
			px = (cal[4] * x - cal[1] * y) / det;
			py = (cal[0] * y - cal[3] * x) / det;
		}
	}
	if (range_valid) {
		// lv_map from the panel range to pixels, inverted; either axis
		// may run backwards (min above max)
		int x = roundi(range[0] + px * (range[1] - range[0]) / (screen_w - 1));
		int y = roundi(range[2] + py * (range[3] - range[2]) / (screen_h - 1));
		x = clampi(x, range[0], range[1]);
		y = clampi(y, range[2], range[3]);
		// swap_axes: LVGL takes x from ABS_Y and y from ABS_X
		*rx = range_swap ? y : x;
		*ry = range_swap ? x : y;
	} else {
		*rx = (int)px;
		*ry = (int)py;
	}
}

static unsigned long long boot_s(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_BOOTTIME, &ts);
	return (unsigned long long)ts.tv_sec;
}

// MARKER: "STATE TIME\n", 26 bytes, in place; 0 when written whole
static int mark(int down, unsigned long long t)
{
	char line[32];
	int n = snprintf(line, sizeof(line), "%-4s %20llu\n", down ? "down" : "up",
			 t);
	return marker_fd >= 0 && n == 26 && pwrite(marker_fd, line, n, 0) == n ? 0 : -1;
}

static int remote_down;	// this run's last touch was down or move

// A release on the panel's node: what "up" sends
static void release(void)
{
	emit(EV_KEY, BTN_TOUCH, 0);
	emit(EV_ABS, ABS_PRESSURE, 0);
	emit(EV_SYN, SYN_REPORT, 0);
}

// SIGTERM, SIGINT: blocked everywhere, taken here; a held browser press
// is released and "up" recorded before the exit
static void *on_signal(void *arg)
{
	sigset_t *set = arg;
	int sig;
	sigwait(set, &sig);
	pthread_mutex_lock(&touch_lock);
	if (remote_down && touch_fd >= 0)
		release();
	if (marker_fd >= 0)
		mark(0, boot_s());
	_exit(0);
	return NULL;
}

static int touch(const char *state, double x, double y)
{
	int rx, ry, down = strcmp(state, "up") != 0;
	pthread_mutex_lock(&touch_lock);
	if (touch_fd < 0)
		touch_fd = find_touch();
	// Recorded before it is made; no record, no touch
	if (touch_fd < 0 || mark(down, boot_s()) < 0) {
		pthread_mutex_unlock(&touch_lock);
		return -1;
	}
	load_calibration();
	to_raw(x, y, &rx, &ry);
	emit(EV_ABS, ABS_X, rx);
	emit(EV_ABS, ABS_Y, ry);
	if (strcmp(state, "move") != 0) {
		emit(EV_KEY, BTN_TOUCH, down);
		emit(EV_ABS, ABS_PRESSURE, down ? 200 : 0);
	}
	emit(EV_SYN, SYN_REPORT, 0);
	if (strcmp(state, "move") != 0)
		remote_down = down;
	pthread_mutex_unlock(&touch_lock);
	return 0;
}

// --- HTTP ----------------------------------------------------------------

// The page drops the stream while it is hidden (a background browser tab,
// also Fluidd's camera iframe in one): every frame costs uncached reads of
// fb0 and a JPEG encode on the printer, for nobody.

static const char page[] =
"<!doctype html><html><head><meta charset=utf-8>"
"<meta name=viewport content='width=device-width,initial-scale=1'>"
"<title>AD5X screen</title><style>"
"html,body{margin:0;height:100%;background:#111;display:flex;"
"align-items:center;justify-content:center}"
"img{max-width:100%;max-height:100vh;touch-action:none;user-select:none;"
"-webkit-user-drag:none;cursor:pointer}</style></head><body>"
"<img id=s src='stream' draggable=false alt='printer screen'>"
"<script>"
"const s=document.getElementById('s');let down=false,last=0;"
"function send(t,e){const r=s.getBoundingClientRect();"
"const x=Math.round((e.clientX-r.left)*s.naturalWidth/r.width),"
"y=Math.round((e.clientY-r.top)*s.naturalHeight/r.height);"
"fetch('touch?s='+t+'&x='+x+'&y='+y,{cache:'no-store'});}"
"s.addEventListener('pointerdown',e=>{down=true;s.setPointerCapture(e.pointerId);send('down',e);e.preventDefault();});"
"s.addEventListener('pointermove',e=>{if(!down)return;const n=Date.now();"
"if(n-last<50)return;last=n;send('move',e);});"
"s.addEventListener('pointerup',e=>{if(!down)return;down=false;send('up',e);});"
"s.addEventListener('pointercancel',e=>{if(down){down=false;send('up',e);}});"
"s.onerror=()=>setTimeout(()=>{if(!document.hidden)s.src='stream?'+Date.now()},2000);"
"document.addEventListener('visibilitychange',()=>{if(document.hidden)"
"s.removeAttribute('src');else s.src='stream?'+Date.now();});"
"</script></body></html>";

static int send_all(int fd, const void *buf, size_t len)
{
	const char *p = buf;
	while (len) {
		ssize_t n = send(fd, p, len, MSG_NOSIGNAL);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return -1;
		p += n;
		len -= n;
	}
	return 0;
}

static void reply(int fd, const char *status, const char *type,
		  const void *body, size_t len)
{
	char hdr[256];
	int n = snprintf(hdr, sizeof(hdr), "HTTP/1.0 %s\r\nContent-Type: %s\r\n"
			 "Content-Length: %zu\r\nCache-Control: no-cache\r\n\r\n",
			 status, type, len);
	if (send_all(fd, hdr, n) == 0 && len)
		send_all(fd, body, len);
}

static const char *param(const char *query, const char *key, char *buf, size_t sz)
{
	char pat[16];
	const char *p;
	size_t i = 0;
	snprintf(pat, sizeof(pat), "%s=", key);
	for (p = query; p && (p = strstr(p, pat)); p++)
		if (p == query || p[-1] == '&' || p[-1] == '?')
			break;
	if (!p)
		return NULL;
	for (p += strlen(pat); *p && *p != '&' && *p != ' ' && i + 1 < sz; p++)
		buf[i++] = *p;
	buf[i] = 0;
	return buf;
}

static void stream(int fd)
{
	static const char head[] = "HTTP/1.0 200 OK\r\n"
		"Content-Type: multipart/x-mixed-replace;boundary=frame\r\n"
		"Cache-Control: no-cache\r\n\r\n";
	char hdr[128];
	unsigned char *jpg;
	size_t len;
	if (send_all(fd, head, sizeof(head) - 1) < 0)
		return;
	for (;;) {
		if (grab_jpeg(&jpg, &len) < 0)
			return;
		int n = snprintf(hdr, sizeof(hdr), "--frame\r\nContent-Type: "
				 "image/jpeg\r\nContent-Length: %zu\r\n\r\n", len);
		int bad = send_all(fd, hdr, n) < 0 || send_all(fd, jpg, len) < 0
			|| send_all(fd, "\r\n", 2) < 0;
		free(jpg);
		if (bad)
			return;
		struct timespec ts = { 0, 1000000000L / fps };
		if (fps <= 1)
			ts = (struct timespec){ 1, 0 };
		nanosleep(&ts, NULL);
	}
}

static void *client(void *arg)
{
	int fd = (int)(intptr_t)arg;
	char req[2048], path[512], a[16], b[16], c[16];
	unsigned char *jpg;
	size_t len;
	ssize_t n = recv(fd, req, sizeof(req) - 1, 0);

	if (n <= 0 || sscanf((req[n] = 0, req), "GET %511s", path) != 1)
		goto out;
	const char *q = strchr(path, '?');
	if (strncmp(path, "/touch", 6) == 0) {
		if (!param(q, "s", a, sizeof(a)) || !param(q, "x", b, sizeof(b))
		    || !param(q, "y", c, sizeof(c)))
			reply(fd, "400 Bad Request", "text/plain", "s, x, y\n", 8);
		else if (touch(a, atof(b), atof(c)) < 0)
			reply(fd, "503 No touch device", "text/plain", "", 0);
		else
			reply(fd, "200 OK", "text/plain", "ok\n", 3);
	} else if (strstr(path, "action=snapshot") || strncmp(path, "/snapshot", 9) == 0) {
		if (grab_jpeg(&jpg, &len) < 0) {
			reply(fd, "503 No framebuffer", "text/plain", "", 0);
		} else {
			reply(fd, "200 OK", "image/jpeg", jpg, len);
			free(jpg);
		}
	} else if (strstr(path, "action=stream") || strncmp(path, "/stream", 7) == 0) {
		stream(fd);
	} else {
		reply(fd, "200 OK", "text/html; charset=utf-8", page, sizeof(page) - 1);
	}
out:
	close(fd);
	return NULL;
}

int main(int argc, char **argv)
{
	int opt, s, one = 1;
	struct sockaddr_in a = { .sin_family = AF_INET };

	while ((opt = getopt(argc, argv, "p:f:q:d:t:s:D:m:")) != -1) {
		switch (opt) {
		case 'p': port = atoi(optarg); break;
		case 'f': fps = atoi(optarg) > 0 ? atoi(optarg) : 1; break;
		case 'q': quality = atoi(optarg); break;
		case 'd': fbdev = optarg; break;
		case 't': touchdev = optarg; break;
		case 's': settings = optarg; break;
		case 'D': drmdev = optarg; break;
		case 'm': marker = optarg; break;
		default:
			fprintf(stderr, "usage: %s [-p PORT] [-f FPS] [-q QUALITY] "
				"[-d FBDEV] [-t TOUCH_EVDEV] [-s SETTINGS] [-D DRMDEV] [-m MARKER]\n", argv[0]);
			return 2;
		}
	}
	drm_open();
	if (fb_open() < 0 && drm_fd < 0)
		return 1;
	// The touch record, written whole once here so later rewrites need no
	// space; without it the screen is view only. Left by an earlier run:
	// "up" now (it may have left a press on the panel), else "up 0".
	struct stat mst;
	int restarted = lstat(marker, &mst) == 0;
	// An earlier run's press still down: release it on the panel first
	if (restarted) {
		char old[32] = "";
		int ofd = open(marker, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
		if (ofd >= 0) {
			if (read(ofd, old, sizeof(old) - 1) < 0)
				old[0] = 0;
			close(ofd);
		}
		if (strncmp(old, "down", 4) == 0) {
			if (touch_fd < 0)
				touch_fd = find_touch();
			if (touch_fd >= 0) {
				release();
				fprintf(stderr, "ad5x-fbstream: released a browser press left down\n");
			} else {
				fprintf(stderr, "ad5x-fbstream: a browser press was left down, no touch device to release it\n");
			}
		}
	}
	marker_fd = open(marker, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0644);
	if (marker_fd < 0 || mark(0, restarted ? boot_s() : 0) < 0) {
		perror(marker);
		fprintf(stderr, "ad5x-fbstream: touches off (no %s)\n", marker);
		if (marker_fd >= 0)
			close(marker_fd);
		marker_fd = -1;
	}
	signal(SIGPIPE, SIG_IGN);
	{
		static sigset_t set;
		pthread_t st;
		sigemptyset(&set);
		sigaddset(&set, SIGTERM);
		sigaddset(&set, SIGINT);
		pthread_sigmask(SIG_BLOCK, &set, NULL);
		if (pthread_create(&st, NULL, on_signal, &set) == 0)
			pthread_detach(st);
	}
	s = socket(AF_INET, SOCK_STREAM, 0);
	setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
	a.sin_port = htons(port);
	a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
	if (s < 0 || bind(s, (struct sockaddr *)&a, sizeof(a)) < 0 || listen(s, 8) < 0) {
		perror("listen");
		return 1;
	}
	for (;;) {
		int c = accept(s, NULL, NULL);
		pthread_t t;
		if (c < 0) {
			if (errno == EINTR)
				continue;
			perror("accept");
			sleep(1);
			continue;
		}
		if (pthread_create(&t, NULL, client, (void *)(intptr_t)c) == 0)
			pthread_detach(t);
		else
			close(c);
	}
}
