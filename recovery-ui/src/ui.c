/* ad5x-recovery-ui screens (LVGL v9, 800x480, touch) */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "ui.h"
#include "commands.h"
#include "job.h"
#include "swu.h"
#include "sys.h"
#include "i18n.h"
#include "lang.h"
#include <stdarg.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* ------------------------------------------------------------------ style */

/* As tools/make_logo.py (the boot logo): dark gradient, accent (74,144,226) */
#define C_BG_TOP   lv_color_make(16, 20, 27)
#define C_BG_BOT   lv_color_make(28, 36, 48)
#define C_CARD     lv_color_make(35, 44, 58)
#define C_CARD_HI  lv_color_make(46, 57, 75)
#define C_BORDER   lv_color_make(58, 70, 90)
#define C_TEXT     lv_color_make(240, 243, 247)
#define C_MUTED    lv_color_make(150, 160, 176)
#define C_ACCENT   lv_color_make(74, 144, 226)
#define C_DANGER   lv_color_make(217, 83, 79)
#define C_WARN     lv_color_make(230, 162, 60)
#define C_OK       lv_color_make(76, 175, 80)

#define W 800
#define H 480
#define PAD 14
#define HEADER_H 64

extern const unsigned char noto_sans_regular_ttf[], noto_sans_bold_ttf[], noto_sans_mono_ttf[];
extern const size_t noto_sans_regular_ttf_len, noto_sans_bold_ttf_len, noto_sans_mono_ttf_len;

static lv_font_t *F16, *F20, *F20B, *F24B, *F28B, *F40, *FMONO;

static lv_font_t *mkfont(const unsigned char *data, size_t len, int px, const lv_font_t *fb)
{
	lv_font_t *f = lv_tiny_ttf_create_data_ex(data, len, px, LV_FONT_KERNING_NORMAL, 256);
	if (!f)
		return (lv_font_t *)fb;
	f->fallback = fb;	/* LV_SYMBOL_* icons */
	return f;
}

static void fonts_init(void)
{
	F16 = mkfont(noto_sans_regular_ttf, noto_sans_regular_ttf_len, 16, &lv_font_montserrat_16);
	F20 = mkfont(noto_sans_regular_ttf, noto_sans_regular_ttf_len, 20, &lv_font_montserrat_20);
	F20B = mkfont(noto_sans_bold_ttf, noto_sans_bold_ttf_len, 20, &lv_font_montserrat_20);
	F24B = mkfont(noto_sans_bold_ttf, noto_sans_bold_ttf_len, 24, &lv_font_montserrat_24);
	F28B = mkfont(noto_sans_bold_ttf, noto_sans_bold_ttf_len, 28, &lv_font_montserrat_28);
	F40 = mkfont(noto_sans_regular_ttf, noto_sans_regular_ttf_len, 40, &lv_font_montserrat_40);
	FMONO = mkfont(noto_sans_mono_ttf, noto_sans_mono_ttf_len, 15, &lv_font_montserrat_14);
}

static lv_obj_t *label(lv_obj_t *parent, const char *text, const lv_font_t *f, lv_color_t c)
{
	lv_obj_t *l = lv_label_create(parent);
	lv_label_set_text(l, text);
	lv_obj_set_style_text_font(l, f, 0);
	lv_obj_set_style_text_color(l, c, 0);
	return l;
}

static lv_obj_t *wrap_label(lv_obj_t *parent, const char *text, const lv_font_t *f, lv_color_t c)
{
	lv_obj_t *l = label(parent, text, f, c);
	lv_label_set_long_mode(l, LV_LABEL_LONG_MODE_WRAP);
	lv_obj_set_width(l, lv_pct(100));
	return l;
}

/* Text with an icon in front: icon, sep, then fmt (a translated text, with
 * its arguments) formatted into t. The icon is never translated. */
static char *iconed_v(char *t, size_t cap, const char *icon, const char *sep,
	const char *fmt, va_list ap)
{
	size_t k = (size_t)snprintf(t, cap, "%s%s", icon ? icon : "", icon ? sep : "");
	if (k < cap)
		vsnprintf(t + k, cap - k, fmt, ap);
	return t;
}

static char *iconed(char *t, size_t cap, const char *icon, const char *sep, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	iconed_v(t, cap, icon, sep, fmt, ap);
	va_end(ap);
	return t;
}

static void set_iconed(lv_obj_t *l, const char *icon, const char *sep, const char *fmt, ...)
{
	char t[480];
	va_list ap;
	va_start(ap, fmt);
	iconed_v(t, sizeof(t), icon, sep, fmt, ap);
	va_end(ap);
	lv_label_set_text(l, t);
}

/* ad5x-status words for slot B, translated; other values as they are */
static const char *slot_word(const char *s)
{
	if (!strcmp(s, "installed"))
		return tr(RS_SLOT_INSTALLED);
	if (!strcmp(s, "not found"))
		return tr(RS_SLOT_NOT_FOUND);
	if (!strcmp(s, "empty"))
		return tr(RS_SLOT_EMPTY);
	if (!strcmp(s, "unknown"))
		return tr(RS_SLOT_UNKNOWN);
	return s;
}

/* SWUpdate's status, translated (the order is swu_status's) */
static const char *swu_status_tr(swu_status s)
{
	static const enum rui_str ids[] = {
		RS_SWU_IDLE, RS_SWU_STARTING, RS_SWU_INSTALLING, RS_SWU_SUCCESS, RS_SWU_FAILED,
		RS_SWU_RECEIVING, RS_SWU_DONE, RS_SWU_SUBPROCESS, RS_SWU_PROGRESS,
	};
	return (unsigned)s < sizeof(ids) / sizeof(ids[0]) ? tr(ids[s]) : swu_status_name(s);
}

static void plain(lv_obj_t *o)
{
	lv_obj_set_style_bg_opa(o, LV_OPA_TRANSP, 0);
	lv_obj_set_style_border_width(o, 0, 0);
	lv_obj_set_style_pad_all(o, 0, 0);
	lv_obj_set_style_radius(o, 0, 0);
}

static lv_obj_t *box(lv_obj_t *parent, lv_flex_flow_t flow)
{
	lv_obj_t *o = lv_obj_create(parent);
	plain(o);
	lv_obj_set_flex_flow(o, flow);
	lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
	return o;
}

static lv_obj_t *card(lv_obj_t *parent)
{
	lv_obj_t *o = lv_obj_create(parent);
	lv_obj_set_style_bg_color(o, C_CARD, 0);
	lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
	lv_obj_set_style_border_color(o, C_BORDER, 0);
	lv_obj_set_style_border_width(o, 1, 0);
	lv_obj_set_style_radius(o, 14, 0);
	lv_obj_set_style_pad_all(o, 12, 0);
	lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
	return o;
}

/* Big touch button: icon + text. kind: 0 normal, 1 accent, 2 danger, 3 warn */
static lv_obj_t *button(lv_obj_t *parent, const char *icon, const char *text, int kind,
			lv_event_cb_t cb, void *ud)
{
	lv_obj_t *b = lv_button_create(parent);
	lv_color_t bg = kind == 1 ? C_ACCENT : kind == 2 ? C_DANGER : kind == 3 ? C_WARN : C_CARD_HI;
	lv_obj_set_style_bg_color(b, bg, 0);
	lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
	lv_obj_set_style_radius(b, 12, 0);
	lv_obj_set_style_shadow_width(b, 0, 0);
	lv_obj_set_style_border_width(b, kind ? 0 : 1, 0);
	lv_obj_set_style_border_color(b, C_BORDER, 0);
	lv_obj_set_style_bg_color(b, lv_color_make(60, 66, 76), LV_STATE_DISABLED);
	lv_obj_set_style_text_color(b, lv_color_make(130, 136, 146), LV_STATE_DISABLED);
	lv_obj_set_style_pad_hor(b, 18, 0);
	lv_obj_set_style_text_color(b, C_TEXT, 0);
	lv_obj_set_height(b, 60);
	lv_obj_t *l = lv_label_create(b);
	char t[160];
	snprintf(t, sizeof(t), "%s%s%s", icon ? icon : "", icon && text ? "  " : "", text ? text : "");
	lv_label_set_text(l, t);
	lv_obj_set_style_text_font(l, F20B, 0);
	lv_obj_center(l);
	if (cb)
		lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, ud);
	return b;
}

static void enable(lv_obj_t *o, bool on)
{
	if (!o)
		return;
	if (on)
		lv_obj_remove_state(o, LV_STATE_DISABLED);
	else
		lv_obj_add_state(o, LV_STATE_DISABLED);
}

static void show(lv_obj_t *o, bool on)
{
	if (!o)
		return;
	if (on)
		lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN);
	else
		lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
}

/* -------------------------------------------------------------- navigation */

typedef void (*page_fn)(void);
static page_fn cur_page;
static void (*cur_refresh)(void);	/* called every 250 ms */
static lv_obj_t *scr;			/* current screen */

static void page_home(void);
static void page_update(void);
static void page_backup(void);
static void page_restore(void);
static void page_stock(void);
static void page_network(void);
static void page_logs(void);
static void page_power(void);
static void page_job(void);

static void go(page_fn f)
{
	lv_obj_clean(lv_layer_top());	/* any dialog */
	cur_refresh = NULL;
	lv_obj_t *old = scr;
	scr = lv_obj_create(NULL);
	lv_obj_set_style_bg_color(scr, C_BG_TOP, 0);
	lv_obj_set_style_bg_grad_color(scr, C_BG_BOT, 0);
	lv_obj_set_style_bg_grad_dir(scr, LV_GRAD_DIR_VER, 0);
	lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
	lv_obj_set_style_text_color(scr, C_TEXT, 0);
	lv_obj_set_style_text_font(scr, F20, 0);
	lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
	cur_page = f;
	f();
	lv_screen_load(scr);
	if (old)
		lv_obj_delete(old);
	if (cur_refresh)
		cur_refresh();
}

static void on_go(lv_event_t *e)
{
	go((page_fn)lv_event_get_user_data(e));
}

static void on_home(lv_event_t *e)
{
	(void)e;
	go(page_home);
}

/* Header with Back (unless back == false) and title; returns the body:
 * a flex column filling the rest of the screen. */
static lv_obj_t *back_btn;

