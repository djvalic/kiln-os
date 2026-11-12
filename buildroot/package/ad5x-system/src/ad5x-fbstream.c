// SPDX-License-Identifier: GPL-3.0-or-later
// ad5x-fbstream: the touch screen in the browser, with touch (as zMod's
// screen view in Fluidd). Reads the visible part of /dev/fb0
// (double-buffered: yoffset from FBIOGET_VSCREENINFO), encodes JPEG with
// libjpeg and serves on 127.0.0.1:PORT (nginx: /screen/):
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
// usage: ad5x-fbstream [-p PORT] [-f FPS] [-q QUALITY] [-d FBDEV]
//                      [-t TOUCH_EVDEV] [-s SETTINGS_JSON]
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

#include <jpeglib.h>

static const char *fbdev = "/dev/fb0";
static const char *touchdev;	// found by name when not given
static const char *settings = "/data/ad5x/helixscreen/config/settings.json";
static int port = 8092, fps = 2, quality = 70;

static int fb_fd = -1;
static uint8_t *fb_mem;
static size_t fb_len;
static struct fb_fix_screeninfo fix;
static unsigned screen_w = 800, screen_h = 480;

static int fb_open(void)
{
	struct fb_var_screeninfo var;
	fb_fd = open(fbdev, O_RDONLY);
	if (fb_fd < 0 || ioctl(fb_fd, FBIOGET_FSCREENINFO, &fix) < 0
	    || ioctl(fb_fd, FBIOGET_VSCREENINFO, &var) < 0) {
		perror(fbdev);
		return -1;
	}
	screen_w = var.xres;
	screen_h = var.yres;
	fb_len = fix.smem_len;
	fb_mem = mmap(NULL, fb_len, PROT_READ, MAP_SHARED, fb_fd, 0);
	if (fb_mem == MAP_FAILED) {
		perror("mmap");
		return -1;
	}
	return 0;
}

static uint8_t channel(uint32_t px, const struct fb_bitfield *f)
{
	uint32_t v = (px >> f->offset) & ((1u << f->length) - 1);
	return f->length >= 8 ? v >> (f->length - 8) : v << (8 - f->length);
}

// JPEG of the visible screen into a malloc'd buffer
static int grab_jpeg(unsigned char **out, size_t *out_len)
{
	struct fb_var_screeninfo var;
	struct jpeg_compress_struct c;
	struct jpeg_error_mgr err;
	unsigned bpp, x, y;
	uint8_t *row;

	if (ioctl(fb_fd, FBIOGET_VSCREENINFO, &var) < 0)
		return -1;
	bpp = var.bits_per_pixel / 8;
	if (bpp != 2 && bpp != 4)
		return -1;
	if ((size_t)(var.yoffset + var.yres) * fix.line_length > fb_len)
		var.yoffset = 0;
	row = malloc(var.xres * 3);
	if (!row)
		return -1;

	c.err = jpeg_std_error(&err);
	jpeg_create_compress(&c);
	*out = NULL;
	*out_len = 0;
	jpeg_mem_dest(&c, out, out_len);
	c.image_width = var.xres;
	c.image_height = var.yres;
	c.input_components = 3;
	c.in_color_space = JCS_RGB;
	jpeg_set_defaults(&c);
	jpeg_set_quality(&c, quality, TRUE);
	jpeg_start_compress(&c, TRUE);
	for (y = 0; y < var.yres; y++) {
		const uint8_t *src = fb_mem + (size_t)(var.yoffset + y)
			* fix.line_length + (size_t)var.xoffset * bpp;
		for (x = 0; x < var.xres; x++) {
			uint32_t px = bpp == 4 ? ((const uint32_t *)src)[x]
					       : ((const uint16_t *)src)[x];
			row[x * 3] = channel(px, &var.red);
			row[x * 3 + 1] = channel(px, &var.green);
			row[x * 3 + 2] = channel(px, &var.blue);
		}
		JSAMPROW r = row;
		jpeg_write_scanlines(&c, &r, 1);
	}
	jpeg_finish_compress(&c);
	jpeg_destroy_compress(&c);
	free(row);
	return 0;
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
		const char *cp = strstr(js, "\"calibration\"");
		cal_valid = ok && cp && strstr(cp, "\"valid\": true");
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

static int touch(const char *state, double x, double y)
{
	int rx, ry, down = strcmp(state, "up") != 0;
	pthread_mutex_lock(&touch_lock);
	if (touch_fd < 0)
		touch_fd = find_touch();
	if (touch_fd < 0) {
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

	while ((opt = getopt(argc, argv, "p:f:q:d:t:s:")) != -1) {
		switch (opt) {
		case 'p': port = atoi(optarg); break;
		case 'f': fps = atoi(optarg) > 0 ? atoi(optarg) : 1; break;
		case 'q': quality = atoi(optarg); break;
		case 'd': fbdev = optarg; break;
		case 't': touchdev = optarg; break;
		case 's': settings = optarg; break;
		default:
			fprintf(stderr, "usage: %s [-p PORT] [-f FPS] [-q QUALITY] "
				"[-d FBDEV] [-t TOUCH_EVDEV] [-s SETTINGS]\n", argv[0]);
			return 2;
		}
	}
	if (fb_open() < 0)
		return 1;
	signal(SIGPIPE, SIG_IGN);
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