static lv_obj_t *page_frame(const char *title, bool back)
{
	lv_obj_t *hdr = box(scr, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(hdr, W, HEADER_H);
	lv_obj_set_pos(hdr, 0, 0);
	lv_obj_set_style_pad_hor(hdr, PAD, 0);
	lv_obj_set_style_pad_column(hdr, 16, 0);
	lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	back_btn = NULL;
	if (back) {
		back_btn = button(hdr, LV_SYMBOL_LEFT, tr(RS_BACK), 0, on_home, NULL);
		lv_obj_set_size(back_btn, 130, 50);
	}
	label(hdr, title, F28B, C_TEXT);
	lv_obj_t *line = lv_obj_create(scr);
	plain(line);
	lv_obj_set_style_bg_color(line, C_ACCENT, 0);
	lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
	lv_obj_set_size(line, W, 2);
	lv_obj_set_pos(line, 0, HEADER_H);

	lv_obj_t *body = box(scr, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_pos(body, PAD, HEADER_H + 2 + 10);
	lv_obj_set_size(body, W - 2 * PAD, H - HEADER_H - 2 - 10 - PAD);
	lv_obj_set_style_pad_row(body, 10, 0);
	return body;
}

/* ------------------------------------------------------- confirm dialogs */

typedef void (*action_fn)(void);

static struct {
	char title[96], text[512], text2[512], ok[96];
	bool danger, twice;
	action_fn fn;
	lv_obj_t *ok_btn;
	lv_timer_t *arm;
	int arm_left;
} dlg;

static void dlg_close(void)
{
	if (dlg.arm) {
		lv_timer_delete(dlg.arm);
		dlg.arm = NULL;
	}
	lv_obj_clean(lv_layer_top());
	lv_obj_remove_flag(lv_layer_top(), LV_OBJ_FLAG_CLICKABLE);
	dlg.ok_btn = NULL;
}

static void dlg_show(int stage);

static void on_dlg_cancel(lv_event_t *e)
{
	(void)e;
	slog("cancelled: %s", dlg.title);
	dlg_close();
}

static void on_dlg_ok(lv_event_t *e)
{
	int stage = (int)(intptr_t)lv_event_get_user_data(e);
	if (dlg.twice && stage == 1) {
		dlg_show(2);
		return;
	}
	dlg_close();
	if (dlg.fn)
		dlg.fn();
}

static void arm_tick(lv_timer_t *t)
{
	(void)t;
	if (!dlg.ok_btn)
		return;
	lv_obj_t *l = lv_obj_get_child(dlg.ok_btn, 0);
	if (--dlg.arm_left > 0) {
		lv_label_set_text_fmt(l, tr(RS_WAIT_N_S), dlg.arm_left);
		return;
	}
	lv_label_set_text(l, dlg.ok);
	enable(dlg.ok_btn, true);
	lv_timer_delete(dlg.arm);
	dlg.arm = NULL;
}

/* Stage 1: question, Cancel left / OK right. Stage 2 (destructive): the
 * last word, buttons swapped (a double tap can't hit both) and OK armed
 * only after 2 s. */
static void dlg_show(int stage)
{
	dlg_close();
	lv_obj_t *top = lv_layer_top();
	lv_obj_add_flag(top, LV_OBJ_FLAG_CLICKABLE);	/* modal */
	lv_obj_t *scrim = lv_obj_create(top);
	plain(scrim);
	lv_obj_set_size(scrim, W, H);
	lv_obj_set_style_bg_color(scrim, lv_color_black(), 0);
	lv_obj_set_style_bg_opa(scrim, LV_OPA_70, 0);
	lv_obj_remove_flag(scrim, LV_OBJ_FLAG_SCROLLABLE);

	lv_obj_t *c = card(scrim);
	lv_obj_set_size(c, 640, LV_SIZE_CONTENT);
	lv_obj_center(c);
	lv_obj_set_style_pad_all(c, 22, 0);
	lv_obj_set_style_border_color(c, dlg.danger ? C_DANGER : C_ACCENT, 0);
	lv_obj_set_style_border_width(c, 2, 0);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(c, 14, 0);

	char t[160];
	if (stage == 2)
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_WARNING, RS_ARE_YOU_SURE));
	else
		snprintf(t, sizeof(t), "%s%s", dlg.danger ? LV_SYMBOL_WARNING "  " : "", dlg.title);
	label(c, t, F28B, dlg.danger ? C_DANGER : C_TEXT);
	wrap_label(c, stage == 2 ? dlg.text2 : dlg.text, F20, C_TEXT);
	if (dlg.twice)
		label(c, tr(stage == 1 ? RS_STEP_1_OF_2 : RS_STEP_2_OF_2),
		      F16, C_MUTED);

	lv_obj_t *row = box(c, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(row, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER,
			      LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_top(row, 6, 0);
	lv_obj_t *cancel = NULL, *ok = NULL;
	if (stage == 2) {
		ok = button(row, NULL, dlg.ok, dlg.danger ? 2 : 1, on_dlg_ok, (void *)(intptr_t)2);
		cancel = button(row, LV_SYMBOL_CLOSE, tr(RS_CANCEL), 0, on_dlg_cancel, NULL);
	} else {
		cancel = button(row, LV_SYMBOL_CLOSE, tr(RS_CANCEL), 0, on_dlg_cancel, NULL);
		ok = button(row, NULL, dlg.twice ? tr(RS_CONTINUE) : dlg.ok, dlg.danger ? 2 : 1,
			    on_dlg_ok, (void *)(intptr_t)1);
	}
	lv_obj_set_size(cancel, 240, 64);
	lv_obj_set_size(ok, 280, 64);
	dlg.ok_btn = ok;
	if (stage == 2) {
		enable(ok, false);
		dlg.arm_left = 3;
		lv_label_set_text_fmt(lv_obj_get_child(ok, 0), tr(RS_WAIT_N_S), dlg.arm_left);
		dlg.arm = lv_timer_create(arm_tick, 700, NULL);
	}
}

static void confirm(const char *title, const char *text, const char *ok, bool danger,
		    const char *text2, action_fn fn)
{
	snprintf(dlg.title, sizeof(dlg.title), "%s", title);
	snprintf(dlg.text, sizeof(dlg.text), "%s", text);
	snprintf(dlg.text2, sizeof(dlg.text2), "%s", text2 ? text2 : "");
	snprintf(dlg.ok, sizeof(dlg.ok), "%s", ok);
	dlg.danger = danger;
	dlg.twice = text2 != NULL;
	dlg.fn = fn;
	dlg_show(1);
}

/* ------------------------------------------------------------ job launch */

typedef enum { JK_CMD, JK_INSTALL, JK_WEB } job_kind;
typedef enum { AFTER_NONE, AFTER_BOOT_MAIN, AFTER_REBOOT } job_after;

static struct {
	job_kind kind;
	char title[96];
	char what[160];		/* subtitle: file, destination... */
	bool cancelable;
	bool reboots;		/* the command reboots the printer */
	bool critical;		/* writes the eMMC: "don't switch off" */
	job_after after;	/* button offered after success */
	bool started;
	bool failed_start;
	unsigned last_seq, last_swu;
	unsigned swu_seq_at_start, swu_result_at_start;
	char *pending;		/* command waiting for a status query to end */
} jb;

static void status_kick(bool slots);
static bool status_busy(void);

static void start_job_x(job_kind kind, const char *title, const char *what, const char *cmd,
			bool cancelable, bool reboots, bool critical, job_after after)
{
	free(jb.pending);
	memset(&jb, 0, sizeof(jb));
	jb.kind = kind;
	snprintf(jb.title, sizeof(jb.title), "%s", title);
	snprintf(jb.what, sizeof(jb.what), "%s", what ? what : "");
	jb.cancelable = cancelable;
	jb.reboots = reboots;
	jb.critical = critical;
	jb.after = after;
	swu_state s;
	swu_get(&s);
	jb.swu_seq_at_start = s.seq;
	jb.swu_result_at_start = s.result_seq;
	/* `ad5x-status --slots` mounts the slots for a moment: a restore or
	 * install must not start meanwhile (it would find rootfs2 mounted) */
	if (cmd && status_busy()) {
		jb.pending = strdup(cmd);
	} else if (cmd) {
		jb.started = job_start(title, cmd);
		jb.failed_start = !jb.started;
	}
	go(page_job);
}

static void start_job(job_kind kind, const char *title, const char *what, const char *cmd,
		      bool cancelable, bool reboots)
{
	start_job_x(kind, title, what, cmd, cancelable, reboots, false, AFTER_NONE);
}

/* ---------------------------------------------------------- system state */

/* `ad5x-status` (key=value lines), refreshed in the background every 5 s;
 * `--slots` (mounts both slots, slower) at start and after every job. */
static struct {
	capture *cap;
	bool cap_slots, want_slots;
	char text[4096];
	char slots[512];	/* slot_a= / slot_b= lines from the last --slots */
	unsigned seq;
	time_t last;
} stc;

static bool status_busy(void)
{
	return stc.cap != NULL;
}

static void status_kick(bool slots)
{
	stc.want_slots |= slots;
	stc.last = 0;
}

static void status_poll(void)
{
	if (stc.cap) {
		if (!capture_done(stc.cap))
			return;
		const char *t = capture_text(stc.cap);
		snprintf(stc.text, sizeof(stc.text), "%s", t ? t : "");
		if (stc.cap_slots) {
			stc.slots[0] = 0;
			for (const char *l = stc.text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL)
				if (!strncmp(l, "slot_", 5)) {
					size_t n = strlen(stc.slots);
					snprintf(stc.slots + n, sizeof(stc.slots) - n, "%.*s\n",
						 (int)strcspn(l, "\n"), l);
				}
		}
		capture_free(stc.cap);
		stc.cap = NULL;
		stc.seq++;
		return;
	}
	time_t now = time(NULL);
	if (job_running() || jb.pending || (stc.last && now - stc.last < 5))
		return;
	stc.last = now;
	stc.cap_slots = stc.want_slots;
	stc.want_slots = false;
	char *c = cmd_expand(stc.cap_slots ? CMD_STATUS_SLOTS : CMD_STATUS, NULL);
	stc.cap = capture_start(c, sizeof(stc.text));
	free(c);
}

static bool kv_in(const char *text, const char *key, char *out, size_t cap)
{
	size_t kl = strlen(key);
	for (const char *l = text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL) {
		if (!strncmp(l, key, kl) && l[kl] == '=') {
			const char *v = l + kl + 1;
			snprintf(out, cap, "%.*s", (int)strcspn(v, "\n"), v);
			return out[0] != 0;
		}
	}
	return false;
}

/* A status value; false when unknown or empty */
static bool kv(const char *key, char *out, size_t cap)
{
	out[0] = 0;
	return kv_in(stc.text, key, out, cap) || kv_in(stc.slots, key, out, cap);
}

/* The printer's IPv4 (no /prefix) and interface */
static bool cur_ip(char *ip, size_t cap, char *ifc, size_t icap)
{
	if (kv("net_ip", ip, cap)) {
		ip[strcspn(ip, "/")] = 0;
		if (!kv("net_if", ifc, icap))
			snprintf(ifc, icap, "net");
		return true;
	}
	return sys_main_ip(ip, cap, ifc, icap);
}

/* ------------------------------------------------------------------- home */

static struct {
	lv_obj_t *ip, *slot, *trace, *last, *chip;
	unsigned seen;
} hm;

static void boot_main_now(void)
{
	char *c = cmd_expand(CMD_BOOT_MAIN, NULL);
	start_job(JK_CMD, tr(RS_BOOT_MAIN_OS), tr(RS_BOOT_MAIN_WHAT),
		  c, false, true);
	free(c);
}

/* What slot B holds: ad5x-status --slots, else a look at its first bytes */
static const char *main_os_text(char *buf, size_t cap)
{
	if (kv("slot_b", buf, cap))
		return buf;
	snprintf(buf, cap, "%s", sys_main_installed() ? "installed" : "not found");
	return buf;
}

static void on_boot_main(lv_event_t *e)
{
	(void)e;
	char what[96];
	main_os_text(what, sizeof(what));
	if (strcmp(what, "empty") && strcmp(what, "not found") && strcmp(what, "unknown"))
		confirm(tr(RS_BOOT_MAIN_Q),
			tr(RS_BOOT_MAIN_TEXT), tr_sym(LV_SYMBOL_PLAY, RS_BOOT_MAIN_OS), false, NULL,
			boot_main_now);
	else
		confirm(tr(RS_NO_MAIN_Q),
			tr(RS_NO_MAIN_TEXT), tr_sym(LV_SYMBOL_PLAY, RS_TRY), true, NULL, boot_main_now);
}

static void home_refresh(void)
{
	if (hm.seen == stc.seq + 1)
		return;
	hm.seen = stc.seq + 1;
	char ip[64], ifc[16], mode[16], ssh[16], buf[300], flag[32], slotb[96], v[64];

	if (cur_ip(ip, sizeof(ip), ifc, sizeof(ifc))) {
		bool have_mode = kv("net_mode", mode, sizeof(mode));
		bool ssh_up = !kv("ssh", ssh, sizeof(ssh)) || !strcmp(ssh, "running");
		const char *ssh_txt = ssh_up ? "ssh root@" : tr(RS_SSH_NOT_RUNNING);
		set_iconed(hm.ip, LV_SYMBOL_WIFI, "   ", "%s  (%s%s%s)    %s%s", ip, ifc,
			have_mode ? ", " : "", have_mode ? mode : "", ssh_txt, ssh_up ? ip : "");
	} else {
		set_iconed(hm.ip, LV_SYMBOL_WIFI, "   ", "%s", tr(RS_NO_NETWORK_HOME));
	}

	bool have_flag = kv("flag", flag, sizeof(flag)) || sys_ota_flag(flag, sizeof(flag));
	const char *boots = !have_flag ? tr(RS_BOOT_FLAG_UNREADABLE)
		: !strcmp(flag, "ota:kernel2") ? tr(RS_NEXT_MAIN)
		: tr(RS_NEXT_RECOVERY);
	set_iconed(hm.slot, LV_SYMBOL_DRIVE, "   ", tr(RS_HOME_SLOT),
		slot_word(main_os_text(slotb, sizeof(slotb))), boots);

	if (kv("main_trace", buf, sizeof(buf)))
		set_iconed(hm.trace, LV_SYMBOL_EYE_OPEN, "   ", tr(RS_HOME_TRACE), buf);
	else
		set_iconed(hm.trace, LV_SYMBOL_EYE_OPEN, "   ", "%s", tr(RS_HOME_NO_TRACE));

	if (kv("update_last", buf, sizeof(buf)) || sys_last_update(buf, sizeof(buf)))
		set_iconed(hm.last, LV_SYMBOL_DOWNLOAD, "   ", tr(RS_HOME_LAST_UPDATE), buf);
	else
		set_iconed(hm.last, LV_SYMBOL_DOWNLOAD, "   ", "%s", tr(RS_HOME_NO_UPDATE));

	swu_state s;
	swu_get(&s);
	bool swu_up = s.connected || (kv("swupdate", v, sizeof(v)) && !strcmp(v, "running"));
	lv_label_set_text(hm.chip, job_running() ? tr(RS_BUSY) : swu_up ? tr(RS_SWU_READY)
					       : tr(RS_SWU_NOT_RUNNING));
	lv_obj_set_style_bg_color(hm.chip, swu_up ? lv_color_make(30, 70, 45)
						  : lv_color_make(80, 50, 30), 0);
}

static lv_obj_t *tile(lv_obj_t *parent, const char *icon, const char *text, lv_color_t ic,
		      bool accent, lv_event_cb_t cb, void *ud)
{
	lv_obj_t *b = lv_button_create(parent);
	lv_obj_set_size(b, (W - 2 * PAD - 3 * 12) / 4, 116);
	lv_obj_set_style_radius(b, 16, 0);
	lv_obj_set_style_shadow_width(b, 0, 0);
	lv_obj_set_style_bg_color(b, accent ? C_ACCENT : C_CARD, 0);
	lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
	lv_obj_set_style_border_color(b, accent ? C_ACCENT : C_BORDER, 0);
	lv_obj_set_style_border_width(b, 1, 0);
	lv_obj_set_style_bg_color(b, accent ? lv_color_make(56, 118, 196) : C_CARD_HI,
				  LV_STATE_PRESSED);
	lv_obj_set_flex_flow(b, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_flex_align(b, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_row(b, 6, 0);
	lv_obj_set_style_pad_hor(b, 6, 0);
	label(b, icon, F40, accent ? C_TEXT : ic);
	lv_obj_t *l = label(b, text, F20B, C_TEXT);
	lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
	lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, ud);
	return b;
}

static void page_home(void)
{
	memset(&hm, 0, sizeof(hm));
	/* Title: "Kiln OS — Recovery" */
	lv_obj_t *hdr = box(scr, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(hdr, W - 2 * PAD, 52);
	lv_obj_set_pos(hdr, PAD, 2);
	lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(hdr, 10, 0);
	label(hdr, "Kiln OS", F28B, C_TEXT);
	label(hdr, tr(RS_RECOVERY_TITLE), F28B, C_ACCENT);
	lv_obj_t *sp = box(hdr, LV_FLEX_FLOW_ROW);
	lv_obj_set_flex_grow(sp, 1);
	lv_obj_set_height(sp, 1);
	hm.chip = label(hdr, "", F16, C_TEXT);
	lv_obj_set_style_bg_opa(hm.chip, LV_OPA_COVER, 0);
	lv_obj_set_style_radius(hm.chip, 12, 0);
	lv_obj_set_style_pad_hor(hm.chip, 12, 0);
	lv_obj_set_style_pad_ver(hm.chip, 4, 0);

	int st_h = 4 * lv_font_get_line_height(F20) + 3 * 4 + 2 * 10 + 2;
	lv_obj_t *st = card(scr);
	lv_obj_set_pos(st, PAD, 56);
	lv_obj_set_size(st, W - 2 * PAD, st_h);
	lv_obj_set_flex_flow(st, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(st, 4, 0);
	lv_obj_set_style_pad_ver(st, 10, 0);
	lv_obj_set_style_pad_hor(st, 16, 0);
	hm.ip = label(st, "", F20, C_TEXT);
	hm.slot = label(st, "", F20, C_TEXT);
	hm.trace = label(st, "", F20, C_MUTED);
	hm.last = label(st, "", F20, C_MUTED);
	lv_obj_t *one[4] = { hm.ip, hm.slot, hm.trace, hm.last };
	for (int i = 0; i < 4; i++) {	/* one line each, "..." if longer */
		lv_label_set_long_mode(one[i], LV_LABEL_LONG_MODE_DOTS);
		lv_obj_set_size(one[i], lv_pct(100), lv_font_get_line_height(F20));
	}

	int gy = 56 + st_h + 10;
	lv_obj_t *grid = box(scr, LV_FLEX_FLOW_ROW_WRAP);
	lv_obj_set_pos(grid, PAD, gy);
	lv_obj_set_size(grid, W - 2 * PAD, H - gy - 8);
	lv_obj_set_style_pad_column(grid, 12, 0);
	lv_obj_set_style_pad_row(grid, 10, 0);
	tile(grid, LV_SYMBOL_PLAY, tr(RS_BOOT_MAIN_OS), C_TEXT, true, on_boot_main, NULL);
	tile(grid, LV_SYMBOL_DOWNLOAD, tr(RS_INSTALL_UPDATE), C_ACCENT, false, on_go, page_update);
	tile(grid, LV_SYMBOL_SAVE, tr(RS_BACK_UP), C_ACCENT, false, on_go, page_backup);
	tile(grid, LV_SYMBOL_REFRESH, tr(RS_RESTORE), C_WARN, false, on_go, page_restore);
	tile(grid, LV_SYMBOL_WARNING, tr(RS_RESTORE_STOCK), C_DANGER, false, on_go, page_stock);
	tile(grid, LV_SYMBOL_WIFI, tr(RS_NETWORK_SSH), C_ACCENT, false, on_go, page_network);
	tile(grid, LV_SYMBOL_LIST, tr(RS_LOGS), C_MUTED, false, on_go, page_logs);
	tile(grid, LV_SYMBOL_POWER, tr(RS_REBOOT_POWER), C_MUTED, false, on_go, page_power);
	cur_refresh = home_refresh;
}

/* ------------------------------------------------------- selectable rows */

static lv_obj_t *row_item(lv_obj_t *list, const char *title, const char *sub,
			  lv_event_cb_t cb, int idx)
{
	lv_obj_t *b = lv_button_create(list);
	lv_obj_set_width(b, lv_pct(100));
	lv_obj_set_height(b, LV_SIZE_CONTENT);
	lv_obj_set_style_min_height(b, 64, 0);
	lv_obj_set_style_radius(b, 10, 0);
	lv_obj_set_style_shadow_width(b, 0, 0);
	lv_obj_set_style_bg_color(b, C_CARD_HI, 0);
	lv_obj_set_style_bg_color(b, lv_color_make(40, 70, 110), LV_STATE_CHECKED);
	lv_obj_set_style_border_color(b, C_ACCENT, LV_STATE_CHECKED);
	lv_obj_set_style_border_width(b, 2, LV_STATE_CHECKED);
	lv_obj_set_style_border_width(b, 0, 0);
	lv_obj_set_style_pad_ver(b, 8, 0);
	lv_obj_set_style_pad_hor(b, 14, 0);
	lv_obj_set_flex_flow(b, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(b, 2, 0);
	lv_obj_t *t = label(b, title, F20B, C_TEXT);
	lv_label_set_long_mode(t, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_width(t, lv_pct(100));
	if (sub) {
		lv_obj_t *s = label(b, sub, F16, C_MUTED);
		lv_label_set_long_mode(s, LV_LABEL_LONG_MODE_DOTS);
		lv_obj_set_width(s, lv_pct(100));
	}
	lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, (void *)(intptr_t)idx);
	return b;
}

static void select_row(lv_obj_t *list, int idx)
{
	uint32_t n = lv_obj_get_child_count(list);
	for (uint32_t i = 0; i < n; i++) {
		lv_obj_t *c = lv_obj_get_child(list, i);
		if ((int)i == idx)
			lv_obj_add_state(c, LV_STATE_CHECKED);
		else
			lv_obj_remove_state(c, LV_STATE_CHECKED);
	}
}

static lv_obj_t *scroll_list(lv_obj_t *parent)
{
	lv_obj_t *l = lv_obj_create(parent);
	plain(l);
	lv_obj_set_flex_flow(l, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(l, 8, 0);
	lv_obj_set_style_pad_right(l, 6, 0);
	lv_obj_set_scroll_dir(l, LV_DIR_VER);
	return l;
}

/* ----------------------------------------------------------- USB sticks */

/* Sticks are mounted by `ad5x-usb mount` (at /run/ad5x/usb/<dev>); the UI
 * sees them in /proc/mounts. Pages with a USB card mount a stick that shows
 * up unmounted once by themselves; Eject runs `ad5x-usb umount`. */
static usb_vol usb[8];
static int nusb;
static struct {
	lv_obj_t *text, *mount, *umount;
	capture *cap;
	const char *doing;	/* "Mounting", "Ejecting" */
	bool tried;		/* automount done on this page */
	char result[160];
} ub;

static int usb_mounted_idx(void)
{
	for (int i = 0; i < nusb; i++)
		if (usb[i].dir[0])
			return i;
	return -1;
}

static void usb_run(rui_entry e, const char *doing)
{
	if (ub.cap)
		return;
	char *c = cmd_expand(e, NULL);
	slog("%s USB: %s", doing, c);
	ub.cap = capture_start(c, 2048);
	ub.doing = doing;
	free(c);
}

static void on_usb_mount(lv_event_t *e)
{
	(void)e;
	usb_run(CMD_USB_MOUNT, tr(RS_MOUNTING));
}

static void on_usb_umount(lv_event_t *e)
{
	(void)e;
	usb_run(CMD_USB_UMOUNT, tr(RS_EJECTING));
}

static void usb_card_free(lv_event_t *e)
{
	(void)e;
	capture_free(ub.cap);
	ub.cap = NULL;
}

/* A card with the USB status line and Mount / Eject */
static void usb_card(lv_obj_t *body)
{
	memset(&ub, 0, sizeof(ub));
	lv_obj_t *c = card(body);
	lv_obj_set_size(c, lv_pct(100), 84);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_ROW);
	lv_obj_set_flex_align(c, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(c, 10, 0);
	ub.text = label(c, "", F20, C_TEXT);
	lv_label_set_long_mode(ub.text, LV_LABEL_LONG_MODE_WRAP);
	lv_obj_set_flex_grow(ub.text, 1);
	ub.mount = button(c, NULL, tr(RS_MOUNT), 1, on_usb_mount, NULL);
	ub.umount = button(c, LV_SYMBOL_EJECT, tr(RS_EJECT), 0, on_usb_umount, NULL);
	lv_obj_add_event_cb(c, usb_card_free, LV_EVENT_DELETE, NULL);
}

/* Returns true when the set of mounted sticks may have changed */
static bool usb_card_refresh(void)
{
	bool changed = false;
	if (ub.cap && capture_done(ub.cap)) {
		const char *t = capture_text(ub.cap);
		const char *last = t;
		for (const char *p = t; p && *p; p++)
			if (*p == '\n' && p[1])
				last = p + 1;
		snprintf(ub.result, sizeof(ub.result), "%.*s", (int)strcspn(last ? last : "", "\n"),
			 last ? last : "");
		capture_free(ub.cap);
		ub.cap = NULL;
		ub.doing = NULL;
		changed = true;
	}
	int before = usb_mounted_idx();
	nusb = sys_usb_list(usb, 8);
	int m = usb_mounted_idx();
	if (m != before)
		changed = true;
	if (!ub.tried && !ub.cap && nusb > 0 && m < 0) {
		ub.tried = true;
		usb_run(CMD_USB_MOUNT, tr(RS_MOUNTING));
	}
	char t[300];
	if (ub.doing) {
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", tr(RS_USB_BUSY), ub.doing);
	} else if (m >= 0) {
		char fr[32];
		human_size(usb[m].free_mb << 20, fr, sizeof(fr));
		char head[160];
		snprintf(head, sizeof(head), tr(RS_USB_MOUNTED), usb[m].dev, usb[m].fs, fr);
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", "%s\n%s", head, usb[m].dir);
	} else if (nusb > 0) {
		char head[160];
		snprintf(head, sizeof(head), tr(RS_USB_NOT_MOUNTED), usb[0].dev);
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", "%s%s%s", head,
			ub.result[0] ? "\n" : "", ub.result);
	} else {
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", "%s", tr(RS_USB_NONE));
	}
	lv_label_set_text(ub.text, t);
	show(ub.mount, !ub.doing && nusb > 0 && m < 0);
	show(ub.umount, !ub.doing && m >= 0);
	return changed;
}

/* ---------------------------------------------------------- install page */

static struct {
	file_ent f[24];
	int n, sel;
	lv_obj_t *list, *install, *check, *hint;
	unsigned tick;
} up;

static void up_fill(void);

static void up_buttons(void)
{
	enable(up.install, up.sel >= 0);
	enable(up.check, up.sel >= 0);
}

static void on_up_row(lv_event_t *e)
{
	up.sel = (int)(intptr_t)lv_event_get_user_data(e);
	select_row(up.list, up.sel);
	up_buttons();
}

static void install_now(void)
{
	if (up.sel < 0 || up.sel >= up.n)
		return;
	const char *v[] = { "FILE", up.f[up.sel].path, NULL };
	char *c = cmd_expand(CMD_INSTALL, v);
	start_job_x(JK_INSTALL, tr(RS_INSTALLING_UPDATE), up.f[up.sel].path, c, false, false, true,
		    AFTER_BOOT_MAIN);
	free(c);
}

static void on_install(lv_event_t *e)
{
	(void)e;
	if (up.sel < 0 || up.sel >= up.n)
		return;
	static char t1[400], t2[400];
	snprintf(t1, sizeof(t1), tr(RS_INSTALL_Q_TEXT), up.f[up.sel].name);
	snprintf(t2, sizeof(t2), "%s", tr(RS_INSTALL_Q_TEXT2));
	confirm(tr(RS_INSTALL_Q), t1, tr_sym(LV_SYMBOL_DOWNLOAD, RS_INSTALL_NOW), true, t2,
		install_now);
}

static void on_up_check(lv_event_t *e)
{
	(void)e;
	if (up.sel < 0 || up.sel >= up.n)
		return;
	const char *v[] = { "FILE", up.f[up.sel].path, NULL };
	char *c = cmd_expand(CMD_INSTALL_CHECK, v);
	start_job(JK_CMD, tr(RS_CHECKING_UPDATE), up.f[up.sel].path, c, true, false);
	free(c);
}

static void on_up_refresh(lv_event_t *e)
{
	(void)e;
	up_fill();
}

static void up_fill(void)
{
	char keep[256] = "";
	if (up.sel >= 0 && up.sel < up.n)
		snprintf(keep, sizeof(keep), "%s", up.f[up.sel].path);
	up.n = sys_list_swu(up.f, 24);
	up.sel = -1;
	lv_obj_clean(up.list);
	for (int i = 0; i < up.n; i++) {
		char sub[300], sz[32], when[32];
		time_t mt = up.f[i].mtime;
		human_size(up.f[i].size, sz, sizeof(sz));
		strftime(when, sizeof(when), "%Y-%m-%d %H:%M", localtime(&mt));
		snprintf(sub, sizeof(sub), "%s  \xc2\xb7  %s  \xc2\xb7  %s", sz, when, up.f[i].path);
		row_item(up.list, up.f[i].name, sub, on_up_row, i);
		if (!strcmp(keep, up.f[i].path))
			up.sel = i;
	}
	if (up.n == 1)
		up.sel = 0;
	if (!up.n) {
		char t[300];
		snprintf(t, sizeof(t), tr(RS_NO_UPDATE_FMT), rui_get(PATH_UPDATE_DIR));
		wrap_label(up.list, t, F20, C_MUTED);
	}
	select_row(up.list, up.sel);
	up_buttons();
}

static void up_refresh(void)
{
	if (usb_card_refresh())
		up.tick = 0;
	if (up.tick++ % 12)	/* every 3 s: web URL, new files */
		return;
	char ip[64], ifc[16];
	if (cur_ip(ip, sizeof(ip), ifc, sizeof(ifc)))
		lv_label_set_text_fmt(up.hint, tr(RS_UPLOAD_HINT), ip);
	else
		lv_label_set_text(up.hint, tr(RS_UPLOAD_HINT_NONET));
	file_ent f[24];
	int n = sys_list_swu(f, 24);
	bool same = n == up.n;
	for (int i = 0; same && i < n; i++)
		same = !strcmp(f[i].path, up.f[i].path);
	if (!same)
		up_fill();
}

static void page_update(void)
{
	memset(&up, 0, sizeof(up));
	up.sel = -1;
	lv_obj_t *body = page_frame(tr(RS_INSTALL_UPDATE), true);
	usb_card(body);
	up.hint = label(body, "", F16, C_MUTED);
	up.list = scroll_list(body);
	lv_obj_set_width(up.list, lv_pct(100));
	lv_obj_set_flex_grow(up.list, 1);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	lv_obj_t *r = button(row, LV_SYMBOL_REFRESH, tr(RS_RESCAN), 0, on_up_refresh, NULL);
	lv_obj_set_width(r, 180);
	up.check = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_CHECK), 0, on_up_check, NULL);
	lv_obj_set_width(up.check, 180);
	up.install = button(row, LV_SYMBOL_DOWNLOAD, tr(RS_INSTALL), 1, on_install, NULL);
	lv_obj_set_flex_grow(up.install, 1);
	up_fill();
	cur_refresh = up_refresh;
}

/* ----------------------------------------------------------- backup page */

static struct {
	lv_obj_t *all, *dest, *start, *dry;
	unsigned tick;
	char destdir[300];
} bk;

static void bk_dest(void)
{
	int m = usb_mounted_idx();
	if (m < 0) {
		bk.destdir[0] = 0;
		lv_label_set_text(bk.dest, tr(RS_BK_DEST_NONE));
		return;
	}
	/* ad5x-backup makes <DEST>/ad5x-backup-<date>-<n>/ */
	snprintf(bk.destdir, sizeof(bk.destdir), "%s", usb[m].dir);
	lv_label_set_text_fmt(bk.dest, tr(RS_BK_DEST), usb[m].dir,
			      rui_get(PATH_BACKUP_PREFIX));
}

static void bk_refresh(void)
{
	if (usb_card_refresh())
		bk.tick = 0;
	if (bk.tick++ % 8)
		return;
	bk_dest();
	enable(bk.start, bk.destdir[0] != 0);
	enable(bk.dry, bk.destdir[0] != 0);
}

static void bk_run(bool dry)
{
	bk_dest();
	if (!bk.destdir[0])
		return;
	bool all = lv_obj_has_state(bk.all, LV_STATE_CHECKED);
	const char *v[] = { "DRY", dry ? "--dry-run" : "", "ALL", all ? "--all" : "",
			    "DEST", bk.destdir, NULL };
	char *c = cmd_expand(CMD_BACKUP, v);
	start_job(JK_CMD, dry ? tr(RS_BACKUP_DRY_RUN) : tr(RS_BACKING_UP), bk.destdir, c, true, false);
	free(c);
}

static void on_bk_start(lv_event_t *e)
{
	(void)e;
	bk_run(false);
}

static void on_bk_dry(lv_event_t *e)
{
	(void)e;
	bk_run(true);
}

static void page_backup(void)
{
	memset(&bk, 0, sizeof(bk));
	lv_obj_t *body = page_frame(tr(RS_BACK_UP_TITLE), true);
	usb_card(body);

	lv_obj_t *c = card(body);
	lv_obj_set_size(c, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(c, 10, 0);
	wrap_label(c, tr(RS_BACKUP_TEXT), F20, C_TEXT);
	lv_obj_t *r = box(c, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(r, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(r, 14, 0);
	bk.all = lv_switch_create(r);
	lv_obj_set_size(bk.all, 76, 40);
	label(r, tr(RS_ALSO_USERDATA), F20, C_TEXT);
	bk.dest = label(c, "", F16, C_MUTED);
	lv_label_set_long_mode(bk.dest, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_width(bk.dest, lv_pct(100));

	lv_obj_t *sp = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_flex_grow(sp, 1);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	bk.dry = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_DRY_RUN), 0, on_bk_dry, NULL);
	lv_obj_set_width(bk.dry, 220);
	bk.start = button(row, LV_SYMBOL_SAVE, tr(RS_START_BACKUP), 1, on_bk_start, NULL);
	lv_obj_set_flex_grow(bk.start, 1);
	cur_refresh = bk_refresh;
}

/* ---------------------------------------------------------- restore page */

static struct {
	backup_set *sets;
	int n, sel;
	bool part_on[16];
	lv_obj_t *list, *parts, *go, *dry;
	unsigned tick;
} rs;

/* Partitions ad5x-restore won't write from here: this recovery's own slot
 * (kernel, rootfs: refused while it runs) and the boot area (only with
 * --i-know, left to the command line). */
static bool rs_locked(const char *p)
{
	return !strcmp(p, "kernel") || !strcmp(p, "rootfs") || !strcmp(p, "boot");
}

static void rs_update_buttons(void)
{
	int k = 0;
	if (rs.sel >= 0)
		for (int i = 0; i < rs.sets[rs.sel].nparts; i++)
			k += rs.part_on[i];
	enable(rs.go, k > 0);
	enable(rs.dry, k > 0);
}

static void on_rs_part(lv_event_t *e)
{
	int i = (int)(intptr_t)lv_event_get_user_data(e);
	rs.part_on[i] = lv_obj_has_state(lv_event_get_target_obj(e), LV_STATE_CHECKED);
	rs_update_buttons();
}

static void rs_fill_parts(void)
{
	lv_obj_clean(rs.parts);
	memset(rs.part_on, 0, sizeof(rs.part_on));
	if (rs.sel < 0) {
		wrap_label(rs.parts, tr(RS_PICK_BACKUP), F20, C_MUTED);
		rs_update_buttons();
		return;
	}
	lv_obj_t *h = label(rs.parts, tr(RS_PARTITIONS_TO_WRITE), F20B, C_TEXT);
	lv_obj_set_width(h, lv_pct(100));
	backup_set *b = &rs.sets[rs.sel];
	bool locked_any = false;
	for (int i = 0; i < b->nparts; i++) {
		lv_obj_t *cb = lv_checkbox_create(rs.parts);
		lv_checkbox_set_text(cb, b->parts[i]);
		lv_obj_set_width(cb, lv_pct(48));
		lv_obj_set_style_text_font(cb, F20, 0);
		lv_obj_set_style_pad_ver(cb, 6, 0);
		lv_obj_set_style_pad_column(cb, 12, 0);
		lv_obj_set_style_width(cb, 30, LV_PART_INDICATOR);
		lv_obj_set_style_height(cb, 30, LV_PART_INDICATOR);
		lv_obj_set_ext_click_area(cb, 8);
		if (rs_locked(b->parts[i])) {
			lv_obj_add_state(cb, LV_STATE_DISABLED);
			lv_obj_set_style_text_color(cb, lv_color_make(110, 118, 130), 0);
			locked_any = true;
		}
		lv_obj_add_event_cb(cb, on_rs_part, LV_EVENT_VALUE_CHANGED, (void *)(intptr_t)i);
	}
	if (locked_any) {
		lv_obj_t *n = wrap_label(rs.parts, tr(RS_GREYED_OUT), F16, C_MUTED);
		lv_obj_set_style_pad_top(n, 4, 0);
	}
	rs_update_buttons();
}

static void on_rs_row(lv_event_t *e)
{
	rs.sel = (int)(intptr_t)lv_event_get_user_data(e);
	select_row(rs.list, rs.sel);
	rs_fill_parts();
}

static void rs_parts_str(char *buf, size_t cap)
{
	buf[0] = 0;
	backup_set *b = &rs.sets[rs.sel];
	for (int i = 0; i < b->nparts; i++)
		if (rs.part_on[i]) {
			size_t n = strlen(buf);
			snprintf(buf + n, cap - n, "%s%s", n ? " " : "", b->parts[i]);
		}
}

static void rs_run(bool dry)
{
	if (rs.sel < 0)
		return;
	char parts[400];
	rs_parts_str(parts, sizeof(parts));
	const char *v[] = { "DRY", dry ? "--dry-run" : "", "SRC", rs.sets[rs.sel].path,
			    "PARTS", parts, NULL };
	char *c = cmd_expand(CMD_RESTORE, v);
	/* After restoring slot B, offer to boot it */
	bool main_slot = strstr(parts, "kernel2") || strstr(parts, "rootfs2");
	start_job_x(JK_CMD, dry ? tr(RS_RESTORE_DRY_RUN) : tr(RS_RESTORING), rs.sets[rs.sel].path, c,
		    dry, false, !dry, !dry && main_slot ? AFTER_BOOT_MAIN : AFTER_NONE);
	free(c);
}

static void rs_go_now(void)
{
	rs_run(false);
}

static void on_rs_dry(lv_event_t *e)
{
	(void)e;
	rs_run(true);
}

static void on_rs_go(lv_event_t *e)
{
	(void)e;
	if (rs.sel < 0)
		return;
	char parts[400];
	static char t1[600], t2[600];
	rs_parts_str(parts, sizeof(parts));
	snprintf(t1, sizeof(t1), tr(RS_RESTORE_Q), rs.sets[rs.sel].label, parts);
	snprintf(t2, sizeof(t2), tr(RS_RESTORE_Q2), parts);
	confirm(tr(RS_RESTORE_BACKUP_Q), t1, tr_sym(LV_SYMBOL_REFRESH, RS_RESTORE_NOW), true, t2,
		rs_go_now);
}

static void rs_fill(void)
{
	rs.n = sys_list_backups(rs.sets, 32);
	rs.sel = rs.n == 1 ? 0 : -1;
	lv_obj_clean(rs.list);
	for (int i = 0; i < rs.n; i++) {
		char sub[200], sz[32];
		human_size(rs.sets[i].size, sz, sizeof(sz));
		snprintf(sub, sizeof(sub), "%d partitions  \xc2\xb7  %s", rs.sets[i].nparts, sz);
		row_item(rs.list, rs.sets[i].label, sub, on_rs_row, i);
	}
	if (!rs.n) {
		char t[200];
		snprintf(t, sizeof(t), tr(usb_mounted_idx() >= 0 ? RS_NO_BACKUPS : RS_INSERT_BACKUP_USB),
			rui_get(PATH_BACKUP_PREFIX));
		wrap_label(rs.list, t, F20, C_MUTED);
	}
	select_row(rs.list, rs.sel);
	rs_fill_parts();
}

static void rs_refresh(void)
{
	if (usb_card_refresh() || rs.tick == 0)
		rs_fill();
	rs.tick++;
}

static void page_restore(void)
{
	static backup_set sets[32];
	memset(&rs, 0, sizeof(rs));
	rs.sets = sets;
	rs.sel = -1;
	lv_obj_t *body = page_frame(tr(RS_RESTORE_TITLE), true);
	usb_card(body);
	lv_obj_t *cols = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_width(cols, lv_pct(100));
	lv_obj_set_flex_grow(cols, 1);
	lv_obj_set_style_pad_column(cols, 12, 0);
	rs.list = scroll_list(cols);
	lv_obj_set_size(rs.list, 360, lv_pct(100));
	lv_obj_t *right = card(cols);
	lv_obj_set_height(right, lv_pct(100));
	lv_obj_set_flex_grow(right, 1);
	lv_obj_set_flex_flow(right, LV_FLEX_FLOW_COLUMN);
	rs.parts = scroll_list(right);
	lv_obj_set_flex_flow(rs.parts, LV_FLEX_FLOW_ROW_WRAP);
	lv_obj_set_width(rs.parts, lv_pct(100));
	lv_obj_set_flex_grow(rs.parts, 1);
	lv_obj_set_style_pad_row(rs.parts, 0, 0);
	lv_obj_set_style_pad_column(rs.parts, 0, 0);
	lv_obj_t *row = box(right, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 10, 0);
	rs.dry = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_CHECK), 0, on_rs_dry, NULL);
	lv_obj_set_flex_grow(rs.dry, 1);
	rs.go = button(row, LV_SYMBOL_REFRESH, tr(RS_RESTORE), 2, on_rs_go, NULL);
	lv_obj_set_flex_grow(rs.go, 1);
	rs_fill();
	cur_refresh = rs_refresh;
}

/* ------------------------------------------------------------ stock page */

static struct {
	lv_obj_t *go, *dry, *note;
	unsigned seen;
} sk;

static void stock_run(bool dry)
{
	const char *v[] = { "DRY", dry ? "--dry-run" : "", NULL };
	char *c = cmd_expand(CMD_RESTORE_STOCK, v);
	/* ad5x-restore-stock points the flag at slot B itself: offer a reboot */
	start_job_x(JK_CMD, dry ? tr(RS_STOCK_DRY_RUN) : tr(RS_RESTORING_STOCK),
		    "/data/ad5x/stock -> slot B", c, dry, false, !dry,
		    dry ? AFTER_NONE : AFTER_REBOOT);
	free(c);
}

static void stock_now(void)
{
	stock_run(false);
}

static void on_stock_dry(lv_event_t *e)
{
	(void)e;
	stock_run(true);
}

static void on_stock(lv_event_t *e)
{
	(void)e;
	confirm(tr(RS_RESTORE_STOCK_Q),
		tr(RS_STOCK_Q_TEXT), tr_sym(LV_SYMBOL_WARNING, RS_RESTORE_STOCK), true,
		tr(RS_STOCK_Q_TEXT2), stock_now);
}

static void stock_refresh(void)
{
	if (sk.seen == stc.seq + 1)
		return;
	sk.seen = stc.seq + 1;
	char v[16];
	bool known = kv("stock_saved", v, sizeof(v));
	bool saved = !known || !strcmp(v, "yes");
	enable(sk.go, saved);
	enable(sk.dry, saved);
	lv_label_set_text(sk.note, !known ? "" : saved
			  ? tr_sym(LV_SYMBOL_OK, RS_STOCK_SAVED_NOTE)
			  : tr_sym(LV_SYMBOL_CLOSE, RS_STOCK_NONE_NOTE));
	lv_obj_set_style_text_color(sk.note, saved ? C_OK : C_WARN, 0);
}

static void page_stock(void)
{
	memset(&sk, 0, sizeof(sk));
	lv_obj_t *body = page_frame(tr(RS_RESTORE_STOCK_FIRMWARE), true);
	lv_obj_t *c = card(body);
	lv_obj_set_width(c, lv_pct(100));
	lv_obj_set_flex_grow(c, 1);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_all(c, 18, 0);
	lv_obj_set_style_pad_row(c, 12, 0);
	label(c, tr_sym(LV_SYMBOL_WARNING, RS_STOCK_BACK_TITLE), F24B, C_WARN);
	wrap_label(c, tr(RS_STOCK_TEXT), F20, C_TEXT);
	sk.note = wrap_label(c, "", F20, C_MUTED);
	wrap_label(c, tr(RS_STOCK_BACKUP_FIRST), F16, C_MUTED);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	sk.dry = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_CHECK), 0, on_stock_dry, NULL);
	lv_obj_set_width(sk.dry, 200);
	sk.go = button(row, LV_SYMBOL_WARNING, tr(RS_RESTORE_STOCK_FW_BTN), 2, on_stock,
		       NULL);
	lv_obj_set_flex_grow(sk.go, 1);
	cur_refresh = stock_refresh;
}

/* ---------------------------------------------------------- network page */

static struct {
	lv_obj_t *rows, *qr, *qrl, *info;
	capture *cap;
	unsigned seen;
	char url[96];
} nw;

static void nw_row(const char *k, const char *v, lv_color_t vc)
{
	lv_obj_t *r = box(nw.rows, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_t *kl = label(r, k, F20, C_MUTED);
	lv_obj_set_width(kl, 120);
	lv_obj_t *vl = label(r, v, F24B, vc);
	lv_label_set_long_mode(vl, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_flex_grow(vl, 1);
}

static void nw_fill(void)
{
	lv_obj_clean(nw.rows);
	char ip[64], ifc[16], mode[16], t[200], v[64], host[64] = "ad5x";
	gethostname(host, sizeof(host));
	bool have = cur_ip(ip, sizeof(ip), ifc, sizeof(ifc));
	if (have) {
		bool m = kv("net_mode", mode, sizeof(mode));
		snprintf(t, sizeof(t), "%s  (%s%s%s)", ip, ifc, m ? ", " : "", m ? mode : "");
		nw_row(tr(RS_ADDRESS), t, C_TEXT);
	} else {
		nw_row(tr(RS_ADDRESS), tr(RS_NO_NETWORK), C_MUTED);
	}
	nw_row(tr(RS_NAME), host, C_TEXT);
	bool ssh_up = !kv("ssh", v, sizeof(v)) || !strcmp(v, "running");
	if (have && ssh_up)
		snprintf(t, sizeof(t), "ssh root@%s", ip);
	else
		snprintf(t, sizeof(t), "%s", ssh_up ? tr(RS_NO_NETWORK) : tr(RS_NOT_RUNNING));
	nw_row("SSH", t, have && ssh_up ? C_ACCENT : C_MUTED);
	char port[16] = "8080";
	kv("web_port", port, sizeof(port));
	if (have) {
		snprintf(nw.url, sizeof(nw.url), "http://%s:%s", ip, port);
		nw_row(tr(RS_UPLOAD), nw.url, C_ACCENT);
		lv_qrcode_update(nw.qr, nw.url, strlen(nw.url));
		show(nw.qr, true);
		lv_label_set_text(nw.qrl, tr(RS_UPDATE_UPLOAD_PAGE));
	} else {
		nw_row(tr(RS_UPLOAD), tr(RS_NO_NETWORK), C_MUTED);
		show(nw.qr, false);
		lv_label_set_text(nw.qrl, tr(RS_PLUG_IN));
	}
	if (kv("release", v, sizeof(v)))
		nw_row(tr(RS_RECOVERY_ROW), v, C_TEXT);
}

/* `ad5x-usb list` lines -> a short USB / rescue summary */
static void nw_usb(const char *list)
{
	char out[600] = "";
	for (const char *l = list; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL) {
		char line[400], dev[64] = "", fs[16] = "", swu[200] = "", *save = NULL;
		int rr = 0, rb = 0, rf = 0, au = 0;
		snprintf(line, sizeof(line), "%.*s", (int)strcspn(l, "\n"), l);
		for (char *w = strtok_r(line, " ", &save); w; w = strtok_r(NULL, " ", &save)) {
			if (!strncmp(w, "dev=", 4)) snprintf(dev, sizeof(dev), "%s", w + 4);
			else if (!strncmp(w, "fs=", 3)) snprintf(fs, sizeof(fs), "%s", w + 3);
			else if (!strncmp(w, "swu=", 4)) snprintf(swu, sizeof(swu), "%s", w + 4);
			else if (!strncmp(w, "rescue_root=", 12)) rr = atoi(w + 12);
			else if (!strncmp(w, "rescue_boot=", 12)) rb = atoi(w + 12);
			else if (!strncmp(w, "rescue_flash=", 13)) rf = atoi(w + 13);
			else if (!strncmp(w, "autoupdate=", 11)) au = atoi(w + 11);
		}
		if (!dev[0])
			continue;
		int nswu = 0;
		for (const char *p = swu; *p; p++)
			nswu += *p == ',';
		nswu += swu[0] != 0;
		size_t n = strlen(out);
		snprintf(out + n, sizeof(out) - n, tr(RS_USB_SUMMARY), n ? "\n" : "", dev, fs, nswu,
			nswu == 1 ? tr(RS_UPDATE_ONE) : tr(RS_UPDATE_MANY));
		n = strlen(out);
		if (rr)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_RESCUE_SYSTEM));
		n = strlen(out);
		if (rb)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_RESCUE_BOOT));
		n = strlen(out);
		if (rf)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_RESCUE_FLASH));
		n = strlen(out);
		if (au)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_AUTOUPDATE));
	}
	lv_label_set_text(nw.info, out[0] ? out : tr(RS_USB_NO_STICK));
}

static void nw_refresh(void)
{
	if (nw.cap && capture_done(nw.cap)) {
		nw_usb(capture_text(nw.cap));
		capture_free(nw.cap);
		nw.cap = NULL;
	}
	if (nw.seen != stc.seq + 1) {
		nw.seen = stc.seq + 1;
		nw_fill();
	}
}

static void nw_free(lv_event_t *e)
{
	(void)e;
	capture_free(nw.cap);
	nw.cap = NULL;
}

static void page_network(void)
{
	memset(&nw, 0, sizeof(nw));
	lv_obj_t *body = page_frame(tr(RS_NETWORK_SSH), true);
	lv_obj_add_event_cb(scr, nw_free, LV_EVENT_DELETE, NULL);
	lv_obj_t *cols = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_width(cols, lv_pct(100));
	lv_obj_set_flex_grow(cols, 1);
	lv_obj_set_style_pad_column(cols, 12, 0);
	lv_obj_t *left = card(cols);
	lv_obj_set_height(left, lv_pct(100));
	lv_obj_set_flex_grow(left, 1);
	lv_obj_set_flex_flow(left, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_all(left, 16, 0);
	lv_obj_set_style_pad_row(left, 10, 0);
	nw.rows = box(left, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_size(nw.rows, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_row(nw.rows, 8, 0);
	nw.info = wrap_label(left, "", F16, C_MUTED);
	wrap_label(left, tr(RS_SSH_LOGIN_TEXT), F16, C_MUTED);

	lv_obj_t *right = card(cols);
	lv_obj_set_size(right, 236, lv_pct(100));
	lv_obj_set_flex_flow(right, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_flex_align(right, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
			      LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_row(right, 12, 0);
	nw.qr = lv_qrcode_create(right);
	lv_qrcode_set_size(nw.qr, 196);
	lv_qrcode_set_dark_color(nw.qr, lv_color_black());
	lv_qrcode_set_light_color(nw.qr, lv_color_white());
	lv_obj_set_style_border_color(nw.qr, lv_color_white(), 0);
	lv_obj_set_style_border_width(nw.qr, 6, 0);
	nw.qrl = wrap_label(right, "", F16, C_MUTED);
	lv_obj_set_style_text_align(nw.qrl, LV_TEXT_ALIGN_CENTER, 0);

	char *c = cmd_expand(CMD_USB_LIST, NULL);
	nw.cap = capture_start(c, 2048);
	free(c);
	cur_refresh = nw_refresh;
}

/* ------------------------------------------------------------- logs page */

enum { LOG_SESSION, LOG_UPDATE, LOG_SWU, LOG_SYSTEM, LOG_N };
static struct {
	int which;
	lv_obj_t *tabs[LOG_N], *view, *text;
	capture *cap;
	unsigned seen;
	char *buf;
} lg;

#define LOG_CAP (24 * 1024)

static void lg_set(const char *t)
{
	lv_label_set_text(lg.text, t && *t ? t : tr(RS_EMPTY_LOG));
	lv_obj_update_layout(lg.view);
	lv_obj_scroll_to_y(lg.view, LV_COORD_MAX, LV_ANIM_OFF);
}

static void lg_load(void)
{
	for (int i = 0; i < LOG_N; i++)
		if (i == lg.which)
			lv_obj_add_state(lg.tabs[i], LV_STATE_CHECKED);
		else
			lv_obj_remove_state(lg.tabs[i], LV_STATE_CHECKED);
	capture_free(lg.cap);
	lg.cap = NULL;
	switch (lg.which) {
	case LOG_SESSION:
		lg.seen = slog_seq();
		slog_copy(lg.buf, LOG_CAP);
		lg_set(lg.buf);
		break;
	case LOG_SYSTEM: {
		char *c = cmd_expand(CMD_SYSLOG, NULL);
		lg.cap = capture_start(c, LOG_CAP);
		free(c);
		lv_label_set_text(lg.text, tr(RS_READING));
		break;
	}
	case LOG_UPDATE:
	case LOG_SWU: {
		char *q = sh_quote(rui_get(lg.which == LOG_SWU ? PATH_SWU_LOG : PATH_LAST_LOG));
		char cmd[600];
		snprintf(cmd, sizeof(cmd), "tail -n 300 %s 2>&1", q);
		free(q);
		lg.cap = capture_start(cmd, LOG_CAP);
		lv_label_set_text(lg.text, tr(RS_READING));
		break;
	}
	}
}

static void lg_refresh(void)
{
	if (lg.cap && capture_done(lg.cap)) {
		lg_set(capture_text(lg.cap));
		capture_free(lg.cap);
		lg.cap = NULL;
	}
	if (lg.which == LOG_SESSION && slog_seq() != lg.seen)
		lg_load();
}

static void on_lg_tab(lv_event_t *e)
{
	lg.which = (int)(intptr_t)lv_event_get_user_data(e);
	lg_load();
}

static void lg_free(lv_event_t *e)
{
	(void)e;
	capture_free(lg.cap);
	lg.cap = NULL;
}

static void page_logs(void)
{
	if (!lg.buf)
		lg.buf = malloc(LOG_CAP);
	lg.cap = NULL;
	lv_obj_t *body = page_frame(tr(RS_LOGS), true);
	lv_obj_add_event_cb(scr, lg_free, LV_EVENT_DELETE, NULL);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 10, 0);
	static const enum rui_str names[LOG_N] = { RS_LOGS_TAB_SESSION, RS_LOGS_TAB_UPDATES, RS_LOGS_TAB_SWUPDATE, RS_LOGS_TAB_SYSTEM };
	for (int i = 0; i < LOG_N; i++) {
		lg.tabs[i] = button(row, NULL, tr(names[i]), 0, on_lg_tab, (void *)(intptr_t)i);
		lv_obj_set_flex_grow(lg.tabs[i], 1);
		lv_obj_set_height(lg.tabs[i], 52);
		lv_obj_set_style_bg_color(lg.tabs[i], C_ACCENT, LV_STATE_CHECKED);
	}
	lg.view = card(body);
	lv_obj_set_width(lg.view, lv_pct(100));
	lv_obj_set_flex_grow(lg.view, 1);
	lv_obj_add_flag(lg.view, LV_OBJ_FLAG_SCROLLABLE);
	lv_obj_set_scroll_dir(lg.view, LV_DIR_VER);
	lv_obj_set_style_bg_color(lg.view, lv_color_make(12, 15, 20), 0);
	lg.text = wrap_label(lg.view, "", FMONO, lv_color_make(205, 214, 226));
	lg_load();
	cur_refresh = lg_refresh;
}

/* ------------------------------------------------------------ power page */

static void reboot_now(void)
{
	char *c = cmd_expand(CMD_REBOOT, NULL);
	start_job(JK_CMD, tr(RS_REBOOTING), "", c, false, true);
	free(c);
}

static void poweroff_now(void)
{
	char *c = cmd_expand(CMD_POWEROFF, NULL);
	start_job(JK_CMD, tr(RS_SHUTTING_DOWN), "", c, false, true);
	free(c);
}

static void on_reboot(lv_event_t *e)
{
	(void)e;
	char flag[32];
	const char *where = (kv("flag", flag, sizeof(flag)) || sys_ota_flag(flag, sizeof(flag))) &&
			    !strcmp(flag, "ota:kernel2")
			    ? tr(RS_REBOOT_MAIN)
			    : tr(RS_REBOOT_RECOVERY);
	static char t[200];
	snprintf(t, sizeof(t), tr(RS_REBOOT_TEXT), where);
	confirm(tr(RS_REBOOT_Q), t, tr_sym(LV_SYMBOL_REFRESH, RS_REBOOT), false, NULL, reboot_now);
}

static void on_poweroff(lv_event_t *e)
{
	(void)e;
	confirm(tr(RS_SHUTDOWN_Q), tr(RS_SHUTDOWN_TEXT), tr_sym(LV_SYMBOL_POWER, RS_SHUT_DOWN),
		false, NULL, poweroff_now);
}

static void page_power(void)
{
	lv_obj_t *body = page_frame(tr(RS_REBOOT_POWER), true);
	lv_obj_t *c = card(body);
	lv_obj_set_width(c, lv_pct(100));
	lv_obj_set_flex_grow(c, 1);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_all(c, 18, 0);
	lv_obj_set_style_pad_row(c, 10, 0);
	label(c, tr_sym(LV_SYMBOL_POWER, RS_POWER), F24B, C_TEXT);
	wrap_label(c, tr(RS_POWER_TEXT), F20, C_TEXT);
	wrap_label(c, tr(RS_POWER_TEXT2), F20, C_MUTED);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	lv_obj_t *b1 = button(row, LV_SYMBOL_PLAY, tr(RS_BOOT_MAIN_OS), 1, on_boot_main, NULL);
	lv_obj_t *b2 = button(row, LV_SYMBOL_REFRESH, tr(RS_REBOOT), 0, on_reboot, NULL);
	lv_obj_t *b3 = button(row, LV_SYMBOL_POWER, tr(RS_SHUT_DOWN), 0, on_poweroff, NULL);
	lv_obj_set_flex_grow(b1, 1);
	lv_obj_set_flex_grow(b2, 1);
	lv_obj_set_flex_grow(b3, 1);
}

/* -------------------------------------------------------------- job page */

static struct {
	lv_obj_t *status, *step, *bar, *pct, *spin, *log, *logtext, *cancel, *done, *boot;
	lv_obj_t *banner;
	char *buf;
	bool ended;
	bool after_reboot;	/* the after-button reboots instead of ad5x-boot-main */
} jp;

#define JOB_VIEW_CAP 8192

static void reboot_now(void);

static void on_after(lv_event_t *e)
{
	if (jp.after_reboot)
		confirm(tr(RS_REBOOT_Q), tr(RS_REBOOT_INTO_FLAG), tr_sym(LV_SYMBOL_REFRESH, RS_REBOOT),
			false, NULL, reboot_now);
	else
		on_boot_main(e);
}

static void on_cancel(lv_event_t *e)
{
	(void)e;
	job_cancel();
}

static void job_banner(bool ok, const char *text)
{
	lv_obj_set_style_bg_color(jp.banner, ok ? lv_color_make(28, 74, 40)
						 : lv_color_make(92, 32, 30), 0);
	lv_obj_set_style_border_color(jp.banner, ok ? C_OK : C_DANGER, 0);
	lv_label_set_text(jp.status, text);
	lv_obj_set_style_text_color(jp.status, ok ? lv_color_make(160, 230, 160)
						  : lv_color_make(255, 170, 160), 0);
}

static void job_refresh(void)
{
	job_state js;
	swu_state ss;
	if (jb.pending) {
		if (status_busy()) {
			lv_label_set_text(jp.step, tr(RS_WAITING_STATUS));
			return;
		}
		jb.started = job_start(jb.title, jb.pending);
		jb.failed_start = !jb.started;
		free(jb.pending);
		jb.pending = NULL;
	}
	job_poll(&js);
	swu_get(&ss);
	bool swu_mode = jb.kind == JK_INSTALL || jb.kind == JK_WEB;
	bool swu_fresh = ss.seq != jb.swu_seq_at_start;

	if (js.seq != jb.last_seq || ss.seq != jb.last_swu) {
		jb.last_seq = js.seq;
		jb.last_swu = ss.seq;
		if (jb.kind != JK_WEB) {
			job_output(jp.buf, JOB_VIEW_CAP);
			lv_label_set_text(jp.logtext, jp.buf[0] ? jp.buf : "\xe2\x80\xa6");
		} else {
			swu_log_copy(jp.buf, JOB_VIEW_CAP);
			lv_label_set_text(jp.logtext, jp.buf);
		}
		lv_obj_update_layout(jp.log);
		lv_obj_scroll_to_y(jp.log, LV_COORD_MAX, LV_ANIM_OFF);
	}

	/* Progress: SWUpdate's for installs, else the command's output */
	int pct = js.progress;
	char step[256] = "";
	if (swu_mode && swu_fresh) {
		pct = ss.overall;
		if (ss.status == SWU_DOWNLOAD)
			snprintf(step, sizeof(step), tr(RS_RECEIVING), ss.dwl_percent);
		else if (ss.nsteps)
			snprintf(step, sizeof(step), tr(RS_STEP_FMT), ss.cur_step,
				 ss.nsteps, ss.image[0] ? ss.image : tr(RS_PREPARING),
				 ss.handler[0] ? " (" : "", ss.handler, ss.handler[0] ? ")" : "");
		else
			snprintf(step, sizeof(step), tr(RS_SWU_STATUS), swu_status_tr(ss.status));
	} else if (js.step[0]) {
		snprintf(step, sizeof(step), "%s", js.step);
	} else if (jb.what[0]) {
		snprintf(step, sizeof(step), "%s", jb.what);
	}
	if (!jp.ended)
		lv_label_set_text(jp.step, step);

	bool have_result = ss.result_seq != jb.swu_result_at_start;
	bool running = jb.kind == JK_WEB ? ss.active : js.running;
	bool ended = !running && (jb.kind == JK_WEB ? have_result
				  : js.finished || jb.failed_start);

	if (jp.ended) {
		/* result shown, nothing more to update */
	} else if (pct >= 0) {
		show(jp.bar, true);
		lv_bar_set_value(jp.bar, pct, LV_ANIM_OFF);
		lv_label_set_text_fmt(jp.pct, "%d%%", pct);
	} else {
		show(jp.bar, running);
		lv_bar_set_value(jp.bar, 0, LV_ANIM_OFF);
		lv_label_set_text(jp.pct, "");
	}
	show(jp.spin, running);

	if (running) {
		if (!jp.ended)
			lv_label_set_text(jp.status, jb.reboots ? tr(RS_RESTARTING)
					  : jb.critical || jb.kind == JK_WEB
					  ? tr(RS_WORKING_DONT_OFF)
					  : tr(RS_WORKING));
		show(jp.cancel, jb.cancelable);
		show(jp.done, false);
		show(jp.boot, false);
		enable(back_btn, false);
		return;
	}
	if (!ended || jp.ended)
		return;
	jp.ended = true;
	bool ok;
	if (jb.kind == JK_WEB)
		ok = ss.result == SWU_SUCCESS;
	else if (jb.kind == JK_INSTALL)
		ok = js.exit_code == 0 && !(have_result && ss.result == SWU_FAILURE);
	else
		ok = js.exit_code == 0;
	char msg[200];
	if (jb.failed_start)
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", "%s", tr(RS_COULD_NOT_START));
	else if (ok)
		iconed(msg, sizeof(msg), LV_SYMBOL_OK, "  ", tr(RS_JOB_DONE), jb.title);
	else if (js.exit_code < 0 && jb.kind != JK_WEB)
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", tr(RS_JOB_STOPPED), jb.title);
	else if (jb.kind == JK_WEB)
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", "%s", tr(RS_UPDATE_FAILED));
	else
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", tr(RS_JOB_FAILED), jb.title,
			js.exit_code);
	job_banner(ok, msg);
	if (ok) {
		show(jp.bar, true);
		lv_bar_set_value(jp.bar, 100, LV_ANIM_OFF);
		lv_label_set_text(jp.pct, "100%");
	}
	slog("%s", msg + 5);
	/* The tools' last line is their result ("backup: OK <dir>",
	 * "swu-apply: FAILED ..."): show it under the banner */
	if (jb.kind != JK_WEB) {
		const char *t = jp.buf, *last = NULL;
		for (const char *p = t; *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : p + strlen(p))
			if (*p != '\n')
				last = p;
		if (last)
			lv_label_set_text_fmt(jp.step, "%.*s", (int)strcspn(last, "\n"), last);
	}
	show(jp.spin, false);
	show(jp.cancel, false);
	show(jp.done, true);
	if (ok && (jb.after == AFTER_BOOT_MAIN || (jb.kind == JK_WEB))) {
		lv_label_set_text(lv_obj_get_child(jp.boot, 0), tr_sym(LV_SYMBOL_PLAY, RS_BOOT_MAIN_OS));
		jp.after_reboot = false;
		show(jp.boot, true);
	} else if (ok && jb.after == AFTER_REBOOT) {
		lv_label_set_text(lv_obj_get_child(jp.boot, 0), tr_sym(LV_SYMBOL_REFRESH, RS_REBOOT));
		jp.after_reboot = true;
		show(jp.boot, true);
	}
	enable(back_btn, true);
	status_kick(true);
}

static void page_job(void)
{
	memset(&jp, 0, sizeof(jp));
	static char buf[JOB_VIEW_CAP];
	jp.buf = buf;
	buf[0] = 0;
	lv_obj_t *body = page_frame(jb.kind == JK_WEB ? tr(RS_UPDATE_FROM_BROWSER) : jb.title, true);

	jp.banner = card(body);
	lv_obj_set_size(jp.banner, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_flow(jp.banner, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(jp.banner, 8, 0);
	lv_obj_set_style_border_width(jp.banner, 2, 0);
	lv_obj_t *r = box(jp.banner, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(r, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(r, 12, 0);
	jp.spin = lv_spinner_create(r);
	lv_obj_set_size(jp.spin, 32, 32);
	lv_obj_set_style_arc_width(jp.spin, 4, LV_PART_MAIN);
	lv_obj_set_style_arc_width(jp.spin, 4, LV_PART_INDICATOR);
	lv_obj_set_style_arc_color(jp.spin, C_ACCENT, LV_PART_INDICATOR);
	jp.status = label(r, tr(RS_WORKING), F24B, C_TEXT);
	lv_obj_set_flex_grow(jp.status, 1);
	jp.pct = label(r, "", F24B, C_TEXT);
	jp.step = label(jp.banner, "", F20, C_MUTED);
	lv_label_set_long_mode(jp.step, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_width(jp.step, lv_pct(100));
	jp.bar = lv_bar_create(jp.banner);
	lv_obj_set_size(jp.bar, lv_pct(100), 22);
	lv_bar_set_range(jp.bar, 0, 100);
	lv_obj_set_style_bg_color(jp.bar, lv_color_make(20, 26, 34), LV_PART_MAIN);
	lv_obj_set_style_bg_color(jp.bar, C_ACCENT, LV_PART_INDICATOR);
	lv_obj_set_style_radius(jp.bar, 8, LV_PART_MAIN);
	lv_obj_set_style_radius(jp.bar, 8, LV_PART_INDICATOR);

	jp.log = card(body);
	lv_obj_set_width(jp.log, lv_pct(100));
	lv_obj_set_flex_grow(jp.log, 1);
	lv_obj_add_flag(jp.log, LV_OBJ_FLAG_SCROLLABLE);
	lv_obj_set_scroll_dir(jp.log, LV_DIR_VER);
	lv_obj_set_style_bg_color(jp.log, lv_color_make(12, 15, 20), 0);
	jp.logtext = wrap_label(jp.log, "", FMONO, lv_color_make(205, 214, 226));

	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	lv_obj_set_flex_align(row, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	jp.cancel = button(row, LV_SYMBOL_STOP, tr(RS_STOP), 2, on_cancel, NULL);
	lv_obj_set_width(jp.cancel, 200);
	jp.boot = button(row, LV_SYMBOL_PLAY, tr(RS_BOOT_MAIN_OS), 1, on_after, NULL);
	lv_obj_set_width(jp.boot, 260);
	jp.done = button(row, LV_SYMBOL_OK, tr(RS_DONE), 0, on_home, NULL);
	lv_obj_set_width(jp.done, 200);
	show(jp.cancel, false);
	show(jp.boot, false);
	show(jp.done, false);
	jb.last_seq = jb.last_swu = ~0u;
	cur_refresh = job_refresh;
}

/* ------------------------------------------------------------------ tick */

static void tick(lv_timer_t *t)
{
	(void)t;
	/* An update started elsewhere (browser upload on :8080): follow it */
	swu_state s;
	swu_get(&s);
	static unsigned seen;
	if (s.seq != seen) {
		seen = s.seq;
		if (s.active && cur_page != page_job && !job_running()) {
			memset(&jb, 0, sizeof(jb));
			jb.kind = JK_WEB;
			snprintf(jb.title, sizeof(jb.title), "%s", tr(RS_UPDATE));
			jb.swu_seq_at_start = s.seq - 1;
			jb.swu_result_at_start = s.result_seq;
			go(page_job);
		}
	}
	status_poll();
	if (cur_refresh)
		cur_refresh();
}

void ui_init(lv_display_t *disp)
{
	i18n_set_lang(lang_from_settings_file(rui_get(PATH_SETTINGS)));
	fonts_init();
	lv_theme_t *th = lv_theme_default_init(disp, C_ACCENT, C_DANGER, true, F20);
	lv_display_set_theme(disp, th);
	go(page_home);
	lv_timer_create(tick, 250, NULL);
	slog("ad5x-recovery-ui started");
}

/* ---------------------------------------------------------- screenshots */

static void settle(int ms)
{
	for (int t = 0; t < ms; t += 20) {
		lv_timer_handler();
		usleep(20000);
	}
}

static void wait_job(void)
{
	for (int i = 0; i < 500 && (job_running() || jb.pending); i++)
		settle(20);
	settle(300);
}

static void click(lv_obj_t *o)
{
	lv_obj_send_event(o, LV_EVENT_CLICKED, NULL);
	settle(100);
}

void ui_run_shots(void (*shot)(const char *name))
{
	settle(300);
	shot("01-home");

	go(page_update);
	settle(200);
	if (up.n > 0) {
		up.sel = 0;
		select_row(up.list, 0);
		up_buttons();
	}
	settle(400);
	shot("02-install-pick");
	click(up.install);
	shot("03-install-confirm1");
	click(dlg.ok_btn);
	shot("04-install-confirm2");
	settle(2400);
	shot("05-install-confirm2-armed");
	dlg_close();

	/* Install as it looks mid-way (SWUpdate progress injected) */
	start_job_x(JK_INSTALL, tr(RS_INSTALLING_UPDATE), "/data/ad5x/update/kiln-os.swu",
		    "echo 'swu-apply: /data/ad5x/update/kiln-os.swu via the daemon'; sleep 30",
		    false, false, true, AFTER_BOOT_MAIN);
	swu_inject(SWU_START, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	swu_inject(SWU_RUN, SWU_SRC_LOCAL, 3, 2, 40, "rootfs.squashfs", "Writing rootfs2");
	settle(400);
	shot("06-install-progress");
	job_cancel();
	wait_job();
	swu_inject(SWU_SUCCESS, SWU_SRC_LOCAL, 3, 3, 100, "kernel.uimage", NULL);
	swu_inject(SWU_IDLE, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);

	start_job_x(JK_INSTALL, tr(RS_INSTALLING_UPDATE), "/data/ad5x/update/kiln-os.swu",
		    "echo 'swu-apply: /data/ad5x/update/kiln-os.swu via the daemon'; "
		    "echo 'swu-apply: OK'", false, false, true, AFTER_BOOT_MAIN);
	swu_inject(SWU_START, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	swu_inject(SWU_SUCCESS, SWU_SRC_LOCAL, 3, 3, 100, "kernel.uimage", NULL);
	wait_job();
	shot("07-install-done");

	go(page_backup);
	settle(300);
	shot("08-backup");
	bk_run(false);
	settle(1500);
	shot("09-backup-running");
	wait_job();
	shot("10-backup-done");

	go(page_restore);
	settle(300);
	if (rs.n > 0) {
		rs.sel = 0;
		select_row(rs.list, 0);
		rs_fill_parts();
		/* tick kernel2 + rootfs2 (the simulated restore fails on rootfs2) */
		uint32_t n = lv_obj_get_child_count(rs.parts);
		for (uint32_t i = 0; i < n; i++) {
			lv_obj_t *c = lv_obj_get_child(rs.parts, i);
			if (lv_obj_check_type(c, &lv_checkbox_class) &&
			    strstr(lv_checkbox_get_text(c), "2")) {
				lv_obj_add_state(c, LV_STATE_CHECKED);
				lv_obj_send_event(c, LV_EVENT_VALUE_CHANGED, NULL);
			}
		}
	}
	settle(400);
	shot("11-restore-pick");
	click(rs.go);
	shot("12-restore-confirm1");
	click(dlg.ok_btn);
	settle(2400);
	shot("13-restore-confirm2");
	dlg_close();
	rs_run(false);
	wait_job();
	shot("14-restore-failed");

	go(page_stock);
	settle(200);
	shot("15-stock");
	on_stock(NULL);
	settle(100);
	shot("16-stock-confirm1");
	dlg_close();

	go(page_network);
	settle(600);
	shot("17-network");

	go(page_logs);
	settle(300);
	shot("18-logs-session");
	lg.which = LOG_SYSTEM;
	lg_load();
	settle(600);
	shot("19-logs-system");

	go(page_power);
	settle(200);
	shot("20-power");
	on_reboot(NULL);
	settle(100);
	shot("21-reboot-confirm");
	dlg_close();

	/* A browser upload arriving while on the home screen */
	go(page_home);
	settle(200);
	swu_inject(SWU_START, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);
	swu_inject(SWU_DOWNLOAD, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);
	settle(400);
	swu_inject(SWU_RUN, SWU_SRC_WEBSERVER, 3, 1, 70, "kernel.uimage", NULL);
	settle(400);
	shot("22-web-upload");
	swu_inject(SWU_SUCCESS, SWU_SRC_WEBSERVER, 3, 3, 100, "rootfs.squashfs", NULL);
	settle(400);
	shot("23-web-upload-done");
	swu_inject(SWU_IDLE, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);

	go(page_home);
	settle(300);
	shot("24-home-again");
}
